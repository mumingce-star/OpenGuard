import json
from pathlib import Path

import pytest

from benchmarks.b06_error_analysis import validate_error_analysis


PATH = Path("benchmarks/b06/error-analysis.json")


def test_empty_pre_gold_analysis_cannot_claim_quality() -> None:
    assert validate_error_analysis(PATH) == {"formal_quality_claimed": False, "gold_frozen": False, "error_count": 0, "rule_change_count": 0}


def test_error_tiers_fp_reasons_and_unfrozen_holdout_gate(tmp_path: Path) -> None:
    value = json.loads(PATH.read_text(encoding="utf-8"))
    value["errors"] = [
        {"error_id": "err-fn-a", "kind": "FN", "tier": "A", "reason": "static_direct", "case_id": "case1"},
        {"error_id": "err-fp-sdk", "kind": "FP", "classification": "sdk_name_collision", "case_id": "case1"},
    ]
    value["rule_changes"] = [{"change_id": "chg1", "rule_version": "0.3.1", "resolved_fn_ids": ["err-fn-a"], "introduced_fp_ids": ["err-fp-sdk"], "holdout": {"status": "blocked_until_human_gold_freeze", "before": None, "after": None}}]
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert validate_error_analysis(path)["rule_change_count"] == 1
    value["rule_changes"][0]["holdout"]["after"] = {"f1": 1.0}
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="unfrozen holdout"):
        validate_error_analysis(path)


def test_rule_change_cannot_claim_unclassified_or_wrong_kind_errors(tmp_path: Path) -> None:
    value = json.loads(PATH.read_text(encoding="utf-8"))
    value["errors"] = [{"error_id": "err-fp", "kind": "FP", "classification": "invalid_url", "case_id": "case1"}]
    value["rule_changes"] = [{"change_id": "chg1", "rule_version": "0.3.1", "resolved_fn_ids": ["err-fp"], "introduced_fp_ids": [], "holdout": {"status": "blocked_until_human_gold_freeze", "before": None, "after": None}}]
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="bind classified FN/FP"):
        validate_error_analysis(path)
