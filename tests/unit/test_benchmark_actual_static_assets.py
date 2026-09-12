from __future__ import annotations

import json
from pathlib import Path

from benchmarks.evaluate import evaluate_scan_result
from benchmarks.run_static_assets import write_result


ROOT = Path(__file__).resolve().parents[2]
CASE_FILE = ROOT / "benchmarks" / "cases" / "static-ai-assets-v1.json"


def test_static_asset_benchmark_uses_generated_scanner_output(tmp_path: Path) -> None:
    """Metrics must be calculated from detector output, not fixture predictions."""
    result_path = tmp_path / "actual.json"
    result = write_result(CASE_FILE, result_path)
    metrics = evaluate_scan_result(result_path)

    assert result["scanner"] == "openguard-static-ai-detector/0.1.2"
    assert [case["id"] for case in result["cases"]] == [
        "model-huggingface", "dataset-huggingface", "api-openai",
        "model-modelscope", "negative-generic-url",
    ]
    assert result["cases"][1]["predicted"] == ["dataset:huggingface:acme/demo-dataset"]
    assert all(evidence["locator"] for case in result["cases"] for evidence in case["evidence"])
    assert metrics["version"] == "0.1.0"
    assert metrics["case_count"] == 5
    assert metrics["metrics"] == {
        "true_positive": 4,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }


def test_generated_result_is_json_serializable(tmp_path: Path) -> None:
    result_path = tmp_path / "actual.json"
    write_result(CASE_FILE, result_path)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["version"] == "0.1.0"
    assert payload["cases"][4]["assets"] == []


def test_metrics_report_missed_and_spurious_labels():
    from benchmarks.evaluate import evaluate_cases
    metrics = evaluate_cases([
        {"id": "positive", "expected": ["model:a", "dataset:b"], "predicted": ["model:a", "api:c"]},
        {"id": "negative", "expected": [], "predicted": ["model:d"]},
    ])["metrics"]
    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 2
    assert metrics["false_negative"] == 1
    assert metrics["precision"] == 1 / 3 and metrics["recall"] == 1 / 2
    assert metrics["f1"] == 0.4


def test_result_versions_and_hash_are_bound_to_actual_sources(tmp_path):
    import hashlib
    result = write_result(CASE_FILE, tmp_path / "actual.json")
    assert result["case_sha256"] == hashlib.sha256(CASE_FILE.read_bytes()).hexdigest()
    assert {e["producer"]["name"] + "/" + e["producer"]["version"] for c in result["cases"] for e in c["evidence"]} == {result["scanner"]}


def test_predictions_do_not_follow_modified_expected_labels(tmp_path):
    case = json.loads(CASE_FILE.read_text())
    for item in case["cases"]:
        item["expected"] = ["unrelated:label"]
    path = tmp_path / "changed-expectations.json"
    path.write_text(json.dumps(case))
    original = write_result(CASE_FILE, tmp_path / "original.json")
    changed = write_result(path, tmp_path / "changed.json")
    assert [c["predicted"] for c in original["cases"]] == [c["predicted"] for c in changed["cases"]]
    assert evaluate_scan_result(tmp_path / "changed.json")["metrics"]["true_positive"] == 0
