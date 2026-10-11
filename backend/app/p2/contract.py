"""P2 v1 wire contract, independent of Assessment and R6 model contracts."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "openguard-p2-result/1"
ALGORITHM = "p2-bound-candidate/1"
SHA = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ID = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
Use = Literal["commercial", "modified", "distributed", "network_service", "training", "redistributed_assets", "source_disclosure"]
State = Literal["candidate", "unknown", "pending", "partial"]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate_key")
            out[key] = value
        return out

    def invalid(_):
        raise ValueError("nonfinite_number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Binding(DTO):
    scan_id: ID
    assessment_id: ID
    assessment_version: int = Field(ge=1)
    registry_revision: int = Field(ge=1)
    project_revision: str | None = Field(max_length=200)
    facts_hash: SHA
    usage_hash: SHA
    rule_version: str = Field(min_length=1, max_length=300)
    assessment_sha256: SHA


class Subject(DTO):
    resource_id: ID
    version: str | None = Field(max_length=200)


class CreateRequest(DTO):
    binding: Binding
    expected_revision: int = Field(ge=0)
    parent_result_id: ID | None
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


QuestionCode = Literal["DELIVERY_SCOPE_FOR_RESOURCES", "OBLIGATION_FULFILLMENT_IN_DELIVERY"]
AnswerCode = Literal["YES_INCLUDE", "NO_EXCLUDE", "NOT_DECIDED", "FULFILLED", "NOT_FULFILLED", "NOT_DELIVERED_YET", "UNKNOWN"]
OPTIONS = {
    "DELIVERY_SCOPE_FOR_RESOURCES": ["YES_INCLUDE", "NO_EXCLUDE", "NOT_DECIDED"],
    "OBLIGATION_FULFILLMENT_IN_DELIVERY": ["FULFILLED", "NOT_FULFILLED", "NOT_DELIVERED_YET", "UNKNOWN"],
}


class AnswerRequest(CreateRequest):
    question_id: ID
    question_code: QuestionCode
    answer_code: AnswerCode
    subjects: list[Subject] = Field(min_length=1, max_length=1000)
    evidence_ids: list[ID] = Field(max_length=100)

    @model_validator(mode="after")
    def valid_set(self):
        if self.answer_code not in OPTIONS[self.question_code]:
            raise ValueError("answer_not_in_question")
        if len({s.resource_id for s in self.subjects}) != len(self.subjects) or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate_binding")
        return self


class MaterialRequest(CreateRequest):
    subject: Subject
    evidence_ids: list[ID] = Field(min_length=1, max_length=100)
    filename: str = Field(min_length=1, max_length=20)
    content_base64: str = Field(min_length=1, max_length=87384)
    source_sha256: SHA
    source_description: str = Field(min_length=1, max_length=512)
    completeness: Literal["FULL_TEXT_CLAIMED", "EXCERPT"]

    @model_validator(mode="after")
    def unique_refs(self):
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate_evidence")
        return self


class Advice(DTO):
    usage: Use
    saved_value: bool | None
    selection: Literal["SELECTED", "NOT_SELECTED", "UNKNOWN"]
    state: Literal["conditional_candidate", "unknown", "not_selected"]
    scope: Literal["RESOURCE"] = "RESOURCE"
    conditions: list[str]
    gaps: list[str]
    basis_evidence_ids: list[ID]
    rule_ids: list[str]


class ResourceResult(DTO):
    subject: Subject
    resource_kind: Literal["component", "ai_asset"]
    state: State
    verification_state: Literal["candidate_only"] = "candidate_only"
    scope: str
    evidence_ids: list[ID]
    evidence_source_hashes: dict[str, SHA]
    material_ids: list[ID]
    answer_ids: list[ID]
    gaps: list[str]
    advice: list[Advice]
    user_assertions: dict[str, AnswerCode]
    inherited_local_support: bool
    inherited_support_source: Literal["PARENT_ASSESSMENT_NOT_NEW_VALUE"] = "PARENT_ASSESSMENT_NOT_NEW_VALUE"


class Question(DTO):
    question_id: ID
    question_code: QuestionCode
    origin: Literal["DETERMINISTIC_P2_NOT_R6_AGGREGATE"] = "DETERMINISTIC_P2_NOT_R6_AGGREGATE"
    subjects: list[Subject]
    options: list[AnswerCode]
    scope_rule: Literal["EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN"] = "EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN"


class Result(DTO):
    schema_version: Literal["openguard-p2-result/1"] = VERSION
    algorithm_version: Literal["p2-bound-candidate/1"] = ALGORITHM
    result_id: ID
    revision: int = Field(ge=1)
    previous_result_id: ID | None
    result_sha256: SHA
    binding: Binding
    data_scope: Literal["OWNER", "TEST_ONLY"]
    computation: Literal["DETERMINISTIC_P2B"] = "DETERMINISTIC_P2B"
    publication_status: Literal["succeeded"] = "succeeded"
    formal_effect: Literal["none"] = "none"
    model_calls: Literal[0] = 0
    state: State
    created_at: str
    usage: dict[Use, bool | None]
    resources: list[ResourceResult]
    questions: list[Question]
    material_ids: list[ID]
    answer_ids: list[ID]
    recomputed_resource_ids: list[ID]
    reused_resource_ids: list[ID]
    companion_summary_id: ID


class Answer(DTO):
    answer_id: ID
    revision: int
    binding: Binding
    question_id: ID
    question_code: QuestionCode
    answer_code: AnswerCode
    subjects: list[Subject]
    evidence_ids: list[ID]
    provenance: Literal["USER_ASSERTED"] = "USER_ASSERTED"
    formal_effect: Literal["none"] = "none"
    data_scope: Literal["OWNER", "TEST_ONLY"]


class Material(DTO):
    material_id: ID
    revision: Literal[1] = 1
    binding: Binding
    subject: Subject
    evidence_ids: list[ID]
    filename: str
    source_sha256: SHA
    byte_count: int = Field(ge=1, le=65536)
    completeness: Literal["FULL_TEXT_CLAIMED", "EXCERPT"]
    parse_status: Literal["text_observed"] = "text_observed"
    adoption_status: Literal["adopted_as_unverified_observation"] = "adopted_as_unverified_observation"
    verification_state: Literal["pending"] = "pending"
    source_level: Literal["user_supplied_unverified"] = "user_supplied_unverified"
    formal_effect: Literal["none"] = "none"
    data_scope: Literal["OWNER", "TEST_ONLY"]


class Summary(DTO):
    summary_id: ID
    result_id: ID
    result_revision: int
    result_sha256: SHA
    binding: Binding
    material_ids: list[ID]
    answer_ids: list[ID]
    state: State
    resource_states: dict[str, State]
    formal_effect: Literal["none"] = "none"
    report_kind: Literal["P2_COMPANION_NOT_FORMAL_REPORT"] = "P2_COMPANION_NOT_FORMAL_REPORT"


class Receipt(DTO):
    result: Result
    answer: Answer | None = None
    material: Material | None = None


class ResultIndex(DTO):
    head_result_id: ID | None
    head_revision: int
    result_ids: list[ID]
    has_more: bool


class ErrorBody(DTO):
    code: str
    message: str
    request_id: str
    details: dict


class ErrorEnvelope(DTO):
    error: ErrorBody


class P2Error(Exception):
    def __init__(self, code, status=409, **details):
        self.code, self.status, self.details = code, status, details
        super().__init__(code)
