"""B02-B must enter A as bound facts, never as an AI Detector substitute."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import socket
import subprocess

import pytest

from app.assessment.engine import build_assessment
from app.detectors.license_notice_facts import canonical_facts_sha256, detect_license_notice_candidates
from app.domain.models import ScanRun
from app.p1.license_notice_candidate_admission import (
    BRIDGE_VERSION,
    CandidateEvidenceObjectBinding,
    LicenseNoticeCandidateAdmissionError,
    SubjectObjectBinding,
    admit_license_notice_candidates,
)


ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "tests" / "fixtures" / "notice-license-facts-v2" / "facts.json"
V3_FACTS = ROOT / "tests" / "fixtures" / "notice-license-facts-v3" / "facts.json"
SAMPLE = ROOT / "examples" / "sample-scan-result.json"


def _facts() -> dict:
    return json.loads(FACTS.read_text(encoding="utf-8"))


def _run() -> ScanRun:
    return ScanRun.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8")))


def _bindings(package: dict, scan: ScanRun):
    detected = detect_license_notice_candidates(
        package, expected_package_sha256=canonical_facts_sha256(package),
    )
    subjects = {item["fact_id"]: item["subject"]["category"] for item in package["facts"]}
    component_id = scan.components[0].id
    asset_id = scan.ai_assets[0].id
    subject_bindings = tuple(
        SubjectObjectBinding(
            fact_id=fact_id,
            resource_id=None if subjects[fact_id] == "root_project" else component_id if subjects[fact_id] == "dependency" else asset_id,
        )
        for fact_id in sorted({item.fact_id for item in detected.findings})
    )
    evidence_id = scan.evidence[0].id
    evidence_bindings = tuple(
        CandidateEvidenceObjectBinding(fact_id, source_evidence_id, evidence_id)
        for fact_id, source_evidence_id in sorted({
            (item.fact_id, binding.evidence_id)
            for item in detected.findings for binding in item.evidence_bindings
        })
    )
    return subject_bindings, evidence_bindings


def _admit(package: dict | None = None):
    package = package or _facts()
    scan = _run()
    assessment = build_assessment(scan)
    subjects, evidence = _bindings(package, scan)
    return admit_license_notice_candidates(
        package, expected_package_sha256=canonical_facts_sha256(package), scan=scan,
        assessment=assessment, subject_bindings=subjects, evidence_bindings=evidence,
    )


def test_v2_b02b_candidates_are_bound_to_terminal_a_scan_and_formal_assessment() -> None:
    admitted = _admit()

    assert admitted.schema_version == BRIDGE_VERSION
    assert len(admitted.candidates) == 17
    assert admitted.source_package_sha256 == canonical_facts_sha256(_facts())
    assert all(item.status == "review_required" for item in admitted.candidates)
    assert all(item.authorization_status == "pending" for item in admitted.candidates)
    assert all(item.license_expression_id is None and item.confirmed_violation is False for item in admitted.candidates)
    root = next(item for item in admitted.candidates if item.fact_id == "fact.root.openguard")
    assert root.subject_kind == "root_project"
    assert root.resource_id is None
    dependency = next(item for item in admitted.candidates if item.subject_kind == "dependency")
    assert dependency.resource_id.startswith("cmp_")
    asset = next(item for item in admitted.candidates if item.subject_kind == "ai_resource")
    assert asset.resource_id.startswith("ast_")


@pytest.mark.parametrize("mutate", [
    lambda package, scan, assessment, subjects, evidence: (subjects[1:], evidence),
    lambda package, scan, assessment, subjects, evidence: (subjects, evidence[1:]),
    lambda package, scan, assessment, subjects, evidence: (
        subjects, evidence + (CandidateEvidenceObjectBinding("fact.root.openguard", "ev.extra", scan.evidence[0].id),)),
])
def test_missing_or_extra_a_bindings_fail_closed(mutate) -> None:
    package, scan = _facts(), _run()
    assessment = build_assessment(scan)
    subjects, evidence = _bindings(package, scan)
    changed_subjects, changed_evidence = mutate(package, scan, assessment, subjects, evidence)

    with pytest.raises(LicenseNoticeCandidateAdmissionError):
        admit_license_notice_candidates(
            package, expected_package_sha256=canonical_facts_sha256(package), scan=scan,
            assessment=assessment, subject_bindings=changed_subjects, evidence_bindings=changed_evidence,
        )


def test_wrong_assessment_or_v3_package_cannot_be_admitted_as_b02b_v2() -> None:
    package, scan = _facts(), _run()
    assessment = build_assessment(scan).model_copy(update={"facts_hash": "0" * 64})
    subjects, evidence = _bindings(package, scan)

    with pytest.raises(LicenseNoticeCandidateAdmissionError):
        admit_license_notice_candidates(
            package, expected_package_sha256=canonical_facts_sha256(package), scan=scan,
            assessment=assessment, subject_bindings=subjects, evidence_bindings=evidence,
        )

    v3 = json.loads(V3_FACTS.read_text(encoding="utf-8"))
    with pytest.raises(LicenseNoticeCandidateAdmissionError):
        admit_license_notice_candidates(
            v3, expected_package_sha256=canonical_facts_sha256(v3), scan=scan,
            assessment=build_assessment(scan), subject_bindings=(), evidence_bindings=(),
        )


def test_admission_is_offline_and_does_not_need_ai_detector(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external capability")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    first = _admit()
    second = _admit()

    assert first == second
