"""Prepare evidence-bound human-review queues for the automated static subset.

This tool does not adjudicate Gold or turn machine disagreements into formal FN/FP.
It does not execute or fetch source repositories and never embeds source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from benchmarks.auto_static_bench import audit

SCHEMA = "openguard.auto-static-review-queue/1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("review input must be an object")
    return value, _sha(raw)


def _match_key(label: dict) -> tuple:
    return (label["locator"], label["line"], label["resource_type"],
            label["provider"], label["name"], label["evidence_sha256"])


def prepare_review_queue(frozen: Path, run_id: str, *, include_holdout: bool = False) -> dict:
    """Audit first, then emit unreviewed cases; holdout is excluded by default."""
    audit_result = audit(frozen, run_id)
    manifest, freeze_sha = _load(frozen / "freeze.json")
    metrics, metrics_sha = _load(frozen / "metrics" / f"{run_id}.json")
    receipt, receipt_sha = _load(frozen / "runs" / f"{run_id}.json")
    samples = {item["sample_id"]: item for item in manifest["samples"]}
    results = {item["sample_id"]: item for item in receipt["sample_results"]}
    allowed = {"train", "dev", "holdout"} if include_holdout else {"train", "dev"}
    cases = []
    for error in metrics["errors"]:
        if error["split"] not in allowed:
            continue
        sample = samples[error["sample_id"]]
        result = results[error["sample_id"]]
        label = error["label"]
        cases.append({
            "error_id": error["error_id"], "sample_id": sample["sample_id"],
            "split": sample["split"], "source_repository": sample["url"],
            "commit_sha": sample["commit_sha"], "input_sha256": sample["input_sha256"],
            "locator": label["locator"], "line": label["line"],
            "resource_type": label["resource_type"], "provider": label["provider"],
            "name": label["name"], "evidence_sha256": label["evidence_sha256"],
            "gold_sha256": result["gold_sha256"],
            "prediction_sha256": result["prediction_sha256"],
            "machine_kind": error["kind"],
            "machine_classification": error.get("classification", "unclassified"),
            "machine_tier": error.get("tier"),
            "label_origin": "machine_oracle" if error["kind"] == "FN" else "detector_candidate",
            "review_state": "unreviewed", "adjudication": None,
        })
    failure_summary = {split: 0 for split in ("train", "dev", "holdout")}
    failures = []
    for sample in manifest["samples"]:
        if sample["state"] != "failed":
            continue
        failure_summary[sample["split"]] += 1
        if sample["split"] in allowed:
            failures.append({
                "sample_id": sample["sample_id"], "split": sample["split"],
                "source_repository": sample["url"], "source_ref": sample["ref"],
                "commit_sha": sample["commit_sha"], "input_sha256": sample["input_sha256"],
                "failure": sample["failure"], "review_state": "unreviewed",
            })
    repeated = []
    for sample in manifest["samples"]:
        if sample["state"] != "fixed" or sample["split"] not in allowed:
            continue
        if results[sample["sample_id"]]["status"] != "completed":
            continue
        prediction, _ = _load(frozen / "predictions" / run_id / f"{sample['sample_id']}.json")
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for label in prediction["labels"]:
            groups[_match_key(label)].append(label)
        for key, labels in groups.items():
            if len(labels) < 2:
                continue
            repeated.append({
                "sample_id": sample["sample_id"], "split": sample["split"],
                "locator": key[0], "line": key[1], "resource_type": key[2],
                "provider": key[3], "name": key[4], "evidence_sha256": key[5],
                "observation_count": len(labels),
                "evidence_ids": sorted({label["evidence_id"] for label in labels}),
                "review_state": "unreviewed",
            })
    return {
        "schema": SCHEMA, "run_id": run_id,
        "freeze_sha256": freeze_sha, "metrics_sha256": metrics_sha,
        "receipt_sha256": receipt_sha,
        "holdout_excluded": not include_holdout,
        "audited_sample_count": audit_result["sample_count"],
        "formal_gold": False, "reviewer_required": True,
        "cases": cases, "failure_summary": failure_summary,
        "failures": failures, "repeated_match_keys": repeated,
    }


def write_review_queue(destination: Path, packet: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as target:
        target.write((json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-holdout", action="store_true")
    args = parser.parse_args(argv)
    try:
        packet = prepare_review_queue(args.frozen, args.run_id, include_holdout=args.include_holdout)
        write_review_queue(args.output, packet)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"auto-static-review: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"case_count": len(packet["cases"]),
                      "failure_count": sum(packet["failure_summary"].values()),
                      "repeated_match_keys": len(packet["repeated_match_keys"]),
                      "holdout_excluded": packet["holdout_excluded"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
