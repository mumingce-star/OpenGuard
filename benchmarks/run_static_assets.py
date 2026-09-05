"""Run the deterministic B6 detector against a versioned bench case."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from app.detectors import detect_ai_assets


def _load_case(path: str | Path) -> Mapping[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid static-assets benchmark case") from error
    if not isinstance(value, Mapping) or set(value) != {"version", "observed_at", "cases"}:
        raise ValueError("invalid static-assets benchmark case")
    if not isinstance(value["version"], str) or not isinstance(value["observed_at"], str) or not isinstance(value["cases"], list):
        raise ValueError("invalid static-assets benchmark case")
    return value


def _label(asset: Mapping[str, Any]) -> str:
    asset_type, provider, name = asset["asset_type"], asset.get("provider"), asset["name"]
    return f"{asset_type}:{provider}:{name}" if provider else f"{asset_type}:{name}"


def run_case_file(path: str | Path) -> dict[str, Any]:
    """Return detector output produced from source snippets in a golden case."""
    document = _load_case(path)
    observed_at = datetime.fromisoformat(document["observed_at"].replace("Z", "+00:00"))
    results: list[dict[str, Any]] = []
    for case in document["cases"]:
        if not isinstance(case, Mapping) or set(case) != {"id", "files", "expected"}:
            raise ValueError("invalid benchmark case entry")
        if not isinstance(case["id"], str) or not isinstance(case["files"], Mapping) or not isinstance(case["expected"], list):
            raise ValueError("invalid benchmark case entry")
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in case["files"].items()):
            raise ValueError("invalid benchmark source files")
        assets, evidence = detect_ai_assets(case["files"], observed_at=observed_at)
        asset_json = [asset.model_dump(mode="json") for asset in assets]
        results.append({
            "id": case["id"], "expected": case["expected"],
            "predicted": sorted(_label(asset) for asset in asset_json),
            "assets": asset_json,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        })
    return {"version": document["version"], "scanner": "openguard-static-ai-detector/0.1.0", "cases": results}


def write_result(case_path: str | Path, result_path: str | Path) -> dict[str, Any]:
    result = run_case_file(case_path)
    destination = Path(result_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
