"""P1 projection DTOs checked against the frozen JSON Schemas."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
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


class P1DiffResourceRef(P1Model):
    scan_id: Text
    resource_kind: Literal['component', 'ai_asset']
    resource_id: Text
    resource_identity_key: Text | None
    resource_instance_key: Text | None


class P1DiffEvidenceRef(P1Model):
    namespace: Literal['scan'] = 'scan'
    scan_id: Text
    evidence_id: Text


class P1DiffFieldChange(P1Model):
    path: Text
    before: str | None
    after: str | None


class P1DiffFactChange(P1DiffFieldChange):
    source_ids_before: list[Text]
    source_ids_after: list[Text]
    evidence_refs: list[P1DiffEvidenceRef]


class P1DiffResourceChange(P1Model):
    kind: Literal['added', 'not_observed_in_target', 'changed', 'ambiguous', 'unmatched']
    before: P1DiffResourceRef | None
    after: P1DiffResourceRef | None
    field_changes: list[P1DiffFieldChange]
    evidence_refs: list[P1DiffEvidenceRef]
    removal_confirmed: bool | None


class P1AssessmentDiff(P1Model):
    status: Literal['compared', 'not_comparable', 'unavailable']
    base: P1AssessmentRef | None
    target: P1AssessmentRef | None
    reason: Text | None
    changes: list[P1DiffFactChange]


class P1DiffCoverage(P1Model):
    gaps: list[Text]
    base_complete: bool
    target_complete: bool


class P1ScanDiffView(P1Model):
    schema_version: Literal['1.0'] = '1.0'
    view_id: Text
    base: P1ScanRef
    target: P1ScanRef
    project_identity_key: Text
    resources: list[P1DiffResourceChange]
    license_observation_changes: list[P1DiffFactChange]
    verification_changes: list[P1DiffFactChange]
    finding_changes: list[P1DiffFactChange]
    assessment_diff: P1AssessmentDiff
    coverage: P1DiffCoverage
    provenance: P1HistoryProvenance


class P1GraphFilter(P1Model):
    resource_ids: list[Text]
    resource_kinds: list[Literal['component', 'ai_asset']]


class P1GraphNode(P1Model):
    id: Text
    kind: Literal['project', 'component', 'ai_asset', 'license_observation', 'evidence', 'finding', 'obligation']
    source_id: Text
    label: Text


class P1SourcePointer(P1Model):
    scan_id: Text
    pointer: Annotated[str, Field(pattern=r'^/')]


class P1GraphEdge(P1Model):
    id: Text
    type: Literal['PROJECT_HAS_RESOURCE', 'RESOURCE_HAS_LICENSE_OBSERVATION', 'RESOURCE_SUPPORTED_BY_EVIDENCE', 'RESOURCE_HAS_FINDING', 'FINDING_SUPPORTED_BY_EVIDENCE', 'FINDING_REFERENCES_OBLIGATION', 'LICENSE_HAS_RULE_OBLIGATION']
    source: Text
    target: Text
    source_refs: Annotated[list[P1SourcePointer], Field(min_length=1)]


class P1GraphCoverage(P1Model):
    view_complete: Literal[True]
    scope: Literal['all', 'filtered']
    node_count: Annotated[int, Field(ge=0)]
    edge_count: Annotated[int, Field(ge=0)]
    scan_gaps: list[Text]


class P1GraphCapacity(P1Model):
    max_nodes: Annotated[int, Field(ge=1)]
    max_edges: Annotated[int, Field(ge=1)]


class P1ResourceGraphView(P1Model):
    schema_version: Literal['1.0']
    view_id: Text
    formal: Literal[False]
    scan_ref: P1ScanRef
    filter: P1GraphFilter
    nodes: list[P1GraphNode]
    edges: list[P1GraphEdge]
    coverage: P1GraphCoverage
    capacity: P1GraphCapacity
    provenance: P1HistoryProvenance


class P1GraphCapacityDetails(P1Model):
    reason: Literal['graph_capacity_exceeded']
    count_basis: Literal['estimated', 'actual']
    node_count: Annotated[int, Field(ge=0)]
    edge_count: Annotated[int, Field(ge=0)]
    configured_capacity: P1GraphCapacity


class P1GraphCapacityErrorBody(P1Model):
    code: Literal['graph_capacity_exceeded']
    message: Text
    request_id: Text
    details: P1GraphCapacityDetails


class P1GraphCapacityErrorEnvelope(P1Model):
    error: P1GraphCapacityErrorBody


TaskStatus = Literal['todo', 'in_progress', 'done', 'dismissed']
TaskNote = Annotated[str, Field(strict=True, max_length=2000)]


class P1ScanEvidenceRef(P1Model):
    namespace: Literal['scan']
    scan_id: Text
    evidence_id: Text


class P1ProfileObservationEvidenceRef(P1Model):
    namespace: Literal['profile_observation']
    observation_id: Text


P1EvidenceRef = P1ScanEvidenceRef | P1ProfileObservationEvidenceRef


class P1TaskOrigin(P1Model):
    kind: Literal['condition', 'restriction', 'gap', 'next_step', 'obligation']
    source_pointer: Annotated[str, Field(pattern=r'^/')]
    source_hash: Hash


class P1RemediationTask(P1Model):
    schema_version: Literal['1.0']
    task_id: Text
    scan_id: Text
    assessment_ref: P1AssessmentRef
    origin: P1TaskOrigin
    resource_ids: list[Text]
    evidence_refs: list[P1EvidenceRef]
    title: Annotated[str, Field(min_length=1, max_length=500)]
    status: TaskStatus
    note: TaskNote
    version: Annotated[int, Field(strict=True, ge=1)]
    superseded: bool
    created_at: Utc
    updated_at: Utc
    provenance: P1HistoryProvenance

    @model_validator(mode='after')
    def final_note(self):
        if self.status in {'done', 'dismissed'} and not self.note.strip():
            raise ValueError('terminal task status requires a nonblank note')
        return self


class P1TaskDeriveRequest(P1Model):
    idempotency_key: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    expected_facts_hash: Hash

    @model_validator(mode='after')
    def valid_key(self):
        if not self.idempotency_key.strip():
            raise ValueError('idempotency key must not be blank')
        return self


def _patch_field_schema(schema: dict) -> None:
    # Python defaults are placeholders; omitted PATCH fields preserve stored values.
    schema.pop('default', None)


class P1TaskPatchRequest(P1Model):
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    status: TaskStatus = Field(default='todo', json_schema_extra=_patch_field_schema,
                               description='Omitted: preserve current status. Explicit null is invalid.')
    note: TaskNote = Field(default='', json_schema_extra=_patch_field_schema,
                           description='Omitted: preserve current note. Explicit null is invalid.')

    @model_validator(mode='after')
    def has_change(self):
        if not self.model_fields_set & {'status', 'note'}:
            raise ValueError('status or note is required')
        return self


class P1TaskCollection(P1Model):
    schema_version: Literal['1.0'] = '1.0'
    items: list[P1RemediationTask]


class P1TaskPage(P1TaskCollection):
    next_cursor: str | None
