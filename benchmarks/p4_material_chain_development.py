"""Replay the exposed P4 development case from pinned Git objects."""

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess

from app.p2.contract import Subject
from app.p2b._apache_redistribution import (
    EvidenceRef, ReviewedBinding, ReviewedUseFact, assess_redistribution,
)
from app.rules.engine import load_ruleset

ROOT = Path(__file__).resolve().parents[1]
REVISION = "2cc7f63a812561bf71de11d2041e4027a345efda"
RESOURCE = "openguard:first-party"
SCOPE = "first_party_code_and_docs"
LICENSE = EvidenceRef("test:openguard:license", "LICENSE",
                      "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4")
SCOPE_REF = EvidenceRef("test:openguard:scope", "README.md",
                        "2941166b3c8574882c34d4af2a6d8af7a5b827b7701e4978813305808b71f4ea")
MODIFIED_PLAN = b"Synthetic planned delivery: modified first-party files in the reviewed scope."


def replay() -> dict:
    evidence: dict[str, bytes] = {}
    materials: list[dict] = []
    for reference in (LICENSE, SCOPE_REF):
        object_name = f"{REVISION}:{reference.path}"
        raw = subprocess.check_output(["git", "show", object_name], cwd=ROOT)
        if hashlib.sha256(raw).hexdigest() != reference.sha256:
            raise ValueError(f"material_hash_mismatch: {reference.path}")
        blob = subprocess.check_output(["git", "rev-parse", object_name], cwd=ROOT, text=True).strip()
        evidence[reference.evidence_id] = raw
        materials.append(asdict(reference) | {"git_blob": blob})

    assessment_inputs = {
        "subject": Subject(resource_id=RESOURCE, version=REVISION),
        "scope": SCOPE,
        "distribution": "planned",
        "declared_license": "Apache-2.0",
        "ruleset": load_ruleset(),
    }
    fact = EvidenceRef("test:modified-delivery", "delivery-plan.txt", hashlib.sha256(MODIFIED_PLAN).hexdigest())
    modified = ReviewedUseFact(RESOURCE, REVISION, SCOPE, fact)
    binding = ReviewedBinding(RESOURCE, REVISION, SCOPE, LICENSE, SCOPE_REF)
    baseline = assess_redistribution(binding=binding, evidence_bytes=evidence, **assessment_inputs)
    extension = assess_redistribution(
        clause="4(b)", binding=replace(binding, modified_files_evidence=modified),
        evidence_bytes=evidence | {fact.evidence_id: MODIFIED_PLAN}, **assessment_inputs,
    )
    missing = assess_redistribution(clause="4(b)", binding=binding, evidence_bytes=evidence, **assessment_inputs)
    cases = [
        ("apache-4a", "conditional", "provide_license_copy_to_recipients_if_redistributed",
         "scenario_only", baseline),
        ("apache-4b", "conditional", "mark_modified_files_if_redistributed",
         "synthetic_reviewed_fact", extension),
        ("apache-4b-missing-modification", "review_required", "modified_delivery_scope_unknown",
         "scenario_only", missing),
    ]
    rows = []
    for case_id, status, expected, use_label, decision in cases:
        actual = decision.link.claim if decision.link else decision.gap.reason
        rows.append({
            "id": case_id, "use_label": use_label, "expected_status": status, "expected": expected,
            "matched": (decision.status, actual) == (status, expected),
            "result": asdict(decision) | {"subject": decision.subject.model_dump(mode="json")},
        })
    return {
        "protocol": "p4-material-chain-development/v2",
        "source": "OpenGuard repository Git objects",
        "resource_id": RESOURCE, "revision": REVISION, "scope": SCOPE,
        "split": "development", "exposed": True, "review_status": "second_review_pending",
        "materials": materials,
        "synthetic_materials": [asdict(fact) | {"fixture": "MODIFIED_PLAN", "start_line": 1, "end_line": 1}],
        "cases": rows,
        "remaining": {"development_projects": 5, "independent_projects": 2,
                      "candidate_claims_minimum": 39, "owner": "Luna and independent reviewers",
                      "split_freeze": "pending", "double_review": "pending", "adjudication": "pending"},
        "development_group": {"baseline_matched": int(rows[0]["matched"]), "baseline_predictions": 1},
        "independent": {"projects": 0, "predictions": 0, "precision": None},
    }


if __name__ == "__main__":
    report = replay()
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    raise SystemExit(0 if all(case["matched"] for case in report["cases"]) else 1)
