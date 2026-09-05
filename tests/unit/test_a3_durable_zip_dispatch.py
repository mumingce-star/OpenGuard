"""Implementation-side I1 tests for private ZIP preparation, not I2 dispatch."""

from __future__ import annotations

import io
import json
import os
import stat
import zipfile
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import OllamaProvider
from app.api import create_app, create_default_app
from app.api.models import ZipScanCreateFields
from app.api.service import ScanApiService
from app.api.zip_scan import ZipScanRuntime
from app.domain.models import ScanRun, ScanStage, ScanStatus
from app.persistence import (
    ZIP_DISPATCH_MAX_INPUTS,
    ZipDispatchDescriptor,
    ZipDispatchError,
    ZipDispatchStore,
    ZipExecutionProfile,
)
from app.persistence import SQLiteScanRunRegistry


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _archive() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("requirements.txt", "requests==2.32.0\n")
    return stream.getvalue()


def _post(client: TestClient, content: bytes, *, key: str | None = None):
    fields = {"source_type": "zip"}
    if key is not None:
        fields["idempotency_key"] = key
    return client.post(
        "/api/v1/scans",
        data=fields,
        files={"file": ("demo.zip", content, "application/zip")},
    )


def _prepared_without_registry(tmp_path: Path, content: bytes = b"prepared-bytes"):
    os.chmod(tmp_path, 0o700)
    upload_root = _private(tmp_path / "uploads")
    dispatch_root = _private(tmp_path / "dispatch")
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ZipDispatchStore(dispatch_root, upload_root)
    reservation = store.reserve_upload()
    archive = upload_root / "openguard-upload-prepared.zip"
    archive.write_bytes(content)
    os.chmod(archive, 0o600)
    store.bind_upload(reservation, archive)
    service = ScanApiService(registry)
    candidate = service.build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive.name,
        project_name="prepared",
        input_digest=hashlib.sha256(content).hexdigest(),
    )
    descriptor = store.prepare(
        archive,
        candidate.run,
        ZipExecutionProfile.from_provider(ai_requested=False, provider=None, ai_timeout_seconds=10.0),
        reservation,
    )
    return registry, store, archive, descriptor, candidate.run


@pytest.fixture
def durable_harness(tmp_path: Path):
    os.chmod(tmp_path, 0o700)
    upload_root = _private(tmp_path / "uploads")
    dispatch_root = _private(tmp_path / "dispatch")
    workspace_root = _private(tmp_path / "workspaces")
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
        yield client, registry, store, upload_root, dispatch_root
    registry.close()


def test_i1_http_injection_prepares_ready_descriptor_without_i2_execution(durable_harness) -> None:
    client, registry, store, upload_root, dispatch_root = durable_harness

    response = _post(client, _archive(), key="durable-request-001")

    assert response.status_code == 202
    scan_id = response.json()["scan_id"]
    run = registry.get(scan_id).run
    assert run.status.value == "queued"
    assert store.read(scan_id, state="prepared") is None
    descriptor = store.read(scan_id, state="ready")
    assert descriptor is not None
    assert descriptor.scan_id == run.id
    assert descriptor.upload_name == run.project.source
    assert descriptor.input_sha256 == run.provenance.input_digest.value
    assert descriptor.run_identity_sha256
    assert descriptor.execution_profile.as_payload() == {
        "plan_version": "zip-dependency-v1",
        "ai_requested": False,
        "ai_identity": None,
        "ai_timeout_seconds": 10.0,
    }
    assert sorted(path.name for path in upload_root.iterdir()) == [descriptor.upload_name]
    assert sorted(path.name for path in dispatch_root.iterdir()) == [f"{scan_id}.ready.json"]
    assert stat.S_IMODE((upload_root / descriptor.upload_name).stat().st_mode) == 0o600
    assert stat.S_IMODE((dispatch_root / f"{scan_id}.ready.json").stat().st_mode) == 0o600


def test_i1_same_key_same_bytes_keeps_original_input_and_profile(durable_harness) -> None:
    client, registry, store, upload_root, dispatch_root = durable_harness
    content = _archive()

    first = _post(client, content, key="durable-request-002")
    second = _post(client, content, key="durable-request-002")

    assert first.status_code == second.status_code == 202
    scan_id = first.json()["scan_id"]
    assert second.json()["scan_id"] == scan_id
    assert len(registry.list_runs().items) == 1
    assert store.read(scan_id, state="ready") is not None
    assert not list(dispatch_root.glob("*.prepared.json"))
    assert len(list(upload_root.iterdir())) == 1


def test_i1_same_key_different_bytes_discards_only_known_loser(durable_harness) -> None:
    client, registry, store, upload_root, dispatch_root = durable_harness

    first = _post(client, _archive(), key="durable-request-003")
    conflict = _post(client, _archive() + b"different", key="durable-request-003")

    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"reason": "idempotency_conflict"}
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 1
    assert len(list(dispatch_root.glob("*.ready.json"))) == 1
    assert not list(dispatch_root.glob("*.prepared.json"))


def test_i1_idempotency_conflict_keeps_409_if_loser_cleanup_fails(
    durable_harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, registry, store, upload_root, dispatch_root = durable_harness
    assert _post(client, _archive(), key="durable-request-003-cleanup").status_code == 202
    monkeypatch.setattr(store, "discard_prepared", lambda *args: (_ for _ in ()).throw(ZipDispatchError("dispatch_store_io_failed")))

    conflict = _post(client, _archive() + b"different", key="durable-request-003-cleanup")

    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"] == {"reason": "idempotency_conflict"}
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 2
    assert len(list(dispatch_root.glob("*.ready.json"))) == 1
    assert len(list(dispatch_root.glob("*.prepared.json"))) == 1


def test_i1_idempotency_repeat_keeps_original_202_if_loser_cleanup_fails(
    durable_harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, registry, store, upload_root, dispatch_root = durable_harness
    content = _archive()
    first = _post(client, content, key="durable-request-003-repeat-cleanup")
    monkeypatch.setattr(
        store,
        "discard_prepared",
        lambda *args: (_ for _ in ()).throw(ZipDispatchError("dispatch_store_io_failed")),
    )

    repeated = _post(client, content, key="durable-request-003-repeat-cleanup")

    assert first.status_code == repeated.status_code == 202
    assert repeated.json()["scan_id"] == first.json()["scan_id"]
    assert len(registry.list_runs().items) == 1
    assert len(list(upload_root.iterdir())) == 2
    assert len(list(dispatch_root.glob("*.ready.json"))) == 1
    assert len(list(dispatch_root.glob("*.prepared.json"))) == 1


def test_i1_prebody_capacity_reservation_blocks_eighth_existing_input(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private(tmp_path / "uploads")
    dispatch_root = _private(tmp_path / "dispatch")
    for index in range(ZIP_DISPATCH_MAX_INPUTS):
        item = upload_root / f"openguard-upload-existing{index}.zip"
        item.write_bytes(b"x")
        os.chmod(item, 0o600)
    store = ZipDispatchStore(dispatch_root, upload_root)

    with pytest.raises(ZipDispatchError, match="dispatch_capacity_exceeded"):
        store.reserve_upload()


def test_i1_descriptor_rejects_unknown_and_duplicate_json_keys(durable_harness) -> None:
    client, _, store, _, _ = durable_harness
    scan_id = _post(client, _archive(), key="durable-request-004").json()["scan_id"]
    descriptor = store.read(scan_id, state="ready")
    assert descriptor is not None
    payload = descriptor.as_payload()
    payload["unexpected"] = True
    with pytest.raises(ZipDispatchError, match="dispatch_descriptor_invalid"):
        ZipDispatchDescriptor.from_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    duplicate = b'{"schema":"openguard.zip-dispatch","schema":"openguard.zip-dispatch"}'
    with pytest.raises(ZipDispatchError, match="dispatch_descriptor_invalid"):
        ZipDispatchDescriptor.from_bytes(duplicate)


def test_i1_profile_captures_locked_ai_identity_without_contacting_provider() -> None:
    profile = ZipExecutionProfile.from_provider(
        ai_requested=True,
        provider=OllamaProvider(),
        ai_timeout_seconds=7.5,
    )

    assert profile.ai_requested is True
    assert profile.ai_identity is not None
    assert profile.ai_identity["provider"] == "ollama-local"
    assert profile.ai_identity["model_id"].startswith("qwen3:")
    assert profile.ai_timeout_seconds == 7.5


def test_i1_profile_rejects_a_nonlocked_or_extra_ai_identity() -> None:
    with pytest.raises(ZipDispatchError, match="dispatch_descriptor_invalid"):
        ZipExecutionProfile(
            True,
            {
                "provider": "ollama-local",
                "model_id": "different",
                "runtime_version": "0.33.3",
                "manifest_digest": "a" * 64,
                "prompt_schema_digest": "b" * 64,
            },
            7.5,
        )
    with pytest.raises(ZipDispatchError, match="dispatch_descriptor_invalid"):
        ZipExecutionProfile(
            True,
            {
                "provider": "ollama-local",
                "model_id": OllamaProvider().producer.model_id,
                "runtime_version": OllamaProvider().producer.version,
                "manifest_digest": OllamaProvider().producer.model_id.rsplit(":", 1)[-1],
                "prompt_schema_digest": "0" * 64,
            },
            7.5,
        )
    with pytest.raises(ZipDispatchError, match="dispatch_descriptor_invalid"):
        ZipExecutionProfile(
            True,
            {
                "provider": "ollama-local",
                "model_id": OllamaProvider().producer.model_id,
                "runtime_version": OllamaProvider().producer.version,
                "manifest_digest": OllamaProvider().producer.model_id.rsplit(":", 1)[-1],
                "prompt_schema_digest": OllamaProvider().producer.prompt_schema_digest.value,
                "extra": "no",
            },
            7.5,
        )


def test_i1_active_staged_upload_is_not_double_counted_during_another_reservation(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    upload_root = _private(tmp_path / "uploads")
    dispatch_root = _private(tmp_path / "dispatch")
    store = ZipDispatchStore(dispatch_root, upload_root)
    first = store.reserve_upload()
    staged = upload_root / "openguard-upload-active.zip"
    staged.write_bytes(b"still-reserved")
    os.chmod(staged, 0o600)
    store.bind_upload(first, staged)

    second = store.reserve_upload()

    first.release()
    second.release()


def test_i1_prepare_rejects_digest_mismatch_without_writing_a_descriptor(tmp_path: Path) -> None:
    registry, store, archive, descriptor, _ = _prepared_without_registry(tmp_path, b"correct")
    # This first preparation establishes the shape. A second staged input with
    # a false candidate digest must fail before its descriptor exists.
    upload_root = archive.parent
    reservation = store.reserve_upload()
    false_archive = upload_root / "openguard-upload-false.zip"
    false_archive.write_bytes(b"actual")
    os.chmod(false_archive, 0o600)
    store.bind_upload(reservation, false_archive)
    service = ScanApiService(registry)
    candidate = service.build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=false_archive.name,
        project_name="false",
        input_digest=hashlib.sha256(b"different").hexdigest(),
    )
    with pytest.raises(ZipDispatchError, match="dispatch_store_corrupt"):
        store.prepare(
            false_archive,
            candidate.run,
            ZipExecutionProfile.from_provider(ai_requested=False, provider=None, ai_timeout_seconds=10.0),
            reservation,
        )
    assert not list((upload_root.parent / "dispatch").glob(f"{candidate.run.id}.*.json"))
    reservation.release()
    registry.close()


def test_i1_prepare_requires_the_live_prebody_reservation(tmp_path: Path) -> None:
    registry, store, archive, _, _ = _prepared_without_registry(tmp_path)
    reservation = store.reserve_upload()
    archive_two = archive.parent / "openguard-upload-released.zip"
    archive_two.write_bytes(b"released")
    os.chmod(archive_two, 0o600)
    store.bind_upload(reservation, archive_two)
    reservation.release()
    service = ScanApiService(registry)
    candidate = service.build_zip_scan_candidate(
        ZipScanCreateFields(source_type="zip"),
        staged_name=archive_two.name,
        project_name="released",
        input_digest=hashlib.sha256(b"released").hexdigest(),
    )
    with pytest.raises(ZipDispatchError, match="dispatch_store_invalid_argument"):
        store.prepare(
            archive_two,
            candidate.run,
            ZipExecutionProfile.from_provider(ai_requested=False, provider=None, ai_timeout_seconds=10.0),
            reservation,
        )
    assert store.read(candidate.run.id, state="prepared") is None
    registry.close()


def test_i1_prepared_no_row_cleanup_fsyncs_missing_input_before_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, store, archive, descriptor, _ = _prepared_without_registry(tmp_path)
    archive.unlink()
    calls: list[Path] = []
    original = store._fsync_directory
    monkeypatch.setattr(store, "_fsync_directory", lambda path: calls.append(path))

    store.cleanup_prepared_without_run(descriptor.scan_id, run_exists=lambda _: False)

    assert store.read(descriptor.scan_id, state="prepared") is None
    assert calls == [archive.parent, archive.parent.parent / "dispatch"]
    monkeypatch.setattr(store, "_fsync_directory", original)
    registry.close()


def test_i1_prepared_cleanup_refuses_an_input_whose_digest_changed(tmp_path: Path) -> None:
    registry, store, archive, descriptor, _ = _prepared_without_registry(tmp_path)
    archive.write_bytes(b"substituted")
    os.chmod(archive, 0o600)

    with pytest.raises(ZipDispatchError, match="dispatch_store_corrupt"):
        store.cleanup_prepared_without_run(descriptor.scan_id, run_exists=lambda _: False)
    assert store.read(descriptor.scan_id, state="prepared") == descriptor
    registry.close()


def test_i1_terminal_cleanup_accepts_a_healthy_cancelled_prepared_descriptor(tmp_path: Path) -> None:
    registry, store, archive, descriptor, queued = _prepared_without_registry(tmp_path)
    stored = registry.create(queued)
    payload = queued.model_dump(mode="python")
    payload.update(
        {
            "status": ScanStatus.CANCELLED,
            "stage": ScanStage.QUEUED,
            "finished_at": queued.created_at,
        }
    )
    terminal = ScanRun.model_validate(payload)
    registry.replace(terminal, expected_revision=stored.revision)

    store.cleanup_terminal(terminal, read_registry=lambda scan_id: registry.get(scan_id).run)

    assert not archive.exists()
    assert store.read(descriptor.scan_id, state="prepared") is None
    registry.close()


def test_i1_default_factory_rejects_durable_configuration_until_i2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "1")

    with pytest.raises(RuntimeError, match="requires the unimplemented I2"):
        create_default_app()
    assert not data_dir.exists()
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "invalid")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_DURABLE_ZIP"):
        create_default_app()
