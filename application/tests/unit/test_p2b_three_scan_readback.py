"""Closure checks for real TEST_ONLY API readbacks of controlled manifests."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "p2b"
READBACK = json.loads((ROOT / "three-scan-readback.json").read_text(encoding="utf-8"))
INDEX = json.loads((ROOT / "real-source-index.json").read_text(encoding="utf-8"))
DRAFT = json.loads((ROOT / "frontend-handoff-draft.json").read_text(encoding="utf-8"))


def test_three_real_scan_assessment_and_evidence_closures():
    assert READBACK["data_grade"] == "TEST_ONLY_REAL_ZIP_SCAN_AND_ASSESSMENT"
    assert READBACK["get_side_effect_free"] is True
    assert len(READBACK["cases"]) == 3
    for row, source, handoff in zip(READBACK["cases"], INDEX["cases"], DRAFT["cases"], strict=True):
        assert row["case_id"] == source["case_id"] == handoff["case_id"]
        assert row["scan_id"].startswith("scn_")
        assert row["scan_id"] == source["scan_id"] == handoff["object"]["scan_id"]
        assert row["resource_id"] == source["scan_object_id"] == handoff["object"]["object_id"]
        assert row["assessment_id"] == source["assessment_id"] == handoff["assessment_id"]
        assert row["assessment"]["version"] == 1 == source["assessment_version"]
        assert row["scan_status"] == "partial"
        assert "rules_stage_not_connected" in {error["code"] for error in row["scan_errors"]}
        assert row["resource"]["ecosystem"] == "npm"
        assert row["resource"]["version"] == source["exact_version"]
        assert row["resource"]["license_expression_id"] is None
        assert len(row["fixed_tag_observations"]) == 2
        for observed, expected_source in zip(row["fixed_tag_observations"], source["materials"], strict=True):
            assert observed["raw_byte_sha256"] == expected_source["content_sha256"]
            assert observed["git_blob_sha1"] == expected_source["git_blob_sha1"]
            assert observed["http_status"] == 200
            assert observed["request_url"] == observed["final_url"]
            assert "not_npm_release_or_applicability" in observed["meaning"]
        assert len(row["evidence"]) == 2
        assert set(row["resource"]["evidence_ids"]) == {e["body"]["id"] for e in row["evidence"]}
        assert row["resource"]["evidence_ids"] == source["evidence_ids"] == handoff["evidence_ids"]
        assert all(e["body"]["kind"] == "manifest_field" for e in row["evidence"])
        assert all(e["body"]["producer"]["name"] == "openguard.javascript-manifest" for e in row["evidence"])
        assert all(e["get_path"].startswith(row["scan_get_path"] + "/evidence/") for e in row["evidence"])
        parent = row["assessment"]["resource_evaluations"]
        assert len(parent) == 1 and parent[0]["resource_id"] == row["resource_id"]
        assert parent[0]["license_verified"] is False
        binding = row["p2"]["binding"]
        assert binding["scan_id"] == row["scan_id"]
        assert binding["assessment_id"] == row["assessment_id"]
        assert binding["assessment_version"] == row["assessment"]["version"]
        assert binding["facts_hash"] == row["assessment"]["facts_hash"]
        assert binding["usage_hash"] == row["assessment"]["usage_hash"]
        before = row["p2"]["before"]
        assert before["binding"] == binding and before["revision"] == 1
        assert before["usage"] == source["assessment_usage_values"] == handoff["usage"]["values"]
        assert before["resources"][0]["subject"] == {"resource_id": row["resource_id"],
                                                         "version": source["exact_version"]}
        assert before["resources"][0]["verification_state"] == "candidate_only"
        assert before["resources"][0]["state"] == "unknown"
        assert "upstream_source_attestation_missing" in before["resources"][0]["gaps"]
        assert all(not advice["basis_evidence_ids"] and not advice["rule_ids"]
                   for advice in before["resources"][0]["advice"])
        assert before["resources"][0]["evidence_source_hashes"] == {
            e["body"]["id"]: e["body"]["content_hash"]["value"] for e in row["evidence"]}
        assert row["p2"]["before_get_path"].endswith(
            f"/results/{before['result_id']}?assessment_version={binding['assessment_version']}")
        after = row["p2"]["after"]
        material = row["p2"]["material"]
        assert after["previous_result_id"] == before["result_id"]
        assert (before["revision"], after["revision"]) == (1, 2)
        assert after["binding"] == before["binding"]
        assert after["state"] == "pending"
        assert after["recomputed_resource_ids"] == [row["resource_id"]]
        assert after["reused_resource_ids"] == []
        assert material["material_id"] in after["material_ids"]
        assert material["material_id"] == source["material_ids"][0]
        assert material["source_sha256"] == next(m["content_sha256"] for m in source["materials"]
                                                 if m["role"] == "license_text")
        assert material["source_level"] == "user_supplied_unverified"
        assert material["parse_status"] == "text_observed"
        assert material["adoption_status"] == "adopted_as_unverified_observation"
        assert material["verification_state"] == "pending"
        assert material["completeness"] == "FULL_TEXT_CLAIMED"
        assert row["p2"]["summary"]["report_kind"] == "P2_COMPANION_NOT_FORMAL_REPORT"


def test_rejections_and_d4_old_result_are_bounded():
    expected = {"wrong_scan": (404, "p2_scan_not_found"),
                "wrong_assessment": (409, "p2_parent_binding_conflict"),
                "wrong_resource": (404, "p2_resource_not_found"),
                "wrong_version": (409, "p2_resource_version_conflict"),
                "wrong_evidence": (409, "p2_evidence_wrong_resource"),
                "invalid_filename": (422, "p2_unsupported_material_name")}
    for row in READBACK["cases"]:
        for label, (status, code) in expected.items():
            error = row["p2"]["errors"][label]
            assert (error["http_status"], error["error_code"]) == (status, code)
            assert error["details"]["state"] in {"rejected", "conflict"}
    express = READBACK["cases"][2]["p2"]
    before, after, material, summary = (express[x] for x in ("before", "after", "material", "summary"))
    assert before["result_id"] != after["result_id"]
    assert (before["revision"], after["revision"]) == (1, 2)
    assert after["previous_result_id"] == before["result_id"]
    assert after["binding"] == before["binding"]
    assert after["state"] == "pending"
    assert after["recomputed_resource_ids"] == [READBACK["cases"][2]["resource_id"]]
    assert after["reused_resource_ids"] == []
    assert material["material_id"] in after["material_ids"]
    assert material["source_level"] == "user_supplied_unverified"
    assert material["parse_status"] == "text_observed"
    assert material["adoption_status"] == "adopted_as_unverified_observation"
    assert material["verification_state"] == "pending"
    assert material["completeness"] == "FULL_TEXT_CLAIMED"
    assert summary["summary_id"] == after["companion_summary_id"]
    assert summary["result_sha256"] == after["result_sha256"]
    assert summary["report_kind"] == "P2_COMPANION_NOT_FORMAL_REPORT"
    assert DRAFT["status"] == "integration_draft_not_formal_api"
    assert DRAFT["required_a_receipts"]["npm_trusted_egress_policy_and_verifier"] is None
