"""Offline Detector 0.3 contract cases; this is not a production Gold set."""

from __future__ import annotations

import json
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
