"""A-owned admission of B02-B candidates into the formal facts/object chain.

This is deliberately an *admission record*, not a second detector and not a
ScanRun mutation.  B02-B only accepts the frozen v2 NOTICE/license facts
package; v3 observations and B02-A AI Detector output have different contracts
and cannot be substituted here.  The result is pinned to an existing terminal
ScanRun and its formal Assessment so later A-owned persistence/report work can
consume an immutable, review-only object without changing the scan facts hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.assessment.engine import facts_digest
from app.assessment.models import Assessment
from app.detectors.license_notice_facts import (
    FindingCandidate,
    LicenseNoticeCandidateSet,
    detect_license_notice_candidates,
)
from app.domain.models import ScanRun


BRIDGE_VERSION = "b02b-formal-candidate-admission/1"


class LicenseNoticeCandidateAdmissionError(ValueError):
    """A caller attempted to admit an unbound or semantically incompatible set."""

    def __init__(self) -> None:
        super().__init__("license_notice_candidate_admission_invalid")


@dataclass(frozen=True, slots=True)
class SubjectObjectBinding:
    """Explicit A-owned binding from a B03/B04 subject fact to a P0 object.

    Root-project facts intentionally have no P0 resource ID: P0 RiskFinding
    only permits component/AI-asset resources.  Project-level candidates remain
    admitted facts rather than being forced into a fabricated component.
    """

    fact_id: str
    resource_id: str | None


@dataclass(frozen=True, slots=True)
class CandidateEvidenceObjectBinding:
    """Maps a candidate's already hash-bound source evidence to an A Evidence ID."""

    fact_id: str
    source_evidence_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class FormalLicenseNoticeCandidate:
    candidate_id: str
    fact_id: str
    subject_canonical_id: str
    subject_kind: str
    resource_id: str | None
    category: str
    code: str
    source_fact_pointer: str
    source_fact_sha256: str
    source_package_sha256: str
    source_evidence_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    status: str = "review_required"
    authorization_status: str = "pending"
    license_expression_id: None = None
    confirmed_violation: bool = False


@dataclass(frozen=True, slots=True)
class FormalLicenseNoticeCandidateAdmission:
    schema_version: str
    scan_id: str
    facts_hash: str
    assessment_id: str
    assessment_version: int
    source_package_sha256: str
    candidates: tuple[FormalLicenseNoticeCandidate, ...]


def _invalid() -> LicenseNoticeCandidateAdmissionError:
    return LicenseNoticeCandidateAdmissionError()


def _subject_kinds(package: Mapping[str, object]) -> dict[str, tuple[str, str]]:
    """Read only fields already fully validated by the v2 detector."""
    try:
        facts = package["facts"]
        if not isinstance(facts, list):
            raise ValueError
        result: dict[str, tuple[str, str]] = {}
        for fact in facts:
            if not isinstance(fact, Mapping) or not isinstance(fact.get("fact_id"), str):
                raise ValueError
            subject = fact.get("subject")
            if not isinstance(subject, Mapping):
                raise ValueError
            category = subject.get("category")
            canonical_id = subject.get("canonical_id")
            if category not in {"root_project", "dependency", "ai_resource"} or not isinstance(canonical_id, str):
                raise ValueError
            if fact["fact_id"] in result:
                raise ValueError
            result[fact["fact_id"]] = (category, canonical_id)
        return result
    except (KeyError, TypeError, ValueError):
        raise _invalid() from None


def _binding_index(
    bindings: tuple[SubjectObjectBinding, ...],
    scan: ScanRun,
    subjects: Mapping[str, tuple[str, str]],
    candidate_fact_ids: set[str],
) -> dict[str, str | None]:
    if len(bindings) != len(candidate_fact_ids):
        raise _invalid()
    resources = {item.id: "dependency" for item in scan.components}
    resources.update({item.id: "ai_resource" for item in scan.ai_assets})
    result: dict[str, str | None] = {}
    for binding in bindings:
        if not isinstance(binding, SubjectObjectBinding) or binding.fact_id in result:
            raise _invalid()
        if binding.fact_id not in candidate_fact_ids:
            raise _invalid()
        subject_kind, _ = subjects[binding.fact_id]
        if subject_kind == "root_project":
            if binding.resource_id is not None:
                raise _invalid()
        elif not isinstance(binding.resource_id, str) or resources.get(binding.resource_id) != subject_kind:
            raise _invalid()
        result[binding.fact_id] = binding.resource_id
    if set(result) != candidate_fact_ids:
        raise _invalid()
    return result


def _evidence_index(
    bindings: tuple[CandidateEvidenceObjectBinding, ...], scan: ScanRun,
    candidates: tuple[FindingCandidate, ...],
) -> dict[tuple[str, str], str]:
    required = {(candidate.fact_id, item.evidence_id) for candidate in candidates for item in candidate.evidence_bindings}
    if len(bindings) != len(required):
        raise _invalid()
    scan_evidence_ids = {item.id for item in scan.evidence}
    result: dict[tuple[str, str], str] = {}
    for binding in bindings:
        key = (binding.fact_id, binding.source_evidence_id)
        if (not isinstance(binding, CandidateEvidenceObjectBinding) or key in result
                or key not in required or binding.evidence_id not in scan_evidence_ids):
            raise _invalid()
        result[key] = binding.evidence_id
    if set(result) != required:
        raise _invalid()
    return result


def admit_license_notice_candidates(
    package: Mapping[str, object], *, expected_package_sha256: str,
    scan: ScanRun, assessment: Assessment,
    subject_bindings: tuple[SubjectObjectBinding, ...],
    evidence_bindings: tuple[CandidateEvidenceObjectBinding, ...],
) -> FormalLicenseNoticeCandidateAdmission:
    """Bind B02-B v2 candidates to immutable A facts and existing P0 objects.

    The function neither invokes B02-A nor accepts v3.  It does not create a
    license, obligation, remediation, RiskFinding, or Assessment and cannot
    alter ``scan``; all output remains a pending, review-only admission record.
    """
    if type(scan) is not ScanRun or type(assessment) is not Assessment:
        raise _invalid()
    if scan.status.value not in {"completed", "partial"}:
        raise _invalid()
    actual_facts_hash = facts_digest(scan)
    if (assessment.formal is not True or assessment.scan_id != scan.id
            or assessment.facts_hash != actual_facts_hash):
        raise _invalid()
    try:
        detected = detect_license_notice_candidates(
            package, expected_package_sha256=expected_package_sha256,
        )
        if type(detected) is not LicenseNoticeCandidateSet or detected.obligations:
            raise _invalid()
        subjects = _subject_kinds(package)
        candidate_fact_ids = {candidate.fact_id for candidate in detected.findings}
        object_index = _binding_index(subject_bindings, scan, subjects, candidate_fact_ids)
        evidence_index = _evidence_index(evidence_bindings, scan, detected.findings)
        admitted = []
        for candidate in detected.findings:
            subject_kind, canonical_id = subjects[candidate.fact_id]
            if canonical_id != candidate.subject_canonical_id:
                raise _invalid()
            source_evidence_ids = tuple(item.evidence_id for item in candidate.evidence_bindings)
            admitted.append(FormalLicenseNoticeCandidate(
                candidate_id=candidate.candidate_id, fact_id=candidate.fact_id,
                subject_canonical_id=canonical_id, subject_kind=subject_kind,
                resource_id=object_index[candidate.fact_id], category=candidate.category,
                code=candidate.code, source_fact_pointer=candidate.source_fact_pointer,
                source_fact_sha256=candidate.source_fact_sha256,
                source_package_sha256=detected.source_package_sha256,
                source_evidence_ids=source_evidence_ids,
                evidence_ids=tuple(evidence_index[(candidate.fact_id, evidence_id)] for evidence_id in source_evidence_ids),
            ))
        return FormalLicenseNoticeCandidateAdmission(
            schema_version=BRIDGE_VERSION, scan_id=scan.id, facts_hash=actual_facts_hash,
            assessment_id=assessment.id, assessment_version=assessment.version,
            source_package_sha256=detected.source_package_sha256, candidates=tuple(admitted),
        )
    except LicenseNoticeCandidateAdmissionError:
        raise
    except Exception:
        raise _invalid() from None


__all__ = [
    "BRIDGE_VERSION", "CandidateEvidenceObjectBinding", "FormalLicenseNoticeCandidate",
    "FormalLicenseNoticeCandidateAdmission", "LicenseNoticeCandidateAdmissionError",
    "SubjectObjectBinding", "admit_license_notice_candidates",
]
