"""Recording-candidate automatic material review, separate from Formal severity."""
from typing import Literal
from pydantic import Field
from .contract import DTO, ID, SHA, Binding, Subject, Use


class SourceReference(DTO):
    kind: Literal['metadata', 'tarball']
    url: str
    sha256: SHA


class SourceMember(DTO):
    member: str
    sha256: SHA


class AutomaticResource(DTO):
    subject: Subject
    name: str
    license_expression: str | None
    state: Literal['CONDITIONAL', 'NONSTANDARD', 'UNAVAILABLE', 'OUTSIDE_NPM']
    priority: Literal['routine', 'attention', 'manual']
    artifact_binding: Literal['RESOLVED_URL_MATCH', 'EXACT_COORDINATE_ONLY', 'NOT_ESTABLISHED']
    conditions: list[str]
    reasons: list[str]
    evidence_ids: list[ID]
    source_refs: list[SourceReference]
    members: list[SourceMember]
    maintenance_deprecated: bool
    applicability_review: Literal['NOT_SIGNED']


class LicenseGroup(DTO):
    license: str
    count: int = Field(ge=0)


class AutomaticSummary(DTO):
    total_resources: int = Field(ge=0)
    priority_counts: dict[Literal['routine', 'attention', 'manual'], int]
    state_counts: dict[Literal['CONDITIONAL', 'NONSTANDARD', 'UNAVAILABLE', 'OUTSIDE_NPM'], int]
    source_packages: int = Field(ge=0)
    license_materials: int = Field(ge=0)
    license_groups: list[LicenseGroup]
    maintenance_count: int = Field(ge=0)


class AutomaticReview(DTO):
    schema_version: Literal['openguard-auto-review/1']
    rule_version: Literal['npm-full-license-review/1']
    review_id: ID
    result_id: ID
    result_sha256: SHA
    binding: Binding
    data_scope: Literal['OWNER', 'TEST_ONLY']
    source_profile_sha256: SHA | None
    source_status: Literal['CHECKED', 'NOT_CONFIGURED']
    usage: dict[Use, bool | None]
    formal_effect: Literal['none']
    model_calls: Literal[0]
    applicability_review: Literal['NOT_SIGNED']
    resources: list[AutomaticResource]
    summary: AutomaticSummary
    limitations: list[str]
