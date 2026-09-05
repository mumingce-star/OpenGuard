"""FastAPI application factory for the frozen OpenGuard P0 routes."""

from __future__ import annotations

import os
import stat
from base64 import b64encode
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Annotated, AsyncIterator, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from fastapi.responses import JSONResponse, Response
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai import OllamaProvider
from app.api.models import (
    ErrorBody,
    ErrorEnvelope,
    GitScanCreateRequest,
    ResourceFilters,
    ResourcesResponse,
    RiskFilters,
    RisksResponse,
    ScanCreateAccepted,
    ScanRunStatusView,
    ZipScanCreateFields,
)
from app.api.service import APPLICATION_VERSION, ApiError, ScanApiService
from app.api.git_scan import GitScanRuntime
from app.api.zip_scan import MULTIPART_REQUEST_MAX_BYTES, RequestBodyTooLarge, ZipScanRuntime
from app.domain.models import Evidence, FindingOutcome, ReportFormat, ReportLink, Severity, VerificationStatus
from app.persistence import SQLiteScanRunRegistry
from app.reporting import PipelineReportPublisher, ReportArtifactStore


_ERROR_RESPONSES = {
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid4()}")


def _error_response(request: Request, error: ApiError) -> JSONResponse:
    request_id = _request_id(request)
    payload = ErrorEnvelope(
        error=ErrorBody(
            code=error.code,
            message=error.message,
            request_id=request_id,
            details={"reason": error.reason},
        )
    )
    return JSONResponse(
        status_code=error.status_code,
        content=payload.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


def _service(request: Request) -> ScanApiService:
    return request.app.state.scan_api_service


def _router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post(
        "/scans",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=ScanCreateAccepted,
        responses=_ERROR_RESPONSES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["source_type", "source"],
                            "properties": {
                                "source_type": {"type": "string", "const": "git"},
                                "source": {"type": "string", "minLength": 1, "maxLength": 2048},
                                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["source_type", "file"],
                            "properties": {
                                "source_type": {"type": "string", "const": "zip"},
                                "file": {"type": "string", "format": "binary"},
                                "idempotency_key": {"type": "string", "minLength": 1, "maxLength": 200},
                            },
                            "additionalProperties": False,
                        }
                    },
                },
            }
        },
    )
    async def create_scan(
        request: Request,
        background_tasks: BackgroundTasks,
        service: Annotated[ScanApiService, Depends(_service)],
    ) -> ScanCreateAccepted:
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type == "application/json":
            try:
                body = GitScanCreateRequest.model_validate(await request.json())
            except Exception:
                raise ApiError(
                    status_code=422,
                    code="invalid_source",
                    message="Request parameters are invalid.",
                    reason="request_invalid",
                ) from None
            runtime: GitScanRuntime | None = request.app.state.git_scan_runtime
            if runtime is None:
                return service.create_git_scan(body)
            return runtime.submit(body, service, background_tasks)

        if media_type == "multipart/form-data":
            runtime: ZipScanRuntime | None = request.app.state.zip_scan_runtime
            if runtime is None:
                raise ApiError(
                    status_code=500,
                    code="internal_error",
                    message="ZIP scanning is unavailable.",
                    reason="zip_runtime_unavailable",
                )
            try:
                async with request.form(max_files=1, max_fields=2, max_part_size=64 * 1024 * 1024) as form:
                    grouped: dict[str, list[object]] = {}
                    for key, value in form.multi_items():
                        grouped.setdefault(key, []).append(value)
                    if set(grouped) - {"source_type", "idempotency_key", "file"}:
                        raise ValueError
                    if len(grouped.get("source_type", [])) != 1 or len(grouped.get("file", [])) != 1:
                        raise ValueError
                    if len(grouped.get("idempotency_key", [])) > 1:
                        raise ValueError
                    source_type = grouped["source_type"][0]
                    idempotency = grouped.get("idempotency_key", [None])[0]
                    upload = grouped["file"][0]
                    if type(source_type) is not str or (idempotency is not None and type(idempotency) is not str):
                        raise ValueError
                    if not isinstance(upload, UploadFile):
                        raise ValueError
                    fields = ZipScanCreateFields(
                        source_type=source_type,
                        idempotency_key=idempotency,
                    )
                    return await runtime.submit(upload, fields, service, background_tasks)
            except ApiError:
                raise
            except RequestBodyTooLarge:
                raise ApiError(
                    status_code=413,
                    code="archive_limit_exceeded",
                    message="ZIP upload exceeds the configured limit.",
                    reason="archive_upload_size_limit",
                ) from None
            except (ValidationError, ValueError, StarletteHTTPException):
                raise ApiError(
                    status_code=422,
                    code="invalid_archive",
                    message="ZIP upload is invalid.",
                    reason="request_invalid",
                ) from None

        raise ApiError(
            status_code=415,
            code="invalid_source",
            message="Request content type is not supported.",
            reason="unsupported_media_type",
        )

    @router.get("/scans/{scan_id}", response_model=ScanRunStatusView, responses=_ERROR_RESPONSES)
    def get_scan(
        scan_id: str,
        service: Annotated[ScanApiService, Depends(_service)],
    ) -> ScanRunStatusView:
        return service.status(scan_id)

    @router.get("/scans/{scan_id}/resources", response_model=ResourcesResponse, responses=_ERROR_RESPONSES)
    def get_resources(
        scan_id: str,
        service: Annotated[ScanApiService, Depends(_service)],
        kind: Annotated[Literal["component", "ai_asset"] | None, Query()] = None,
        ecosystem: Annotated[Literal["pypi", "npm", "unknown"] | None, Query()] = None,
        provider: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
        verification_status: Annotated[VerificationStatus | None, Query()] = None,
    ) -> ResourcesResponse:
        return service.resources(
            scan_id,
            ResourceFilters(
                kind=kind,
                ecosystem=ecosystem,
                provider=provider,
                verification_status=verification_status,
            ),
        )

    @router.get("/scans/{scan_id}/risks", response_model=RisksResponse, responses=_ERROR_RESPONSES)
    def get_risks(
        scan_id: str,
        service: Annotated[ScanApiService, Depends(_service)],
        outcome: Annotated[FindingOutcome | None, Query()] = None,
        severity: Annotated[Severity | None, Query()] = None,
        resource_kind: Annotated[Literal["component", "ai_asset"] | None, Query()] = None,
    ) -> RisksResponse:
        return service.risks(
            scan_id,
            RiskFilters(outcome=outcome, severity=severity, resource_kind=resource_kind),
        )

    @router.get(
        "/scans/{scan_id}/evidence/{evidence_id}",
        response_model=Evidence,
        responses=_ERROR_RESPONSES,
    )
    def get_evidence(
        scan_id: str,
        evidence_id: str,
        service: Annotated[ScanApiService, Depends(_service)],
    ) -> Evidence:
        return service.evidence(scan_id, evidence_id)

    @router.get("/scans/{scan_id}/report", response_model=ReportLink, responses=_ERROR_RESPONSES)
    def get_report(
        scan_id: str,
        service: Annotated[ScanApiService, Depends(_service)],
        report_format: Annotated[ReportFormat, Query(alias="format")],
        download: Annotated[bool, Query()] = False,
    ) -> ReportLink | Response:
        if download:
            stored = service.download_report(scan_id, report_format)
            digest = b64encode(bytes.fromhex(stored.link.content_hash.value)).decode("ascii")
            return Response(
                content=stored.content,
                media_type=stored.media_type,
                headers={
                    "Cache-Control": "private, no-store",
                    "Content-Disposition": f'attachment; filename="{stored.filename}"',
                    "Content-Digest": f"sha-256=:{digest}:",
                    "Content-Security-Policy": "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'",
                    "ETag": f'"sha256:{stored.link.content_hash.value}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return service.report(scan_id, report_format)

    return router


def create_app(
    registry: SQLiteScanRunRegistry,
    *,
    zip_runtime: ZipScanRuntime | None = None,
    git_runtime: GitScanRuntime | None = None,
    report_store: ReportArtifactStore | None = None,
    close_registry: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if close_registry:
                registry.close()

    app = FastAPI(title="OpenGuard API", version=APPLICATION_VERSION, lifespan=lifespan)
    app.state.scan_api_service = ScanApiService(registry, report_store=report_store)
    app.state.zip_scan_runtime = zip_runtime
    app.state.git_scan_runtime = git_runtime

    @app.middleware("http")
    async def limit_zip_request_body(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if request.method == "POST" and request.url.path == "/api/v1/scans" and media_type == "multipart/form-data":
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared = int(content_length)
                except ValueError:
                    return _error_response(
                        request,
                        ApiError(
                            status_code=422,
                            code="invalid_archive",
                            message="ZIP upload is invalid.",
                            reason="request_invalid",
                        ),
                    )
                if declared < 0 or declared > MULTIPART_REQUEST_MAX_BYTES:
                    return _error_response(
                        request,
                        ApiError(
                            status_code=413,
                            code="archive_limit_exceeded",
                            message="ZIP upload exceeds the configured limit.",
                            reason="archive_upload_size_limit",
                        ),
                    )
            received = 0
            original_receive = request._receive

            async def receive() -> dict[str, object]:
                nonlocal received
                message = await original_receive()
                body = message.get("body", b"")
                if type(body) is not bytes:
                    raise RequestBodyTooLarge
                received += len(body)
                if received > MULTIPART_REQUEST_MAX_BYTES:
                    raise RequestBodyTooLarge
                return message

            request._receive = receive
        return await call_next(request)

    @app.middleware("http")
    async def add_request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = f"req_{uuid4()}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError) -> JSONResponse:
        return _error_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return _error_response(
            request,
            ApiError(
                status_code=422,
                code="invalid_source",
                message="Request parameters are invalid.",
                reason="request_invalid",
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 404:
            message = "The requested route was not found."
            reason = "route_not_found"
        elif error.status_code == 405:
            message = "The request method is not allowed."
            reason = "method_not_allowed"
        else:
            message = "The request could not be completed."
            reason = "http_error"
        return _error_response(
            request,
            ApiError(
                status_code=error.status_code,
                code="invalid_source",
                message=message,
                reason=reason,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
        return _error_response(
            request,
            ApiError(
                status_code=500,
                code="internal_error",
                message="The request could not be completed.",
                reason="unexpected_failure",
            ),
        )

    app.include_router(_router())
    return app


def create_default_app() -> FastAPI:
    configured = os.environ.get("OPENGUARD_DATA_DIR", "data")
    if not configured or "\x00" in configured:
        raise RuntimeError("invalid OPENGUARD_DATA_DIR")
    data_dir = Path(configured).resolve()
    try:
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = data_dir.lstat()
    except OSError as error:
        raise RuntimeError("OpenGuard data directory is unavailable") from error
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("OpenGuard data directory must be private")
    upload_root = data_dir / "uploads"
    workspace_root = data_dir / "workspaces"
    report_root = data_dir / "reports"
    for root in (upload_root, workspace_root, report_root):
        try:
            root.mkdir(mode=0o700, exist_ok=True)
            info = root.lstat()
        except OSError as error:
            raise RuntimeError("OpenGuard runtime directory is unavailable") from error
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError("OpenGuard runtime directory must be private")
    ai_enabled = os.environ.get("OPENGUARD_ENABLE_AI", "0")
    if ai_enabled not in {"0", "1"}:
        raise RuntimeError("invalid OPENGUARD_ENABLE_AI")
    registry = SQLiteScanRunRegistry(data_dir / "scans.db")
    report_store = ReportArtifactStore(report_root)
    ai_provider = OllamaProvider() if ai_enabled == "1" else None
    runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        report_publisher=PipelineReportPublisher(report_store),
        ai_provider=ai_provider,
        ai_enabled=ai_enabled == "1",
    )
    git_enabled = os.environ.get("OPENGUARD_ENABLE_PUBLIC_GIT", "0")
    if git_enabled not in {"0", "1"}:
        raise RuntimeError("invalid OPENGUARD_ENABLE_PUBLIC_GIT")
    git_runtime = (
        GitScanRuntime(
            registry,
            workspace_root=workspace_root,
            report_publisher=PipelineReportPublisher(report_store),
            ai_provider=ai_provider,
            ai_enabled=ai_enabled == "1",
        )
        if git_enabled == "1"
        else None
    )
    return create_app(
        registry,
        zip_runtime=runtime,
        git_runtime=git_runtime,
        report_store=report_store,
        close_registry=True,
    )


__all__ = ["create_app", "create_default_app"]
