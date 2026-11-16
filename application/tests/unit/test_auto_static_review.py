"""Review packets must preserve provenance without inventing Gold decisions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import auto_static_review as review


def _fixture(tmp_path: Path) -> Path:
    frozen = tmp_path / "frozen"
    for name in ("metrics", "runs", "predictions/run"):
        (frozen / name).mkdir(parents=True)
    samples = [
        {"sample_id": "train_repo", "split": "train", "url": "https://github.com/example/train.git",
         "ref": "HEAD", "commit_sha": "a" * 40, "input_sha256": "b" * 64,
         "state": "fixed", "failure": None},
        {"sample_id": "holdout_repo", "split": "holdout", "url": "https://github.com/example/holdout.git",
         "ref": "HEAD", "commit_sha": "f" * 40, "input_sha256": "a" * 64,
         "state": "fixed", "failure": None},
        {"sample_id": "failed_repo", "split": "holdout", "url": "https://github.com/example/failed.git",
         "ref": "HEAD", "commit_sha": None, "input_sha256": None,
         "state": "failed", "failure": "archive exceeds byte limit"},
    ]
    (frozen / "freeze.json").write_text(json.dumps({"samples": samples}), encoding="utf-8")
    label = {"locator": "src/client.ts", "line": 4, "resource_type": "api", "provider": "openai",
             "name": "openai", "evidence_sha256": "c" * 64, "evidence_id": "evd-one"}
    (frozen / "predictions/run/train_repo.json").write_text(
        json.dumps({"labels": [label, {**label, "evidence_id": "evd-two"}]}), encoding="utf-8")
    (frozen / "predictions/run/holdout_repo.json").write_text(json.dumps({"labels": []}), encoding="utf-8")
    errors = [
        {"error_id": "fn_train", "kind": "FN", "tier": "B", "classification": "rule_extension",
         "sample_id": "train_repo", "split": "train", "label": label},
        {"error_id": "fp_holdout", "kind": "FP", "classification": "unclassified",
         "sample_id": "holdout_repo", "split": "holdout", "label": label},
    ]
    (frozen / "metrics/run.json").write_text(json.dumps({"errors": errors}), encoding="utf-8")
    (frozen / "runs/run.json").write_text(json.dumps({"sample_results": [
        {"sample_id": "train_repo", "status": "completed", "gold_sha256": "d" * 64, "prediction_sha256": "e" * 64},
        {"sample_id": "holdout_repo", "status": "completed", "gold_sha256": "d" * 64, "prediction_sha256": "e" * 64},
        {"sample_id": "failed_repo", "status": "failed"},
    ]}), encoding="utf-8")
    return frozen


def test_review_queue_defaults_to_non_holdout_and_keeps_failure_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = _fixture(tmp_path)
    monkeypatch.setattr(review, "audit", lambda _frozen, _run: {"status": "verified", "sample_count": 3})
    packet = review.prepare_review_queue(frozen, "run")
    assert [case["error_id"] for case in packet["cases"]] == ["fn_train"]
    assert packet["cases"][0]["review_state"] == "unreviewed"
    assert packet["cases"][0]["adjudication"] is None
    assert packet["cases"][0]["label_origin"] == "machine_oracle"
    assert packet["formal_gold"] is False and packet["reviewer_required"] is True
    assert packet["cases"][0]["commit_sha"] == "a" * 40
    assert packet["failure_summary"] == {"train": 0, "dev": 0, "holdout": 1}
    assert packet["failures"] == []
    assert packet["holdout_excluded"] is True
    assert len(packet["repeated_match_keys"]) == 1
    assert packet["repeated_match_keys"][0]["evidence_ids"] == ["evd-one", "evd-two"]
    assert "archive exceeds byte limit" not in json.dumps(packet)
    assert '"excerpt"' not in json.dumps(packet)


def test_explicit_holdout_packet_preserves_failure_and_is_write_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = _fixture(tmp_path)
    monkeypatch.setattr(review, "audit", lambda _frozen, _run: {"status": "verified", "sample_count": 3})
    packet = review.prepare_review_queue(frozen, "run", include_holdout=True)
    assert [case["error_id"] for case in packet["cases"]] == ["fn_train", "fp_holdout"]
    assert packet["cases"][1]["label_origin"] == "detector_candidate"
    assert packet["failures"][0]["failure"] == "archive exceeds byte limit"
    assert packet["holdout_excluded"] is False
    target = tmp_path / "review.json"
    review.write_review_queue(target, packet)
    with pytest.raises(FileExistsError):
        review.write_review_queue(target, packet)


def test_review_queue_fails_closed_when_artifact_audit_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = _fixture(tmp_path)
    def reject(_frozen: Path, _run: str) -> dict:
        raise ValueError("prediction hash mismatch")
    monkeypatch.setattr(review, "audit", reject)
    with pytest.raises(ValueError, match="prediction hash mismatch"):
        review.prepare_review_queue(frozen, "run")
