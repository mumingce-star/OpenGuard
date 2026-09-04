from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.detectors import detect_ai_assets
from app.domain.models import DetectionMethod, Evidence, EvidenceKind, ProducerRef, ProducerType, VerificationStatus
from app.licenses import normalize_license
from app.rules.engine import load_ruleset
from benchmarks.evaluate import evaluate_file


def _evidence(status: VerificationStatus = VerificationStatus.VERIFIED) -> Evidence:
    return Evidence(
        id="evd_123e4567-e89b-12d3-a456-426614174000", kind=EvidenceKind.LICENSE_TEXT,
        locator="LICENSE", detected_by=DetectionMethod.MANUAL,
        producer=ProducerRef(type=ProducerType.HUMAN, name="reviewer", version="1"),
        observed_at=datetime(2026, 9, 5, tzinfo=timezone.utc), verification_status=status,
    )


def test_b4_normalizes_alias_and_compound_expression() -> None:
    license_expression = normalize_license("mit OR Apache License 2.0", [_evidence()])
    assert license_expression.expression == "MIT OR Apache-2.0"
    assert license_expression.normalized_ids == ["Apache-2.0", "MIT"]
    assert license_expression.verification_status is VerificationStatus.VERIFIED


def test_b4_keeps_unknown_license_pending() -> None:
    license_expression = normalize_license("Internal-Proprietary", [_evidence()])
    assert license_expression.normalized_ids == []
    assert license_expression.verification_status is VerificationStatus.PENDING


def test_b5_ruleset_covers_fifteen_explicit_license_families() -> None:
    ruleset = load_ruleset()
    assert len(ruleset.rules) == 15
    assert {"MIT", "Apache-2.0", "GPL-3.0-only", "AGPL-3.0-only", "Unlicense"}.issubset(
        {license_id for rule in ruleset.rules for license_id in rule.license_ids}
    )


def test_b6_static_detector_returns_pending_assets_with_evidence() -> None:
    assets, evidence = detect_ai_assets(
        {"src/client.py": "model='https://huggingface.co/acme/demo'\nclient = openai.responses.create()"},
        observed_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    assert {asset.asset_type.value for asset in assets} == {"model", "api"}
    assert all(asset.authorization_status is VerificationStatus.PENDING for asset in assets)
    assert len(evidence) == 2


def test_b7_smoke_benchmark_reports_raw_false_positive() -> None:
    result = evaluate_file(Path("benchmarks/cases/p0-smoke.json"))
    assert result["case_count"] == 3
    assert result["metrics"] == {"true_positive": 3, "false_positive": 1, "false_negative": 0, "precision": 0.75, "recall": 1.0, "f1": 0.8571428571428571}
