"""B01 real Hugging Face metadata parser against fixed provider snapshots."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata
from app.p1.profile_models import ParsedMetadataObservation
from app.scanners.huggingface_metadata import HuggingFaceMetadataParser


FIXTURE_ROOT = Path("tests/fixtures/huggingface/resource-profile-v1")
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
V2_FIXTURE_ROOT = Path("tests/fixtures/huggingface/resource-profile-v2")
V2_MANIFEST = json.loads((V2_FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _temporary(snapshot: dict, *, payload: object | None = None) -> TemporaryMetadata:
    value = snapshot["payload"] if payload is None else payload
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    revision = value.get("sha") if isinstance(value, dict) else None
    source = SourceDescriptor(
        provider=snapshot["provider"],
        resource_kind=snapshot["resource_kind"],
        repository_id=value.get("id", "missing") if isinstance(value, dict) else "missing",
        requested_revision=None,
        revision_mode="default_observation",
        resolved_revision=revision,
        revision_locator="/sha" if revision else None,
        version_status="revision_observed" if revision else "bounded_content_revision_unconfirmed",
        source_url=(
            f"https://huggingface.co/api/{snapshot['resource_kind']}s/"
            f"{value.get('id', 'missing')}"
        ),
        fetched_at="2026-09-20T10:22:00Z",
        content_type="application/json",
        body_size=len(body),
        body_sha256=hashlib.sha256(body).hexdigest(),
    )
    return TemporaryMetadata(source, body)


def _parse(snapshot: dict) -> ParsedMetadataObservation:
    temporary = _temporary(snapshot)
    return HuggingFaceMetadataParser().parse(
        provider=snapshot["provider"],
        resource_kind=snapshot["resource_kind"],
        resource_identity=snapshot["payload"]["id"],
        temporary_metadata=temporary,
        source_descriptor=temporary.source,
    )


def _fields(result: ParsedMetadataObservation) -> dict[str, object]:
    return {field.name: field.value for field in result.fields}


@pytest.mark.parametrize("record", MANIFEST["records"], ids=lambda row: row["case_id"])
def test_fixed_real_snapshots_match_manifest(record: dict) -> None:
    path = FIXTURE_ROOT / record["fixture"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["source_file_sha256"]
    snapshot = json.loads(path.read_text(encoding="utf-8"))

    result = _parse(snapshot)
    fields = _fields(result)
    observed = record["observed"]

    assert result.parser_version == "openguard-huggingface-metadata/1"
    assert result.verification_status == "pending"
    assert fields["canonical_id"] == observed["canonical_id"]
    assert fields["revision"] == observed["revision"]
    assert fields["visibility"] == observed["visibility"]
    assert fields["access_gate"] == observed["gated"]
    assert fields["disabled"] == str(observed["disabled"]).lower()
    expected_license = observed["declared_license_raw"]
    if isinstance(expected_license, list):
        expected_license = json.dumps(expected_license, ensure_ascii=False, separators=(",", ":"))
    assert fields["declared_license_raw"] == expected_license
    assert result.coverage_gaps == []
    assert len(result.bounded_excerpt) <= 1_000


@pytest.mark.parametrize("case", MANIFEST["counterexamples"], ids=lambda row: row["case_id"])
def test_counterexamples_remain_pending_and_expose_gaps(case: dict) -> None:
    snapshot = json.loads((FIXTURE_ROOT / case["fixture"]).read_text(encoding="utf-8"))
    result = _parse(snapshot)
    fields = _fields(result)

    assert result.verification_status == "pending"
    assert "license_expression_id" not in fields
    assert "authorization_status" not in fields
    if case["case_id"] == "hf-missing-license-and-revision":
        assert "revision" not in fields
        assert "declared_license_raw" not in fields
        assert {"metadata_revision_unavailable", "declared_license_unavailable"} <= set(result.coverage_gaps)
    elif case["case_id"] == "hf-conflicting-declared-license":
        assert "declared_license_raw" not in fields
        assert fields["declared_license_top_level"] == "MIT"
        assert fields["declared_license_card"] == "Apache-2.0"
        assert "conflicting_declared_license" in result.coverage_gaps
    else:
        assert fields["declared_license_raw"] == "NOASSERTION"
        assert fields["access_gate"] == "unknown"
        assert "unsupported_gate_value" in result.coverage_gaps


@pytest.mark.parametrize(
    "fault",
    [
        "provider",
        "kind",
        "identity",
        "descriptor",
        "hash",
        "revision",
        "content_type",
        "replayable",
        "duplicate_key",
        "non_object",
        "invalid_utf8",
    ],
)
def test_binding_and_json_tampering_fails_closed(fault: str) -> None:
    snapshot = json.loads((FIXTURE_ROOT / MANIFEST["records"][0]["fixture"]).read_text(encoding="utf-8"))
    temporary = _temporary(snapshot)
    descriptor = temporary.source
    provider, kind, identity = descriptor.provider, descriptor.resource_kind, descriptor.repository_id

    if fault == "provider":
        provider = "other"
    elif fault == "kind":
        kind = "dataset"
    elif fault == "identity":
        identity = "other/resource"
    elif fault == "descriptor":
        descriptor = replace(descriptor, repository_id="other/resource")
    elif fault == "hash":
        descriptor = replace(descriptor, body_sha256="0" * 64)
    elif fault == "revision":
        descriptor = replace(descriptor, resolved_revision="0" * 40)
    elif fault == "content_type":
        descriptor = replace(descriptor, content_type="text/plain")
    elif fault == "replayable":
        descriptor = replace(descriptor, full_response_replay_available=True)
    elif fault in {"duplicate_key", "non_object", "invalid_utf8"}:
        body = {
            "duplicate_key": b'{"id":"a/b","id":"a/b"}',
            "non_object": b"[]",
            "invalid_utf8": b"\xff",
        }[fault]
        descriptor = replace(
            descriptor,
            body_size=len(body),
            body_sha256=hashlib.sha256(body).hexdigest(),
            resolved_revision=None,
            revision_locator=None,
            version_status="bounded_content_revision_unconfirmed",
        )
        temporary = TemporaryMetadata(descriptor, body)

    with pytest.raises(ValueError, match="metadata_invalid"):
        HuggingFaceMetadataParser().parse(
            provider=provider,
            resource_kind=kind,
            resource_identity=identity,
            temporary_metadata=temporary,
            source_descriptor=descriptor,
        )


def test_output_never_contains_complete_raw_response_or_unknown_fields() -> None:
    snapshot = json.loads((FIXTURE_ROOT / MANIFEST["records"][0]["fixture"]).read_text(encoding="utf-8"))
    snapshot["payload"]["unknown_secret_like_field"] = "RAW_SENTINEL_MUST_NOT_ESCAPE"
    temporary = _temporary(snapshot)
    result = HuggingFaceMetadataParser().parse(
        provider="huggingface",
        resource_kind="model",
        resource_identity=snapshot["payload"]["id"],
        temporary_metadata=temporary,
        source_descriptor=temporary.source,
    )

    encoded = result.model_dump_json()
    assert "RAW_SENTINEL_MUST_NOT_ESCAPE" not in encoded
    assert temporary.bounded_bytes().decode("utf-8") not in encoded
    assert len(result.fields) <= 10


def test_existing_parser_port_accepts_implementation_output() -> None:
    """The B01 implementation satisfies the existing A07 parser port unchanged."""
    from app.p1.profile_models import MetadataParser

    snapshot = json.loads((FIXTURE_ROOT / MANIFEST["records"][0]["fixture"]).read_text(encoding="utf-8"))
    temporary = _temporary(snapshot)
    parser: MetadataParser = HuggingFaceMetadataParser()
    observation = parser.parse(
        provider=temporary.source.provider,
        resource_kind=temporary.source.resource_kind,
        resource_identity=temporary.source.repository_id,
        temporary_metadata=temporary,
        source_descriptor=temporary.source,
    )

    assert type(observation) is ParsedMetadataObservation
    assert observation.parser_version == "openguard-huggingface-metadata/1"
    assert observation.verification_status == "pending"
    assert {field.name for field in observation.fields} >= {
        "canonical_id",
        "revision",
        "declared_license_raw",
    }


@pytest.mark.parametrize("record", V2_MANIFEST["records"], ids=lambda row: row["case_id"])
def test_v2_fixed_snapshots_extend_model_dataset_coverage(record: dict) -> None:
    path = V2_FIXTURE_ROOT / record["fixture"]
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert source_hash == record["source_file_sha256"]
    assert source_hash == record["source_observation_sha256"]
    snapshot = json.loads(path.read_text(encoding="utf-8"))

    result = _parse(snapshot)
    fields = _fields(result)
    observed = record["observed"]
    expected_license = observed["declared_license_raw"]
    if isinstance(expected_license, list):
        expected_license = json.dumps(expected_license, ensure_ascii=False, separators=(",", ":"))

    assert result.verification_status == "pending"
    assert fields["canonical_id"] == observed["canonical_id"]
    assert fields["revision"] == observed["revision"]
    assert fields["declared_license_raw"] == expected_license
    assert fields["access_gate"] == observed["access_gate"]
    assert "authorization_status" not in fields
    assert "license_expression_id" not in fields


def test_v2_fixture_contract_has_exactly_five_models_and_five_datasets() -> None:
    kinds = [record["resource_kind"] for record in V2_MANIFEST["records"]]
    assert kinds.count("model") == 5
    assert kinds.count("dataset") == 5


def test_v2_illegal_input_fixture_fails_closed_without_a_conclusion() -> None:
    case = next(case for case in V2_MANIFEST["counterexamples"] if case["case_id"] == "hf-illegal-identity")
    path = V2_FIXTURE_ROOT / case["fixture"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case["source_file_sha256"]
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    temporary = _temporary(snapshot)

    with pytest.raises(ValueError, match=case["expected_error"]):
        HuggingFaceMetadataParser().parse(
            provider="huggingface",
            resource_kind="model",
            resource_identity=snapshot["payload"]["id"],
            temporary_metadata=temporary,
            source_descriptor=temporary.source,
        )


@pytest.mark.parametrize(
    "case",
    [case for case in V2_MANIFEST["counterexamples"] if "expected_gaps" in case],
    ids=lambda row: row["case_id"],
)
def test_v2_counterexamples_preserve_gaps_without_raw_leakage(case: dict) -> None:
    path = V2_FIXTURE_ROOT / case["fixture"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case["source_file_sha256"]
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    raw = path.read_text(encoding="utf-8")

    result = _parse(snapshot)
    fields = _fields(result)
    assert result.verification_status == "pending"
    assert set(case["expected_gaps"]) <= set(result.coverage_gaps)
    assert raw not in result.model_dump_json()
    assert "authorization_status" not in fields
    assert "license_expression_id" not in fields
