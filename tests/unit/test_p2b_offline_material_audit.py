"""Existing receipt accounting and synthetic text negatives, with no source admission."""
from copy import deepcopy
import hashlib
from pathlib import Path
import socket
import sqlite3

import pytest

from app.p2.contract import digest, strict_json
from app.p2b.candidates import USAGE_FIELDS
from app.p2b.offline_material_audit import CLAUSE_ANCHORS, audit_existing_material

ROOT = Path(__file__).resolve().parents[2]


def inputs(index=0):
    cases = strict_json((ROOT / "docs/p2/p2b-evidence-closure.json").read_bytes())["cases"]
    readback = strict_json((ROOT / "tests/fixtures/p2b/three-scan-readback.json").read_bytes())["cases"]
    return deepcopy(cases[index]), deepcopy(readback[index]["p2"]["after"])


def rehash(case, result):
    result["result_sha256"] = digest({k: v for k, v in result.items() if k != "result_sha256"})
    case["results"][-1]["result_sha256"] = result["result_sha256"]


def synthetic_bytes(text):
    # This is first-party synthetic text, never a replacement for upstream bytes.
    case, result = inputs()
    raw = text.encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    case["material"].update(source_sha256=sha, byte_count=len(raw))
    observation = next(x for x in case["fixed_tag_observations"] if x["role"] == "license_text")
    observation.update(raw_byte_sha256=sha, byte_count=len(raw),
                       git_blob_sha1=hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())
    return case, result, raw


@pytest.mark.parametrize("index", range(3))
def test_existing_observations_are_reused_and_unknown_values_preserved(index):
    case, result = inputs(index)
    before = deepcopy((case, result))
    audit = audit_existing_material(case, result_payload=result)
    assert (case, result) == before
    assert audit["usage"] == {key: None for key in USAGE_FIELDS}
    assert audit["new_facts"] == 0 and audit["new_evidence_ids"] == []
    assert audit["new_positive_license_advice"] == []
    assert audit["verification_state"] == "pending" and audit["formal_effect"] == "none"
    assert all(x["status"] == "bytes_not_re_read" for x in audit["clause_mapping"])
    assert "scan_coverage_incomplete" in audit["remaining_gaps"]
    assert {f"usage_{key}_unknown" for key in USAGE_FIELDS} <= set(audit["remaining_gaps"])


@pytest.mark.parametrize("field", USAGE_FIELDS)
def test_null_cannot_be_silently_changed_even_after_rehash(field):
    case, result = inputs()
    result["usage"][field] = True
    rehash(case, result)
    with pytest.raises(ValueError, match="existing_usage_pin_mismatch"):
        audit_existing_material(case, result_payload=result)


@pytest.mark.parametrize("version", ["6.0.0", "7.0.1", "latest", None])
def test_wrong_version_material_is_refused(version):
    case, result = inputs()
    case["material"]["subject"]["version"] = version
    with pytest.raises(ValueError, match="material_subject_mismatch"):
        audit_existing_material(case, result_payload=result)


@pytest.mark.parametrize("field", ["scan_id", "assessment_id", "facts_hash", "usage_hash"])
def test_material_parent_binding_cannot_be_reassigned(field):
    case, result = inputs()
    case["material"]["binding"][field] = "0" * 64
    with pytest.raises(ValueError, match="material_parent_binding_mismatch"):
        audit_existing_material(case, result_payload=result)


@pytest.mark.parametrize("field,value", [
    ("source_level", "upstream_verified"), ("verification_state", "verified"),
    ("formal_effect", "approved"), ("adoption_status", "officially_admitted"),
])
def test_upload_observation_cannot_promote_itself(field, value):
    case, result = inputs()
    case["material"][field] = value
    with pytest.raises(ValueError):
        audit_existing_material(case, result_payload=result)


def test_material_reference_cannot_be_removed_with_valid_result_digest():
    case, result = inputs()
    result["resources"][0]["material_ids"] = []
    rehash(case, result)
    with pytest.raises(ValueError, match="material_reference_closure_invalid"):
        audit_existing_material(case, result_payload=result)


def test_source_record_hash_is_not_a_substitute_for_byte_hash():
    case, result = inputs()
    case["material"]["source_sha256"] = digest(case["fixed_tag_observations"][0])
    with pytest.raises(ValueError, match="existing_observation_hash_mismatch"):
        audit_existing_material(case, result_payload=result)


def test_original_byte_mismatch_is_refused():
    case, result = inputs()
    with pytest.raises(ValueError, match="material_hash_mismatch"):
        audit_existing_material(case, result_payload=result, content=b"MIT License\n")


def test_synthetic_clause_locations_preserve_original_utf8_byte_offsets():
    text = "中文前缀\r\n" + "\r\n".join(CLAUSE_ANCHORS.values()) + "\r\n"
    case, result, raw = synthetic_bytes(text)
    audit = audit_existing_material(case, result_payload=result, content=raw)
    for row in audit["clause_mapping"]:
        assert row["status"] == "anchor_observed"
        locator = row["locators"][0]
        assert raw[locator["start_byte"]:locator["end_byte_exclusive"]].decode() == CLAUSE_ANCHORS[row["topic"]]
        assert locator["start_line"] == locator["end_line"]
    assert audit["scope_analysis"]["text_mapping_is_applicability_proof"] is False
    assert audit["new_positive_license_advice"] == []


@pytest.mark.parametrize("text,status", [
    ("MIT License\n", "anchor_missing"),
    (CLAUSE_ANCHORS["notice_retention"] + "\n" + CLAUSE_ANCHORS["notice_retention"], "anchor_ambiguous"),
])
def test_keyword_or_duplicate_clause_never_proves_scope_or_permission(text, status):
    case, result, raw = synthetic_bytes(text)
    audit = audit_existing_material(case, result_payload=result, content=raw)
    assert next(x for x in audit["clause_mapping"] if x["topic"] == "notice_retention")["status"] == status
    assert audit["new_facts"] == 0 and audit["new_positive_license_advice"] == []
    assert "owner_license_applicability_unconfirmed" in audit["remaining_gaps"]


def test_missing_clause_mapping_and_prior_observation_never_create_extra_facts(monkeypatch):
    case, result = inputs()
    def forbidden(*args, **kwargs):
        raise AssertionError("offline audit attempted network or database access")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    first = audit_existing_material(case, result_payload=result)
    assert first == audit_existing_material(case, result_payload=result)
    assert first["observation_accounting"] == "existing_unverified_observation_reused"


def test_supplied_git_blob_hash_is_checked_against_bytes():
    case, result, raw = synthetic_bytes("MIT License\n")
    next(x for x in case["fixed_tag_observations"] if x["role"] == "license_text")["git_blob_sha1"] = "0" * 40
    with pytest.raises(ValueError, match="existing_observation_byte_binding_mismatch"):
        audit_existing_material(case, result_payload=result, content=raw)
