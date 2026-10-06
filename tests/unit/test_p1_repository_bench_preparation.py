import json
from pathlib import Path

import pytest

from benchmarks.p1_repository_bench import validate_preparation, validate_run_binding


MANIFEST = Path("benchmarks/p1-fixed-repositories/preparation.json")


def test_p1_preparation_has_25_retained_slots_and_at_least_five_holdouts() -> None:
    result = validate_preparation(MANIFEST)
    assert result["fixed_sample_count"] == 0
    assert result["holdout_count"] == 0
    assert result["retained_failed_sample_count"] == 0
    assert result["formal_quality_ready"] is False
    assert result["errors"] == []
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(payload["samples"]) == 25
    assert sum(row["split"] == "holdout" for row in payload["samples"]) == 7


def test_fixed_or_failed_samples_require_facts_and_failures_cannot_disappear(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["samples"][0] = {"sample_id": "p1repo01", "family_id": "pending01", "split": "train", "state": "failed", "source": {"url": "https://example.invalid/repo", "commit_sha": "a" * 40, "input_sha256": "b" * 64, "fetched_at": "2026-09-30T00:00:00Z", "license_declaration": "MIT"}}
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert {item["code"] for item in validate_preparation(path)["errors"]} == {"FAILED_SAMPLE_REASON_REQUIRED"}


def test_preparation_document_rejects_legacy_or_formal_quality_scope(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["scope"] = "0.1.0_formal_quality"
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid P1 repository bench manifest"):
        validate_preparation(path)


def test_every_actual_run_requires_detector_rule_config_and_input_binding() -> None:
    valid = {"run_id": "run_p1repo01", "detector_version": "0.3.0", "rule_version": "rules/1", "config_sha256": "a" * 64, "input_sha256": "b" * 64, "status": "failed"}
    validate_run_binding(valid)
    for key in ("detector_version", "rule_version", "config_sha256", "input_sha256"):
        missing = valid.copy()
        missing.pop(key)
        with pytest.raises(ValueError, match="invalid P1 benchmark run binding"):
            validate_run_binding(missing)
