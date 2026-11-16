"""B02 derives only hash-bound review candidates from fixed B03/B04 facts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.detectors.license_notice_facts import canonical_facts_sha256


FACTS_PATH = Path("tests/fixtures/notice-license-facts-v2/facts.json")
MATRIX_PATH = Path("tests/fixtures/p1-integration-b-v1/candidate-matrix.json")
EXPECTED_PACKAGE_SHA256 = "9cdcb294c7e46ce57a2e3b4a92e5693439dbc6b82f15e138b61b6cc6df172577"


def _facts() -> dict:
    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _detect(value: dict, *, expected_hash: str = EXPECTED_PACKAGE_SHA256):
    from app.detectors.license_notice_facts import detect_license_notice_candidates

    return detect_license_notice_candidates(
        value,
        expected_package_sha256=expected_hash,
    )


def test_v2_facts_produce_stable_hash_bound_findings_without_legal_upgrade() -> None:
    value = _facts()
    result = _detect(value)

    assert len(result.findings) == 17
    assert result == _detect(_facts())
    assert result.source_package_sha256 == canonical_facts_sha256(value)
    assert result.obligations == ()
    assert [item.fact_id for item in result.findings] == sorted(item.fact_id for item in result.findings)
    assert {item.code for item in result.findings} >= {
        "GAP_ROOT_NOTICE_MISSING",
        "GAP_NOTICE_FILE_NOT_OBSERVED",
        "GAP_AI_LICENSE_TEXT_NOT_VERIFIED",
        "LICENSE_DECLARATION_UNVERIFIED",
    }
    assert all(item.status == "review_required" for item in result.findings)
    assert all(item.authorization_status == "pending" for item in result.findings)
    assert all(item.license_expression_id is None for item in result.findings)
    assert all(item.confirmed_violation is False for item in result.findings)
    assert all(item.source_fact_pointer.startswith("/facts/") for item in result.findings)
    assert all(len(item.source_fact_sha256) == 64 for item in result.findings)
    assert all(item.source_package_sha256 == result.source_package_sha256 for item in result.findings)
    assert {item.fact_id for item in result.findings if item.code == "LICENSE_DECLARATION_UNVERIFIED"} == {
        "fact.ai.gpt2",
        "fact.ai.bert",
        "fact.ai.imdb",
    }
    assert not {item.fact_id for item in result.findings} & {
        "fact.dep.jackson-databind",
        "fact.dep.springboot",
    }


def test_evidence_bindings_include_object_pointer_and_all_declared_hash_scopes() -> None:
    result = _detect(_facts())
    declaration = next(
        item for item in result.findings
        if item.fact_id == "fact.ai.gpt2" and item.code == "LICENSE_DECLARATION_UNVERIFIED"
    )

    assert len(declaration.evidence_bindings) == 1
    binding = declaration.evidence_bindings[0]
    assert binding.evidence_id == "ev.hf.gpt2.license"
    assert binding.evidence_pointer == "/evidence/7"
    assert binding.selected_json_pointer == "/payload/cardData/license"
    assert len(binding.source_file_sha256) == 64
    assert len(binding.selected_content_sha256) == 64
    assert binding.source_file_sha256 != binding.selected_content_sha256


def test_fixed_candidate_matrix_covers_positive_negative_false_positive_and_false_negative_guards() -> None:
    matrix = _matrix()
    result = _detect(_facts())
    actual: dict[str, list[dict[str, str]]] = {}
    for candidate in result.findings:
        actual.setdefault(candidate.fact_id, []).append(
            {"category": candidate.category, "code": candidate.code}
        )
        assert candidate.status == "review_required"
        assert candidate.authorization_status == "pending"
        assert candidate.license_expression_id is None
        assert candidate.confirmed_violation is False

    expected = matrix["expected_candidates_by_fact"]
    assert matrix["source_package_sha256"] == result.source_package_sha256
    assert set(expected) == {fact["fact_id"] for fact in _facts()["facts"]}
    assert {
        fact_id: sorted(items, key=lambda item: (item["category"], item["code"]))
        for fact_id, items in actual.items()
    } == {
        fact_id: sorted(items, key=lambda item: (item["category"], item["code"]))
        for fact_id, items in expected.items() if items
    }

    guards = matrix["false_positive_guards"]
    assert all(not actual.get(fact_id) for fact_id in guards["zero_candidate_facts"])
    assert not {candidate.category for candidate in result.findings} & set(guards["forbidden_candidate_categories"])
    assert all(candidate.confirmed_violation is not guards["forbidden_confirmed_violation"] for candidate in result.findings)
    assert {
        candidate.code for candidate in result.findings if candidate.code in guards["notice_gap_is_not_violation"]
    } == set(guards["notice_gap_is_not_violation"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("schema_version", "unexpected"),
        lambda value: value.__setitem__("unexpected", "not accepted"),
        lambda value: value["evidence"][0].__setitem__("unexpected", "not accepted"),
        lambda value: value["report_v2_rows"][0].__setitem__("unexpected", "not accepted"),
        lambda value: value["facts"][0].__setitem__("authorization_status", "verified"),
        lambda value: value["facts"][0]["license_observations"][0].__setitem__("license_expression_id", "Apache-2.0"),
        lambda value: value["facts"][0]["relationships"]["license"]["evidence_ids"].append("ev.missing"),
        lambda value: value["facts"][0].__setitem__("gaps", ["GAP_ROOT_NOTICE_MISSING", "GAP_ROOT_NOTICE_MISSING"]),
        lambda value: value["evidence"][0].__setitem__("selected_content_sha256", "0" * 63),
        lambda value: value["evidence"][7].__setitem__("selected_json_pointer", None),
        lambda value: value["policies"].__setitem__("gap_is_noncompliance", True),
    ],
)
def test_untrusted_unknown_or_upgraded_fact_input_fails_closed(mutate) -> None:
    from app.detectors.license_notice_facts import FactsDetectorInputError

    original = _facts()
    value = copy.deepcopy(original)
    mutate(value)
    with pytest.raises(FactsDetectorInputError, match="facts_detector_invalid"):
        _detect(value)


def test_well_formed_tampering_is_rejected_by_the_external_package_hash() -> None:
    from app.detectors.license_notice_facts import FactsDetectorInputError

    original = _facts()
    changed = copy.deepcopy(original)
    changed["evidence"][0]["selected_content_sha256"] = "0" * 64

    with pytest.raises(FactsDetectorInputError, match="facts_detector_invalid"):
        _detect(changed)
