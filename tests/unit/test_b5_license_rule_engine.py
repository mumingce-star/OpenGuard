"""B5 YAML-data-driven license obligation regression tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.models import (
    Component,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    LicenseExpression,
    ProducerRef,
    ProducerType,
    VerificationStatus,
)
from app.rules import evaluate, load_ruleset


_NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)
_EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174000"
_LICENSE_ID = "lic_123e4567-e89b-12d3-a456-426614174000"
_COMPONENT_ID = "cmp_123e4567-e89b-12d3-a456-426614174000"


def _evidence(status: VerificationStatus = VerificationStatus.VERIFIED) -> Evidence:
    return Evidence(
        id=_EVIDENCE_ID, kind=EvidenceKind.LICENSE_TEXT, locator="LICENSE", excerpt="fixture license text",
        detected_by=DetectionMethod.SCANCODE,
        producer=ProducerRef(type=ProducerType.SCANNER, name="fixture", version="1"),
        observed_at=_NOW, verification_status=status,
    )


def _license(identifier: str, status: VerificationStatus = VerificationStatus.VERIFIED) -> LicenseExpression:
    return LicenseExpression(
        id=_LICENSE_ID, expression=identifier, normalized_ids=[identifier], evidence_ids=[_EVIDENCE_ID],
        confidence=1.0, verification_status=status,
    )


def _component() -> Component:
    return Component(
        id=_COMPONENT_ID, name="fixture", version="1", ecosystem="npm", purl="pkg:npm/fixture@1",
        license_expression_id=_LICENSE_ID, evidence_ids=[_EVIDENCE_ID],
        detected_by=[DetectionMethod.MANIFEST_PARSER], confidence=1.0,
    )


@pytest.mark.parametrize("case", json.loads((Path(__file__).parents[1] / "fixtures" / "license-rules" / "cases.json").read_text(encoding="utf-8"))["verified_cases"])
def test_each_rule_fixture_produces_evidence_gated_review(case: dict[str, str]) -> None:
    result = evaluate(_component(), _license(case["license_id"]), [_evidence()])
    assert len(result.obligations) == len(result.findings) == len(result.remediations) == 1
    assert result.findings[0].rule_id == case["expected_rule"]
    assert result.findings[0].outcome.value == "review_required"
    assert result.findings[0].severity.value == case["expected_severity"]
    assert result.findings[0].evidence_ids == [_EVIDENCE_ID]
    assert result.obligations[0].verification_status is VerificationStatus.PENDING


def test_pending_license_is_not_promoted_to_license_rule() -> None:
    result = evaluate(_component(), _license("MIT", VerificationStatus.PENDING), [_evidence(VerificationStatus.PENDING)])
    assert not result.obligations and not result.remediations
    assert result.findings[0].rule_id == "license-evidence-gate"
    assert result.findings[0].outcome.value == "review_required"


def test_unknown_license_and_missing_evidence_stay_unknown() -> None:
    result = evaluate(_component(), _license("LicenseRef-Internal"), [])
    assert not result.obligations and not result.remediations
    assert result.findings[0].outcome.value == "unknown"
    assert not result.findings[0].evidence_ids


def test_ruleset_rejects_non_data_document(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text('{"ruleset_version":"1","rules":[],"include":"other.yaml"}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid ruleset document"):
        load_ruleset(invalid)


def test_result_is_deterministic() -> None:
    first = evaluate(_component(), _license("MIT"), [_evidence()])
    second = evaluate(_component(), _license("MIT"), [_evidence()])
    assert first == second
