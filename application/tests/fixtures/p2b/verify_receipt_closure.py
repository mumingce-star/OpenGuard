"""Verify published readbacks offline; never open a data root or contact a service."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from app.p2.contract import Binding, Material, Result, Summary, digest, strict_json

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def verify(readback, index, draft):
    """Check DTOs, hashes and cross-document identities, without authenticating origin."""
    schema = strict_json((ROOT / "schemas/p2/contract-v1.schema.json").read_bytes())
    models = {"Binding": Binding, "Material": Material, "Result": Result, "Summary": Summary}

    def dto(name, body):
        models[name].model_validate(body)
        Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]}).validate(body)

    require(readback["data_grade"] == "TEST_ONLY_REAL_ZIP_SCAN_AND_ASSESSMENT", "data_grade_changed")
    require(len(readback["cases"]) == len(index["cases"]) == len(draft["cases"]) == 3, "case_closure")
    archive_spec = importlib.util.spec_from_file_location("p2b_controlled_archive", FIXTURES / "run_three_scans.py")
    archive_module = importlib.util.module_from_spec(archive_spec)
    archive_spec.loader.exec_module(archive_module)
    rows = []
    for row, source, handoff in zip(readback["cases"], index["cases"], draft["cases"], strict=True):
        p2 = row["p2"]
        binding = p2["binding"]
        dto("Binding", binding)
        sid, aid, rid = row["scan_id"], row["assessment_id"], row["resource_id"]
        require(row["case_id"] == source["case_id"] == handoff["case_id"], "case_identity")
        require(sid == binding["scan_id"] == source["scan_id"] == handoff["object"]["scan_id"], "scan_binding")
        require(aid == binding["assessment_id"] == source["assessment_id"] == handoff["assessment_id"], "assessment_binding")
        require(rid == row["resource"]["id"] == source["scan_object_id"] == handoff["object"]["object_id"], "resource_binding")
        require(row["resource"]["version"] == source["exact_version"] == handoff["object"]["version"], "resource_version")
        require(row["input_grade"] == "CONTROLLED_FIRST_PARTY_MANIFEST_ONLY", "input_grade_changed")
        # Published scans were acquired on POSIX. ZipInfo's creator OS differs on
        # Windows; pin that header to 3, preserving all file bytes and metadata.
        raw_archive = archive_module.archive(source["name"], source["exact_version"])
        output = io.BytesIO()
        manifest_hashes = {}
        with zipfile.ZipFile(io.BytesIO(raw_archive)) as original, zipfile.ZipFile(output, "w") as normalized:
            for info in original.infolist():
                body = original.read(info.filename)
                manifest_hashes[info.filename] = hashlib.sha256(body).hexdigest()
                info.create_system = 3
                normalized.writestr(info, body)
        require(hashlib.sha256(output.getvalue()).hexdigest() == row["archive_sha256"], "controlled_input_digest")
        require(row["scan_status"] == "partial" and row["scan_stage"] == "rules", "scan_terminal_changed")
        require(any(e["code"] == "rules_stage_not_connected" for e in row["scan_errors"]), "scan_gap_removed")
        require(binding["assessment_version"] == row["assessment"]["version"] == 1, "assessment_version")
        require(row["assessment"]["id"] == aid, "assessment_identity")
        for key in ("facts_hash", "usage_hash", "rule_version"):
            require(binding[key] == row["assessment"][key], "parent_hash_binding")
        scan_path = f"/api/v1/scans/{sid}"
        base = f"{scan_path}/assessments/{aid}/p2"
        suffix = f"?assessment_version={binding['assessment_version']}"
        require(row["scan_get_path"] == scan_path and row["resource_list_get_path"] == scan_path + "/resources", "scan_get_path")
        require(row["assessment_get_path"] == f"{scan_path}/assessments/{aid}", "assessment_get_path")
        require(p2["binding_get_path"] == base + "/binding", "binding_get_path")
        evidence = {e["body"]["id"]: e["body"] for e in row["evidence"]}
        require(len(evidence) == len(row["evidence"]) == 2, "evidence_identity")
        require(set(evidence) == set(row["resource"]["evidence_ids"]) == set(source["evidence_ids"]) == set(handoff["evidence_ids"]), "evidence_closure")
        for e in row["evidence"]:
            require(e["get_path"] == f"{scan_path}/evidence/{e['body']['id']}", "evidence_get_path")
            require(e["body"]["kind"] == "manifest_field", "manifest_only")
            require(e["body"]["content_hash"]["value"] == manifest_hashes[e["body"]["locator"].split(":", 1)[0]], "manifest_source_digest")
        hashes = {eid: e["content_hash"]["value"] for eid, e in evidence.items()}
        before, after = p2["before"], p2["after"]
        for label, result in (("before", before), ("after", after)):
            dto("Result", result)
            require(result["binding"] == binding and result["data_scope"] == "TEST_ONLY", "result_binding")
            payload = dict(result)
            expected = payload.pop("result_sha256")
            require(digest(payload) == expected, "result_digest")
            require(p2[label + "_get_path"] == f"{base}/results/{result['result_id']}{suffix}", "result_get_path")
            require(len(result["resources"]) == 1, "result_resource_closure")
            resource = result["resources"][0]
            require(resource["subject"] == {"resource_id": rid, "version": source["exact_version"]}, "result_subject")
            require(resource["evidence_source_hashes"] == hashes and set(resource["evidence_ids"]) == set(evidence), "result_evidence_hashes")
            require(resource["verification_state"] == "candidate_only" and result["formal_effect"] == "none", "formal_escalation")
            require(all(a["state"] != "conditional_candidate" and not a["basis_evidence_ids"] and not a["conditions"] for a in resource["advice"]), "untrusted_positive_advice")
        require(before["revision"] == 1 and after["revision"] == 2 and after["previous_result_id"] == before["result_id"], "result_revision_chain")
        require(before["state"] == "unknown" and after["state"] == "pending", "result_state")
        require(handoff["before"]["candidate_state"] == before["state"], "draft_before_state")
        require(handoff["before"]["gaps"] == sorted(set(before["resources"][0]["gaps"] + ["controlled_manifest_only"])), "draft_before_gaps")
        for label, result in (("before", before), ("after", after)):
            require(handoff["server_" + label] == {"result_id": result["result_id"], "revision": result["revision"],
                                                  "state": result["state"], "get_path": p2[label + "_get_path"]}, "draft_result_binding")
        require(before["usage"] == after["usage"] == source["assessment_usage_values"] == handoff["usage"]["values"], "usage_binding")
        material, summary = p2["material"], p2["summary"]
        dto("Material", material)
        dto("Summary", summary)
        require(material["binding"] == summary["binding"] == binding, "companion_binding")
        require(material["subject"] == after["resources"][0]["subject"] and set(material["evidence_ids"]) <= set(evidence), "material_binding")
        require(after["material_ids"] == after["resources"][0]["material_ids"] == source["material_ids"] == [material["material_id"]], "material_closure")
        license_source = next(m for m in source["materials"] if m["role"] == "license_text")
        require(material["source_sha256"] == license_source["content_sha256"], "material_digest")
        require(p2["material_get_path"] == f"{base}/materials/{material['material_id']}{suffix}", "material_get_path")
        require(p2["summary_get_path"] == f"{base}/results/{after['result_id']}/summary{suffix}", "summary_get_path")
        require(summary["summary_id"] == after["companion_summary_id"] and summary["result_id"] == after["result_id"], "summary_identity")
        require(summary["result_revision"] == after["revision"] and summary["result_sha256"] == after["result_sha256"], "summary_result_binding")
        require(summary["material_ids"] == after["material_ids"] and summary["answer_ids"] == after["answer_ids"] and summary["state"] == after["state"], "summary_closure")
        observations = row["fixed_tag_observations"]
        require(observations == source["new_fixed_tag_observations"], "source_observation_changed")
        for observed, expected_source in zip(observations, source["materials"], strict=True):
            require(observed["raw_byte_sha256"] == expected_source["content_sha256"] and observed["git_blob_sha1"] == expected_source["git_blob_sha1"], "tag_digest")
        rows.append({"case_id": row["case_id"], "input_grade": row["input_grade"], "archive_sha256": row["archive_sha256"],
                     "scan_id": sid, "scan_status": row["scan_status"], "scan_errors": row["scan_errors"],
                     "resource": row["resource"], "manifest_evidence": row["evidence"], "fixed_tag_observations": observations,
                     "binding": binding, "assessment_get_path": row["assessment_get_path"],
                     "material": material, "material_get_path": p2["material_get_path"],
                     "results": [{"result_id": r["result_id"], "revision": r["revision"], "result_sha256": r["result_sha256"],
                                  "get_path": p2[label + "_get_path"], "state": r["state"], "gaps": r["resources"][0]["gaps"]}
                                 for label, r in (("before", before), ("after", after))],
                     "summary": summary, "summary_get_path": p2["summary_get_path"],
                     "usage_hash": binding["usage_hash"], "usage_values": before["usage"],
                     "suggestions_added": [], "suggestions_removed": [], "suggestions_updated": [],
                     "basis_evidence_ids": [], "old_formal_report_readback": None, "full_assessment_readback": None,
                     "npm_release_applicability": "pending", "evidence_grade": "PUBLISHED_REAL_RECEIPTS_REVERIFIED_OFFLINE"})
    return {"kind": "openguard.p2b.receipt-closure/1", "overall": "PARTIAL", "owner_review": "pending",
            "verification": "offline_DTO_schema_digest_and_reference_checks_not_live_GET",
            "data_scope": "TEST_ONLY", "express_rule_tuning": False, "cases": rows}


def main():
    inputs = [strict_json((FIXTURES / name).read_bytes()) for name in
              ("three-scan-readback.json", "real-source-index.json", "frontend-handoff-draft.json")]
    print(json.dumps(verify(*inputs), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
