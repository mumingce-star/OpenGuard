"""B02 conservative candidates derived from bounded B03/B04 fact packages.

The detector is intentionally pure and fail-closed. It accepts an already
loaded v2 facts package plus a hash pinned by its caller; it never reads a
path, fetches metadata, normalizes a license, or writes a Formal Assessment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import uuid


_SCHEMA_VERSION = "openguard.notice-license-facts/2"
_NAMESPACE = uuid.UUID("b2d3b4f7-38da-55cf-827c-b8301e170701")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.:-]{2,127}")
_GAP_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
_RELATIONSHIP_NAMES = ("license", "notice", "copyright")
_RELATIONSHIP_STATES = {"observed", "gap", "text_observed", "declared_unverified"}
_ROOT_FIELDS = {
    "schema_version", "package_status", "generated_at", "source_package", "producer",
    "evidence", "facts", "report_v2_rows", "policies",
}
_SOURCE_PACKAGE_FIELDS = {
    "path", "schema_version", "fixed_commit", "source_file_sha256", "commit_blob_sha256",
}
_PRODUCER_FIELDS = {"name", "version"}
_POLICY_FIELDS = {
    "license_expression_autofill", "authorization_default", "gap_is_noncompliance",
    "notice_absence_is_violation",
}
_EVIDENCE_FIELDS = {
    "evidence_id", "kind", "locator", "source_url", "source_revision", "content_scope",
    "source_file_sha256", "container_sha256", "selected_content_sha256",
    "selected_json_pointer", "excerpt", "verification", "captured_at", "producer",
}
_FACT_FIELDS = {
    "fact_id", "subject", "authorization_status", "license_observations", "relationships",
    "gaps", "review_status",
}
_SUBJECT_FIELDS = {
    "category", "canonical_id", "display_name", "version", "source_url", "usage_scope",
    "source_revision",
}
_OBSERVATION_FIELDS = {
    "raw_value", "observation_kind", "evidence_ids", "license_expression_id",
    "observation_strength",
}
_RELATIONSHIP_FIELDS = {"state", "evidence_ids", "gap_code", "applicability"}
_REPORT_ROW_FIELDS = {
    "row_id", "subject_fact_id", "resource_name_and_type", "version_and_source",
    "license_or_authorization", "usage_or_open_mode", "key_obligations_or_restrictions",
    "team_modifications", "compliance_status", "authorization_status",
    "license_expression_ids", "observation_strengths", "evidence_ids", "gap_codes",
}


class FactsDetectorInputError(ValueError):
    """The untrusted facts input cannot safely produce B02 candidates."""

    def __init__(self) -> None:
        super().__init__("facts_detector_invalid")


@dataclass(frozen=True, slots=True)
class EvidenceHashBinding:
    """Immutable locator and declared hashes for one referenced Evidence."""

    evidence_id: str
    evidence_pointer: str
    source_file_sha256: str
    container_sha256: str | None
    selected_content_sha256: str
    selected_json_pointer: str | None


@dataclass(frozen=True, slots=True)
class FindingCandidate:
    """A review candidate, never a violation or authorization conclusion."""

    candidate_id: str
    fact_id: str
    subject_canonical_id: str
    category: str
    code: str
    source_fact_pointer: str
    source_fact_sha256: str
    source_package_sha256: str
    evidence_bindings: tuple[EvidenceHashBinding, ...]
    status: str = "review_required"
    authorization_status: str = "pending"
    license_expression_id: None = None
    confirmed_violation: bool = False


@dataclass(frozen=True, slots=True)
class ObligationCandidate:
    """Reserved candidate shape; pending v2 facts cannot safely create one."""

    candidate_id: str
    fact_id: str
    source_fact_pointer: str
    source_fact_sha256: str
    source_package_sha256: str
    evidence_bindings: tuple[EvidenceHashBinding, ...]
    status: str = "review_required"
    authorization_status: str = "pending"
    license_expression_id: None = None


@dataclass(frozen=True, slots=True)
class LicenseNoticeCandidateSet:
    source_package_sha256: str
    findings: tuple[FindingCandidate, ...]
    obligations: tuple[ObligationCandidate, ...]


def _invalid() -> FactsDetectorInputError:
    return FactsDetectorInputError()


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise _invalid()
    return value


def _closed(value: Mapping[str, object], fields: set[str]) -> Mapping[str, object]:
    if set(value) != fields:
        raise _invalid()
    return value


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid()
    return value


def _nullable_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _matches(value: object, pattern: re.Pattern[str]) -> str:
    text = _string(value)
    if pattern.fullmatch(text) is None:
        raise _invalid()
    return text


def canonical_facts_sha256(package: Mapping[str, object]) -> str:
    """Hash the complete logical package with stable UTF-8 JSON encoding."""
    try:
        payload = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise _invalid() from None
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _object_sha256(value: Mapping[str, object]) -> str:
    return canonical_facts_sha256(value)


def _producer(value: object) -> None:
    producer = _closed(_mapping(value), _PRODUCER_FIELDS)
    _string(producer.get("name"))
    _string(producer.get("version"))


def _string_list(
    value: object,
    *,
    known_ids: set[str] | None = None,
    pattern: re.Pattern[str] | None = None,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _invalid()
    parsed = tuple(_string(item) for item in value)
    if len(parsed) != len(set(parsed)):
        raise _invalid()
    if known_ids is not None and any(item not in known_ids for item in parsed):
        raise _invalid()
    if pattern is not None and any(pattern.fullmatch(item) is None for item in parsed):
        raise _invalid()
    return parsed


def _validate_source_and_policies(root: Mapping[str, object]) -> None:
    if root.get("package_status") != "draft_facts_only":
        raise _invalid()
    generated_at = _string(root.get("generated_at"))
    if not generated_at.endswith("Z"):
        raise _invalid()
    source = _closed(_mapping(root.get("source_package")), _SOURCE_PACKAGE_FIELDS)
    _string(source.get("path"))
    _string(source.get("schema_version"))
    if re.fullmatch(r"[0-9a-f]{40}", _string(source.get("fixed_commit"))) is None:
        raise _invalid()
    _matches(source.get("source_file_sha256"), _SHA256)
    _matches(source.get("commit_blob_sha256"), _SHA256)
    _producer(root.get("producer"))
    policies = _closed(_mapping(root.get("policies")), _POLICY_FIELDS)
    if policies != {
        "license_expression_autofill": False,
        "authorization_default": "pending",
        "gap_is_noncompliance": False,
        "notice_absence_is_violation": False,
    }:
        raise _invalid()


def _validate_evidence(value: object, index: int) -> EvidenceHashBinding:
    item = _closed(_mapping(value), _EVIDENCE_FIELDS)
    evidence_id = _matches(item.get("evidence_id"), _IDENTIFIER)
    kind = item.get("kind")
    scope = item.get("content_scope")
    verification = item.get("verification")
    if kind not in {"repository_file", "archive_entry", "provider_snapshot"}:
        raise _invalid()
    if scope not in {"whole_file", "archive_entry", "json_pointer_value"}:
        raise _invalid()
    if verification not in {"repository_bytes_verified", "archive_bytes_verified", "fixture_bytes_verified"}:
        raise _invalid()
    _string(item.get("locator"))
    _nullable_string(item.get("source_url"))
    _nullable_string(item.get("source_revision"))
    excerpt = _string(item.get("excerpt"))
    if len(excerpt) > 1000:
        raise _invalid()
    captured_at = _string(item.get("captured_at"))
    if not captured_at.endswith("Z"):
        raise _invalid()
    _producer(item.get("producer"))
    source_hash = _matches(item.get("source_file_sha256"), _SHA256)
    container_hash = item.get("container_sha256")
    if container_hash is not None:
        container_hash = _matches(container_hash, _SHA256)
    selected_hash = _matches(item.get("selected_content_sha256"), _SHA256)
    selected_pointer = item.get("selected_json_pointer")
    if selected_pointer is not None:
        selected_pointer = _string(selected_pointer)
        if not selected_pointer.startswith("/"):
            raise _invalid()
    if (scope == "json_pointer_value") != (selected_pointer is not None):
        raise _invalid()
    if scope == "archive_entry" and container_hash is None:
        raise _invalid()
    return EvidenceHashBinding(
        evidence_id=evidence_id,
        evidence_pointer=f"/evidence/{index}",
        source_file_sha256=source_hash,
        container_sha256=container_hash,
        selected_content_sha256=selected_hash,
        selected_json_pointer=selected_pointer,
    )


def _validate_relationships(
    value: object,
    evidence_ids: set[str],
) -> dict[str, tuple[str, tuple[str, ...], str | None]]:
    relationships = _mapping(value)
    if set(relationships) != set(_RELATIONSHIP_NAMES):
        raise _invalid()
    parsed: dict[str, tuple[str, tuple[str, ...], str | None]] = {}
    for name in _RELATIONSHIP_NAMES:
        relation = _closed(_mapping(relationships[name]), _RELATIONSHIP_FIELDS)
        state = relation.get("state")
        if state not in _RELATIONSHIP_STATES:
            raise _invalid()
        refs = _string_list(relation.get("evidence_ids"), known_ids=evidence_ids, pattern=_IDENTIFIER)
        gap_code = relation.get("gap_code")
        if gap_code is not None:
            gap_code = _matches(gap_code, _GAP_CODE)
        if relation.get("applicability") != "pending_review" or (state == "gap") != (gap_code is not None):
            raise _invalid()
        if state == "gap" and refs:
            raise _invalid()
        parsed[name] = (state, refs, gap_code)
    return parsed


def _validate_fact(
    fact: object,
    *,
    evidence_ids: set[str],
) -> tuple[Mapping[str, object], str, str, list[tuple[str, str, tuple[str, ...]]], tuple[str, ...], tuple[str, ...]]:
    item = _closed(_mapping(fact), _FACT_FIELDS)
    fact_id = _matches(item.get("fact_id"), _IDENTIFIER)
    if item.get("authorization_status") != "pending" or item.get("review_status") != "pending_human_review":
        raise _invalid()
    subject = _closed(_mapping(item.get("subject")), _SUBJECT_FIELDS)
    canonical_id = _string(subject.get("canonical_id"))
    category = subject.get("category")
    if category not in {"root_project", "dependency", "ai_resource"}:
        raise _invalid()
    _string(subject.get("display_name"))
    _nullable_string(subject.get("version"))
    _nullable_string(subject.get("source_url"))
    _nullable_string(subject.get("source_revision"))
    if subject.get("usage_scope") not in {"project", "runtime", "test", "model", "dataset"}:
        raise _invalid()

    observations = item.get("license_observations")
    if not isinstance(observations, list):
        raise _invalid()
    observation_refs: set[str] = set()
    strengths: set[str] = set()
    for observation in observations:
        current = _closed(_mapping(observation), _OBSERVATION_FIELDS)
        raw_value = current.get("raw_value")
        if not (raw_value is None or isinstance(raw_value, str) or (
            isinstance(raw_value, list) and all(isinstance(part, str) for part in raw_value)
        )):
            raise _invalid()
        if current.get("observation_kind") not in {"license_text_heading", "provider_declared_raw", "missing"}:
            raise _invalid()
        strength = current.get("observation_strength")
        if strength not in {"text_observed", "provider_declared_unverified", "missing"}:
            raise _invalid()
        strengths.add(strength)
        if current.get("license_expression_id") is not None:
            raise _invalid()
        observation_refs.update(_string_list(
            current.get("evidence_ids"), known_ids=evidence_ids, pattern=_IDENTIFIER,
        ))

    relationships = _validate_relationships(item.get("relationships"), evidence_ids)
    gaps = _string_list(item.get("gaps"), pattern=_GAP_CODE)
    relationship_gaps = {value[2] for value in relationships.values() if value[2] is not None}
    if not relationship_gaps.issubset(set(gaps)):
        raise _invalid()
    relationship_refs = {ref for value in relationships.values() for ref in value[1]}
    if observation_refs != set(relationships["license"][1]) or not relationship_refs.issubset(evidence_ids):
        raise _invalid()
    if relationships["license"][0] == "declared_unverified":
        if category != "ai_resource" or "provider_declared_unverified" not in strengths:
            raise _invalid()
    elif "provider_declared_unverified" in strengths:
        raise _invalid()

    refs = tuple(sorted(relationship_refs | observation_refs))
    candidates = [("evidence_gap", code, refs) for code in gaps]
    if relationships["license"][0] == "declared_unverified":
        candidates.append((
            "unverified_license_declaration",
            "LICENSE_DECLARATION_UNVERIFIED",
            relationships["license"][1],
        ))
    return item, fact_id, canonical_id, candidates, gaps, tuple(sorted(strengths))


def _validate_report_rows(
    value: object,
    *,
    parsed_facts: list[tuple[Mapping[str, object], str, str, list[tuple[str, str, tuple[str, ...]]], tuple[str, ...], tuple[str, ...]]],
    evidence_ids: set[str],
) -> None:
    if not isinstance(value, list) or len(value) != len(parsed_facts):
        raise _invalid()
    facts_by_id = {item[1]: item for item in parsed_facts}
    seen_rows: set[str] = set()
    seen_facts: set[str] = set()
    for raw_row in value:
        row = _closed(_mapping(raw_row), _REPORT_ROW_FIELDS)
        row_id = _matches(row.get("row_id"), _IDENTIFIER)
        fact_id = _matches(row.get("subject_fact_id"), _IDENTIFIER)
        if row_id in seen_rows or fact_id in seen_facts or fact_id not in facts_by_id:
            raise _invalid()
        seen_rows.add(row_id)
        seen_facts.add(fact_id)
        for field in (
            "resource_name_and_type", "version_and_source", "license_or_authorization",
            "usage_or_open_mode", "key_obligations_or_restrictions", "team_modifications",
        ):
            _string(row.get(field))
        if row.get("compliance_status") != "待核验" or row.get("authorization_status") != "pending":
            raise _invalid()
        if row.get("license_expression_ids") != []:
            raise _invalid()
        fact, _, _, _, gaps, strengths = facts_by_id[fact_id]
        row_strengths = _string_list(row.get("observation_strengths"))
        row_refs = _string_list(row.get("evidence_ids"), known_ids=evidence_ids, pattern=_IDENTIFIER)
        row_gaps = _string_list(row.get("gap_codes"), pattern=_GAP_CODE)
        relationships = _mapping(fact["relationships"])
        expected_refs: set[str] = set()
        for relationship in relationships.values():
            relationship_map = _mapping(relationship)
            expected_refs.update(_string_list(
                relationship_map.get("evidence_ids"), known_ids=evidence_ids, pattern=_IDENTIFIER,
            ))
        if set(row_strengths) != set(strengths) or set(row_refs) != expected_refs or set(row_gaps) != set(gaps):
            raise _invalid()
    if seen_facts != set(facts_by_id):
        raise _invalid()


def _candidate_id(fact_id: str, category: str, code: str, fact_sha256: str) -> str:
    return f"b02_{uuid.uuid5(_NAMESPACE, f'{fact_id}|{category}|{code}|{fact_sha256}')}"


def detect_license_notice_candidates(
    package: Mapping[str, object],
    *,
    expected_package_sha256: str,
) -> LicenseNoticeCandidateSet:
    """Return hash-bound review candidates or reject the complete package."""
    try:
        expected_hash = _matches(expected_package_sha256, _SHA256)
        root = _closed(_mapping(package), _ROOT_FIELDS)
        if root.get("schema_version") != _SCHEMA_VERSION:
            raise _invalid()
        actual_hash = canonical_facts_sha256(root)
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise _invalid()
        _validate_source_and_policies(root)

        raw_evidence = root.get("evidence")
        raw_facts = root.get("facts")
        if not isinstance(raw_evidence, list) or not raw_evidence or not isinstance(raw_facts, list) or not raw_facts:
            raise _invalid()
        bindings = tuple(_validate_evidence(item, index) for index, item in enumerate(raw_evidence))
        binding_by_id = {item.evidence_id: item for item in bindings}
        if len(binding_by_id) != len(bindings):
            raise _invalid()
        parsed = [_validate_fact(item, evidence_ids=set(binding_by_id)) for item in raw_facts]
        fact_ids = [item[1] for item in parsed]
        if len(fact_ids) != len(set(fact_ids)):
            raise _invalid()
        _validate_report_rows(root.get("report_v2_rows"), parsed_facts=parsed, evidence_ids=set(binding_by_id))

        findings: list[FindingCandidate] = []
        for index, (fact, fact_id, canonical_id, candidate_specs, gaps, _) in enumerate(parsed):
            fact_hash = _object_sha256(fact)
            for category, code, refs in candidate_specs:
                pointer = (
                    f"/facts/{index}/gaps/{gaps.index(code)}"
                    if category == "evidence_gap"
                    else f"/facts/{index}/relationships/license"
                )
                findings.append(FindingCandidate(
                    candidate_id=_candidate_id(fact_id, category, code, fact_hash),
                    fact_id=fact_id,
                    subject_canonical_id=canonical_id,
                    category=category,
                    code=code,
                    source_fact_pointer=pointer,
                    source_fact_sha256=fact_hash,
                    source_package_sha256=actual_hash,
                    evidence_bindings=tuple(binding_by_id[ref] for ref in sorted(refs)),
                ))
        findings.sort(key=lambda item: (item.fact_id, item.category, item.code))
        # The v2 contract has neither a verified applicable license expression
        # nor an authorization decision. Creating an obligation candidate would
        # therefore overstate the input even if its status remained pending.
        return LicenseNoticeCandidateSet(actual_hash, tuple(findings), ())
    except FactsDetectorInputError:
        raise
    except Exception:
        raise _invalid() from None


__all__ = [
    "EvidenceHashBinding",
    "FactsDetectorInputError",
    "FindingCandidate",
    "LicenseNoticeCandidateSet",
    "ObligationCandidate",
    "canonical_facts_sha256",
    "detect_license_notice_candidates",
]
