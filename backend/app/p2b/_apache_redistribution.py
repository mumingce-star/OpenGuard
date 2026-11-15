"""Private evidence-to-claim adapter for reviewed Apache-2.0 clauses."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.licenses import parse_license_expression
from app.p2.contract import Subject
from app.rules.engine import RuleSet

from .materials import MAX_MATERIAL_BYTES, _decode_material_text

_REVIEWED_LICENSE_SHA256 = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
_CLAUSE = (
    b"(a) You must give any other recipients of the Work or\n"
    b"          Derivative Works a copy of this License;"
)
_MODIFIED_FILES_CLAUSE = (
    b"(b) You must cause any modified files to carry prominent notices\n"
    b"          stating that You changed the files;"
)
_SCOPE_STATEMENT = (
    "OpenGuard 的团队自主代码和文档采用 [Apache License 2.0](LICENSE) 开放。"
    "第三方软件、模型、数据、素材和服务仍分别受其自身许可证、授权条款或服务条款约束；"
    "本仓库的许可证不会改变第三方内容原有权利归属。"
).encode("utf-8")
_RULE_ID = "LIC-APACHE-2.0-NOTICE"
_SCOPE = "first_party_code_and_docs"


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    path: str
    sha256: str


@dataclass(frozen=True)
class ReviewedUseFact:
    resource_id: str
    revision: str
    scope: str
    reference: EvidenceRef


@dataclass(frozen=True)
class ReviewedBinding:
    """A-side reviewed metadata from one immutable repository snapshot."""

    resource_id: str
    revision: str
    scope: str
    license_text: EvidenceRef
    scope_statement: EvidenceRef
    no_distribution_evidence: ReviewedUseFact | None = None
    modified_files_evidence: ReviewedUseFact | None = None
    planned_distribution_evidence: ReviewedUseFact | None = None


@dataclass(frozen=True)
class Gap:
    category: str
    reason: str
    next_action: str


@dataclass(frozen=True)
class LocatedEvidence:
    reference: EvidenceRef
    start_byte: int
    end_byte_exclusive: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ClauseLink:
    rule_id: str
    rule_version: str
    ruleset_sha256: str
    clause: str
    claim: str
    license_evidence: LocatedEvidence
    scope_evidence: LocatedEvidence
    use_evidence: EvidenceRef | None = None
    planned_distribution_evidence: EvidenceRef | None = None
    preconditions: tuple[str, ...] = ("redistribution_of_bound_first_party_work",)
    unresolved: tuple[str, ...] = ("actual_distribution", "obligation_fulfillment", "other_clauses_and_terms")


@dataclass(frozen=True)
class Assessment:
    subject: Subject
    scope: str
    use: Literal["distributed"] = "distributed"
    status: Literal["review_required", "not_applicable", "conditional"] = "review_required"
    link: ClauseLink | None = None
    gap: Gap | None = None
    applicability_evidence: EvidenceRef | None = None
    distribution: Literal["planned", "verified_absent", "unknown"] = "unknown"


def _locate(reference: EvidenceRef, raw: bytes, excerpt: bytes) -> LocatedEvidence:
    start = raw.index(excerpt)
    end = start + len(excerpt)
    return LocatedEvidence(reference, start, end, raw[:start].count(b"\n") + 1, raw[:end].count(b"\n") + 1)


def assess_redistribution(
    subject: Subject,
    *,
    scope: str | None,
    distribution: Literal["planned", "verified_absent", "unknown"],
    binding: ReviewedBinding | None,
    evidence_bytes: Mapping[str, bytes],
    declared_license: str | None,
    ruleset: RuleSet,
    clause: Literal["4(a)", "4(b)"] = "4(a)",
) -> Assessment:
    """Consume bytes from A's authorized reader and metadata from its reviewed registry.

    A scenario of planned redistribution gives a conditional requirement only.
    The input `verified_absent` requires independently confirmed use facts from A.
    """
    scenario = distribution if distribution in {"planned", "verified_absent"} else "unknown"

    def gap(category: str, reason: str, action: str) -> Assessment:
        return Assessment(subject, scope or "unknown", gap=Gap(category, reason, action), distribution=scenario)

    if clause not in {"4(a)", "4(b)"}:
        return gap("unsupported", "clause_unsupported", "review_original_clause_and_rule_mapping")
    if not subject.version or not scope:
        return gap("user_fact_missing", "subject_version_or_scope_unknown", "confirm_exact_subject_and_scope")
    if binding is None:
        return gap("missing_material", "reviewed_binding_missing", "provide_version_bound_license_and_scope_evidence")
    if (subject.resource_id, subject.version, scope) != (binding.resource_id, binding.revision, binding.scope):
        return gap("evidence_conflict", "subject_binding_mismatch", "review_source_resource_version_and_scope")
    if scope != _SCOPE or not re.fullmatch(r"[0-9a-f]{40}", binding.revision):
        return gap("unsupported", "scope_or_revision_unsupported", "provide_reviewed_first_party_git_commit_scope")

    license_ref, scope_ref = binding.license_text, binding.scope_statement
    absence = binding.no_distribution_evidence if distribution == "verified_absent" else None
    modified = binding.modified_files_evidence if clause == "4(b)" and distribution == "planned" else None
    planned = binding.planned_distribution_evidence if distribution == "planned" else None
    for fact in (absence, modified, planned):
        if fact is not None and (fact.resource_id, fact.revision, fact.scope) != (subject.resource_id, subject.version, scope):
            return gap("evidence_conflict", "use_fact_binding_mismatch", "review_use_fact_resource_version_and_scope")
    absence_ref = absence.reference if absence is not None else None
    modified_ref = modified.reference if modified is not None else None
    planned_ref = planned.reference if planned is not None else None
    references = tuple(
        reference for reference in (license_ref, scope_ref, absence_ref, modified_ref, planned_ref)
        if reference is not None
    )
    evidence_ids = {reference.evidence_id for reference in references}
    if (
        (license_ref.path, scope_ref.path) != ("LICENSE", "README.md")
        or "" in evidence_ids
        or len(evidence_ids) != len(references)
        or len({reference.path for reference in references}) != len(references)
        or any(not reference.path for reference in references)
    ):
        return gap("evidence_conflict", "invalid_evidence_references", "review_distinct_evidence_references")
    for reference in references:
        raw = evidence_bytes.get(reference.evidence_id)
        if raw is None or raw == b"":
            reason = "evidence_reference_unresolved" if raw is None else "empty_material"
            return gap("missing_material", reason, "provide_complete_pinned_evidence_bytes")
        if not isinstance(raw, bytes) or len(raw) > MAX_MATERIAL_BYTES:
            return gap("unsupported", "material_size_or_type_unsupported", "provide_bounded_utf8_bytes")
        if hashlib.sha256(raw).hexdigest() != reference.sha256:
            return gap("evidence_conflict", "evidence_hash_mismatch", "review_original_evidence_and_hash")
        try:
            _decode_material_text(raw)
        except ValueError as error:
            return gap("parse_failure", str(error), "provide_intact_utf8_material")

    if license_ref.sha256 != _REVIEWED_LICENSE_SHA256:
        return gap("unsupported", "license_text_not_reviewed", "review_full_text_and_additional_terms")
    raw_scope = evidence_bytes[scope_ref.evidence_id]
    if raw_scope.count(_SCOPE_STATEMENT) != 1:
        return gap("evidence_conflict", "scope_statement_unresolved", "review_first_party_scope_statement")
    if declared_license is not None:
        expression = parse_license_expression(declared_license)
        if not expression.supported or expression.operators:
            return gap("unsupported", "license_expression_unsupported", "review_original_license_expression")
        if expression.expression != "Apache-2.0":
            return gap("evidence_conflict", "license_text_declaration_mismatch", "reconcile_declaration_with_bound_text")

    if distribution == "verified_absent":
        if absence_ref is None:
            return gap("user_fact_missing", "no_distribution_evidence_missing", "confirm_and_record_delivery_scope")
        return Assessment(
            subject, scope, status="not_applicable",
            gap=Gap("not_applicable", "verified_no_redistribution", "reassess_if_distribution_changes"),
            applicability_evidence=absence_ref, distribution=scenario,
        )
    if distribution != "planned":
        return gap("user_fact_missing", "distribution_unknown", "confirm_whether_the_bound_resource_is_distributed")
    if clause == "4(b)" and modified_ref is None:
        return gap("user_fact_missing", "modified_delivery_scope_unknown", "confirm_modified_files_in_planned_delivery")

    rule = next((entry for entry in ruleset.rules if entry.id == _RULE_ID), None)
    if (rule is None or rule.version != "1.0.0" or rule.license_ids != ("Apache-2.0",)
            or rule.obligation_action != "retain_license_and_notice"):
        return gap("unsupported", "rule_version_unsupported", "review_clause_mapping_for_current_ruleset")
    raw_license = evidence_bytes[license_ref.evidence_id]
    return Assessment(subject, scope, status="conditional", distribution=scenario, link=ClauseLink(
        rule_id=rule.id,
        rule_version=rule.version,
        ruleset_sha256=ruleset.source_digest,
        clause=f"Apache-2.0 §{clause}",
        claim=("mark_modified_files_if_redistributed" if modified_ref
               else "provide_license_copy_to_recipients_if_redistributed"),
        license_evidence=_locate(license_ref, raw_license, _MODIFIED_FILES_CLAUSE if modified_ref else _CLAUSE),
        scope_evidence=_locate(scope_ref, raw_scope, _SCOPE_STATEMENT),
        use_evidence=modified_ref or planned_ref,
        planned_distribution_evidence=planned_ref,
        preconditions=("redistribution_of_bound_first_party_work", "reviewed_modified_files_in_planned_delivery")
        if modified_ref else ("redistribution_of_bound_first_party_work",),
    ))
