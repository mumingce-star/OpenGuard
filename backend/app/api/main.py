"""FastAPI application factory for the frozen OpenGuard P0 routes."""

from __future__ import annotations

import os
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Annotated, AsyncIterator, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

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
)
from app.api.service import APPLICATION_VERSION, ApiError, ScanApiService
from app.domain.models import Evidence, FindingOutcome, ReportFormat, ReportLink, Severity, VerificationStatus
from app.persistence import SQLiteScanRunRegistry


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
    )
    def create_scan(
        body: GitScanCreateRequest,
        service: Annotated[ScanApiService, Depends(_service)],
    ) -> ScanCreateAccepted:
        return service.create_git_scan(body)

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
    ) -> ReportLink:
        return service.report(scan_id, report_format)

    return router


def create_app(
    registry: SQLiteScanRunRegistry,
    *,
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
    app.state.scan_api_service = ScanApiService(registry)

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
    data_dir = Path(configured)
    try:
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = data_dir.lstat()
    except OSError as error:
        raise RuntimeError("OpenGuard data directory is unavailable") from error
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("OpenGuard data directory must be private")
    return create_app(SQLiteScanRunRegistry(data_dir / "scans.db"), close_registry=True)


__all__ = ["create_app", "create_default_app"]
