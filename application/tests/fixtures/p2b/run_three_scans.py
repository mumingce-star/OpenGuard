"""Replay three controlled first-party manifests through the real ZIP and Assessment APIs.

This does not install npm packages or assert that upstream tag files belong to
the scanned objects. Run on POSIX with PYTHONPATH=backend. Data stays TEST_ONLY.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.zip_scan import ZipScanRuntime
from app.assessment.service import AssessmentService
from app.assessment.store import AssessmentStore
from app.persistence import SQLiteScanRunRegistry


CASES = (
    ("P2B-POS-ISNUMBER-7", "is-number", "7.0.0", "closed_source"),
    ("P2B-LIMIT-LODASH-41721", "lodash", "4.17.21", "unknown"),
    ("P2B-HOLDOUT-EXPRESS-4182", "express", "4.18.2", "service"),
)


def private(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def archive(name: str, version: str) -> bytes:
    # The exact package version is a first-party declaration, not an installed package.
    manifest = {"name": "openguard-p2b-controlled-input", "private": True,
                "dependencies": {name: version}}
    lock = {"name": manifest["name"], "lockfileVersion": 3,
            "packages": {"": manifest, f"node_modules/{name}": {"version": version}}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as z:
        for filename, value in (("package.json", manifest), ("package-lock.json", lock)):
            payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
            info = zipfile.ZipInfo(filename, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            z.writestr(info, payload)
    return stream.getvalue()


def acquire_fixed_tag_materials(source_case: dict) -> tuple[list[dict], bytes]:
    """Read exact upstream tag bytes; these are not npm release/applicability evidence."""
    observations = []
    license_bytes = None
    for entry in source_case["materials"]:
        url = entry["url"].replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/", 1)
        assert url.startswith("https://raw.githubusercontent.com/")
        for attempt in range(3):
            try:
                with urlopen(url, timeout=20) as response:
                    raw = response.read(65537)
                    assert response.status == 200 and len(raw) <= 65536
                    final_url = response.geturl()
                    assert final_url == url, (url, final_url)
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        sha256 = hashlib.sha256(raw).hexdigest()
        blob_sha1 = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert sha256 == entry["content_sha256"] and blob_sha1 == entry["git_blob_sha1"], url
        observations.append({"role": entry["role"], "request_url": url, "final_url": final_url,
                             "http_status": 200, "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                             "byte_count": len(raw), "raw_byte_sha256": sha256, "git_blob_sha1": blob_sha1,
                             "meaning": "fixed_upstream_git_tag_file_bytes_not_npm_release_or_applicability"})
        if entry["role"] == "license_text":
            license_bytes = raw
    assert license_bytes is not None
    return observations, license_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--p2", action="store_true", help="exercise A candidate P2 API when available")
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--handoff-draft", type=Path)
    parser.add_argument("--acquire-fixed-tags", action="store_true")
    args = parser.parse_args()
    root = private(args.data_root.absolute())
    uploads, workspaces = private(root / "uploads"), private(root / "workspaces")
    registry = SQLiteScanRunRegistry(root / "scans.sqlite")
    assessment = AssessmentService(registry, AssessmentStore(root / "assessment.db", min_free_bytes=0))
    assessment.initialize()
    runtime = ZipScanRuntime(registry, upload_root=uploads, workspace_root=workspaces)
    p2_service = None
    if args.p2:
        from app.p2.service import P2Service
        from app.p2.store import P2Store
        p2_store = P2Store(root / "p2.db")
        p2_store.initialize()
        p2_service = P2Service(registry, assessment.store, p2_store, data_scope="TEST_ONLY")
    app = create_app(registry, zip_runtime=runtime, assessment_service=assessment, p2_service=p2_service) if args.p2 else create_app(registry, zip_runtime=runtime, assessment_service=assessment)
    source_cases = None
    if args.acquire_fixed_tags:
        assert args.source_index and args.p2
        source_cases = json.loads(args.source_index.read_text(encoding="utf-8"))["cases"]
    results = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for case_number, (case_id, name, version, preset) in enumerate(CASES):
            observations, license_bytes = acquire_fixed_tag_materials(source_cases[case_number]) if source_cases else ([], None)
            raw = archive(name, version)
            submitted = client.post("/api/v1/scans", data={"source_type": "zip", "idempotency_key": case_id},
                                    files={"file": (f"{case_id}.zip", raw, "application/zip")})
            assert submitted.status_code == 202, (case_id, submitted.status_code, submitted.text)
            sid = submitted.json()["scan_id"]
            base = f"/api/v1/scans/{sid}"
            run_response = client.get(base)
            resources_response = client.get(base + "/resources")
            assert run_response.status_code == resources_response.status_code == 200
            run = run_response.json()
            matches = [x["resource"] for x in resources_response.json()["items"]
                       if x["resource"]["name"] == name and x["resource"]["version"] == version]
            assert len(matches) == 1, (case_id, resources_response.text)
            resource = matches[0]
            evidence = []
            for eid in resource["evidence_ids"]:
                path = base + "/evidence/" + eid
                response = client.get(path)
                assert response.status_code == 200, (path, response.text)
                evidence.append({"get_path": path, "body": response.json()})
            request_id = case_id + "-assessment-1"
            created = client.post(base + "/assessments", json={"request_id": request_id, "usage": {"preset": preset}})
            assert created.status_code == 202, (case_id, created.status_code, created.text)
            job = client.get(base + "/assessments/jobs/" + request_id)
            assert job.status_code == 200 and job.json()["status"] == "succeeded", job.text
            aid = job.json()["assessment_id"]
            assessment_path = base + "/assessments/" + aid
            assessment_response = client.get(assessment_path)
            assert assessment_response.status_code == 200, assessment_response.text
            assessed = assessment_response.json()
            record = {
                "case_id": case_id, "input_grade": "CONTROLLED_FIRST_PARTY_MANIFEST_ONLY",
                "archive_sha256": hashlib.sha256(raw).hexdigest(),
                "scan_id": sid, "scan_get_path": base, "scan_status": run["status"],
                "scan_stage": run["stage"], "scan_errors": run["errors"],
                "resource_id": resource["id"], "resource": resource,
                "resource_list_get_path": base + "/resources", "evidence": evidence,
                "assessment_id": aid, "assessment_get_path": assessment_path,
                "assessment": {key: assessed[key] for key in ("id", "version", "facts_hash", "usage_hash",
                                                            "rule_version", "resource_evaluations")},
                "fixed_tag_observations": observations,
            }
            if args.p2:
                p2_base = assessment_path + "/p2"
                binding_response = client.get(p2_base + "/binding")
                assert binding_response.status_code == 200, binding_response.text
                binding = binding_response.json()
                created_result = client.post(p2_base + "/results", json={
                    "binding": binding, "expected_revision": 0, "parent_result_id": None,
                    "idempotency_key": case_id + "-result-1"})
                assert created_result.status_code == 201, (case_id, created_result.text)
                before = created_result.json()["result"]
                version_query = f"?assessment_version={binding['assessment_version']}"
                before_path = p2_base + "/results/" + before["result_id"] + version_query
                assert client.get(before_path).json() == before
                record["p2"] = {"binding_get_path": p2_base + "/binding", "binding": binding,
                                "before_get_path": before_path, "before": before,
                                "errors": {}}
                # A deliberately wrong resource is an actual server rejection.
                head_index = client.get(p2_base + "/results" + version_query).json()
                current = client.get(p2_base + "/results/" + head_index["head_result_id"] + version_query).json()
                material_request = {
                    "binding": binding, "expected_revision": current["revision"],
                    "parent_result_id": current["result_id"], "idempotency_key": case_id + "-wrong-resource",
                    "subject": before["resources"][0]["subject"],
                    "evidence_ids": resource["evidence_ids"][:1], "filename": "LICENSE",
                    "content_base64": base64.b64encode(b"Controlled input only.").decode(),
                    "source_sha256": hashlib.sha256(b"Controlled input only.").hexdigest(),
                    "source_description": "Controlled first-party input, not upstream", "completeness": "EXCERPT"}
                negatives = {
                    "wrong_scan": (p2_base.replace(sid, "scn_00000000-0000-4000-8000-000000000000", 1), material_request),
                    "wrong_assessment": (p2_base, {**material_request, "binding": {**binding, "assessment_id": "asm_nonexistent"}}),
                    "wrong_resource": (p2_base, {**material_request, "subject": {**material_request["subject"], "resource_id": "cmp_wrong_resource"}}),
                    "wrong_version": (p2_base, {**material_request, "subject": {**material_request["subject"], "version": "0.0.0"}}),
                    "wrong_evidence": (p2_base, {**material_request, "evidence_ids": ["evd_nonexistent"]}),
                    "invalid_filename": (p2_base, {**material_request, "filename": "README"}),
                }
                for label, (path, payload) in negatives.items():
                    response = client.post(path + "/materials", json={**payload,
                        "idempotency_key": case_id + "-" + label})
                    assert response.status_code >= 400, (label, response.text)
                    error = response.json()["error"]
                    record["p2"]["errors"][label] = {"http_status": response.status_code,
                                                       "error_code": error["code"], "details": error["details"]}
                if license_bytes is not None or name == "express":
                    # Fixed tag bytes are real; A still records unverified user-supplied material.
                    raw_material = license_bytes if license_bytes is not None else b"MIT License\nControlled first-party observation; upstream applicability unverified.\n"
                    source_url = observations[-1]["request_url"] if observations else "Controlled first-party excerpt; not upstream LICENSE"
                    subject = before["resources"][0]["subject"]
                    submitted_material = client.post(p2_base + "/materials", json={
                        "binding": binding, "expected_revision": before["revision"],
                        "parent_result_id": before["result_id"], "idempotency_key": case_id + "-material-1",
                        "subject": subject, "evidence_ids": resource["evidence_ids"][:1],
                        "filename": "LICENSE", "content_base64": base64.b64encode(raw_material).decode(),
                        "source_sha256": hashlib.sha256(raw_material).hexdigest(),
                        "source_description": source_url + "; fixed tag file only; npm inclusion and applicability unverified",
                        "completeness": "FULL_TEXT_CLAIMED" if license_bytes is not None else "EXCERPT"})
                    assert submitted_material.status_code == 201, submitted_material.text
                    after = submitted_material.json()["result"]
                    material = submitted_material.json()["material"]
                    after_path = p2_base + "/results/" + after["result_id"] + version_query
                    summary_path = p2_base + "/results/" + after["result_id"] + "/summary" + version_query
                    material_path = p2_base + "/materials/" + material["material_id"] + version_query
                    assert client.get(after_path).json() == after
                    assert client.get(before_path).json() == before
                    record["p2"].update(after=after, after_get_path=after_path,
                                        material=client.get(material_path).json(), material_get_path=material_path,
                                        summary=client.get(summary_path).json(), summary_get_path=summary_path)
            results.append(record)
        database_paths = [root / "scans.sqlite", root / "assessment.db"]
        if args.p2:
            database_paths.append(root / "p2.db")
        before_get_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in database_paths}
        for record in results:
            paths = [record["scan_get_path"], record["resource_list_get_path"],
                     record["assessment_get_path"], *(e["get_path"] for e in record["evidence"])]
            if args.p2:
                paths.extend([record["p2"]["binding_get_path"], record["p2"]["before_get_path"]])
                paths.extend(record["p2"].get(key) for key in ("after_get_path", "material_get_path", "summary_get_path")
                             if record["p2"].get(key))
            for path in paths:
                response = client.get(path)
                assert response.status_code == 200, (path, response.text)
        after_get_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in database_paths}
        assert before_get_hashes == after_get_hashes, "GET mutated a persisted database"
    registry.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"kind": "openguard.p2b.three-scan-readback/1",
                                       "data_grade": "TEST_ONLY_REAL_ZIP_SCAN_AND_ASSESSMENT",
                                       "get_side_effect_free": True,
                                       "database_sha256_after_get": after_get_hashes,
                                       "cases": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.source_index:
        index = json.loads(args.source_index.read_text(encoding="utf-8"))
        for entry, record in zip(index["cases"], results, strict=True):
            assert entry["case_id"] == record["case_id"]
            entry.update(scan_id=record["scan_id"], scan_object_id=record["resource_id"],
                         assessment_id=record["assessment_id"], assessment_version=record["assessment"]["version"],
                         facts_hash=record["assessment"]["facts_hash"], usage_hash=record["assessment"]["usage_hash"],
                         assessment_usage_values=record.get("p2", {}).get("before", {}).get("usage"),
                         evidence_ids=record["resource"]["evidence_ids"],
                         material_ids=[record["p2"]["material"]["material_id"]] if record.get("p2", {}).get("material") else [],
                         p2_before_result_id=record.get("p2", {}).get("before", {}).get("result_id"),
                         p2_after_result_id=record.get("p2", {}).get("after", {}).get("result_id"),
                         p2_summary_id=record.get("p2", {}).get("summary", {}).get("summary_id"),
                         scan_input_grade="CONTROLLED_FIRST_PARTY_MANIFEST_ONLY", scan_status=record["scan_status"],
                         scan_readback_path=record["scan_get_path"])
            entry["new_fixed_tag_observations"] = record["fixed_tag_observations"]
            entry["unknowns"] = [x for x in entry["unknowns"]
                                  if x not in {"actual scan_id and object_id", "P0 Evidence binding"}]
            limitation = "controlled manifest does not prove installed or published npm package contents"
            if limitation not in entry["unknowns"]:
                entry["unknowns"].append(limitation)
        args.source_index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.handoff_draft:
        draft = json.loads(args.handoff_draft.read_text(encoding="utf-8"))
        for entry, record in zip(draft["cases"], results, strict=True):
            assert entry["case_id"] == record["case_id"]
            entry["object"].update(scan_id=record["scan_id"], object_id=record["resource_id"])
            entry["evidence_ids"] = record["resource"]["evidence_ids"]
            entry["material_ids"] = [record["p2"]["material"]["material_id"]] if record.get("p2", {}).get("material") else []
            entry["usage"] = {"values": record["p2"]["before"]["usage"],
                              "assessment_version": record["assessment"]["version"],
                              "usage_hash": record["assessment"]["usage_hash"],
                              "source": "A_assessment_readback"}
            entry["assessment_id"] = record["assessment_id"]
            entry["assessment_version"] = record["assessment"]["version"]
            entry["facts_hash"] = record["assessment"]["facts_hash"]
            entry["usage_hash"] = record["assessment"]["usage_hash"]
            entry["p2_before_result_id"] = record.get("p2", {}).get("before", {}).get("result_id")
            entry["p2_after_result_id"] = record.get("p2", {}).get("after", {}).get("result_id")
            entry["p2_summary_id"] = record.get("p2", {}).get("summary", {}).get("summary_id")
            entry["before"]["gaps"] = [x for x in entry["before"]["gaps"] if x != "real_scan_binding_missing"]
            entry["before"]["gaps"].extend(["controlled_manifest_only", "upstream_source_attestation_missing"])
            if record.get("p2"):
                entry["server_before"] = {"result_id": record["p2"]["before"]["result_id"],
                                          "revision": record["p2"]["before"]["revision"],
                                          "get_path": record["p2"]["before_get_path"],
                                          "state": record["p2"]["before"]["state"]}
                if record["p2"].get("after"):
                    entry["server_after"] = {"result_id": record["p2"]["after"]["result_id"],
                                             "revision": record["p2"]["after"]["revision"],
                                             "get_path": record["p2"]["after_get_path"],
                                             "state": record["p2"]["after"]["state"]}
                    entry["after"] = {"result_id": record["p2"]["after"]["result_id"],
                                      "revision": record["p2"]["after"]["revision"],
                                      "state": record["p2"]["after"]["state"],
                                      "verification_state": "candidate_only",
                                      "formal_effect": "none"}
            entry["readback_receipt"] = "tests/fixtures/p2b/three-scan-readback.json"
            entry["data_grade"] = "TEST_ONLY_REAL_ZIP_SCAN_WITH_CONTROLLED_MANIFEST"
            entry["review_status"] = "pending"
        draft["required_a_receipts"]["three_scan_runs_with_before_after_assessments"] = None
        missing = draft["observed_backend_candidate"]["missing_for_formal_handoff"]
        draft["observed_backend_candidate"]["missing_for_formal_handoff"] = [
            value for value in missing if value != "three_package_scan_and_evidence_bindings"]
        draft["three_case_scan_binding_receipt"] = "tests/fixtures/p2b/three-scan-readback.json"
        draft["formal_fields_pending_a"] = ["formal_report_id", "formal_report_readback_sha256",
                                            "trusted_upstream_applicability_attestation", "owner_acceptance",
                                            "frontend_compatible_sha", "official_npm_get_receipt"]
        draft["status"] = "integration_draft_not_formal_api"
        args.handoff_draft.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
