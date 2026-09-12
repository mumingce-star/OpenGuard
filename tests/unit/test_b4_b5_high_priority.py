"""Regression tests for the high-priority B4/B5 integrity fixes."""

from __future__ import annotations

from datetime import datetime, timezone

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
from app.licenses import normalize_license
from app.rules import evaluate


_EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174010"
_MISSING_EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174011"


def _evidence() -> Evidence:
    return Evidence(
        id=_EVIDENCE_ID,
        kind=EvidenceKind.LICENSE_TEXT,
        locator="LICENSE",
        excerpt="fixture license text",
        detected_by=DetectionMethod.MANUAL,
        producer=ProducerRef(type=ProducerType.HUMAN, name="fixture-reviewer", version="1"),
        observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )


def _component(license_id: str) -> Component:
    return Component(
        id="cmp_123e4567-e89b-12d3-a456-426614174010",
        name="fixture",
        version="1",
        ecosystem="npm",
        purl="pkg:npm/fixture@1",
        license_expression_id=license_id,
        evidence_ids=[_EVIDENCE_ID],
        detected_by=[DetectionMethod.MANUAL],
        confidence=1.0,
    )


def _evaluate(text: str):
    evidence = _evidence()
    license_expression = normalize_license(text, [evidence])
    return license_expression, evaluate(_component(license_expression.id), license_expression, [evidence])


def test_or_requires_a_license_choice_instead_of_asserting_every_branch() -> None:
    _, result = _evaluate("MIT OR GPL-3.0-only")

    assert not result.obligations and not result.remediations
    assert [item.rule_id for item in result.findings] == ["license-choice-required"]
    assert result.findings[0].outcome.value == "review_required"


def test_and_evaluates_every_covered_branch() -> None:
    _, result = _evaluate("MIT AND GPL-3.0-only")

    assert {item.rule_id for item in result.findings} == {
        "LIC-MIT-NOTICE",
        "LIC-GPL-3.0-ONLY-COPYLEFT",
    }
    assert len(result.obligations) == len(result.remediations) == 2


def test_partial_and_coverage_is_reported_without_hiding_matched_rules() -> None:
    _, result = _evaluate("MIT AND CDDL-1.0")

    assert {item.rule_id for item in result.findings} == {
        "LIC-MIT-NOTICE",
        "license-rule-coverage",
    }
    coverage = next(item for item in result.findings if item.rule_id == "license-rule-coverage")
    assert "CDDL-1.0" in coverage.trigger


def test_agpl_rule_is_reachable_through_normalization() -> None:
    license_expression, result = _evaluate("AGPL-3.0-only")

    assert license_expression.normalized_ids == ["AGPL-3.0-only"]
    assert [item.rule_id for item in result.findings] == ["LIC-AGPL-3.0-ONLY-NETWORK"]


def test_missing_referenced_evidence_fails_closed() -> None:
    evidence = _evidence()
    license_expression = normalize_license("MIT", [evidence]).model_copy(
        update={"evidence_ids": [_EVIDENCE_ID, _MISSING_EVIDENCE_ID]}
    )
    result = evaluate(_component(license_expression.id), license_expression, [evidence])

    assert not result.obligations and not result.remediations
    assert [item.rule_id for item in result.findings] == ["license-evidence-integrity"]
    assert result.findings[0].outcome.value == "unknown"


def test_expression_and_normalized_ids_disagreement_fails_closed() -> None:
    evidence = _evidence()
    license_expression = LicenseExpression(
        id="lic_123e4567-e89b-12d3-a456-426614174010",
        expression="GPL-3.0-only",
        normalized_ids=["MIT"],
        evidence_ids=[_EVIDENCE_ID],
        confidence=1.0,
        verification_status=VerificationStatus.VERIFIED,
    )
    result = evaluate(_component(license_expression.id), license_expression, [evidence])

    assert not result.obligations and not result.remediations
    assert [item.rule_id for item in result.findings] == ["license-expression-integrity"]
    assert result.findings[0].outcome.value == "unknown"


def test_verified_unsupported_expression_remains_an_explicit_coverage_unknown() -> None:
    evidence = _evidence()
    license_expression = LicenseExpression(
        id="lic_123e4567-e89b-12d3-a456-426614174012",
        expression="LicenseRef-Internal",
        normalized_ids=[],
        evidence_ids=[_EVIDENCE_ID],
        confidence=1.0,
        verification_status=VerificationStatus.VERIFIED,
    )
    result = evaluate(_component(license_expression.id), license_expression, [evidence])

    assert not result.obligations and not result.remediations
    assert [item.rule_id for item in result.findings] == ["license-rule-coverage"]
    assert "LicenseRef-Internal" in result.findings[0].trigger
