"""Implementation tests for A2-3a public Git and TrustedEgress."""

from __future__ import annotations

import io
import os
import socket
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import GitScanRuntime, create_app, create_default_app
from app.ingestion import ZipIngestionService
from app.ingestion.git_materializer import inspect_git_tree, materialize_git_tree
from app.ingestion.git_runner import GitProcessRunner, GitRuntimeIdentity
from app.ingestion.trusted_egress import TrustedEgressProxy
from app.ingestion.url_policy import parse_public_git_url
from app.ingestion.workspace import WorkspaceManager
from app.persistence import SQLiteScanRunRegistry
from app.reporting import PipelineReportPublisher, ReportArtifactStore
from app.security.address_policy import resolve_and_require_public
from app.security.doh_resolver import _parse_dns, _query
from app.security.errors import IngestionSecurityError
from app.security.limits import GitSafetyLimits, ZipSafetyLimits


PYTHON = "/usr/bin/git"
PUBLIC_V4 = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _git(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(
        [PYTHON, "-C", str(repository), *arguments],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
    ).stdout


def _repository(path: Path, files: dict[str, str]) -> Path:
    path.mkdir()
    subprocess.run([PYTHON, "init", "--quiet", str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _git(path, "config", "user.name", "OpenGuard Test")
    _git(path, "config", "user.email", "test@example.invalid")
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(path, "add", "--all")
    _git(path, "commit", "--quiet", "-m", "fixture")
    return path


def _archive() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("requirements.txt", "fastapi==0.141.1\n")
        archive.writestr("package.json", '{"dependencies":{"react":"19.2.0"}}')
    return stream.getvalue()


@pytest.mark.parametrize(
    "source,reason",
    [
        ("https://github.com/example/%2frepo", "path_invalid"),
        ("https://github.com/example/%252frepo", "path_invalid"),
        ("https://git_hub.com/example/repo", "host_invalid"),
        ("https://127.0.0.1/example/repo", "host_not_public"),
        ("https://github.com/example//repo", "path_invalid"),
    ],
)
def test_url_policy_rejects_ambiguous_or_non_dns_sources(source: str, reason: str) -> None:
    with pytest.raises(IngestionSecurityError) as captured:
        parse_public_git_url(source)
    assert (captured.value.code, captured.value.reason) == ("invalid_source", reason)


def test_url_policy_returns_canonical_host_and_url() -> None:
    parsed = parse_public_git_url("https://GitHub.COM:443/mumingce-star/OpenGuard.git")
    assert parsed.host == "github.com"
    assert parsed.canonical == "https://github.com/mumingce-star/OpenGuard.git"


def test_address_policy_requires_every_dns_answer_to_be_public() -> None:
    safe = resolve_and_require_public("example.org", resolver=lambda _host, _port: [PUBLIC_V4])
    assert safe.addresses == ("93.184.216.34",)
    mixed = [PUBLIC_V4, (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))]
    with pytest.raises(IngestionSecurityError) as captured:
        resolve_and_require_public("example.org", resolver=lambda _host, _port: mixed)
    assert captured.value.reason == "source_address_not_public"

    wrong_port = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 22))
    with pytest.raises(IngestionSecurityError) as captured:
        resolve_and_require_public("example.org", resolver=lambda _host, _port: [wrong_port])
    assert captured.value.reason == "source_address_not_public"


def test_doh_wire_parser_accepts_only_matching_bounded_a_response() -> None:
    transaction_id = 0x1234
    question = _query("example.org", 1, transaction_id)[12:]
    answer = b"\xc0\x0c" + b"\x00\x01\x00\x01" + b"\x00\x00\x00\x3c" + b"\x00\x04" + bytes((93, 184, 216, 34))
    message = b"\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + question + answer
    assert _parse_dns(message, transaction_id, 1) == ("93.184.216.34",)
    with pytest.raises(OSError):
        _parse_dns(message, 0x9999, 1)


def test_git_process_policy_is_allowlist_only_and_forces_https_proxy(tmp_path: Path) -> None:
    runner = object.__new__(GitProcessRunner)
    runner.executable = Path("/usr/bin/git")
    environment = runner._environment(_private(tmp_path / "home"), "http://127.0.0.1:40000")
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert environment["HTTPS_PROXY"] == environment["https_proxy"] == "http://127.0.0.1:40000"
    assert environment["HTTP_PROXY"] == environment["ALL_PROXY"] == ""
    assert "GITHUB_TOKEN" not in environment and "SSH_AUTH_SOCK" not in environment
    argv = runner._argv(("clone", "--no-checkout"), proxy_url=environment["HTTPS_PROXY"])
    rendered = "\n".join(argv)
    assert "protocol.allow=never" in rendered
    assert "protocol.https.allow=always" in rendered
    assert "http.followRedirects=false" in rendered
    assert "credential.helper=" in rendered


def test_git_objects_materialize_as_regular_non_executable_inventory(tmp_path: Path) -> None:
    repository = _repository(
        tmp_path / "repository",
        {"requirements.txt": "requests==2.32.5\n", "src/app.py": "print('data only')\n"},
    )
    root = _private(tmp_path / "workspaces")
    home = _private(tmp_path / "home")
    limits = GitSafetyLimits()
    runner = GitProcessRunner(Path(PYTHON), limits)
    manager = WorkspaceManager(root, ZipSafetyLimits(uncompressed_max_bytes=limits.materialized_max_bytes))
    workspace = manager.create()
    try:
        result = materialize_git_tree(
            runner,
            repository,
            workspace,
            home=home,
            limits=limits,
            deadline=time.monotonic() + 30,
        )
        from app.ingestion.inventory import build_inventory

        inventory = build_inventory(workspace, ("tree",))
        assert result.revision == _git(repository, "rev-parse", "HEAD").decode().strip()
        assert [entry.relative_path for entry in inventory.entries] == ["requirements.txt", "src/app.py"]
        assert result.file_count == 2
        tree_fd = workspace.open_directory(("tree",))
        try:
            assert os.stat("requirements.txt", dir_fd=tree_fd, follow_symlinks=False).st_mode & 0o111 == 0
        finally:
            os.close(tree_fd)
    finally:
        manager.cleanup(workspace)
        manager.close()
    assert list(root.iterdir()) == []


def test_git_tree_rejects_symlink_before_materialization(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "repository", {"target.txt": "safe"})
    (repository / "link").symlink_to("target.txt")
    _git(repository, "add", "link")
    _git(repository, "commit", "--quiet", "-m", "symlink")
    limits = GitSafetyLimits()
    runner = GitProcessRunner(Path(PYTHON), limits)
    with pytest.raises(IngestionSecurityError) as captured:
        inspect_git_tree(
            runner,
            repository,
            home=_private(tmp_path / "home"),
            limits=limits,
            deadline=time.monotonic() + 30,
        )
    assert captured.value.reason == "git_entry_unsafe"


class _FakeGitIngestion:
    def __init__(self, root: Path, calls: list[str], *, failure_reason: str | None = None) -> None:
        self.root = root
        self.calls = calls
        self.failure_reason = failure_reason

    def ingest_with_consumer(self, source: str, consumer: object, *, read_limits: object) -> object:
        self.calls.append(source)
        if self.failure_reason is not None:
            code = "invalid_source" if self.failure_reason.startswith("source_") else "scanner_failed"
            raise IngestionSecurityError(code, self.failure_reason)
        service = ZipIngestionService(self.root)
        try:
            result = service.ingest_with_consumer(io.BytesIO(_archive()), consumer, read_limits=read_limits)  # type: ignore[arg-type]
        finally:
            service.close()
        return SimpleNamespace(
            inventory=result.inventory,
            consumer_result=result.consumer_result,
            revision="a" * 40,
            runtime_identity=GitRuntimeIdentity(version="2.50.1", config_digest="b" * 64),
            egress_evidence=(object(),),
        )

    def close(self) -> None:
        return None


def test_default_app_rejects_ambiguous_public_git_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _private(tmp_path / "runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data))
    monkeypatch.setenv("OPENGUARD_ENABLE_PUBLIC_GIT", "true")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_PUBLIC_GIT"):
        create_default_app()


@pytest.fixture
def git_api(tmp_path: Path) -> Iterator[tuple[TestClient, SQLiteScanRunRegistry, list[str]]]:
    os.chmod(tmp_path, 0o700)
    workspaces = _private(tmp_path / "workspaces")
    reports = _private(tmp_path / "reports")
    calls: list[str] = []
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    store = ReportArtifactStore(reports)
    runtime = GitScanRuntime(
        registry,
        workspace_root=workspaces,
        report_publisher=PipelineReportPublisher(store),
        ingestion_factory=lambda root: _FakeGitIngestion(root, calls),  # type: ignore[arg-type]
    )
    with TestClient(create_app(registry, git_runtime=runtime, report_store=store)) as client:
        yield client, registry, calls
    registry.close()


def test_git_json_runs_pipeline_and_publishes_honest_partial_report(git_api: tuple[TestClient, SQLiteScanRunRegistry, list[str]]) -> None:
    client, registry, calls = git_api
    request = {
        "source_type": "git",
        "source": "https://GitHub.COM:443/mumingce-star/OpenGuard.git",
        "idempotency_key": "git-a2-3a-001",
    }
    first = client.post("/api/v1/scans", json=request)
    second = client.post("/api/v1/scans", json=request)
    assert first.status_code == second.status_code == 202
    assert first.json()["scan_id"] == second.json()["scan_id"]
    assert calls == ["https://github.com/mumingce-star/OpenGuard.git"]
    run = registry.get(first.json()["scan_id"]).run
    assert (run.status.value, run.stage.value, run.progress) == ("partial", "rules", 70)
    assert run.project.revision == "a" * 40 and run.project.root_digest == run.provenance.inventory_digest
    assert {(item.ecosystem, item.name) for item in run.components} == {("npm", "react"), ("pypi", "fastapi")}
    assert {item.name for item in run.provenance.tool_versions} >= {"git-client"}
    assert len(run.report_links) == 4
    report = client.get(f"/api/v1/scans/{run.id}/report", params={"format": "json", "download": "true"})
    assert report.status_code == 200
    assert b'rules_stage_not_connected' in report.content


def test_git_post_accept_security_failure_is_durable_failed_not_partial(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    workspaces = _private(tmp_path / "workspaces")
    calls: list[str] = []
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    runtime = GitScanRuntime(
        registry,
        workspace_root=workspaces,
        ingestion_factory=lambda root: _FakeGitIngestion(root, calls, failure_reason="source_address_not_public"),  # type: ignore[arg-type]
    )
    try:
        with TestClient(create_app(registry, git_runtime=runtime)) as client:
            response = client.post(
                "/api/v1/scans",
                json={"source_type": "git", "source": "https://github.com/example/repository.git"},
            )
            assert response.status_code == 202
            run = registry.get(response.json()["scan_id"]).run
            assert (run.status.value, run.stage.value, run.progress) == ("failed", "ingestion", 5)
            assert [(error.code, error.message) for error in run.errors] == [
                ("invalid_source", "Public Git ingestion failed.")
            ]
            assert not run.report_links
    finally:
        registry.close()


def test_git_capacity_failure_is_distinguished_from_runtime_failure(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    workspaces = _private(tmp_path / "workspaces")
    calls: list[str] = []
    registry = SQLiteScanRunRegistry(tmp_path / "scans.sqlite")
    runtime = GitScanRuntime(
        registry,
        workspace_root=workspaces,
        ingestion_factory=lambda root: _FakeGitIngestion(
            root,
            calls,
            failure_reason="git_materialized_limit_exceeded",
        ),  # type: ignore[arg-type]
    )
    try:
        with TestClient(create_app(registry, git_runtime=runtime)) as client:
            response = client.post(
                "/api/v1/scans",
                json={"source_type": "git", "source": "https://github.com/example/repository.git"},
            )
            assert response.status_code == 202
            run = registry.get(response.json()["scan_id"]).run
            assert (run.status.value, run.stage.value, run.progress) == ("failed", "ingestion", 5)
            assert [(error.code, error.message) for error in run.errors] == [
                ("scanner_failed", "Public Git repository exceeds the configured scan capacity limit.")
            ]
            assert calls == ["https://github.com/example/repository.git"]
            assert not run.report_links
    finally:
        registry.close()


@pytest.mark.skipif(os.environ.get("OPENGUARD_RUN_LOOPBACK_TESTS") != "1", reason="requires controlled loopback bind")
def test_trusted_egress_connects_only_validated_address_and_counts_tunnel_bytes() -> None:
    proxy_peer: socket.socket | None = None

    def connector(_endpoint: object, _timeout: float) -> socket.socket:
        nonlocal proxy_peer
        outbound, proxy_peer = socket.socketpair()
        return outbound

    with TrustedEgressProxy(
        "example.org",
        transfer_max_bytes=1024,
        connect_timeout_s=3,
        resolver=lambda _host, _port: [PUBLIC_V4],
        connector=connector,  # type: ignore[arg-type]
    ) as proxy:
        client = socket.create_connection(("127.0.0.1", int(proxy.proxy_url.rsplit(":", 1)[1])), timeout=3)
        client.sendall(b"CONNECT example.org:443 HTTP/1.1\r\nHost: example.org:443\r\n\r\n")
        assert client.recv(4096).startswith(b"HTTP/1.1 200")
        assert proxy_peer is not None

        def echo() -> None:
            assert proxy_peer is not None
            assert proxy_peer.recv(4) == b"ping"
            proxy_peer.sendall(b"pong")
            proxy_peer.close()

        thread = threading.Thread(target=echo)
        thread.start()
        client.sendall(b"ping")
        assert client.recv(4) == b"pong"
        client.close()
        thread.join(timeout=3)
        assert proxy.ledger.used == 8
        assert proxy.evidence[0].dialed_address == "93.184.216.34"
        assert proxy.evidence[0].tls_server_name == "example.org"


@pytest.fixture
def local_git_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Replace transport only; exercise real Git objects, sessions and cleanup."""
    import shutil
    import app.ingestion.git_stream as module

    repository = _repository(tmp_path / "source", {
        "package.json": '{"dependencies":{"react":"19.2.0"}}',
        "package-lock.json": '{"name":"fixture","lockfileVersion":3,"packages":{"":{"dependencies":{"react":"19.2.0"}},"node_modules/react":{"version":"19.2.0","license":"MIT"}}}',
        "README.md": "Model: https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct\n",
    })

    class Transport:
        proxy_url = "http://127.0.0.1:1"
        evidence = (object(),)
        failure_reason = None

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def clone(_self, source, destination, **kwargs):
        shutil.copytree(repository, destination)

    monkeypatch.setattr(module, "TrustedEgressProxy", Transport)
    monkeypatch.setattr(GitProcessRunner, "clone_no_checkout", clone)
    root = _private(tmp_path / "git-workspaces")
    service = module.GitIngestionService(root)
    yield service, root
    service.close()


@pytest.mark.parametrize("behavior", ["complete", "exception", "tamper"])
def test_git_trusted_tree_lifetime_integrity_and_cleanup(local_git_service, behavior):
    service, root = local_git_service
    captured = {}

    def consumer(session):
        captured["session"] = session
        return session.inventory.root_digest

    def tree_consumer(tree, inventory):
        captured["tree"] = tree
        assert inventory is captured["session"].inventory
        assert captured["session"].read_bytes("README.md", max_bytes=512).startswith(b"Model:")
        fd = tree._directory_fd
        captured["fd"] = fd
        assert os.stat("README.md", dir_fd=fd).st_size > 0
        if behavior == "exception":
            raise ValueError("scanner failed")
        if behavior == "tamper":
            target = os.open("README.md", os.O_WRONLY | os.O_TRUNC, dir_fd=fd)
            try:
                os.write(target, b"changed")
            finally:
                os.close(target)

    if behavior == "complete":
        result = service.ingest_with_consumer("https://github.com/example/repo", consumer, tree_consumer=tree_consumer)
        assert result.consumer_result == result.inventory.root_digest
    else:
        with pytest.raises(IngestionSecurityError) as error:
            service.ingest_with_consumer("https://github.com/example/repo", consumer, tree_consumer=tree_consumer)
        assert error.value.code == "scanner_failed"
        if behavior == "exception":
            assert error.value.reason == "scan_consumer_failed"
        else:
            assert error.value.reason != "scan_consumer_failed"
    assert not captured["tree"]._active
    with pytest.raises(OSError):
        os.fstat(captured["fd"])
    with pytest.raises(IngestionSecurityError):
        captured["tree"].proc_target()
    with pytest.raises(IngestionSecurityError):
        captured["session"].read_bytes("README.md", max_bytes=512)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("external_enabled", [False, True])
def test_git_existing_runtime_reaches_assets_license_risk_and_reports(local_git_service, tmp_path, monkeypatch, external_enabled):
    """Real materialization and production pipeline; external binary seam only."""
    import app.pipeline.public_git as module
    from app.pipeline.external_scans import ExternalScanFacts

    service, root = local_git_service
    calls = []

    def external(tree, inventory, clock):
        assert tree._active and os.fstat(tree._directory_fd)
        calls.append(inventory.root_digest)
        return ExternalScanFacts()

    monkeypatch.setattr(module, "collect_external_scans", external)
    registry = SQLiteScanRunRegistry(tmp_path / "git-run.sqlite")
    store = ReportArtifactStore(_private(tmp_path / "git-reports"))
    runtime = GitScanRuntime(registry, workspace_root=root,
        ingestion_factory=lambda _: service, external_scanners=external_enabled,
        report_publisher=PipelineReportPublisher(store))
    try:
        with TestClient(create_app(registry, git_runtime=runtime, report_store=store)) as client:
            response = client.post("/api/v1/scans", json={"source_type": "git", "source": "https://github.com/example/repo"})
            assert response.status_code == 202
            run = registry.get(response.json()["scan_id"]).run
            assert run.status.value == "completed", run.errors
            assert not run.errors
            assert calls == ([run.provenance.inventory_digest.value] if external_enabled else [])
            assert {asset.name for asset in run.ai_assets} == {"Qwen/Qwen2.5-Coder-32B-Instruct"}
            assert any(item.expression == "MIT" for item in run.licenses)
            assert run.findings and all(item.evidence_ids for item in run.findings)
            assert len(run.report_links) == 4
            for format in ("json", "html", "csv", "resource_inventory"):
                report = client.get(f"/api/v1/scans/{run.id}/report", params={"format": format, "download": "true"})
                assert report.status_code == 200
                assert b"Qwen" in report.content
            assert list(root.iterdir()) == []
    finally:
        registry.close()


@pytest.mark.parametrize("value", [0, 1, "1", None])
def test_git_external_scanners_requires_boolean(tmp_path, value):
    from app.pipeline.public_git import build_public_git_dependency_plan
    from app.pipeline.worker import PipelineError

    clock = lambda: datetime.now(timezone.utc)
    with pytest.raises(PipelineError):
        build_public_git_dependency_plan("https://github.com/example/repo", tmp_path, clock=clock, external_scanners=value)
    registry = SQLiteScanRunRegistry(tmp_path / "boolean.sqlite")
    try:
        with pytest.raises(ValueError, match="invalid Git runtime"):
            GitScanRuntime(registry, workspace_root=tmp_path, external_scanners=value)
    finally:
        registry.close()


def test_git_tree_close_failure_poisoned_and_cleaned(local_git_service, monkeypatch):
    from app.ingestion.zip_stream import TrustedTreeScan

    service, root = local_git_service
    original = TrustedTreeScan.close

    def fail_close(tree):
        original(tree)
        raise OSError("close failure")

    monkeypatch.setattr(TrustedTreeScan, "close", fail_close)
    with pytest.raises(IngestionSecurityError):
        service.ingest_with_consumer("https://github.com/example/repo", lambda session: None,
                                     tree_consumer=lambda tree, inventory: None)
    assert list(root.iterdir()) == []
    with pytest.raises(IngestionSecurityError) as error:
        service.ingest_with_consumer("https://github.com/example/repo", lambda session: None)
    assert error.value.reason == "workspace_cleanup_failed"


@pytest.mark.parametrize('source', [
    'https://github.com/openai/openai-python/',
    'https://github.com/openai/openai-python.git/',
])
def test_github_root_url_accepts_one_trailing_slash(source: str) -> None:
    assert parse_public_git_url(source).canonical == source[:-1]


@pytest.mark.parametrize('source', [
    'https://github.com/microsoft/autogenhttps://github.com/run-llama/llama_index',
    'https://github.com/openai/openai-python/tree/main',
    'https://github.com/openai/openai-python/blob/main/README.md',
    'https://github.com/openai/openai-python//',
])
def test_github_non_repository_and_joined_urls_fail_before_network(source: str) -> None:
    with pytest.raises(IngestionSecurityError):
        parse_public_git_url(source)


def test_bounded_tree_records_symlink_and_gitlink_without_following(tmp_path: Path) -> None:
    from app.ingestion.git_materializer import inspect_bounded_git_tree
    repository = _repository(tmp_path / 'repo', {'requirements.txt': 'packaging==25.0'})
    revision = _git(repository, 'rev-parse', 'HEAD').decode().strip()
    (repository / 'outside').symlink_to('/etc/passwd')
    _git(repository, 'add', 'outside')
    _git(repository, 'update-index', '--add', '--cacheinfo', f'160000,{revision},subproject')
    _git(repository, 'commit', '--quiet', '-m', 'special entries')
    limits = GitSafetyLimits()
    runner = GitProcessRunner(Path(PYTHON), limits, bounded=True)
    _, selected, omitted, discovered = inspect_bounded_git_tree(runner, repository,
        home=_private(tmp_path / 'home'), limits=limits, deadline=time.monotonic() + 10)
    assert discovered == 3
    assert [e.relative_path for e in selected] == ['requirements.txt']
    assert {(e.path, e.reason) for e in omitted} == {
        ('outside', 'symlink_not_followed'), ('subproject', 'submodule_not_fetched')}


def test_bounded_large_tree_selects_root_manifests_before_deep_sources() -> None:
    from app.ingestion.git_materializer import inspect_bounded_git_tree
    names = [f'src/deep/file_{i:05d}.py' for i in range(4500)] + ['README.md', 'LICENSE', 'pyproject.toml']
    class Runner:
        def capture(self, args, **kwargs):
            if 'rev-parse' in args:
                return b'a' * 40 + b'\n'
            assert '-l' not in args
            return b''.join(b'100644 blob ' + b'a' * 40 + b'\t' + name.encode() + b'\0' for name in names)
    _, selected, omitted, discovered = inspect_bounded_git_tree(Runner(), Path('/unused'),
        home=Path('/unused'), limits=GitSafetyLimits(), deadline=time.monotonic() + 10)
    assert discovered == len(names)
    assert len(selected) == 512
    assert [e.relative_path for e in selected[:3]] == ['LICENSE', 'pyproject.toml', 'README.md']
    assert len(omitted) == len(names) - 512
    assert {e.path for e in omitted} | {e.relative_path for e in selected} == set(names)


def test_offline_object_commands_deny_promisor_network() -> None:
    runner = GitProcessRunner(Path(PYTHON), GitSafetyLimits(), bounded=True)
    offline = runner._argv(('cat-file', '--batch-check'))
    assert offline.index('protocol.https.allow=never') > offline.index('protocol.https.allow=always')
    assert 'remote.origin.promisor=false' in offline
    assert runner._environment(Path('/unused'))['GIT_NO_LAZY_FETCH'] == '1'
    online = runner._argv(('fetch', 'origin'), proxy_url='http://127.0.0.1:12345')
    assert 'protocol.https.allow=never' not in online
    assert 'http.proxy=http://127.0.0.1:12345' in online


@pytest.mark.parametrize("licensed", [False, True])
def test_bounded_coverage_survives_pipeline_and_report_with_complete_paths(tmp_path: Path, monkeypatch, licensed: bool) -> None:
    from app.ingestion.git_materializer import GitOmission
    if licensed:
        def licensed_archive():
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                archive.writestr('package.json', '{"dependencies":{"react":"19.2.0"}}')
                archive.writestr('package-lock.json', '{"lockfileVersion":3,"packages":{"":{"dependencies":{"react":"19.2.0"}},"node_modules/react":{"version":"19.2.0","license":"MIT"}}}')
            return stream.getvalue()
        monkeypatch.setitem(_FakeGitIngestion.ingest_with_consumer.__globals__, '_archive', licensed_archive)
    class BoundedFixture(_FakeGitIngestion):
        def ingest_with_consumer(self, *args, **kwargs):
            result = super().ingest_with_consumer(*args, **kwargs)
            result.omissions = (GitOmission('docs/<untrusted>.bin', 'bounded_byte_budget', 'c' * 40),
                                GitOmission('submodule', 'submodule_not_fetched', 'd' * 40))
            result.discovered_entries = 4
            return result
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / 'scans.sqlite')
    store = ReportArtifactStore(_private(tmp_path / 'reports'))
    runtime = GitScanRuntime(registry, workspace_root=_private(tmp_path / 'workspaces'),
        report_publisher=PipelineReportPublisher(store), ingestion_factory=lambda root: BoundedFixture(root, []))
    try:
        with TestClient(create_app(registry, git_runtime=runtime, report_store=store)) as client:
            accepted = client.post('/api/v1/scans', json={'source_type':'git', 'source':'https://github.com/example/repo'})
            assert accepted.status_code == 202
            run = registry.get(accepted.json()['scan_id']).run
            assert run.status.value == 'partial'
            if licensed:
                assert run.stage.value == 'report'
                assert any(e.code == 'scan_incomplete' for e in run.errors)
            error = next(e for e in run.errors if e.code == 'git_scan_coverage_partial')
            coverage = [e for e in run.evidence if e.id in error.evidence_ids]
            assert {e.locator for e in coverage} == {'docs/<untrusted>.bin', 'submodule'}
            assert all('Git revision=' + 'a' * 40 in e.excerpt for e in coverage)
            assert all(e.content_hash is None for e in coverage)
            assert run.summary.evidence_count == len(run.evidence)
            html = client.get(f'/api/v1/scans/{run.id}/report?format=html&download=true').text
            assert '扫描覆盖范围：未扫描条目' in html
            assert 'docs/&lt;untrusted&gt;.bin' in html and 'submodule_not_fetched' in html
            assert 'docs/<untrusted>.bin' not in html
    finally:
        registry.close()


def test_bounded_many_licenses_do_not_starve_project_manifests() -> None:
    from app.ingestion.git_materializer import inspect_bounded_git_tree
    names = [f'integrations/packages/pkg{i:05d}/LICENSE' for i in range(4500)] + [
        'core/pyproject.toml', 'core/LICENSE', 'README.md']
    class Runner:
        def capture(self, args, **kwargs):
            if 'rev-parse' in args:
                return b'a' * 40 + b'\n'
            return b''.join(b'100644 blob ' + b'a' * 40 + b'\t' + name.encode() + b'\0' for name in names)
    _, selected, _, _ = inspect_bounded_git_tree(Runner(), Path('/unused'), home=Path('/unused'),
        limits=GitSafetyLimits(), deadline=time.monotonic() + 10)
    assert {'core/pyproject.toml', 'core/LICENSE', 'README.md'} <= {e.relative_path for e in selected[:3]}


def test_bounded_materialization_omits_oversize_blob_without_fabricated_file(tmp_path: Path, monkeypatch) -> None:
    from app.ingestion.git_materializer import materialize_bounded_git_tree
    from app.ingestion.inventory import build_inventory
    repository = _repository(tmp_path / 'repo', {'large.txt': 'x' * (4 * 1024 * 1024 + 1),
                                                'requirements.txt': 'packaging==25.0'})
    limits = GitSafetyLimits()
    runner = GitProcessRunner(Path(PYTHON), limits, bounded=True)
    # Local fixture objects already exist: test the real object reader/materializer.
    monkeypatch.setattr(runner, 'fetch_objects', lambda *args, **kwargs: None)
    manager = WorkspaceManager(_private(tmp_path / 'work'), ZipSafetyLimits())
    workspace = manager.create()
    try:
        result = materialize_bounded_git_tree(runner, repository, workspace,
            home=_private(tmp_path / 'home'), limits=limits, deadline=time.monotonic() + 10,
            proxy_url='http://127.0.0.1:1')
        inventory = build_inventory(workspace)
        assert result.file_count == 1
        assert [(e.relative_path, e.size_bytes) for e in inventory.entries] == [('requirements.txt', 15)]
        assert [(e.path, e.reason) for e in result.omissions] == [('large.txt', 'bounded_single_file_budget')]
    finally:
        manager.cleanup(workspace)
        manager.close()


def test_offline_missing_promisor_blob_cannot_hydrate_from_origin(tmp_path: Path) -> None:
    source = _repository(tmp_path / 'source', {'payload.txt': 'must not be hydrated'})
    _git(source, 'config', 'uploadpack.allowFilter', 'true')
    oid = _git(source, 'rev-parse', 'HEAD:payload.txt').decode().strip()
    target = tmp_path / 'partial'
    subprocess.run([PYTHON, 'clone', '--quiet', '--no-checkout', '--filter=blob:none',
                    source.as_uri(), str(target)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    packs_before = sorted((target / '.git/objects/pack').iterdir())
    runner = GitProcessRunner(Path(PYTHON), GitSafetyLimits(), bounded=True)
    with pytest.raises(IngestionSecurityError):
        runner.object_sizes(target, (oid,), home=_private(tmp_path / 'home'), deadline=time.monotonic() + 5)
    assert sorted((target / '.git/objects/pack').iterdir()) == packs_before


def test_bounded_selection_respects_python_manifest_candidate_budget(tmp_path: Path, monkeypatch) -> None:
    from app.ingestion.git_materializer import materialize_bounded_git_tree
    from app.ingestion.inventory import build_inventory
    repository = _repository(tmp_path / 'repo', {f'pkg{i:03d}/pyproject.toml': '[project]\nname="example"\n' for i in range(65)})
    limits = GitSafetyLimits()
    runner = GitProcessRunner(Path(PYTHON), limits, bounded=True)
    monkeypatch.setattr(runner, 'fetch_objects', lambda *args, **kwargs: None)
    manager = WorkspaceManager(_private(tmp_path / 'work'), ZipSafetyLimits())
    workspace = manager.create()
    try:
        result = materialize_bounded_git_tree(runner, repository, workspace,
            home=_private(tmp_path / 'home'), limits=limits, deadline=time.monotonic() + 10,
            proxy_url='http://127.0.0.1:1')
        assert len(build_inventory(workspace).entries) == 64
        assert [(e.path, e.reason) for e in result.omissions] == [('pkg064/pyproject.toml', 'bounded_python_manifest_count')]
    finally:
        manager.cleanup(workspace)
        manager.close()


def test_bounded_omissions_survive_no_dependency_failure_and_remain_reportable(tmp_path: Path, monkeypatch) -> None:
    from app.ingestion.git_materializer import GitOmission
    def only_readme():
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('README.md', 'No supported dependency declarations here.')
        return stream.getvalue()
    monkeypatch.setitem(_FakeGitIngestion.ingest_with_consumer.__globals__, '_archive', only_readme)
    class BoundedFixture(_FakeGitIngestion):
        def ingest_with_consumer(self, *args, **kwargs):
            result = super().ingest_with_consumer(*args, **kwargs)
            result.omissions = (GitOmission('omitted/source.bin', 'bounded_single_file_budget', 'c' * 40),)
            result.discovered_entries = 2
            return result
    os.chmod(tmp_path, 0o700)
    registry = SQLiteScanRunRegistry(tmp_path / 'scans.sqlite')
    store = ReportArtifactStore(_private(tmp_path / 'reports'))
    runtime = GitScanRuntime(registry, workspace_root=_private(tmp_path / 'workspaces'),
        report_publisher=PipelineReportPublisher(store), ingestion_factory=lambda root: BoundedFixture(root, []))
    try:
        with TestClient(create_app(registry, git_runtime=runtime, report_store=store)) as client:
            accepted = client.post('/api/v1/scans', json={'source_type':'git', 'source':'https://github.com/example/repo'})
            assert accepted.status_code == 202
            run = registry.get(accepted.json()['scan_id']).run
            assert run.status.value == 'partial', run.model_dump_json()
            assert not run.components and not run.ai_assets and not run.findings
            assert {e.code for e in run.errors} >= {'git_scan_coverage_partial', 'dependency_manifest_not_found'}
            assert [e.locator for e in run.evidence] == ['omitted/source.bin']
            assert len(run.report_links) == 4
            html = client.get(f'/api/v1/scans/{run.id}/report?format=html&download=true').text
            assert 'omitted/source.bin' in html and 'bounded_single_file_budget' in html
    finally:
        registry.close()


def test_bounded_blob_fetch_batches_are_capped_at_256_unique_objects(tmp_path: Path, monkeypatch) -> None:
    from app.ingestion.git_materializer import materialize_bounded_git_tree
    repository = _repository(tmp_path / 'repo', {f'src/file{i:03d}.txt': str(i) for i in range(258)})
    runner = GitProcessRunner(Path(PYTHON), GitSafetyLimits(), bounded=True)
    calls = []
    monkeypatch.setattr(runner, 'fetch_objects', lambda repository, ids, **kwargs: calls.append(ids))
    manager = WorkspaceManager(_private(tmp_path / 'work'), ZipSafetyLimits())
    workspace = manager.create()
    try:
        result = materialize_bounded_git_tree(runner, repository, workspace,
            home=_private(tmp_path / 'home'), limits=GitSafetyLimits(), deadline=time.monotonic() + 10,
            proxy_url='http://127.0.0.1:1')
        assert [len(batch) for batch in calls] == [256, 2]
        assert result.file_count == 258 and not result.omissions
    finally:
        manager.cleanup(workspace)
        manager.close()


def test_bounded_scancode_vcs_budget_records_all_26_ignored_paths(tmp_path: Path, monkeypatch) -> None:
    from app.ingestion.git_materializer import materialize_bounded_git_tree
    from app.ingestion.git_runner import _SCANCODE_VCS_IGNORED_PARTS
    from app.ingestion.inventory import build_inventory
    ignored_paths = [
        '.gitignore', '.gitattributes', 'one/.hgignore', 'two/.bzrignore',
        'three/.svnignore', 'four/.tfignore', 'five/vssver.scc', 'six/.cvsignore',
        'nested/CVS/payload', 'nested/_MTN/payload', 'nested/_darcs/payload',
        'nested/{arch}/payload', '.repo/item', '.bzr/item', '.svn/item', '.hg/item',
        *[f'pkg{i}/.GITIGNORE' for i in range(10)],
    ]
    assert len(ignored_paths) == 26
    source_files = {path: 'fixture' for path in ignored_paths}
    source_files.update({'README.md': 'example', 'requirements.txt': 'packaging==25.0'})
    repository = _repository(tmp_path / 'repo', source_files)
    runner = GitProcessRunner(Path(PYTHON), GitSafetyLimits(), bounded=True)
    fetched = []
    monkeypatch.setattr(runner, 'fetch_objects', lambda repository, ids, **kwargs: fetched.extend(ids))
    manager = WorkspaceManager(_private(tmp_path / 'work'), ZipSafetyLimits())
    workspace = manager.create()
    try:
        result = materialize_bounded_git_tree(runner, repository, workspace,
            home=_private(tmp_path / 'home'), limits=GitSafetyLimits(), deadline=time.monotonic() + 10,
            proxy_url='http://127.0.0.1:1')
        actual = {e.relative_path for e in build_inventory(workspace).entries}
        excluded = {e.path for e in result.omissions}
        assert len(actual & set(ignored_paths)) == 8
        assert len(excluded) == 18
        assert {e.reason for e in result.omissions} == {'bounded_scancode_vcs_budget'}
        assert actual.isdisjoint(excluded)
        assert actual | excluded == set(source_files)
        assert all(any(part.lower() in _SCANCODE_VCS_IGNORED_PARTS for part in path.split('/')) for path in excluded)
    finally:
        manager.cleanup(workspace)
        manager.close()


def test_bounded_three_vcs_files_remain_fully_scanned(tmp_path: Path, monkeypatch) -> None:
    from app.ingestion.git_materializer import materialize_bounded_git_tree
    repository = _repository(tmp_path / 'repo', {
        '.gitignore': 'fixture', '.inline-snapshot/external/.gitignore': 'fixture',
        'api_reference/.gitattributes': 'fixture', 'requirements.txt': 'packaging==25.0'})
    runner = GitProcessRunner(Path(PYTHON), GitSafetyLimits(), bounded=True)
    monkeypatch.setattr(runner, 'fetch_objects', lambda *args, **kwargs: None)
    manager = WorkspaceManager(_private(tmp_path / 'work'), ZipSafetyLimits())
    workspace = manager.create()
    try:
        result = materialize_bounded_git_tree(runner, repository, workspace,
            home=_private(tmp_path / 'home'), limits=GitSafetyLimits(), deadline=time.monotonic() + 10,
            proxy_url='http://127.0.0.1:1')
        assert result.file_count == 4 and not result.omissions
    finally:
        manager.cleanup(workspace)
        manager.close()
