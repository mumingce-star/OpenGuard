"""Task-scoped, two-stage admission of an explicitly reviewed real ZIP fact.

This is an internal operator tool, not a public approval API.  ``prepare`` is
read-only; ``apply`` runs a *new* scan through the existing pipeline and rule
engine.  Neither function upgrades an old ScanRun or treats a self-reported
reviewer name as authenticated identity.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import tarfile
import tempfile
import tomllib
import uuid
import zipfile
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path

from app.assessment.engine import canonical_bytes, facts_digest
from app.domain.models import (DetectionMethod, Evidence, EvidenceKind,
                               LicenseExpression, ProducerRef, ScanRun,
                               ScanStage, ScanStatus, VerificationStatus)
from app.persistence.scan_registry import SQLiteScanRunRegistry
from app.pipeline.dependency_plan import replace_run
from app.pipeline.worker import PipelinePlan, PipelineStep


SOURCE_COMMIT = "f63a5818b3ef59997ca6d365b75b12099a475079"
SOURCE_ARCHIVE_SHA256 = "6927e8bac8e2c9e13b84aa988ef7f0125f3283ac4d3712cb9937219f6100ea04"
ARTIFACT_SHA256 = "c40756b57adaa8b1efeeced5c196f3f3b7c435f90e84ea7f443901bec8099ef6"
ARTIFACT_URL = ("https://files.pythonhosted.org/packages/18/a5/"
                "b60d21ac674192f8ab0ba4e9fd860690f9b4a6e51ca5df118733b487d8d6/"
                "pydantic-2.13.4.tar.gz")
LICENSE_MEMBER = "pydantic-2.13.4/LICENSE"
PACKAGE_MEMBER = "pydantic-2.13.4/pyproject.toml"
METADATA_MEMBER = "pydantic-2.13.4/PKG-INFO"
_NAMESPACE = uuid.UUID("af50b739-78ee-5be5-986f-3ee6de0ae4d2")


class ReviewAdmissionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _reject(code: str) -> None:
    raise ReviewAdmissionError(code) from None


def _bounded_file_bytes(path: Path, *, limit: int) -> bytes:
    """Read one regular, non-symlink file through one descriptor with a real cap."""
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_size > limit:
            _reject("material_unsafe")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_dev != info.st_dev
                    or opened.st_ino != info.st_ino or opened.st_size > limit):
                _reject("material_unsafe")
            raw = source.read(limit + 1)
        if len(raw) > limit:
            _reject("material_unsafe")
        return raw
    except ReviewAdmissionError:
        raise
    except OSError:
        _reject("material_unavailable")
    raise AssertionError("unreachable")


def _sha256_file(path: Path, *, limit: int) -> str:
    return hashlib.sha256(_bounded_file_bytes(path, limit=limit)).hexdigest()


def _read_source(db_path: Path, scan_id: str) -> ScanRun:
    """Read the existing registry with a non-creating, query-only connection."""
    if type(scan_id) is not str or not scan_id.startswith("scn_"):
        _reject("source_scan_invalid")
    try:
        SQLiteScanRunRegistry._private_stat(db_path.parent, directory=True)
        SQLiteScanRunRegistry._private_stat(db_path, directory=False)
        with sqlite3.connect(db_path.absolute().as_uri() + "?mode=ro", uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            SQLiteScanRunRegistry._verify_schema(db)
            row = db.execute(
                "SELECT scan_id,revision,idempotency_key,idempotency_fingerprint,"
                "created_at,status,contract_version,run_json FROM scan_runs WHERE scan_id=?",
                (scan_id,),
            ).fetchone()
            if row is None:
                _reject("source_scan_not_found")
            return SQLiteScanRunRegistry._row_to_stored(row).run
    except ReviewAdmissionError:
        raise
    except Exception:
        _reject("source_scan_unavailable")
    raise AssertionError("unreachable")


def _read_member(archive: bytes, member: str, *, maximum: int) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as source:
            rows = [row for row in source.infolist() if row.filename == member]
            if len(rows) != 1 or rows[0].is_dir() or rows[0].file_size > maximum:
                _reject("source_member_invalid")
            with source.open(rows[0]) as stream:
                raw = stream.read(maximum + 1)
            if len(raw) != rows[0].file_size or len(raw) > maximum:
                _reject("source_member_invalid")
            return raw
    except (OSError, ValueError, zipfile.BadZipFile):
        _reject("source_member_invalid")
    raise AssertionError("unreachable")


def _license_bytes(sdist: Path) -> bytes:
    raw_artifact = _bounded_file_bytes(sdist, limit=2 * 1024 * 1024)
    if hashlib.sha256(raw_artifact).hexdigest() != ARTIFACT_SHA256:
        _reject("artifact_hash_mismatch")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw_artifact), mode="r:gz") as archive:
            members = archive.getmembers()
            selected = [item for item in members if item.name == LICENSE_MEMBER]
            package = [item for item in members if item.name == PACKAGE_MEMBER]
            metadata_members = [item for item in members if item.name == METADATA_MEMBER]
            if (len(selected) != 1 or not selected[0].isfile() or selected[0].size > 16 * 1024
                    or len(package) != 1 or not package[0].isfile() or package[0].size > 128 * 1024
                    or len(metadata_members) != 1 or not metadata_members[0].isfile()
                    or metadata_members[0].size > 128 * 1024):
                _reject("artifact_structure_invalid")
            package_stream = archive.extractfile(package[0])
            license_stream = archive.extractfile(selected[0])
            metadata_stream = archive.extractfile(metadata_members[0])
            if package_stream is None or license_stream is None or metadata_stream is None:
                _reject("artifact_structure_invalid")
            metadata = tomllib.loads(package_stream.read(128 * 1024 + 1).decode("utf-8"))
            project = metadata.get("project", {})
            package_metadata = BytesParser().parsebytes(metadata_stream.read(128 * 1024 + 1))
            if (project.get("name") != "pydantic" or package_metadata.get("Name") != "pydantic"
                    or package_metadata.get("Version") != "2.13.4"
                    or package_metadata.get("License-Expression") != "MIT"
                    or project.get("license") != "MIT" or LICENSE_MEMBER.rsplit("/", 1)[-1] not in project.get("license-files", [])):
                _reject("artifact_identity_mismatch")
            raw = license_stream.read(16 * 1024 + 1)
            if len(raw) != selected[0].size or not raw:
                _reject("artifact_structure_invalid")
            raw.decode("utf-8")
            return raw
    except (OSError, ValueError, UnicodeError, tarfile.TarError, KeyError, TypeError):
        _reject("artifact_structure_invalid")
    raise AssertionError("unreachable")


def _card_body(run: ScanRun, source_archive: Path, sdist: Path, prepared_at: str) -> dict:
    if run.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL} or run.project.source_type.value != "zip":
        _reject("source_scan_not_ready")
    if (run.project.root_digest is None or run.provenance.inventory_digest is None
            or run.project.root_digest != run.provenance.inventory_digest):
        _reject("source_inventory_unbound")
    source_bytes = _bounded_file_bytes(source_archive, limit=64 * 1024 * 1024)
    archive_hash = hashlib.sha256(source_bytes).hexdigest()
    if archive_hash != SOURCE_ARCHIVE_SHA256 or archive_hash != run.provenance.input_digest.value:
        _reject("source_input_mismatch")
    named = [item for item in run.components if item.ecosystem == "pypi" and item.name.casefold() == "pydantic"]
    if len(named) != 1 or named[0].version != "2.13.4":
        _reject("resource_ambiguous_or_version_mismatch")
    resource = named[0]
    manifest = _read_member(source_bytes, "backend/pyproject.toml", maximum=262144)
    manifest_hash = hashlib.sha256(manifest).hexdigest()
    matching = [item for item in run.evidence if item.id in resource.evidence_ids
                and item.kind is EvidenceKind.MANIFEST_FIELD
                and item.locator.startswith("backend/pyproject.toml:")
                and item.excerpt == "pydantic==2.13.4"
                and item.content_hash is not None and item.content_hash.value == manifest_hash
                and item.verification_status is VerificationStatus.VERIFIED]
    if len(matching) != 1 or b'"pydantic==2.13.4"' not in manifest:
        _reject("resource_source_unbound")
    license_raw = _license_bytes(sdist)
    return {
        "schema": "openguard.reviewed-obligation-card/1", "state": "pending",
        "prepared_at": prepared_at, "source_commit": SOURCE_COMMIT,
        "source_scan_id": run.id, "source_facts_hash": facts_digest(run),
        "source_status": run.status.value, "source_input_sha256": archive_hash,
        "source_inventory_sha256": run.project.root_digest.value,
        "resource_id": resource.id, "resource_name": resource.name,
        "resource_version": resource.version, "manifest_evidence_id": matching[0].id,
        "manifest_locator": matching[0].locator, "manifest_sha256": manifest_hash,
        "artifact_url": ARTIFACT_URL, "artifact_sha256": ARTIFACT_SHA256,
        "license_member": LICENSE_MEMBER,
        "license_sha256": hashlib.sha256(license_raw).hexdigest(),
        "license_text": license_raw.decode("utf-8"),
        "scope_candidate": "runtime_dependency",
        "scope_basis_to_confirm": "backend/pyproject.toml project.dependencies declares pydantic==2.13.4; whether this describes actual intended use requires human confirmation.",
        "not_reviewed": ["installed wheel and runtime bytes", "pydantic-core and other transitive dependencies",
                         "actual distribution artifact and fulfillment", "other resources and their licenses",
                         "external identity or signature of the reviewer"],
    }


def prepare(db_path: Path, source_scan_id: str, source_archive: Path, sdist: Path,
            *, now: datetime | None = None) -> dict:
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None or at.utcoffset() != timezone.utc.utcoffset(at):
        _reject("prepared_at_invalid")
    body = _card_body(_read_source(db_path, source_scan_id), source_archive, sdist,
                      at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
    return {**body, "card_sha256": hashlib.sha256(canonical_bytes(body)).hexdigest()}


def confirmation_hash(card: dict, record: dict) -> str:
    """Check explicit exact-material statements before any new scan is created."""
    if type(card) is not dict or type(record) is not dict:
        _reject("confirmation_invalid")
    body = {key: value for key, value in card.items() if key != "card_sha256"}
    try:
        card_hash = hashlib.sha256(canonical_bytes(body)).hexdigest()
    except (TypeError, ValueError):
        _reject("card_invalid")
    if card.get("card_sha256") != card_hash:
        _reject("card_hash_mismatch")
    required = {"schema", "card_sha256", "source_scan_id", "resource_id", "resource_version",
                "artifact_sha256", "license_sha256", "scope", "reviewer_self_reported",
                "confirmed_at", "license_text_reviewed_in_full", "license_applies_to_exact_artifact",
                "scope_confirmed", "applicability_basis", "scope_basis", "limits_acknowledged"}
    if set(record) != required or record.get("schema") != "openguard.reviewed-obligation-confirmation/1":
        _reject("confirmation_invalid")
    for key, expected in (("card_sha256", card["card_sha256"]), ("source_scan_id", card["source_scan_id"]),
                          ("resource_id", card["resource_id"]), ("resource_version", card["resource_version"]),
                          ("artifact_sha256", card["artifact_sha256"]), ("license_sha256", card["license_sha256"]),
                          ("scope", card["scope_candidate"])):
        if record.get(key) != expected:
            _reject("confirmation_binding_mismatch")
    if any(record.get(key) is not True for key in ("license_text_reviewed_in_full",
                                                    "license_applies_to_exact_artifact", "scope_confirmed",
                                                    "limits_acknowledged")):
        _reject("confirmation_incomplete")
    if (any(type(record.get(key)) is not str or not 12 <= len(record[key].strip()) <= 1000
            for key in ("applicability_basis", "scope_basis"))
            or type(record.get("reviewer_self_reported")) is not str
            or not 1 <= len(record["reviewer_self_reported"].strip()) <= 100):
        _reject("confirmation_incomplete")
    if type(card.get("prepared_at")) is not str or type(record.get("confirmed_at")) is not str:
        _reject("confirmation_time_invalid")
    try:
        prepared_at = datetime.fromisoformat(card["prepared_at"].replace("Z", "+00:00"))
        confirmed_at = datetime.fromisoformat(record["confirmed_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        _reject("confirmation_time_invalid")
    if (confirmed_at.tzinfo is None or confirmed_at.utcoffset() != timezone.utc.utcoffset(confirmed_at)
            or confirmed_at < prepared_at or confirmed_at > datetime.now(timezone.utc)):
        _reject("confirmation_time_invalid")
    try:
        return hashlib.sha256(canonical_bytes(record)).hexdigest()
    except (TypeError, ValueError):
        _reject("confirmation_invalid")
    raise AssertionError("unreachable")


def bind_reviewed_fact(run: ScanRun, *, card: dict, record: dict, record_hash: str) -> ScanRun:
    """NORMALIZE-stage adapter; B5's unchanged RULES stage remains authoritative."""
    matches = [item for item in run.components if item.ecosystem == "pypi" and item.name.casefold() == "pydantic"]
    if (len(matches) != 1 or matches[0].id != card["resource_id"]
            or matches[0].version != card["resource_version"]
            or run.provenance.input_digest.value != card["source_input_sha256"]
            or run.project.root_digest is None or run.project.root_digest.value != card["source_inventory_sha256"]):
        _reject("rescanned_resource_mismatch")
    resource = matches[0]
    if any(item.id == resource.license_expression_id and item.verification_status is VerificationStatus.VERIFIED
           for item in run.licenses):
        _reject("already_verified")
    now = datetime.now(timezone.utc)
    producer = ProducerRef(type="human", name=record["reviewer_self_reported"].strip(), version="self-reported/1",
                           config_digest={"algorithm": "sha256", "value": record_hash})
    license_eid = "evd_" + str(uuid.uuid5(_NAMESPACE, record_hash + ":license"))
    scope_eid = "evd_" + str(uuid.uuid5(_NAMESPACE, record_hash + ":scope"))
    license_id = "lic_" + str(uuid.uuid5(_NAMESPACE, record_hash + ":MIT"))
    license_evidence = Evidence(
        id=license_eid, kind=EvidenceKind.LICENSE_TEXT, locator=card["artifact_url"] + "#LICENSE",
        excerpt=card["license_text"][:1000], content_hash={"algorithm": "sha256", "value": card["license_sha256"]},
        detected_by=DetectionMethod.MANUAL, producer=producer, observed_at=now,
        verification_status=VerificationStatus.VERIFIED,
    )
    scope_evidence = Evidence(
        id=scope_eid, kind=EvidenceKind.METADATA,
        locator="reviewed-obligation/confirmation-" + record_hash + ".json",
        excerpt=json.dumps({"kind": "openguard.scope.v1", "resource_id": resource.id,
                            "version": resource.version, "scope": record["scope"],
                            "license_expression_id": license_id}, sort_keys=True, separators=(",", ":")),
        content_hash={"algorithm": "sha256", "value": record_hash},
        detected_by=DetectionMethod.MANUAL, producer=producer, observed_at=now,
        verification_status=VerificationStatus.VERIFIED,
    )
    expression = LicenseExpression(
        id=license_id, expression="MIT", normalized_ids=["MIT"], source_url=card["artifact_url"],
        evidence_ids=[license_eid], confidence=1.0, verification_status=VerificationStatus.VERIFIED,
    )
    components = [item.model_copy(update={"license_expression_id": license_id,
                                    "evidence_ids": sorted(set(item.evidence_ids + [license_eid, scope_eid]))})
                  if item.id == resource.id else item for item in run.components]
    evidence = sorted([*run.evidence, license_evidence, scope_evidence], key=lambda item: item.id)
    producers = [*run.provenance.tool_versions, producer]
    return replace_run(run, components=components, evidence=evidence,
                       licenses=sorted([*run.licenses, expression], key=lambda item: item.id),
                       summary=run.summary.model_copy(update={"evidence_count": len(evidence)}),
                       provenance=run.provenance.model_copy(update={"tool_versions": producers}))


def reviewed_plan(plan: PipelinePlan, *, card: dict, record: dict, record_hash: str) -> PipelinePlan:
    if confirmation_hash(card, record) != record_hash:
        _reject("confirmation_hash_mismatch")
    if len(plan.steps) != 7 or plan.steps[3].stage is not ScanStage.NORMALIZE:
        _reject("pipeline_shape_changed")
    original = plan.steps[3].handler
    def normalize(run: ScanRun) -> ScanRun:
        return bind_reviewed_fact(original(run), card=card, record=record, record_hash=record_hash)
    steps = list(plan.steps)
    steps[3] = PipelineStep(ScanStage.NORMALIZE, normalize)
    return PipelinePlan(tuple(steps))


def _private_json_exclusive(path: Path, value: object) -> None:
    """Preserve the exact accepted input and an interrupted attempt for audit."""
    parent = path.parent
    try:
        parent.mkdir(mode=0o700, exist_ok=True)
        SQLiteScanRunRegistry._private_stat(parent, directory=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        _reject("confirmation_replay")
    except Exception:
        _reject("review_record_unavailable")
    try:
        data = canonical_bytes(value)
        with os.fdopen(descriptor, "wb") as sink:
            sink.write(data)
            sink.flush()
            os.fsync(sink.fileno())
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        # Never delete a partially written record: it prevents silent retry.
        _reject("review_record_unavailable")


def _source_snapshot(workspace_root: Path, name: str, source_bytes: bytes,
                     expected_sha256: str) -> tuple[tempfile.TemporaryDirectory, Path]:
    """Give the existing ZIP pipeline a private copy of the verified input."""
    holder = tempfile.TemporaryDirectory(prefix="reviewed-input-", dir=workspace_root)
    staged = Path(holder.name) / name
    try:
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as sink:
            sink.write(source_bytes)
            sink.flush()
            os.fsync(sink.fileno())
        if _sha256_file(staged, limit=64 * 1024 * 1024) != expected_sha256:
            _reject("source_input_mismatch")
        return holder, staged
    except Exception:
        holder.cleanup()
        raise


def apply(data_dir: Path, source_archive: Path, sdist: Path,
          card: dict, record: dict, *, expected_confirmation_sha256: str) -> dict:
    """Apply one explicit confirmation via a fresh original ZIP pipeline.

    The source scan stays terminal and immutable.  A private attempt record is
    written before the new queued run, and never rewritten on failure.  The
    returned receipt is written separately by the operator CLI after success.
    """
    from app.api.models import ZipScanCreateFields
    from app.api.service import ScanApiService
    from app.assessment.service import AssessmentService
    from app.assessment.store import AssessmentStore
    from app.p1.models import P1TaskDeriveRequest, P1TaskRef
    from app.p1.remediation import RemediationService
    from app.p1.remediation_store import RemediationTaskStore
    from app.p1.report_v2 import ReportV2Service
    from app.p1.report_v2_store import ReportV2Store
    from app.pipeline.local_zip import build_local_zip_dependency_plan
    from app.pipeline.worker import ScanPipelineWorker
    from app.reporting import PipelineReportPublisher, ReportArtifactStore

    record_hash = confirmation_hash(card, record)
    if record_hash != expected_confirmation_sha256:
        _reject("confirmation_hash_mismatch")
    source_bytes = _bounded_file_bytes(source_archive, limit=64 * 1024 * 1024)
    if hashlib.sha256(source_bytes).hexdigest() != card.get("source_input_sha256"):
        _reject("source_input_mismatch")
    try:
        at = datetime.fromisoformat(card["prepared_at"].replace("Z", "+00:00"))
        actual = prepare(data_dir / "scans.db", card["source_scan_id"], source_archive, sdist, now=at)
    except (KeyError, TypeError, ValueError):
        _reject("card_invalid")
    if actual != card:
        _reject("card_stale")
    snapshot = None
    try:
        SQLiteScanRunRegistry._private_stat(data_dir, directory=True)
        workspace_root = data_dir / "workspaces"
        report_root = data_dir / "reports"
        SQLiteScanRunRegistry._private_stat(workspace_root, directory=True)
        SQLiteScanRunRegistry._private_stat(report_root, directory=True)
        snapshot, verified_archive = _source_snapshot(
            workspace_root, source_archive.name, source_bytes, card["source_input_sha256"])
        registry = SQLiteScanRunRegistry(data_dir / "scans.db")
        if registry.active_count():
            _reject("scan_runtime_busy")
        source_run = registry.get(card["source_scan_id"]).run
        if facts_digest(source_run) != card["source_facts_hash"]:
            _reject("source_scan_changed")
        # Initialize every existing consumer before reserving a new ScanRun.
        assessment_store = AssessmentStore(data_dir / "assessment.db")
        assessment_service = AssessmentService(registry, assessment_store)
        assessment_service.initialize()
        task_store = RemediationTaskStore(data_dir / "remediation.db")
        task_store.initialize()
        report_store = ReportV2Store(data_dir / "report_v2.db")
        report_store.initialize()
        p0_reports = ReportArtifactStore(report_root)
        registry.assessment_observer = assessment_service.on_terminal

        request = ZipScanCreateFields(
            source_type="zip", idempotency_key="reviewed-obligation-" + record_hash,
            usage=source_run.project.usage,
        )
        candidate = ScanApiService(registry).build_zip_scan_candidate(
            request, staged_name=verified_archive.name, project_name=source_run.project.name,
            input_digest=card["source_input_sha256"],
        )
        review_root = data_dir / "reviewed-obligation"
        confirmation_path = review_root / ("confirmation-" + record_hash + ".json")
        _private_json_exclusive(confirmation_path, record)
        attempt_path = review_root / ("attempt-" + record_hash + ".json")
        _private_json_exclusive(attempt_path, {
            "schema": "openguard.reviewed-obligation-attempt/1", "state": "pending_scan",
            "source_scan_id": source_run.id, "new_scan_id": candidate.run.id,
            "card": card, "confirmation": record, "confirmation_sha256": record_hash,
            "source_archive_sha256": card["source_input_sha256"],
            "artifact_sha256": card["artifact_sha256"],
        })
        accepted, created = ScanApiService(registry).commit_zip_scan_candidate(candidate)
        if not created or accepted.scan_id != candidate.run.id:
            _reject("confirmation_replay")
        plan = reviewed_plan(build_local_zip_dependency_plan(
            verified_archive, workspace_root, clock=lambda: datetime.now(timezone.utc),
            external_scanners=False, ai_enabled=False,
        ), card=card, record=record, record_hash=record_hash)
        stored = ScanPipelineWorker(registry, terminal_publisher=PipelineReportPublisher(p0_reports).publish).run(
            accepted.scan_id, plan,
        )
        run = stored.run
        target = [item for item in run.components if item.id == card["resource_id"]]
        obligations = [item for item in run.obligations if target and item.license_expression_id == target[0].license_expression_id]
        if run.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL} or not obligations:
            _reject("rules_did_not_generate_obligation")
        assessment = assessment_store.latest(run.id)
        if assessment is None or not assessment.formal or assessment.facts_hash != facts_digest(run):
            _reject("formal_assessment_unavailable")
        selected = [item for item in assessment.obligations if card["resource_id"] in item.resource_ids]
        if not selected:
            _reject("formal_obligation_unavailable")
        tasks = RemediationService(registry, assessment_store, task_store).derive(
            run.id, assessment.id,
            P1TaskDeriveRequest(idempotency_key="reviewed-obligation-" + record_hash,
                                expected_facts_hash=assessment.facts_hash),
        ).items
        obligation_tasks = [item for item in tasks if item.origin.kind == "obligation"
                            and card["resource_id"] in item.resource_ids]
        if not obligation_tasks:
            _reject("obligation_task_unavailable")
        report = ReportV2Service(registry, assessment_store, task_store, report_store).create(
            run.id, assessment.id, idempotency_key="reviewed-obligation-" + record_hash,
            task_refs=[P1TaskRef(task_id=item.task_id, version=item.version) for item in obligation_tasks],
            notice_refs=[],
        )
        service = ReportV2Service(registry, assessment_store, task_store, report_store)
        artifacts = {}
        for format in ("json", "html"):
            raw = service.artifact(run.id, assessment.id, report.snapshot_id, format)
            if raw is None:
                _reject("report_artifact_unavailable")
            artifact = next((item for item in report.artifacts if item.format == format), None)
            if artifact is None or artifact.content_hash != hashlib.sha256(raw).hexdigest():
                _reject("report_artifact_mismatch")
            artifacts[format] = {"sha256": artifact.content_hash,
                                 "size_bytes": len(raw), "href": artifact.href}
        return {
            "schema": "openguard.reviewed-obligation-result/1", "data_level": "acceptance_real_reviewed",
            "source_scan_id": source_run.id, "new_scan_id": run.id,
            "source_facts_hash": card["source_facts_hash"], "facts_hash": assessment.facts_hash,
            "confirmation_sha256": record_hash, "assessment_id": assessment.id,
            "obligations": [{"obligation_id": item.id, "rule_id": item.rule_id,
                             "rule_version": item.rule_version, "evidence_ids": item.source_evidence_ids,
                             "resource_id": card["resource_id"]} for item in obligations],
            "task_refs": [{"task_id": item.task_id, "version": item.version} for item in obligation_tasks],
            "report_snapshot_id": report.snapshot_id,
            "artifacts": artifacts,
            "review_attempt_path": str(attempt_path),
        }
    except ReviewAdmissionError:
        raise
    except Exception as error:
        # Never roll back an already persisted scan or overwrite prior reports.
        code = getattr(error, "code", "")
        suffix = code if type(code) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) else type(error).__name__.lower()
        raise ReviewAdmissionError("review_apply_failed_" + suffix) from error
    finally:
        if snapshot is not None:
            snapshot.cleanup()
    raise AssertionError("unreachable")
