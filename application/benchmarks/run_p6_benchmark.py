#!/usr/bin/env python3
"""Evaluate the frozen P6 corpus through the real OpenGuard ASGI application.

Use the approved Python environment and a new TASK41 evidence directory. The
fixture root is its tmp-data directory. Paths and expected results are frozen in
the manifest; the runner never writes the manifest or uses an internet transport.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
from time import monotonic, perf_counter_ns
import traceback
import zipfile


PARENT = "ab2c1256c4a2efb8714cc90b9f39eda0fc5fc224"
SCHEMA = "openguard-p6-benchmark/1"
SPLITS = ("development", "independent_holdout")
USES = {"commercial", "distributed", "modified"}
STATES = {"SUPPORT", "RESTRICTION", "UNKNOWN", "COUNTER_EVIDENCE", "NOT_COVERED"}
PERF_ENDPOINTS = (
    "scan", "assessment_create", "material_upload", "material_claims_initial",
    "material_claims_incremental", "report_export",
)
SLUG = re.compile(r"[a-zA-Z0-9_-]{1,96}")
SHA256 = re.compile(r"[a-f0-9]{64}")


class CriticalError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_safety(condition, kind, message):
    if not condition:
        raise CriticalError(kind, message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def now():
    return datetime.now(timezone.utc).isoformat()


def no_duplicates(pairs):
    value = dict(pairs)
    require(len(value) == len(pairs), "Duplicate JSON fields")
    return value


def load(raw):
    return json.loads(raw, object_pairs_hook=no_duplicates)


def keyed(items, description):
    result = {item["id"]: item for item in items}
    require(len(result) == len(items), f"Duplicate {description} ID")
    require(all(SLUG.fullmatch(identity) for identity in result), f"Invalid {description} ID")
    return result


def path_beneath(root, relative):
    member = PurePosixPath(relative)
    require(not member.is_absolute() and ".." not in member.parts and member.parts,
            f"Unsafe fixture path: {relative}")
    path = root.joinpath(*member.parts)
    require(path.resolve(strict=True) == path, f"Aliased fixture path: {relative}")
    return path


def fixture_hashes(root, inventory):
    for name, record in inventory.items():
        path = path_beneath(root, name)
        require(path.is_file(), f"Expected a file: {name}")
        raw = path.read_bytes()
        require(len(raw) == record["bytes"] and sha(raw) == record["sha256"],
                f"Fixture integrity mismatch: {name}")


def fixture_ref(inventory, path, digest):
    require(path in inventory and inventory[path]["sha256"] == digest,
            f"Fixture was not frozen under the requested digest: {path}")


def read_manifest(manifest_path, frozen_sha, fixture_root):
    raw = manifest_path.read_bytes()
    require(SHA256.fullmatch(frozen_sha) and sha(raw) == frozen_sha, "Frozen manifest SHA-256 mismatch")
    manifest = load(raw)
    require(manifest["schema_version"] == SCHEMA, "Invalid manifest schema")
    require(manifest["data_scope"] == "TEST_ONLY" and manifest["parent_commit"] == PARENT,
            "Invalid scope or parent")
    projects = keyed(manifest["projects"], "project")
    scenarios = keyed(manifest["scenarios"], "scenario")
    cases = keyed(manifest["cases"], "case")
    require(Counter(project["split"] for project in projects.values()) ==
            {"development": 6, "independent_holdout": 2}, "Unexpected project split counts")
    require(len({(item["name"], item["version"]) for item in projects.values()}) == 8,
            "Duplicate project/package identity")
    require(len({(item["project_id"], item["scenario_id"], item["usage"]) for item in cases.values()})
            == len(cases) and len(cases) >= 40, "Benchmark needs at least 40 distinct project/scenario/usage cases")
    require({case["expected_state"] for case in cases.values()} == STATES, "Incomplete five-state corpus")
    fixture_hashes(fixture_root, manifest["fixtures"])
    for scenario in scenarios.values():
        require(scenario["project_id"] in projects and set(scenario["usage"]) == USES,
                "Invalid scenario project or usages")
        require(all(value is None or type(value) is bool for value in scenario["usage"].values()),
                "Invalid scenario usage declaration")
        fixture_ref(manifest["fixtures"], scenario["zip"]["path"], scenario["zip"]["sha256"])
        source = scenario["source"]
        if source is not None:
            source_root = path_beneath(fixture_root, source["root"])
            profile_path = (PurePosixPath(source["root"]) / "profile.json").as_posix()
            fixture_ref(manifest["fixtures"], profile_path, source["profile_sha256"])
            profile = load((source_root / "profile.json").read_bytes())
            require(profile["data_scope"] == "TEST_ONLY", "Source profile scope mismatch")
            for package in profile["packages"]:
                for stem in ("metadata", "tarball", "license"):
                    relative = (PurePosixPath(source["root"]) / package[f"{stem}_file"]).as_posix()
                    fixture_ref(manifest["fixtures"], relative, package[f"{stem}_sha256"])
        for action in scenario["actions"]:
            if action["type"] == "material":
                fixture_ref(manifest["fixtures"], action["path"], action["sha256"])
                require(re.fullmatch(r"(?i)(license|licence|notice)(\.(txt|md|rst))?", action["filename"]),
                        "Invalid benchmark material filename")
            else:
                require(action["type"] == "answer" and action["answer_code"] == "NOT_FULFILLED",
                        "Unexpected benchmark action")
    cases_by_scenario = {scenario_id: [] for scenario_id in scenarios}
    for case in cases.values():
        scenario = scenarios[case["scenario_id"]]
        require(case["project_id"] == scenario["project_id"] and case["usage"] in USES,
                "Case-to-scenario scope mismatch")
        require(type(case["support_scope_applicable"]) is bool and bool(case["ground_truth"]),
                "Missing frozen case annotation")
        cases_by_scenario[scenario["id"]].append(case)
    require(all(cases_by_scenario.values()), "Scenario without a frozen case")
    require({scenario["project_id"] for scenario in scenarios.values()} == set(projects),
            "Project without an evaluated scenario")
    performance = manifest["performance_scenarios"]
    require(bool(performance) and len(set(performance)) == len(performance)
            and all(any(action["type"] == "material" for action in scenarios[s]["actions"]) for s in performance),
            "Performance scenarios must exercise incremental material mutations")
    return manifest, projects, scenarios, cases_by_scenario


def audit_network(attempts):
    def audit(event, args):
        if event in {"socket.bind", "socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                     "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg"}:
            attempts.append(event)
            raise PermissionError("P6 evaluation prohibits network and listener operations")
    sys.addaudithook(audit)


def configure_app(root, scenario, fixture_root):
    for key in tuple(os.environ):
        if key.startswith("OPENGUARD_") or key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            del os.environ[key]
    os.environ.update({
        "OPENGUARD_DATA_DIR": str(root),
        "OPENGUARD_ENABLE_ASSESSMENTS": "1",
        "OPENGUARD_ENABLE_P2": "1",
        "OPENGUARD_P2_READONLY": "0",
        "OPENGUARD_P2_DATA_SCOPE": "TEST_ONLY",
        "OPENGUARD_ENABLE_AI": "0",
        "OPENGUARD_ENABLE_P2_AI": "0",
        "OPENGUARD_ENABLE_P2_CHAT": "0",
        "OPENGUARD_ENABLE_ASSISTANT": "0",
        "OPENGUARD_ENABLE_PUBLIC_GIT": "0",
        "OPENGUARD_ENABLE_EXTERNAL_SCANNERS": "0",
        "OPENGUARD_ENABLE_PROFILE_METADATA": "0",
        "OPENGUARD_ENABLE_DURABLE_ZIP": "0",
        "OPENGUARD_OFFICIAL_SOURCE_AUTO": "0",
        "OPENGUARD_OFFICIAL_JOBS_ENABLED": "0",
    })
    if scenario["source"] is not None:
        source = scenario["source"]
        os.environ["OPENGUARD_P2_PUBLIC_SOURCE_ROOT"] = str(path_beneath(fixture_root, source["root"]))
        os.environ["OPENGUARD_P2_PUBLIC_SOURCE_PROFILE_SHA256"] = source["profile_sha256"]
    from app.api.main import create_default_app
    return create_default_app(data_dir=root)


class ScenarioTrace:
    def __init__(self, folder, phase, round_number, scenario, split, deadline):
        self.folder = folder
        self.phase = phase
        self.round_number = round_number
        self.scenario = scenario["id"]
        self.split = split
        self.started_ns = perf_counter_ns()
        self.deadline = deadline
        self.exchanges = []
        folder.mkdir(mode=0o700, parents=True)

    def call(self, client, endpoint, method, path, status, **kwargs):
        if monotonic() >= self.deadline:
            raise TimeoutError("TASK41 execution budget expired")
        index = len(self.exchanges) + 1
        started = perf_counter_ns()
        try:
            response = client.request(method, path, **kwargs)
        except Exception as exc:
            self.exchanges.append({"endpoint": endpoint, "method": method, "path": path,
                                   "status": None, "elapsed_ms": elapsed(started),
                                   "error_type": type(exc).__name__})
            raise
        content = response.content
        attributes = {"endpoint": endpoint, "method": method, "path": path,
                      "status": response.status_code, "elapsed_ms": elapsed(started),
                      "sha256": sha(content), "bytes": len(content)}
        is_json = "json" in response.headers.get("content-type", "")
        address = f"{index:02d}-{endpoint}." + ("json" if is_json else "zip")
        (self.folder / address).write_bytes(content)
        attributes["response"] = address
        self.exchanges.append(attributes)
        require(response.status_code == status, f"{self.scenario} {endpoint}: HTTP {response.status_code}")
        if monotonic() >= self.deadline:
            raise TimeoutError("TASK41 execution budget expired")
        return response

    def json(self, *args, **kwargs):
        return self.call(*args, **kwargs).json()

    def record(self, status):
        return {"status": status, "phase": self.phase, "round": self.round_number,
                "scenario_id": self.scenario, "split": self.split, "elapsed_ms": elapsed(self.started_ns),
                "exchanges": self.exchanges}


def elapsed(started):
    return (perf_counter_ns() - started) / 1_000_000


def exact_subject(scan, project):
    found = [component for component in scan["components"]
             if component["name"] == project["name"] and component["version"] == project["version"]
             and component["component_type"] == "application"]
    require(len(found) == 1, f"No unique genuine scan root for {project['id']}")
    return {"resource_id": found[0]["id"], "version": found[0]["version"]}


def scan_closure(scan):
    licenses = {item["id"]: set(item["evidence_ids"]) for item in scan["licenses"]}
    return {
        item["id"]: (item.get("version"), set(item["evidence_ids"]) | licenses.get(item.get("license_expression_id"), set()))
        for item in scan["components"] + scan["ai_assets"]
    }


def collect_binding_counts(scan, result):
    closure = scan_closure(scan)
    source_hashes = {item["id"]: (item["content_hash"] or {}).get("value") for item in scan["evidence"]}
    reliable_pairs = 0
    check_safety({row["subject"]["resource_id"] for row in result["resources"]} == set(closure),
                 "USED_RESOURCE_EXCLUDED", "Saved Result omits or adds ScanRun resources")
    for row in result["resources"]:
        subject = row["subject"]
        version, allowed_ids = closure[subject["resource_id"]]
        check_safety(subject["version"] == version and set(row["evidence_ids"]) <= allowed_ids,
                     "CROSS_OBJECT_OR_VERSION_BINDING", "Saved Result resource/version Evidence closure diverged")
        for eid, digest in row["evidence_source_hashes"].items():
            check_safety(eid in allowed_ids and (digest is None or digest == source_hashes[eid]),
                         "CROSS_OBJECT_OR_VERSION_BINDING", "Saved Evidence hash is outside its own ScanRun closure")
            reliable_pairs += digest is not None
    return {"discovered_resources": len(closure), "generated_evidence_records": len(source_hashes),
            "hash_verified_resource_evidence_links": reliable_pairs}


def case_view(trace, client, url, result, endpoint):
    view = trace.json(client, endpoint, "GET", url + "/material-claims", 200,
                      params={"assessment_version": result["binding"]["assessment_version"]})
    require(view["schema_version"] == "openguard-material-claims/4", "Unexpected material-claims contract")
    check_safety(
        (view["result_id"], view["result_sha256"], view["revision"], view["binding"], view["data_scope"])
        == (result["result_id"], result["result_sha256"], result["revision"], result["binding"], "TEST_ONLY"),
        "CROSS_OBJECT_OR_VERSION_BINDING", "v4 view has wrong Result, Assessment or scope",
    )
    require(view["model_calls"] == result["model_calls"] == 0, "Unexpected model accounting")
    check_safety(view["formal_effect"] == "none" and view["applicability_review"] == "NOT_SIGNED",
                 "UNSAFE_SUPPORT", "v4 overstates formal effect or human verification")
    rows = {row["subject"]["resource_id"]: row for row in result["resources"]}
    expected_pairs = {(rid, use) for rid in rows for use in USES}
    observed_claims = {(claim["subject"]["resource_id"], claim["usage"]): claim for claim in view["claims"]}
    observed_advice = {(item["subject"]["resource_id"], item["usage"]): item for item in view["advice"]}
    check_safety(
        set(observed_claims) == set(observed_advice) == expected_pairs
        and len(observed_claims) == len(view["claims"]) == len(view["advice"]),
        "USED_RESOURCE_EXCLUDED", "v4 claim/advice omits or duplicates a resource/usage pair",
    )
    materials = {item["material_id"]: item for item in view["materials"]}
    check_safety(set(materials) == set(result["material_ids"]),
                 "CROSS_OBJECT_OR_VERSION_BINDING", "v4 materials diverged from saved Result")
    for rid, use in expected_pairs:
        row = rows[rid]
        claim = observed_claims[rid, use]
        advice = observed_advice[rid, use]
        check_safety(
            claim["subject"] == advice["subject"] == row["subject"]
            and advice["claim_ids"] == [claim["claim_id"]]
            and claim["state"] == advice["state"]
            and set(claim["material_ids"]) <= set(row["material_ids"])
            and all(materials[mid]["subject"] == row["subject"] for mid in claim["material_ids"])
            and all(evidence["evidence_id"] in row["evidence_ids"]
                    and row["evidence_source_hashes"].get(evidence["evidence_id"]) == evidence["source_sha256"]
                    for evidence in claim["evidence"]),
            "CROSS_OBJECT_OR_VERSION_BINDING", f"Invalid v4 Evidence/material closure for {rid} / {use}",
        )
        selected = result["usage"][use]
        check_safety(
            not (selected is True and row["resource_kind"] == "component" and advice["state"] == "NOT_COVERED"),
            "USED_RESOURCE_EXCLUDED", f"Selected component excluded for {rid} / {use}",
        )
        if advice["state"] != "SUPPORT":
            continue
        source = next((item for item in view["source_observations"] if item["subject"] == row["subject"]), None)
        declaration = next((item for item in view["declaration_observations"]
                            if item["subject"] == row["subject"]), None)
        check_safety(
            selected is True and row["resource_kind"] == "component" and endpoint != "material_claims_initial"
            and source is not None and source["notice_status"] == "ABSENT_COMPLETE"
            and declaration is not None and declaration["evidence_status"] == "COMPLETE"
            and row["user_assertions"].get("OBLIGATION_FULFILLMENT_IN_DELIVERY") != "NOT_FULFILLED"
            and bool(claim["clause_ids"]) and bool(claim["material_ids"]) and not claim["counter_evidence"],
            "UNSAFE_SUPPORT", f"SUPPORT lacks selected exact-source basis or ignores a restriction for {rid} / {use}",
        )
        declared = declaration["expression"]
        check_safety(declared in {"MIT", "Apache-2.0"}, "UNSAFE_SUPPORT", "Unsupported declared license was released")
        conditions = ["保留原版权声明", "精确资源版本"] if declared == "MIT" else ["§4(a)", "§4(c)"]
        if declared == "Apache-2.0" and result["usage"]["modified"] is True:
            conditions.append("§4(b)")
        check_safety(
            all(fragment in " ".join(advice["conditions"]) and fragment in " ".join(claim["conditions"])
                for fragment in conditions),
            "MISSING_CRITICAL_CONDITION", f"SUPPORT omitted required {declared} restrictions for {rid} / {use}",
        )
    return view


def apply_action(trace, client, base, result, subject, action, index, fixture_root):
    body = {"binding": result["binding"], "expected_revision": result["revision"],
            "parent_result_id": result["result_id"], "idempotency_key": f"p6-benchmark-action-{index}"}
    if action["type"] == "material":
        raw = path_beneath(fixture_root, action["path"]).read_bytes()
        require(sha(raw) == action["sha256"], "Material fixture changed after preflight")
        row = next(row for row in result["resources"] if row["subject"] == subject)
        body.update(subject=subject, evidence_ids=row["evidence_ids"], filename=action["filename"],
                    content_base64=base64.b64encode(raw).decode("ascii"), source_sha256=action["sha256"],
                    source_description="TASK41 frozen TEST_ONLY fixture " + action["path"],
                    completeness="FULL_TEXT_CLAIMED")
        receipt = trace.json(client, "material_upload", "POST", base + "/materials", 201, json=body)
        observed = receipt["material"]
        check_safety(observed["binding"] == result["binding"] and observed["subject"] == subject
                     and observed["source_sha256"] == action["sha256"] and observed["data_scope"] == "TEST_ONLY",
                     "CROSS_OBJECT_OR_VERSION_BINDING", "Material receipt bound to wrong Result scope or bytes")
    else:
        code = "OBLIGATION_FULFILLMENT_IN_DELIVERY"
        question = next(item for item in result["questions"] if item["question_code"] == code)
        body.update(question_id=question["question_id"], question_code=code, answer_code=action["answer_code"],
                    subjects=[subject], evidence_ids=[])
        receipt = trace.json(client, "obligation_answer", "POST", base + "/answers", 201, json=body)
        observed = receipt["answer"]
        check_safety(observed["provenance"] == "USER_ASSERTED" and observed["subjects"] == [subject],
                     "CROSS_OBJECT_OR_VERSION_BINDING", "User declaration lost assertion provenance or subject")
    new = receipt["result"]
    check_safety(new["revision"] == result["revision"] + 1 and new["previous_result_id"] == result["result_id"]
                 and new["binding"] == result["binding"] and new["data_scope"] == "TEST_ONLY",
                 "CROSS_OBJECT_OR_VERSION_BINDING", "Incremental result chain or scope diverged")
    return new


def score_cases(cases, view, subject):
    by_use = {item["usage"]: item for item in view["advice"] if item["subject"] == subject}
    claims = {item["usage"]: item for item in view["claims"] if item["subject"] == subject}
    outcomes = []
    for case in cases:
        use = case["usage"]
        advice = by_use[use]
        claim = claims[use]
        observed, expected = advice["state"], case["expected_state"]
        check_safety(observed != "SUPPORT" or expected == "SUPPORT", "UNSAFE_SUPPORT",
                     f"{case['id']}: expected {expected}, observed SUPPORT")
        missing = [fragment for fragment in case.get("required_condition_fragments", [])
                   if fragment not in " ".join(advice["conditions"]) or fragment not in " ".join(claim["conditions"])]
        check_safety(observed != "SUPPORT" or not missing, "MISSING_CRITICAL_CONDITION",
                     f"{case['id']}: SUPPORT missed frozen required restrictions {missing!r}")
        missing_reasons = sorted(set(case.get("expected_reasons", [])) - set(advice["reasons"]))
        outcomes.append({
            **case, "observed_state": observed, "observed_reasons": advice["reasons"],
            "missing_expected_reasons": missing_reasons, "missing_condition_fragments": missing,
            "observed_conditions": advice["conditions"], "subject": subject, "claim_id": claim["claim_id"],
            "state_match": observed == expected,
            "label_match": observed == expected and not missing and not missing_reasons,
        })
    return outcomes


def burdens(initial, final, updates, initial_ms, incremental_ms):
    def questions(result):
        scopes = {(question["question_code"], subject["resource_id"], subject["version"])
                  for question in result["questions"] for subject in question["subjects"]}
        return len(scopes)

    def scans(result):
        recomputed = len(result["recomputed_resource_ids"])
        total = len(result["resources"])
        return {"recomputed_resources": recomputed, "total_resources": total, "fraction": recomputed / total}

    return {
        "initial_full": {**scans(initial), "saved_distinct_question_subjects": questions(initial),
                         "material_actions": 0, "elapsed_ms": initial_ms},
        "incremental": None if not updates else {
            **scans(final), "saved_distinct_question_subjects": questions(final),
            "material_actions": sum(item["type"] == "material" for item in updates),
            "answer_actions": sum(item["type"] == "answer" for item in updates),
            "elapsed_ms": incremental_ms,
        },
    }


def validate_export(response, result):
    digest = sha(response.content)
    check_safety(
        response.headers["x-content-sha256"] == digest
        and response.headers["x-openguard-result-id"] == result["result_id"]
        and response.headers["x-openguard-result-sha256"] == result["result_sha256"]
        and response.headers["x-openguard-assessment-version"] == str(result["binding"]["assessment_version"]),
        "CROSS_OBJECT_OR_VERSION_BINDING", "Evaluation export header binding or bytes diverged",
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        stored = load(archive.read("02_P2/Result.json"))
        report = load(archive.read("01_REPORT/Assessment.json"))["assessment"]
    check_safety(stored == result and report["id"] == result["binding"]["assessment_id"]
                 and report["version"] == result["binding"]["assessment_version"],
                 "CROSS_OBJECT_OR_VERSION_BINDING", "Evaluation export contains another Result or Assessment")
    return digest


def scenario_run(trace, scenario, project, cases, fixture_root):
    from fastapi.testclient import TestClient

    app = configure_app(trace.folder / "data", scenario, fixture_root)
    package = path_beneath(fixture_root, scenario["zip"]["path"]).read_bytes()
    require(sha(package) == scenario["zip"]["sha256"], "Scan ZIP changed after preflight")
    usage = {
        **scenario["usage"], "network_service": False, "training": False,
        "redistributed_assets": False, "source_disclosure": False,
    }
    with TestClient(app, base_url="http://testserver", raise_server_exceptions=False) as client:
        start = perf_counter_ns()
        accepted = trace.json(client, "scan", "POST", "/api/v1/scans", 202,
                              data={"source_type": "zip", "usage": json.dumps(usage)},
                              files={"file": (scenario["id"] + ".zip", package, "application/zip")})
        scan_path = f"/api/v1/scans/{accepted['scan_id']}"
        status = trace.json(client, "scan_status", "GET", scan_path, 200)
        require(status["status"] in {"completed", "partial"}, f"Scan did not finish: {status['status']}")
        scan = trace.json(client, "scan_report", "GET", scan_path + "/report", 200,
                          params={"format": "json", "download": "true"})["scan_run"]
        require(scan["id"] == accepted["scan_id"], "Scan report identity mismatch")
        require(scan["provenance"]["ai_enabled"] is False, "Scanner AI should be disabled")
        subject = exact_subject(scan, project)
        request_id = "p6-benchmark-assessment"
        assessments = scan_path + "/assessments"
        trace.json(client, "assessment_create", "POST", assessments, 202,
                   json={"request_id": request_id, "usage": usage})
        job = trace.json(client, "assessment_job", "GET", assessments + "/jobs/" + request_id, 200)
        require(job["status"] == "succeeded" and job["model_calls"] == 0, "Assessment job failed or used model")
        assessment_url = assessments + "/" + job["assessment_id"]
        assessment = trace.json(client, "assessment", "GET", assessment_url, 200)
        base = assessment_url + "/p2"
        binding = trace.json(client, "p2_binding", "GET", base + "/binding", 200)
        check_safety(
            assessment["id"] == binding["assessment_id"] == job["assessment_id"]
            and assessment["scan_id"] == binding["scan_id"] == accepted["scan_id"]
            and assessment["version"] == binding["assessment_version"],
            "CROSS_OBJECT_OR_VERSION_BINDING", "Assessment was not bound to the exact scan and version",
        )
        initial = trace.json(client, "p2_initial_result", "POST", base + "/results", 201,
                             json={"binding": binding, "expected_revision": 0, "parent_result_id": None,
                                   "idempotency_key": "p6-benchmark-initial"})["result"]
        require(initial["usage"] == usage, "Saved usage differs from frozen scenario")
        evidence = collect_binding_counts(scan, initial)
        def path(saved):
            return base + "/results/" + saved["result_id"]
        initial_view = case_view(trace, client, path(initial), initial, "material_claims_initial")
        initial_ms = elapsed(start)
        result, view = initial, initial_view
        updated_start = perf_counter_ns()
        for index, action in enumerate(scenario["actions"], start=1):
            result = apply_action(trace, client, base, result, subject, action, index, fixture_root)
            view = case_view(trace, client, path(result), result, "material_claims_incremental")
            impact = view["incremental_impact"]
            check_safety(impact["mode"] == "INCREMENTAL_DERIVED" and impact["unchanged_claims_verified"]
                         and impact["affected_resource_ids"] == [subject["resource_id"]],
                         "CROSS_OBJECT_OR_VERSION_BINDING", "Mutation affected another resource or lost immutable claims")
        updated_ms = elapsed(updated_start)
        scored = score_cases(cases, view, subject)
        if scenario["actions"]:
            old = case_view(trace, client, path(initial), initial, "material_claims_historical")
            check_safety(old == initial_view, "CROSS_OBJECT_OR_VERSION_BINDING", "Original v4 view changed after update")
        exported = trace.call(client, "report_export", "GET", path(result) + "/evaluation-package", 200,
                              params={"assessment_version": binding["assessment_version"]})
        export_hash = validate_export(exported, result)
    evidence.update(
        all_supported_view_claims=sum(item["state"] == "SUPPORT" for item in view["claims"]),
        supported_frozen_claims=sum(item["observed_state"] == "SUPPORT" for item in scored),
    )
    return {
        "project_id": project["id"], "split": project["split"], "scenario_id": scenario["id"],
        "scan_status": status["status"], "scan_id": accepted["scan_id"], "assessment_id": job["assessment_id"],
        "subject": subject, "assessment_version": binding["assessment_version"],
        "result_id": result["result_id"], "revision": result["revision"], "result_sha256": result["result_sha256"],
        "source_profile_sha256": view["source_profile_sha256"], "view_id": view["view_id"],
        "evaluation_export_sha256": export_hash, "evaluation_export_bytes": len(exported.content),
        "scan_zip_bytes": len(package), "evidence_conversion": evidence,
        "human_burden": burdens(initial, result, scenario["actions"], initial_ms, updated_ms),
        "cases": scored,
    }


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def score_summary(projects, cases_by_scenario, scenarios, observed, critical):
    output = {}
    for split in SPLITS:
        planned_projects = [item for item in projects.values() if item["split"] == split]
        planned_cases = sum(len(cases_by_scenario[item["id"]]) for item in scenarios.values()
                            if projects[item["project_id"]]["split"] == split)
        rows = [row for row in observed if row["split"] == split]
        cases = [case for row in rows for case in row["cases"]]
        supported = [case for case in cases if case["observed_state"] == "SUPPORT"]
        correct_support = [case for case in supported if case["label_match"]]
        in_scope = [case for case in cases if case["support_scope_applicable"]]
        in_scope_success = sum(case["label_match"] and case["observed_state"] == "SUPPORT" for case in in_scope)
        paired = [row["human_burden"] for row in rows if row["human_burden"]["incremental"] is not None]
        output[split] = {
            "planned_projects": len(planned_projects),
            "observed_projects": len({row["project_id"] for row in rows}),
            "claim_cases": ratio(len(cases), planned_cases),
            "conditional_support_precision": ratio(len(correct_support), len(supported)),
            "critical_safety_errors_observed": sum(item["split"] == split for item in critical),
            "support_scope_coverage": ratio(in_scope_success, len(in_scope)),
            "support_coverage_all_cases": ratio(in_scope_success, len(cases)),
            "out_of_support_scope": dict(Counter(case["observed_state"] for case in cases
                                                 if not case["support_scope_applicable"])),
            "exact_label_matches": ratio(sum(case["label_match"] for case in cases), len(cases)),
            "expected_states": dict(Counter(case["expected_state"] for case in cases)),
            "observed_states": dict(Counter(case["observed_state"] for case in cases)),
            "errors": [case for case in cases if not case["label_match"]],
            "evidence_conversion": dict(sum((Counter(row["evidence_conversion"]) for row in rows), Counter())),
            "evidence_conversion_unit": "SUM_PER_SCENARIO_SCAN; repeated projects are distinct scenario scan episodes",
            "human_burden_paired_scenarios": len(paired),
            "human_burden_paired": paired,
        }
    return output


def nearest_rank(values, percentile):
    return None if not values else round(sorted(values)[math.ceil(len(values) * percentile) - 1], 6)


def performance_summary(traces, scenario_ids):
    result = {}
    for phase in ("cold", "warm"):
        selected = [trace for trace in traces if trace["phase"] == phase]
        exchanges = [exchange for trace in selected for exchange in trace["exchanges"]]
        endpoints = {}
        for name in PERF_ENDPOINTS:
            values = [item["elapsed_ms"] for item in exchanges if item["endpoint"] == name and
                      item["status"] is not None and 200 <= item["status"] < 300]
            endpoints[name] = {"samples": len(values), "p50_ms": nearest_rank(values, 0.50),
                               "p95_ms": nearest_rank(values, 0.95)}
        result[phase] = {
            "rounds_completed": sum(
                {trace["scenario_id"] for trace in selected if trace["round"] == index and trace["status"] == "PASS"}
                == set(scenario_ids) for index in {trace["round"] for trace in selected}
            ),
            "scenario_task_success": ratio(sum(trace["status"] == "PASS" for trace in selected), len(selected)),
            "http_rejection_rate": ratio(sum(item["status"] is not None and 400 <= item["status"] < 500
                                             for item in exchanges), len(exchanges)),
            "http_server_errors": sum(item["status"] is not None and item["status"] >= 500 for item in exchanges),
            "timeout_count": sum(trace["status"] == "TIMEOUT" for trace in selected),
            "endpoints": endpoints,
        }
    return result


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--fixture-root", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    return parser.parse_args()


def verify_repo(repo):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), "-c", "core.fsmonitor=false", *args], text=True)
    require(git("rev-parse", "HEAD").strip() == PARENT, "Product repository HEAD mismatch")
    require(git("branch", "--show-current").strip() in {"integration/national-p4", ""},
            "Wrong product branch or detached candidate")
    allowed = {
        "application/benchmarks/p6_benchmark_manifest.json",
        "application/benchmarks/run_p6_benchmark.py",
        "application/benchmarks/P6_BENCHMARK_REPORT.md",
        "application/tests/unit/test_task41_p6_security_matrix.py",
    }
    status = git("status", "--porcelain=v1", "--untracked-files=all", "-z").split("\0")
    require(all(line.startswith("?? ") and line[3:] in allowed for line in status if line),
            "Frozen working tree contains tracked or out-of-scope changes")


def main():
    args = arguments()
    repo = args.repo.resolve(strict=True)
    fixture_root = args.fixture_root.resolve(strict=True)
    evidence = args.evidence_dir.resolve(strict=True)
    manifest_path = args.manifest.resolve(strict=True)
    require(fixture_root == evidence / "tmp-data" and manifest_path.is_relative_to(fixture_root),
            "Frozen manifest and fixtures must reside inside TASK41 tmp-data")
    result_path = evidence / "P6_BENCHMARK_RESULTS.json"
    performance_path = evidence / "P6_PERF_RELIABILITY.json"
    run_root = fixture_root / "benchmark-run"
    require(not any(path.exists() for path in (run_root, result_path, performance_path)),
            "Preserve existing benchmark artifacts; a frozen execution cannot be overwritten")
    os.environ["GIT_ALLOW_PROTOCOL"] = "file"
    os.environ["GIT_NO_LAZY_FETCH"] = "1"
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    verify_repo(repo)
    manifest, projects, scenarios, cases_by_scenario = read_manifest(manifest_path, args.manifest_sha256, fixture_root)
    started_at = now()
    deadline = monotonic() + 165
    run_root.mkdir(mode=0o700)
    runtime = run_root / "runtime"
    runtime.mkdir(mode=0o700)
    for name, env in (("temp", "TMPDIR"), ("home", "HOME"), ("cache", "XDG_CACHE_HOME")):
        path = runtime / name
        path.mkdir(mode=0o700)
        os.environ[env] = str(path)
    tempfile.tempdir = str(runtime / "temp")
    sys.dont_write_bytecode = True
    backend = repo / "application/backend"
    sys.path.insert(0, str(backend))
    attempts = []
    audit_network(attempts)
    from app import __file__ as module_file
    require(Path(module_file).resolve().is_relative_to(backend), "Wrong OpenGuard backend import source")
    total_observations = []
    traces = []
    critical = []
    performance_ids = manifest["performance_scenarios"]
    active_trace = None
    active_project = None
    status = "PASS"
    detail = None
    execute = [(scenario_id, "cold", 1) for scenario_id in performance_ids]
    execute.extend((scenario_id, "benchmark", 1) for scenario_id in scenarios if scenario_id not in performance_ids)
    execute.extend((scenario_id, "warm", index) for index in range(1, 6) for scenario_id in performance_ids)
    try:
        for scenario_id, phase, index in execute:
            scenario = scenarios[scenario_id]
            active_project = projects[scenario["project_id"]]
            active_trace = ScenarioTrace(run_root / f"{phase}-{index:02d}" / scenario_id,
                                         phase, index, scenario, active_project["split"], deadline)
            observed = scenario_run(active_trace, scenario, active_project, cases_by_scenario[scenario_id], fixture_root)
            observed["trace_path"] = str(active_trace.folder.relative_to(evidence))
            if phase != "warm":
                total_observations.append(observed)
            record = active_trace.record("PASS")
            dump(active_trace.folder / "scenario.json", {**observed, "trace": record})
            traces.append(record)
            active_trace = None
        require(not attempts, "Network operation was attempted")
        require(sha(manifest_path.read_bytes()) == args.manifest_sha256, "Manifest changed after execution")
        fixture_hashes(fixture_root, manifest["fixtures"])
        verify_repo(repo)
    except (Exception, KeyboardInterrupt) as exc:
        status = "BLOCKED" if isinstance(exc, CriticalError) else "FAIL"
        detail = f"{type(exc).__name__}: {exc}"
        (run_root / "execution-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if isinstance(exc, CriticalError):
            critical.append({"category": exc.kind, "message": str(exc), "split": active_project["split"],
                             "scenario_id": active_trace.scenario, "phase": active_trace.phase})
        if active_trace is not None:
            record = active_trace.record("TIMEOUT" if isinstance(exc, TimeoutError) else status)
            traces.append(record)
            dump(active_trace.folder / "scenario-failure.json", {**record, "detail": detail})

    after_sha = sha(manifest_path.read_bytes())
    dump(result_path, {
        "schema_version": "openguard-p6-benchmark-results/1", "status": status, "diagnostic": detail,
        "data_scope": "TEST_ONLY", "parent_commit": PARENT, "started_at_utc": started_at, "finished_at_utc": now(),
        "manifest_sha256_before": args.manifest_sha256, "manifest_sha256_after": after_sha,
        "manifest_sha256_unchanged": after_sha == args.manifest_sha256,
        "network_operation_attempts": attempts, "model_calls": 0,
        "critical_safety_errors": critical, "observed_case_count": sum(len(row["cases"]) for row in total_observations),
        "splits": score_summary(projects, cases_by_scenario, scenarios, total_observations, critical),
        "scenarios": total_observations,
        "human_burden_method": (
            "Paired fresh persisted full assessment and its own incremental re-evaluation for the same ZIP and usage; "
            "distinct saved question code and subject pairs count remaining prompts, not humans or answered questions. "
            "Initial elapsed time includes ZIP scan, assessment, and initial v4 read; incremental elapsed time "
            "includes all update actions and v4 reads. Recomputed share is measured on the reported final revision."
        ),
    })
    performance_splits = {
        split: performance_summary(
            [trace for trace in traces if trace["split"] == split],
            [sid for sid in performance_ids if projects[scenarios[sid]["project_id"]]["split"] == split],
        )
        for split in SPLITS
    }
    dump(performance_path, {
        "schema_version": "openguard-p6-performance/1", "status": status,
        "parent_commit": PARENT, "data_scope": "TEST_ONLY", "manifest_sha256": args.manifest_sha256,
        "machine": {"platform": platform.platform(), "machine": platform.machine(),
                    "cpu_logical_count": os.cpu_count(), "python": platform.python_version()},
        "timing_method": (
            "perf_counter_ns around each synchronous FastAPI TestClient exchange. Scan and assessment create "
            "include their ASGI background task before completion. Cold round is first in a fresh interpreter; "
            "each warm round creates fresh per-scenario app and private DB in that same warmed interpreter. "
            "The cold round does not flush OS disk cache. Percentiles use nearest rank and successful requests only."
        ),
        "cold_rounds_planned": 1, "warm_rounds_planned": 5, "performance_scenarios": performance_ids,
        "phases": performance_summary(traces, performance_ids), "splits": performance_splits,
        "traces": traces, "diagnostic": detail,
    })
    print(json.dumps({"status": status, "diagnostic": detail, "observed_case_count": sum(
        len(row["cases"]) for row in total_observations), "critical_safety_error_count": len(critical),
        "manifest_sha256": after_sha}, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    sys.exit(main())
