"""Explicit, synthetic-only P1 integration application factory.

This module is intentionally separate from the production application factory.
It provides a narrow, reproducible data space for P1 API integration work and
does not start scanners, dispatchers, models, metadata refreshes, or observers.
Importing it is side-effect free; callers must explicitly call :func:`initialize`.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import sqlite3
import stat
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.main import create_app
from app.api.models import ErrorBody, ErrorEnvelope
from app.assessment.engine import facts_digest, build_assessment
from app.assessment.service import AssessmentService
from app.assessment.store import AssessmentStore
from app.domain.models import ScanRun
from app.domain.usage import UsageDeclaration
from app.p1.remediation import RemediationService
from app.p1.remediation_store import RemediationTaskStore
from app.p1.report_v2 import ReportV2Service
from app.p1.report_v2_graph import ReportGraphReader
from app.p1.report_v2_store import ReportV2Store
from app.persistence import SQLiteScanRunRegistry
from app.persistence.scan_registry import ScanRegistryError


SEED_VERSION = "p1-dev-integration/2"
MARKER_NAME = ".openguard-dev-integration.json"
MANIFEST_NAME = "dev-manifest.json"
_DEV_PREFIX = "p1-dev-"
_DATABASES = ("scans.db", "assessment.db", "remediation.db", "report_v2.db")
_NOW = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)


class DevIntegrationError(RuntimeError):
    """Stable failure code for the opt-in isolated development environment."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DevManifest:
    synthetic: bool
    seed_version: str
    root_id: str
    code_version: str
    scans: dict[str, str]
    assessments: dict[str, dict[str, Any]]
    comparisons: dict[str, str]
    graph_refs: dict[str, dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _repository_root(repository_root: Path | None) -> Path:
    value = repository_root if repository_root is not None else Path(__file__).resolve().parents[2]
    try:
        value = value.resolve(strict=True)
    except OSError as error:
        raise DevIntegrationError("repository_root_invalid") from error
    if not value.is_dir() or value.is_symlink():
        raise DevIntegrationError("repository_root_invalid")
    return value


def _expected_parent(repository_root: Path) -> Path:
    return repository_root / "output" / "manual-fixes"


def _root(root: Path, repository_root: Path | None, *, must_exist: bool) -> Path:
    repo = _repository_root(repository_root)
    parent = _expected_parent(repo)
    raw = root.expanduser()
    if ".." in raw.parts:
        raise DevIntegrationError("root_invalid")
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    # Check the lexical path before resolve() so an alias such as
    # `repo/alias -> repo/output` cannot hide an unsafe ancestor.
    probe = Path(raw.anchor)
    for part in raw.parts[1:]:
        probe /= part
        if probe.is_symlink():
            raise DevIntegrationError("root_unsafe")
    try:
        # strict=False is intentional only for the requested leaf; the parent
        # relationship below prevents traversal through an arbitrary directory.
        candidate = root.expanduser().resolve(strict=False)
        expected = parent.resolve(strict=False)
    except OSError as error:
        raise DevIntegrationError("root_invalid") from error
    if candidate.parent != expected or not candidate.name.startswith(_DEV_PREFIX):
        raise DevIntegrationError("root_invalid")
    if any(item.is_symlink() for item in (candidate, *candidate.parents)):
        raise DevIntegrationError("root_unsafe")
    if must_exist and not candidate.is_dir():
        raise DevIntegrationError("root_uninitialized")
    return candidate


def _private_directory(path: Path) -> None:
    try:
        info = path.stat()
    except OSError as error:
        raise DevIntegrationError("root_unavailable") from error
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise DevIntegrationError("root_unsafe")


def _private_regular(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise DevIntegrationError("root_uninitialized") from error
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077):
        raise DevIntegrationError("root_unsafe")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(_json_bytes(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DevIntegrationError("root_unavailable") from error


def _load_json(path: Path) -> dict[str, Any]:
    _private_regular(path)
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError, TypeError) as error:
        raise DevIntegrationError("root_uninitialized") from error
    if not isinstance(value, dict):
        raise DevIntegrationError("root_uninitialized")
    return value


def _new_root_id() -> str:
    """Generate an instance identity independent of host/container mount paths."""
    return "dev_" + uuid4().hex


def _validate_marker(root: Path) -> dict[str, Any]:
    marker = _load_json(root / MARKER_NAME)
    required = {"synthetic", "seed_version", "root_id", "code_version", "tool"}
    if (set(marker) != required or marker["synthetic"] is not True
            or marker["seed_version"] != SEED_VERSION
            or marker["tool"] != "app.dev_integration"
            or not isinstance(marker["root_id"], str) or not marker["root_id"]
            or not isinstance(marker["code_version"], str) or not marker["code_version"]):
        raise DevIntegrationError("root_uninitialized")
    return marker


def _validate_database_set(root: Path) -> None:
    for name in _DATABASES:
        path = root / name
        if path.is_symlink() or not path.exists():
            raise DevIntegrationError("root_uninitialized")
        _private_regular(path)


_REQUIRED_TABLES = {
    "scans.db": {"registry_metadata", "scan_runs"},
    "assessment.db": {"assessments", "assessment_requests", "assessment_jobs"},
    "remediation.db": {"tasks", "task_versions", "derive_requests"},
    "report_v2.db": {"report_snapshots", "report_artifacts", "report_requests"},
}

# Seed-v2 sidecar expectations mirror the existing stores' columns and keys.
# This is a dev-entry check, not a migration or a new public storage contract.
_SIDECAR_COLUMNS = {
    'assessments': ('id:TEXT:0:1 scan_id:TEXT version:INTEGER cache_key:TEXT payload:BLOB html:BLOB report_json:BLOB html_hash:TEXT json_hash:TEXT', [('scan_id', 'version'), ('scan_id', 'cache_key')]),
    'assessment_requests': ('scan_id:TEXT:1:1 request_key:TEXT:1:2 cache_key:TEXT assessment_id:TEXT', []),
    'assessment_jobs': ('scan_id:TEXT:1:1 request_id:TEXT:1:2 fingerprint:TEXT status:TEXT assessment_id:TEXT:0 error:TEXT:0 created_at:TEXT elapsed_seconds:REAL:0 model_calls:INTEGER:1:0:0 cache_hit:INTEGER:1:0:0', []),
    'chat_sessions': ('scan_id:TEXT:0:1 generation:INTEGER', []),
    'chat_turns': ('scan_id:TEXT:1:1 request_id:TEXT:1:2 generation:INTEGER assessment_id:TEXT question:TEXT answer:TEXT:0 evidence_json:TEXT status:TEXT error:TEXT:0 created_at:TEXT elapsed_seconds:REAL:0 bytes:INTEGER', []),
    'tasks': ('task_id:TEXT:0:1 scan_id:TEXT assessment_id:TEXT origin_key:TEXT created_at:TEXT version:INTEGER payload:BLOB payload_hash:TEXT', [('scan_id', 'assessment_id', 'origin_key')]),
    'task_versions': ('task_id:TEXT:1:1 version:INTEGER:1:2 payload:BLOB payload_hash:TEXT', []),
    'derive_requests': ('scan_id:TEXT:1:1 assessment_id:TEXT:1:2 request_key:TEXT:1:3 fingerprint:TEXT task_ids:BLOB task_ids_hash:TEXT', []),
    'report_snapshots': ('snapshot_id:TEXT:0:1 scan_id:TEXT assessment_id:TEXT created_at:TEXT payload:BLOB payload_hash:TEXT', []),
    'report_artifacts': ('snapshot_id:TEXT:1:1 format:TEXT:1:2 payload:BLOB payload_hash:TEXT size_bytes:INTEGER', []),
    'report_requests': ('scan_id:TEXT:1:1 assessment_id:TEXT:1:2 request_key:TEXT:1:3 fingerprint:TEXT snapshot_id:TEXT', []),
}


def _check_sidecar_schema(connection, name):
    tables = set(_REQUIRED_TABLES[name])
    if name == 'assessment.db':
        tables |= {'chat_sessions', 'chat_turns'}
    objects = connection.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    indexes = {'task_page'} if name == 'remediation.db' else {'report_scope'} if name == 'report_v2.db' else set()
    expected_objects = {('table', t) for t in tables} | {('index', i) for i in indexes}
    if set(objects) != expected_objects or connection.execute('PRAGMA user_version').fetchone() != (0,):
        raise DevIntegrationError('root_uninitialized')
    for table in tables:
        encoded, unique_keys = _SIDECAR_COLUMNS[table]
        expected = []
        for ordinal, word in enumerate(encoded.split()):
            pieces = word.split(':')
            column, kind = pieces[:2]
            nullable = int(pieces[2]) if len(pieces) > 2 else 1
            primary = int(pieces[3]) if len(pieces) > 3 else 0
            default = pieces[4] if len(pieces) > 4 else None
            expected.append((ordinal, column, kind, nullable, default, primary))
        actual = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        extended = connection.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
        sql = connection.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0]
        if (actual != expected or extended != [(*row, 0) for row in expected]
                or connection.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
                or re.search(r'\b(CHECK|REFERENCES|COLLATE|GENERATED|AUTOINCREMENT|STRICT)\b|WITHOUT\s+ROWID|ON\s+CONFLICT', sql, re.I)):
            raise DevIntegrationError('root_uninitialized')
        primary_key = tuple(row[1] for row in sorted(expected, key=lambda r: r[5]) if row[5])
        expected_keys = {('u', key) for key in unique_keys} | {('pk', primary_key)}
        actual_keys = set()
        for index in connection.execute(f'PRAGMA index_list("{table}")'):
            escaped = index[1].replace('"', '""')
            columns = tuple(row[2] for row in connection.execute(f'PRAGMA index_info("{escaped}")'))
            details = connection.execute(f'PRAGMA index_xinfo("{escaped}")').fetchall()
            if any(row[3] != 0 or row[4] != 'BINARY' for row in details if row[5]):
                raise DevIntegrationError('root_uninitialized')
            if index[4] or (index[2] and index[3] not in {'u', 'pk'}):
                raise DevIntegrationError('root_uninitialized')
            if index[2]:
                actual_keys.add((index[3], columns))
            elif not ((index[1], columns) in {
                ('task_page', ('scan_id', 'assessment_id', 'created_at', 'task_id')),
                ('report_scope', ('scan_id', 'assessment_id', 'created_at', 'snapshot_id')),
            }):
                raise DevIntegrationError('root_uninitialized')
        if actual_keys != expected_keys:
            raise DevIntegrationError('root_uninitialized')


def _readonly_schema_preflight(root: Path) -> None:
    """Reject a wrong/corrupt sidecar before any store can initialize it."""
    for name, required in _REQUIRED_TABLES.items():
        path = root / name
        try:
            connection = sqlite3.connect(
                f"file:{quote(str(path), safe='/')}?mode=ro", uri=True, timeout=1,
            )
            try:
                connection.execute("PRAGMA query_only=ON")
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if not required.issubset(tables):
                    raise DevIntegrationError('root_uninitialized')
                if name == 'scans.db':
                    # Reuse the P0 verifier itself, before its writable _connect.
                    SQLiteScanRunRegistry._verify_schema(connection)
                else:
                    _check_sidecar_schema(connection, name)
            finally:
                connection.close()
        except (OSError, sqlite3.Error, ScanRegistryError) as error:
            raise DevIntegrationError("root_uninitialized") from error
        if not required.issubset(tables):
            raise DevIntegrationError("root_uninitialized")


def read_manifest(root: Path, *, repository_root: Path | None = None) -> DevManifest:
    """Read an already-created synthetic instance without writing any database."""
    path = _root(root, repository_root, must_exist=True)
    _private_directory(path)
    marker = _validate_marker(path)
    _validate_database_set(path)
    _readonly_schema_preflight(path)
    value = _load_json(path / MANIFEST_NAME)
    try:
        manifest = DevManifest(**value)
    except TypeError as error:
        raise DevIntegrationError("root_uninitialized") from error
    if (manifest.synthetic is not True or manifest.seed_version != SEED_VERSION
            or manifest.root_id != marker["root_id"] or manifest.code_version != marker["code_version"]):
        raise DevIntegrationError("root_uninitialized")
    required = {"completed_base", "completed_target", "partial"}
    if set(manifest.scans) != required or set(manifest.comparisons) != {"base_scan_id", "target_scan_id"}:
        raise DevIntegrationError("root_uninitialized")
    if set(manifest.assessments) != set(manifest.scans.values()) or set(manifest.graph_refs) != set(manifest.scans.values()):
        raise DevIntegrationError("root_uninitialized")
    return manifest


def validate_root(root: Path, *, repository_root: Path | None = None) -> DevManifest:
    """Validate isolation and return the manifest.  This function never seeds."""
    manifest = read_manifest(root, repository_root=repository_root)
    path = _root(root, repository_root, must_exist=True)
    registry = None
    try:
        registry = SQLiteScanRunRegistry(path / "scans.db")
        assessments = AssessmentStore(path / "assessment.db", min_free_bytes=0)
        tasks = RemediationTaskStore(path / "remediation.db", min_free_bytes=0)
        reports = ReportV2Store(path / "report_v2.db", min_free_bytes=0)
        for scan_id, row in manifest.assessments.items():
            run = registry.get(scan_id).run
            assessment = assessments.get(scan_id, row["assessment_id"])
            if (run.id != scan_id or assessment is None or assessment.scan_id != scan_id
                    or assessment.version != row["version"] or assessment.facts_hash != row["facts_hash"]
                    or assessment.usage_hash != row["usage_hash"] or assessment.facts_hash != facts_digest(run)
                    or assessment.formal is not True):
                raise DevIntegrationError("root_uninitialized")
            # This read proves the sidecar is an initialized SQLite task store;
            # an empty task list is the expected post-seed state.
            tasks.page(scan_id, row["assessment_id"], limit=1)
        # `replay` reaches the report store schema without creating a report.
        reports.replay(next(iter(manifest.scans.values())), next(iter(manifest.assessments.values()))["assessment_id"],
                       "dev-integration-probe", None)
    except DevIntegrationError:
        raise
    except Exception as error:
        raise DevIntegrationError("root_uninitialized") from error
    finally:
        if registry is not None:
            registry.close()
    return manifest


def _fixture() -> dict[str, Any]:
    # This fixture belongs to this repository's source tree.  An injected
    # repository_root changes only the safe temporary data location in tests;
    # it must never turn an arbitrary directory into a fixture source.
    path = Path(__file__).resolve().parents[2] / "examples" / "sample-scan-result.json"
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError, TypeError) as error:
        raise DevIntegrationError("seed_fixture_unavailable") from error
    if not isinstance(value, dict):
        raise DevIntegrationError("seed_fixture_unavailable")
    return value


def _scan_payload(source: dict[str, Any], *, number: int, revision: str, status: str) -> dict[str, Any]:
    value = deepcopy(source)
    scan_id = "scn_" + str(UUID(int=number))
    value.update(
        id=scan_id,
        idempotency_key=None,
        status="queued",
        stage="queued",
        progress=0,
        created_at=_NOW.isoformat().replace("+00:00", "Z"),
        started_at=None,
        finished_at=None,
        report_links=[],
        errors=[],
    )
    value["project"].update(
        id="prj_" + str(UUID(int=4242)),
        name="OpenGuard synthetic P1 integration fixture",
        source_type="git",
        source="https://github.com/openguard-synthetic/p1-fixture.git",
        revision=revision,
        root_digest={"algorithm": "sha256", "value": hashlib.sha256(revision.encode()).hexdigest()},
        created_at=_NOW.isoformat().replace("+00:00", "Z"),
    )
    if number == 102:
        value["components"][0]["version"] = "2.0.0"
    value["summary"] = {
        "component_count": len(value["components"]),
        "ai_asset_count": len(value["ai_assets"]),
        "evidence_count": len(value["evidence"]),
        "finding_counts": {name: sum(item["outcome"] == name for item in value["findings"])
                           for name in ("pass", "warning", "review_required", "unknown")},
    }
    if status == "partial":
        value.update(status="partial", stage="report", progress=95,
                     started_at=_NOW.isoformat().replace("+00:00", "Z"),
                     finished_at=_NOW.isoformat().replace("+00:00", "Z"),
                     errors=[{"code": "synthetic_coverage_gap", "stage": "scan",
                              "message": "Synthetic fixture coverage is incomplete.", "recoverable": True}])
    return value


def _persist_run(registry: SQLiteScanRunRegistry, payload: dict[str, Any]) -> ScanRun:
    queued_payload = deepcopy(payload)
    queued_payload.update(status="queued", stage="queued", progress=0, started_at=None, finished_at=None, errors=[])
    queued = ScanRun.model_validate(queued_payload)
    registry.create(queued)
    running_payload = deepcopy(queued_payload)
    running_payload.update(status="running", stage="ingestion", progress=5,
                           started_at=_NOW.isoformat().replace("+00:00", "Z"))
    running = ScanRun.model_validate(running_payload)
    registry.replace(running, expected_revision=1)
    final_payload = deepcopy(payload)
    if final_payload["status"] == "queued":
        final_payload.update(status="completed", stage="completed", progress=100,
                             started_at=_NOW.isoformat().replace("+00:00", "Z"),
                             finished_at=_NOW.isoformat().replace("+00:00", "Z"))
    final = ScanRun.model_validate(final_payload)
    registry.replace(final, expected_revision=2)
    return final


def initialize(root: Path, *, repository_root: Path | None = None,
               code_version: str = "unknown") -> DevManifest:
    """Create one private synthetic development instance; never overwrite it."""
    repo = _repository_root(repository_root)
    if not isinstance(code_version, str) or not code_version.strip() or len(code_version) > 200:
        raise DevIntegrationError("code_version_invalid")
    path = _root(root, repo, must_exist=False)
    parent = _expected_parent(repo)
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise DevIntegrationError("root_unavailable") from error
    if path.exists():
        # The launcher may pre-create the exact bind-mount leaf.  Accept only
        # an empty private directory; an unmarked file or database is never a
        # safe candidate for a synthetic instance.
        _private_directory(path)
        try:
            if any(path.iterdir()):
                raise DevIntegrationError("root_already_initialized")
        except OSError as error:
            raise DevIntegrationError("root_unavailable") from error
    else:
        try:
            path.mkdir(mode=0o700)
        except OSError as error:
            raise DevIntegrationError("root_unavailable") from error
    _private_directory(path)

    registry = SQLiteScanRunRegistry(path / "scans.db")
    assessment_store = AssessmentStore(path / "assessment.db", min_free_bytes=0)
    task_store = RemediationTaskStore(path / "remediation.db", min_free_bytes=0)
    report_store = ReportV2Store(path / "report_v2.db", min_free_bytes=0)
    try:
        AssessmentService(registry, assessment_store, provider=None).initialize()
        task_store.initialize()
        report_store.initialize()
        fixture = _fixture()
        base = _persist_run(registry, _scan_payload(fixture, number=101, revision="synthetic-base-1", status="completed"))
        target = _persist_run(registry, _scan_payload(fixture, number=102, revision="synthetic-target-2", status="completed"))
        partial = _persist_run(registry, _scan_payload(fixture, number=103, revision="synthetic-partial-3", status="partial"))
        usage = UsageDeclaration(preset="internal", declared_at=_NOW)
        assessments: dict[str, dict[str, Any]] = {}
        graph_refs: dict[str, dict[str, str]] = {}
        graph_reader = ReportGraphReader(max_nodes=20_000, max_edges=60_000)
        for run in (base, target, partial):
            assessment = build_assessment(run, usage, generated_at=_NOW)
            assessment_store.create(assessment, idempotency_key="synthetic-" + run.id, run=run)
            stored = registry.get(run.id)
            reference, _ = graph_reader.capture(stored)
            assessments[run.id] = {
                "assessment_id": assessment.id,
                "version": assessment.version,
                "facts_hash": assessment.facts_hash,
                "usage_hash": assessment.usage_hash,
            }
            graph_refs[run.id] = reference.model_dump(mode="json")
        manifest = DevManifest(
            synthetic=True,
            seed_version=SEED_VERSION,
            root_id=_new_root_id(),
            code_version=code_version,
            scans={"completed_base": base.id, "completed_target": target.id, "partial": partial.id},
            assessments=assessments,
            comparisons={"base_scan_id": base.id, "target_scan_id": target.id},
            graph_refs=graph_refs,
        )
        _atomic_json(path / MANIFEST_NAME, manifest.to_dict())
        _validate_database_set(path)
        _atomic_json(path / MARKER_NAME, {"synthetic": True, "seed_version": SEED_VERSION,
                                          "root_id": manifest.root_id, "code_version": code_version,
                                          "tool": "app.dev_integration"})
        return read_manifest(path, repository_root=repo)
    except Exception as error:
        if isinstance(error, DevIntegrationError):
            raise
        raise DevIntegrationError("seed_failed") from error
    finally:
        registry.close()


def create_dev_app(root: Path, *, origins: tuple[str, ...], repository_root: Path | None = None):
    """Wire existing P1 services over an initialized synthetic root only."""
    path = _root(root, repository_root, must_exist=True)
    manifest = validate_root(path, repository_root=repository_root)
    if not origins or any(not isinstance(origin, str) or not origin for origin in origins):
        raise DevIntegrationError("origin_invalid")
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password
                or parsed.port is None):
            raise DevIntegrationError("origin_invalid")
    configured_origins = os.environ.get("OPENGUARD_WEB_ORIGINS")
    if configured_origins != ",".join(origins):
        # The shared factory intentionally resolves its origin allowlist at
        # request time.  The launcher therefore supplies this value in the
        # isolated process environment before the factory is constructed;
        # this function never mutates a caller's environment.
        raise DevIntegrationError("origin_configuration_invalid")
    registry = SQLiteScanRunRegistry(path / "scans.db")
    assessment_store = AssessmentStore(path / "assessment.db", min_free_bytes=0)
    task_store = RemediationTaskStore(path / "remediation.db", min_free_bytes=0)
    report_store = ReportV2Store(path / "report_v2.db", min_free_bytes=0)
    assessment_service = AssessmentService(registry, assessment_store, provider=None)
    remediation_service = RemediationService(registry, assessment_store, task_store)
    report_service = ReportV2Service(registry, assessment_store, task_store, report_store,
                                     graph_reader=ReportGraphReader(max_nodes=20_000, max_edges=60_000))
    app = create_app(registry, close_registry=True, assessment_service=assessment_service,
                     remediation_service=remediation_service, report_v2_service=report_service)

    @app.middleware("http")
    async def dev_write_boundary(request: Request, call_next):
        # Fixed assessment GET requires the existing service, but development
        # integration never enables assessment/chat/reassessment or scans.
        if request.method in {"POST", "PATCH", "DELETE"}:
            parts = request.url.path.strip("/").split("/")
            task = (len(parts) == 8 and parts[:3] == ["api", "v1", "scans"]
                    and parts[4] == "assessments" and parts[6] == "remediation-tasks"
                    and (request.method == "PATCH" or (request.method == "POST" and parts[7] == "derive")))
            report = (request.method == "POST" and len(parts) == 7 and parts[:3] == ["api", "v1", "scans"]
                      and parts[4] == "assessments" and parts[6] == "report-v2")
            if not task and not report:
                request_id = "req_dev_" + uuid4().hex
                payload = ErrorEnvelope(error=ErrorBody(
                    code="feature_disabled", message="This write operation is disabled in isolated development.",
                    request_id=request_id, details={"reason": "dev_integration_write_disabled"},
                ))
                return JSONResponse(status_code=503, headers={"X-Request-ID": request_id},
                                    content=payload.model_dump(mode="json"))
        return await call_next(request)

    identity = {key: manifest.to_dict()[key] for key in ('root_id', 'synthetic', 'seed_version')}
    identity_header = json.dumps(identity, sort_keys=True, separators=(',', ':'))

    @app.middleware("http")
    async def dev_instance_identity(request: Request, call_next):
        # Development-only transport metadata; no P0/P1 JSON or production route changes.
        # A supplied precondition also prevents writes if the peer changes after bind.
        supplied = request.headers.get('X-OpenGuard-Dev-Identity')
        if supplied is not None:
            try:
                provided = json.loads(supplied)
                matches = (isinstance(provided, dict) and provided.get('synthetic') is True
                           and provided == identity)
            except (ValueError, TypeError):
                matches = False
            if not matches:
                return JSONResponse(status_code=409, content={'detail': 'development identity mismatch'},
                                    headers={'X-OpenGuard-Dev-Identity': identity_header})
        response = await call_next(request)
        response.headers['X-OpenGuard-Dev-Identity'] = identity_header
        return response

    app.state.dev_integration_root = path
    app.state.dev_integration_manifest = manifest.to_dict()
    return app
