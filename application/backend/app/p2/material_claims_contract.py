"""Additive /material-claims v3 view; P2 Result/Material wire types stay frozen."""
from typing import Literal
from pydantic import Field, model_validator
from .contract import DTO, Binding, Subject, SHA, ID, Use

Status = Literal['SUPPORT', 'RESTRICTION', 'UNKNOWN', 'COUNTER_EVIDENCE', 'NOT_COVERED']


class Clause(DTO):
    clause_id: ID
    material_id: ID
    material_sha256: SHA
    kind: Literal['license_identifier', 'copyright', 'permission', 'condition', 'warranty', 'notice']
    byte_start: int = Field(ge=0, le=65536)
    byte_end: int = Field(ge=1, le=65536)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=65536)
    quote_sha256: SHA

    @model_validator(mode='after')
    def ordered(self):
        if self.byte_end <= self.byte_start or self.line_end < self.line_start:
            raise ValueError('invalid_clause_range')
        return self


class EvidenceRef(DTO):
    evidence_id: ID
    source_sha256: SHA | None


class DeclarationObservation(DTO):
    subject: Subject
    expression: str
    normalized_ids: list[str]
    declaration_evidence_ids: list[ID]
    evidence: list[EvidenceRef]
    evidence_status: Literal['COMPLETE', 'UNKNOWN']


class MaterialObservation(DTO):
    material_id: ID
    subject: Subject
    source_sha256: SHA
    byte_count: int = Field(ge=1, le=65536)
    filename: str
    parse_state: Literal['MATCHED_MIT', 'NOTICE_OBSERVED', 'UNSUPPORTED', 'FAILED']
    parse_reason: str
    binding_state: Literal['BOUND_TO_SAVED_RESULT'] = 'BOUND_TO_SAVED_RESULT'
    adoption_state: Literal['OBSERVATION_ONLY', 'CONDITIONAL_TEXT_BASIS']
    declared_spdx: str
    text_license: Literal['MIT', 'UNKNOWN']
    license_version: None = None  # MIT text has no numeric license version.
    version_scope: Literal['RESOURCE_VERSION_NOT_LICENSE_VERSION'] = 'RESOURCE_VERSION_NOT_LICENSE_VERSION'
    role: Literal['root_package', 'dependency', 'unknown']
    role_state: Literal['observed', 'inferred', 'unknown']
    role_basis_evidence_ids: list[ID]
    source_binding: Literal['PINNED_RELEASE_MATCH', 'NOT_ESTABLISHED']
    source_profile_sha256: SHA | None
    evidence: list[EvidenceRef]
    clauses: list[Clause] = Field(max_length=5)


class SourceMember(DTO):
    path: str = Field(min_length=1, max_length=4096)
    bytes: int = Field(ge=0, le=4 * 1024 * 1024)
    sha256: SHA | None
    inspection_state: Literal['EXTRACTED_UNREVIEWED', 'UNSUPPORTED_FORMAT', 'PARSE_FAILED', 'LIMIT_EXCEEDED', 'INVALID_TYPE', 'READ_FAILED']


class SourceObservation(DTO):
    source_observation_id: ID
    subject: Subject
    source_profile_sha256: SHA
    archive_sha256: SHA
    notice_status: Literal['ABSENT_COMPLETE', 'PRESENT_UNREVIEWED', 'INCOMPLETE', 'INVALID']
    reason: str
    member_count: int = Field(ge=0, le=2000)
    enumeration_complete: bool
    notices: list[SourceMember] = Field(max_length=20)


class CounterEvidence(DTO):
    code: Literal['SPDX_TEXT_CONFLICT', 'SPDX_NORMALIZATION_CONFLICT', 'BOUND_LICENSE_BYTES_CONFLICT', 'NOTICE_REQUIRES_REVIEW']
    material_ids: list[ID]
    evidence_ids: list[ID]
    source_observation_ids: list[ID]
    declaration_evidence_ids: list[ID]
    evidence_status: Literal['COMPLETE', 'UNKNOWN']


class ClaimLink(DTO):
    claim_id: ID
    usage: Use
    subject: Subject
    material_ids: list[ID]
    evidence: list[EvidenceRef]
    clause_ids: list[ID]
    conditions: list[str]
    counter_evidence: list[CounterEvidence]
    state: Status
    formal_effect: Literal['none'] = 'none'


class PurposeAdvice(DTO):
    usage: Use
    subject: Subject
    saved_value: bool | None
    state: Status
    reasons: list[str]
    claim_ids: list[ID]
    conditions: list[str]
    limitations: list[str]


class MaterialClaims(DTO):
    schema_version: Literal['openguard-material-claims/3'] = 'openguard-material-claims/3'
    rule_version: Literal['mit-bound-claim/3'] = 'mit-bound-claim/3'
    view_id: ID
    result_id: ID
    result_sha256: SHA
    revision: int = Field(ge=1)
    previous_result_id: ID | None
    binding: Binding
    data_scope: Literal['OWNER', 'TEST_ONLY']
    source_status: Literal['CHECKED', 'NOT_CONFIGURED']
    source_profile_sha256: SHA | None
    declaration_observations: list[DeclarationObservation] = Field(max_length=1000)
    materials: list[MaterialObservation] = Field(max_length=20)
    source_observations: list[SourceObservation] = Field(max_length=1000)
    claims: list[ClaimLink] = Field(max_length=3000)
    advice: list[PurposeAdvice] = Field(max_length=3000)
    formal_effect: Literal['none'] = 'none'
    applicability_review: Literal['NOT_SIGNED'] = 'NOT_SIGNED'
    model_calls: Literal[0] = 0
