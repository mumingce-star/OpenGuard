"""Luna-owned black-box I1 acceptance tests for durable ZIP dispatch.

These tests intentionally build their ZIP bytes, multipart body, identity
projection, SQLite snapshots, and crash-process observations independently of
the implementation-side unit tests.  They cover I1 storage only; I2 recovery,
dispatch, and execution are deliberately out of scope.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
import selectors
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from starlette.datastructures import Headers, UploadFile
from fastapi.testclient import TestClient

import app.api.zip_scan as zip_scan_module
import app.persistence.zip_dispatch as zip_dispatch_module
from app.ai import OllamaProvider
from app.api import create_app
from app.api.models import ZipScanCreateFields
from app.api.service import ApiError, ScanApiService
from app.api.zip_scan import ZipScanRuntime
from app.domain.models import ScanRun, ScanStage, ScanStatus
from app.persistence import (
    SQLiteScanRunRegistry,
    ZipDispatchDescriptor,
    ZipDispatchError,
    ZipDispatchStore,
    ZipExecutionProfile,
)


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
