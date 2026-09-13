"""History DTOs checked against the frozen P1 JSON Schema."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.domain.models import ScanStatus, ScanStage, SourceType, ScanSummary

Text = Annotated[str, Field(min_length=1)]
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Utc = Annotated[str, Field(pattern=r'Z$')]


class P1Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class P1GithubIdentity(P1Model):
    method: Literal['canonical_github_repo_v1']
    key: Annotated[str, Field(pattern=r'^github\.com/[^/?#]+/[^/?#]+$')]
    source_project_id: Text


class P1ScanOnlyIdentity(P1Model):
    method: Literal['scan_only']
    key: Text
    source_project_id: Text


class P1ScanRef(P1Model):
    scan_id: Text
    revision: Text | None
    facts_hash: Hash
    input_hash: Hash
    inventory_hash: Hash | None
    status: ScanStatus
    registry_revision: Annotated[int, Field(ge=1)]


class P1AssessmentRef(P1Model):
    assessment_id: Text
    version: Annotated[int, Field(ge=1)]
    scan_id: Text
    facts_hash: Hash
    usage_hash: Hash
    rule_version: Text
    formal: Literal[True]


class P1Producer(P1Model):
    name: Text
    version: Text


class P1HistoryProvenance(P1Model):
    producer: P1Producer
    source_refs: list[P1ScanRef]
    assessment_refs: list[P1AssessmentRef]
    generated_at: Utc
    algorithm_version: Text
    parameters_hash: Hash


class P1ScanHistoryItem(P1Model):
    schema_version: Literal['1.0'] = '1.0'
    scan_id: Text
    project_identity: P1GithubIdentity | P1ScanOnlyIdentity
    source_type: SourceType
    source: Text
    revision: Text | None
    input_hash: Hash
    inventory_hash: Hash | None
    status: ScanStatus
    stage: ScanStage
    created_at: Utc
    finished_at: Utc | None
    component_count: Annotated[int, Field(ge=0)]
    ai_asset_count: Annotated[int, Field(ge=0)]
    finding_count: Annotated[int, Field(ge=0)]
    summary: ScanSummary
    latest_assessment: P1AssessmentRef | None
    provenance: P1HistoryProvenance


class P1HistoryPage(P1Model):
    schema_version: Literal['1.0'] = '1.0'
    items: list[P1ScanHistoryItem]
    next_cursor: str | None
