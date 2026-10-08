"""Structured B06 error-analysis and ablation gate, independent of Gold."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


_FN = {"A": "static_direct", "B": "rule_extension", "C": "dynamic_or_unsafe"}
_FP = {"sdk_name_collision", "example_code", "comment_or_documentation", "invalid_url", "irrelevant_configuration"}


def validate_error_analysis(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid B06 error analysis") from error
    if not isinstance(value, Mapping) or set(value) != {"schema", "status", "gold_frozen", "errors", "rule_changes"}:
        raise ValueError("invalid B06 error analysis")
    if value["schema"] != "openguard.b06-error-analysis/1" or value["status"] not in {"preparation_not_evaluated", "evaluated"} or type(value["gold_frozen"]) is not bool:
        raise ValueError("invalid B06 error analysis")
    if value["status"] == "evaluated":
        raise ValueError("v1 cannot establish formal quality without bound human Gold evidence")
    if value["gold_frozen"]:
        raise ValueError("preparation cannot claim frozen human Gold")
    errors = value["errors"]
    changes = value["rule_changes"]
    if not isinstance(errors, list) or not isinstance(changes, list):
        raise ValueError("invalid B06 error analysis")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in errors:
        if not isinstance(item, Mapping) or not isinstance(item.get("error_id"), str) or not item["error_id"] or item["error_id"] in by_id:
            raise ValueError("invalid B06 error identity")
        kind = item.get("kind")
        if kind == "FN":
            if set(item) != {"error_id", "kind", "tier", "reason", "case_id"} or item["tier"] not in _FN or item["reason"] != _FN[item["tier"]]:
                raise ValueError("invalid B06 FN classification")
        elif kind == "FP":
            if set(item) != {"error_id", "kind", "classification", "case_id"} or item["classification"] not in _FP:
                raise ValueError("invalid B06 FP classification")
        else:
            raise ValueError("invalid B06 error kind")
        by_id[item["error_id"]] = item
    for change in changes:
        required = {"change_id", "rule_version", "resolved_fn_ids", "introduced_fp_ids", "holdout"}
        if not isinstance(change, Mapping) or set(change) != required or not all(isinstance(change[key], str) and change[key] for key in ("change_id", "rule_version")):
            raise ValueError("invalid B06 rule change")
        resolved, introduced = change["resolved_fn_ids"], change["introduced_fp_ids"]
        if not isinstance(resolved, list) or not isinstance(introduced, list) or len(set(resolved)) != len(resolved) or len(set(introduced)) != len(introduced):
            raise ValueError("invalid B06 rule change references")
        if any(item not in by_id or by_id[item]["kind"] != "FN" for item in resolved) or any(item not in by_id or by_id[item]["kind"] != "FP" for item in introduced):
            raise ValueError("B06 rule change must bind classified FN/FP records")
        holdout = change["holdout"]
        if not isinstance(holdout, Mapping):
            raise ValueError("invalid B06 holdout record")
        if holdout != {"status": "blocked_until_human_gold_freeze", "before": None, "after": None}:
            raise ValueError("unfrozen holdout cannot claim a change")
    return {"formal_quality_claimed": False, "gold_frozen": False, "error_count": len(errors), "rule_change_count": len(changes)}
