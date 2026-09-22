"""Offline integrity and contract checks for the fixed P1 integration package."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/p1-integration-v1"


def load(name: str):
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validator(name: str):
    schemas = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "schemas/p1").glob("*.schema.json")}
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas.values())
    return Draft202012Validator(schemas[name + ".schema"], registry=registry, format_checker=FormatChecker())


def test_generator_and_all_file_hashes_are_reproducible():
    subprocess.run(["node", str(FIXTURE / "generate.mjs"), "--check"], cwd=ROOT, check=True)
    manifest = load("manifest.json")
    for row in [*manifest["sources"], *manifest["artifacts"]]:
        path = ROOT / row["path"] if "purpose" in row else FIXTURE / row["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
        if "purpose" in row:
            committed = subprocess.run(
                ["git", "show", f'{row["fixed_commit"]}:{row["path"]}'],
                cwd=ROOT, check=True, capture_output=True,
            ).stdout
            assert hashlib.sha256(committed).hexdigest() == row["commit_blob_sha256"]
        else:
            assert row["source_commits"] == [
                "23fae26485db2fe3449ec8e7cccc3af64a487002",
                "e2d8c016ef5f4cfcddd23abb0205ec41c7cf3db1",
            ]


def test_two_fixed_related_revisions_and_scan_states():
    manifest = load("manifest.json")
    revisions = [row["commit"] for row in manifest["revisions"]]
    assert len(revisions) == len(set(revisions)) == 2
    for commit in revisions:
        subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=ROOT, check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", revisions[0], revisions[1]], cwd=ROOT, check=True)
    scans = load("scans.json")
    assert scans["project_key"] == manifest["project"]["canonical_id"]
    assert [row["status"] for row in scans["items"]] == ["partial", "completed"]
    assert [row["revision"] for row in scans["items"]] == revisions


def test_real_finding_obligation_and_remediation_lineage():
    scans = load("scans.json")
    assessment = load("assessment.json")
    upstream = load("remediation-input.json")
    task = load("remediation-task.json")
    rules = json.loads((ROOT / "rules/license-obligations.yaml").read_text(encoding="utf-8"))
    finding = scans["items"][1]["findings"][0]
    obligation = assessment["obligations"][0]
    assert finding["code"] == "GAP_ROOT_NOTICE_MISSING" and finding["status"] == "review_required"
    assert finding["id"] in assessment["finding_ids"]
    assert obligation["rule_id"] in {row["id"] for row in rules["rules"]}
    assert obligation["fulfillment"] == "pending"
    assert task["origin"] == {"kind": "obligation", "source_pointer": "/obligations/0", "source_hash": canonical_digest(obligation)}
    assert upstream["derive_request"] == {"idempotency_key": "p1-fixed-notice-review-v1", "expected_facts_hash": assessment["facts_hash"]}
    assert upstream["eligible_origins"][0]["source_hash"] == task["origin"]["source_hash"]
    assert task["scan_id"] == assessment["scan_id"] == task["assessment_ref"]["scan_id"]
    validator("remediation-task").validate(task)


def test_graph_tiers_are_exact_closed_and_schema_valid():
    for size in (100, 300, 500):
        graph = load(f"graph-{size}.json")
        validator("resource-graph-view").validate(graph)
        node_ids = {node["id"] for node in graph["nodes"]}
        assert len(node_ids) == len(graph["nodes"]) == graph["coverage"]["node_count"] == size
        assert len({edge["id"] for edge in graph["edges"]}) == len(graph["edges"]) == graph["coverage"]["edge_count"]
        assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in graph["edges"])
        assert {"finding", "obligation", "evidence", "ai_asset", "component"} <= {node["kind"] for node in graph["nodes"]}


def test_history_has_205_schema_valid_records_and_both_revisions():
    history = load("history.json")
    check = validator("scan-history-item")
    assert history["count"] == len(history["items"]) == 205
    assert len({row["scan_id"] for row in history["items"]}) == 205
    for row in history["items"]:
        check.validate(row)
        assert row["finding_count"] == sum(row["summary"]["finding_counts"].values())
    assert {row["status"] for row in history["items"]} >= {"completed", "partial"}
    assert {row["revision"] for row in history["items"]} == {"23fae26485db2fe3449ec8e7cccc3af64a487002", "e2d8c016ef5f4cfcddd23abb0205ec41c7cf3db1"}


def test_report_v2_input_uses_real_profile_notice_facts_without_snapshot():
    value = load("report-v2-input.json")
    profile_manifest = json.loads((ROOT / value["resource_profile"]["source"]).read_text(encoding="utf-8"))
    notice_facts = json.loads((ROOT / value["notice_license_facts"]["source"]).read_text(encoding="utf-8"))
    profile = profile_manifest["records"][1]
    assert profile["case_id"] == value["resource_profile"]["case_id"]
    assert profile["license_expression_id"] is value["resource_profile"]["license_expression_id"] is None
    assert profile["authorization_status"] == value["resource_profile"]["authorization_status"] == "pending"
    fact_ids = {row["fact_id"] for row in notice_facts["facts"]}
    assert {"fact.root.openguard", "fact.dep.jackson-databind", "fact.dep.hamcrest", "fact.dep.mockito", "fact.ai.bert"} <= fact_ids
    assert value["policy"] == {"license_expression_autofill": False, "unknown_items_are_gaps": True, "requires_human_review": True}
    assert value["expected_consumer_result"]["report_snapshot_created"] is False
    assert not (FIXTURE / "report-v2-snapshot.json").exists()
