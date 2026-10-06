"""Fail-closed preparation gate for the P1 fixed-repository benchmark."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SPLITS = frozenset({"train", "dev", "holdout"})
_STATES = frozenset({"planned", "fixed", "failed"})


def _document(path: str | Path) -> Mapping[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid P1 repository bench manifest") from error
    if not isinstance(value, Mapping):
        raise ValueError("invalid P1 repository bench manifest")
    return value


def validate_preparation(path: str | Path) -> dict[str, Any]:
    """Validate planning/fixed records without fetching a repository.

    Only a fully frozen collection may be labelled ready for Gold, prediction,
    result or metrics.  A failed sample is deliberately retained in the same
    ledger and counts toward neither the fixed corpus nor reported metrics.
    """
    value = _document(path)
    if set(value) != {"schema", "scope", "samples", "artifact_layout"}:
        raise ValueError("invalid P1 repository bench manifest")
    if value["schema"] != "openguard.p1-repository-bench-preparation/1" or value["scope"] != "preparation_not_formal_quality":
        raise ValueError("invalid P1 repository bench manifest")
    if not isinstance(value["samples"], list) or not 20 <= len(value["samples"]) <= 30:
        raise ValueError("P1 benchmark requires 20-30 retained sample records")
    if value["artifact_layout"] != {"gold": "gold/", "prediction": "predictions/", "metric": "metrics/", "run": "runs/"}:
        raise ValueError("Gold, prediction, metric and run artifact paths must be separate")

    seen, errors, frozen, holdouts, failed = set(), [], [], [], []
    for sample in value["samples"]:
        if not isinstance(sample, Mapping) or set(sample) != {"sample_id", "family_id", "split", "state", "source"}:
            raise ValueError("invalid P1 sample record")
        sample_id, state, split = sample["sample_id"], sample["state"], sample["split"]
        if not isinstance(sample_id, str) or not sample_id or sample_id in seen or state not in _STATES or split not in _SPLITS:
            raise ValueError("invalid P1 sample identity")
        seen.add(sample_id)
        source = sample["source"]
        if not isinstance(source, Mapping):
            raise ValueError("invalid P1 sample source")
        if state == "planned":
            if source != {"status": "not_collected"}:
                raise ValueError("planned samples cannot claim source facts")
            continue
        required = {"url", "commit_sha", "input_sha256", "fetched_at", "license_declaration"}
        if not required <= set(source) or not all(isinstance(source[key], str) and source[key] for key in required):
            errors.append({"sample_id": sample_id, "code": "SOURCE_FACTS_INCOMPLETE"})
        elif not _COMMIT.fullmatch(source["commit_sha"]) or not _SHA256.fullmatch(source["input_sha256"]):
            errors.append({"sample_id": sample_id, "code": "SOURCE_HASH_INVALID"})
        if state == "fixed":
            frozen.append(sample_id)
            if split == "holdout":
                holdouts.append(sample_id)
        else:
            failed.append(sample_id)
            if source.get("failure") not in {"fetch_failed", "input_hash_mismatch", "license_unavailable", "scanner_failed"}:
                errors.append({"sample_id": sample_id, "code": "FAILED_SAMPLE_REASON_REQUIRED"})
    ready = not errors and len(frozen) >= 20 and len(holdouts) >= 5
    return {
        "manifest_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "fixed_sample_count": len(frozen), "holdout_count": len(holdouts),
        "retained_failed_sample_count": len(failed), "formal_quality_ready": ready,
        "errors": errors,
    }


def validate_run_binding(value: Mapping[str, Any]) -> None:
    """Require immutable detector/rule/config/input identities for one run."""
    required = {"run_id", "detector_version", "rule_version", "config_sha256", "input_sha256", "status"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("invalid P1 benchmark run binding")
    if (not all(isinstance(value[key], str) and value[key] for key in ("run_id", "detector_version", "rule_version"))
            or not _SHA256.fullmatch(value["config_sha256"])
            or not _SHA256.fullmatch(value["input_sha256"])
            or value["status"] not in {"completed", "failed"}):
        raise ValueError("invalid P1 benchmark run binding")
