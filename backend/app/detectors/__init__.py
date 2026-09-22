"""Deterministic AI resource detectors."""

from .static_assets import detect_ai_assets
from .license_notice_facts import (
    EvidenceHashBinding,
    FactsDetectorInputError,
    FindingCandidate,
    LicenseNoticeCandidateSet,
    ObligationCandidate,
    canonical_facts_sha256,
    detect_license_notice_candidates,
)

__all__ = [
    "EvidenceHashBinding",
    "FactsDetectorInputError",
    "FindingCandidate",
    "LicenseNoticeCandidateSet",
    "ObligationCandidate",
    "canonical_facts_sha256",
    "detect_ai_assets",
    "detect_license_notice_candidates",
]
