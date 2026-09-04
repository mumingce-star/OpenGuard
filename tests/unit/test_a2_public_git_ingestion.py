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
    def __init__(self, root: Path, calls: list[str], *, failure: bool = False) -> None:
        self.root = root
        self.calls = calls
        self.failure = failure

    def ingest_with_consumer(self, source: str, consumer: object, *, read_limits: object) -> object:
        self.calls.append(source)
        if self.failure:
            raise IngestionSecurityError("invalid_source", "source_address_not_public")
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
        ingestion_factory=lambda root: _FakeGitIngestion(root, calls, failure=True),  # type: ignore[arg-type]
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
