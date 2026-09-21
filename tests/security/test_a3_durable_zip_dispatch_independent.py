"""Luna-owned black-box acceptance tests for durable ZIP dispatch.

These tests intentionally build their ZIP bytes, multipart body, identity
projection, SQLite snapshots, and crash-process observations independently of
the implementation-side unit tests.  The original I1 storage assertions stay
unchanged; the appended I2 cases exercise the lifecycle, recovery, dispatch,
and report-visibility contract with real child processes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.client
import io
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
import selectors
import socket
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from starlette.datastructures import Headers, UploadFile
from fastapi.testclient import TestClient

import app.api.zip_scan as zip_scan_module
import app.persistence.zip_dispatch as zip_dispatch_module
from app.ai import OllamaProvider, apply_ai_remediations
from app.api import create_app, create_default_app
from app.api.models import GitScanCreateRequest, ZipScanCreateFields
from app.api.service import ApiError, ScanApiService
from app.api.zip_scan import ZipScanRuntime
from app.domain.models import (
    Component,
    ComponentType,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    FindingOutcome,
    HashValue,
    LicenseExpression,
    ProducerRef,
    ProducerType,
    ReportFormat,
    ReportLink,
    RiskFinding,
    Severity,
    ScanError,
    ScanRun,
    ScanStage,
    ScanStatus,
    VerificationStatus,
)
from app.persistence import (
    SQLiteScanRunRegistry,
    ZipDispatchDescriptor,
    ZipDispatchError,
    ZipDispatchStore,
    ZipExecutionProfile,
)
from app.pipeline.zip_dispatcher import ZipDispatcher
from app.reporting import PipelineReportPublisher, ReportArtifactStore


# Independent fixed I1 capacity oracle.  These values are intentionally not
# imported from the implementation so a changed constant cannot self-approve.
ORACLE_MAX_INPUTS = 8
ORACLE_MAX_BYTES = 512 * 1024 * 1024
ORACLE_RESERVATION_BYTES = 64 * 1024 * 1024


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _dynamic_zip(label: str = "independent") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("requirements.txt", f"requests==2.32.0\n# {label}\n")
        archive.writestr("src/{label}.py", "print('OpenGuard independent fixture')\n")
    return output.getvalue()


def _manual_multipart(content: bytes, *, key: str | None = None, filename: str = "independent.zip") -> tuple[bytes, str]:
    boundary = "----OpenGuardLuna" + hashlib.sha256(os.urandom(24)).hexdigest()[:24]
    parts = [
        (
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="source_type"\r\n\r\n'
            "zip\r\n"
        ).encode(),
    ]
    if key is not None:
        parts.append(
            (
                f'--{boundary}\r\n'
                'Content-Disposition: form-data; name="idempotency_key"\r\n\r\n'
                f"{key}\r\n"
            ).encode()
        )
    parts.append(
        (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _post_raw(client: TestClient, content: bytes, *, key: str | None = None, filename: str = "independent.zip"):
    body, boundary = _manual_multipart(content, key=key, filename=filename)
    return client.post(
        "/api/v1/scans",
        content=body,
        headers={
            "content-type": f"multipart/form-data; boundary={boundary}",
            "content-length": str(len(body)),
        },
    )


@pytest.fixture
def independent_harness(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ZipDispatchStore(dispatch_root, upload_root)
    runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        dispatch_store=store,
    )
    app = create_app(registry, zip_runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, registry, store, upload_root, dispatch_root, workspace_root
    registry.close()


def _make_prepared_bundle(tmp_path: Path, *, content: bytes | None = None):
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ZipDispatchStore(dispatch_root, upload_root)
    archive = upload_root / "openguard-upload-independent.zip"
    reservation = store.reserve_upload()
    archive.write_bytes(content if content is not None else _dynamic_zip("prepared"))
    os.chmod(archive, 0o600)
    store.bind_upload(reservation, archive)
    service = ScanApiService(registry)
    candidate = service.build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="independent",
        input_digest=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    profile = ZipExecutionProfile.from_provider(
        ai_requested=False,
        provider=None,
        ai_timeout_seconds=10.0,
    )
    descriptor = store.prepare(archive, candidate.run, profile, reservation)
    return registry, store, archive, descriptor, candidate.run, workspace_root


def _manual_identity(run: ScanRun) -> str:
    """Recompute the immutable identity projection without implementation code."""

    def utc(value: object) -> str:
        return value.isoformat().replace("+00:00", "Z")  # type: ignore[union-attr]

    projection = {
        "contract_version": run.contract_version,
        "id": run.id,
        "idempotency_key": run.idempotency_key,
        "created_at": utc(run.created_at),
        "project": {
            "id": run.project.id,
            "name": run.project.name,
            "source_type": run.project.source_type.value,
            "source": run.project.source,
            "created_at": utc(run.project.created_at),
        },
        "provenance": {
            "input_digest": run.provenance.input_digest.model_dump(mode="json"),
        },
    }
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _asgi_call(app, body: bytes, *, content_type: str, content_length: str | None = None, forbid_receive: bool = False):
    async def invoke():
        received = 0
        sent: list[dict[str, object]] = []
        messages = [{"type": "http.request", "body": body, "more_body": False}]

        async def receive():
            nonlocal received
            received += 1
            if forbid_receive:
                raise AssertionError("ASGI receive consumed a byte before quota reservation")
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message: dict[str, object]):
            sent.append(message)

        headers = [(b"content-type", content_type.encode())]
        if content_length is not None:
            headers.append((b"content-length", content_length.encode()))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/scans",
            "raw_path": b"/api/v1/scans",
            "query_string": b"",
            "headers": headers,
            "client": ("independent", 1),
            "server": ("independent", 80),
            "root_path": "",
        }
        await app(scope, receive, send)
        payload = b"".join(
            message.get("body", b"")
            for message in sent
            if message.get("type") == "http.response.body"
        )
        status = next(message["status"] for message in sent if message.get("type") == "http.response.start")
        return int(status), payload, received

    return asyncio.run(invoke())


def test_i1_independent_http_prepares_ready_and_keeps_i2_idle(independent_harness) -> None:
    client, registry, store, upload_root, dispatch_root, _ = independent_harness
    response = _post_raw(client, _dynamic_zip("http"), key="luna-http-001")

    assert response.status_code == 202
    scan_id = response.json()["scan_id"]
    stored = registry.get(scan_id).run
    ready = store.read(scan_id, state="ready")
    assert stored.status is ScanStatus.QUEUED
    assert ready is not None
    assert store.read(scan_id, state="prepared") is None
    assert ready.upload_name == stored.project.source
    assert ready.input_sha256 == stored.provenance.input_digest.value
    assert ready.run_identity_sha256 == _manual_identity(stored)
    assert ready.execution_profile.as_payload() == {
        "plan_version": "zip-dependency-v1",
        "ai_requested": False,
        "ai_identity": None,
        "ai_timeout_seconds": 10.0,
    }
    assert sorted(path.name for path in upload_root.iterdir()) == [ready.upload_name]
    assert sorted(path.name for path in dispatch_root.iterdir()) == [f"{scan_id}.ready.json"]
    assert stat.S_IMODE((upload_root / ready.upload_name).stat().st_mode) == 0o600
    assert stat.S_IMODE((dispatch_root / f"{scan_id}.ready.json").stat().st_mode) == 0o600


def test_i1_strict_descriptor_json_rejects_unknown_duplicate_utf8_nonfinite_and_bool(tmp_path: Path) -> None:
    registry, store, archive, descriptor, _, _ = _make_prepared_bundle(tmp_path)
    canonical = descriptor.to_bytes()
    cases: list[bytes] = []

    unknown = descriptor.as_payload()
    unknown["unknown"] = True
    cases.append(json.dumps(unknown, sort_keys=True, separators=(",", ":")).encode())

    cases.append(b'{"schema":"openguard.zip-dispatch","schema":"openguard.zip-dispatch"}')
    cases.append(canonical + b"\xff")

    nonfinite = descriptor.as_payload()
    nonfinite["execution_profile"]["ai_timeout_seconds"] = float("nan")  # type: ignore[index]
    cases.append(json.dumps(nonfinite, sort_keys=True, separators=(",", ":")).encode())

    bool_version = descriptor.as_payload()
    bool_version["version"] = True
    cases.append(json.dumps(bool_version, sort_keys=True, separators=(",", ":")).encode())

    for raw in cases:
        with pytest.raises(ZipDispatchError) as failure:
            ZipDispatchDescriptor.from_bytes(raw)
        assert failure.value.code == "dispatch_descriptor_invalid"

    registry.close()


def test_i1_descriptor_binds_identity_filename_and_refuses_prepared_ready_conflict(tmp_path: Path) -> None:
    registry, store, archive, descriptor, run, _ = _make_prepared_bundle(tmp_path)
    assert descriptor.upload_name == archive.name == run.project.source
    assert descriptor.run_identity_sha256 == _manual_identity(run)
    ready_path = tmp_path / "dispatch" / f"{descriptor.scan_id}.ready.json"
    os.link(tmp_path / "dispatch" / f"{descriptor.scan_id}.prepared.json", ready_path)
    with pytest.raises(ZipDispatchError) as failure:
        store.read(descriptor.scan_id, state="prepared")
    assert failure.value.code == "dispatch_store_conflict"
    registry.close()


def test_i1_ai_profile_records_locked_qwen3_identity_without_transport(tmp_path: Path) -> None:
    profile = ZipExecutionProfile.from_provider(
        ai_requested=True,
        provider=OllamaProvider(),
        ai_timeout_seconds=7.25,
    )
    assert profile.ai_requested is True
    assert profile.ai_identity is not None
    assert profile.ai_identity["provider"] == "ollama-local"
    assert str(profile.ai_identity["model_id"]).startswith("qwen3:")
    assert profile.ai_timeout_seconds == 7.25


def test_i1_capacity_rejects_eighth_body_before_asgi_receive(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    for index in range(ORACLE_MAX_INPUTS):
        item = upload_root / f"openguard-upload-existing_{index}.zip"
        item.write_bytes(b"existing")
        os.chmod(item, 0o600)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ZipDispatchStore(dispatch_root, upload_root)
    runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        dispatch_store=store,
    )
    app = create_app(registry, zip_runtime=runtime)
    body, boundary = _manual_multipart(_dynamic_zip("never-read"))
    status_code, payload, receive_calls = _asgi_call(
        app,
        body,
        content_type=f"multipart/form-data; boundary={boundary}",
        content_length=str(len(body)),
        forbid_receive=True,
    )
    assert status_code == 500
    assert json.loads(payload)["error"]["details"] == {"reason": "dispatch_capacity_exceeded"}
    assert receive_calls == 0
    registry.close()


def test_i1_concurrent_reservations_account_for_residual_inputs(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    for index in range(ORACLE_MAX_INPUTS - 1):
        item = upload_root / f"openguard-upload-residual_{index}.zip"
        item.write_bytes(b"x")
        os.chmod(item, 0o600)
    store = ZipDispatchStore(dispatch_root, upload_root)
    gate = threading.Barrier(3)
    outcomes: list[tuple[str, object]] = []
    outcome_lock = threading.Lock()

    def reserve() -> None:
        gate.wait()
        try:
            token = store.reserve_upload()
        except ZipDispatchError as error:
            with outcome_lock:
                outcomes.append(("error", error.code))
        else:
            with outcome_lock:
                outcomes.append(("ok", token))

    threads = [threading.Thread(target=reserve) for _ in range(2)]
    for thread in threads:
        thread.start()
    gate.wait()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert sorted(kind for kind, _ in outcomes) == ["error", "ok"]
    assert outcomes[0][1] == "dispatch_capacity_exceeded" or outcomes[1][1] == "dispatch_capacity_exceeded"
    for kind, value in outcomes:
        if kind == "ok":
            value.release()  # type: ignore[union-attr]


def test_i1_fixed_byte_oracle_counts_512_mib_residual_and_64_mib_reservation(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    # Sparse files exercise stat-based accounting without allocating 512 MiB
    # in memory or writing a large test artifact.
    for index in range(ORACLE_MAX_INPUTS - 1):
        item = upload_root / f"openguard-upload-byte_{index}.zip"
        with item.open("wb") as stream:
            stream.truncate(ORACLE_RESERVATION_BYTES)
        os.chmod(item, 0o600)
    store = ZipDispatchStore(dispatch_root, upload_root)
    reservation = store.reserve_upload()
    with pytest.raises(ZipDispatchError) as failure:
        store.reserve_upload()
    assert failure.value.code == "dispatch_capacity_exceeded"
    reservation.release()

    full_case = _private_dir(tmp_path / "full")
    full_upload = _private_dir(full_case / "uploads")
    full_dispatch = _private_dir(full_case / "dispatch")
    full_input = full_upload / "openguard-upload-full.zip"
    with full_input.open("wb") as stream:
        stream.truncate(ORACLE_MAX_BYTES)
    os.chmod(full_input, 0o600)
    full_store = ZipDispatchStore(full_dispatch, full_upload)
    with pytest.raises(ZipDispatchError) as full_failure:
        full_store.reserve_upload()
    assert full_failure.value.code == "dispatch_capacity_exceeded"


def test_i1_private_input_security_rejects_mode_symlink_and_fifo(tmp_path: Path) -> None:
    for kind in ("mode", "symlink", "fifo"):
        case = _private_dir(tmp_path / kind)
        upload_root = _private_dir(case / "uploads")
        dispatch_root = _private_dir(case / "dispatch")
        target = upload_root / "openguard-upload-security.zip"
        target.write_bytes(b"safe")
        if kind == "mode":
            os.chmod(target, 0o644)
        elif kind == "symlink":
            replacement = upload_root / "replacement.bin"
            replacement.write_bytes(b"safe")
            os.chmod(replacement, 0o600)
            target.unlink()
            target.symlink_to(replacement.name)
        else:
            target.unlink()
            os.mkfifo(target, 0o600)
        with pytest.raises(ZipDispatchError) as failure:
            ZipDispatchStore(dispatch_root, upload_root)
        assert failure.value.code in {"dispatch_store_corrupt", "dispatch_store_path_invalid"}


def test_i1_prepare_fsync_event_order_is_input_prepared_registry_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    fsyncs: list[str] = []
    events: list[str] = []
    original_fsync = ZipDispatchStore._fsync_directory

    def logged_fsync(path: Path) -> None:
        fsyncs.append(path.name)
        original_fsync(path)

    monkeypatch.setattr(ZipDispatchStore, "_fsync_directory", staticmethod(logged_fsync))
    store = ZipDispatchStore(dispatch_root, upload_root, event_hook=events.append)
    archive = upload_root / "openguard-upload-order.zip"
    reservation = store.reserve_upload()
    archive.write_bytes(_dynamic_zip("order"))
    os.chmod(archive, 0o600)
    store.bind_upload(reservation, archive)
    candidate = ScanApiService(registry).build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="order",
        input_digest=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    descriptor = store.prepare(
        archive,
        candidate.run,
        ZipExecutionProfile.from_provider(ai_requested=False, provider=None, ai_timeout_seconds=10.0),
        reservation,
    )
    store.checkpoint("after_prepared_before_registry")
    registry.create(candidate.run)
    store.checkpoint("after_registry_before_ready")
    store.promote(descriptor)

    assert events == [
        "input_fsynced",
        "prepared_fsynced",
        "after_prepared_before_registry",
        "after_registry_before_ready",
        "ready_fsynced",
    ]
    assert fsyncs[:2] == ["uploads", "dispatch"]
    assert store.read(candidate.run.id, state="ready") == descriptor
    registry.close()


@pytest.mark.parametrize(
    ("fault", "expected_rows", "expected_prepared", "expected_ready"),
    [
        ("input_file_fsync", 0, 0, 0),
        ("input_archive_fsync", 0, 0, 0),
        ("prepared_file_fsync", 0, 0, 0),
        ("prepared_directory_fsync", 0, 1, 0),
        ("ready_directory_fsync", 1, 0, 1),
        ("rename", 1, 1, 0),
    ],
)
def test_i1_real_http_syscall_faults_never_claim_202_and_retain_state(
    independent_harness,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    expected_rows: int,
    expected_prepared: int,
    expected_ready: int,
) -> None:
    """Inject actual syscall failures, not merely checkpoint/event failures."""

    client, registry, store, upload_root, dispatch_root, _ = independent_harness
    fsync_counts = {"upload_file": 0, "dispatch_file": 0, "directory": 0}
    real_fsync = zip_dispatch_module.os.fsync

    def failing_fsync(file_descriptor: int) -> None:
        info = os.fstat(file_descriptor)
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"
        else:
            identity = (info.st_dev, info.st_ino)
            upload_identity = {
                (entry.st_dev, entry.st_ino)
                for entry in (item.lstat() for item in upload_root.iterdir())
                if stat.S_ISREG(entry.st_mode)
            }
            dispatch_identity = {
                (entry.st_dev, entry.st_ino)
                for entry in (item.lstat() for item in dispatch_root.iterdir())
                if stat.S_ISREG(entry.st_mode)
            }
            if identity in upload_identity:
                kind = "upload_file"
            elif identity in dispatch_identity:
                kind = "dispatch_file"
            else:
                raise AssertionError(f"unidentified regular file fsync inode: {identity}")
        fsync_counts[kind] += 1
        failed = (
            fault == "input_file_fsync" and kind == "upload_file" and fsync_counts[kind] == 1
        ) or (
            fault == "input_archive_fsync" and kind == "upload_file" and fsync_counts[kind] == 2
        ) or (
            fault == "prepared_directory_fsync" and kind == "directory" and fsync_counts[kind] == 3
        ) or (
            fault == "ready_directory_fsync" and kind == "directory" and fsync_counts[kind] == 4
        ) or (
            fault == "prepared_file_fsync" and kind == "dispatch_file" and fsync_counts[kind] == 1
        )
        if failed:
            raise OSError(f"independent {fault} injection")
        real_fsync(file_descriptor)

    monkeypatch.setattr(zip_dispatch_module.os, "fsync", failing_fsync)
    if fault == "rename":
        monkeypatch.setattr(
            zip_dispatch_module.os,
            "rename",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("independent rename injection")),
        )

    response = _post_raw(client, _dynamic_zip(f"syscall-{fault}"), key=f"luna-syscall-{fault}")
    assert response.status_code != 202
    assert len(registry.list_runs().items) == expected_rows
    assert len(list(dispatch_root.glob("*.prepared.json"))) == expected_prepared
    assert len(list(dispatch_root.glob("*.ready.json"))) == expected_ready
    assert len(list(upload_root.iterdir())) == (1 if fault != "input_file_fsync" else 0)
    if fault == "input_file_fsync":
        assert fsync_counts["upload_file"] == 1
    elif fault == "input_archive_fsync":
        assert fsync_counts["upload_file"] == 2
    elif fault == "prepared_file_fsync":
        assert fsync_counts["upload_file"] == 2
        assert fsync_counts["dispatch_file"] == 1
    elif fault == "prepared_directory_fsync":
        assert fsync_counts["directory"] == 3
    elif fault == "ready_directory_fsync":
        assert fsync_counts["directory"] == 4


def _crash_child_code() -> str:
    return r'''
import json
import os
import base64
from pathlib import Path

from app.persistence import SQLiteScanRunRegistry, ZipDispatchStore, ZipExecutionProfile
from app.domain.models import ScanRun

event_fd = int(os.environ["OG_EVENT_FD"])
control_fd = int(os.environ["OG_CONTROL_FD"])
target = os.environ["OG_TARGET_EVENT"]

def hook(name):
    os.write(event_fd, (name + "\n").encode("ascii"))
    if name == target:
        os.read(control_fd, 1)

dispatch = Path(os.environ["OG_DISPATCH_ROOT"])
uploads = Path(os.environ["OG_UPLOAD_ROOT"])
database = Path(os.environ["OG_DATABASE"])
archive = Path(os.environ["OG_ARCHIVE"])
run = ScanRun.model_validate(json.loads(os.environ["OG_RUN_JSON"]))
store = ZipDispatchStore(dispatch, uploads, event_hook=hook)
registry = SQLiteScanRunRegistry(database)
reservation = store.reserve_upload()
archive.write_bytes(base64.b64decode(os.environ["OG_CONTENT_B64"]))
os.chmod(archive, 0o600)
store.bind_upload(reservation, archive)
descriptor = store.prepare(
    archive,
    run,
    ZipExecutionProfile.from_provider(ai_requested=False, provider=None, ai_timeout_seconds=10.0),
    reservation,
)
store.checkpoint("after_prepared_before_registry")
if target != "prepared_fsynced":
    registry.create(run)
    store.checkpoint("after_registry_before_ready")
if target == "ready_fsynced":
    store.promote(descriptor)
'''


def _read_persistent_state_in_new_process(
    database: Path, dispatch_root: Path, upload_root: Path, scan_id: str
) -> dict[str, object]:
    code = r'''
import hashlib
import json
import sys
from pathlib import Path
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError, ZipDispatchStore

database = Path(sys.argv[1])
dispatch = Path(sys.argv[2])
uploads = Path(sys.argv[3])
scan_id = sys.argv[4]
store = ZipDispatchStore(dispatch, uploads)
registry = SQLiteScanRunRegistry(database)
prepared = store.read(scan_id, state="prepared")
ready = store.read(scan_id, state="ready")
descriptor = ready or prepared
row = None
try:
    row = registry.get(scan_id).run
except ScanRegistryError as error:
    if error.code != "registry_not_found":
        raise
    row = None
inputs = sorted(uploads.glob("openguard-upload-*.zip"))
input_digest = None
if len(inputs) == 1:
    digest = hashlib.sha256()
    with inputs[0].open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    input_digest = digest.hexdigest()
print(json.dumps({
    "prepared": prepared is not None,
    "ready": ready is not None,
    "rows": len(registry.list_runs().items),
    "input_sha256": input_digest,
    "descriptor": None if descriptor is None else {
        "scan_id": descriptor.scan_id,
        "upload_name": descriptor.upload_name,
        "input_sha256": descriptor.input_sha256,
        "run_identity_sha256": descriptor.run_identity_sha256,
    },
    "run": None if row is None else {
        "id": row.id,
        "source": row.project.source,
        "input_sha256": row.provenance.input_digest.value,
    },
}, sort_keys=True))
'''
    child_env = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2] / "backend")
    child_env["PYTHONPATH"] = backend + os.pathsep + child_env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code, str(database), str(dispatch_root), str(upload_root), scan_id],
        env=child_env,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _wait_for_process_event(event_fd: int, process: subprocess.Popen[bytes], target: str, *, timeout: float = 10.0) -> None:
    selector = selectors.DefaultSelector()
    selector.register(event_fd, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    stream = b""
    try:
        target_line = (target + "\n").encode()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"timed out waiting for child event {target!r}")
            if not selector.select(remaining):
                raise AssertionError(f"timed out waiting for child event {target!r}")
            byte = os.read(event_fd, 1)
            if not byte:
                stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
                raise AssertionError(f"child exited before {target}: {stderr}")
            stream += byte
            if stream.endswith(target_line):
                return
    finally:
        selector.close()


@pytest.mark.parametrize(
    ("target_event", "expected_prepared", "expected_ready", "expected_rows"),
    [
        ("input_fsynced", False, False, 0),
        ("prepared_fsynced", True, False, 0),
        ("after_registry_before_ready", True, False, 1),
        ("ready_fsynced", False, True, 1),
    ],
)
def test_i1_new_process_observes_each_fsync_crash_window(
    tmp_path: Path,
    target_event: str,
    expected_prepared: bool,
    expected_ready: bool,
    expected_rows: int,
) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    content = _dynamic_zip(target_event)
    archive = upload_root / "openguard-upload-independent.zip"
    candidate = ScanApiService(registry).build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="independent",
        input_digest=hashlib.sha256(content).hexdigest(),
    )
    run = candidate.run
    registry.close()

    event_read, event_write = os.pipe()
    control_read, control_write = os.pipe()
    child_env = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2] / "backend")
    child_env["PYTHONPATH"] = backend + os.pathsep + child_env.get("PYTHONPATH", "")
    child_env.update(
        {
            "OG_EVENT_FD": str(event_write),
            "OG_CONTROL_FD": str(control_read),
            "OG_TARGET_EVENT": target_event,
            "OG_DISPATCH_ROOT": str(tmp_path / "dispatch"),
            "OG_UPLOAD_ROOT": str(tmp_path / "uploads"),
            "OG_DATABASE": str(tmp_path / "scans.sqlite"),
            "OG_ARCHIVE": str(archive),
            "OG_RUN_JSON": json.dumps(run.model_dump(mode="json"), ensure_ascii=False),
            "OG_CONTENT_B64": base64.b64encode(content).decode("ascii"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-c", _crash_child_code()],
        env=child_env,
        pass_fds=(event_write, control_read),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(event_write)
    os.close(control_read)
    try:
        _wait_for_process_event(event_read, process, target_event)
        process.kill()
        process.wait(timeout=10)
    finally:
        os.close(event_read)
        os.close(control_write)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    state = _read_persistent_state_in_new_process(
        tmp_path / "scans.sqlite", tmp_path / "dispatch", tmp_path / "uploads", run.id
    )
    assert state["prepared"] is expected_prepared
    assert state["ready"] is expected_ready
    assert state["rows"] == expected_rows
    assert state["input_sha256"] == hashlib.sha256(content).hexdigest()
    descriptor_state = state["descriptor"]
    if descriptor_state is not None:
        assert descriptor_state == {
            "scan_id": run.id,
            "upload_name": run.project.source,
            "input_sha256": hashlib.sha256(content).hexdigest(),
            "run_identity_sha256": _manual_identity(run),
        }
    row_state = state["run"]
    if expected_rows:
        assert row_state == {
            "id": run.id,
            "source": run.project.source,
            "input_sha256": hashlib.sha256(content).hexdigest(),
        }
    else:
        assert row_state is None


def test_i1_prepared_no_row_cleanup_requires_healthy_absence_and_fsyncs_missing_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry, store, archive, descriptor, _, _ = _make_prepared_bundle(tmp_path)
    sentinel = archive.parent / "openguard-upload-unrelated.zip"
    sentinel.write_bytes(b"keep")
    os.chmod(sentinel, 0o600)
    archive.unlink()
    fsyncs: list[Path] = []
    original = ZipDispatchStore._fsync_directory
    monkeypatch.setattr(store, "_fsync_directory", lambda path: (fsyncs.append(path), original(path))[1])
    store.cleanup_prepared_without_run(descriptor.scan_id, run_exists=lambda scan_id: False)
    assert store.read(descriptor.scan_id, state="prepared") is None
    assert not archive.exists()
    assert sentinel.exists()
    assert fsyncs == [archive.parent, tmp_path / "dispatch"]
    registry.close()


def test_i1_cleanup_refuses_running_or_unhealthy_prepared_pair(tmp_path: Path) -> None:
    registry, store, archive, descriptor, queued, _ = _make_prepared_bundle(tmp_path)
    with pytest.raises(ZipDispatchError) as missing_row:
        store.cleanup_prepared_without_run(descriptor.scan_id, run_exists=lambda _: True)
    assert missing_row.value.code == "dispatch_store_conflict"
    assert archive.exists()
    assert store.read(descriptor.scan_id, state="prepared") == descriptor

    stored = registry.create(queued)
    with pytest.raises(ZipDispatchError) as running:
        store.cleanup_terminal(queued, read_registry=lambda _: queued)
    assert running.value.code == "dispatch_store_invalid_argument"
    assert archive.exists()
    assert store.read(descriptor.scan_id, state="prepared") == descriptor
    assert registry.get(queued.id).revision == stored.revision
    registry.close()


def test_i1_terminal_cleanup_accepts_healthy_cancelled_prepared_snapshot(tmp_path: Path) -> None:
    registry, store, archive, descriptor, queued, _ = _make_prepared_bundle(tmp_path)
    stored = registry.create(queued)
    payload = queued.model_dump(mode="python")
    payload.update({"status": ScanStatus.CANCELLED, "stage": ScanStage.QUEUED, "finished_at": queued.created_at})
    cancelled = ScanRun.model_validate(payload)
    registry.replace(cancelled, expected_revision=stored.revision)
    store.cleanup_terminal(cancelled, read_registry=lambda scan_id: registry.get(scan_id).run)
    assert not archive.exists()
    assert store.read(descriptor.scan_id, state="prepared") is None
    registry.close()


def test_i1_direct_submit_without_prebody_token_is_rejected(independent_harness) -> None:
    _, registry, _, _, _, workspace_root = independent_harness
    runtime = ZipScanRuntime(
        registry,
        upload_root=workspace_root.parent / "uploads",
        workspace_root=workspace_root,
        dispatch_store=ZipDispatchStore(workspace_root.parent / "dispatch", workspace_root.parent / "uploads"),
    )
    upload = UploadFile(
        file=io.BytesIO(_dynamic_zip("no-token")),
        filename="no-token.zip",
        headers=Headers({"content-type": "application/zip"}),
    )

    async def invoke():
        return await runtime.submit(
            upload,
            ZipScanCreateFields(source_type="zip"),
            ScanApiService(registry),
            BackgroundTasks(),
        )

    with pytest.raises(ApiError) as failure:
        asyncio.run(invoke())
    assert failure.value.reason == "dispatch_reservation_required"


def test_i1_commit_uncertainty_keeps_prepared_input_and_registry_row(independent_harness, monkeypatch: pytest.MonkeyPatch) -> None:
    client, registry, store, upload_root, dispatch_root, _ = independent_harness
    original_create = registry.create
    called = False

    def commit_then_raise(run: ScanRun, *, idempotency_fingerprint: str | None = None):
        nonlocal called
        stored = original_create(run, idempotency_fingerprint=idempotency_fingerprint)
        called = True
        raise RuntimeError("commit result intentionally uncertain")

    monkeypatch.setattr(registry, "create", commit_then_raise)
    response = _post_raw(client, _dynamic_zip("commit-uncertain"), key="luna-commit-uncertain")
    assert response.status_code == 500
    assert called is True
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 1
    assert len(list(dispatch_root.glob("*.prepared.json"))) == 1
    assert not list(dispatch_root.glob("*.ready.json"))


def test_i1_same_key_same_bytes_profile_change_keeps_original_identity(independent_harness) -> None:
    client, registry, store, upload_root, dispatch_root, workspace_root = independent_harness
    content = _dynamic_zip("profile-original")
    first = _post_raw(client, content, key="luna-profile-change")
    assert first.status_code == 202
    first_id = first.json()["scan_id"]

    ai_runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        ai_provider=OllamaProvider(),
        ai_enabled=True,
        ai_timeout_seconds=7.25,
        dispatch_store=ZipDispatchStore(dispatch_root, upload_root),
    )
    ai_app = create_app(registry, zip_runtime=ai_runtime)
    with TestClient(ai_app, raise_server_exceptions=False) as ai_client:
        repeated = _post_raw(ai_client, content, key="luna-profile-change")
    assert repeated.status_code == 202
    assert repeated.json()["scan_id"] == first_id
    original = store.read(first_id, state="ready")
    assert original is not None
    assert original.execution_profile.ai_requested is False
    assert original.execution_profile.ai_timeout_seconds == 10.0
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 1
    assert not list(dispatch_root.glob("*.prepared.json"))


def test_i1_same_key_same_bytes_true_to_false_keeps_original_profile_and_id(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    content = _dynamic_zip("true-original")

    def make_runtime(*, enabled: bool, timeout: float) -> ZipScanRuntime:
        return ZipScanRuntime(
            registry,
            upload_root=upload_root,
            workspace_root=workspace_root,
            ai_provider=OllamaProvider() if enabled else None,
            ai_enabled=enabled,
            ai_timeout_seconds=timeout,
            dispatch_store=ZipDispatchStore(dispatch_root, upload_root),
        )

    with TestClient(create_app(registry, zip_runtime=make_runtime(enabled=True, timeout=7.5)), raise_server_exceptions=False) as first_client:
        first = _post_raw(first_client, content, key="luna-true-to-false")
    with TestClient(create_app(registry, zip_runtime=make_runtime(enabled=False, timeout=21.0)), raise_server_exceptions=False) as second_client:
        repeated = _post_raw(second_client, content, key="luna-true-to-false")

    assert first.status_code == repeated.status_code == 202
    assert repeated.json()["scan_id"] == first.json()["scan_id"]
    descriptor = ZipDispatchStore(dispatch_root, upload_root).read(first.json()["scan_id"], state="ready")
    assert descriptor is not None
    assert descriptor.execution_profile.ai_requested is True
    assert descriptor.execution_profile.ai_timeout_seconds == 7.5
    assert len(registry.list_runs().items) == 1
    registry.close()


def test_i1_same_key_different_bytes_returns_409_and_only_known_loser_is_removed(independent_harness) -> None:
    client, registry, store, upload_root, dispatch_root, _ = independent_harness
    first = _post_raw(client, _dynamic_zip("original"), key="luna-different-bytes")
    conflict = _post_raw(client, _dynamic_zip("different"), key="luna-different-bytes")
    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"reason": "idempotency_conflict"}
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 1
    assert len(list(dispatch_root.glob("*.ready.json"))) == 1
    assert not list(dispatch_root.glob("*.prepared.json"))
    assert store.read(first.json()["scan_id"], state="ready") is not None


def test_i1_loser_cleanup_failure_preserves_public_idempotency_result(independent_harness, monkeypatch: pytest.MonkeyPatch) -> None:
    client, registry, store, upload_root, dispatch_root, _ = independent_harness
    first = _post_raw(client, _dynamic_zip("loser-original"), key="luna-loser-cleanup")
    monkeypatch.setattr(
        store,
        "discard_prepared",
        lambda *args: (_ for _ in ()).throw(ZipDispatchError("dispatch_store_io_failed")),
    )
    conflict = _post_raw(client, _dynamic_zip("loser-conflict"), key="luna-loser-cleanup")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"reason": "idempotency_conflict"}
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 2
    assert len(list(dispatch_root.glob("*.ready.json"))) == 1
    assert len(list(dispatch_root.glob("*.prepared.json"))) == 1
    assert store.read(first.json()["scan_id"], state="ready") is not None


def test_i1_real_cross_thread_staging_race_preserves_expected_202_contract(independent_harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """P1: A creates the staged file, B reserves before A binds it.

    The bounded event wait is only a scheduling observation: the request-A
    TestClient thread is paused after mkstemp, while request-B is an actual
    independent thread.  Once the implementation serializes create+bind, B
    remains blocked until A resumes; this test then releases A and cannot
    deadlock under the corrected lock scope.
    """

    _, registry, store, upload_root, _, workspace_root = independent_harness
    app = create_app(
        registry,
        zip_runtime=ZipScanRuntime(
            registry,
            upload_root=upload_root,
            workspace_root=workspace_root,
            dispatch_store=store,
        ),
    )
    created = threading.Event()
    resume = threading.Event()
    b_started = threading.Event()
    b_done = threading.Event()
    b_outcome: list[object] = []
    a_outcome: list[object] = []
    original_mkstemp = zip_scan_module.tempfile.mkstemp

    def paused_mkstemp(*args, **kwargs):
        result = original_mkstemp(*args, **kwargs)
        created.set()
        assert resume.wait(timeout=10)
        return result

    monkeypatch.setattr(zip_scan_module.tempfile, "mkstemp", paused_mkstemp)

    def request_a() -> None:
        with TestClient(app, raise_server_exceptions=False) as client:
            a_outcome.append(_post_raw(client, _dynamic_zip("race-a"), key="luna-race-a"))

    def request_b() -> None:
        b_started.set()
        try:
            b_outcome.append(store.reserve_upload())
        except ZipDispatchError as error:
            b_outcome.append(error)
        finally:
            b_done.set()

    thread_a = threading.Thread(target=request_a)
    thread_a.start()
    assert created.wait(timeout=10)
    thread_b = threading.Thread(target=request_b)
    thread_b.start()
    assert b_started.wait(timeout=10)
    # In the unfixed implementation B can complete before A binds.  In the
    # corrected implementation B waits on the create+bind critical section;
    # this bounded event wait never serves as an arbitrary timing assumption.
    b_acquired_before_a_resume = b_done.wait(timeout=1.0)
    resume.set()
    thread_a.join(timeout=10)
    thread_b.join(timeout=10)
    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    for result in b_outcome:
        if hasattr(result, "release"):
            result.release()

    assert b_acquired_before_a_resume in {True, False}
    assert a_outcome and a_outcome[0].status_code == 202, (
        a_outcome[0].status_code,
        a_outcome[0].json() if a_outcome else None,
    )
    assert len(registry.list_runs().items) == 1


# ---------------------------------------------------------------------------
# I2 independent process harness.  This section deliberately does not import
# dispatcher internals, worker stage tables, or implementation-side fixtures.
# Every child opens its own SQLite connection and its own store instance.


def _with_independent_ai_aggregate(run: ScanRun) -> ScanRun:
    producer = ProducerRef(
        type=ProducerType.PARSER,
        name="independent-fixture",
        version="1",
    )
    evidence = Evidence(
        id="evd_123e4567-e89b-12d3-a456-426614174000",
        kind=EvidenceKind.FILE,
        locator="requirements.txt",
        detected_by=DetectionMethod.MANIFEST_PARSER,
        producer=producer,
        observed_at=run.created_at,
        verification_status=VerificationStatus.VERIFIED,
    )
    license_expression = LicenseExpression(
        id="lic_123e4567-e89b-12d3-a456-426614174000",
        expression="MIT",
        evidence_ids=[evidence.id],
        confidence=1.0,
        verification_status=VerificationStatus.VERIFIED,
    )
    component = Component(
        id="cmp_123e4567-e89b-12d3-a456-426614174000",
        name="independent-fixture",
        version="1.0.0",
        ecosystem="pypi",
        component_type=ComponentType.LIBRARY,
        license_expression_id=license_expression.id,
        evidence_ids=[evidence.id],
        detected_by=[DetectionMethod.MANIFEST_PARSER],
        confidence=1.0,
    )
    finding = RiskFinding(
        id="rsk_123e4567-e89b-12d3-a456-426614174000",
        resource_kind="component",
        resource_id=component.id,
        outcome=FindingOutcome.WARNING,
        severity=Severity.MEDIUM,
        title="Independent fixture finding",
        description="Independent fixture finding for the provider boundary.",
        rule_id="independent-rule",
        rule_version="1",
        trigger="independent-fixture",
        evidence_ids=[evidence.id],
        confidence=1.0,
    )
    payload = run.model_dump(mode="python")
    payload["evidence"] = [evidence]
    payload["licenses"] = [license_expression]
    payload["components"] = [component]
    payload["findings"] = [finding]
    payload["summary"] = run.summary.model_copy(
        update={
            "component_count": 1,
            "evidence_count": 1,
            "finding_counts": {
                FindingOutcome.PASS: 0,
                FindingOutcome.WARNING: 1,
                FindingOutcome.REVIEW_REQUIRED: 0,
                FindingOutcome.UNKNOWN: 0,
            },
        }
    )
    return ScanRun.model_validate(payload)


def _seed_dispatch_fixture(
    tmp_path: Path,
    *,
    state: str,
    content: bytes | None = None,
    profile: ZipExecutionProfile | None = None,
    aggregate: bool = False,
    report_links: bool = False,
):
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    report_root = _private_dir(tmp_path / "reports")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ZipDispatchStore(dispatch_root, upload_root)
    archive = upload_root / "openguard-upload-independent.zip"
    archive_content = content if content is not None else _dynamic_zip(f"i2-{state}")
    reservation = store.reserve_upload()
    archive.write_bytes(archive_content)
    os.chmod(archive, 0o600)
    store.bind_upload(reservation, archive)
    candidate = ScanApiService(registry).build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="independent-i2",
        input_digest=hashlib.sha256(archive_content).hexdigest(),
    )
    selected_profile = profile or ZipExecutionProfile.from_provider(
        ai_requested=False,
        provider=None,
        ai_timeout_seconds=10.0,
    )
    descriptor = store.prepare(archive, candidate.run, selected_profile, reservation)
    reservation.release()
    run = _with_independent_ai_aggregate(candidate.run) if aggregate else candidate.run

    if state != "prepared":
        stored = registry.create(run)
        if state in {"ready", "running", "terminal"}:
            store.promote(descriptor)
        if state == "running":
            payload = run.model_dump(mode="python")
            payload.update(
                {
                    "status": ScanStatus.RUNNING,
                    "stage": ScanStage.INVENTORY,
                    "progress": 15,
                    "started_at": run.created_at,
                    "finished_at": None,
                }
            )
            if report_links:
                payload["report_links"] = [
                    ReportLink(
                        format=ReportFormat.JSON,
                        href=f"reports/{run.id}/json",
                        content_hash=HashValue(
                            algorithm="sha256", value="0" * 64
                        ),
                        generated_at=run.created_at,
                    )
                ]
            running = ScanRun.model_validate(payload)
            registry.replace(running, expected_revision=stored.revision)
        elif state == "terminal":
            running_payload = run.model_dump(mode="python")
            running_payload.update(
                {
                    "status": ScanStatus.RUNNING,
                    "stage": ScanStage.RULES,
                    "progress": 70,
                    "started_at": run.created_at,
                    "finished_at": None,
                }
            )
            running = ScanRun.model_validate(running_payload)
            running_stored = registry.replace(running, expected_revision=stored.revision)
            payload = running.model_dump(mode="python")
            payload.update(
                {
                    "status": ScanStatus.PARTIAL,
                    "finished_at": run.created_at,
                    "errors": [
                        ScanError(
                            code="independent_terminal",
                            stage=ScanStage.RULES,
                            message="Independent terminal fixture.",
                            recoverable=True,
                        )
                    ],
                }
            )
            terminal = ScanRun.model_validate(payload)
            registry.replace(terminal, expected_revision=running_stored.revision)
    return registry, store, archive, descriptor, run, workspace_root, report_root


def _seed_legacy_git_fixture(tmp_path: Path, *, state: str):
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    report_root = _private_dir(tmp_path / "reports")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    accepted = ScanApiService(registry).create_git_scan(
        GitScanCreateRequest(
            source_type="git",
            source="https://github.com/example/openguard-legacy.git",
        )
    )
    run = registry.get(accepted.scan_id).run
    if state == "running":
        stored = registry.get(run.id)
        running = run.model_copy(
            update={
                "status": ScanStatus.RUNNING,
                "stage": ScanStage.INVENTORY,
                "progress": 15,
                "started_at": run.created_at,
                "finished_at": None,
            }
        )
        run = registry.replace(running, expected_revision=stored.revision).run
    return (
        registry,
        ZipDispatchStore(dispatch_root, upload_root),
        run,
        workspace_root,
        report_root,
    )


def _child_environment(
    tmp_path: Path,
    *,
    event_write: int,
    control_read: int,
    scan_id: str,
    upload_name: str,
    ai_enabled: bool = False,
    ai_timeout_seconds: float = 10.0,
    mode: str = "terminal",
    with_reports: bool = False,
    provider_count: Path | None = None,
    kill_phase: str | None = None,
    kill_stage: str | None = None,
    handler_count: Path | None = None,
    publisher_kill_phase: str | None = None,
    busy_timeout_ms: int = 5000,
    cas_log: Path | None = None,
    provider_incompatible: bool = False,
    claim_io: bool = False,
    cas_busy_barrier: bool = False,
) -> dict[str, str]:
    backend = str(Path(__file__).resolve().parents[2] / "backend")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = backend + os.pathsep + environment.get("PYTHONPATH", "")
    environment.update(
        {
            "OG_EVENT_FD": str(event_write),
            "OG_CONTROL_FD": str(control_read),
            "OG_DATA_DIR": str(tmp_path),
            "OG_SCAN_ID": scan_id,
            "OG_UPLOAD_NAME": upload_name,
            "OG_AI_ENABLED": "1" if ai_enabled else "0",
            "OG_AI_TIMEOUT": str(ai_timeout_seconds),
            "OG_CHILD_MODE": mode,
            "OG_WITH_REPORTS": "1" if with_reports else "0",
            "OG_BUSY_TIMEOUT_MS": str(busy_timeout_ms),
        }
    )
    if provider_count is not None:
        environment["OG_PROVIDER_COUNT"] = str(provider_count)
    if kill_phase is not None:
        environment["OG_KILL_PHASE"] = kill_phase
    if kill_stage is not None:
        environment["OG_KILL_STAGE"] = kill_stage
    if handler_count is not None:
        environment["OG_HANDLER_COUNT"] = str(handler_count)
    if publisher_kill_phase is not None:
        environment["OG_PUBLISHER_KILL_PHASE"] = publisher_kill_phase
    if cas_log is not None:
        environment["OG_CAS_LOG"] = str(cas_log)
    if provider_incompatible:
        environment["OG_PROVIDER_INCOMPATIBLE"] = "1"
    if claim_io:
        environment["OG_CLAIM_IO"] = "1"
    if cas_busy_barrier:
        environment["OG_CAS_BUSY_BARRIER"] = "1"
    return environment


def _dispatcher_child_code() -> str:
    return r'''
import json
import os
import select
import time
from pathlib import Path

from app.ai import OllamaProvider, apply_ai_remediations
from app.domain.models import ScanStage, ScanStatus
from app.persistence import ScanRegistryError, SQLiteScanRunRegistry, ZipDispatchStore
import app.persistence.zip_dispatch as zip_store_module
from app.pipeline import zip_dispatcher as dispatcher_module
from app.pipeline.worker import PipelinePlan, PipelineStep
from app.pipeline.zip_dispatcher import ZipDispatcher
from app.reporting import PipelineReportPublisher, ReportArtifactStore

event_fd = int(os.environ["OG_EVENT_FD"])
control_fd = int(os.environ["OG_CONTROL_FD"])
data_dir = Path(os.environ["OG_DATA_DIR"])
scan_id = os.environ["OG_SCAN_ID"]
upload_name = os.environ["OG_UPLOAD_NAME"]
mode = os.environ["OG_CHILD_MODE"]
ai_enabled = os.environ["OG_AI_ENABLED"] == "1"
ai_timeout = float(os.environ["OG_AI_TIMEOUT"])
kill_phase = os.environ.get("OG_KILL_PHASE")
kill_stage_name = os.environ.get("OG_KILL_STAGE")
kill_stage = ScanStage[kill_stage_name] if kill_stage_name else None
stage_progress = {
    ScanStage.INGESTION: 5,
    ScanStage.INVENTORY: 15,
    ScanStage.SCAN: 35,
    ScanStage.NORMALIZE: 55,
    ScanStage.RULES: 70,
    ScanStage.AI_ASSIST: 85,
    ScanStage.REPORT: 95,
}

def emit(value):
    os.write(event_fd, (value + "\n").encode("ascii"))

def wait_for_parent(timeout=20.0):
    global shutdown_requested
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([control_fd], [], [], max(0.01, deadline - time.monotonic()))
        if ready:
            command = os.read(control_fd, 1)
            if command == b"s":
                shutdown_requested = True
                emit("shutdown_requested")
                continue
            return

shutdown_requested = False

provider = None
if os.environ.get("OG_PROVIDER_COUNT"):
    count_path = Path(os.environ["OG_PROVIDER_COUNT"])

    class CountingProvider:
        mode = "local"
        producer = OllamaProvider().producer

        def generate(self, payload, timeout_seconds):
            with count_path.open("a", encoding="ascii") as stream:
                stream.write("call\n")
                stream.flush()
                os.fsync(stream.fileno())
            emit("provider_called")
            wait_for_parent()
            return "unused"

    provider = CountingProvider()
elif ai_enabled:
    provider = OllamaProvider()
    if os.environ.get("OG_PROVIDER_INCOMPATIBLE") == "1":
        class IncompatibleProvider:
            mode = "local"
            producer = provider.producer.model_copy(update={"model_id": "qwen3:incompatible"})

            def generate(self, payload, timeout_seconds):
                raise RuntimeError("incompatible provider must not be called")
        provider = IncompatibleProvider()

if os.environ.get("OG_PROVIDER_COUNT") or kill_phase:
    def independent_plan(*args, **kwargs):
        def step(run):
            if kill_phase and run.stage is kill_stage:
                handler_path = os.environ.get("OG_HANDLER_COUNT")
                if handler_path:
                    with Path(handler_path).open("a", encoding="ascii") as stream:
                        stream.write("handler\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                emit("handler_enter")
                if kill_phase == "handler_before_return":
                    wait_for_parent()
            if os.environ.get("OG_PROVIDER_COUNT") and run.stage is ScanStage.AI_ASSIST:
                return apply_ai_remediations(
                    run,
                    provider,
                    enabled=True,
                    timeout_seconds=ai_timeout,
                ).run
            return run
        stages = (
            ScanStage.INGESTION,
            ScanStage.INVENTORY,
            ScanStage.SCAN,
            ScanStage.NORMALIZE,
            ScanStage.RULES,
            ScanStage.AI_ASSIST,
            ScanStage.REPORT,
        )
        return PipelinePlan(
            steps=tuple(PipelineStep(stage, step) for stage in stages)
        )
    dispatcher_module.build_local_zip_dependency_plan = independent_plan

registry = SQLiteScanRunRegistry(
    data_dir / "scans.sqlite",
    busy_timeout_ms=int(os.environ.get("OG_BUSY_TIMEOUT_MS", "5000")),
)
store = ZipDispatchStore(
    data_dir / "dispatch", data_dir / "uploads", recovery_mode=True
)
if mode == "cleanup_kill":
    original_unlink = zip_store_module.os.unlink
    cleanup_barrier_seen = False
    def unlink_after_zip(path, *args, **kwargs):
        global cleanup_barrier_seen
        result = original_unlink(path, *args, **kwargs)
        if (
            not cleanup_barrier_seen
            and path == upload_name
            and kwargs.get("dir_fd") is not None
        ):
            cleanup_barrier_seen = True
            emit("zip_deleted_before_descriptor")
            wait_for_parent()
        return result
    zip_store_module.os.unlink = unlink_after_zip
replace_state = {"target_stage_cas_seen": False}
base_replace = registry.replace
cas_log_path = os.environ.get("OG_CAS_LOG")
cas_error_count = 0
if cas_log_path:
    original_replace = base_replace
    def replace_with_log(run, expected_revision):
        global cas_error_count
        try:
            result = original_replace(run, expected_revision=expected_revision)
        except Exception as error:
            record = {
                "when": time.monotonic(),
                "outcome": "error",
                "code": str(getattr(error, "code", type(error).__name__)),
                "status": run.status.value,
                "stage": run.stage.value,
            }
            with Path(cas_log_path).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            emit("cas_error:" + record["code"])
            if (
                os.environ.get("OG_CAS_BUSY_BARRIER")
                and record["code"] == "registry_busy"
            ):
                cas_error_count += 1
                if cas_error_count == 3:
                    emit("cas_busy_phase_complete")
                    wait_for_parent()
            raise
        record = {
            "when": time.monotonic(),
            "outcome": "ok",
            "status": run.status.value,
            "stage": run.stage.value,
        }
        with Path(cas_log_path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        emit("cas_ok:" + record["stage"])
        return result
    registry.replace = replace_with_log
    base_replace = registry.replace
if os.environ.get("OG_CLAIM_IO"):
    claim_io_seen = False
    original_claim_replace = registry.replace
    def replace_with_claim_io(run, expected_revision):
        global claim_io_seen
        if (
            not claim_io_seen
            and run.status is ScanStatus.RUNNING
            and run.stage is ScanStage.INGESTION
            and run.progress == 5
        ):
            claim_io_seen = True
            emit("claim_io_injected")
            raise ScanRegistryError("registry_io_failed")
        return original_claim_replace(run, expected_revision=expected_revision)
    registry.replace = replace_with_claim_io
    base_replace = registry.replace
if kill_phase:
    def replace_with_worker_barrier(run, expected_revision):
        target = kill_stage
        if (
            kill_phase == "claim_after_cas"
            and run.status is ScanStatus.RUNNING
            and run.stage is ScanStage.INGESTION
            and run.progress == 5
        ):
            result = base_replace(run, expected_revision=expected_revision)
            emit("claim_committed")
            wait_for_parent()
            return result
        if (
            kill_phase == "stage_cas_after"
            and run.status is ScanStatus.RUNNING
            and run.stage is target
            and run.progress == stage_progress[target]
            and not replace_state["target_stage_cas_seen"]
        ):
            result = base_replace(run, expected_revision=expected_revision)
            replace_state["target_stage_cas_seen"] = True
            emit("stage_cas_committed")
            wait_for_parent()
            return result
        if (
            kill_phase == "handler_return_before_cas"
            and run.status is ScanStatus.RUNNING
            and run.stage is target
            and run.progress == stage_progress[target]
            and replace_state["target_stage_cas_seen"]
        ):
            emit("handler_returned_before_cas")
            wait_for_parent()
            return base_replace(run, expected_revision=expected_revision)
        result = base_replace(run, expected_revision=expected_revision)
        if (
            kill_phase == "handler_return_before_cas"
            and run.status is ScanStatus.RUNNING
            and run.stage is target
            and run.progress == stage_progress[target]
        ):
            replace_state["target_stage_cas_seen"] = True
        return result
    registry.replace = replace_with_worker_barrier
publisher = None
if os.environ.get("OG_WITH_REPORTS") == "1":
    publisher = PipelineReportPublisher(ReportArtifactStore(data_dir / "reports"))
if os.environ.get("OG_PUBLISHER_ORPHAN") == "1":
    original_publish = publisher.publish
    def publish_then_fail(run):
        result = original_publish(run)
        emit("reports_published")
        raise RuntimeError("independent publisher failure")
    publisher.publish = publish_then_fail
if os.environ.get("OG_PUBLISHER_KILL_PHASE") == "before_terminal_cas":
    original_publish = publisher.publish
    def publish_then_barrier(run):
        result = original_publish(run)
        emit("reports_published_before_cas")
        wait_for_parent()
        return result
    publisher.publish = publish_then_barrier
if os.environ.get("OG_PUBLISHER_KILL_PHASE") == "after_terminal_cas":
    base_terminal_replace = registry.replace
    def replace_after_terminal_cas(run, expected_revision):
        result = base_terminal_replace(run, expected_revision=expected_revision)
        if run.status in {ScanStatus.COMPLETED, ScanStatus.PARTIAL} and run.report_links:
            emit("terminal_cas_committed")
            wait_for_parent()
        return result
    registry.replace = replace_after_terminal_cas

dispatcher = ZipDispatcher(
    registry,
    store,
    data_dir=data_dir,
    workspace_root=data_dir / "workspaces",
    report_publisher=publisher,
    ai_provider=provider,
    ai_enabled=ai_enabled,
    ai_timeout_seconds=ai_timeout,
)
emit("registry_ready")
started = False
try:
    if mode == "start_on_parent":
        wait_for_parent()
    dispatcher.start()
    started = True
    emit("started")
    if mode == "hold":
        wait_for_parent()
    elif mode == "shutdown_after_start":
        deadline = time.monotonic() + 20.0
        while not shutdown_requested and time.monotonic() < deadline:
            select.select([], [], [], 0.01)
        if shutdown_requested:
            # The handler barrier owns the control byte; stop_and_join waits
            # until that active callback is released by the test process.
            dispatcher.stop_and_join()
        else:
            wait_for_parent()
    elif mode == "diagnostic":
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            diagnostic = dispatcher.diagnostic_for(scan_id)
            if diagnostic is not None:
                emit("diagnostic:" + diagnostic)
                break
            select.select([], [], [], 0.01)
        wait_for_parent()
    elif mode == "cleanup_kill":
        # The cleanup thread owns the barrier after deleting the verified ZIP;
        # keep this process alive until the parent performs the simulated kill.
        wait_for_parent()
    else:
        deadline = time.monotonic() + 20.0
        finished = False
        while time.monotonic() < deadline:
            try:
                if scan_id == "*":
                    items = registry.list_runs().items
                    current = items[0].run if items else None
                else:
                    current = registry.get(scan_id).run
            except Exception:
                current = None
            if current is not None and current.status in {
                ScanStatus.COMPLETED,
                ScanStatus.PARTIAL,
                ScanStatus.FAILED,
                ScanStatus.CANCELLED,
            }:
                emit("terminal:" + current.status.value)
                finished = True
                break
            if mode == "cleanup":
                try:
                    no_descriptor = (
                        store.read(scan_id, state="prepared") is None
                        and store.read(scan_id, state="ready") is None
                    )
                except Exception:
                    no_descriptor = False
                if no_descriptor and not (data_dir / "uploads" / upload_name).exists():
                    emit("cleaned")
                    finished = True
                    break
            remaining = max(0.01, min(0.1, deadline - time.monotonic()))
            select.select([], [], [], remaining)
        if not finished:
            emit("timeout")
        wait_for_parent()
except Exception as error:
    emit("error:" + str(getattr(error, "code", type(error).__name__)))
finally:
    if started:
        dispatcher.stop_and_join()
        registry.close()
        dispatcher.release_lifecycle_lock()
        emit("stopped")
    else:
        registry.close()
'''


def _spawn_dispatcher_child(
    tmp_path: Path,
    *,
    scan_id: str,
    upload_name: str,
    mode: str = "terminal",
    ai_enabled: bool = False,
    ai_timeout_seconds: float = 10.0,
    with_reports: bool = False,
    provider_count: Path | None = None,
    publisher_orphan: bool = False,
    kill_phase: str | None = None,
    kill_stage: str | None = None,
    handler_count: Path | None = None,
    publisher_kill_phase: str | None = None,
    provider_incompatible: bool = False,
    busy_timeout_ms: int = 5000,
    cas_log: Path | None = None,
    claim_io: bool = False,
    cas_busy_barrier: bool = False,
):
    event_read, event_write = os.pipe()
    control_read, control_write = os.pipe()
    environment = _child_environment(
        tmp_path,
        event_write=event_write,
        control_read=control_read,
        scan_id=scan_id,
        upload_name=upload_name,
        ai_enabled=ai_enabled,
        ai_timeout_seconds=ai_timeout_seconds,
        mode=mode,
        with_reports=with_reports,
        provider_count=provider_count,
        kill_phase=kill_phase,
        kill_stage=kill_stage,
        handler_count=handler_count,
        publisher_kill_phase=publisher_kill_phase,
        provider_incompatible=provider_incompatible,
        busy_timeout_ms=busy_timeout_ms,
        cas_log=cas_log,
        claim_io=claim_io,
        cas_busy_barrier=cas_busy_barrier,
    )
    if publisher_orphan:
        environment["OG_PUBLISHER_ORPHAN"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-c", _dispatcher_child_code()],
        env=environment,
        pass_fds=(event_write, control_read),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(event_write)
    os.close(control_read)
    return process, event_read, control_write


def _release_dispatcher_child(process, event_read: int, control_write: int) -> None:
    try:
        os.write(control_write, b"x")
    except OSError:
        pass
    finally:
        os.close(control_write)
    try:
        _wait_for_process_event(event_read, process, "stopped", timeout=20.0)
    finally:
        os.close(event_read)
    process.wait(timeout=20)


def _kill_process(process: subprocess.Popen[bytes], *file_descriptors: int) -> None:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=20)
    for descriptor in file_descriptors:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _assert_no_process_event(
    event_read: int,
    process: subprocess.Popen[bytes],
    target: str,
    *,
    timeout: float = 1.25,
) -> None:
    selector = selectors.DefaultSelector()
    selector.register(event_read, selectors.EVENT_READ)
    target_line = (target + "\n").encode("ascii")
    buffer = b""
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if not selector.select(remaining):
                return
            byte = os.read(event_read, 1)
            if not byte:
                return
            buffer += byte
            if target_line in buffer:
                raise AssertionError(f"unexpected child event {target!r}")
    finally:
        selector.close()


def _read_run_once(database: Path, scan_id: str) -> ScanRun:
    reader_code = r'''
import sys
from pathlib import Path
from app.persistence import SQLiteScanRunRegistry

registry = SQLiteScanRunRegistry(Path(sys.argv[1]))
try:
    print(registry.get(sys.argv[2]).run.model_dump_json(), flush=True)
finally:
    registry.close()
'''
    environment = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2] / "backend")
    environment["PYTHONPATH"] = backend + os.pathsep + environment.get("PYTHONPATH", "")
    process = subprocess.Popen(
        [sys.executable, "-c", reader_code, str(database), scan_id],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=20)
        raise AssertionError(f"independent reader timed out: {database} {scan_id}")
    assert process.returncode == 0, stderr.decode(errors="replace")
    return ScanRun.model_validate_json(stdout.decode("utf-8"))


def _assert_four_format_downloads(
    database: Path,
    report_root: Path,
    scan_id: str,
    *,
    available: bool,
) -> None:
    registry = SQLiteScanRunRegistry(database)
    app = create_app(registry, report_store=ReportArtifactStore(report_root))
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            for report_format in ReportFormat:
                response = client.get(
                    f"/api/v1/scans/{scan_id}/report",
                    params={"format": report_format.value, "download": "true"},
                )
                if not available:
                    assert response.status_code == 409
                    assert response.json()["error"]["code"] == "report_not_ready"
                    continue
                assert response.status_code == 200
                assert response.content
                link = next(item for item in registry.get(scan_id).run.report_links if item.format is report_format)
                assert hashlib.sha256(response.content).hexdigest() == link.content_hash.value
                encoded = base64.b64encode(bytes.fromhex(link.content_hash.value)).decode("ascii")
                assert response.headers["content-digest"] == f"sha-256=:{encoded}:"
                assert response.headers["etag"] == f'"sha256:{link.content_hash.value}"'
    finally:
        registry.close()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_uvicorn(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
            raise AssertionError(f"uvicorn exited before listening: {stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            select_timeout = min(0.1, max(0.0, deadline - time.monotonic()))
            if select_timeout:
                pause = selectors.SelectSelector()
                try:
                    pause.select(select_timeout)
                finally:
                    pause.close()
    raise AssertionError("uvicorn did not listen on loopback within the timeout")


def _finish_child_after_event(
    process: subprocess.Popen[bytes],
    event_read: int,
    control_write: int,
    target: str,
) -> None:
    try:
        _wait_for_process_event(event_read, process, target, timeout=20.0)
        _release_dispatcher_child(process, event_read, control_write)
    except Exception:
        _kill_process(process, event_read, control_write)
        raise


def _worker_race_child_code() -> str:
    return r'''
import json
import os
from pathlib import Path

from app.persistence import SQLiteScanRunRegistry
from app.pipeline import ScanPipelineWorker, build_local_zip_dependency_plan
from app.pipeline.worker import PipelineError

event_fd = int(os.environ["OG_EVENT_FD"])
database = Path(os.environ["OG_DATABASE"])
archive = Path(os.environ["OG_ARCHIVE"])
workspace = Path(os.environ["OG_WORKSPACE"])
scan_id = os.environ["OG_SCAN_ID"]
control_fd_text = os.environ.get("OG_CONTROL_FD")
control_fd = int(control_fd_text) if control_fd_text is not None else None

def emit(value):
    os.write(event_fd, (value + "\n").encode("ascii"))

registry = SQLiteScanRunRegistry(database)
try:
    if control_fd is not None:
        emit("barrier_ready")
        os.read(control_fd, 1)
    plan = build_local_zip_dependency_plan(
        archive,
        workspace,
        clock=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    try:
        result = ScanPipelineWorker(registry).run(scan_id, plan)
        outcome = "done:" + result.run.status.value
    except PipelineError as error:
        outcome = "error:" + error.code
    print(outcome, flush=True)
    emit("finished")
finally:
    registry.close()
'''


def _spawn_worker_child(
    tmp_path: Path,
    scan_id: str,
    *,
    control_read: int | None = None,
):
    event_read, event_write = os.pipe()
    environment = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2] / "backend")
    environment["PYTHONPATH"] = backend + os.pathsep + environment.get("PYTHONPATH", "")
    environment.update(
        {
            "OG_EVENT_FD": str(event_write),
            "OG_DATABASE": str(tmp_path / "scans.sqlite"),
            "OG_ARCHIVE": str(tmp_path / "uploads" / "openguard-upload-independent.zip"),
            "OG_WORKSPACE": str(tmp_path / "workspaces"),
            "OG_SCAN_ID": scan_id,
        }
    )
    pass_fds = [event_write]
    if control_read is not None:
        environment["OG_CONTROL_FD"] = str(control_read)
        pass_fds.append(control_read)
    process = subprocess.Popen(
        [sys.executable, "-c", _worker_race_child_code()],
        env=environment,
        pass_fds=tuple(pass_fds),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(event_write)
    return process, event_read


def _cancel_race_child_code() -> str:
    return r'''
import os
import sys
from pathlib import Path

from app.domain.models import ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError

event_fd = int(os.environ["OG_EVENT_FD"])
control_fd = int(os.environ["OG_CONTROL_FD"])
database = Path(os.environ["OG_DATABASE"])
scan_id = os.environ["OG_SCAN_ID"]

def emit(value):
    os.write(event_fd, (value + "\n").encode("ascii"))

registry = SQLiteScanRunRegistry(database)
try:
    queued = registry.get(scan_id)
    cancelled = queued.run.model_copy(update={
        "status": ScanStatus.CANCELLED,
        "stage": ScanStage.QUEUED,
        "progress": 0,
        "started_at": None,
        "finished_at": queued.run.created_at,
    })
    emit("barrier_ready")
    os.read(control_fd, 1)
    try:
        registry.replace(cancelled, expected_revision=queued.revision)
        print("cancelled", flush=True)
        emit("cancelled")
    except ScanRegistryError as error:
        print("error:" + error.code, flush=True)
        emit("error:" + error.code)
finally:
    registry.close()
'''


def _spawn_cancel_race_child(tmp_path: Path, scan_id: str, control_read: int):
    event_read, event_write = os.pipe()
    environment = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2] / "backend")
    environment["PYTHONPATH"] = backend + os.pathsep + environment.get("PYTHONPATH", "")
    environment.update(
        {
            "OG_EVENT_FD": str(event_write),
            "OG_CONTROL_FD": str(control_read),
            "OG_DATABASE": str(tmp_path / "scans.sqlite"),
            "OG_SCAN_ID": scan_id,
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-c", _cancel_race_child_code()],
        env=environment,
        pass_fds=(event_write, control_read),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(event_write)
    return process, event_read


def _sqlite_holder_child_code() -> str:
    return r'''
import os
import select
import sqlite3
import sys

database = sys.argv[1]
event_fd = int(os.environ["OG_EVENT_FD"])
control_fd = int(os.environ["OG_CONTROL_FD"])

def emit(value):
    os.write(event_fd, (value + "\n").encode("ascii"))

connection = sqlite3.connect(database, timeout=0, isolation_level=None)
try:
    connection.execute("BEGIN IMMEDIATE")
    emit("locked")
    select.select([control_fd], [], [], 20.0)
    connection.execute("COMMIT")
    emit("released")
finally:
    connection.close()
'''


def _spawn_sqlite_holder(tmp_path: Path):
    event_read, event_write = os.pipe()
    control_read, control_write = os.pipe()
    environment = os.environ.copy()
    environment.update(
        {
            "OG_EVENT_FD": str(event_write),
            "OG_CONTROL_FD": str(control_read),
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _sqlite_holder_child_code(),
            str(tmp_path / "scans.sqlite"),
        ],
        env=environment,
        pass_fds=(event_write, control_read),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    os.close(event_write)
    os.close(control_read)
    return process, event_read, control_write


def test_dz01_real_child_holds_private_lifecycle_lock_and_consumes_ready(tmp_path: Path) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path, scan_id=run.id, upload_name=descriptor.upload_name
    )
    try:
        _wait_for_process_event(event_read, process, "started", timeout=20.0)
        lock_path = tmp_path / ".openguard-zip-dispatch.lock"
        lock_info = lock_path.lstat()
        assert stat.S_ISREG(lock_info.st_mode)
        assert not stat.S_ISLNK(lock_info.st_mode)
        assert lock_info.st_uid == os.geteuid()
        assert stat.S_IMODE(lock_info.st_mode) == 0o600
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.PARTIAL
    assert final.stage is ScanStage.RULES
    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()


@pytest.mark.parametrize(
    ("state", "mode", "event", "expected_status"),
    [
        ("prepared", "cleanup", "cleaned", None),
        ("queued", "terminal", "terminal:partial", ScanStatus.PARTIAL),
        ("ready", "terminal", "terminal:partial", ScanStatus.PARTIAL),
    ],
)
def test_dz02_startup_reconciles_prepared_and_ready_states(
    tmp_path: Path,
    state: str,
    mode: str,
    event: str,
    expected_status: ScanStatus | None,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state=state
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        mode=mode,
    )
    try:
        _wait_for_process_event(event_read, process, "started", timeout=20.0)
        _wait_for_process_event(event_read, process, event, timeout=20.0)
        _release_dispatcher_child(process, event_read, control_write)
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.prepared.json").exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    try:
        rows = registry.list_runs().items
        if expected_status is None:
            assert rows == ()
        else:
            assert len(rows) == 1
            assert rows[0].run.status is expected_status
    finally:
        registry.close()


def test_dz03_mismatched_ready_descriptor_stays_queued_and_is_not_dispatched(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    ready_path = tmp_path / "dispatch" / f"{run.id}.ready.json"
    payload = descriptor.as_payload()
    payload["input_sha256"] = "f" * 64
    ready_path.write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    os.chmod(ready_path, 0o600)
    registry.close()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path, scan_id=run.id, upload_name=descriptor.upload_name, mode="hold"
    )
    try:
        _wait_for_process_event(event_read, process, "started", timeout=20.0)
        _assert_no_process_event(process=process, event_read=event_read, target="terminal:partial")
        _release_dispatcher_child(process, event_read, control_write)
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.QUEUED
    assert archive.exists()
    assert ready_path.exists()


def test_dz04_lost_wakeup_is_recovered_by_periodic_scan_and_four_http_downloads(
    tmp_path: Path,
) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    report_root = _private_dir(tmp_path / "reports")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ZipDispatchStore(dispatch_root, upload_root)
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path, scan_id="*", upload_name="unused.zip", with_reports=True
    )
    scan_id: str | None = None
    try:
        _wait_for_process_event(event_read, process, "started", timeout=20.0)
        runtime = ZipScanRuntime(
            registry,
            upload_root=upload_root,
            workspace_root=workspace_root,
            dispatch_store=store,
        )
        with TestClient(create_app(registry, zip_runtime=runtime), raise_server_exceptions=False) as client:
            response = _post_raw(client, _dynamic_zip("lost-wakeup"), key="dz04-lost-wakeup")
        assert response.status_code == 202
        scan_id = response.json()["scan_id"]
        _wait_for_process_event(event_read, process, "terminal:partial", timeout=20.0)
        _release_dispatcher_child(process, event_read, control_write)
    except Exception:
        _kill_process(process, event_read, control_write)
        registry.close()
        raise

    assert scan_id is not None
    completed = registry.get(scan_id).run
    assert completed.status is ScanStatus.PARTIAL
    assert [link.format for link in completed.report_links] == list(ReportFormat)
    report_app = create_app(
        registry,
        report_store=ReportArtifactStore(report_root),
    )
    media_types = {
        ReportFormat.HTML: "text/html",
        ReportFormat.JSON: "application/json",
        ReportFormat.CSV: "text/csv",
        ReportFormat.RESOURCE_INVENTORY: "text/csv",
    }
    with TestClient(report_app, raise_server_exceptions=False) as client:
        for link in completed.report_links:
            downloaded = client.get(
                f"/api/v1/scans/{scan_id}/report",
                params={"format": link.format.value, "download": "true"},
            )
            assert downloaded.status_code == 200
            assert downloaded.content
            assert downloaded.headers["content-type"].split(";", 1)[0] == media_types[link.format]
            assert hashlib.sha256(downloaded.content).hexdigest() == link.content_hash.value
            encoded = base64.b64encode(bytes.fromhex(link.content_hash.value)).decode("ascii")
            assert downloaded.headers["content-digest"] == f"sha-256=:{encoded}:"
            assert downloaded.headers["etag"] == f'"sha256:{link.content_hash.value}"'
    registry.close()


def test_dz05_repeated_multipart_is_one_durable_run_and_keeps_original_profile(
    tmp_path: Path,
) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private_dir(tmp_path / "uploads")
    dispatch_root = _private_dir(tmp_path / "dispatch")
    workspace_root = _private_dir(tmp_path / "workspaces")
    report_root = _private_dir(tmp_path / "reports")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    content = _dynamic_zip("idempotency")

    legacy_runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        dispatch_store=ZipDispatchStore(dispatch_root, upload_root),
    )
    with TestClient(create_app(registry, zip_runtime=legacy_runtime), raise_server_exceptions=False) as client:
        first = _post_raw(client, content, key="dz05-profile-snapshot")
    ai_runtime = ZipScanRuntime(
        registry,
        upload_root=upload_root,
        workspace_root=workspace_root,
        ai_provider=OllamaProvider(),
        ai_enabled=True,
        ai_timeout_seconds=5.0,
        dispatch_store=ZipDispatchStore(dispatch_root, upload_root),
    )
    with TestClient(create_app(registry, zip_runtime=ai_runtime), raise_server_exceptions=False) as client:
        repeated = _post_raw(client, content, key="dz05-profile-snapshot")
    assert first.status_code == repeated.status_code == 202
    scan_id = first.json()["scan_id"]
    assert repeated.json()["scan_id"] == scan_id
    assert len(registry.list_runs().items) == 1
    descriptor = ZipDispatchStore(dispatch_root, upload_root).read(scan_id, state="ready")
    assert descriptor is not None
    assert descriptor.execution_profile.ai_requested is False

    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path, scan_id=scan_id, upload_name=descriptor.upload_name
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise
    final = _read_run_once(tmp_path / "scans.sqlite", scan_id)
    assert final.status is ScanStatus.PARTIAL
    assert not list(report_root.glob("*"))


def test_dz06_second_real_process_cannot_acquire_the_lifecycle_lock(tmp_path: Path) -> None:
    registry, _, _, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    first, first_events, first_control = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        mode="shutdown_after_start",
        kill_phase="handler_before_return",
        kill_stage="INGESTION",
    )
    second = second_events = second_control = None
    try:
        _wait_for_process_event(first_events, first, "handler_enter", timeout=20.0)
        os.write(first_control, b"s")
        _wait_for_process_event(first_events, first, "shutdown_requested", timeout=20.0)
        second, second_events, second_control = _spawn_dispatcher_child(
            tmp_path, scan_id=run.id, upload_name=descriptor.upload_name, mode="hold"
        )
        _wait_for_process_event(
            second_events, second, "error:dispatch_lock_unavailable", timeout=20.0
        )
        second.wait(timeout=20)
        os.close(second_events)
        os.close(second_control)
        second_events = second_control = None
        os.write(first_control, b"x")
        _wait_for_process_event(first_events, first, "stopped", timeout=20.0)
        first.wait(timeout=20)
        os.close(first_events)
        os.close(first_control)
        first_events = first_control = None
    finally:
        if second is not None and second.poll() is None:
            _kill_process(second, *(fd for fd in (second_events, second_control) if fd is not None))
        else:
            for descriptor in (second_events, second_control):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
        if first.poll() is None:
            _kill_process(first, *(fd for fd in (first_events, first_control) if fd is not None))
        else:
            for descriptor in (first_events, first_control):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass


def test_dz06_fork_child_from_real_dispatcher_does_not_extend_parent_lock(
    tmp_path: Path,
) -> None:
    registry, store, archive, descriptor, run, workspace_root, _ = _seed_dispatch_fixture(
        tmp_path, state="queued"
    )
    (tmp_path / "dispatch" / f"{run.id}.prepared.json").unlink()
    archive.unlink()
    dispatcher = ZipDispatcher(
        registry,
        store,
        data_dir=tmp_path,
        workspace_root=workspace_root,
    )
    child_event_read, child_event_write = os.pipe()
    child_control_read, child_control_write = os.pipe()
    child_pid = None
    second = second_events = second_control = None
    try:
        dispatcher.start()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(child_event_read)
            os.close(child_control_write)
            os.write(child_event_write, b"child_ready\n")
            os.read(child_control_read, 1)
            os._exit(0)
        os.close(child_event_write)
        os.close(child_control_read)
        child_event_write = child_control_read = -1
        selector = selectors.DefaultSelector()
        selector.register(child_event_read, selectors.EVENT_READ)
        try:
            assert selector.select(20.0)
            assert os.read(child_event_read, 12) == b"child_ready\n"
        finally:
            selector.close()

        # The child inherited the dispatcher object, but the product at-fork
        # hook closed its inherited lifecycle descriptor without unlocking the
        # parent's open file description.
        second, second_events, second_control = _spawn_dispatcher_child(
            tmp_path, scan_id=run.id, upload_name=descriptor.upload_name, mode="hold"
        )
        _wait_for_process_event(
            second_events, second, "error:dispatch_lock_unavailable", timeout=20.0
        )
        second.wait(timeout=20)
        os.close(second_events)
        os.close(second_control)
        second_events = second_control = None

        dispatcher.stop_and_join()
        registry.close()
        dispatcher.release_lifecycle_lock()
        second, second_events, second_control = _spawn_dispatcher_child(
            tmp_path, scan_id=run.id, upload_name=descriptor.upload_name, mode="hold"
        )
        _wait_for_process_event(second_events, second, "started", timeout=20.0)
        _release_dispatcher_child(second, second_events, second_control)
        second_events = second_control = None

        os.write(child_control_write, b"x")
        os.close(child_control_write)
        child_control_write = -1
        _, status = os.waitpid(child_pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        child_pid = None
        os.close(child_event_read)
        child_event_read = -1
    finally:
        if second is not None and second.poll() is None:
            _kill_process(second, *(fd for fd in (second_events, second_control) if fd is not None))
        else:
            for descriptor_fd in (second_events, second_control):
                if descriptor_fd is not None:
                    try:
                        os.close(descriptor_fd)
                    except OSError:
                        pass
        if child_pid is not None:
            try:
                os.write(child_control_write, b"x")
            except OSError:
                pass
            os.waitpid(child_pid, 0)
        for descriptor_fd in (
            child_event_read,
            child_event_write,
            child_control_read,
            child_control_write,
        ):
            if descriptor_fd >= 0:
                try:
                    os.close(descriptor_fd)
                except OSError:
                    pass
        if dispatcher._thread is not None or dispatcher.has_lifecycle_lock:
            dispatcher.stop_and_join()
            registry.close()
            dispatcher.release_lifecycle_lock()


def test_dz07_two_real_workers_have_one_queued_cas_winner(tmp_path: Path) -> None:
    registry, _, _, descriptor, run, _, _ = _seed_dispatch_fixture(tmp_path, state="ready")
    registry.close()
    children = [_spawn_worker_child(tmp_path, run.id) for _ in range(2)]
    outcomes: list[str] = []
    try:
        for process, event_read in children:
            _wait_for_process_event(event_read, process, "finished", timeout=20.0)
            process.wait(timeout=20)
            stdout = process.stdout.read().decode("utf-8", errors="replace") if process.stdout else ""
            outcomes.append(stdout.strip().splitlines()[-1])
            os.close(event_read)
    finally:
        for process, event_read in children:
            if process.poll() is None:
                _kill_process(process, event_read)
            else:
                try:
                    os.close(event_read)
                except OSError:
                    pass

    assert sum(item.startswith("done:") for item in outcomes) == 1
    assert sum(item == "error:pipeline_not_claimable" for item in outcomes) == 1
    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.PARTIAL
    check = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    try:
        assert len(check.list_runs().items) == 1
    finally:
        check.close()
    # The direct worker race has no cleanup authority; the durable pair remains
    # visible for the dispatcher/cleanup owner and is not mistaken for absent.
    assert (tmp_path / "uploads" / descriptor.upload_name).exists()
    assert (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()


def test_dz07_common_claim_barrier_has_one_cancelled_or_terminal_cas_winner(
    tmp_path: Path,
) -> None:
    registry, _, _, descriptor, run, _, _ = _seed_dispatch_fixture(tmp_path, state="ready")
    registry.close()
    control_read, control_write = os.pipe()
    worker = cancel = None
    worker_events = cancel_events = None
    try:
        worker, worker_events = _spawn_worker_child(
            tmp_path, run.id, control_read=control_read
        )
        cancel, cancel_events = _spawn_cancel_race_child(tmp_path, run.id, control_read)
        os.close(control_read)
        control_read = -1
        _wait_for_process_event(worker_events, worker, "barrier_ready", timeout=20.0)
        _wait_for_process_event(cancel_events, cancel, "barrier_ready", timeout=20.0)
        # Both OS processes have taken the same pre-CAS snapshot before the
        # shared release, so the winner is decided by the registry CAS itself.
        os.write(control_write, b"xx")
        os.close(control_write)
        control_write = -1
        worker.wait(timeout=20)
        cancel.wait(timeout=20)
        worker_out = worker.stdout.read().decode("utf-8", errors="replace") if worker.stdout else ""
        cancel_out = cancel.stdout.read().decode("utf-8", errors="replace") if cancel.stdout else ""
        worker_result = worker_out.strip().splitlines()[-1]
        cancel_result = cancel_out.strip().splitlines()[-1]
    finally:
        for process, descriptors in (
            (worker, (worker_events,)),
            (cancel, (cancel_events,)),
        ):
            if process is not None and process.poll() is None:
                _kill_process(process, *(fd for fd in descriptors if fd is not None and fd >= 0))
            else:
                for descriptor_fd in descriptors:
                    if descriptor_fd is not None and descriptor_fd >= 0:
                        try:
                            os.close(descriptor_fd)
                        except OSError:
                            pass
        for descriptor_fd in (control_read, control_write):
            if descriptor_fd >= 0:
                try:
                    os.close(descriptor_fd)
                except OSError:
                    pass

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    if final.status is ScanStatus.CANCELLED:
        assert cancel_result == "cancelled"
        assert worker_result == "error:pipeline_not_claimable"
    else:
        assert final.status is ScanStatus.PARTIAL
        assert cancel_result == "error:registry_revision_conflict"
        assert worker_result == "done:partial"


@pytest.mark.parametrize(
    ("source_type", "state"),
    [("zip", "queued"), ("zip", "running"), ("git", "queued"), ("git", "running")],
)
def test_dz07_legacy_runs_without_descriptors_are_byte_for_byte_untouched(
    tmp_path: Path,
    source_type: str,
    state: str,
) -> None:
    if source_type == "zip":
        registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
            tmp_path, state=state
        )
        for descriptor_path in (
            tmp_path / "dispatch" / f"{run.id}.prepared.json",
            tmp_path / "dispatch" / f"{run.id}.ready.json",
        ):
            if descriptor_path.exists():
                descriptor_path.unlink()
        upload_name = descriptor.upload_name
    else:
        registry, _, run, _, _ = _seed_legacy_git_fixture(tmp_path, state=state)
        archive = None
        upload_name = "openguard-upload-legacy.zip"
    before = _read_run_once(tmp_path / "scans.sqlite", run.id)
    if source_type == "zip":
        assert archive is not None and archive.exists()
    registry.close()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path, scan_id=run.id, upload_name=upload_name, mode="hold"
    )
    try:
        _wait_for_process_event(event_read, process, "started", timeout=20.0)
        _assert_no_process_event(event_read, process, "terminal:partial")
        _assert_no_process_event(event_read, process, "terminal:failed")
        _release_dispatcher_child(process, event_read, control_write)
        event_read = control_write = -1
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    after = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert after == before
    assert not (tmp_path / "dispatch" / f"{run.id}.prepared.json").exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()
    if source_type == "zip":
        assert archive is not None and archive.exists()


@pytest.mark.parametrize(
    ("aggregate", "expected_status"),
    [(False, ScanStatus.FAILED), (True, ScanStatus.PARTIAL)],
)
def test_dz08_interrupted_running_is_converged_without_handler_replay(
    tmp_path: Path,
    aggregate: bool,
    expected_status: ScanStatus,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="running", aggregate=aggregate
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:" + expected_status.value)
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is expected_status
    assert final.stage is ScanStage.INVENTORY
    assert final.progress == 15
    assert final.errors[-1].code == "worker_interrupted"
    assert final.report_links == []
    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()


@pytest.mark.parametrize(
    ("kill_phase", "kill_stage", "event", "expected_stage", "expected_progress", "handler_calls"),
    [
        ("claim_after_cas", None, "claim_committed", ScanStage.INGESTION, 5, 0),
        ("handler_before_return", "INGESTION", "handler_enter", ScanStage.INGESTION, 5, 1),
        ("stage_cas_after", "INVENTORY", "stage_cas_committed", ScanStage.INVENTORY, 15, 0),
        ("handler_return_before_cas", "INVENTORY", "handler_returned_before_cas", ScanStage.INVENTORY, 15, 1),
    ],
)
def test_dz08_real_worker_kill_windows_preserve_last_durable_snapshot(
    tmp_path: Path,
    kill_phase: str,
    kill_stage: str | None,
    event: str,
    expected_stage: ScanStage,
    expected_progress: int,
    handler_calls: int,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    handler_count = tmp_path / "handler-calls.txt"
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        kill_phase=kill_phase,
        kill_stage=kill_stage,
        handler_count=handler_count,
    )
    try:
        _wait_for_process_event(event_read, process, event, timeout=20.0)
        _kill_process(process, event_read, control_write)
        event_read = control_write = -1
    finally:
        if process.poll() is None:
            _kill_process(process, *(fd for fd in (event_read, control_write) if fd >= 0))

    interrupted = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert interrupted.status is ScanStatus.RUNNING
    assert interrupted.stage is expected_stage
    assert interrupted.progress == expected_progress
    assert interrupted.id == run.id
    assert interrupted.project == run.project
    assert interrupted.provenance.input_digest == run.provenance.input_digest
    assert interrupted.created_at == run.created_at
    assert interrupted.started_at is not None
    calls = handler_count.read_text(encoding="ascii").splitlines() if handler_count.exists() else []
    assert len(calls) == handler_calls

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        handler_count=handler_count,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:failed")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.FAILED
    assert final.stage is expected_stage
    assert final.progress == expected_progress
    assert final.started_at == interrupted.started_at
    assert final.created_at == interrupted.created_at
    assert final.project == interrupted.project
    assert final.provenance.input_digest == interrupted.provenance.input_digest
    assert [error.code for error in final.errors] == ["worker_interrupted"]
    assert final.report_links == []
    calls_after_restart = handler_count.read_text(encoding="ascii").splitlines() if handler_count.exists() else []
    assert calls_after_restart == calls
    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()


def test_dz08_running_with_report_links_is_retained_and_not_replayed(tmp_path: Path) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="running", report_links=True
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        mode="hold",
    )
    try:
        _wait_for_process_event(event_read, process, "started", timeout=20.0)
        _assert_no_process_event(
            process=process, event_read=event_read, target="terminal:failed"
        )
        _release_dispatcher_child(process, event_read, control_write)
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.RUNNING
    assert len(final.report_links) == 1
    assert archive.exists()
    assert (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()


def test_dz09_provider_call_is_counted_once_across_interrupted_restart(tmp_path: Path) -> None:
    profile = ZipExecutionProfile.from_provider(
        ai_requested=True,
        provider=OllamaProvider(),
        ai_timeout_seconds=5.0,
    )
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready", profile=profile, aggregate=True
    )
    registry.close()
    count_path = tmp_path / "provider-calls.txt"
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        ai_enabled=True,
        ai_timeout_seconds=5.0,
        provider_count=count_path,
    )
    try:
        _wait_for_process_event(event_read, process, "provider_called", timeout=20.0)
        _kill_process(process, event_read, control_write)
        event_read = control_write = -1
    finally:
        if process.poll() is None:
            _kill_process(process, *(fd for fd in (event_read, control_write) if fd >= 0))

    interrupted = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert interrupted.status is ScanStatus.RUNNING
    assert interrupted.stage is ScanStage.AI_ASSIST
    assert count_path.read_text(encoding="ascii").splitlines() == ["call"]

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        ai_enabled=True,
        ai_timeout_seconds=5.0,
        provider_count=count_path,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    # Frozen §7.2: an interrupted run with a durable aggregate converges to
    # PARTIAL; the provider call must not be replayed during reconciliation.
    assert final.status is ScanStatus.PARTIAL
    assert final.errors[-1].code == "worker_interrupted"
    assert final.report_links == []
    assert not archive.exists()


def test_dz10_published_orphans_are_invisible_until_terminal_links_commit(tmp_path: Path) -> None:
    registry, _, archive, descriptor, run, _, report_root = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        with_reports=True,
        publisher_orphan=True,
    )
    try:
        _wait_for_process_event(event_read, process, "reports_published", timeout=20.0)
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.PARTIAL
    assert final.errors[-1].code == "report_publish_failed"
    assert final.report_links == []
    assert not archive.exists()
    report_registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    report_app = create_app(
        report_registry,
        report_store=ReportArtifactStore(report_root),
    )
    with TestClient(report_app, raise_server_exceptions=False) as client:
        for report_format in ReportFormat:
            response = client.get(
                f"/api/v1/scans/{run.id}/report",
                params={"format": report_format.value, "download": "true"},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "report_not_ready"
    report_registry.close()


def test_dz10_kill_after_publisher_before_terminal_cas_leaves_orphan_invisible(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, report_root = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        with_reports=True,
        publisher_kill_phase="before_terminal_cas",
    )
    try:
        _wait_for_process_event(
            event_read, process, "reports_published_before_cas", timeout=20.0
        )
        _kill_process(process, event_read, control_write)
        event_read = control_write = -1
    finally:
        if process.poll() is None:
            _kill_process(process, *(fd for fd in (event_read, control_write) if fd >= 0))

    interrupted = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert interrupted.status is ScanStatus.RUNNING
    assert interrupted.report_links == []
    assert archive.exists()
    _assert_four_format_downloads(
        tmp_path / "scans.sqlite", report_root, run.id, available=False
    )

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        with_reports=True,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise
    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.PARTIAL
    assert final.errors[-1].code == "worker_interrupted"
    assert final.report_links == []
    _assert_four_format_downloads(
        tmp_path / "scans.sqlite", report_root, run.id, available=False
    )


def test_dz10_kill_after_terminal_cas_preserves_links_and_real_downloads(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, report_root = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        with_reports=True,
        publisher_kill_phase="after_terminal_cas",
    )
    try:
        _wait_for_process_event(event_read, process, "terminal_cas_committed", timeout=20.0)
        _kill_process(process, event_read, control_write)
        event_read = control_write = -1
    finally:
        if process.poll() is None:
            _kill_process(process, *(fd for fd in (event_read, control_write) if fd >= 0))

    after_cas = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert after_cas.status is ScanStatus.PARTIAL
    assert [link.format for link in after_cas.report_links] == list(ReportFormat)
    assert archive.exists()
    assert (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        with_reports=True,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise
    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final == after_cas.model_copy()
    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()
    _assert_four_format_downloads(
        tmp_path / "scans.sqlite", report_root, run.id, available=True
    )


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("missing", "dispatch_input_unavailable"),
        ("digest", "dispatch_input_invalid"),
        ("permissions", "dispatch_input_invalid"),
        ("symlink", "dispatch_input_invalid"),
    ],
)
def test_dz11_bad_input_fails_closed_without_handler_or_publisher(
    tmp_path: Path,
    corruption: str,
    expected_error: str,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    ready_path = tmp_path / "dispatch" / f"{run.id}.ready.json"
    if corruption == "missing":
        archive.unlink()
        retained = False
    elif corruption == "digest":
        archive.write_bytes(b"substituted-after-acceptance")
        os.chmod(archive, 0o600)
        retained = True
    elif corruption == "symlink":
        target = tmp_path / "external-not-owned.zip"
        target.write_bytes(_dynamic_zip("symlink-target"))
        os.chmod(target, 0o600)
        archive.unlink()
        archive.symlink_to(target)
        retained = True
    else:
        os.chmod(archive, 0o644)
        retained = True
    registry.close()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path, scan_id=run.id, upload_name=descriptor.upload_name
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:failed")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.FAILED
    assert final.errors[-1].code == expected_error
    assert final.report_links == []
    assert archive.exists() is retained
    assert ready_path.exists() is retained
    if corruption == "symlink":
        assert archive.is_symlink()
        assert target.exists()


@pytest.mark.parametrize(
    ("ai_enabled", "timeout", "provider_incompatible", "expected_status", "expected_error"),
    [
        (False, 10.0, False, ScanStatus.FAILED, "dispatch_profile_disabled"),
        # Acceptance-time timeout is part of the descriptor and must not be
        # revalidated against a later administrator default.
        (True, 6.0, False, ScanStatus.PARTIAL, None),
        # A legal provider object with a different model identity is a
        # profile mismatch, and must be rejected before any provider call.
        (True, 5.0, True, ScanStatus.FAILED, "dispatch_profile_mismatch"),
    ],
)
def test_dz12_ai_profile_is_checked_before_dispatch(
    tmp_path: Path,
    ai_enabled: bool,
    timeout: float,
    provider_incompatible: bool,
    expected_status: ScanStatus,
    expected_error: str | None,
) -> None:
    profile = ZipExecutionProfile.from_provider(
        ai_requested=True,
        provider=OllamaProvider(),
        ai_timeout_seconds=5.0,
    )
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready", profile=profile
    )
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        ai_enabled=ai_enabled,
        ai_timeout_seconds=timeout,
        provider_incompatible=provider_incompatible,
    )
    try:
        _finish_child_after_event(
            process,
            event_read,
            control_write,
            "terminal:" + expected_status.value,
        )
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is expected_status
    if expected_error is not None:
        assert final.errors[-1].code == expected_error
    else:
        assert not any(error.code == "dispatch_profile_mismatch" for error in final.errors)
    assert final.report_links == []
    assert not archive.exists()


def test_dz12_corrupt_descriptor_is_diagnosed_without_business_retry(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    ready_path = tmp_path / "dispatch" / f"{run.id}.ready.json"
    ready_path.write_bytes(b"{not-canonical-json")
    os.chmod(ready_path, 0o600)
    before = _read_run_once(tmp_path / "scans.sqlite", run.id)
    registry.close()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        mode="diagnostic",
    )
    try:
        _wait_for_process_event(
            event_read,
            process,
            "diagnostic:dispatch_descriptor_blocked",
            timeout=20.0,
        )
        _assert_no_process_event(event_read, process, "terminal:partial")
        _assert_no_process_event(event_read, process, "terminal:failed")
        _release_dispatcher_child(process, event_read, control_write)
        event_read = control_write = -1
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    after = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert after == before
    assert archive.exists()
    assert ready_path.read_bytes() == b"{not-canonical-json"


def test_dz13_sqlite_busy_does_not_false_terminal_and_is_retried_next_cycle(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    registry.close()
    dispatcher = dispatcher_events = dispatcher_control = None
    holder = holder_events = holder_control = None
    cas_log = tmp_path / "cas-attempts.jsonl"
    try:
        dispatcher, dispatcher_events, dispatcher_control = _spawn_dispatcher_child(
            tmp_path,
            scan_id=run.id,
            upload_name=descriptor.upload_name,
            mode="start_on_parent",
            busy_timeout_ms=50,
            cas_log=cas_log,
        )
        _wait_for_process_event(dispatcher_events, dispatcher, "registry_ready", timeout=20.0)
        holder, holder_events, holder_control = _spawn_sqlite_holder(tmp_path)
        _wait_for_process_event(holder_events, holder, "locked", timeout=20.0)
        os.write(dispatcher_control, b"x")
        _wait_for_process_event(dispatcher_events, dispatcher, "started", timeout=20.0)
        for _ in range(3):
            _wait_for_process_event(
                dispatcher_events, dispatcher, "cas_error:registry_busy", timeout=20.0
            )
        attempts_before_release = [
            json.loads(line) for line in cas_log.read_text(encoding="utf-8").splitlines()
        ]
        busy_attempts = [item for item in attempts_before_release if item["outcome"] == "error"]
        assert len(busy_attempts) == 3
        assert [item["code"] for item in busy_attempts] == [
            "registry_busy",
            "registry_busy",
            "registry_busy",
        ]
        times = [item["when"] for item in busy_attempts]
        assert times[1] - times[0] >= 0.08
        assert times[2] - times[1] >= 0.4
        os.write(holder_control, b"x")
        os.close(holder_control)
        holder_control = -1
        _wait_for_process_event(holder_events, holder, "released", timeout=20.0)
        holder.wait(timeout=20)
        _wait_for_process_event(dispatcher_events, dispatcher, "cas_ok:ingestion", timeout=20.0)
        attempts_after_release = [
            json.loads(line) for line in cas_log.read_text(encoding="utf-8").splitlines()
        ]
        assert any(
            item["outcome"] == "ok"
            and item["status"] == "running"
            and item["stage"] == "ingestion"
            and item["when"] - times[-1] >= 0.8
            for item in attempts_after_release
        )
        os.close(holder_events)
        holder_events = -1
        _finish_child_after_event(dispatcher, dispatcher_events, dispatcher_control, "terminal:partial")
        dispatcher_events = dispatcher_control = -1
    finally:
        if holder is not None and holder.poll() is None:
            _kill_process(holder, *(fd for fd in (holder_events, holder_control) if fd >= 0))
        else:
            for descriptor_fd in (holder_events, holder_control):
                if descriptor_fd is None:
                    continue
                if descriptor_fd >= 0:
                    try:
                        os.close(descriptor_fd)
                    except OSError:
                        pass
        if dispatcher is not None and dispatcher.poll() is None:
            _kill_process(
                dispatcher,
                *(fd for fd in (dispatcher_events, dispatcher_control) if fd is not None and fd >= 0),
            )

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.PARTIAL
    assert not any(error.code == "registry_busy" for error in final.errors)
    assert not archive.exists()


def test_dz13_running_recovery_busy_cas_retries_after_release_without_false_terminal(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="running"
    )
    registry.close()
    dispatcher = dispatcher_events = dispatcher_control = None
    holder = holder_events = holder_control = None
    cas_log = tmp_path / "recovery-cas-attempts.jsonl"
    try:
        dispatcher, dispatcher_events, dispatcher_control = _spawn_dispatcher_child(
            tmp_path,
            scan_id=run.id,
            upload_name=descriptor.upload_name,
            mode="start_on_parent",
            busy_timeout_ms=50,
            cas_log=cas_log,
            cas_busy_barrier=True,
        )
        _wait_for_process_event(dispatcher_events, dispatcher, "registry_ready", timeout=20.0)
        holder, holder_events, holder_control = _spawn_sqlite_holder(tmp_path)
        _wait_for_process_event(holder_events, holder, "locked", timeout=20.0)
        os.write(dispatcher_control, b"x")
        for _ in range(3):
            _wait_for_process_event(
                dispatcher_events, dispatcher, "cas_error:registry_busy", timeout=20.0
            )
        _wait_for_process_event(
            dispatcher_events, dispatcher, "cas_busy_phase_complete", timeout=20.0
        )
        attempts = [
            json.loads(line) for line in cas_log.read_text(encoding="utf-8").splitlines()
        ]
        busy_attempts = [item for item in attempts if item["outcome"] == "error"]
        assert len(busy_attempts) == 3
        assert [item["stage"] for item in busy_attempts] == ["inventory"] * 3
        busy_times = [item["when"] for item in busy_attempts]
        assert busy_times[1] - busy_times[0] >= 0.08
        assert busy_times[2] - busy_times[1] >= 0.4

        os.write(dispatcher_control, b"x")
        _wait_for_process_event(dispatcher_events, dispatcher, "started", timeout=20.0)
        os.write(holder_control, b"x")
        os.close(holder_control)
        holder_control = -1
        _wait_for_process_event(holder_events, holder, "released", timeout=20.0)
        holder.wait(timeout=20)
        _wait_for_process_event(dispatcher_events, dispatcher, "cas_ok:inventory", timeout=20.0)
        attempts_after_release = [
            json.loads(line) for line in cas_log.read_text(encoding="utf-8").splitlines()
        ]
        recovery_success = [
            item
            for item in attempts_after_release
            if item["outcome"] == "ok"
            and item["status"] == "failed"
            and item["stage"] == "inventory"
        ]
        assert recovery_success
        recovery_delta = recovery_success[0]["when"] - busy_times[-1]
        print(f"DZ13 recovery CAS third-to-success interval: {recovery_delta:.6f}s")
        assert recovery_delta >= 1.0
        assert any(
            item["outcome"] == "ok"
            and item["status"] == "failed"
            and item["stage"] == "inventory"
            and item["when"] - busy_times[-1] >= 1.0
            for item in attempts_after_release
        )
        _finish_child_after_event(dispatcher, dispatcher_events, dispatcher_control, "terminal:failed")
        dispatcher_events = dispatcher_control = -1
    finally:
        if holder is not None and holder.poll() is None:
            _kill_process(holder, *(fd for fd in (holder_events, holder_control) if fd >= 0))
        else:
            for descriptor_fd in (holder_events, holder_control):
                if descriptor_fd is not None and descriptor_fd >= 0:
                    try:
                        os.close(descriptor_fd)
                    except OSError:
                        pass
        if dispatcher is not None and dispatcher.poll() is None:
            _kill_process(
                dispatcher,
                *(fd for fd in (dispatcher_events, dispatcher_control) if fd is not None and fd >= 0),
            )

    final = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert final.status is ScanStatus.FAILED
    assert [error.code for error in final.errors] == ["worker_interrupted"]
    assert not archive.exists()


def test_dz13_unknown_claim_io_marks_uncertain_without_business_retry(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="ready"
    )
    before = _read_run_once(tmp_path / "scans.sqlite", run.id)
    registry.close()
    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        mode="hold",
        claim_io=True,
    )
    try:
        _wait_for_process_event(event_read, process, "claim_io_injected", timeout=20.0)
        _assert_no_process_event(event_read, process, "terminal:partial")
        _assert_no_process_event(event_read, process, "terminal:failed")
        _release_dispatcher_child(process, event_read, control_write)
        event_read = control_write = -1
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    after = _read_run_once(tmp_path / "scans.sqlite", run.id)
    assert after == before
    assert archive.exists()
    assert (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()


def test_dz14_terminal_cleanup_removes_only_a_verified_owned_pair(tmp_path: Path) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="terminal"
    )
    unrelated_upload = tmp_path / "uploads" / "openguard-upload-unrelated.zip"
    unrelated_upload.write_bytes(b"unrelated")
    os.chmod(unrelated_upload, 0o600)
    unrelated_dispatch = tmp_path / "dispatch" / "unrelated.txt"
    unrelated_dispatch.write_bytes(b"keep")
    os.chmod(unrelated_dispatch, 0o600)
    registry.close()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
    except Exception:
        _kill_process(process, event_read, control_write)
        raise
    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()
    assert unrelated_upload.exists()
    assert unrelated_dispatch.exists()


def test_dz14_kill_after_zip_delete_restarts_cleanup_and_preserves_unknown_objects(
    tmp_path: Path,
) -> None:
    registry, _, archive, descriptor, run, _, _ = _seed_dispatch_fixture(
        tmp_path, state="terminal"
    )
    unrelated_upload = tmp_path / "uploads" / "openguard-upload-unknown.zip"
    unrelated_upload.write_bytes(b"unknown-upload")
    os.chmod(unrelated_upload, 0o600)
    unrelated_dispatch = tmp_path / "dispatch" / "unknown-object.bin"
    unrelated_dispatch.write_bytes(b"unknown-dispatch")
    os.chmod(unrelated_dispatch, 0o600)
    registry.close()

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
        mode="cleanup_kill",
    )
    try:
        _wait_for_process_event(
            event_read, process, "zip_deleted_before_descriptor", timeout=20.0
        )
        assert not archive.exists()
        assert (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()
        assert unrelated_upload.exists()
        assert unrelated_dispatch.exists()
        _kill_process(process, event_read, control_write)
        event_read = control_write = -1
    finally:
        if process.poll() is None:
            _kill_process(process, *(fd for fd in (event_read, control_write) if fd >= 0))

    process, event_read, control_write = _spawn_dispatcher_child(
        tmp_path,
        scan_id=run.id,
        upload_name=descriptor.upload_name,
    )
    try:
        _finish_child_after_event(process, event_read, control_write, "terminal:partial")
        event_read = control_write = -1
    except Exception:
        _kill_process(process, event_read, control_write)
        raise

    assert not archive.exists()
    assert not (tmp_path / "dispatch" / f"{run.id}.ready.json").exists()
    assert unrelated_upload.exists()
    assert unrelated_dispatch.exists()


def test_dz15_durable_off_is_default_and_registry_schema_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "factory-data"
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "0")
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "0")
    monkeypatch.setenv("OPENGUARD_ENABLE_PUBLIC_GIT", "0")
    app = create_default_app()
    assert app.state.zip_scan_runtime._dispatch_store is None
    assert not (data_dir / ".openguard-zip-dispatch.lock").exists()
    assert not (data_dir / "dispatch").exists()
    app.state.scan_api_service._registry.close()

    connection = sqlite3.connect(data_dir / "scans.db")
    try:
        tables = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        )
    finally:
        connection.close()
    assert tables == ("registry_metadata", "scan_runs")

    for invalid in ("2", "true", ""):
        monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", invalid)
        with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_DURABLE_ZIP"):
            create_default_app()


def test_dz15_default_production_factory_posts_and_downloads_persisted_zip(
    tmp_path: Path,
) -> None:
    os.chmod(tmp_path, 0o700)
    data_dir = tmp_path / "production-data"
    port = _free_loopback_port()
    project_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "backend")
    environment.update(
        {
            "OPENGUARD_DATA_DIR": str(data_dir),
            "OPENGUARD_ENABLE_DURABLE_ZIP": "1",
            "OPENGUARD_ENABLE_AI": "0",
            "OPENGUARD_ENABLE_PUBLIC_GIT": "0",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.api.main:create_default_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=project_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    scan_id = None
    try:
        _wait_for_uvicorn(process, port)
        body, boundary = _manual_multipart(_dynamic_zip("production-factory"))
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request(
                "POST",
                "/api/v1/scans",
                body=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            accepted = json.loads(response.read().decode("utf-8"))
            assert response.status == 202
            assert accepted["status"] == "queued"
            scan_id = accepted["scan_id"]
        finally:
            connection.close()

        terminal = None
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request("GET", f"/api/v1/scans/{scan_id}")
                status_response = connection.getresponse()
                status_body = json.loads(status_response.read().decode("utf-8"))
            finally:
                connection.close()
            assert status_response.status == 200
            if status_body["status"] in {"completed", "partial", "failed", "cancelled"}:
                terminal = status_body
                break
            pause = selectors.SelectSelector()
            try:
                pause.select(min(0.2, max(0.0, deadline - time.monotonic())))
            finally:
                pause.close()
        assert terminal is not None
        assert terminal["status"] == "partial"

        downloaded: dict[str, bytes] = {}
        for report_format in ReportFormat:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request(
                    "GET",
                    f"/api/v1/scans/{scan_id}/report?format={report_format.value}&download=true",
                )
                report_response = connection.getresponse()
                content = report_response.read()
                assert report_response.status == 200
                assert content
                assert report_response.getheader("content-digest", "").startswith("sha-256=:")
                assert report_response.getheader("etag", "").startswith('"sha256:')
                downloaded[report_format.value] = content
            finally:
                connection.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    assert scan_id is not None
    persisted = _read_run_once(data_dir / "scans.db", scan_id)
    assert persisted.status is ScanStatus.PARTIAL
    assert [link.format.value for link in persisted.report_links] == [
        report_format.value for report_format in ReportFormat
    ]
    for link in persisted.report_links:
        assert hashlib.sha256(downloaded[link.format.value]).hexdigest() == link.content_hash.value
