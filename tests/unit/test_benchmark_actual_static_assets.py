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

    assert result["scanner"] == "openguard-static-ai-detector/0.1.0"
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
