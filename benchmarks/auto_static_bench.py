"""Reproducible, unattended benchmark for the oracle's bounded static subset.

Raw third-party ZIPs and generated artifacts belong in an ignored local output
directory.  This tool never executes or installs code from a source archive.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from benchmarks.auto_static_oracle import ORACLE_VERSION, oracle_file, self_test, supported

CATALOG_SCHEMA = "openguard.auto-static-catalog/1"
FREEZE_SCHEMA = "openguard.auto-static-freeze/2"
RUN_SCHEMA = "openguard.auto-static-run/2"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_ID = re.compile(r"^[a-z][a-z0-9_-]{2,40}$")
_MAX_ZIP = 64 * 1024 * 1024
_MAX_FILES = 20_000
_MAX_TEXT = 256 * 1024
_MAX_TOTAL_TEXT = 32 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _oracle_source_sha() -> str:
    return _sha(Path(__file__).with_name("auto_static_oracle.py").read_bytes())


def _runner_source_sha() -> str:
    return _sha(Path(__file__).read_bytes())


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_once(path: Path, value: object) -> str:
    data = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(data)
    return _sha(data)


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid JSON object: {path.name}")
    return value


def _github_repository(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port:
        raise ValueError("source must be an HTTPS GitHub repository URL")
    parts = parsed.path.removesuffix(".git").strip("/").split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        raise ValueError("source must identify one GitHub repository")
    return parts[0], parts[1]


def validate_catalog(value: dict) -> None:
    if set(value) != {"schema", "samples"} or value["schema"] != CATALOG_SCHEMA:
        raise ValueError("invalid automated source catalog")
    samples = value["samples"]
    if not isinstance(samples, list) or not 20 <= len(samples) <= 30:
        raise ValueError("catalog needs 20-30 retained sample records")
    ids: set[str] = set()
    families: dict[str, str] = {}
    repositories: set[tuple[str, str]] = set()
    holdouts = 0
    for row in samples:
        if not isinstance(row, dict) or set(row) != {"sample_id", "family_id", "split", "url", "ref"}:
            raise ValueError("invalid catalog sample")
        sample_id, family, split = row["sample_id"], row["family_id"], row["split"]
        if not isinstance(sample_id, str) or not _ID.fullmatch(sample_id) or sample_id in ids:
            raise ValueError("duplicate or invalid sample ID")
        if not isinstance(family, str) or not _ID.fullmatch(family) or split not in {"train", "dev", "holdout"}:
            raise ValueError("invalid family or split")
        if family in families and families[family] != split:
            raise ValueError("family leaks across splits")
        if not isinstance(row["ref"], str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", row["ref"]) or ".." in row["ref"]:
            raise ValueError("invalid source ref")
        repository = tuple(part.lower() for part in _github_repository(row["url"]))
        if repository in repositories:
            raise ValueError("duplicate repository in catalog")
        ids.add(sample_id)
        repositories.add(repository)
        families[family] = split
        holdouts += split == "holdout"
    if holdouts < 5:
        raise ValueError("catalog needs at least five holdouts")


def _resolve_commit(url: str, ref: str) -> str:
    if _SHA.fullmatch(ref):
        return ref
    completed = subprocess.run(
        ["git", "ls-remote", url, ref], capture_output=True, text=True,
        timeout=35, check=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    heads = [line.split("\t", 1)[0] for line in completed.stdout.splitlines() if "\t" in line]
    if len(heads) != 1 or not _SHA.fullmatch(heads[0]):
        raise ValueError("source ref did not resolve to one commit")
    return heads[0]


def _download_zip(owner: str, repo: str, commit: str) -> bytes:
    url = f"https://codeload.github.com/{owner}/{repo}/zip/{commit}"
    request = urllib.request.Request(url, headers={"User-Agent": "OpenGuard-Bench/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if urlsplit(response.geturl()).hostname != "codeload.github.com":
            raise ValueError("unexpected archive redirect")
        chunks, size = [], 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > _MAX_ZIP:
                raise ValueError("archive exceeds byte limit")
            chunks.append(chunk)
    return b"".join(chunks)


def _snapshot(raw: bytes) -> tuple[dict[str, str], dict, dict]:
    """Read bounded UTF-8 source files directly from a ZIP, without extraction."""
    if len(raw) > _MAX_ZIP:
        raise ValueError("archive exceeds byte limit")
    files: dict[str, str] = {}
    skipped = {"unsupported": 0, "oversize": 0, "non_utf8": 0, "symlink": 0}
    license_fact = {"declaration": "unknown", "file": None, "file_sha256": None, "declarations": []}
    total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_FILES:
            raise ValueError("archive exceeds file-count limit")
        seen_paths: set[str] = set()
        for info in infos:
            name = PurePosixPath(info.filename)
            parts = name.parts
            if info.filename.startswith("/") or "\\" in info.filename or "//" in info.filename or any(part in {"", ".", ".."} for part in parts):
                raise ValueError("unsafe archive path")
            if info.is_dir():
                continue
            if len(parts) < 2:
                raise ValueError("unsafe archive path")
            locator = "/".join(parts[1:])
            if not locator or locator in seen_paths:
                raise ValueError("duplicate archive path")
            seen_paths.add(locator)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                skipped["symlink"] += 1
                continue
            if info.file_size > _MAX_TEXT or total + info.file_size > _MAX_TOTAL_TEXT:
                skipped["oversize"] += 1
                continue
            if not supported(locator) and locator.upper() not in {"LICENSE", "LICENSE.MD", "LICENSE.TXT", "COPYING"}:
                skipped["unsupported"] += 1
                continue
            with archive.open(info) as source:
                data = source.read(_MAX_TEXT + 1)
            if len(data) > _MAX_TEXT:
                raise ValueError("source file exceeds byte limit")
            total += len(data)
            try:
                text = data.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                skipped["non_utf8"] += 1
                continue
            if locator.upper() in {"LICENSE", "LICENSE.MD", "LICENSE.TXT", "COPYING"} and license_fact["file"] is None:
                match = re.search(r"(?mi)^\s*SPDX-License-Identifier:\s*([A-Za-z0-9-.+]+)\s*$", text)
                license_fact["file"] = locator
                license_fact["file_sha256"] = _sha(data)
                if match:
                    license_fact["declarations"].append({"value": match.group(1), "locator": locator,
                                                          "file_sha256": _sha(data), "kind": "spdx_header"})
            if supported(locator):
                files[locator] = text
    for locator in ("pyproject.toml", "package.json"):
        text = files.get(locator)
        if text is None:
            continue
        try:
            document = tomllib.loads(text) if locator.endswith(".toml") else json.loads(text)
            value = document.get("project", {}).get("license") if locator.endswith(".toml") else document.get("license")
        except (ValueError, TypeError, AttributeError):
            continue
        if isinstance(value, str) and 0 < len(value) <= 200 and not any(ord(char) < 32 for char in value):
            license_fact["declarations"].append({"value": value, "locator": locator,
                                                  "file_sha256": _sha(text.encode("utf-8")), "kind": "metadata_literal"})
    declarations = {row["value"] for row in license_fact["declarations"]}
    license_fact["declaration"] = next(iter(declarations)) if len(declarations) == 1 else ("conflict" if declarations else "unknown")
    license_fact["declaration_evidence_sha256"] = license_fact["declarations"][0]["file_sha256"] if len(declarations) == 1 else None
    return files, skipped, license_fact


def freeze(catalog_path: Path, destination: Path, reuse_from: Path | None = None, *, retry_failed: bool = False) -> dict:
    self_test()
    catalog_raw = catalog_path.read_bytes()
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    previous: dict[str, dict] = {}
    if reuse_from is not None:
        previous_manifest = _read_json(reuse_from / "freeze.json")
        if previous_manifest.get("schema") not in {"openguard.auto-static-freeze/1", FREEZE_SCHEMA}:
            raise ValueError("invalid source freeze for reuse")
        previous = {row["sample_id"]: row for row in previous_manifest["samples"]}
        for row in previous.values():
            if row["state"] == "fixed":
                raw = (reuse_from / "snapshots" / f"{row['sample_id']}.zip").read_bytes()
                if _sha(raw) != row["input_sha256"]:
                    raise ValueError("reused input hash mismatch")
                _snapshot(raw)
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "catalog.json").open("xb") as target:
        target.write(catalog_raw)
    (destination / "snapshots").mkdir()
    records = []
    input_hashes: set[str] = set()
    for item in catalog["samples"]:
        owner, repo = _github_repository(item["url"])
        record = {**item, "fetched_at": _now(), "commit_sha": None, "input_sha256": None,
                  "license_declaration": "unknown", "license_evidence_sha256": None,
                  "license_file_sha256": None, "license_sources": [],
                  "state": "failed", "failure": None}
        try:
            old = previous.get(item["sample_id"])
            if old is not None:
                if any(old[key] != item[key] for key in ("sample_id", "family_id", "split", "url", "ref")):
                    raise ValueError("reused sample identity changed")
                if old["state"] == "failed" and not retry_failed:
                    records.append({**old, "reused_from_sha256": _sha((reuse_from / "freeze.json").read_bytes())})
                    continue
                if old["state"] == "fixed":
                    raw = (reuse_from / "snapshots" / f"{item['sample_id']}.zip").read_bytes()
                    if _sha(raw) != old["input_sha256"]:
                        raise ValueError("reused input hash mismatch")
                    _files, _skipped, license_fact = _snapshot(raw)
                    if old["input_sha256"] in input_hashes:
                        raise ValueError("duplicate input archive")
                    (destination / "snapshots" / f"{item['sample_id']}.zip").write_bytes(raw)
                    input_hashes.add(old["input_sha256"])
                    records.append({**old, "license_declaration": license_fact["declaration"],
                                    "license_evidence_sha256": license_fact["declaration_evidence_sha256"],
                                    "license_file_sha256": license_fact["file_sha256"],
                                    "license_sources": license_fact["declarations"],
                                    "reused_from_sha256": _sha((reuse_from / "freeze.json").read_bytes())})
                    continue
                record["previous_failure"] = old["failure"]
                record["retried_from_sha256"] = _sha((reuse_from / "freeze.json").read_bytes())
            commit = old["commit_sha"] if old and isinstance(old["commit_sha"], str) and _SHA.fullmatch(old["commit_sha"]) else _resolve_commit(item["url"], item["ref"])
            record["commit_sha"] = commit
            raw = _download_zip(owner, repo, commit)
            record["input_sha256"] = _sha(raw)
            if record["input_sha256"] in input_hashes:
                raise ValueError("duplicate input archive")
            files, skipped, license_fact = _snapshot(raw)
            if not files:
                raise ValueError("no supported UTF-8 source files")
            record["license_declaration"] = license_fact["declaration"]
            record["license_evidence_sha256"] = license_fact["declaration_evidence_sha256"]
            record["license_file_sha256"] = license_fact["file_sha256"]
            record["license_sources"] = license_fact["declarations"]
            record["collection_skipped"] = skipped
            (destination / "snapshots" / f"{item['sample_id']}.zip").write_bytes(raw)
            record["state"] = "fixed"
            input_hashes.add(record["input_sha256"])
        except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
            record["failure"] = str(error) if isinstance(error, ValueError) else type(error).__name__
        records.append(record)
    manifest = {"schema": FREEZE_SCHEMA, "catalog_sha256": _sha(catalog_raw),
                "oracle_version": ORACLE_VERSION, "oracle_source_sha256": _oracle_source_sha(),
                "frozen_at": _now(), "samples": records}
    _write_once(destination / "freeze.json", manifest)
    return manifest


def _identity(item: dict) -> tuple:
    return (item["locator"], item["line"], item["resource_type"], item["provider"], item["name"], item["evidence_sha256"])


def _score(gold: list[dict], predicted: list[dict], sample_id: str, split: str,
           files: dict[str, str]) -> dict:
    actual = {_identity(item): item for item in gold}
    found = {_identity(item): item for item in predicted}
    errors = []
    for key in sorted(actual.keys() - found.keys()):
        label = actual[key]
        error_id = "fn_" + _sha(repr((sample_id, key)).encode())[:16]
        tier = "B" if label["oracle_rule"] == "javascript_sdk_alias" else "A"
        errors.append({"error_id": error_id, "kind": "FN", "tier": tier,
                       "classification": "rule_extension" if tier == "B" else "static_direct",
                       "sample_id": sample_id, "split": split, "label": label})
    for key in sorted(found.keys() - actual.keys()):
        label = found[key]
        error_id = "fp_" + _sha(repr((sample_id, key)).encode())[:16]
        classification = "unclassified"
        source_lines = files[label["locator"]].splitlines()
        if 1 <= label["line"] <= len(source_lines):
            line = source_lines[label["line"] - 1]
            fragments = re.findall(r"/\*.*?\*/|(?:^|\s)//.*$|(?:^|\s)#.*$", line)
            provider_marker = {"openai": "OpenAI", "anthropic": "Anthropic",
                               "google": "GoogleGenAI"}.get(label["provider"])
            if any((label.get("source_url") and label["source_url"] in fragment)
                   or (label["resource_type"] == "api" and provider_marker and provider_marker in fragment)
                   for fragment in fragments):
                classification = "comment_or_documentation"
        errors.append({"error_id": error_id, "kind": "FP", "classification": classification,
                       "sample_id": sample_id, "split": split, "label": label})
    return {"tp": len(actual.keys() & found.keys()), "fp": len(found.keys() - actual.keys()),
            "fn": len(actual.keys() - found.keys()), "errors": errors}


def _summary(rows: list[dict]) -> dict:
    tp = sum(row["tp"] for row in rows)
    fp = sum(row["fp"] for row in rows)
    fn = sum(row["fn"] for row in rows)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall) if precision + recall else 0.0) if precision is not None and recall is not None else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def evaluate(frozen: Path, run_id: str) -> dict:
    if not _ID.fullmatch(run_id):
        raise ValueError("invalid run ID")
    self_test()
    manifest_path = frozen / "freeze.json"
    manifest = _read_json(manifest_path)
    if (manifest.get("schema") != FREEZE_SCHEMA or manifest.get("oracle_version") != ORACLE_VERSION
            or manifest.get("oracle_source_sha256") != _oracle_source_sha()):
        raise ValueError("freeze/oracle version mismatch")
    catalog_raw = (frozen / "catalog.json").read_bytes()
    if _sha(catalog_raw) != manifest.get("catalog_sha256"):
        raise ValueError("frozen catalog hash mismatch")
    catalog = json.loads(catalog_raw)
    validate_catalog(catalog)
    if len(manifest.get("samples", [])) != len(catalog["samples"]):
        raise ValueError("frozen sample ledger is incomplete")
    for source, record in zip(catalog["samples"], manifest["samples"]):
        if any(record.get(key) != source[key] for key in ("sample_id", "family_id", "split", "url", "ref")):
            raise ValueError("frozen sample identity changed")
        if record.get("state") == "fixed":
            if not isinstance(record.get("commit_sha"), str) or not _SHA.fullmatch(record["commit_sha"]) or not re.fullmatch(r"[0-9a-f]{64}", record.get("input_sha256") or ""):
                raise ValueError("incomplete fixed sample identity")
        elif record.get("state") != "failed" or not record.get("failure"):
            raise ValueError("failed sample must be retained with a reason")
    if (frozen / "metrics" / f"{run_id}.json").exists() or (frozen / "runs" / f"{run_id}.json").exists():
        raise FileExistsError("run ID already exists")
    config = {"max_text_bytes": _MAX_TEXT, "max_total_text_bytes": _MAX_TOTAL_TEXT,
              "matching": "sample+locator+line+resource_type+provider+name+file_sha256",
              "prediction_scope": "oracle_eligible_lines_only", "oracle_version": ORACLE_VERSION,
              "runner_source_sha256": _runner_source_sha()}
    config_sha = _sha(_json_bytes(config))
    from app.detectors import detect_static_asset_candidates
    from app.detectors.static_assets import _PRODUCER
    from app.detectors import static_assets, structured_models
    detector_source_sha = _sha(Path(static_assets.__file__).read_bytes() + b"\x00" +
                               Path(structured_models.__file__).read_bytes())

    results = []
    for item in manifest["samples"]:
        result = {"sample_id": item["sample_id"], "split": item["split"], "input_sha256": item["input_sha256"],
                  "status": "failed", "failure": None, "scored_files": 0, "unscored_files": 0,
                  "unscored_predictions": 0, "skipped_files": None}
        if item["state"] != "fixed":
            result["failure"] = "collection_failed"
            results.append(result)
            continue
        try:
            raw = (frozen / "snapshots" / f"{item['sample_id']}.zip").read_bytes()
            if _sha(raw) != item["input_sha256"]:
                raise ValueError("input_hash_mismatch")
            files, skipped, _license = _snapshot(raw)
            scored_files, labels, eligible_lines = {}, [], {}
            for locator, text in sorted(files.items()):
                oracle_result = oracle_file(locator, text)
                if oracle_result["unscored_constructs"]:
                    result["unscored_files"] += 1
                    continue
                if not oracle_result["eligible_lines"]:
                    result["unscored_files"] += 1
                    continue
                scored_files[locator] = text
                eligible_lines[locator] = oracle_result["eligible_lines"]
                labels.extend(oracle_result["labels"])
            result["scored_files"] = len(scored_files)
            result["skipped_files"] = skipped
            if not scored_files:
                raise ValueError("no_scored_files")
            gold = {"schema": "openguard.auto-static-gold/1", "sample_id": item["sample_id"],
                    "input_sha256": item["input_sha256"], "oracle_version": ORACLE_VERSION,
                    "scope": "bounded_static_literals", "labels": labels,
                    "eligible_lines": eligible_lines,
                    "scored_files": sorted(scored_files), "unscored_files": result["unscored_files"]}
            gold_path = frozen / "gold" / f"{item['sample_id']}.json"
            gold_bytes = _json_bytes(gold)
            if gold_path.exists():
                if gold_path.read_bytes() != gold_bytes:
                    raise ValueError("frozen_gold_drift")
                gold_hash = _sha(gold_bytes)
            else:
                gold_hash = _write_once(gold_path, gold)
            candidates = detect_static_asset_candidates(scored_files)
            if any(candidate.review_status != "review_required" or candidate.authorization_status.value != "pending"
                   for candidate in candidates):
                raise ValueError("candidate_status_invalid")
            all_predictions = [{"locator": candidate.locator, "line": candidate.start_line,
                            "resource_type": candidate.resource_type.value, "provider": candidate.provider,
                            "name": candidate.name, "source_url": candidate.source_url,
                            "evidence_id": candidate.evidence_id, "evidence_sha256": candidate.evidence_sha256,
                            "rule_version": candidate.rule_version, "review_status": candidate.review_status,
                            "authorization_status": candidate.authorization_status.value}
                           for candidate in candidates if candidate.start_line is not None]
            predictions = [candidate for candidate in all_predictions
                           if candidate["line"] in eligible_lines.get(candidate["locator"], ())]
            result["unscored_predictions"] = len(all_predictions) - len(predictions)
            prediction = {"schema": "openguard.auto-static-prediction/1", "sample_id": item["sample_id"],
                          "input_sha256": item["input_sha256"], "detector_version": _PRODUCER.version,
                          "rule_version": _PRODUCER.version, "detector_source_sha256": detector_source_sha,
                          "config_sha256": config_sha,
                          "gold_sha256": gold_hash, "labels": predictions}
            result["prediction_sha256"] = _write_once(frozen / "predictions" / run_id / f"{item['sample_id']}.json", prediction)
            result.update(_score(labels, predictions, item["sample_id"], item["split"], scored_files))
            result["gold_sha256"] = gold_hash
            result["status"] = "completed"
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
            result["failure"] = type(error).__name__ if str(error) not in {"input_hash_mismatch", "no_scored_files", "frozen_gold_drift"} else str(error)
        results.append(result)
    completed = [row for row in results if row["status"] == "completed"]
    by_split = {split: _summary([row for row in completed if row["split"] == split]) for split in ("train", "dev", "holdout")}
    errors = [error for row in completed for error in row["errors"]]
    fixed = sum(item["state"] == "fixed" for item in manifest["samples"])
    holdout_scored = sum(row["split"] == "holdout" for row in completed)
    evaluation_failures = sum(item["state"] == "fixed" and row["status"] == "failed"
                              for item, row in zip(manifest["samples"], results))
    scored_file_count = sum(row["scored_files"] for row in results)
    unscored_file_count = sum(row["unscored_files"] for row in results)
    scored_prediction_count = sum(row["tp"] + row["fp"] for row in completed)
    unscored_prediction_count = sum(row["unscored_predictions"] for row in results)
    metrics = {"schema": "openguard.auto-static-metrics/1", "run_id": run_id,
               "freeze_sha256": _sha(manifest_path.read_bytes()),
               "tier": "automated_static_subset", "bench_2_reportable": False,
               "runner_source_sha256": _runner_source_sha(),
               "automated_scope_ready": fixed >= 20 and holdout_scored >= 5 and len(completed) >= 20
               and evaluation_failures == 0
               and by_split["holdout"]["recall"] is not None,
               "total_samples": len(results), "fixed_samples": fixed, "completed_samples": len(completed),
               "failed_samples": len(results) - len(completed), "holdout_scored": holdout_scored,
               "collection_failed_samples": len(results) - fixed,
               "evaluation_failed_samples": evaluation_failures,
               "scored_files": scored_file_count,
               "unscored_files": unscored_file_count,
               "eligible_file_coverage": scored_file_count / (scored_file_count + unscored_file_count) if scored_file_count + unscored_file_count else None,
               "unscored_predictions": unscored_prediction_count,
               "prediction_scope_coverage": scored_prediction_count / (scored_prediction_count + unscored_prediction_count) if scored_prediction_count + unscored_prediction_count else None,
               "failure_rate": (len(results) - len(completed)) / len(results),
               "overall": _summary(completed), "splits": by_split, "errors": errors}
    metrics_sha = _write_once(frozen / "metrics" / f"{run_id}.json", metrics)
    receipt = {"schema": RUN_SCHEMA, "run_id": run_id, "created_at": _now(),
               "freeze_sha256": _sha(manifest_path.read_bytes()), "oracle_version": ORACLE_VERSION,
               "oracle_source_sha256": _oracle_source_sha(),
               "detector_version": _PRODUCER.version, "rule_version": _PRODUCER.version,
               "detector_source_sha256": detector_source_sha,
               "runner_source_sha256": _runner_source_sha(),
               "config_sha256": config_sha, "metrics_sha256": metrics_sha,
               "sample_results": results}
    _write_once(frozen / "runs" / f"{run_id}.json", receipt)
    return metrics


def audit(frozen: Path, run_id: str) -> dict:
    """Verify saved artifacts without fetching sources or running either labeler."""
    if not _ID.fullmatch(run_id):
        raise ValueError("invalid run ID")
    manifest_bytes = (frozen / "freeze.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    catalog_bytes = (frozen / "catalog.json").read_bytes()
    catalog = json.loads(catalog_bytes)
    validate_catalog(catalog)
    if manifest.get("schema") != FREEZE_SCHEMA or manifest.get("catalog_sha256") != _sha(catalog_bytes):
        raise ValueError("freeze/catalog hash mismatch")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or len(samples) != len(catalog["samples"]):
        raise ValueError("sample ledger mismatch")
    metrics_path = frozen / "metrics" / f"{run_id}.json"
    metrics_bytes = metrics_path.read_bytes()
    metrics = json.loads(metrics_bytes)
    receipt = _read_json(frozen / "runs" / f"{run_id}.json")
    freeze_sha = _sha(manifest_bytes)
    if (metrics.get("schema") != "openguard.auto-static-metrics/1" or metrics.get("run_id") != run_id
            or metrics.get("freeze_sha256") != freeze_sha or receipt.get("schema") != RUN_SCHEMA
            or receipt.get("run_id") != run_id or receipt.get("freeze_sha256") != freeze_sha
            or receipt.get("metrics_sha256") != _sha(metrics_bytes)
            or receipt.get("oracle_version") != manifest.get("oracle_version")
            or receipt.get("oracle_source_sha256") != manifest.get("oracle_source_sha256")):
        raise ValueError("metrics receipt mismatch")
    results = receipt.get("sample_results")
    if not isinstance(results, list) or len(results) != len(samples):
        raise ValueError("sample ledger mismatch")
    completed, fixed, collection_failed, evaluation_failed, repeated_match_keys = [], 0, 0, 0, 0
    for source, sample, result in zip(catalog["samples"], samples, results):
        if (not isinstance(sample, dict) or not isinstance(result, dict)
                or any(sample.get(key) != source[key] for key in ("sample_id", "family_id", "split", "url", "ref"))
                or any(result.get(key) != sample.get(key) for key in ("sample_id", "split", "input_sha256"))):
            raise ValueError("sample ledger mismatch")
        sample_id = source["sample_id"]
        if sample.get("state") == "failed":
            collection_failed += 1
            if not sample.get("failure") or result.get("status") != "failed" or result.get("failure") != "collection_failed":
                raise ValueError("failed sample ledger mismatch")
            if (frozen / "snapshots" / f"{sample_id}.zip").exists():
                raise ValueError("failed sample has an unrecorded snapshot")
            continue
        if sample.get("state") != "fixed" or not isinstance(sample.get("commit_sha"), str) or not _SHA.fullmatch(sample["commit_sha"]):
            raise ValueError("sample ledger mismatch")
        fixed += 1
        raw = (frozen / "snapshots" / f"{sample_id}.zip").read_bytes()
        if _sha(raw) != sample.get("input_sha256"):
            raise ValueError("input hash mismatch")
        if result.get("status") != "completed":
            evaluation_failed += 1
            if result.get("status") != "failed" or not result.get("failure"):
                raise ValueError("failed sample ledger mismatch")
            continue
        gold_path = frozen / "gold" / f"{sample_id}.json"
        gold_bytes = gold_path.read_bytes()
        if _sha(gold_bytes) != result.get("gold_sha256"):
            raise ValueError("gold hash mismatch")
        prediction_path = frozen / "predictions" / run_id / f"{sample_id}.json"
        prediction_bytes = prediction_path.read_bytes()
        if _sha(prediction_bytes) != result.get("prediction_sha256"):
            raise ValueError("prediction hash mismatch")
        gold, prediction = json.loads(gold_bytes), json.loads(prediction_bytes)
        if (gold.get("schema") != "openguard.auto-static-gold/1" or gold.get("sample_id") != sample_id
                or gold.get("input_sha256") != sample["input_sha256"]
                or gold.get("oracle_version") != receipt.get("oracle_version")
                or prediction.get("schema") != "openguard.auto-static-prediction/1"
                or prediction.get("sample_id") != sample_id
                or prediction.get("input_sha256") != sample["input_sha256"]
                or prediction.get("gold_sha256") != result["gold_sha256"]
                or prediction.get("detector_version") != receipt.get("detector_version")
                or prediction.get("rule_version") != receipt.get("rule_version")
                or prediction.get("detector_source_sha256") != receipt.get("detector_source_sha256")
                or prediction.get("config_sha256") != receipt.get("config_sha256")):
            raise ValueError("artifact identity mismatch")
        gold_labels, predicted_labels = gold.get("labels"), prediction.get("labels")
        if not isinstance(gold_labels, list) or not isinstance(predicted_labels, list):
            raise ValueError("invalid label list")
        actual = {_identity(label) for label in gold_labels}
        predicted = {_identity(label) for label in predicted_labels}
        repeated_match_keys += len(predicted_labels) - len(predicted)
        if (len(actual) != len(gold_labels)
                or any(label.get("review_status") != "review_required" or label.get("authorization_status") != "pending"
                       for label in predicted_labels)
                or (result.get("tp"), result.get("fp"), result.get("fn")) !=
                (len(actual & predicted), len(predicted - actual), len(actual - predicted))):
            raise ValueError("sample score mismatch")
        expected_errors = {
            "fn_" + _sha(repr((sample_id, key)).encode())[:16]: ("FN", key)
            for key in actual - predicted
        }
        expected_errors.update({
            "fp_" + _sha(repr((sample_id, key)).encode())[:16]: ("FP", key)
            for key in predicted - actual
        })
        errors = result.get("errors")
        if (not isinstance(errors, list) or len(errors) != len(expected_errors)
                or any(not isinstance(error, dict) or error.get("error_id") not in expected_errors
                       or not isinstance(error.get("label"), dict)
                       or (error.get("kind"), _identity(error["label"])) != expected_errors[error["error_id"]]
                       or error.get("sample_id") != sample_id or error.get("split") != sample["split"]
                       for error in errors)):
            raise ValueError("sample error ledger mismatch")
        completed.append(result)
    by_split = {split: _summary([row for row in completed if row["split"] == split])
                for split in ("train", "dev", "holdout")}
    scored_files = sum(row["scored_files"] for row in results)
    unscored_files = sum(row["unscored_files"] for row in results)
    unscored_predictions = sum(row["unscored_predictions"] for row in results)
    scored_predictions = sum(row["tp"] + row["fp"] for row in completed)
    holdout_count = sum(row["split"] == "holdout" for row in completed)
    expected = {"total_samples": len(results), "fixed_samples": fixed,
                "completed_samples": len(completed), "failed_samples": len(results) - len(completed),
                "holdout_scored": holdout_count, "collection_failed_samples": collection_failed,
                "evaluation_failed_samples": evaluation_failed, "scored_files": scored_files,
                "unscored_files": unscored_files,
                "eligible_file_coverage": scored_files / (scored_files + unscored_files) if scored_files + unscored_files else None,
                "unscored_predictions": unscored_predictions,
                "prediction_scope_coverage": scored_predictions / (scored_predictions + unscored_predictions) if scored_predictions + unscored_predictions else None,
                "failure_rate": (len(results) - len(completed)) / len(results),
                "overall": _summary(completed), "splits": by_split,
                "errors": [error for row in completed for error in row["errors"]],
                "automated_scope_ready": fixed >= 20 and holdout_count >= 5 and len(completed) >= 20
                and evaluation_failed == 0 and by_split["holdout"]["recall"] is not None}
    if (metrics.get("tier") != "automated_static_subset" or metrics.get("bench_2_reportable") is not False
            or metrics.get("runner_source_sha256") != receipt.get("runner_source_sha256")
            or any(metrics.get(key) != value for key, value in expected.items())):
        raise ValueError("metrics aggregation mismatch")
    return {"status": "verified", "sample_count": len(samples), "fixed_count": fixed,
            "completed_count": len(completed), "failed_count": len(results) - len(completed),
            "holdout_count": holdout_count, "repeated_match_keys": repeated_match_keys}


def compare(before: Path, after: Path, rule_version: str, destination: Path) -> dict:
    old, new = _read_json(before), _read_json(after)
    if old.get("schema") != new.get("schema") or old.get("schema") != "openguard.auto-static-metrics/1":
        raise ValueError("incompatible metrics")
    if old["freeze_sha256"] != new["freeze_sha256"]:
        raise ValueError("different input corpus")
    audit(before.parent.parent, old["run_id"])
    audit(after.parent.parent, new["run_id"])
    def receipt_for(path: Path, metrics: dict) -> dict:
        receipt = _read_json(path.parent.parent / "runs" / f"{metrics['run_id']}.json")
        if receipt.get("schema") != RUN_SCHEMA or receipt.get("metrics_sha256") != _sha(path.read_bytes()) or receipt.get("freeze_sha256") != metrics["freeze_sha256"]:
            raise ValueError("metrics receipt mismatch")
        return receipt
    old_receipt, new_receipt = receipt_for(before, old), receipt_for(after, new)
    if old_receipt["config_sha256"] != new_receipt["config_sha256"]:
        raise ValueError("different scoring configurations")
    if rule_version != new_receipt["rule_version"]:
        raise ValueError("rule version is not bound to after run")
    old_errors = {item["error_id"]: item for item in old["errors"]}
    new_errors = {item["error_id"]: item for item in new["errors"]}
    result = {"schema": "openguard.auto-static-rule-change/1", "rule_version": rule_version,
              "before_metrics_sha256": _sha(before.read_bytes()), "after_metrics_sha256": _sha(after.read_bytes()),
              "before_run_id": old["run_id"], "after_run_id": new["run_id"],
              "before_detector_version": old_receipt["detector_version"],
              "after_detector_version": new_receipt["detector_version"],
              "before_rule_version": old_receipt["rule_version"],
              "config_sha256": new_receipt["config_sha256"],
              "resolved_fn_ids": sorted(key for key in old_errors.keys() - new_errors.keys() if old_errors[key]["kind"] == "FN"),
              "introduced_fp_ids": sorted(key for key in new_errors.keys() - old_errors.keys() if new_errors[key]["kind"] == "FP"),
              "holdout": {"before": old["splits"]["holdout"], "after": new["splits"]["holdout"]}}
    _write_once(destination, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freezing = commands.add_parser("freeze")
    freezing.add_argument("catalog", type=Path)
    freezing.add_argument("output", type=Path)
    freezing.add_argument("--reuse", type=Path, help="reuse and verify immutable records from a prior freeze")
    freezing.add_argument("--retry-failed", action="store_true", help="retry prior failures while retaining their revision link")
    running = commands.add_parser("evaluate")
    running.add_argument("frozen", type=Path)
    running.add_argument("run_id")
    auditing = commands.add_parser("audit")
    auditing.add_argument("frozen", type=Path)
    auditing.add_argument("run_id")
    diffing = commands.add_parser("compare")
    diffing.add_argument("before", type=Path)
    diffing.add_argument("after", type=Path)
    diffing.add_argument("rule_version")
    diffing.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            result = freeze(args.catalog, args.output, reuse_from=args.reuse, retry_failed=args.retry_failed)
            print(json.dumps({"fixed": sum(x["state"] == "fixed" for x in result["samples"]),
                              "failed": sum(x["state"] == "failed" for x in result["samples"])}))
        elif args.command == "evaluate":
            result = evaluate(args.frozen, args.run_id)
            print(json.dumps({key: result[key] for key in ("automated_scope_ready", "completed_samples", "failed_samples", "overall")}))
        elif args.command == "audit":
            print(json.dumps(audit(args.frozen, args.run_id)))
        else:
            result = compare(args.before, args.after, args.rule_version, args.output)
            print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"auto-static-bench: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
