"""Evidence-grounded NoticeDraft snapshots; no scanner, AI or network operations."""
from datetime import datetime, timezone
from uuid import uuid4

from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStoreError
from app.persistence import ScanRegistryError
from .models import P1NoticeDraft
from .notice_facts import NoticeFactsReader, validate_input, digest
from .notice_draft_store import NoticeDraftStoreError, content_hash

VERSION = 'notice/1.0'


class NoticeDraftServiceError(RuntimeError):
    def __init__(self, code, reason=None):
        self.code, self.reason = code, reason or code
        super().__init__(self.reason)


def resource_ids(fact, run):
    subject = fact.subject
    candidates = []
    if subject.category == 'dependency' and subject.version is not None:
        candidates = [r.id for r in run.components if r.purl == subject.canonical_id
                      and r.version == subject.version and r.source_url == subject.source_url]
    elif subject.category == 'ai_resource' and subject.version is not None:
        candidates = [r.id for r in run.ai_assets if
                      subject.canonical_id == f'huggingface:{r.asset_type}:{r.name}'
                      and r.version == subject.version and r.source_url == subject.source_url
                      and subject.source_url == ('https://huggingface.co/' + ('datasets/' if str(r.asset_type) == 'dataset' else '') + r.name)]
    return (candidates, None) if len(candidates) == 1 else ([], 'resource_ambiguous' if candidates else 'resource_not_mapped')


def evidence_refs(source, run):
    # P0 cannot express archive-container/provider-pointer provenance completely.
    # Only exact repository-file location + revision + SHA + excerpt may bind.
    if (source.kind != 'repository_file' or source.content_scope != 'whole_file'
            or not source.source_url or run.project.revision != source.source_revision
            or source.source_url != f'{run.project.source}/blob/{source.source_revision}/{source.locator}'):
        return []
    candidates = [e for e in run.evidence if str(e.kind) == 'file' and e.locator == source.locator
                  and e.content_hash is not None and e.content_hash.algorithm == 'sha256'
                  and e.content_hash.value == source.selected_content_sha256
                  and e.excerpt == source.excerpt and str(e.detected_by) != 'ai_candidate']
    if len(candidates) != 1:
        return []
    return [dict(namespace='scan', scan_id=run.id, evidence_id=candidates[0].id)]


class NoticeDraftService:
    def __init__(self, registry, assessment_store, store, *, facts_reader: NoticeFactsReader | None = None):
        self.registry, self.assessment_store, self.store = registry, assessment_store, store
        self.facts_reader = facts_reader

    def create(self, scan_id, assessment_id, *, idempotency_key):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200 or not idempotency_key.strip():
            raise NoticeDraftServiceError('invalid_argument', 'idempotency_key_invalid')
        if self.facts_reader is None:
            raise NoticeDraftServiceError('feature_disabled', 'notice_facts_reader_not_available')
        try:
            stored = self.registry.get(scan_id)
        except ScanRegistryError as error:
            if error.code == 'registry_invalid_argument':
                raise NoticeDraftServiceError('invalid_argument', 'scan_id_invalid') from error
            code = 'not_found' if error.code == 'registry_not_found' else 'upstream_unavailable'
            raise NoticeDraftServiceError(code, 'scan_store_unavailable') from error
        run = stored.run
        if run.status in {'queued', 'running'}:
            raise NoticeDraftServiceError('not_ready', 'scan_not_ready')
        if run.status not in {'completed', 'partial'}:
            raise NoticeDraftServiceError('not_comparable', 'scan_not_comparable')
        try:
            assessment = self.assessment_store.get(scan_id, assessment_id)
            if assessment is None:
                if self.assessment_store.get_by_id(assessment_id) is not None:
                    raise NoticeDraftServiceError('conflict', 'assessment_scan_mismatch')
                raise NoticeDraftServiceError('not_found', 'assessment_not_found')
        except AssessmentStoreError as error:
            raise NoticeDraftServiceError('upstream_unavailable', 'assessment_store_unavailable') from error
        if (run.id != scan_id or assessment.id != assessment_id or assessment.scan_id != scan_id
                or assessment.formal is not True or assessment.facts_hash != facts_digest(run)):
            raise NoticeDraftServiceError('conflict', 'notice_fixed_binding_mismatch')
        if (assessment.input_hash != run.provenance.input_digest.value or assessment.revision != run.project.revision
                or assessment.scan_status != run.status):
            raise NoticeDraftServiceError('conflict', 'notice_fixed_binding_mismatch')
        try:
            source = self.facts_reader.read(scan_id, assessment.facts_hash)
            package = validate_input(source, scan_id, assessment.facts_hash)
        except Exception as error:
            # Reader failures are context-free; paths/URLs/SQL never enter HTTP errors.
            raise NoticeDraftServiceError('upstream_unavailable', 'notice_facts_invalid') from error
        scan_ref = dict(scan_id=run.id, revision=run.project.revision, facts_hash=assessment.facts_hash,
                        input_hash=run.provenance.input_digest.value,
                        inventory_hash=run.provenance.inventory_digest.value if run.provenance.inventory_digest else None,
                        status=str(run.status), registry_revision=stored.revision)
        assessment_ref = dict(assessment_id=assessment.id, version=assessment.version, scan_id=scan_id,
                              facts_hash=assessment.facts_hash, usage_hash=assessment.usage_hash,
                              rule_version=assessment.rule_version, formal=True)
        entries = []
        gaps = {'draft_only_not_obligation_fulfillment', 'authorization_pending', 'license_expression_not_inferred'}
        evidence = {e.evidence_id: e for e in package.evidence}
        for fact in sorted(package.facts, key=lambda f: f.fact_id):
            resources, resource_gap = resource_ids(fact, run)
            missing = set(fact.gaps)
            if resource_gap:
                missing.add(resource_gap)
            refs = []
            source_ids = set(fact.relationships.license.evidence_ids + fact.relationships.notice.evidence_ids + fact.relationships.copyright.evidence_ids)
            for eid in sorted(source_ids):
                mapped = evidence_refs(evidence[eid], run)
                if not mapped:
                    missing.add('source_evidence_not_mapped_to_scan_namespace')
                refs.extend(mapped)
            notice = fact.relationships.notice
            excerpts = []
            if notice.state in {'observed', 'text_observed'}:
                for eid in sorted(notice.evidence_ids):
                    e = evidence[eid]
                    if e.kind in {'repository_file', 'archive_entry'}:
                        excerpts.append(e.excerpt)
            if not excerpts:
                missing.add('notice_text_not_observed')
            gaps.update(missing)
            # These are stable source IDs, never ScanRun evidence IDs.
            entries.append(dict(entry_id=fact.fact_id, resource_ids=resources, license_expression_ids=[],
                                obligation_refs=[], evidence_refs=sorted({digest(r): r for r in refs}.values(), key=lambda r: r['evidence_id']),
                                text='\n'.join(excerpts) if excerpts else None, missing=sorted(missing)))
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        value = dict(schema_version='1.0', draft_id='ntc_' + str(uuid4()), created_at=now,
                     generator_version=VERSION, binding=dict(scan_ref=scan_ref, assessment_ref=assessment_ref,
                     task_refs=[], notice_refs=[], algorithm_refs=[]), entries=entries, coverage_gaps=sorted(gaps),
                     provenance=dict(producer=dict(name='openguard-notice-draft', version='1.0'),
                     source_refs=[scan_ref], assessment_refs=[assessment_ref], generated_at=now,
                     algorithm_version=VERSION, parameters_hash=source.expected_package_hash))
        value['content_hash'] = content_hash(value)
        try:
            saved = self.store.create(scan_id, assessment_id, idempotency_key, value)
        except NoticeDraftStoreError as error:
            raise NoticeDraftServiceError('conflict' if error.code == 'idempotency_conflict' else 'upstream_unavailable', error.code) from error
        return P1NoticeDraft.model_validate(saved)

    def get(self, scan_id, assessment_id, draft_id):
        # Deliberately does not access registry, assessment store, or facts reader.
        try:
            value = self.store.get(scan_id, assessment_id, draft_id)
        except NoticeDraftStoreError as error:
            raise NoticeDraftServiceError('upstream_unavailable', error.code) from error
        return P1NoticeDraft.model_validate(value) if value is not None else None
