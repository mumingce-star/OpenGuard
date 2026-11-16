"""Implementation-side I1 tests for private ZIP preparation, not I2 dispatch."""

from __future__ import annotations

import io
import json
import os
import stat
import time
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
from app.persistence import ScanRegistryError
from app.pipeline.zip_dispatcher import ZipDispatcher, ZipDispatcherError


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


def _prepared_without_registry(tmp_path: Path, content: bytes = b"prepared-bytes", *, external_scanners: bool = False):
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
        ZipExecutionProfile.from_provider(
            ai_requested=False, provider=None, ai_timeout_seconds=10.0, external_scanners=external_scanners,
        ),
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


def test_i2_default_factory_keeps_legacy_default_and_runs_durable_zip_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "0")
    legacy = create_default_app()
    assert legacy.state.zip_scan_runtime._dispatch_store is None
    legacy.state.scan_api_service._registry.close()

    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "1")
    durable = create_default_app()
    assert durable.state.zip_scan_runtime._dispatch_store is not None
    with TestClient(durable, raise_server_exceptions=False) as client:
        accepted = _post(client, _archive(), key="i2-factory-001")
        assert accepted.status_code == 202
        scan_id = accepted.json()["scan_id"]
        deadline = time.monotonic() + 5
        response = client.get(f"/api/v1/scans/{scan_id}")
        while response.json()["status"] not in {"partial", "failed", "completed"} and time.monotonic() < deadline:
            time.sleep(0.05)
            response = client.get(f"/api/v1/scans/{scan_id}")
        assert response.json()["status"] == "partial"
        assert response.json()["stage"] == "rules"
        assert response.json()["errors"][-1]["code"] == "rules_stage_not_connected"

    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "invalid")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_DURABLE_ZIP"):
        create_default_app()


def test_i2_lifecycle_lock_rejects_a_second_durable_application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "1")
    first = create_default_app()
    second = create_default_app()

    with TestClient(first):
        with pytest.raises(ZipDispatcherError, match="dispatch_lock_unavailable"):
            with TestClient(second):
                pass


def test_i2_fatal_dispatcher_rejects_a_durable_multipart_before_capacity_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "1")
    app = create_default_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        dispatcher = app.state.zip_dispatcher
        dispatcher._stop_fatal("dispatch_storage_failure")
        response = _post(client, _archive(), key="i2-fatal-before-body")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.json()["error"]["details"] == {"reason": "dispatch_storage_failure"}
    assert not list((data_dir / "uploads").glob("openguard-upload-*.zip"))


def test_i2_input_storage_fault_stops_dispatch_and_refuses_the_next_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "1")
    app = create_default_app()
    calls = 0

    with TestClient(app, raise_server_exceptions=False) as client:
        store = app.state.zip_scan_runtime._dispatch_store

        def fail_input(_: ZipDispatchDescriptor) -> Path:
            nonlocal calls
            calls += 1
            raise ZipDispatchError("dispatch_store_io_failed")

        monkeypatch.setattr(store, "input_path_for_dispatch", fail_input)
        first = _post(client, _archive(), key="i2-storage-fault-first")
        assert first.status_code == 202
        scan_id = first.json()["scan_id"]
        deadline = time.monotonic() + 5
        while app.state.zip_dispatcher.fatal_diagnostic is None and time.monotonic() < deadline:
            time.sleep(0.025)
        second = _post(client, _archive(), key="i2-storage-fault-second")
        stored = app.state.scan_api_service._registry.get(scan_id)

    assert calls == 1
    assert app.state.zip_dispatcher.fatal_diagnostic == "dispatch_storage_failure"
    assert app.state.zip_dispatcher.diagnostic_for(scan_id) == "dispatch_input_storage_failure"
    assert stored.run.status is ScanStatus.QUEUED
    assert second.status_code == 500
    assert second.json()["error"]["details"] == {"reason": "dispatch_storage_failure"}


def _ready_dispatcher_case(tmp_path: Path, *, content: bytes = b"zip-bytes"):
    registry, store, archive, descriptor, queued = _prepared_without_registry(tmp_path, content)
    registry.create(queued)
    store.promote(descriptor)
    workspace_root = _private(tmp_path / "workspaces")
    dispatcher = ZipDispatcher(
        registry,
        store,
        data_dir=tmp_path,
        workspace_root=workspace_root,
    )
    return registry, store, archive, descriptor, queued, dispatcher


def _wait_terminal(registry: SQLiteScanRunRegistry, scan_id: str):
    deadline = time.monotonic() + 5
    stored = registry.get(scan_id)
    while stored.run.status.value not in {"partial", "failed", "completed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.025)
        stored = registry.get(scan_id)
    return stored


def _stop_dispatcher(dispatcher: ZipDispatcher, registry: SQLiteScanRunRegistry) -> None:
    dispatcher.stop_and_join()
    registry.close()
    dispatcher.release_lifecycle_lock()


def test_i2_replays_only_a_queued_ready_descriptor_after_startup(tmp_path: Path) -> None:
    registry, store, archive, descriptor, queued, dispatcher = _ready_dispatcher_case(tmp_path, content=_archive())
    try:
        dispatcher.start()
        terminal = _wait_terminal(registry, queued.id)
        assert terminal.run.status is ScanStatus.PARTIAL
        assert terminal.run.errors[-1].code == "rules_stage_not_connected"
        assert store.read(queued.id, state="ready") is None
        assert not archive.exists()
    finally:
        _stop_dispatcher(dispatcher, registry)


def test_i2_missing_bound_input_converges_queued_without_a_handler(tmp_path: Path) -> None:
    registry, store, archive, descriptor, queued, dispatcher = _ready_dispatcher_case(tmp_path)
    archive.unlink()
    try:
        dispatcher.start()
        terminal = _wait_terminal(registry, queued.id)
        assert terminal.run.status is ScanStatus.FAILED
        assert terminal.run.stage is ScanStage.INGESTION
        assert terminal.run.errors[-1].code == "dispatch_input_unavailable"
        assert store.read(queued.id, state="ready") is None
    finally:
        _stop_dispatcher(dispatcher, registry)


def test_i2_startup_running_is_honestly_terminalized_without_replay(tmp_path: Path) -> None:
    registry, store, _, descriptor, queued, dispatcher = _ready_dispatcher_case(tmp_path)
    initial = registry.get(queued.id)
    payload = queued.model_dump(mode="python")
    payload.update(
        status=ScanStatus.RUNNING,
        stage=ScanStage.INGESTION,
        progress=5,
        started_at=queued.created_at,
    )
    registry.replace(ScanRun.model_validate(payload), expected_revision=initial.revision)
    try:
        dispatcher.start()
        terminal = _wait_terminal(registry, queued.id)
        assert terminal.run.status is ScanStatus.FAILED
        assert terminal.run.errors[-1].code == "worker_interrupted"
        assert terminal.run.started_at == queued.created_at
        assert store.read(descriptor.scan_id, state="ready") is None
    finally:
        _stop_dispatcher(dispatcher, registry)


def test_i2_startup_busy_recovery_is_deferred_to_the_dispatcher_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _, _, _, queued, dispatcher = _ready_dispatcher_case(tmp_path)
    initial = registry.get(queued.id)
    payload = queued.model_dump(mode="python")
    payload.update(
        status=ScanStatus.RUNNING,
        stage=ScanStage.INGESTION,
        progress=5,
        started_at=queued.created_at,
    )
    registry.replace(ScanRun.model_validate(payload), expected_revision=initial.revision)
    original = registry.replace
    attempts = 0
    timestamps: list[float] = []

    def busy_before_recovery(run: ScanRun, *, expected_revision: int):
        nonlocal attempts
        if run.status in {ScanStatus.FAILED, ScanStatus.PARTIAL} and attempts < 3:
            attempts += 1
            timestamps.append(time.monotonic())
            raise ScanRegistryError("registry_busy")
        if run.status in {ScanStatus.FAILED, ScanStatus.PARTIAL}:
            timestamps.append(time.monotonic())
        return original(run, expected_revision=expected_revision)

    monkeypatch.setattr(registry, "replace", busy_before_recovery)
    try:
        dispatcher.start()
        dispatcher.notify()
        terminal = _wait_terminal(registry, queued.id)
        assert attempts == 3
        assert timestamps[3] - timestamps[2] >= 0.9
        assert terminal.run.errors[-1].code == "worker_interrupted"
    finally:
        _stop_dispatcher(dispatcher, registry)


def test_i2_uncertain_claim_conflict_isolated_without_a_second_worker_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _, _, _, queued, dispatcher = _ready_dispatcher_case(tmp_path, content=_archive())
    original = registry.replace
    claim_attempts = 0

    def conflict_the_only_claim(run: ScanRun, *, expected_revision: int):
        nonlocal claim_attempts
        if run.status is ScanStatus.RUNNING and run.stage is ScanStage.INGESTION and run.progress == 5:
            claim_attempts += 1
            raise ScanRegistryError("registry_revision_conflict")
        return original(run, expected_revision=expected_revision)

    monkeypatch.setattr(registry, "replace", conflict_the_only_claim)
    try:
        dispatcher.start()
        time.sleep(1.2)
        assert claim_attempts == 1
        assert registry.get(queued.id).run.status is ScanStatus.QUEUED
        assert queued.id in dispatcher._uncertain_running
    finally:
        _stop_dispatcher(dispatcher, registry)


def test_i2_profile_timeout_is_preserved_from_acceptance_not_current_default(tmp_path: Path) -> None:
    registry, store, _, _, queued = _prepared_without_registry(tmp_path)
    profile = ZipExecutionProfile.from_provider(ai_requested=True, provider=OllamaProvider(), ai_timeout_seconds=2.5)
    descriptor = ZipDispatchDescriptor.from_run(queued, profile)
    dispatcher = ZipDispatcher(
        registry,
        store,
        data_dir=tmp_path,
        workspace_root=_private(tmp_path / "workspaces"),
        ai_provider=OllamaProvider(),
        ai_enabled=True,
        ai_timeout_seconds=10.0,
    )
    assert dispatcher._profile_failure(descriptor) is None
    registry.close()


def test_i2_fork_child_closes_the_inherited_fd_without_unlocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry, store, _, _, _ = _prepared_without_registry(tmp_path)
    dispatcher = ZipDispatcher(registry, store, data_dir=tmp_path, workspace_root=_private(tmp_path / "workspaces"))
    closed: list[int] = []
    dispatcher._lock_fd = 321
    monkeypatch.setattr("app.pipeline.zip_dispatcher.os.close", closed.append)
    monkeypatch.setattr("app.pipeline.zip_dispatcher.fcntl.flock", lambda *_: pytest.fail("child must not unlock"))

    dispatcher._after_fork_child()

    assert closed == [321]
    assert dispatcher.has_lifecycle_lock is False
    assert dispatcher._forked_child_pid == os.getpid()
    registry.close()


def test_i2_global_store_failure_stops_the_dispatcher_with_a_fixed_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, store, _, _, _ = _prepared_without_registry(tmp_path)
    dispatcher = ZipDispatcher(registry, store, data_dir=tmp_path, workspace_root=_private(tmp_path / "workspaces"))
    monkeypatch.setattr(store, "scan_ids", lambda **_: (_ for _ in ()).throw(ZipDispatchError("dispatch_store_io_failed")))

    dispatcher._run()

    assert dispatcher.fatal_diagnostic == "dispatch_cycle_stopped"
    registry.close()


def test_i2_recovery_store_preserves_bound_work_when_an_unrelated_upload_is_suspicious(tmp_path: Path) -> None:
    registry, store, archive, descriptor, queued = _prepared_without_registry(tmp_path)
    registry.create(queued)
    store.promote(descriptor)
    suspicious = archive.parent / "unrecognized-input"
    suspicious.write_bytes(b"do-not-delete")
    os.chmod(suspicious, 0o600)

    with pytest.raises(ZipDispatchError, match="dispatch_store_corrupt"):
        ZipDispatchStore(store.dispatch_root, store.upload_root)
    recovery = ZipDispatchStore(store.dispatch_root, store.upload_root, recovery_mode=True)

    assert recovery.read(descriptor.scan_id, state="ready") == descriptor
    with pytest.raises(ZipDispatchError, match="dispatch_store_corrupt"):
        recovery.reserve_upload()
    assert suspicious.exists()
    registry.close()


def test_external_profile_old_payload_stays_four_keys_and_true_roundtrips() -> None:
    legacy = {
        "plan_version": "local-zip-dependencies/v1",
        "ai_requested": False, "ai_identity": None, "ai_timeout_seconds": 10.0,
    }
    # The schema constant is already frozen by the original I1 payload test.
    from app.persistence.zip_dispatch import ZIP_DISPATCH_PLAN_VERSION
    legacy["plan_version"] = ZIP_DISPATCH_PLAN_VERSION
    profile = ZipExecutionProfile.from_payload(legacy)
    assert profile.external_scanners is False
    assert profile.as_payload() == legacy
    enabled = ZipExecutionProfile.from_provider(
        ai_requested=False, provider=None, ai_timeout_seconds=10.0, external_scanners=True,
    )
    assert enabled.as_payload() == {**legacy, "external_scanners": True}
    assert ZipExecutionProfile.from_payload(enabled.as_payload()) == enabled
    for invalid in (0, 1, "true", None):
        with pytest.raises(ZipDispatchError, match="dispatch_descriptor_invalid"):
            ZipExecutionProfile.from_payload({**legacy, "external_scanners": invalid})


@pytest.mark.parametrize("value", ["", "true", "false", "2", "01", " 1"])
def test_external_factory_flag_requires_exact_zero_or_one(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENGUARD_ENABLE_EXTERNAL_SCANNERS", value)
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_EXTERNAL_SCANNERS"):
        create_default_app()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("flag", [None, "0", "1"])
def test_external_factory_config_reaches_both_runtime_and_dispatcher(tmp_path, monkeypatch, flag) -> None:
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENGUARD_ENABLE_DURABLE_ZIP", "1")
    if flag is None:
        monkeypatch.delenv("OPENGUARD_ENABLE_EXTERNAL_SCANNERS", raising=False)
    else:
        monkeypatch.setenv("OPENGUARD_ENABLE_EXTERNAL_SCANNERS", flag)
    app = create_default_app()
    try:
        assert app.state.zip_scan_runtime._external_scanners is (flag == "1")
        assert app.state.zip_dispatcher._external_scanners is (flag == "1")
    finally:
        app.state.scan_api_service._registry.close()


def test_external_acceptance_persists_true_without_running_tools(tmp_path) -> None:
    os.chmod(tmp_path, 0o700)
    upload = _private(tmp_path / "uploads")
    store = ZipDispatchStore(_private(tmp_path / "dispatch"), upload)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    runtime = ZipScanRuntime(
        registry, upload_root=upload, workspace_root=_private(tmp_path / "workspaces"),
        dispatch_store=store, external_scanners=True,
    )
    try:
        with TestClient(create_app(registry, zip_runtime=runtime)) as client:
            response = _post(client, _archive())
        assert response.status_code == 202
        descriptor = store.read(response.json()["scan_id"], state="ready")
        assert descriptor.execution_profile.external_scanners is True
        assert descriptor.as_payload()["execution_profile"]["external_scanners"] is True
    finally:
        registry.close()


@pytest.mark.parametrize("accepted,current", [(False, True), (True, True), (True, False)])
def test_external_recovery_uses_accepted_profile_and_fails_closed_when_disabled(
    tmp_path, monkeypatch, accepted, current,
) -> None:
    registry, store, _, descriptor, queued = _prepared_without_registry(
        tmp_path, _archive(), external_scanners=accepted,
    )
    registry.create(queued)
    store.promote(descriptor)
    recovered = ZipDispatchStore(store.dispatch_root, store.upload_root, recovery_mode=True)
    observed = []
    from app.pipeline import zip_dispatcher as dispatch_module
    real_builder = dispatch_module.build_local_zip_dependency_plan

    def capture_builder(*args, **kwargs):
        observed.append(kwargs.pop("external_scanners"))
        # This test isolates accepted-profile selection; the real external
        # scanner integration is tested at the pipeline boundary separately.
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(dispatch_module, "build_local_zip_dependency_plan", capture_builder)
    dispatcher = ZipDispatcher(
        registry, recovered, data_dir=tmp_path, workspace_root=_private(tmp_path / "workspaces"),
        external_scanners=current,
    )
    try:
        dispatcher.start()
        terminal = _wait_terminal(registry, queued.id)
        assert terminal.run.status in {ScanStatus.PARTIAL, ScanStatus.FAILED}
        if accepted and not current:
            assert observed == []
            assert terminal.run.errors[-1].code == "dispatch_profile_disabled"
        else:
            assert observed == [accepted]
            assert terminal.run.status is ScanStatus.PARTIAL
            assert terminal.run.errors[-1].code == "rules_stage_not_connected"
    finally:
        _stop_dispatcher(dispatcher, registry)


def test_external_runtime_dispatcher_binding_rejects_different_flags(tmp_path) -> None:
    registry, store, _, _, _ = _prepared_without_registry(tmp_path)
    workspace = _private(tmp_path / "workspaces")
    runtime = ZipScanRuntime(
        registry, upload_root=store.upload_root, workspace_root=workspace,
        dispatch_store=store, external_scanners=True,
    )
    dispatcher = ZipDispatcher(registry, store, data_dir=tmp_path, workspace_root=workspace)
    try:
        with pytest.raises(ValueError, match="matching ZIP runtime"):
            create_app(registry, zip_runtime=runtime, zip_dispatcher=dispatcher, close_registry=True)
    finally:
        registry.close()


def test_external_background_runtime_forwards_flag_to_plan(tmp_path, monkeypatch) -> None:
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    runtime = ZipScanRuntime(
        registry, upload_root=_private(tmp_path / "uploads"),
        workspace_root=_private(tmp_path / "workspaces"), external_scanners=True,
    )
    from app.api import zip_scan as zip_module
    real_builder = zip_module.build_local_zip_dependency_plan
    observed = []

    def capture_builder(*args, **kwargs):
        observed.append(kwargs.pop("external_scanners"))
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(zip_module, "build_local_zip_dependency_plan", capture_builder)
    try:
        with TestClient(create_app(registry, zip_runtime=runtime)) as client:
            response = _post(client, _archive())
        assert response.status_code == 202
        assert observed == [True]
        assert registry.get(response.json()["scan_id"]).run.status is ScanStatus.PARTIAL
    finally:
        registry.close()
