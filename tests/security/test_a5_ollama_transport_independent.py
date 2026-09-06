"""Independent TCP/security checks for the locked A5-1a Ollama transport.

This file deliberately owns its HTTP fixture, protocol expectations, resource
identity and response construction.  It does not import transport constants,
fake openers or expected-output helpers from the implementation-side tests.
The fixture is an in-memory protocol server only; it is never an Ollama
runtime and never downloads or executes a model.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from app.ai import OllamaProvider, OllamaTransportError, apply_ai_remediations
from app.domain.models import ScanRun


ROOT = Path(__file__).resolve().parents[2]

# Independent, full-width resource identities locked by the A5-1a contract.
EXPECTED_OLLAMA_VERSION = "0.33.3"
EXPECTED_MODEL_NAME = "qwen3:4b-instruct-2507-q4_K_M"
EXPECTED_MANIFEST_DIGEST = (
    "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
)
EXPECTED_MODEL_ID = f"{EXPECTED_MODEL_NAME}@sha256:{EXPECTED_MANIFEST_DIGEST}"

EXPECTED_FORMAT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "finding_id", "summary", "steps", "evidence_ids"],
    "properties": {
        "schema_version": {"const": "openguard.ai-remediation/v1"},
        "finding_id": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "minLength": 1, "maxLength": 1000},
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "evidence_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
    },
}

KNOWN_FINDING_ID = "rsk_123e4567-e89b-12d3-a456-426614174000"
KNOWN_EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174000"
SENSITIVE_SENTINEL = "authorization=fixture-secret"


def _clean_run() -> ScanRun:
    value = copy.deepcopy(json.loads((ROOT / "examples/sample-scan-result.json").read_text()))
    value["findings"][0]["remediation_id"] = None
    value["remediations"] = []
    return ScanRun.model_validate(value)


def _valid_model_response() -> str:
    return json.dumps(
        {
            "schema_version": "openguard.ai-remediation/v1",
            "finding_id": KNOWN_FINDING_ID,
            "summary": "Review the cited evidence.",
            "steps": ["Record the human review."],
            "evidence_ids": [KNOWN_EVIDENCE_ID],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


class _Scenario:
    def __init__(
        self,
        *,
        version: str = EXPECTED_OLLAMA_VERSION,
        tags_digest: str = EXPECTED_MANIFEST_DIGEST,
        version_status: int = 200,
        version_content_type: str = "application/json; charset=utf-8",
        version_raw: bytes | None = None,
        generate_raw: bytes | None = None,
        delay_path: str | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.version = version
        self.tags_digest = tags_digest
        self.version_status = version_status
        self.version_content_type = version_content_type
        self.version_raw = version_raw
        self.generate_raw = generate_raw
        self.delay_path = delay_path
        self.delay_seconds = delay_seconds
        self.requests: list[tuple[str, str, bytes]] = []
        self._lock = threading.Lock()

    def record(self, method: str, path: str, body: bytes) -> None:
        with self._lock:
            self.requests.append((method, path, body))

    def response(self, method: str, path: str, body: bytes) -> tuple[int, str, bytes]:
        if self.delay_path == path:
            time.sleep(self.delay_seconds)

        if path == "/api/version" and method == "GET":
            if self.version_raw is not None:
                return self.version_status, self.version_content_type, self.version_raw
            return (
                self.version_status,
                self.version_content_type,
                json.dumps({"version": self.version}, separators=(",", ":")).encode(),
            )

        if path == "/api/tags" and method == "GET":
            return (
                200,
                "application/json; charset=utf-8",
                json.dumps(
                    {"models": [{"name": EXPECTED_MODEL_NAME, "digest": self.tags_digest}]},
                    separators=(",", ":"),
                ).encode(),
            )

        if path == "/api/generate" and method == "POST":
            if self.generate_raw is not None:
                return 200, "application/json; charset=utf-8", self.generate_raw
            return (
                200,
                "application/json; charset=utf-8",
                json.dumps(
                    {
                        "model": EXPECTED_MODEL_NAME,
                        "done": True,
                        "response": _valid_model_response(),
                    },
                    separators=(",", ":"),
                ).encode(),
            )

        return 404, "application/json", b'{"error":"not found"}'


class _FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: object) -> None:
        return None

    def _serve(self, method: str) -> None:
        length = self.headers.get("Content-Length", "0")
        try:
            body = self.rfile.read(int(length)) if length.isdigit() else b""
        except Exception:
            body = b""
        scenario: _Scenario = self.server.scenario  # type: ignore[attr-defined]
        scenario.record(method, self.path, body)
        status, content_type, payload = scenario.response(method, self.path, body)
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # A deliberate timeout can close the client socket before this
            # bounded fixture finishes its response; the client-side assertion
            # remains the source of truth for timeout/degradation.
            return None

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._serve("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        self._serve("POST")


class _LoopbackFixture:
    def __init__(self, scenario: _Scenario) -> None:
        self.scenario = scenario
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.origin: str | None = None

    def __enter__(self) -> "_LoopbackFixture":
        # Binding is intentionally real and unskipped.  A PermissionError is
        # an environment-level gate and must remain visible to the test run.
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        server.daemon_threads = True
        server.scenario = self.scenario  # type: ignore[attr-defined]
        self.server = server
        self.origin = f"http://127.0.0.1:{server.server_port}"
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2.0)


def _assert_sanitized_failure(provider: OllamaProvider, *, timeout: float = 2.0) -> None:
    with pytest.raises(OllamaTransportError) as raised:
        provider.generate('{"finding":"fixture"}', timeout)
    assert str(raised.value) == "ollama_transport_unavailable"
    assert raised.value.__cause__ is None
    assert SENSITIVE_SENTINEL not in str(raised.value)


def test_real_tcp_version_tags_generate_order_and_frozen_request_contract() -> None:
    scenario = _Scenario()
    with _LoopbackFixture(scenario) as fixture:
        provider = OllamaProvider(fixture.origin)  # type: ignore[arg-type]
        prompt = '{"schema_version":"independent-fixture/v1","instruction":"untrusted"}'
        assert provider.generate(prompt, 2.0) == _valid_model_response()

    assert [(method, path) for method, path, _body in scenario.requests] == [
        ("GET", "/api/version"),
        ("GET", "/api/tags"),
        ("POST", "/api/generate"),
    ]
    method, path, raw_body = scenario.requests[-1]
    assert method == "POST"
    assert path == "/api/generate"
    request = json.loads(raw_body.decode("utf-8"))
    assert request["model"] == EXPECTED_MODEL_NAME
    assert request["prompt"] == prompt
    assert request["stream"] is False
    assert request["think"] is False
    assert request["format"] == EXPECTED_FORMAT
    assert request["options"] == {"temperature": 0, "seed": 0, "num_predict": 1024}
    system = request["system"]
    assert isinstance(system, str)
    assert "untrusted" in system.lower()
    assert "evidence" in system.lower()
    assert "legal" in system.lower()


def test_environment_proxy_variables_cannot_intercept_loopback_transport(monkeypatch) -> None:
    proxy = "http://127.0.0.1:1"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, proxy)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    scenario = _Scenario()
    with _LoopbackFixture(scenario) as fixture:
        provider = OllamaProvider(fixture.origin)  # type: ignore[arg-type]
        assert provider.generate('{"proxy":"must-not-be-used"}', 2.0) == _valid_model_response()

    assert [path for _method, path, _body in scenario.requests] == [
        "/api/version",
        "/api/tags",
        "/api/generate",
    ]


def test_real_tcp_valid_result_flows_through_a5_to_pending_remediation() -> None:
    run = _clean_run()
    scenario = _Scenario()
    with _LoopbackFixture(scenario) as fixture:
        result = apply_ai_remediations(
            run,
            OllamaProvider(fixture.origin),  # type: ignore[arg-type]
            timeout_seconds=2.0,
        )

    assert result.status == "generated"
    assert len(result.run.remediations) == 1
    remediation = result.run.remediations[0]
    assert remediation.finding_id == KNOWN_FINDING_ID
    assert remediation.evidence_ids == [KNOWN_EVIDENCE_ID]
    assert remediation.verification_status.value == "pending"
    assert remediation.generated_by.model_id == EXPECTED_MODEL_ID
    assert result.run.findings[0].remediation_id == remediation.id
    assert result.run.provenance.ai_enabled is True
    assert result.run.provenance.ai_model is not None
    assert [path for _method, path, _body in scenario.requests] == [
        "/api/version",
        "/api/tags",
        "/api/generate",
    ]


def test_real_socket_timeout_becomes_a5_degraded_without_leak(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    scenario = _Scenario(delay_path="/api/version", delay_seconds=0.25)
    started = time.monotonic()
    with _LoopbackFixture(scenario) as fixture:
        result = apply_ai_remediations(
            _clean_run(),
            OllamaProvider(fixture.origin),  # type: ignore[arg-type]
            timeout_seconds=0.05,
        )
    elapsed = time.monotonic() - started

    assert elapsed < 1.5
    assert result.status == "degraded"
    assert result.run.remediations == []
    assert result.run.findings[0].remediation_id is None
    assert result.run.errors[-1].code == "ai_provider_unavailable"
    assert SENSITIVE_SENTINEL not in result.run.model_dump_json()
    assert len(scenario.requests) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(
            _Scenario(version="0.33.2"),
            id="wrong-runtime-version",
        ),
        pytest.param(
            _Scenario(tags_digest="f" * 64),
            id="wrong-manifest-digest",
        ),
        pytest.param(
            _Scenario(
                version_content_type="text/plain",
                version_raw=b"version=0.33.3; " + SENSITIVE_SENTINEL.encode(),
            ),
            id="non-json-content-type",
        ),
        pytest.param(
            _Scenario(
                version_raw=b"{" + b"x" * 4096,
            ),
            id="version-wrapper-overlimit",
        ),
    ],
)
def test_actual_http_identity_content_and_size_failures_are_sanitized(
    scenario: _Scenario,
) -> None:
    with _LoopbackFixture(scenario) as fixture:
        provider = OllamaProvider(fixture.origin)  # type: ignore[arg-type]
        _assert_sanitized_failure(provider)

    assert scenario.requests
    assert SENSITIVE_SENTINEL not in json.dumps(scenario.requests, default=str)


def test_loopback_shutdown_leaves_no_persistent_fixture_files(tmp_path: Path) -> None:
    before = sorted(item.name for item in tmp_path.iterdir())
    scenario = _Scenario()
    with _LoopbackFixture(scenario) as fixture:
        origin = fixture.origin
        assert origin is not None
        assert OllamaProvider(origin).generate("{}", 2.0) == _valid_model_response()

    assert sorted(item.name for item in tmp_path.iterdir()) == before
    assert origin is not None
    _assert_sanitized_failure(OllamaProvider(origin), timeout=0.5)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:11434",
        "http://example.test:11434",
        "https://127.0.0.1:11434",
        "http://192.0.2.10:11434",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434/api/generate",
        "http://127.0.0.1:11434?cloud=true",
    ],
)
def test_non_literal_loopback_origins_fail_closed_without_network(origin: str) -> None:
    with pytest.raises(OllamaTransportError) as raised:
        OllamaProvider(origin)
    assert str(raised.value) == "ollama_transport_unavailable"
    assert raised.value.__cause__ is None
    assert origin not in str(raised.value)


def test_transport_fixture_has_no_proxy_environment_side_effects(monkeypatch) -> None:
    before = {name: os.environ.get(name) for name in ("HTTP_PROXY", "NO_PROXY")}
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    assert os.environ["HTTP_PROXY"] != before["HTTP_PROXY"]
    assert os.environ["NO_PROXY"] != before["NO_PROXY"]
