"""FastAPI application factory for the frozen OpenGuard P0 routes."""

from __future__ import annotations
from app.domain.usage import UsageDeclaration

import os
import json
import stat
import secrets
import threading
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
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.p1.history import HistoryReader
from app.p1.models import P1HistoryPage, P1ScanDiffView, P1ResourceGraphView, P1GraphCapacityErrorEnvelope
from app.p1.graph import GraphReader, GraphCapacityError
from app.p1.models import P1TaskDeriveRequest, P1TaskPatchRequest, P1TaskCollection, P1TaskPage, P1RemediationTask
from app.p1.diff import DiffReader
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
from app.persistence import SQLiteScanRunRegistry, ZipDispatchStore
from app.pipeline.zip_dispatcher import ZipDispatcher
from app.reporting import PipelineReportPublisher, ReportArtifactStore


_P1_GRAPH_MAX_NODES = 20_000
_P1_GRAPH_MAX_EDGES = 60_000

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
    if isinstance(error, GraphCapacityError):
        payload = P1GraphCapacityErrorEnvelope.model_validate({"error": {
            "code": error.code, "message": error.message, "request_id": request_id,
            "details": {"reason": error.reason, **error.capacity_details},
        }})
        return JSONResponse(status_code=413, content=payload.model_dump(mode="json"),
                            headers={"X-Request-ID": request_id})
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
        responses={**_ERROR_RESPONSES, 503: {"model": ErrorEnvelope}},
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
                                "usage": {"anyOf": [UsageDeclaration.model_json_schema(), {"type": "null"}]},
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
                                "usage": {"type": "string", "maxLength": 2048, "description": "Optional UsageDeclaration JSON; omission preserves legacy behavior"},
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
                raise ApiError(status_code=503, code="git_scanning_unavailable", message="当前环境未启用 Git 扫描，请使用已启用扫描服务的入口。", reason="git_runtime_disabled")
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
            dispatcher: ZipDispatcher | None = request.app.state.zip_dispatcher
            if dispatcher is not None and not dispatcher.is_accepting:
                raise ApiError(
                    status_code=500,
                    code="internal_error",
                    message="ZIP scanning is unavailable.",
                    reason="dispatch_storage_failure",
                )
            reservation = runtime.reserve_upload_capacity()
            try:
                async with request.form(max_files=1, max_fields=3, max_part_size=64 * 1024 * 1024) as form:
                    grouped: dict[str, list[object]] = {}
                    for key, value in form.multi_items():
                        grouped.setdefault(key, []).append(value)
                    if set(grouped) - {"source_type", "idempotency_key", "file", "usage"}:
                        raise ValueError
                    if len(grouped.get("source_type", [])) != 1 or len(grouped.get("file", [])) != 1:
                        raise ValueError
                    if len(grouped.get("idempotency_key", [])) > 1:
                        raise ValueError
                    if len(grouped.get("usage", [])) > 1:
                        raise ValueError
                    usage = grouped.get("usage", [None])[0]
                    if usage is not None and (not isinstance(usage, str) or len(usage)>2048):
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
                        usage=json.loads(usage) if usage is not None else None,
                    )
                    return await runtime.submit(upload, fields, service, background_tasks, reservation=reservation)
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
            finally:
                runtime.release_upload_capacity(reservation)

        raise ApiError(
            status_code=415,
            code="invalid_source",
            message="Request content type is not supported.",
            reason="unsupported_media_type",
        )

    @router.get("/scans", response_model=P1HistoryPage, responses={400: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}})
    def list_scans(
        request: Request,
        cursor: str | None = None,
        limit: str = "20",
        status: str | None = None,
        source_type: str | None = None,
        q: str | None = None,
        project_key: str | None = None,
    ) -> P1HistoryPage:
        assessment = request.app.state.assessment_service
        return HistoryReader(
            request.app.state.scan_api_service._registry,
            assessment.store if assessment is not None else None,
            request.app.state.history_cursor_key,
        ).page(cursor=cursor, limit=limit, status=status, source_type=source_type, q=q, project_key=project_key)

    @router.get("/scans/{target_scan_id}/diff", response_model=P1ScanDiffView,
                responses={code: {"model": ErrorEnvelope} for code in (400, 404, 409, 503)})
    def compare_scans(
        target_scan_id: str,
        request: Request,
        base_scan_id: str,
        base_assessment_id: str | None = None,
        target_assessment_id: str | None = None,
    ) -> P1ScanDiffView:
        assessment = request.app.state.assessment_service
        value = DiffReader(
            request.app.state.scan_api_service._registry,
            assessment.store if assessment is not None else None,
        ).compare(target_scan_id, base_scan_id, base_assessment_id, target_assessment_id)
        try:
            return P1ScanDiffView.model_validate(value)
        except ValidationError:
            raise ApiError(
                status_code=503, code="upstream_unavailable",
                message="Stored facts cannot be represented by the Diff contract.",
                reason="diff_reference_integrity",
            ) from None

    def task_service(request: Request):
        service = request.app.state.remediation_service
        if service is None:
            raise ApiError(status_code=503, code="feature_disabled",
                           message="整改任务服务尚未配置。", reason="remediation_not_configured")
        return service

    @router.get("/scans/{scan_id}/assessments/{assessment_id}/remediation-tasks", response_model=P1TaskPage,
                responses={code: {"model": ErrorEnvelope} for code in (400, 404, 409, 503)})
    def list_remediation_tasks(scan_id: str, assessment_id: str, request: Request,
                               cursor: str | None = None, limit: str = "20") -> P1TaskPage:
        if set(request.query_params) - {"cursor", "limit"} or any(len(request.query_params.getlist(k)) > 1 for k in request.query_params):
            raise ApiError(status_code=400, code="invalid_argument", message="任务查询参数无效。", reason="request_invalid")
        return task_service(request).page(scan_id, assessment_id, cursor=cursor, limit=limit)

    @router.post("/scans/{scan_id}/assessments/{assessment_id}/remediation-tasks/derive", response_model=P1TaskCollection,
                 responses={code: {"model": ErrorEnvelope} for code in (400, 404, 409, 503)})
    def derive_remediation_tasks(scan_id: str, assessment_id: str, request: Request,
                                 payload: P1TaskDeriveRequest) -> P1TaskCollection:
        return task_service(request).derive(scan_id, assessment_id, payload)

    @router.patch("/scans/{scan_id}/assessments/{assessment_id}/remediation-tasks/{task_id}", response_model=P1RemediationTask,
                  responses={code: {"model": ErrorEnvelope} for code in (400, 404, 409, 503)})
    def patch_remediation_task(scan_id: str, assessment_id: str, task_id: str, request: Request,
                               payload: P1TaskPatchRequest) -> P1RemediationTask:
        return task_service(request).patch(scan_id, assessment_id, task_id, payload)

    @router.get("/scans/{scan_id}/graph", response_model=P1ResourceGraphView,
                responses={**{code: {"model": ErrorEnvelope} for code in (400, 404, 409, 503)},
                           413: {"model": P1GraphCapacityErrorEnvelope}})
    def get_resource_graph(
        scan_id: str,
        request: Request,
        resource_ids: Annotated[list[str] | None, Query()] = None,
        resource_kinds: Annotated[list[str] | None, Query()] = None,
    ) -> P1ResourceGraphView:
        if set(request.query_params) - {"resource_ids", "resource_kinds"}:
            raise ApiError(status_code=400, code="invalid_argument",
                           message="资源筛选参数无效。", reason="resource_filter_invalid")
        value = GraphReader(
            request.app.state.scan_api_service._registry,
            max_nodes=request.app.state.p1_graph_max_nodes,
            max_edges=request.app.state.p1_graph_max_edges,
        ).read(scan_id, resource_ids, resource_kinds)
        try:
            return P1ResourceGraphView.model_validate(value)
        except ValidationError:
            raise ApiError(status_code=503, code="upstream_unavailable",
                           message="Stored facts cannot be represented by the Graph contract.",
                           reason="graph_reference_integrity") from None

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
                    "Content-Security-Policy": "sandbox allow-downloads; default-src 'none'; base-uri 'none'; form-action 'none'",
                    "ETag": f'"sha256:{stored.link.content_hash.value}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return service.report(scan_id, report_format)

    return router


class _PersistentCapacity:
    """Single-process admission watermark, not a filesystem hard quota.

    The request lock bridges upload parsing and durable record creation. After
    202, queued/running rows retain their headroom, including after restart.
    """

    def __init__(self, root: Path, registry: SQLiteScanRunRegistry, *,
                 limit_bytes: int = 2 * 1024**3, reserve_bytes: int = 256 * 1024**2,
                 free_floor_bytes: int = 512 * 1024**2) -> None:
        if any(type(v) is not int or v <= 0 for v in (limit_bytes, reserve_bytes, free_floor_bytes)):
            raise ValueError("invalid persistent capacity budget")
        if reserve_bytes > limit_bytes:
            raise ValueError("persistent capacity reserve exceeds budget")
        self.root, self.registry = root, registry
        self.limit_bytes, self.reserve_bytes, self.free_floor_bytes = limit_bytes, reserve_bytes, free_floor_bytes
        self.lock = threading.Lock()

    def check(self) -> None:
        root_info = self.root.lstat()
        if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid() or root_info.st_mode & 0o077:
            raise OSError("invalid capacity root")
        pending = [self.root]
        seen: set[tuple[int, int]] = set()
        used = 0
        entries = 0
        while pending:
            directory = pending.pop()
            for path in directory.iterdir():
                info = path.lstat()
                # Only the separate Compose workspace mount is excluded.
                # A same-filesystem local workspace consumes persistent space.
                if path == self.root / "workspaces" and stat.S_ISDIR(info.st_mode) and info.st_dev != root_info.st_dev:
                    continue
                entries += 1
                if entries > 100_000:
                    raise OSError("capacity inventory limit")
                if stat.S_ISDIR(info.st_mode):
                    if info.st_dev != root_info.st_dev:
                        raise OSError("unexpected capacity mount")
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    identity = (info.st_dev, info.st_ino)
                    if identity not in seen:
                        used += max(info.st_size, info.st_blocks * 512)
                        seen.add(identity)
                else:
                    raise OSError("unexpected capacity entry")
        reservation = (self.registry.active_count() + 1) * self.reserve_bytes
        fs = os.statvfs(self.root)
        if used + reservation > self.limit_bytes or fs.f_bavail * fs.f_frsize < self.free_floor_bytes + reservation:
            raise ApiError(status_code=503, code="scan_capacity_unavailable",
                           message="持久存储容量不足，已保留历史报告。请由负责人检查存储后再提交扫描。",
                           reason="persistent_capacity_exceeded")


def create_app(
    registry: SQLiteScanRunRegistry,
    *,
    zip_runtime: ZipScanRuntime | None = None,
    git_runtime: GitScanRuntime | None = None,
    report_store: ReportArtifactStore | None = None,
    close_registry: bool = False,
    zip_dispatcher: ZipDispatcher | None = None,
    persistent_capacity: _PersistentCapacity | None = None,
    assessment_service=None,
    remediation_service=None,
    report_v2_service=None,
    notice_draft_service=None,
    profile_service=None,
    profile_routes_enabled=True,
) -> FastAPI:
    if zip_dispatcher is not None:
        # Durable lifecycle ownership is deliberately all-or-nothing.  An
        # injected dispatcher must use exactly this registry and runtime store,
        # and this lifespan must close the registry before it can release the
        # flock.  That prevents a caller from accidentally pairing a lock for
        # one data root with a worker using another.
        if (
            not close_registry
            or zip_runtime is None
            or zip_runtime._registry is not registry
            or type(zip_runtime._dispatch_store) is not ZipDispatchStore
            or not zip_dispatcher.is_bound_to(
                registry,
                zip_runtime._dispatch_store,
                ai_provider=zip_runtime._ai_provider,
                ai_enabled=zip_runtime._ai_enabled,
                ai_timeout_seconds=zip_runtime._ai_timeout_seconds,
                external_scanners=zip_runtime._external_scanners,
            )
        ):
            raise ValueError("zip dispatcher must own the matching ZIP runtime and registry lifecycle")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        dispatcher_started = False
        try:
            if zip_dispatcher is not None:
                zip_dispatcher.start()
                dispatcher_started = True
            yield
        finally:
            if dispatcher_started:
                zip_dispatcher.stop_and_join()
            if close_registry:
                registry.close()
            if zip_dispatcher is not None and zip_dispatcher.has_lifecycle_lock:
                zip_dispatcher.release_lifecycle_lock()

    app = FastAPI(title="OpenGuard API", version=APPLICATION_VERSION, lifespan=lifespan)
    app.state.scan_api_service = ScanApiService(registry, report_store=report_store)
    app.state.zip_scan_runtime = zip_runtime
    app.state.git_scan_runtime = git_runtime
    app.state.zip_dispatcher = zip_dispatcher
    app.state.assessment_service = assessment_service
    app.state.remediation_service = remediation_service
    app.state.report_v2_service = report_v2_service
    app.state.notice_draft_service = notice_draft_service
    from app.p1.profile import ProfileService
    app.state.profile_service = profile_service or ProfileService(registry)
    app.state.history_cursor_key = secrets.token_bytes(32)
    app.state.p1_graph_max_nodes = _P1_GRAPH_MAX_NODES
    app.state.p1_graph_max_edges = _P1_GRAPH_MAX_EDGES

    @app.middleware("http")
    async def v4_write_boundary(request: Request, call_next):
        path = request.url.path
        segments = path.strip("/").split("/")
        task_path = (len(segments) == 8 and segments[:3] == ["api", "v1", "scans"]
                     and segments[4] == "assessments" and segments[6] == "remediation-tasks")
        task_write = task_path and (request.method == "PATCH" or (request.method == "POST" and segments[7] == "derive"))
        existing_write = assessment_service is not None and request.method in {"POST", "DELETE"} and ("/assessments" in path or path.endswith("/chat"))
        report_write = (
            request.method == "POST" and len(segments) == 7
            and segments[:3] == ["api", "v1", "scans"]
            and segments[4] == "assessments" and segments[6] == "report-v2"
        )
        profile_write = (profile_routes_enabled and request.method == 'POST' and len(segments) == 6
                         and segments[:3] == ['api', 'v1', 'scans'] and segments[4:] == ['resource-profiles', 'refresh'])
        notice_write = (request.method == 'POST' and len(segments) == 7
                        and segments[:3] == ['api', 'v1', 'scans']
                        and segments[4] == 'assessments' and segments[6] == 'notice-drafts')
        if task_write or report_write or existing_write or profile_write or notice_write:
            from urllib.parse import urlsplit
            configured = os.environ.get("OPENGUARD_WEB_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080")
            allowed = configured.split(",")
            origin = request.headers.get("origin")
            if any(urlsplit(x).hostname not in {"127.0.0.1", "localhost", "::1"} or urlsplit(x).scheme != "http" for x in allowed):
                return _error_response(request, ApiError(status_code=503,code="origin_configuration_invalid",message="本地来源配置不可用。",reason="origin_configuration_invalid"))
            if (origin is not None and origin not in allowed) or request.headers.get("sec-fetch-site") == "cross-site":
                return _error_response(request, ApiError(status_code=403,code="origin_rejected",message="仅允许本地产品页面提交此操作。",reason="origin_rejected"))
            if request.method in {"POST", "PATCH"}:
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    if task_write or report_write or profile_write or notice_write:
                        return _error_response(request, ApiError(status_code=400,code="invalid_argument",message="请求必须为JSON。",reason="request_invalid"))
                    return _error_response(request, ApiError(status_code=422,code="request_invalid",message="请求必须为JSON。",reason="request_invalid"))
                chunks=[]; size=0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 16384:
                        return _error_response(request, ApiError(status_code=413,code="request_too_large",message="问题内容超过请求容量。",reason="request_too_large"))
                    chunks.append(chunk)
                request._body = b"".join(chunks)
        return await call_next(request)

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
    async def persistent_capacity_admission(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if persistent_capacity is None or request.method != "POST" or request.url.path.rstrip("/") != "/api/v1/scans":
            return await call_next(request)
        if not persistent_capacity.lock.acquire(blocking=False):
            return _error_response(request, ApiError(status_code=503, code="scan_capacity_unavailable",
                message="扫描提交正在受理，请稍后重试。", reason="persistent_capacity_busy"))
        try:
            try:
                await run_in_threadpool(persistent_capacity.check)
            except ApiError as error:
                return _error_response(request, error)
            except Exception:
                return _error_response(request, ApiError(status_code=503, code="scan_capacity_unavailable",
                    message="无法核实持久存储容量，已暂停新扫描；历史报告保留。", reason="persistent_capacity_unavailable"))
            return await call_next(request)
        finally:
            persistent_capacity.lock.release()

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
        route = request.scope.get("route")
        if (request.method, getattr(route, "path", None)) == ("POST", "/api/v1/scans/{scan_id}/resource-profiles/refresh"):
            return _error_response(request, ApiError(
                status_code=400, code="invalid_argument",
                message="Profile刷新请求参数无效。", reason="request_invalid",
            ))
        if (request.method, getattr(route, "path", None)) in {
            ("POST", "/api/v1/scans/{scan_id}/assessments/{assessment_id}/notice-drafts"),
            ("GET", "/api/v1/scans/{scan_id}/assessments/{assessment_id}/notice-drafts/{draft_id}"),
            ("POST", "/api/v1/scans/{scan_id}/assessments/{assessment_id}/report-v2"),
            ("GET", "/api/v1/scans/{scan_id}/assessments/{assessment_id}/report-v2/{snapshot_id}"),
        }:
            return _error_response(request, ApiError(
                status_code=400, code="invalid_argument",
                message="报告请求参数无效。", reason="request_invalid",
            ))
        if (request.method, getattr(route, "path", None)) in {
            ("POST", "/api/v1/scans/{scan_id}/assessments/{assessment_id}/remediation-tasks/derive"),
            ("PATCH", "/api/v1/scans/{scan_id}/assessments/{assessment_id}/remediation-tasks/{task_id}"),
        }:
            return _error_response(request, ApiError(
                status_code=400, code="invalid_argument",
                message="Remediation task parameters are invalid.", reason="request_invalid",
            ))
        if request.method == "GET" and getattr(route, "path", None) == "/api/v1/scans/{target_scan_id}/diff":
            return _error_response(request, ApiError(
                status_code=400, code="invalid_argument",
                message="Diff parameters are invalid.", reason="request_invalid",
            ))
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
    from app.api.report_v2 import router as report_v2_router
    app.include_router(report_v2_router())
    from app.api.notice_draft import router as notice_draft_router
    app.include_router(notice_draft_router())
    if profile_routes_enabled:
        from app.api.profile import router as profile_router
        app.include_router(profile_router())
    if assessment_service is not None:
        from app.api.assessment import router as assessment_router
        app.include_router(assessment_router())
    return app


def create_default_app() -> FastAPI:
    external_scanners = os.environ.get("OPENGUARD_ENABLE_EXTERNAL_SCANNERS", "0")
    if external_scanners not in {"0", "1"}:
        raise RuntimeError("invalid OPENGUARD_ENABLE_EXTERNAL_SCANNERS")
    durable_zip_enabled = os.environ.get("OPENGUARD_ENABLE_DURABLE_ZIP", "0")
    if durable_zip_enabled not in {"0", "1"}:
        raise RuntimeError("invalid OPENGUARD_ENABLE_DURABLE_ZIP")
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
    dispatch_root = data_dir / "dispatch"
    roots = (upload_root, workspace_root, report_root)
    if durable_zip_enabled == "1":
        roots = (*roots, dispatch_root)
    for root in roots:
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
    docker_ollama = os.environ.get("OPENGUARD_OLLAMA_DOCKER_HOST", "0")
    if docker_ollama not in {"0", "1"}:
        raise RuntimeError("invalid OPENGUARD_OLLAMA_DOCKER_HOST")
    ai_provider = (
        OllamaProvider("http://host.docker.internal:11434", docker_host=True)
        if docker_ollama == "1" else OllamaProvider()
    ) if ai_enabled == "1" else None
    dispatch_store = (
        ZipDispatchStore(dispatch_root, upload_root, recovery_mode=True)
        if durable_zip_enabled == "1"
        else None
    )
    v4_enabled = os.environ.get("OPENGUARD_ENABLE_ASSESSMENTS", "0")
    if v4_enabled not in {"0", "1"}:
        raise RuntimeError("invalid OPENGUARD_ENABLE_ASSESSMENTS")
    scan_ai_enabled = ai_enabled == "1" and v4_enabled != "1"
    runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        report_publisher=PipelineReportPublisher(report_store),
        ai_provider=ai_provider,
        ai_enabled=scan_ai_enabled,
        ai_timeout_seconds=30.0,
        dispatch_store=dispatch_store,
        external_scanners=external_scanners == "1",
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
            ai_enabled=scan_ai_enabled,
            ai_timeout_seconds=30.0,
            external_scanners=external_scanners == "1",
        )
        if git_enabled == "1"
        else None
    )
    dispatcher = (
        ZipDispatcher(
            registry,
            dispatch_store,
            data_dir=data_dir,
            workspace_root=workspace_root,
            report_publisher=PipelineReportPublisher(report_store),
            ai_provider=ai_provider,
            ai_enabled=scan_ai_enabled,
            ai_timeout_seconds=30.0,
            external_scanners=external_scanners == "1",
        )
        if dispatch_store is not None
        else None
    )
    assessment_service = None
    remediation_service = None
    report_v2_service = None
    if v4_enabled == "1":
        from app.assessment.service import AssessmentService
        from app.assessment.store import AssessmentStore
        from app.p1.remediation import RemediationService
        from app.p1.remediation_store import RemediationTaskStore
        from app.p1.report_v2 import ReportV2Service
        from app.p1.report_v2_store import ReportV2Store
        from app.p1.report_v2_graph import ReportGraphReader

        assessment_store = AssessmentStore(data_dir / "assessment.db")
        assessment_service = AssessmentService(registry, assessment_store, ai_provider)
        assessment_service.initialize()
        # Initialize the entire opt-in workflow before publishing an app. Store
        # failures propagate: never serve a partially configured workflow, and
        # never delete existing sidecars as a startup rollback.
        remediation_store = RemediationTaskStore(data_dir / "remediation.db")
        remediation_store.initialize()
        report_v2_store = ReportV2Store(data_dir / "report_v2.db")
        report_v2_store.initialize()
        remediation_service = RemediationService(registry, assessment_store, remediation_store)
        report_v2_service = ReportV2Service(
            registry, assessment_store, remediation_store, report_v2_store,
            graph_reader=ReportGraphReader(
                max_nodes=_P1_GRAPH_MAX_NODES, max_edges=_P1_GRAPH_MAX_EDGES,
            ),
        )
        # Optional terminal observation is separate from report publication and ScanRun CAS.
        registry.assessment_observer = assessment_service.on_terminal
    return create_app(
        registry,
        zip_runtime=runtime,
        git_runtime=git_runtime,
        report_store=report_store,
        close_registry=True,
        zip_dispatcher=dispatcher,
        persistent_capacity=_PersistentCapacity(data_dir, registry),
        assessment_service=assessment_service,
        remediation_service=remediation_service,
        report_v2_service=report_v2_service,
    )


__all__ = ["create_app", "create_default_app"]
