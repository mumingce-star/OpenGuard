"""Application service for the minimal P0 FastAPI vertical slice."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import platform
import sys
import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import UUID, uuid4

from app.api.models import (
    GitScanCreateRequest,
    ResourceFilters,
    ResourcesResponse,
    ResourceView,
    RiskFilters,
    RisksResponse,
    ScanCreateAccepted,
    ScanRunStatusView,
    ZipScanCreateFields,
)
from app.domain.models import (
    CONTRACT_VERSION,
    Evidence,
    FindingOutcome,
    HashValue,
    Project,
    ReportFormat,
    ReportLink,
    RunEnvironment,
    RunProvenance,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    SourceType,
)
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError
from app.reporting import ReportArtifactStore, ReportStoreError, StoredReport


APPLICATION_VERSION = "0.1.0"
_RESULT_STATUSES = frozenset({ScanStatus.COMPLETED, ScanStatus.PARTIAL})


class ApiError(RuntimeError):
    """A stable public error without internal exception context."""

    def __init__(self, *, status_code: int, code: str, message: str, reason: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.reason = reason
        super().__init__(code)


def _fail(*, status_code: int, code: str, message: str, reason: str) -> None:
    raise ApiError(status_code=status_code, code=code, message=message, reason=reason) from None


def canonicalize_public_git_url(value: str) -> str:
    """Validate the frozen public-HTTPS Git source boundary without networking."""

    try:
        encoded_value = value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="url_invalid")
    if len(encoded_value) > 2048 or any(unicodedata.category(character) == "Cc" for character in value):
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="url_invalid")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="url_invalid")
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="url_invalid")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        _fail(status_code=422, code="invalid_source", message="Public repository URL is not allowed.", reason="host_not_public")
    lowered = hostname.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        _fail(status_code=422, code="invalid_source", message="Public repository URL is not allowed.", reason="host_not_public")
    decoded_segments = [unquote(segment) for segment in parsed.path.split("/")]
    if any(unicodedata.category(character) == "Cc" for segment in decoded_segments for character in segment):
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="url_invalid")
    if parsed.path in {"", "/"} or any(segment in {".", ".."} for segment in decoded_segments):
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="path_invalid")
    try:
        ascii_host = lowered.encode("idna").decode("ascii")
    except UnicodeError:
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="host_invalid")
    return urlunsplit(("https", ascii_host, parsed.path, "", ""))


def _project_name(source: str) -> str:
    name = unquote(urlsplit(source).path.rstrip("/").rsplit("/", 1)[-1])
    if name.endswith(".git"):
        name = name[:-4]
    if not name:
        _fail(status_code=422, code="invalid_source", message="Public repository URL is invalid.", reason="path_invalid")
    return name[:200]


class ScanApiService:
    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        *,
        report_store: ReportArtifactStore | None = None,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._registry = registry
        self._report_store = report_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or uuid4

    def create_git_scan(self, request: GitScanCreateRequest) -> ScanCreateAccepted:
        source = canonicalize_public_git_url(request.source)
        created_at = self._clock()
        source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        fingerprint_payload = json.dumps(
            {"source": source, "source_type": "git"},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        run = ScanRun(
            contract_version=CONTRACT_VERSION,
            id=f"scn_{self._id_factory()}",
            idempotency_key=request.idempotency_key,
            status=ScanStatus.QUEUED,
            stage=ScanStage.QUEUED,
            progress=0,
            project=Project(
                id=f"prj_{self._id_factory()}",
                name=_project_name(source),
                source_type=SourceType.GIT,
                source=source,
                created_at=created_at,
            ),
            summary=ScanSummary(
                component_count=0,
                ai_asset_count=0,
                evidence_count=0,
                finding_counts={outcome: 0 for outcome in FindingOutcome},
            ),
            provenance=RunProvenance(
                input_digest=HashValue(algorithm="sha256", value=source_digest),
                tool_versions=[],
                ruleset_version="pending",
                contract_version=CONTRACT_VERSION,
                ai_enabled=False,
                run_environment=RunEnvironment(
                    python_version=platform.python_version(),
                    platform=f"{sys.platform}/{platform.machine()}",
                    openguard_version=APPLICATION_VERSION,
                ),
            ),
            created_at=created_at,
        )
        fingerprint = hashlib.sha256(fingerprint_payload).hexdigest() if request.idempotency_key is not None else None
        try:
            stored = self._registry.create(run, idempotency_fingerprint=fingerprint)
        except ScanRegistryError as error:
            if error.code == "registry_idempotency_conflict":
                _fail(
                    status_code=409,
                    code="invalid_source",
                    message="Idempotency key was already used for a different source.",
                    reason="idempotency_conflict",
                )
            _fail(status_code=500, code="internal_error", message="The scan could not be created.", reason="registry_failure")
        return ScanCreateAccepted(
            scan_id=stored.run.id,
            status=stored.run.status,
            status_url=f"/api/v1/scans/{stored.run.id}",
        )

    def create_zip_scan(
        self,
        request: ZipScanCreateFields,
        *,
        staged_name: str,
        project_name: str,
        input_digest: str,
    ) -> tuple[ScanCreateAccepted, bool]:
        if (
            type(staged_name) is not str
            or not staged_name
            or "/" in staged_name
            or "\\" in staged_name
            or type(project_name) is not str
            or not project_name
            or len(project_name) > 200
            or type(input_digest) is not str
            or len(input_digest) != 64
        ):
            _fail(status_code=500, code="internal_error", message="The scan could not be created.", reason="zip_runtime_failure")
        try:
            int(input_digest, 16)
        except ValueError:
            _fail(status_code=500, code="internal_error", message="The scan could not be created.", reason="zip_runtime_failure")

        created_at = self._clock()
        candidate_id = f"scn_{self._id_factory()}"
        fingerprint_payload = json.dumps(
            {"input_digest": input_digest, "source_type": "zip"},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        run = ScanRun(
            contract_version=CONTRACT_VERSION,
            id=candidate_id,
            idempotency_key=request.idempotency_key,
            status=ScanStatus.QUEUED,
            stage=ScanStage.QUEUED,
            progress=0,
            project=Project(
                id=f"prj_{self._id_factory()}",
                name=project_name,
                source_type=SourceType.ZIP,
                source=staged_name,
                created_at=created_at,
            ),
            summary=ScanSummary(
                component_count=0,
                ai_asset_count=0,
                evidence_count=0,
                finding_counts={outcome: 0 for outcome in FindingOutcome},
            ),
            provenance=RunProvenance(
                input_digest=HashValue(algorithm="sha256", value=input_digest),
                tool_versions=[],
                ruleset_version="pending",
                contract_version=CONTRACT_VERSION,
                ai_enabled=False,
                run_environment=RunEnvironment(
                    python_version=platform.python_version(),
                    platform=f"{sys.platform}/{platform.machine()}",
                    openguard_version=APPLICATION_VERSION,
                ),
            ),
            created_at=created_at,
        )
        fingerprint = hashlib.sha256(fingerprint_payload).hexdigest() if request.idempotency_key is not None else None
        try:
            stored = self._registry.create(run, idempotency_fingerprint=fingerprint)
        except ScanRegistryError as error:
            if error.code == "registry_idempotency_conflict":
                _fail(
                    status_code=409,
                    code="invalid_source",
                    message="Idempotency key was already used for a different source.",
                    reason="idempotency_conflict",
                )
            _fail(status_code=500, code="internal_error", message="The scan could not be created.", reason="registry_failure")
        accepted = ScanCreateAccepted(
            scan_id=stored.run.id,
            status=stored.run.status,
            status_url=f"/api/v1/scans/{stored.run.id}",
        )
        return accepted, stored.run.id == candidate_id

    def status(self, scan_id: str) -> ScanRunStatusView:
        run = self._get_run(scan_id)
        return ScanRunStatusView(
            scan_id=run.id,
            status=run.status,
            stage=run.stage,
            progress=run.progress,
            summary=run.summary,
            errors=run.errors,
        )

    def resources(self, scan_id: str, filters: ResourceFilters) -> ResourcesResponse:
        run = self._ready_run(scan_id)
        items: list[ResourceView] = []
        if filters.kind in {None, "component"} and filters.provider is None and filters.verification_status is None:
            for component in run.components:
                if filters.ecosystem is None or component.ecosystem == filters.ecosystem:
                    items.append(ResourceView(kind="component", resource=component))
        if filters.kind in {None, "ai_asset"} and filters.ecosystem is None:
            for asset in run.ai_assets:
                if filters.provider is not None and asset.provider != filters.provider:
                    continue
                if filters.verification_status is not None and asset.authorization_status is not filters.verification_status:
                    continue
                items.append(ResourceView(kind="ai_asset", resource=asset))
        items.sort(key=lambda item: (item.kind, item.resource.id))
        return ResourcesResponse(items=items, total=len(items), filters=filters)

    def risks(self, scan_id: str, filters: RiskFilters) -> RisksResponse:
        run = self._ready_run(scan_id)
        items = [
            finding
            for finding in run.findings
            if (filters.outcome is None or finding.outcome is filters.outcome)
            and (filters.severity is None or finding.severity is filters.severity)
            and (filters.resource_kind is None or finding.resource_kind == filters.resource_kind)
        ]
        items.sort(key=lambda finding: finding.id)
        return RisksResponse(items=items, total=len(items))

    def evidence(self, scan_id: str, evidence_id: str) -> Evidence:
        run = self._ready_run(scan_id)
        for evidence in run.evidence:
            if evidence.id == evidence_id:
                return evidence
        _fail(status_code=404, code="evidence_not_found", message="Evidence was not found.", reason="not_found")

    def report(self, scan_id: str, report_format: ReportFormat) -> ReportLink:
        run = self._get_run(scan_id)
        if run.status not in _RESULT_STATUSES:
            _fail(status_code=409, code="report_not_ready", message="Requested report is not ready.", reason="status_not_ready")
        if self._report_store is not None:
            return self._stored_report(run.id, report_format).link
        for link in run.report_links:
            if link.format is report_format:
                return link
        _fail(status_code=409, code="report_not_ready", message="Requested report is not ready.", reason="not_generated")

    def download_report(self, scan_id: str, report_format: ReportFormat) -> StoredReport:
        run = self._get_run(scan_id)
        if run.status not in _RESULT_STATUSES:
            _fail(status_code=409, code="report_not_ready", message="Requested report is not ready.", reason="status_not_ready")
        if self._report_store is None:
            _fail(status_code=409, code="report_not_ready", message="Requested report is not ready.", reason="not_generated")
        return self._stored_report(run.id, report_format)

    def _stored_report(self, scan_id: str, report_format: ReportFormat) -> StoredReport:
        store = self._report_store
        if store is None:
            _fail(
                status_code=409,
                code="report_not_ready",
                message="Requested report is not ready.",
                reason="not_generated",
            )
        try:
            return store.get(scan_id, report_format)
        except ReportStoreError as error:
            if error.code == "report_store_not_found":
                _fail(
                    status_code=409,
                    code="report_not_ready",
                    message="Requested report is not ready.",
                    reason="not_generated",
                )
            _fail(
                status_code=500,
                code="internal_error",
                message="The report could not be read.",
                reason="report_storage_failure",
            )

    def _get_run(self, scan_id: str) -> ScanRun:
        try:
            return self._registry.get(scan_id).run
        except ScanRegistryError as error:
            if error.code in {"registry_not_found", "registry_invalid_argument"}:
                _fail(status_code=404, code="scan_not_found", message="Scan was not found.", reason="not_found")
            _fail(status_code=500, code="internal_error", message="The scan could not be read.", reason="registry_failure")

    def _ready_run(self, scan_id: str) -> ScanRun:
        run = self._get_run(scan_id)
        if run.status not in _RESULT_STATUSES:
            _fail(status_code=409, code="scan_not_ready", message="Scan results are not ready.", reason="status_not_ready")
        return run


__all__ = ["APPLICATION_VERSION", "ApiError", "ScanApiService", "canonicalize_public_git_url"]
