"""A-owned, offline v2 consumption boundary, not a detector or facts producer.

The injected reader owns per-scan package selection and its independently pinned
canonical hash. No path, URL, generator, or fixture is opened by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Annotated, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


Text = Annotated[str, Field(min_length=1)]
Sha = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Identifier = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.:-]{2,127}$')]
Gap = Annotated[str, Field(pattern=r'^[A-Z][A-Z0-9_]{2,63}$')]
Strength = Literal['text_observed', 'provider_declared_unverified', 'missing']


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class Producer(Strict):
    name: Text
    version: Text


class SourcePackage(Strict):
    path: Text
    schema_version: Text
    fixed_commit: Annotated[str, Field(pattern=r'^[0-9a-f]{40}$')]
    source_file_sha256: Sha
    commit_blob_sha256: Sha


class Evidence(Strict):
    evidence_id: Identifier
    kind: Literal['repository_file', 'archive_entry', 'provider_snapshot']
    locator: Text
    source_url: str | None
    source_revision: Text | None
    content_scope: Literal['whole_file', 'archive_entry', 'json_pointer_value']
    source_file_sha256: Sha
    container_sha256: Sha | None
    selected_content_sha256: Sha
    selected_json_pointer: Annotated[str, Field(pattern=r'^/')] | None
    excerpt: Annotated[str, Field(min_length=1, max_length=1000)]
    verification: Literal['repository_bytes_verified', 'archive_bytes_verified', 'fixture_bytes_verified']
    captured_at: Text
    producer: Producer


class Relationship(Strict):
    state: Literal['observed', 'gap', 'text_observed', 'declared_unverified']
    evidence_ids: list[Identifier]
    gap_code: Gap | None
    applicability: Literal['pending_review']


class Subject(Strict):
    category: Literal['root_project', 'dependency', 'ai_resource']
    canonical_id: Text
    display_name: Text
    version: str | None
    source_url: str | None
    usage_scope: Literal['project', 'runtime', 'test', 'model', 'dataset']
    source_revision: Text | None


class Observation(Strict):
    raw_value: str | list[str] | None
    observation_kind: Literal['license_text_heading', 'provider_declared_raw', 'missing']
    evidence_ids: list[Identifier]
    license_expression_id: None
    observation_strength: Strength


class Relationships(Strict):
    license: Relationship
    notice: Relationship
    copyright: Relationship


class Fact(Strict):
    fact_id: Identifier
    subject: Subject
    authorization_status: Literal['pending']
    license_observations: list[Observation]
    relationships: Relationships
    gaps: list[Gap]
    review_status: Literal['pending_human_review']


class Row(Strict):
    row_id: Identifier
    subject_fact_id: Identifier
    resource_name_and_type: Text
    version_and_source: Text
    license_or_authorization: Text
    usage_or_open_mode: Text
    key_obligations_or_restrictions: Text
    team_modifications: Text
    compliance_status: Literal['待核验']
    authorization_status: Literal['pending']
    license_expression_ids: Annotated[list[str], Field(max_length=0)]
    observation_strengths: Annotated[list[Strength], Field(min_length=1)]
    evidence_ids: list[Identifier]
    gap_codes: list[Gap]


class Policies(Strict):
    license_expression_autofill: Literal[False]
    authorization_default: Literal['pending']
    gap_is_noncompliance: Literal[False]
    notice_absence_is_violation: Literal[False]


class Package(Strict):
    schema_version: Literal['openguard.notice-license-facts/2']
    package_status: Literal['draft_facts_only']
    generated_at: Text
    source_package: SourcePackage
    producer: Producer
    evidence: Annotated[list[Evidence], Field(min_length=1, max_length=20000)]
    facts: Annotated[list[Fact], Field(min_length=1, max_length=20000)]
    report_v2_rows: Annotated[list[Row], Field(min_length=1, max_length=20000)]
    policies: Policies


@dataclass(frozen=True)
class NoticeFactsInput:
    scan_id: str
    facts_hash: str
    package: dict
    expected_package_hash: str


class NoticeFactsReader(Protocol):
    def read(self, scan_id: str, facts_hash: str) -> NoticeFactsInput: ...


def utc(value: str) -> None:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', value):
        raise ValueError('timestamp_invalid')
    datetime.fromisoformat(value[:-1] + '+00:00')


def unique(values) -> set:
    result = set(values)
    if len(result) != len(values):
        raise ValueError('duplicate_values')
    return result


def validate_input(value: NoticeFactsInput, scan_id: str, facts_hash: str) -> Package:
    if not isinstance(value, NoticeFactsInput) or (value.scan_id, value.facts_hash) != (scan_id, facts_hash):
        raise ValueError('notice_source_binding')
    raw = canonical(value.package)
    if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != value.expected_package_hash:
        raise ValueError('notice_package_hash')
    # Validate a detached copy: a reader cannot mutate facts while we construct.
    package = Package.model_validate(json.loads(raw))
    if any(type(v) is not bool or v for k, v in value.package['policies'].items() if k != 'authorization_default'):
        raise ValueError('notice_policy_invalid')
    utc(package.generated_at)
    if package.source_package.source_file_sha256 != package.source_package.commit_blob_sha256:
        raise ValueError('source_package_hash_binding')
    evidence_ids = unique([e.evidence_id for e in package.evidence])
    fact_ids = unique([f.fact_id for f in package.facts])
    unique([r.row_id for r in package.report_v2_rows])
    if unique([r.subject_fact_id for r in package.report_v2_rows]) != fact_ids:
        raise ValueError('report_fact_closure')
    for e in package.evidence:
        utc(e.captured_at)
        if e.source_url is not None and not urlsplit(e.source_url).scheme:
            raise ValueError('source_url_invalid')
        if e.kind == 'repository_file':
            if (e.content_scope != 'whole_file' or e.verification != 'repository_bytes_verified'
                    or e.container_sha256 is not None or e.selected_json_pointer is not None
                    or e.source_file_sha256 != e.selected_content_sha256 or not e.source_revision):
                raise ValueError('repository_evidence_integrity')
        elif e.kind == 'archive_entry':
            if (e.content_scope != 'archive_entry' or e.verification != 'archive_bytes_verified'
                    or e.container_sha256 != e.source_file_sha256 or e.selected_json_pointer is not None):
                raise ValueError('archive_evidence_integrity')
        elif (e.content_scope != 'json_pointer_value' or e.verification != 'fixture_bytes_verified'
              or e.container_sha256 is not None or not e.selected_json_pointer or not e.source_revision
              or not e.locator.endswith('#' + e.selected_json_pointer)):
            raise ValueError('provider_evidence_integrity')
    evidence_by_id = {e.evidence_id: e for e in package.evidence}
    by_id = {f.fact_id: f for f in package.facts}
    for f in package.facts:
        unique(f.gaps)
        if f.subject.source_url is not None and not urlsplit(f.subject.source_url).scheme:
            raise ValueError('subject_url_invalid')
        for r in (f.relationships.license, f.relationships.notice, f.relationships.copyright):
            refs = unique(r.evidence_ids)
            if not refs <= evidence_ids or ((r.state == 'gap') != (r.gap_code is not None)):
                raise ValueError('relationship_integrity')
            if (r.state == 'gap' and (refs or r.gap_code not in f.gaps)) or (r.state != 'gap' and not refs):
                raise ValueError('relationship_source_missing')
        for observation in f.license_observations:
            if not unique(observation.evidence_ids) <= evidence_ids:
                raise ValueError('observation_closure')
            for eid in observation.evidence_ids:
                e = evidence_by_id[eid]
                if e.content_scope == 'json_pointer_value' and digest(observation.raw_value) != e.selected_content_sha256:
                    raise ValueError('selected_value_hash_mismatch')
    for row in package.report_v2_rows:
        fact = by_id[row.subject_fact_id]
        refs = set(fact.relationships.license.evidence_ids + fact.relationships.notice.evidence_ids + fact.relationships.copyright.evidence_ids)
        if (unique(row.evidence_ids) != refs or unique(row.gap_codes) != set(fact.gaps)
                or unique(row.observation_strengths) != {o.observation_strength for o in fact.license_observations}):
            raise ValueError('report_machine_fields_mismatch')
    return package
