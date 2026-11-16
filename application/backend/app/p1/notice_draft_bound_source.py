"""Read exact BOUND sources and project observations without formal authority.

No collection, admission, binding, network or source writes occur here.
CZ validation stays in the existing A2 decoder; formal references deliberately
remain empty until a separate, explicitly authorized mapping exists.
"""
from dataclasses import dataclass

from app.notice_source import NoticeSourcePackage
from .notice_source_adapter import decode_bound_notice_source
from .notice_source_store import BoundNoticeSource, BoundNoticeSourceReader

VERSION = 'notice-bound/1.0'


class BoundNoticeDraftSourceError(RuntimeError):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason
        super().__init__(reason)


@dataclass(frozen=True)
class BoundNoticeDraftSource:
    package: NoticeSourcePackage
    package_hash: str
    scan_id: str
    registry_revision: int
    facts_hash: str
    assessment_id: str
    assessment_version: int


def read_bound_draft_source(reader: BoundNoticeSourceReader, stored, assessment) -> BoundNoticeDraftSource:
    run = stored.run
    try:
        bound = reader.read(run.id, assessment.facts_hash, assessment.id, assessment.version)
    except Exception as error:
        # The service exposes only stable reasons, never storage/decoder details.
        raise BoundNoticeDraftSourceError('upstream_unavailable', 'notice_source_unavailable') from error
    if bound is None:
        raise BoundNoticeDraftSourceError('not_ready', 'notice_source_not_bound')
    if not isinstance(bound, BoundNoticeSource):
        raise BoundNoticeDraftSourceError('upstream_unavailable', 'notice_source_invalid')
    if (run.provenance.inventory_digest is None
            or bound.scan_id != run.id
            or bound.registry_revision != stored.revision
            or bound.input_digest != run.provenance.input_digest.value
            or bound.inventory_digest != run.provenance.inventory_digest.value
            or bound.facts_hash != assessment.facts_hash
            or bound.assessment_id != assessment.id
            or bound.assessment_version != assessment.version
            or bound.assessment_facts_hash != assessment.facts_hash):
        raise BoundNoticeDraftSourceError('conflict', 'notice_source_binding_mismatch')
    try:
        package = decode_bound_notice_source(bound)
    except Exception as error:
        raise BoundNoticeDraftSourceError('upstream_unavailable', 'notice_source_invalid') from error
    return BoundNoticeDraftSource(package, bound.package_hash, bound.scan_id,
                                  bound.registry_revision, bound.facts_hash,
                                  bound.assessment_id, bound.assessment_version)


def project_bound_entries(source: BoundNoticeDraftSource) -> tuple[list[dict], set[str]]:
    package = source.package
    gaps = {'draft_only_not_obligation_fulfillment', 'authorization_pending',
            'license_expression_not_inferred', *package.coverage.gap_codes}
    if package.coverage.state == 'partial':
        gaps.add('notice_source_partial')
    if package.coverage.omissions:
        gaps.add('notice_source_omissions_present')
    content_gaps = {
        'excerpt': 'notice_source_excerpt_truncated',
        'not_observed': 'notice_text_not_observed',
        'not_scanned': 'notice_text_not_scanned',
        'read_failed': 'notice_text_read_failed',
    }
    entries = []
    for observation in sorted(package.observations, key=lambda item: item.observation_key):
        content = observation.content
        missing = set(content.gap_codes)
        if content.state in content_gaps:
            missing.add(content_gaps[content.state])
        missing.add('resource_relation_unresolved' if observation.relation.state == 'unresolved'
                    else 'resource_relation_not_formalized')
        gaps.update(missing)
        entries.append(dict(
            entry_id=observation.observation_key, resource_ids=[], license_expression_ids=[],
            obligation_refs=[], evidence_refs=[],
            text=content.text if content.state in {'full', 'excerpt'} else None,
            missing=sorted(missing)))
    return entries, gaps
