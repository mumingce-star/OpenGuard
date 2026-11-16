"""Fixed-corpus acceptance for Detector 0.3 static entry points."""

from datetime import datetime, timezone

from app.detectors import detect_static_asset_candidates
from benchmarks.run_static_assets import run_case_file


def test_detector_03_fixed_bench_reports_metrics_and_classified_differences() -> None:
    result = run_case_file("benchmarks/cases/detector-03-static-assets.json")
    expected = set()
    predicted = set()
    for case in result["cases"]:
        expected.update((case["id"], label) for label in case["expected"])
        predicted.update((case["id"], label) for label in case["predicted"])
        assert case["error_analysis"] == {"false_negatives": [], "false_positives": []}

    tp, fp, fn = len(expected & predicted), len(predicted - expected), len(expected - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    assert (tp, fp, fn, precision, recall, f1) == (7, 0, 0, 1.0, 1.0, 1.0)
    assert result["scanner"] == "openguard-static-ai-detector/0.3.0"


def test_detector_03_candidates_are_evidence_bound_and_pending() -> None:
    result = run_case_file("benchmarks/cases/detector-03-static-assets.json")
    for case in result["cases"]:
        evidence_ids = {item["id"] for item in case["evidence"]}
        for asset in case["assets"]:
            assert asset["authorization_status"] == "pending"
            assert asset["evidence_ids"] and set(asset["evidence_ids"]) <= evidence_ids
            for evidence in case["evidence"]:
                assert evidence["producer"]["version"] == "0.3.0"
                assert evidence["content_hash"]["algorithm"] == "sha256"
                assert evidence["verification_status"] == "pending"


def test_detector_03_unified_candidate_view_keeps_review_gate_and_hash() -> None:
    candidates = detect_static_asset_candidates(
        {".env.example": "OPENAI_API_KEY=placeholder\n"},
        observed_at=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert (candidate.resource_type.value, candidate.provider, candidate.name) == ("api", "openai", "openai")
    assert candidate.locator == ".env.example"
    assert candidate.rule_version == "0.3.0"
    assert len(candidate.evidence_sha256) == 64
    assert candidate.review_status == "review_required"
    assert candidate.authorization_status.value == "pending"
