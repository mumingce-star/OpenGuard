"""Offline Detector 0.3 contract cases; this is not a production Gold set."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.detectors import detect_ai_assets


_CASES = json.loads((Path(__file__).parents[1] / "fixtures" / "detector-0.3" / "cases.json").read_text("utf-8"))
_NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def test_fixture_is_non_gold_and_split_isolated() -> None:
    assert _CASES["schema"] == "openguard.detector-fixtures/0.3"
    assert _CASES["scope"] == "offline_non_gold"
    members: dict[str, set[str]] = {}
    for case in _CASES["cases"]:
        assert case["split"] in {"train", "dev", "holdout"}
        members.setdefault(case["family_id"], set()).add(case["split"])
    assert all(len(splits) == 1 for splits in members.values())
    assert {case["split"] for case in _CASES["cases"]} == {"train", "dev", "holdout"}


def test_every_fn_fp_taxonomy_case_has_a_deterministic_offline_fixture() -> None:
    labels = {case["taxonomy"] for case in _CASES["cases"]}
    assert {"FN-ABSENT", "FN-EVIDENCE", "FP-ATTRIBUTION", "FP-HALLUCINATED", "FP-OVERPRECISION", "FP-LEAKAGE"} <= labels
    for case in _CASES["cases"]:
        assets, _ = detect_ai_assets(case["files"], observed_at=_NOW)
        actual = sorted(f"{item.provider}:{item.name}" for item in assets if item.asset_type.value == "model")
        assert actual == case["expected_models"], case["id"]
        for item in assets:
            assert item.authorization_status.value == "pending"
            assert item.license_expression_id is None


def test_imports_are_not_candidates_but_calls_examples_and_explicit_config_are_distinguished() -> None:
    files = {
        "sdk_only.py": "from transformers import AutoModel\nfrom datasets import load_dataset\n",
        "runtime.py": "from transformers import AutoModel\nfrom datasets import load_dataset\nAutoModel.from_pretrained('org/runtime-model')\nload_dataset('org/runtime-dataset')\n",
        "README.md": "```python\nfrom transformers import AutoTokenizer\nAutoTokenizer.from_pretrained('org/example-model')\n```\n",
        "config.toml": "model_name_or_path = 'org/config-model'\ndataset_name = 'org/config-dataset'\n",
    }
    assets, evidence = detect_ai_assets(files, observed_at=_NOW)
    assert {(item.asset_type.value, item.name) for item in assets} == {
        ("model", "org/runtime-model"), ("dataset", "org/runtime-dataset"),
        ("model", "org/example-model"), ("model", "org/config-model"),
        ("dataset", "org/config-dataset"),
    }
    assert not any(item.locator == "sdk_only.py" for item in evidence)
    methods = {(item.locator, item.detected_by.value, item.kind.value) for item in evidence}
    assert ("runtime.py", "ast", "file") in methods
    assert ("README.md", "static_pattern", "file") in methods
    assert ("config.toml", "manifest_parser", "manifest_field") in methods


def test_json_toml_yaml_are_strict_and_hf_non_resource_routes_remain_excluded() -> None:
    assets, _ = detect_ai_assets({
        "a.json": '{"model_name_or_path":"org/json-model","dataset":"org/json-dataset"}',
        "b.yaml": "model_id: 'org/yaml-model'\ndataset_path: 'org/yaml-dataset'\n",
        "bad.json": '{"model":"org/first","model":"org/second"}',
        "README.md": "https://huggingface.co/docs/transformers https://huggingface.co/blog/x https://huggingface.co/papers/1",
    }, observed_at=_NOW)
    assert {(item.asset_type.value, item.name) for item in assets} == {
        ("model", "org/json-model"), ("dataset", "org/json-dataset"),
        ("model", "org/yaml-model"), ("dataset", "org/yaml-dataset"),
    }


def test_detector_input_prediction_result_and_version_are_frozen_together() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "detector-0.3"
    detector = json.loads((fixture_dir / "detector.json").read_text("utf-8"))
    source = json.loads((fixture_dir / "input.json").read_text("utf-8"))
    prediction = json.loads((fixture_dir / "prediction.json").read_text("utf-8"))
    result = json.loads((fixture_dir / "result.json").read_text("utf-8"))
    assert detector["detector"]["version"] == source["detector_version"] == prediction["detector_version"] == result["detector_version"] == "0.3.0"
    assert detector["execution_performed"] is False
    assert prediction["execution_status"] == result["result_status"] == "not_executed"
    assert prediction["formal_metrics_claimed"] is result["formal_metrics_claimed"] is False
    assert result["metrics"] is None


def test_versioned_manifest_hash_binds_every_artifact_and_dependency_edge() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "detector-0.3"
    manifest = json.loads((fixture_dir / "manifest.json").read_text("utf-8"))
    assert manifest["schema"] == "openguard.detector-artifact-manifest/1"
    assert manifest["scope"] == "offline_non_gold"
    assert manifest["detector"] == {"name": "static_ai_assets", "version": "0.3.0"}
    artifacts = {item["artifact_id"]: item for item in manifest["artifacts"]}
    assert set(artifacts) == {"cases", "detector", "input", "prediction", "result"}
    assert artifacts["result"]["depends_on"] == ["detector", "input", "prediction"]
    for artifact_id, artifact in artifacts.items():
        data = (fixture_dir / artifact["path"]).read_bytes()
        assert len(data) == artifact["size_bytes"], artifact_id
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"], artifact_id
        assert all(dependency in artifacts for dependency in artifact.get("depends_on", []))
        if artifact_id != "cases":
            payload = json.loads(data)
            assert payload["artifact_id"] == artifact_id
            refs = {reference["artifact_id"]: reference for reference in payload.get("references", [])}
            for dependency in artifact.get("depends_on", []):
                assert refs[dependency]["path"] == artifacts[dependency]["path"]
                assert refs[dependency]["sha256"] == artifacts[dependency]["sha256"]


def test_manifest_hash_gate_rejects_a_tampered_artifact_in_memory() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "detector-0.3"
    manifest = json.loads((fixture_dir / "manifest.json").read_text("utf-8"))
    prediction = next(item for item in manifest["artifacts"] if item["artifact_id"] == "prediction")
    original = (fixture_dir / prediction["path"]).read_bytes()
    assert hashlib.sha256(original + b"\n").hexdigest() != prediction["sha256"]


def test_p0_b02a_static_provider_matrix_has_typed_located_pending_evidence() -> None:
    files = {
        "README.md": "https://huggingface.co/org/hf-model\nhttps://modelscope.cn/models/org/ms-model\nopenai.responses anthropic.messages google.genai\n",
        "runtime.py": "from transformers import AutoModel\nfrom datasets import load_dataset\nAutoModel.from_pretrained('org/ast-model')\nload_dataset('org/ast-dataset')\n",
        "config.yaml": "model_name_or_path: 'org/config-model'\ndataset_name: 'org/config-dataset'\n",
    }
    assets, evidence = detect_ai_assets(files, observed_at=_NOW)
    assert {(item.asset_type.value, item.provider, item.name) for item in assets} == {
        ("model", "huggingface", "org/hf-model"),
        ("model", "modelscope", "org/ms-model"),
        ("api", "openai", "openai"), ("api", "anthropic", "anthropic"), ("api", "google", "google"),
        ("model", "huggingface", "org/ast-model"), ("dataset", "huggingface", "org/ast-dataset"),
        ("model", "huggingface", "org/config-model"), ("dataset", "huggingface", "org/config-dataset"),
    }
    assert all(item.authorization_status.value == "pending" and item.license_expression_id is None and item.confidence == 0.6 for item in assets)
    assert all(item.locator in files and item.start_line >= 1 and item.end_line >= item.start_line for item in evidence)
    assert {item.detected_by.value for item in evidence} == {"static_pattern", "ast", "manifest_parser"}


def test_p0_b02a_rejects_dynamic_calls_and_does_not_execute_input() -> None:
    source = "from transformers import AutoModel\nfrom datasets import load_dataset\nAutoModel.from_pretrained(model_id)\nload_dataset(dataset_id)\n"
    assert detect_ai_assets({"dynamic.py": source}, observed_at=_NOW) == ([], [])
