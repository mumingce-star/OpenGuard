"""只读复核 P1 固定来源和 train/dev 原证据；不裁决 Gold、不读取 holdout 个案。"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tomllib
import xml.etree.ElementTree as ET

from app.detectors.license_notice_facts import detect_license_notice_candidates
from benchmarks.auto_static_bench import _snapshot, audit
from benchmarks.auto_static_review import prepare_review_queue


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load(path: Path) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("nonfinite_json")

    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=invalid_constant)


def verify_case(case: dict, files: dict[str, str]) -> dict:
    """仅确认文件/行身份；机器 FN/FP 分类不能据此升级为错误裁决。"""
    if case["split"] not in {"train", "dev"}:
        raise ValueError("holdout_case_forbidden")
    text = files.get(case["locator"])
    if text is None:
        state, reason = "无法判断", "bounded_source_unavailable"
    elif sha(text.encode()) != case["evidence_sha256"]:
        raise ValueError("source_evidence_hash_mismatch")
    elif type(case["line"]) is not int or not 1 <= case["line"] <= len(text.splitlines()):
        raise ValueError("source_line_mismatch")
    else:
        state, reason = "待真人裁决", "source_bytes_and_line_verified_semantics_unadjudicated"
    return {**case, "source_verification": "verified" if state == "待真人裁决" else "unavailable",
            "triage_state": state, "triage_reason": reason, "confirmed_detector_error": False,
            "human_adjudication": None,
            "bounded_inventory_entry": {"path": case["locator"], "size_bytes": len(text.encode()),
                                        "sha256": sha(text.encode())} if text is not None else None,
            "a_terminal": None, "draft_report": None}


def review_sources(frozen: Path, run_id: str) -> dict:
    summary = audit(frozen, run_id)
    queue = prepare_review_queue(frozen, run_id, include_holdout=False)
    saved_path = frozen / "review-train-dev-v1.json"
    if load(saved_path) != queue:
        raise ValueError("saved_review_queue_mismatch")
    manifest = load(frozen / "freeze.json")
    cases_by_sample: dict[str, list] = {}
    for case in queue["cases"]:
        cases_by_sample.setdefault(case["sample_id"], []).append(case)
    cases, sources = [], []
    for sample in manifest["samples"]:
        sources.append({key: sample.get(key) for key in (
            "sample_id", "split", "state", "url", "commit_sha", "input_sha256", "failure")})
        if sample["sample_id"] not in cases_by_sample:
            continue
        if sample["split"] not in {"train", "dev"}:
            raise ValueError("holdout_case_forbidden")
        raw = (frozen / "snapshots" / f"{sample['sample_id']}.zip").read_bytes()
        if sha(raw) != sample["input_sha256"]:
            raise ValueError("input_hash_mismatch")
        files, _, _ = _snapshot(raw)
        prediction = load(frozen / "predictions" / run_id / f"{sample['sample_id']}.json")
        for case in cases_by_sample[sample["sample_id"]]:
            checked = verify_case(case, files)
            checked["prediction_evidence_ids"] = sorted({label["evidence_id"] for label in prediction["labels"]
                if all(label.get(key) == case[key] for key in (
                    "locator", "line", "resource_type", "provider", "name", "evidence_sha256"))})
            checked["inventory_scope"] = "bounded_static_source_not_A_inventory"
            cases.append(checked)
    return {"scope": "automated_static_subset", "integrity": summary,
            "freeze_sha256": queue["freeze_sha256"], "metrics_sha256": queue["metrics_sha256"],
            "receipt_sha256": queue["receipt_sha256"], "saved_queue_sha256": sha(saved_path.read_bytes()),
            "source_ledger": sources, "case_count": len(cases),
            "machine_kinds": dict(Counter(case["machine_kind"] for case in cases)),
            "triage_counts": {state: sum(case["triage_state"] == state for case in cases)
                              for state in ("已确认", "无法判断", "待真人裁决")},
            "cases": cases, "repeated_train_dev": queue["repeated_match_keys"],
            "failure_summary": queue["failure_summary"], "formal_gold": False,
            "holdout_case_read": False, "old_holdout_exposed": True,
            "rule_change_proposed": False, "ablation": None}


def fixture_chain(root: Path) -> dict:
    expected = load(root / "tests/fixtures/p1-integration-b-v1/expected.json")
    v2 = load(root / "tests/fixtures/notice-license-facts-v2/facts.json")
    # 外部固定预期来自已发布联验包，不以当前输入现场生成 pin。
    pinned = expected["source_package_sha256"]
    detected = detect_license_notice_candidates(v2, expected_package_sha256=pinned)
    v3_path = root / "tests/fixtures/notice-license-facts-v3/facts.json"
    v3 = load(v3_path)
    rows = []
    for version, package in (("v2", v2), ("v3", v3)):
        for fact in package["facts"]:
            refs = set(fact.get("fact_provenance_evidence_ids", []))
            for relation in fact["relationships"].values():
                refs.update(relation["evidence_ids"])
            evidence = [item for item in package["evidence"] if item["evidence_id"] in refs]
            if refs != {item["evidence_id"] for item in evidence}:
                raise ValueError("dangling_evidence")
            rows.append({"version": version, "fact_id": fact["fact_id"], "subject": fact["subject"],
                         "fact_sha256": sha(canonical(fact)), "package_sha256": sha(canonical(package)),
                         "relationships": fact["relationships"], "gaps": fact["gaps"],
                         "evidence": [{key: item.get(key) for key in (
                             "evidence_id", "locator", "source_revision", "source_file_sha256",
                             "container_sha256", "selected_content_sha256", "selected_json_pointer")}
                                      for item in evidence],
                         "candidate_ids": [item.candidate_id for item in detected.findings
                                           if version == "v2" and item.fact_id == fact["fact_id"]],
                         "inventory": None, "a_terminal": None, "draft_report": None,
                         "missing": ["A固定输入与inventory", "A终态与Evidence映射", "A同版本Draft/Report引用"]})
    git_sources, source_bytes = [], {}
    for source in v3["source_inputs"]:
        revision = source["source_revision"]
        if len(revision) == 40:
            raw = subprocess.run(["git", "show", f"{revision}:{source['path']}"], cwd=root,
                                 check=True, capture_output=True).stdout
        else:
            raw = (root / source["path"]).read_bytes()
        actual = sha(raw)
        source_bytes[source["path"]] = raw
        git_sources.append({**source, "actual_sha256": actual,
                            "state": "verified" if actual == source["source_file_sha256"] else "mismatch"})
    mismatched_paths = {item["path"] for item in git_sources if item["state"] == "mismatch"}
    affected = [item["evidence_id"] for item in v3["evidence"] if item["source_path"] in mismatched_paths]
    evidence_checks = []
    for item in v3["evidence"]:
        raw = source_bytes.get(item["source_path"])
        if raw is None:
            raw = (root / item["source_path"]).read_bytes()
        scope = item["content_scope"]
        if scope == "whole_file":
            selected = raw
        elif scope == "json_pointer_value":
            value = json.loads(raw)
            for token in item["selected_json_pointer"].split("/")[1:]:
                value = value[token.replace("~1", "/").replace("~0", "~")]
            selected = value.encode() if isinstance(value, str) else json.dumps(
                value, ensure_ascii=False, separators=(",", ":")).encode()
        elif scope == "toml_declaration":
            name = item["evidence_id"].rsplit(".", 1)[1]
            document = tomllib.loads(raw.decode())
            section = "development" if "optional-dependencies" in item["locator"] else "runtime"
            declarations = document["project"]["optional-dependencies"]["dev"] if section == "development" else document["project"]["dependencies"]
            declaration = next(value for value in declarations if value.split("==")[0] == name)
            selected = json.dumps({"section": section, "declaration": declaration}, separators=(",", ":")).encode()
        elif scope == "xml_dependency":
            artifact = item["evidence_id"].rsplit(".", 1)[1]
            xml = ET.fromstring(raw)
            dependencies = xml.findall("{*}dependencies/{*}dependency")
            dependency = next(value for value in dependencies if value.findtext("{*}artifactId") == artifact)
            version = dependency.findtext("{*}version")
            if version and version.startswith("${") and version.endswith("}"):
                # 仅解析同文件的显式属性，不运行 Maven 或继承/远程依赖解析。
                properties = xml.find("{*}properties")
                version = properties.findtext("{*}" + version[2:-1]) if properties is not None else None
            selected = json.dumps({"group_id": dependency.findtext("{*}groupId"), "artifact_id": artifact,
                                   "version": version, "scope": dependency.findtext("{*}scope")},
                                  separators=(",", ":")).encode()
        else:
            raise ValueError("unsupported_v3_hash_scope")
        evidence_checks.append({"evidence_id": item["evidence_id"], "source_file_sha256": sha(raw),
                                "selected_content_sha256": sha(selected),
                                "source_state": "verified" if sha(raw) == item["source_file_sha256"] else "mismatch",
                                "selected_state": "verified" if sha(selected) == item["selected_content_sha256"] else "mismatch"})
    for row in rows:
        if row["version"] == "v3":
            row["source_binding_state"] = "mismatch" if any(
                item["locator"].split("#")[0] in mismatched_paths for item in row["evidence"]
            ) else "source_hash_checked_or_external_observation"
    return {"scope": "preparation", "v2_findings": len(detected.findings),
            "v2_obligations": len(detected.obligations), "v3_facts": len(v3["facts"]),
            "git_source_checks": git_sources, "rows": rows,
            "candidates": [asdict(item) for item in detected.findings],
            "a_receipt_received": False, "v3_as_v2": False,
            "source_binding_affected_evidence": affected,
            "source_binding_accepted": not mismatched_paths,
            "v3_evidence_checks": evidence_checks}


def profile_sources(root: Path) -> list[dict]:
    result = []
    for provider, versions in (("huggingface", ("v1", "v2")), ("modelscope", ("v1",))):
        for version in versions:
            base = root / "tests/fixtures" / provider / f"resource-profile-{version}"
            manifest_path = base / "manifest.json"
            manifest = load(manifest_path)
            for record in manifest["records"] + manifest.get("counterexamples", []):
                path = Path(record["fixture"])
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("unsafe_profile_path")
                raw = (base / path).read_bytes()
                actual = sha(raw)
                if actual != record["source_file_sha256"]:
                    raise ValueError("profile_source_hash_mismatch")
                body = load(base / path)
                observed = record.get("observed")
                if observed and provider == "huggingface":
                    if body["payload"]["id"] != observed["canonical_id"] or body["payload"].get("sha") != observed.get("revision"):
                        raise ValueError("profile_identity_revision_mismatch")
                if observed and provider == "modelscope":
                    data = body["payload"]["Data"]
                    if f"{data['Namespace']}/{data['Name']}" != observed["canonical_id"]:
                        raise ValueError("profile_identity_revision_mismatch")
                result.append({"provider": provider, "fixture_version": version,
                               "manifest_sha256": sha(manifest_path.read_bytes()),
                               "case_id": record["case_id"], "source_file_sha256": actual,
                               "resource_kind": record.get("resource_kind", body.get("resource_kind")),
                               "identity": observed.get("canonical_id") if observed else None,
                               "revision": observed.get("revision") if observed else None,
                               "revision_quality": "synthetic_fixture_revision" if observed and
                                   observed.get("revision") and len(set(observed["revision"])) == 1 else
                                   "fixture_observed_not_independently_attested",
                               "source_url": body.get("source_url"),
                               "expected_source_url": f"https://huggingface.co/api/{record.get('resource_kind')}s/{observed['canonical_id']}"
                                   if observed and provider == "huggingface" else body.get("source_url"),
                               "source_fields_state": "snapshot_fields_only_not_transport_attestation",
                               "source_kind": body.get("source_kind", "offline_regression_fixture"),
                               "upstream_response_sha256": None,
                               "expected_error": record.get("expected_error"),
                               "expected_gaps": record.get("expected_gaps", []),
                               "independent_receipt": None, "independent_state": "待签收"})
    return result


def blind_source_packet(cases: list[dict]) -> dict:
    """移除预测答案，只给源文件入口；选择性队列不能变成总体 Gold。"""
    unique = {}
    for case in cases:
        if case["split"] not in {"train", "dev"}:
            raise ValueError("holdout_case_forbidden")
        identity = (case["sample_id"], case["locator"], case["evidence_sha256"])
        unique[identity] = {key: case[key] for key in (
            "source_repository", "commit_sha", "input_sha256", "locator", "evidence_sha256")}
    return {"schema": "openguard.p1-blind-source-review-preparation/1", "status": "preparation_not_gold",
            "formal_gold": False,
            "selection_bias": "机器分歧所在文件的选择性复核，不能估计总体Recall；无系统答案但不称正式Gold盲包",
            "task": "从固定源文件独立列出受限静态资源引用及理由；不猜运行、许可或授权",
            "reviewer_receipt": None,
            "records": [{"case_id": "source_" + sha(repr(identity).encode())[:16], **item, "judgment": None}
                        for identity, item in sorted(unique.items())]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blind-output", type=Path)
    args = parser.parse_args()
    root = Path.cwd()
    result = {"schema": "openguard.p1-b-offline-audit/1", "status": "PARTIAL",
              "environment": {"platform": platform.system(), "python": platform.python_version()},
              "head": subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                                     text=True).stdout.strip(),
              "formal_metrics": None, "formal_performance": None,
              "sources": review_sources(args.frozen, args.run_id), "fact_chain": fixture_chain(root),
              "profiles": profile_sources(root)}
    with args.output.open("xb") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")
    if args.blind_output:
        with args.blind_output.open("xb") as stream:
            stream.write(json.dumps(blind_source_packet(result["sources"]["cases"]), ensure_ascii=False,
                                    sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")
    print(json.dumps({"status": result["status"], "source_integrity": result["sources"]["integrity"],
                      "triage": result["sources"]["triage_counts"],
                      "git_sources": result["fact_chain"]["git_source_checks"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
