"""Report V2 HTTP adapter; no production storage initialization or rendering."""
from __future__ import annotations

from base64 import b64encode
import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import Field, ValidationError, model_validator

from app.api.models import ErrorEnvelope
from app.api.service import ApiError
from app.p1.models import (
    P1AlgorithmRef,
    P1GraphCapacityErrorEnvelope,
    P1Model,
    P1NoticeRef,
    P1ReportV2Snapshot,
    P1TaskRef,
)
from app.p1.report_v2 import ReportV2Service, ReportV2ServiceError


PREFIX = "/api/v1/scans/{scan_id}/assessments/{assessment_id}/report-v2"
ERROR_RESPONSES = {
    code: {"model": ErrorEnvelope}
    for code in (400, 403, 404, 409, 413, 503)
}
ERROR_RESPONSES[413] = {"model": ErrorEnvelope | P1GraphCapacityErrorEnvelope}
SERVICE_STATUS = {
    "invalid_argument": 400,
    "not_found": 404,
    "conflict": 409,
    "not_ready": 409,
    "upstream_unavailable": 503,
}


class ReportTaskRef(P1TaskRef):
    # HTTP input must not coerce True or "1" into version=1.
    version: Annotated[int, Field(strict=True, ge=1)]


class ReportV2CreateRequest(P1Model):
    idempotency_key: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    task_refs: list[ReportTaskRef] = Field(default_factory=list)
    notice_refs: list[P1NoticeRef] = Field(default_factory=list)
    algorithm_refs: list[P1AlgorithmRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_key_and_tasks(self):
        if not self.idempotency_key.strip():
            raise ValueError("idempotency key must not be blank")
        ids = [ref.task_id for ref in self.task_refs]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate task reference")
        return self


def _fail(status: int, code: str, reason: str) -> None:
    raise ApiError(
        status_code=status,
        code=code,
        message="报告请求无法完成，请检查请求或稍后重试。",
        reason=reason,
    )


def _service(request: Request) -> ReportV2Service:
    value = getattr(request.app.state, "report_v2_service", None)
    if value is None:
        _fail(503, "feature_disabled", "report_v2_not_configured")
    return value


def _query(request: Request, allowed: set[str]) -> None:
    params = request.query_params
    if set(params) - allowed or any(len(params.getlist(key)) != 1 for key in params):
        _fail(400, "invalid_argument", "request_invalid")


def _translate(error: ReportV2ServiceError) -> None:
    # These are context-free internal codes, never exception text or SQL.
    if error.code not in SERVICE_STATUS:
        _fail(503, "upstream_unavailable", "report_service_unavailable")
    _fail(SERVICE_STATUS[error.code], error.code, error.reason)


def router() -> APIRouter:
    result = APIRouter(prefix=PREFIX, tags=["Report V2"])

    @result.post("", response_model=P1ReportV2Snapshot, responses=ERROR_RESPONSES)
    def create_report(
        scan_id: str,
        assessment_id: str,
        payload: ReportV2CreateRequest,
        request: Request,
    ) -> P1ReportV2Snapshot:
        _query(request, set())
        service = _service(request)
        try:
            return service.create(
                scan_id,
                assessment_id,
                idempotency_key=payload.idempotency_key,
                task_refs=payload.task_refs,
                notice_refs=payload.notice_refs,
                algorithm_refs=payload.algorithm_refs,
            )
        except ReportV2ServiceError as error:
            _translate(error)
        except ValidationError:
            _fail(503, "upstream_unavailable", "report_source_integrity")

    @result.get(
        "/{snapshot_id}",
        response_class=Response,
        responses={
            **ERROR_RESPONSES,
            200: {
                "description": "Stored, immutable JSON or HTML artifact bytes.",
                "content": {
                    "application/json": {},
                    "text/html": {"schema": {"type": "string"}},
                },
            },
        },
    )
    def download_report(
        scan_id: str,
        assessment_id: str,
        snapshot_id: str,
        request: Request,
        format: Annotated[Literal["json", "html"], Query()] = "json",
    ) -> Response:
        _query(request, {"format"})
        service = _service(request)
        try:
            snapshot = service.get(scan_id, assessment_id, snapshot_id)
            if snapshot is None:
                _fail(404, "not_found", "report_not_found")
            payload = service.artifact(scan_id, assessment_id, snapshot_id, format)
        except ReportV2ServiceError as error:
            _translate(error)
        except ValidationError:
            _fail(503, "upstream_unavailable", "report_snapshot_integrity")

        metadata = [item for item in snapshot.artifacts if item.format == format]
        if not isinstance(payload, bytes) or not payload or len(metadata) != 1:
            _fail(503, "upstream_unavailable", "report_artifact_integrity")
        raw_digest = hashlib.sha256(payload).digest()
        if (metadata[0].size_bytes != len(payload)
                or metadata[0].content_hash != raw_digest.hex()):
            _fail(503, "upstream_unavailable", "report_artifact_integrity")

        # Return saved bytes directly: GET must not render or consult latest sources.
        return Response(
            content=payload,
            media_type="application/json" if format == "json" else "text/html",
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": f'attachment; filename="openguard-report-v2.{format}"',
                "Content-Digest": f"sha-256=:{b64encode(raw_digest).decode('ascii')}:",
                "ETag": f'"sha256:{raw_digest.hex()}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": (
                    "sandbox allow-downloads; default-src 'none'; "
                    "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
                ),
            },
        )

    return result
