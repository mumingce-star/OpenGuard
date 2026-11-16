"""Independent B01 parser safety probes without network, paths, or persistence."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata
from app.scanners.huggingface_metadata import HuggingFaceMetadataParser


def _input(payload: dict) -> TemporaryMetadata:
    body = json.dumps(payload, separators=(",", ":")).encode()
    revision = payload.get("sha")
    source = SourceDescriptor(
        provider="huggingface",
        resource_kind="model",
        repository_id=payload["id"],
        requested_revision=revision,
        revision_mode="fixed",
        resolved_revision=revision,
        revision_locator="/sha",
        version_status="revision_observed",
        source_url=f"https://huggingface.co/api/models/{payload['id']}/revision/{revision}",
        fetched_at="2026-09-20T10:22:00Z",
        content_type="application/json",
        body_size=len(body),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    return TemporaryMetadata(source, body)


def test_parser_is_offline_deterministic_and_does_not_mutate_input(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "id": "org/model",
        "sha": "a" * 40,
        "private": False,
        "gated": False,
        "disabled": False,
        "cardData": {"license": "apache-2.0"},
    }
    temporary = _input(payload)
    original = temporary.bounded_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external capability")

    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    parser = HuggingFaceMetadataParser()
    kwargs = dict(
        provider="huggingface",
        resource_kind="model",
        resource_identity="org/model",
        temporary_metadata=temporary,
        source_descriptor=temporary.source,
    )
    assert parser.parse(**kwargs) == parser.parse(**kwargs)
    assert temporary.bounded_bytes() == original


@pytest.mark.parametrize(
    "payload,gap",
    [
        ({"id": "org/model", "sha": "a" * 40, "private": "false", "gated": False, "disabled": False}, "unsupported_private_value"),
        ({"id": "org/model", "sha": "a" * 40, "private": False, "gated": [], "disabled": False}, "unsupported_gate_value"),
        ({"id": "org/model", "sha": "a" * 40, "private": False, "gated": False, "disabled": 0}, "unsupported_disabled_value"),
        ({"id": "org/model", "sha": "a" * 40, "private": False, "gated": False, "disabled": False, "cardData": {"license": ["mit", 1]}}, "unsupported_declared_license_value"),
    ],
)
def test_unsupported_optional_values_are_pending_gaps(payload: dict, gap: str) -> None:
    temporary = _input(payload)
    result = HuggingFaceMetadataParser().parse(
        provider="huggingface",
        resource_kind="model",
        resource_identity="org/model",
        temporary_metadata=temporary,
        source_descriptor=temporary.source,
    )
    assert result.verification_status == "pending"
    assert gap in result.coverage_gaps


def test_mutated_temporary_body_is_rejected_against_descriptor() -> None:
    temporary = _input({
        "id": "org/model",
        "sha": "a" * 40,
        "private": False,
        "gated": False,
        "disabled": False,
    })
    changed = b'{"id":"org/model","sha":"' + b"a" * 40 + b'","private":true}'
    corrupted = TemporaryMetadata(temporary.source, changed)
    with pytest.raises(ValueError, match="metadata_invalid"):
        HuggingFaceMetadataParser().parse(
            provider="huggingface",
            resource_kind="model",
            resource_identity="org/model",
            temporary_metadata=corrupted,
            source_descriptor=temporary.source,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda descriptor: replace(descriptor, source_url="https://example.invalid/metadata"),
        lambda descriptor: replace(descriptor, fetched_at="2026-09-20T10:22:00+08:00"),
        lambda descriptor: replace(descriptor, fetched_at="not-a-timestamp"),
        lambda descriptor: replace(descriptor, body_sha256=descriptor.body_sha256.upper()),
        lambda descriptor: replace(descriptor, body_size=True),
    ],
)
def test_source_provenance_quality_failures_are_closed(mutate) -> None:
    temporary = _input({
        "id": "org/model", "sha": "a" * 40, "private": False, "gated": False, "disabled": False,
    })
    descriptor = mutate(temporary.source)
    with pytest.raises(ValueError, match="metadata_invalid"):
        HuggingFaceMetadataParser().parse(
            provider="huggingface",
            resource_kind="model",
            resource_identity="org/model",
            temporary_metadata=temporary,
            source_descriptor=descriptor,
        )


def test_symbolic_requested_revision_keeps_observed_commit_pending() -> None:
    payload = {
        "id": "org/model", "sha": "b" * 40, "private": False, "gated": False, "disabled": False,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    descriptor = SourceDescriptor(
        provider="huggingface", resource_kind="model", repository_id="org/model",
        requested_revision="main", revision_mode="symbolic", resolved_revision="b" * 40,
        revision_locator="/sha", version_status="revision_observed",
        source_url="https://huggingface.co/api/models/org/model/revision/main",
        fetched_at="2026-09-20T10:22:00Z", content_type="application/json",
        body_size=len(body), body_sha256=hashlib.sha256(body).hexdigest(),
    )
    result = HuggingFaceMetadataParser().parse(
        provider="huggingface", resource_kind="model", resource_identity="org/model",
        temporary_metadata=TemporaryMetadata(descriptor, body), source_descriptor=descriptor,
    )
    assert result.verification_status == "pending"
    assert {item.name: item.value for item in result.fields}["revision"] == "b" * 40
