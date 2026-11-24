"""Local launcher contracts. The process test serves only an isolated loopback copy."""

import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from deployment import launcher


ROOT = Path(__file__).resolve().parents[3]
LOCAL = "http://127.0.0.1:11434"
DOCKER = "http://host.docker.internal:11434"
FLAGS = ("OPENGUARD_CONTAINER_MODE", "OPENGUARD_OLLAMA_DOCKER_HOST")


@pytest.fixture(autouse=True)
def default_environment(monkeypatch):
    for key in (*FLAGS, "OPENGUARD_PYTHON"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(("container", "docker"), [
    ("", "0"), ("true", "0"), (" 1", "0"), ("0", "1"),
    ("1", ""), ("1", "yes"), ("1", "1 "),
])
def test_invalid_flags_fail_before_check(monkeypatch, capsys, container, docker):
    for key, value in zip(FLAGS, (container, docker), strict=True):
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(launcher, "check", lambda: pytest.fail("invalid flags reached check"))
    assert launcher.main(["check"]) == 2
    assert "ERROR:" in capsys.readouterr().err


@pytest.mark.parametrize(("container", "host", "status"), [
    ("0", "127.0.0.1", 0), ("0", "0.0.0.0", 2), ("0", "localhost", 2),
    ("1", "127.0.0.1", 0), ("1", "0.0.0.0", 0), ("1", "::", 2), ("1", "192.0.2.1", 2),
])
def test_host_allowlist_before_serve(monkeypatch, container, host, status):
    monkeypatch.setenv(FLAGS[0], container)
    calls = []

    def serve(port, model_origin, *, host):
        calls.append((port, model_origin, host))

    monkeypatch.setattr(launcher, "serve", serve)
    assert launcher.main(["serve", "--port", "8000", "--host", host]) == status
    assert calls == ([(8000, LOCAL, host)] if status == 0 else [])


@pytest.mark.parametrize(("container", "docker", "origin", "allowed"), [
    ("0", "0", LOCAL, True), ("0", "0", DOCKER, False),
    ("1", "0", DOCKER, False), ("1", "1", DOCKER, True), ("1", "1", LOCAL, True),
    ("1", "1", DOCKER + "/", False), ("1", "1", DOCKER + "?x=1", False),
    ("1", "1", "http://host.docker.internal:11435", False),
    ("1", "1", "http://host.docker.internal.example:11434", False),
    ("0", "0", "http://127.0.0.1:11435", False),
])
def test_literal_model_origin(monkeypatch, container, docker, origin, allowed):
    for key, value in zip(FLAGS, (container, docker), strict=True):
        monkeypatch.setenv(key, value)
    if allowed:
        assert launcher.parse_origin(origin).geturl() == origin
    else:
        with pytest.raises((ValueError, RuntimeError)):
            launcher.parse_origin(origin)


def test_network_guard_limits_the_resolved_docker_alias(monkeypatch):
    for key in FLAGS:
        monkeypatch.setenv(key, "1")
    lookups = []
    hooks = []

    def resolver(host, port, *_args, **_kwargs):
        lookups.append((host, port))
        assert (host, port) == ("host.docker.internal", 11434)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.17.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    monkeypatch.setattr(sys, "addaudithook", hooks.append)
    launcher.install_network_guard(DOCKER)
    assert lookups == [("host.docker.internal", 11434)]
    assert len(hooks) == 1
    hook = hooks[0]
    hook("socket.getaddrinfo", ("host.docker.internal", 11434, 0, 0, 0))
    hook("socket.connect", (None, ("172.17.0.1", 11434)))
    hook("socket.connect", (None, ("127.0.0.1", 11434)))
    for host, port in [
        ("host.docker.internal", 11435), ("example.invalid", 11434),
        ("other.docker.internal", 11434), ("172.17.0.2", 11434),
    ]:
        with pytest.raises(PermissionError):
            hook("socket.connect", (None, (host, port)))
    with pytest.raises(PermissionError):
        hook("socket.getaddrinfo", ("example.invalid", 11434, 0, 0, 0))


@pytest.mark.parametrize("origin", [LOCAL, DOCKER])
def test_runtime_reinjects_only_effective_docker_permission(monkeypatch, tmp_path, origin):
    monkeypatch.setattr(os, "environ", {key: "1" for key in FLAGS} | {"OPENGUARD_UNEXPECTED": "x"})
    monkeypatch.setattr(launcher, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples/http-server.bundle").touch()
    monkeypatch.setattr(launcher, "sample_report", lambda: [{"match": True}])
    launcher.configure_runtime(origin)
    assert os.environ[FLAGS[0]] == "1"
    assert os.environ[FLAGS[1]] == ("1" if origin == DOCKER else "0")
    assert os.environ["OPENGUARD_ASSISTANT_ORIGIN"] == origin
    assert os.environ["OPENGUARD_ENABLE_AI"] == "0"
    assert "OPENGUARD_UNEXPECTED" not in os.environ


@pytest.mark.parametrize(("docker_host", "origin", "host"), [
    ("0", LOCAL, "127.0.0.1"), ("1", DOCKER, "host.docker.internal"),
])
def test_explicit_model_services_share_the_configured_endpoint(monkeypatch, tmp_path, docker_host, origin, host):
    from app.assistant import service as assistant
    from app.p2 import ai_analysis as analysis

    monkeypatch.setenv("OPENGUARD_P2_DATA_SCOPE", "TEST_ONLY")
    monkeypatch.setenv("OPENGUARD_ASSISTANT_LOCK_PATH", str(tmp_path / "model.lock"))
    monkeypatch.setenv("OPENGUARD_ENABLE_ASSISTANT", "1")
    monkeypatch.setenv("OPENGUARD_ASSISTANT_ORIGIN", origin)
    monkeypatch.setenv("OPENGUARD_CONTAINER_MODE", docker_host)
    monkeypatch.setenv("OPENGUARD_OLLAMA_DOCKER_HOST", docker_host)
    monkeypatch.setattr(assistant.AssistantStore, "initialize", lambda _self: None)
    monkeypatch.setattr(analysis.AnalysisStore, "initialize", lambda _self: None)
    p2 = SimpleNamespace(data_scope="TEST_ONLY", store=SimpleNamespace(path=tmp_path / "p2.db"))
    actual = {}
    monkeypatch.setattr(assistant, "AssistantService", lambda _store, provider, *_args: actual.update(assistant=provider))
    monkeypatch.setattr(analysis, "P2AnalysisService", lambda _p2, _store, provider, **_kwargs: actual.update(p2=provider))
    assistant.configured_service(tmp_path)
    analysis.configured_service(p2, str(tmp_path / "budget.json"))
    assert (actual["assistant"].host, actual["assistant"].port) == (host, 11434)
    assert actual["p2"].transport._origin == origin
    assert actual["p2"].model_calls == 0


def test_public_docker_alias_resolution_fails_closed(monkeypatch):
    for key in FLAGS:
        monkeypatch.setenv(key, "1")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.1", 11434)),
    ])
    monkeypatch.setattr(sys, "addaudithook", lambda *_: pytest.fail("public alias installed a socket guard"))
    with pytest.raises(RuntimeError):
        launcher.install_network_guard(DOCKER)


def test_docker_model_check_uses_only_provider_identity_gets(monkeypatch, capsys):
    from app.ai import OllamaProvider

    for key in FLAGS:
        monkeypatch.setenv(key, "1")
    calls = []
    monkeypatch.setattr(launcher, "install_network_guard", lambda origin: calls.append(("guard", origin)))

    def response(self, path, *, deadline, limit):
        calls.append((self._origin, path))
        return {
            "/api/version": {"version": launcher.OLLAMA_VERSION},
            "/api/tags": {"models": [{"name": launcher.MODEL_NAME, "digest": launcher.MODEL_MANIFEST}]},
        }[path]

    monkeypatch.setattr(OllamaProvider, "_request_json", response)
    assert launcher.model_check(DOCKER) == 0
    assert calls == [("guard", DOCKER), (DOCKER, "/api/version"), (DOCKER, "/api/tags")]
    assert json.loads(capsys.readouterr().out)["generation_requests"] == 0


def test_runtime_python_honors_absolute_locked_override(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "RUNTIME", tmp_path / "runtime")
    for key, value in zip(FLAGS, ("1", "0"), strict=True):
        monkeypatch.setenv(key, value)
    exe = tmp_path / "preinstalled" / "bin" / "python"
    exe.parent.mkdir(parents=True)
    exe.touch(mode=0o700)
    monkeypatch.setenv("OPENGUARD_PYTHON", str(exe))
    monkeypatch.setattr(launcher, "dependency_report", lambda path: {"ready": Path(path) == exe})
    assert launcher.runtime_python() == exe


def test_runtime_python_rejects_unlocked_and_relative_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "RUNTIME", tmp_path / "runtime")
    exe = tmp_path / "python"
    exe.touch(mode=0o700)
    monkeypatch.setattr(launcher, "dependency_report", lambda _path: {"ready": False})
    for path in ("python", str(exe)):
        monkeypatch.setenv("OPENGUARD_PYTHON", path)
        with pytest.raises((ValueError, RuntimeError)):
            launcher.runtime_python()


@pytest.mark.parametrize(("implementation", "is_ready"), [("cpython", True), ("pypy", False)])
def test_locked_interpreter_report_requires_cpython(monkeypatch, implementation, is_ready):
    lock = {"pytest": "8.4.2"}
    monkeypatch.setattr(launcher, "pins", lambda: lock)
    response = {
        "python": "/isolated/python", "version": [3, 12, 14], "implementation": implementation,
        "packages": {name: {"expected": value, "actual": value, "match": True} for name, value in lock.items()},
    }
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps(response)))
    assert launcher.dependency_report(Path(response["python"]))["ready"] is is_ready


def test_runtime_python_preserves_package_venv_priority(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "RUNTIME", tmp_path)
    existing = tmp_path / "venv/bin/python"
    existing.parent.mkdir(parents=True)
    existing.touch(mode=0o700)
    monkeypatch.setenv("OPENGUARD_PYTHON", "invalid-override")
    assert launcher.runtime_python() == existing


@pytest.mark.parametrize(("candidates", "chosen"), [
    ({"runtime": True, "override": True, "python3.12": True, "python3": True}, "runtime"),
    ({"override": True, "python3.12": True, "python3": True}, "override"),
    ({"python3.12": True, "python3": True}, "python3.12"),
    ({"python3.12": False, "python3": True}, "python3"),
    ({"python3": False}, None),
])
def test_posix_launcher_order_and_argv(tmp_path, candidates, chosen):
    shutil.copy2(ROOT / "start.sh", tmp_path / "start.sh")
    bins = tmp_path / "bin"
    bins.mkdir()
    (bins / "dirname").symlink_to("/usr/bin/dirname")
    env = {"PATH": str(bins)}
    for name, detectable in candidates.items():
        path = {
            "runtime": tmp_path / "runtime/venv/bin/python",
            "override": tmp_path / "explicit/bin/python",
        }.get(name, bins / name)
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = 0 if detectable else 1
        path.write_text(
            '#!/bin/sh\n'
            f'if [ "${{1:-}}" = "-c" ] || [ "${{2:-}}" = "-c" ]; then exit {probe}; fi\n'
            f'printf "%s\\n" "{name}" "$@"\n'
        )
        path.chmod(0o700)
        if name == "override":
            env["OPENGUARD_PYTHON"] = str(path)
    shell = ["/bin/sh"]
    syntax = subprocess.run(shell + ["-n", "start.sh"], cwd=tmp_path, env=env, capture_output=True, timeout=5)
    assert syntax.returncode == 0, syntax.stderr
    reply = subprocess.run(
        shell + ["start.sh", "--port", "0", "--a-value", "space kept"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=5,
    )
    if chosen is None:
        assert reply.returncode == 2 and "3.12" in reply.stderr
    else:
        assert reply.returncode == 0, reply.stderr
        assert reply.stdout.splitlines() == [
            chosen, "-B", "openguard.py", "start", "--port", "0", "--a-value", "space kept",
        ]


def test_sigterm_preserves_isolated_data_and_exits_zero(tmp_path):
    copy = tmp_path / "package"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "node_modules", "runtime", "evidence",
    ))
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENGUARD_")}
    with (tmp_path / "server.log").open("w+") as log:
        server = subprocess.Popen(
            [sys.executable, "-B", str(copy / "openguard.py"), "serve", "--port", "0"],
            cwd=copy, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
        )
        try:
            ready = copy / "runtime/SERVER.json"
            deadline = time.monotonic() + 20
            report = None
            while report is None and time.monotonic() < deadline:
                if server.poll() is not None:
                    break
                if ready.is_file():
                    try:
                        info = json.loads(ready.read_text())
                        assert info["host"] == "127.0.0.1" and info["pid"] == server.pid
                        conn = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=1)
                        try:
                            conn.request("GET", "/healthz")
                            response = conn.getresponse()
                            assert response.status == 200
                            report = json.loads(response.read())
                        finally:
                            conn.close()
                    except (OSError, ValueError):
                        pass
                if report is None:
                    time.sleep(0.05)
            log.seek(0)
            assert report and report["status"] == "ok", log.read()
            marker = copy / "runtime/test-only-keep"
            marker.write_bytes(b"preserved")
            server.send_signal(signal.SIGTERM)
            assert server.wait(timeout=10) == 0
            assert marker.read_bytes() == b"preserved"
        finally:
            if server.poll() is None:
                server.kill()
                server.wait(timeout=5)
