"""B01 ModelScope offline metadata adapter and cross-source observation contract."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata
from app.scanners.huggingface_metadata import HuggingFaceMetadataParser
from app.scanners.modelscope_metadata import ModelScopeMetadataParser


def _modelscope(payload: object) -> TemporaryMetadata:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    source = SourceDescriptor(
        provider="modelscope", resource_kind="model", repository_id="acme/demo-model",
        requested_revision=None, revision_mode="default_observation", resolved_revision=None,
        revision_locator=None, version_status="bounded_content_revision_unconfirmed",
        source_url="https://modelscope.cn/api/v1/models/acme/demo-model",
        fetched_at="2026-09-27T00:00:00Z", content_type="application/json",
        body_size=len(body), body_sha256=hashlib.sha256(body).hexdigest(),
        transport_version="modelscope-metadata-transport/1",
    )
    return TemporaryMetadata(source, body)


def _parse_modelscope(payload: object):
    temporary = _modelscope(payload)
    return ModelScopeMetadataParser().parse(
        provider="modelscope", resource_kind="model", resource_identity="acme/demo-model",
        temporary_metadata=temporary, source_descriptor=temporary.source,
    )


def _fields(value):
    return {field.name: field.value for field in value.fields}


def test_modelscope_adapter_exposes_only_pending_observations() -> None:
    result = _parse_modelscope({"Code": 200, "Success": True, "Data": {
        "Namespace": "acme", "Name": "demo-model", "License": "Apache-2.0",
        "Visibility": "public", "Gated": False, "Revision": "master",
        "LastUpdatedTime": "2026-09-20T00:00:00Z",
        "authorization_status": "approved", "secret_like": "must-not-escape",
    }})

    fields = _fields(result)
    assert result.parser_version == "openguard-modelscope-metadata/1"
    assert result.verification_status == "pending"
    assert {field.verification_status for field in result.fields} == {"pending"}
    assert fields == {
        "canonical_id": "acme/demo-model", "revision_hint": "master",
        "last_modified": "2026-09-20T00:00:00Z", "visibility": "public",
        "access_gate": "ungated", "declared_license_raw": "Apache-2.0",
    }
    serialized = result.model_dump_json()
    assert "authorization_status" not in serialized
    assert "must-not-escape" not in serialized
    assert "Apache-2.0" in serialized  # provider declaration, not a license conclusion
    assert "metadata_revision_unavailable" in result.coverage_gaps


@pytest.mark.parametrize("payload,gap", [
    ({"Code": 200, "Success": True, "Data": {"Namespace": "acme", "Name": "demo-model", "License": []}}, "unsupported_declared_license_value"),
    ({"Code": 200, "Success": True, "Data": {"Namespace": "acme", "Name": "demo-model", "Visibility": 5}}, "unsupported_visibility_value"),
    ({"Code": 200, "Success": True, "Data": {"Namespace": "acme", "Name": "demo-model", "Gated": "false"}}, "unsupported_gate_value"),
])
def test_modelscope_exceptional_optional_metadata_stays_pending(payload: dict, gap: str) -> None:
    result = _parse_modelscope(payload)
    assert result.verification_status == "pending"
    assert gap in result.coverage_gaps
    assert "authorization_status" not in _fields(result)
    assert "license_expression_id" not in _fields(result)


@pytest.mark.parametrize("payload", [
    {"Code": 500, "Success": False, "Data": {"Namespace": "acme", "Name": "demo-model"}},
    {"Code": 200, "Success": True, "Data": {"Namespace": "acme", "Name": "other"}},
    {"Code": 200, "Success": True, "Data": {"Namespace": "../acme", "Name": "demo-model"}},
])
def test_modelscope_exceptional_envelope_or_identity_fails_closed(payload: dict) -> None:
    with pytest.raises(ValueError, match="metadata_invalid"):
        _parse_modelscope(payload)


def test_modelscope_duplicate_json_key_and_descriptor_tampering_fail_closed() -> None:
    temporary = _modelscope({"Code": 200, "Success": True, "Data": {"Namespace": "acme", "Name": "demo-model"}})
    duplicate = b'{"Code":200,"Code":200,"Success":true,"Data":{"Namespace":"acme","Name":"demo-model"}}'
    descriptor = replace(temporary.source, body_size=len(duplicate), body_sha256=hashlib.sha256(duplicate).hexdigest())
    with pytest.raises(ValueError, match="metadata_invalid"):
        ModelScopeMetadataParser().parse(provider="modelscope", resource_kind="model", resource_identity="acme/demo-model",
            temporary_metadata=TemporaryMetadata(descriptor, duplicate), source_descriptor=descriptor)
    with pytest.raises(ValueError, match="metadata_invalid"):
        ModelScopeMetadataParser().parse(provider="modelscope", resource_kind="model", resource_identity="acme/demo-model",
            temporary_metadata=temporary, source_descriptor=replace(temporary.source, transport_version="hf-metadata-transport/1"))


def test_cross_source_contract_keeps_metadata_as_observation_not_a_conclusion() -> None:
    hf_payload = {"id": "acme/demo-model", "sha": "a" * 40, "private": False,
                  "gated": False, "disabled": False, "license": "Apache-2.0"}
    body = json.dumps(hf_payload, separators=(",", ":")).encode()
    hf_source = SourceDescriptor(
        provider="huggingface", resource_kind="model", repository_id="acme/demo-model",
        requested_revision=None, revision_mode="default_observation", resolved_revision="a" * 40,
        revision_locator="/sha", version_status="revision_observed",
        source_url="https://huggingface.co/api/models/acme/demo-model", fetched_at="2026-09-27T00:00:00Z",
        content_type="application/json", body_size=len(body), body_sha256=hashlib.sha256(body).hexdigest(),
    )
    hf = HuggingFaceMetadataParser().parse(provider="huggingface", resource_kind="model", resource_identity="acme/demo-model",
        temporary_metadata=TemporaryMetadata(hf_source, body), source_descriptor=hf_source)
    ms = _parse_modelscope({"Code": 200, "Success": True, "Data": {
        "Namespace": "acme", "Name": "demo-model", "License": "Apache-2.0", "Gated": False,
    }})

    for result in (hf, ms):
        fields = _fields(result)
        assert result.verification_status == "pending"
        assert fields["canonical_id"] == "acme/demo-model"
        assert fields["declared_license_raw"] == "Apache-2.0"
        assert "authorization_status" not in fields
        assert "license_expression_id" not in fields
