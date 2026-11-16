"""Offline end-to-end checks for the automated static subset benchmark."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from benchmarks import auto_static_bench as bench
from benchmarks.auto_static_oracle import oracle_file, self_test


def _catalog() -> dict:
    return {"schema": bench.CATALOG_SCHEMA, "samples": [
        {"sample_id": f"repo{i:02d}", "family_id": f"family{i:02d}",
         "split": "holdout" if i >= 18 else ("train" if i < 8 else "dev"),
         "url": f"https://github.com/example/repo{i:02d}.git", "ref": "HEAD"}
        for i in range(25)
    ]}


def _archive(repo: str) -> bytes:
    content = 'target = "https://huggingface.co/acme/model"\n# '+repo+'\n'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(f"{repo}-fixed/", "")
        archive.writestr(f"{repo}-fixed/main.py", content)
        archive.writestr(f"{repo}-fixed/LICENSE", "SPDX-License-Identifier: MIT\n")
    return output.getvalue()


def test_oracle_known_answers_and_unsupported_dynamic_scope() -> None:
    self_test()
    result = oracle_file("sample.py", 'import datasets\nname = get_name()\ndatasets.load_dataset(name)\n# https://huggingface.co/acme/comment\n')
    assert result["labels"] == []
    assert result["unscored_constructs"] == 1
    js = oracle_file("client.ts", 'import { GoogleGenAI as Client } from "@google/genai";\nconst x = new Client();\n// "https://huggingface.co/acme/comment"\n')
    assert [(x["provider"], x["oracle_rule"]) for x in js["labels"]] == [("google", "javascript_sdk_alias")]
    multi = oracle_file("multi.py", '说明 = """前缀\nhttps://huggingface.co/acme/model\n"""\n')
    assert [(x["line"], x["name"]) for x in multi["labels"]] == [(2, "acme/model")]


def test_catalog_rejects_split_leak_and_duplicate_repository() -> None:
    value = _catalog()
    bench.validate_catalog(value)
    value["samples"][-1]["family_id"] = value["samples"][0]["family_id"]
    with pytest.raises(ValueError, match="family leaks"):
        bench.validate_catalog(value)
    value = _catalog()
    value["samples"][-1]["url"] = value["samples"][0]["url"]
    with pytest.raises(ValueError, match="duplicate repository"):
        bench.validate_catalog(value)


def test_oracle_self_test_failure_prevents_freeze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
    def fail() -> None:
        raise RuntimeError("known-answer drift")
    monkeypatch.setattr(bench, "self_test", fail)
    output = tmp_path / "frozen"
    with pytest.raises(RuntimeError, match="known-answer drift"):
        bench.freeze(catalog, output)
    assert not output.exists()


def test_archive_path_and_duplicate_entries_are_rejected() -> None:
    for entries in (["root/../escape.py"], ["root/a.py", "root/a.py"]):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for index, name in enumerate(entries):
                if index and name == entries[0]:
                    with pytest.warns(UserWarning, match="Duplicate name"):
                        archive.writestr(name, "model = 'acme/model'\n")
                else:
                    archive.writestr(name, "model = 'acme/model'\n")
        with pytest.raises(ValueError, match="unsafe archive path|duplicate archive path"):
            bench._snapshot(output.getvalue())


def test_comment_fp_is_classified_only_with_comment_evidence() -> None:
    source = 'const x = "ok"; /** OpenAI.ChatCompletion */\n'
    prediction = {"locator": "client.ts", "line": 1, "resource_type": "api", "provider": "openai",
                  "name": "openai", "source_url": None, "evidence_sha256": bench._sha(source.encode())}
    error = bench._score([], [prediction], "repo00", "dev", {"client.ts": source})["errors"][0]
    assert error["classification"] == "comment_or_documentation"
    source = 'const x = "ok"; const value = OpenAI.ChatCompletion;\n'
    prediction["evidence_sha256"] = bench._sha(source.encode())
    error = bench._score([], [prediction], "repo00", "dev", {"client.ts": source})["errors"][0]
    assert error["classification"] == "unclassified"


def test_freeze_evaluate_and_compare_are_separate_and_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
    monkeypatch.setattr(bench, "_resolve_commit", lambda _url, _ref: "a" * 40)
    monkeypatch.setattr(bench, "_download_zip", lambda _owner, repo, _commit: _archive(repo))
    frozen = tmp_path / "frozen"
    manifest = bench.freeze(catalog, frozen)
    assert len(manifest["samples"]) == 25
    assert all(row["state"] == "fixed" and row["license_declaration"] == "MIT" for row in manifest["samples"])
    assert len([row for row in manifest["samples"] if row["split"] == "holdout"]) == 7

    metrics = bench.evaluate(frozen, "baseline")
    assert metrics["automated_scope_ready"] is True
    assert metrics["bench_2_reportable"] is False
    assert metrics["overall"] == {"tp": 25, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert (frozen / "gold" / "repo00.json").is_file()
    assert (frozen / "predictions" / "baseline" / "repo00.json").is_file()
    assert (frozen / "metrics" / "baseline.json").is_file()
    assert (frozen / "runs" / "baseline.json").is_file()
    with pytest.raises(FileExistsError):
        bench.evaluate(frozen, "baseline")

    bench.evaluate(frozen, "candidate")
    comparison = bench.compare(frozen / "metrics" / "baseline.json", frozen / "metrics" / "candidate.json",
                               "0.3.0", frozen / "rule-change.json")
    assert comparison["resolved_fn_ids"] == []
    assert comparison["introduced_fp_ids"] == []
    assert comparison["holdout"]["before"] == comparison["holdout"]["after"]
    candidate_prediction = frozen / "predictions" / "candidate" / "repo00.json"
    candidate_bytes = candidate_prediction.read_bytes()
    candidate_prediction.write_bytes(candidate_bytes + b" ")
    with pytest.raises(ValueError, match="prediction hash mismatch"):
        bench.compare(frozen / "metrics" / "baseline.json", frozen / "metrics" / "candidate.json",
                      "0.3.0", frozen / "tampered-prediction-change.json")
    candidate_prediction.write_bytes(candidate_bytes)
    with pytest.raises(ValueError, match="rule version"):
        bench.compare(frozen / "metrics" / "baseline.json", frozen / "metrics" / "candidate.json",
                      "unbound", frozen / "other-change.json")
    candidate_path = frozen / "metrics" / "candidate.json"
    modified = json.loads(candidate_path.read_text(encoding="utf-8"))
    modified["overall"]["precision"] = 1.0
    candidate_path.write_text(json.dumps(modified), encoding="utf-8")
    with pytest.raises(ValueError, match="metrics receipt mismatch"):
        bench.compare(frozen / "metrics" / "baseline.json", candidate_path,
                      "0.3.0", frozen / "tampered-change.json")


def test_collection_failure_is_retained_and_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
    monkeypatch.setattr(bench, "_resolve_commit", lambda _url, _ref: "a" * 40)
    def download(_owner: str, repo: str, _commit: str) -> bytes:
        if repo == "repo00":
            raise OSError("network unavailable")
        return _archive(repo)
    monkeypatch.setattr(bench, "_download_zip", download)
    frozen = tmp_path / "frozen"
    manifest = bench.freeze(catalog, frozen)
    assert manifest["samples"][0]["state"] == "failed"
    assert manifest["samples"][0]["failure"] == "OSError"
    metrics = bench.evaluate(frozen, "failed_run")
    assert metrics["automated_scope_ready"] is True
    assert metrics["total_samples"] == 25 and metrics["failed_samples"] == 1
    assert metrics["collection_failed_samples"] == 1 and metrics["evaluation_failed_samples"] == 0
    receipt = json.loads((frozen / "runs" / "failed_run.json").read_text(encoding="utf-8"))
    assert receipt["sample_results"][0]["status"] == "failed"
    changed = json.loads((frozen / "freeze.json").read_text(encoding="utf-8"))
    changed["samples"].pop(0)
    (frozen / "freeze.json").write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="ledger is incomplete"):
        bench.evaluate(frozen, "removed_failure")
    assert not (frozen / "metrics" / "removed_failure.json").exists()


def test_tampered_archive_is_counted_as_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
    monkeypatch.setattr(bench, "_resolve_commit", lambda _url, _ref: "a" * 40)
    monkeypatch.setattr(bench, "_download_zip", lambda _owner, repo, _commit: _archive(repo))
    frozen = tmp_path / "frozen"
    bench.freeze(catalog, frozen)
    (frozen / "snapshots" / "repo00.zip").write_bytes(b"tampered")
    metrics = bench.evaluate(frozen, "tamper")
    assert metrics["failed_samples"] == 1 and metrics["automated_scope_ready"] is False
    assert metrics["evaluation_failed_samples"] == 1
    receipt = json.loads((frozen / "runs" / "tamper.json").read_text(encoding="utf-8"))
    assert receipt["sample_results"][0]["failure"] == "input_hash_mismatch"


def test_revision_reuses_verified_snapshots_and_retains_prior_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first_catalog = _catalog()
    source = tmp_path / "catalog.json"
    source.write_text(json.dumps(first_catalog), encoding="utf-8")
    monkeypatch.setattr(bench, "_resolve_commit", lambda _url, _ref: "a" * 40)
    calls: list[str] = []
    def first_download(_owner: str, repo: str, _commit: str) -> bytes:
        calls.append(repo)
        if repo == "repo00":
            raise OSError("unavailable")
        return _archive(repo)
    monkeypatch.setattr(bench, "_download_zip", first_download)
    old_dir = tmp_path / "old"
    bench.freeze(source, old_dir)
    next_catalog = _catalog()
    for i in range(25, 30):
        next_catalog["samples"].append({"sample_id": f"repo{i:02d}", "family_id": f"family{i:02d}",
                                         "split": "holdout", "url": f"https://github.com/example/repo{i:02d}.git", "ref": "HEAD"})
    source.write_text(json.dumps(next_catalog), encoding="utf-8")
    calls.clear()
    new_dir = tmp_path / "new"
    manifest = bench.freeze(source, new_dir, reuse_from=old_dir)
    assert calls == [f"repo{i:02d}" for i in range(25, 30)]
    assert manifest["samples"][0]["state"] == "failed"
    assert sum(row["state"] == "fixed" for row in manifest["samples"]) == 29
    assert manifest["samples"][1]["input_sha256"] == json.loads((old_dir / "freeze.json").read_text())["samples"][1]["input_sha256"]


def test_read_only_audit_detects_artifact_and_ledger_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
    monkeypatch.setattr(bench, "_resolve_commit", lambda _url, _ref: "a" * 40)
    monkeypatch.setattr(bench, "_download_zip", lambda _owner, repo, _commit: _archive(repo))
    frozen = tmp_path / "frozen"
    bench.freeze(catalog, frozen)
    bench.evaluate(frozen, "baseline")
    before = sorted(path.relative_to(frozen) for path in frozen.rglob("*"))
    report = bench.audit(frozen, "baseline")
    assert report == {"status": "verified", "sample_count": 25, "fixed_count": 25,
                      "completed_count": 25, "failed_count": 0, "holdout_count": 7,
                      "repeated_match_keys": 0}
    assert sorted(path.relative_to(frozen) for path in frozen.rglob("*")) == before

    prediction = frozen / "predictions" / "baseline" / "repo00.json"
    original = prediction.read_bytes()
    prediction.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="prediction hash mismatch"):
        bench.audit(frozen, "baseline")
    prediction.write_bytes(original)
    prediction.unlink()
    with pytest.raises(FileNotFoundError):
        bench.audit(frozen, "baseline")
    prediction.write_bytes(original)

    gold = frozen / "gold" / "repo00.json"
    original = gold.read_bytes()
    gold.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="gold hash mismatch"):
        bench.audit(frozen, "baseline")
    gold.write_bytes(original)

    snapshot = frozen / "snapshots" / "repo00.zip"
    original = snapshot.read_bytes()
    snapshot.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="input hash mismatch"):
        bench.audit(frozen, "baseline")
    snapshot.write_bytes(original)

    receipt = frozen / "runs" / "baseline.json"
    original = receipt.read_bytes()
    changed = json.loads(original)
    changed["sample_results"][0]["tp"] = 0
    receipt.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="sample score mismatch"):
        bench.audit(frozen, "baseline")
    changed = json.loads(original)
    changed["sample_results"][0]["errors"] = [{"error_id": "fp_fake", "kind": "FP", "label": {}}]
    receipt.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="sample error ledger mismatch"):
        bench.audit(frozen, "baseline")


def test_read_only_audit_retains_collection_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(_catalog()), encoding="utf-8")
    monkeypatch.setattr(bench, "_resolve_commit", lambda _url, _ref: "a" * 40)
    def download(_owner: str, repo: str, _commit: str) -> bytes:
        if repo == "repo00":
            raise OSError("network unavailable")
        return _archive(repo)
    monkeypatch.setattr(bench, "_download_zip", download)
    frozen = tmp_path / "frozen"
    bench.freeze(catalog, frozen)
    bench.evaluate(frozen, "baseline")
    assert bench.audit(frozen, "baseline")["failed_count"] == 1
    unexpected = frozen / "snapshots" / "repo00.zip"
    unexpected.write_bytes(_archive("repo00"))
    with pytest.raises(ValueError, match="unrecorded snapshot"):
        bench.audit(frozen, "baseline")
    unexpected.unlink()
    receipt = frozen / "runs" / "baseline.json"
    changed = json.loads(receipt.read_text(encoding="utf-8"))
    changed["sample_results"].pop(0)
    receipt.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="sample ledger mismatch"):
        bench.audit(frozen, "baseline")
