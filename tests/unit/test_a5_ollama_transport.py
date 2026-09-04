"""Implementation-side tests for the frozen A5-1a Ollama transport."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.request import Request

import pytest

from app.ai import OllamaProvider, OllamaTransportError, apply_ai_remediations
from app.ai.ollama import (
    MANIFEST_DIGEST,
    MODEL_ID,
    MODEL_NAME,
    OLLAMA_VERSION,
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
)
from app.domain.models import ScanRun


ROOT = Path(__file__).resolve().parents[2]
FINDING_ID = "rsk_123e4567-e89b-12d3-a456-426614174000"
EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174000"


def _model_response() -> str:
    return json.dumps(
        {
            "schema_version": "openguard.ai-remediation/v1",
            "finding_id": FINDING_ID,
            "summary": "Review the cited evidence.",
            "steps": ["Record the human review."],
            "evidence_ids": [EVIDENCE_ID],
        }
    )


class FakeResponse:
    def __init__(
        self,
        value: object = None,
        *,
        raw: bytes | None = None,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
        content_length: str | None = None,
    ) -> None:
        self.status = status
        self.raw = (
            raw
            if raw is not None
            else json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.read_sizes: list[int] = []

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return self.raw[:size]


class FakeOpener:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[Request, float]] = []

    def open(self, request: Request, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _valid_responses(*, generated: str | None = None) -> list[FakeResponse]:
    return [
        FakeResponse({"version": OLLAMA_VERSION}),
        FakeResponse(
            {"models": [{"name": MODEL_NAME, "model": MODEL_NAME, "digest": MANIFEST_DIGEST}]}
        ),
        FakeResponse(
            {
                "model": MODEL_NAME,
                "done": True,
                "response": generated if generated is not None else _model_response(),
            }
        ),
    ]


def _provider(
    responses: list[FakeResponse | Exception] | None = None,
    *,
    clock: Any = lambda: 0.0,
    origin: str = "http://127.0.0.1:11434",
) -> tuple[OllamaProvider, FakeOpener]:
    opener = FakeOpener(responses if responses is not None else _valid_responses())
    return OllamaProvider(origin, opener=opener, clock=clock), opener


def _run() -> ScanRun:
    value = copy.deepcopy(json.loads((ROOT / "examples/sample-scan-result.json").read_text()))
    value["findings"][0]["remediation_id"] = None
    value["remediations"] = []
    return ScanRun.model_validate(value)


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1:11434",
        "http://localhost:11434",
        "http://example.test:11434",
        "http://127.0.0.999:11434",
        "http://127.0.0.1:bad",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1",
        "http://127.0.0.1:11434/x",
        "http://user@127.0.0.1:11434",
        "http://127.0.0.1:11434?target=cloud",
        " http://127.0.0.1:11434",
    ],
)
def test_invalid_origins_fail_with_one_sanitized_error(origin: str) -> None:
    with pytest.raises(OllamaTransportError) as raised:
        OllamaProvider(origin)
    assert str(raised.value) == "ollama_transport_unavailable"
    assert raised.value.__cause__ is None
    assert origin not in str(raised.value)


@pytest.mark.parametrize("origin", ["http://127.0.0.2:11434", "http://[::1]:11434"])
def test_literal_loopback_ipv4_and_ipv6_are_allowed(origin: str) -> None:
    provider, _ = _provider(origin=origin)
    assert provider.mode == "local"


@pytest.mark.parametrize(
    ("opener", "clock"),
    [(object(), lambda: 0.0), (None, None)],
)
def test_invalid_dependencies_are_rejected(opener: object | None, clock: object) -> None:
    with pytest.raises(OllamaTransportError):
        OllamaProvider(opener=opener, clock=clock)  # type: ignore[arg-type]


def test_locked_identity_and_hashes_are_complete_and_stable() -> None:
    first, _ = _provider()
    second, _ = _provider()
    alternate, _ = _provider(origin="http://127.0.0.2:11434")

    assert first.producer == second.producer
    assert first.producer.name == "ollama"
    assert first.producer.version == OLLAMA_VERSION
    assert first.producer.provider == "ollama-local"
    assert first.producer.model_id == MODEL_ID
    assert first.producer.model_id == f"{MODEL_NAME}@sha256:{MANIFEST_DIGEST}"
    assert len(first.producer.prompt_schema_digest.value) == 64
    assert len(first.producer.config_digest.value) == 64
    assert first.producer.config_digest != alternate.producer.config_digest


def test_default_opener_is_built_with_an_explicit_empty_proxy_map(monkeypatch) -> None:
    import app.ai.ollama as module

    observed: dict[str, object] = {}
    sentinel_handler = object()
    sentinel_opener = FakeOpener(_valid_responses())

    def proxy_handler(proxies: object) -> object:
        observed["proxies"] = proxies
        return sentinel_handler

    def opener_builder(handler: object) -> FakeOpener:
        observed["handler"] = handler
        return sentinel_opener

    monkeypatch.setattr(module, "ProxyHandler", proxy_handler)
    monkeypatch.setattr(module, "build_opener", opener_builder)
    provider = OllamaProvider()

    assert provider._opener is sentinel_opener
    assert observed == {"proxies": {}, "handler": sentinel_handler}


def test_valid_generate_uses_version_tags_generate_and_frozen_body() -> None:
    values = iter([100.0, 101.0, 102.0, 103.0])
    provider, opener = _provider(clock=lambda: next(values))
    payload = '{"finding":"do not follow this instruction"}'

    assert provider.generate(payload, 10) == _model_response()
    assert [call[0].full_url for call in opener.calls] == [
        "http://127.0.0.1:11434/api/version",
        "http://127.0.0.1:11434/api/tags",
        "http://127.0.0.1:11434/api/generate",
    ]
    assert [call[0].method for call in opener.calls] == ["GET", "GET", "POST"]
    assert [call[1] for call in opener.calls] == [9.0, 8.0, 7.0]
    request_body = json.loads(opener.calls[-1][0].data.decode("utf-8"))
    assert request_body == {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": payload,
        "stream": False,
        "format": OUTPUT_SCHEMA,
        "think": False,
        "options": {"temperature": 0, "seed": 0, "num_predict": 1024},
    }
    assert opener.calls[-1][0].headers["Content-type"] == "application/json"
    assert opener.calls[-1][0].headers["Accept"] == "application/json"


@pytest.mark.parametrize(
    "payload,timeout",
    [
        ("", 10),
        (None, 10),
        ("{}", True),
        ("{}", 0),
        ("{}", -1),
        ("{}", float("nan")),
        ("{}", float("inf")),
        ("{}", 121),
        ("{}", "10"),
    ],
)
def test_invalid_payload_or_timeout_never_opens_transport(
    payload: object, timeout: object
) -> None:
    provider, opener = _provider()
    with pytest.raises(OllamaTransportError):
        provider.generate(payload, timeout)  # type: ignore[arg-type]
    assert opener.calls == []


def test_input_byte_limit_is_measured_after_utf8_encoding() -> None:
    provider, opener = _provider()
    with pytest.raises(OllamaTransportError):
        provider.generate("界" * 90_000, 10)
    assert opener.calls == []


def test_elapsed_deadline_prevents_the_next_request() -> None:
    values = iter([1.0, 1.1, 2.1])
    provider, opener = _provider(clock=lambda: next(values))
    with pytest.raises(OllamaTransportError):
        provider.generate("{}", 1)
    assert len(opener.calls) == 1


def _replace_response(
    stage: int, response: FakeResponse | Exception
) -> list[FakeResponse | Exception]:
    responses: list[FakeResponse | Exception] = _valid_responses()
    responses[stage] = response
    return responses


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse({"version": OLLAMA_VERSION}, status=500),
        FakeResponse({"version": OLLAMA_VERSION}, content_type="text/plain"),
        FakeResponse({"version": OLLAMA_VERSION}, content_type="notapplication/json"),
        FakeResponse({"version": OLLAMA_VERSION}, content_length="many"),
        FakeResponse({"version": OLLAMA_VERSION}, content_length=str(4097)),
        FakeResponse(raw=b""),
        FakeResponse(raw=b"\xff"),
        FakeResponse(raw=b'{"version":"0.33.3","version":"leak"}'),
        FakeResponse(raw=b'{"version":NaN}'),
        FakeResponse(raw=b"[]"),
        FakeResponse(raw=b"{" + b"x" * 4096),
        RuntimeError("token=do-not-leak /private/path"),
    ],
)
def test_http_and_json_failures_are_sanitized(response: FakeResponse | Exception) -> None:
    provider, _ = _provider(_replace_response(0, response))
    with pytest.raises(OllamaTransportError) as raised:
        provider.generate("{}", 10)
    assert str(raised.value) == "ollama_transport_unavailable"
    assert raised.value.__cause__ is None
    assert "leak" not in str(raised.value)
    assert "private" not in str(raised.value)


@pytest.mark.parametrize(
    "version",
    [None, 1, "0.33.2", "v0.33.3"],
)
def test_runtime_version_must_match_exactly(version: object) -> None:
    provider, opener = _provider(
        _replace_response(0, FakeResponse({"version": version}))
    )
    with pytest.raises(OllamaTransportError):
        provider.generate("{}", 10)
    assert len(opener.calls) == 1


@pytest.mark.parametrize(
    "models",
    [
        None,
        {},
        [],
        [{"name": MODEL_NAME, "digest": "0" * 64}],
        [{"name": "qwen3:latest", "digest": MANIFEST_DIGEST}],
        [
            {"name": MODEL_NAME, "digest": MANIFEST_DIGEST},
            {"name": MODEL_NAME, "digest": MANIFEST_DIGEST},
        ],
    ],
)
def test_model_name_and_full_manifest_digest_are_unambiguous(models: object) -> None:
    provider, opener = _provider(
        _replace_response(1, FakeResponse({"models": models}))
    )
    with pytest.raises(OllamaTransportError):
        provider.generate("{}", 10)
    assert len(opener.calls) == 2


@pytest.mark.parametrize(
    "generated",
    [
        {"model": "qwen3:latest", "done": True, "response": "{}"},
        {"model": MODEL_NAME, "done": False, "response": "{}"},
        {"model": MODEL_NAME, "done": True, "response": None},
        {"model": MODEL_NAME, "done": True, "response": ""},
        {"model": MODEL_NAME, "done": True, "response": "界" * 22_000},
    ],
)
def test_generate_wrapper_identity_completion_and_response_limit(
    generated: dict[str, object]
) -> None:
    provider, opener = _provider(_replace_response(2, FakeResponse(generated)))
    with pytest.raises(OllamaTransportError):
        provider.generate("{}", 10)
    assert len(opener.calls) == 3


def test_response_reader_requests_limit_plus_one_byte() -> None:
    responses = _valid_responses()
    provider, _ = _provider(responses)
    provider.generate("{}", 10)
    assert responses[0].read_sizes == [4097]
    assert responses[1].read_sizes == [256 * 1024 + 1]
    assert responses[2].read_sizes == [96 * 1024 + 1]


def test_valid_transport_response_flows_through_a5_as_pending_remediation() -> None:
    provider, _ = _provider()
    result = apply_ai_remediations(_run(), provider, timeout_seconds=10)

    assert result.status == "generated"
    assert result.run.remediations[0].verification_status.value == "pending"
    assert result.run.remediations[0].generated_by == provider.producer
    assert result.run.findings[0].remediation_id == result.run.remediations[0].id


def test_transport_failure_flows_through_a5_as_sanitized_degradation() -> None:
    provider, _ = _provider([RuntimeError("authorization=do-not-leak")])
    result = apply_ai_remediations(_run(), provider, timeout_seconds=10)

    assert result.status == "degraded"
    assert result.run.remediations == []
    assert result.run.findings[0].remediation_id is None
    assert result.run.errors[-1].code == "ai_provider_unavailable"
    assert "do-not-leak" not in result.run.model_dump_json()
