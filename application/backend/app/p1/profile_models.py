"""Strict Profile DTO and offline parser port; no network or persistence."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Annotated, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata
from .models import (P1ScanRef, P1DiffResourceRef, P1EvidenceRef, P1HistoryProvenance,
                     P1Producer, P1SourcePointer, Hash, Text)

PORT_VERSION='metadata-parser-port/1'
Status=Literal['verified','pending','not_applicable','rejected']
JobStatus=Literal['pending','succeeded','failed']
Bounded=Annotated[str,Field(min_length=1,max_length=1000)]


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,hide_input_in_errors=True)
    def __repr__(self): return f'<{type(self).__name__}>'
    def __str__(self): return repr(self)


class MetadataField(Strict):
    name: Annotated[str,Field(min_length=1,max_length=100)]
    value: Bounded | None
    locator: Bounded
    verification_status: Status

    @field_validator('name')
    @classmethod
    def field_name(cls,value):
        if value.casefold() in {'raw','payload','body','response','response_blob','headers','cookie','cookies','token',
            'raw_json','raw_bytes','authorization','authorization_status','compliance','formal_assessment','evidence_id','obligation_fulfillment'}:
            raise ValueError('metadata_invalid')
        return value


class ParsedMetadataObservation(Strict):
    parser_version: Annotated[str,Field(min_length=1,max_length=100)]
    bounded_excerpt: Annotated[str,Field(max_length=1000)]
    fields: Annotated[list[MetadataField],Field(max_length=64)]
    verification_status: Status
    coverage_gaps: Annotated[list[Bounded],Field(max_length=64)]


class MetadataParser(Protocol):
    def parse(self, *, provider: str, resource_kind: str, resource_identity: str,
              temporary_metadata: TemporaryMetadata, source_descriptor: SourceDescriptor
              ) -> ParsedMetadataObservation: ...


class MetadataObservation(ParsedMetadataObservation):
    observation_id: Text
    provider: Text
    resource_identity_key: Text
    requested_revision: Text | None
    resolved_revision: Text | None
    source_url: Annotated[str,Field(pattern=r'^https://')]
    fetched_at: str
    content_hash: Hash
    producer: P1Producer
    provenance: P1HistoryProvenance
    full_response_replay_available: Literal[False]

    @field_validator('fetched_at')
    @classmethod
    def utc_date(cls,value):
        if not value.endswith('Z') or datetime.fromisoformat(value.replace('Z','+00:00')).utcoffset()!=timezone.utc.utcoffset(None):
            raise ValueError('metadata_invalid')
        return value


class ProfileIdentity(Strict):
    name: Text
    version: Text | None
    ecosystem: Text | None
    provider: Text | None
    source_url: Text | None


class LicenseObservation(Strict):
    license_expression_id: Text
    expression: Text
    relation_scope: Text
    evidence_refs: list[P1EvidenceRef]
    verification_status: Status


class AuthorizationFact(Strict):
    status: Status
    source_ref: P1SourcePointer


class ResourceProfile(Strict):
    schema_version: Literal['1.0']='1.0'
    profile_id: Text
    scan_ref: P1ScanRef
    resource_ref: P1DiffResourceRef
    identity: ProfileIdentity
    license_observations: list[LicenseObservation]
    authorization_fact: AuthorizationFact | None
    metadata_observations: list[MetadataObservation]
    coverage_gaps: list[Text]
    evidence_refs: list[P1EvidenceRef]
    provenance: P1HistoryProvenance


class RefreshRequest(Strict):
    resource_ids: Annotated[list[Annotated[str,Field(min_length=1,max_length=200)]],Field(min_length=1,max_length=32)]
    expected_facts_hash: Hash
    idempotency_key: Annotated[str,Field(min_length=1,max_length=200)]

    @model_validator(mode='after')
    def normalized(self):
        if not self.idempotency_key.strip() or any(not x.strip() for x in self.resource_ids) or len(set(self.resource_ids))!=len(self.resource_ids):
            raise ValueError('invalid_argument')
        self.resource_ids=sorted(self.resource_ids)
        return self


class RefreshItem(Strict):
    resource_id: Text
    status: JobStatus
    observation_id: Text | None
    error_code: Text | None


class RefreshJob(Strict):
    schema_version: Literal['1.0']='1.0'
    job_id: Text
    scan_id: Text
    facts_hash: Hash
    resource_ids: list[Text]
    status: JobStatus
    items: list[RefreshItem]
    created_at: str
    completed_at: str | None
    algorithm_version: Text
