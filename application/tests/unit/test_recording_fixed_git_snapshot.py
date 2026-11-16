"""Operator-pinned source cache: genuine new scan, never a reused result."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app.ingestion.git_stream import GitIngestionService
from app.security.errors import IngestionSecurityError

URL = "https://github.com/http-party/http-server"


def snapshot_type():
    import app.ingestion.git_stream as module
    assert "snapshot" in inspect.signature(GitIngestionService).parameters, "operator-pinned source is absent"
    return module.FixedGitSnapshot


@pytest.fixture
def captured(tmp_path):
    repo = tmp_path / "fixture"
    repo.mkdir()
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(tmp_path)}
    def git(*args):
        return subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
            env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10).stdout
    git("init", "--quiet")
    git("config", "user.name", "Offline Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (repo / "package.json").write_text('{"name":"fixture","version":"1.0.0","license":"MIT","dependencies":{"chalk":"4.1.2"}}')
    (repo / "package-lock.json").write_text('{"lockfileVersion":3,"packages":{"":{"name":"fixture","version":"1.0.0","license":"MIT","dependencies":{"chalk":"4.1.2"}},"node_modules/chalk":{"version":"4.1.2","license":"MIT"}}}')
    (repo / "README.md").write_text("synthetic repository; never executed")
    git("add", ".")
    git("commit", "--quiet", "-m", "synthetic unit fixture")
    revision = git("rev-parse", "HEAD").decode().strip()
    bundle = tmp_path / "source.bundle"
    git("bundle", "create", str(bundle), "HEAD")
    content = bundle.read_bytes()
    bundle.chmod(0o444)
    return dict(bundle_path=bundle, source_url=URL, revision=revision,
        bundle_sha256=hashlib.sha256(content).hexdigest(), bundle_size=len(content),
        captured_at="2026-10-13T09:28:06+00:00", capture_receipt_sha256="a" * 64)


def service(tmp_path, snapshot):
    root = tmp_path / "workspaces"
    root.mkdir(mode=0o700)
    return GitIngestionService(root, snapshot=snapshot), root


def test_real_offline_bundle_is_materialized_once_without_egress(captured, tmp_path, monkeypatch):
    profile = snapshot_type()(**captured)
    import app.ingestion.git_stream as module
    monkeypatch.setattr(module, "TrustedEgressProxy", lambda *a, **k: pytest.fail("network attempted"))
    ingestion, root = service(tmp_path, profile)
    try:
        result = ingestion.ingest_with_consumer(URL, lambda session: session.read_bytes("package.json"))
        assert json.loads(result.consumer_result)["name"] == "fixture"
        assert result.revision == profile.revision
        assert result.egress_evidence == ()
        assert result.source_snapshot.bundle_sha256 == profile.bundle_sha256
        assert result.source_snapshot.capture_receipt_sha256 == "a" * 64
        assert result.source_snapshot.source_url == URL
        assert result.source_snapshot.kind == "FIXED_GIT_SOURCE_SNAPSHOT"
        assert result.runtime_identity.version
        assert len(result.inventory.entries) == 3
        assert result.omissions == ()
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


@pytest.mark.parametrize("field,value", [
    ("bundle_sha256", "b" * 64), ("bundle_size", 1),
    ("revision", "0" * 40), ("source_url", "https://github.com/other/repo"),
])
def test_wrong_binding_rejects_before_consumer(captured, tmp_path, field, value):
    captured[field] = value
    profile = snapshot_type()(**captured)
    ingestion, root = service(tmp_path, profile)
    try:
        with pytest.raises(IngestionSecurityError):
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("consumer reached"))
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


@pytest.mark.parametrize("field,value", [
    ("bundle_sha256", "PASS"), ("revision", "main"), ("bundle_size", True),
    ("bundle_size", -1), ("captured_at", "yesterday"), ("captured_at", "2026-10-13T09:00:00"),
    ("capture_receipt_sha256", ""), ("source_url", "http://github.com/http-party/http-server"),
    ("bundle_path", Path("relative.bundle")),
])
def test_invalid_operator_profile_rejected(captured, field, value):
    profile_type = snapshot_type()
    captured[field] = value
    with pytest.raises((ValueError, IngestionSecurityError)):
        profile_type(**captured)


@pytest.mark.parametrize("change", ["tamper", "symlink", "writable"])
def test_file_tamper_link_and_mutability_rejected(captured, tmp_path, change):
    profile_type = snapshot_type()
    bundle = captured["bundle_path"]
    if change == "tamper":
        bundle.chmod(0o600)
        data = bytearray(bundle.read_bytes()); data[-1] ^= 1
        bundle.write_bytes(data); bundle.chmod(0o444)
    elif change == "symlink":
        target = tmp_path / "link.bundle"; target.symlink_to(bundle)
        captured["bundle_path"] = target
    else:
        bundle.chmod(0o644)
    ingestion, root = service(tmp_path, profile_type(**captured))
    try:
        with pytest.raises(IngestionSecurityError):
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("consumer reached"))
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


def test_default_online_branch_still_requires_real_egress(tmp_path, monkeypatch):
    snapshot_type()
    import app.ingestion.git_stream as module
    class EmptyProxy:
        proxy_url = "http://127.0.0.1:1"
        failure_reason = None
        evidence = ()
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(module, "TrustedEgressProxy", EmptyProxy)
    root = tmp_path / "online"; root.mkdir(mode=0o700)
    ingestion = GitIngestionService(root)
    monkeypatch.setattr(ingestion._runner, "clone_no_checkout", lambda *a, **k: None)
    try:
        with pytest.raises(IngestionSecurityError) as error:
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("consumer reached"))
        assert error.value.reason == "source_connection_failed"
    finally:
        ingestion.close()


def test_completion_seal_includes_snapshot_identity(captured, tmp_path):
    profile = snapshot_type()(**captured)
    from app.ingestion.notice_ingestion import NoticeDependencyResult, NoticeIngestionError, _snapshot
    ingestion, _ = service(tmp_path, profile)
    try:
        result = ingestion.ingest_with_consumer(URL, lambda _: NoticeDependencyResult("fixture", None))
        original = _snapshot(result)
        changed = replace(result, source_snapshot=replace(result.source_snapshot, capture_receipt_sha256="b" * 64))
        assert _snapshot(changed) != original
    finally:
        ingestion.close()


def test_default_factory_accepts_internal_ingestion_factory_only():
    from app.api.main import create_default_app
    assert "git_ingestion_factory" in inspect.signature(create_default_app).parameters
    from app.api.models import GitScanCreateRequest
    assert "snapshot" not in GitScanCreateRequest.model_fields
    assert "bundle_path" not in GitScanCreateRequest.model_fields


def test_source_evidence_survives_real_pipeline_without_manufacturing_partial(captured, tmp_path, monkeypatch):
    profile = snapshot_type()(**captured)
    from app.api import GitScanRuntime, create_app
    from app.persistence import SQLiteScanRunRegistry
    from app.reporting import PipelineReportPublisher, ReportArtifactStore
    from fastapi.testclient import TestClient
    import app.ingestion.git_stream as module
    monkeypatch.setattr(module, "TrustedEgressProxy", lambda *a, **k: pytest.fail("network attempted"))
    root = tmp_path / "workspaces"; root.mkdir(mode=0o700)
    reports = tmp_path / "reports"; reports.mkdir(mode=0o700)
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ReportArtifactStore(reports)
    runtime = GitScanRuntime(registry, workspace_root=root,
        ingestion_factory=lambda path: GitIngestionService(path, snapshot=profile),
        report_publisher=PipelineReportPublisher(store))
    try:
        with TestClient(create_app(registry, git_runtime=runtime, report_store=store)) as client:
            accepted = client.post("/api/v1/scans", json={"source_type": "git", "source": URL})
            assert accepted.status_code == 202
            run = registry.get(accepted.json()["scan_id"]).run
            assert run.status.value == "completed", run.errors
            assert run.project.revision == profile.revision
            assert not run.errors
            observations = [e for e in run.evidence if e.locator == "source-snapshot/git"]
            assert len(observations) == 1
            item = observations[0]
            assert item.producer.name == "git-source-snapshot"
            assert "本次离线重扫" in item.excerpt and profile.bundle_sha256 in item.excerpt
            assert str(profile.bundle_path) not in item.excerpt
            assert run.summary.evidence_count == len(run.evidence)
            assert any(p.name == "git-source-snapshot" for p in run.provenance.tool_versions)
            exported = client.get(f"/api/v1/scans/{run.id}/report?format=json&download=true")
            assert exported.status_code == 200
            assert profile.bundle_sha256 in exported.text
            before = run.model_dump_json()
            assert client.get(f"/api/v1/scans/{run.id}").status_code == 200
            assert registry.get(run.id).run.model_dump_json() == before
            assert list(root.iterdir()) == []
    finally:
        registry.close()


def test_callback_failure_expires_session_and_cleans_workspace(captured, tmp_path):
    profile = snapshot_type()(**captured)
    ingestion, root = service(tmp_path, profile)
    retained = []
    def consume(session):
        retained.append(session)
        raise ValueError("synthetic error")
    try:
        with pytest.raises(IngestionSecurityError) as error:
            ingestion.ingest_with_consumer(URL, consume)
        assert error.value.reason == "scan_consumer_failed"
        assert list(root.iterdir()) == []
        with pytest.raises(IngestionSecurityError):
            retained[0].read_bytes("package.json")
    finally:
        ingestion.close()


def test_offline_clone_protocol_exception_is_exact_and_does_not_leak(captured, tmp_path, monkeypatch):
    profile = snapshot_type()(**captured)
    ingestion, _ = service(tmp_path, profile)
    calls = []
    capture = ingestion._runner.capture
    def observe(args, **kwargs):
        calls.append((args, ingestion._runner._argv(args)))
        return capture(args, **kwargs)
    monkeypatch.setattr(ingestion._runner, "capture", observe)
    try:
        ingestion.ingest_with_consumer(URL, lambda _: None)
        local = [args for args, _ in calls if "protocol.file.allow=always" in args]
        assert len(local) == 1
        assert "clone" in local[0] and "--no-checkout" in local[0] and "--no-recurse-submodules" in local[0]
        assert local[0][-2].endswith("/source.bundle")
        for args, argv in calls:
            assert "protocol.https.allow=never" in argv and "protocol.allow=never" in argv
            assert "core.hooksPath=/dev/null" in argv and "remote.origin.promisor=false" in argv
            if "clone" not in args:
                assert "protocol.file.allow=always" not in argv
    finally:
        ingestion.close()


def test_timeout_blocks_before_clone_and_consumer(captured, tmp_path, monkeypatch):
    profile = snapshot_type()(**captured)
    import app.ingestion.fixed_git_snapshot as module
    ingestion, root = service(tmp_path, profile)
    monkeypatch.setattr(module, "_deadline", lambda _: (_ for _ in ()).throw(
        IngestionSecurityError("scanner_timeout", "fixed_git_snapshot_timeout")))
    monkeypatch.setattr(ingestion._runner, "capture", lambda *a, **k: pytest.fail("Git launched"))
    try:
        with pytest.raises(IngestionSecurityError) as error:
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("consumer reached"))
        assert error.value.code == "scanner_timeout"
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


def test_final_open_is_nonblocking_before_file_type_validation(captured, monkeypatch):
    snapshot_type()
    import app.ingestion.fixed_git_snapshot as module
    original = module.os.open
    calls = []
    def record(path, flags, *args, **kwargs):
        if path == captured["bundle_path"].name:
            calls.append(flags)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(module.os, "open", record)
    descriptor = module._open_no_links(captured["bundle_path"])
    os.close(descriptor)
    assert calls and calls[0] & os.O_NONBLOCK


def test_fifo_is_rejected_without_waiting_for_a_writer(captured, tmp_path):
    profile_type = snapshot_type()
    fifo = tmp_path / "pipe.bundle"; os.mkfifo(fifo, 0o400)
    captured["bundle_path"] = fifo
    ingestion, root = service(tmp_path, profile_type(**captured))
    try:
        with pytest.raises(IngestionSecurityError) as error:
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("consumer reached"))
        assert error.value.reason == "fixed_git_snapshot_file_invalid"
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


def test_every_new_ingestion_rehashes_bundle(captured, tmp_path):
    profile = snapshot_type()(**captured)
    ingestion, root = service(tmp_path, profile)
    try:
        assert ingestion.ingest_with_consumer(URL, lambda _: "first").consumer_result == "first"
        bundle = profile.bundle_path
        bundle.chmod(0o600); data = bytearray(bundle.read_bytes()); data[-1] ^= 1
        bundle.write_bytes(data); bundle.chmod(0o444)
        with pytest.raises(IngestionSecurityError):
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("second consumer reached"))
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


def test_source_changes_during_same_fd_copy_are_rejected(captured, tmp_path, monkeypatch):
    profile = snapshot_type()(**captured)
    import app.ingestion.fixed_git_snapshot as module
    read = module.os.read
    changed = []
    def mutating_read(fd, amount):
        chunk = read(fd, amount)
        if chunk and not changed:
            os.utime(profile.bundle_path, ns=(1, 1)); changed.append(True)
        return chunk
    monkeypatch.setattr(module.os, "read", mutating_read)
    ingestion, root = service(tmp_path, profile)
    try:
        with pytest.raises(IngestionSecurityError) as error:
            ingestion.ingest_with_consumer(URL, lambda _: pytest.fail("consumer reached"))
        assert error.value.reason == "fixed_git_snapshot_identity_mismatch"
        assert list(root.iterdir()) == []
    finally:
        ingestion.close()


def test_default_factory_passes_explicit_snapshot_to_real_runtime(captured, tmp_path, monkeypatch):
    profile = snapshot_type()(**captured)
    from app.api.main import create_default_app
    from fastapi.testclient import TestClient
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(tmp_path / "private-data"))
    for flag in ("AI", "EXTERNAL_SCANNERS", "DURABLE_ZIP", "P2"):
        monkeypatch.setenv("OPENGUARD_ENABLE_" + flag, "0")
    monkeypatch.setenv("OPENGUARD_ENABLE_ASSESSMENTS", "1")
    monkeypatch.setenv("OPENGUARD_ENABLE_PUBLIC_GIT", "1")
    app = create_default_app(git_ingestion_factory=lambda root: GitIngestionService(root, snapshot=profile))
    with TestClient(app) as client:
        response = client.post("/api/v1/scans", json={"source_type": "git", "source": URL})
        assert response.status_code == 202
        service = app.state.assessment_service
        run = service.registry.get(response.json()["scan_id"]).run
        assert run.status.value == "completed", run.errors
        assert run.project.revision == profile.revision
        assert any(e.locator == "source-snapshot/git" for e in run.evidence)
