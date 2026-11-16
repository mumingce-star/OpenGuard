"""Independent socket checks; these protocol fixtures never run a model."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading

import pytest

from app.ai import OllamaProvider, OllamaTransportError


ORIGIN = "http://host.docker.internal:11434"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
DIGEST = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
ANSWER = '{"fixture":"structured response"}'


@contextmanager
def server(*, redirect_path=None, redirect_status=302, location=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.command, self.path, self.headers.get("Host"), body))
            if self.path == redirect_path:
                self.send_response(redirect_status)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            values = {
                "/api/version": {"version": "0.33.3"},
                "/api/tags": {"models": [{"name": MODEL, "digest": DIGEST}]},
                "/api/generate": {"model": MODEL, "done": True, "response": ANSWER},
            }
            raw = json.dumps(values.get(self.path, {})).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield httpd.server_port, requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def map_docker_dns(monkeypatch, port):
    actual_resolver = socket.getaddrinfo
    lookups = []

    def resolve(host, requested_port, *args, **kwargs):
        lookups.append((host, requested_port))
        if host == "host.docker.internal" and requested_port == 11434:
            return actual_resolver("127.0.0.1", port, *args, **kwargs)
        return actual_resolver(host, requested_port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    return lookups


def test_explicit_docker_opt_in_uses_real_http_and_ignores_proxies(monkeypatch):
    with server() as (port, requests), server() as (proxy_port, proxy_requests):
        lookups = map_docker_dns(monkeypatch, port)
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            monkeypatch.setenv(key, f"http://127.0.0.1:{proxy_port}")
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "")
        with pytest.raises(OllamaTransportError, match="^ollama_transport_unavailable$"):
            OllamaProvider(ORIGIN)
        assert not requests and not lookups
        provider = OllamaProvider(ORIGIN, docker_host=True)
        assert provider.generate('{"input":"untrusted fixture"}', 3) == ANSWER
        assert [(method, path) for method, path, _, _ in requests] == [
            ("GET", "/api/version"), ("GET", "/api/tags"), ("POST", "/api/generate")
        ]
        assert all(host == "host.docker.internal:11434" for _, _, host, _ in requests)
        payload = json.loads(requests[-1][3])
        assert payload["model"] == MODEL
        assert payload["prompt"] == '{"input":"untrusted fixture"}'
        assert payload["stream"] is False and payload["think"] is False
        assert provider.producer.model_id == f"{MODEL}@sha256:{DIGEST}"
        assert not proxy_requests
        assert lookups == [("host.docker.internal", 11434)] * 3


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("path", ["/api/version", "/api/tags", "/api/generate"])
def test_redirects_never_contact_target(monkeypatch, status, path):
    with server() as (target_port, target_requests):
        with server(redirect_path=path, redirect_status=status,
                    location=f"http://127.0.0.1:{target_port}/leak") as (port, requests):
            map_docker_dns(monkeypatch, port)
            with pytest.raises(OllamaTransportError, match="^ollama_transport_unavailable$"):
                OllamaProvider(ORIGIN, docker_host=True).generate("private-facts", 3)
            assert requests[-1][1] == path
            assert not target_requests


@pytest.mark.parametrize("origin", [
    "http://host.docker.internal:11434/", "http://HOST.DOCKER.INTERNAL:11434",
    "http://host.docker.internal.:11434", "http://host.docker.internal:11435",
    "https://host.docker.internal:11434", "http://host.docker.internal",
    "http://host.docker.internal:11434/api/generate", "http://host.docker.internal:11434?x=1",
    "http://host.docker.internal:11434#fragment", "http://user@host.docker.internal:11434",
    "http://host.docker.internal.evil:11434", "http://127.0.0.1:11434",
    " http://host.docker.internal:11434", "http://host.docker.internal:11434\n",
])
def test_docker_opt_in_rejects_origin_variants_without_dns(monkeypatch, origin):
    def reject_resolution(*_args, **_kwargs):
        pytest.fail("invalid origin reached DNS")

    monkeypatch.setattr(socket, "getaddrinfo", reject_resolution)
    with pytest.raises(OllamaTransportError, match="^ollama_transport_unavailable$"):
        OllamaProvider(origin, docker_host=True)
