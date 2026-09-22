"""Read persisted Notice snapshots only; no initialization or facts generation."""
from .models import P1NoticeDraft
from .notice_draft_store import NoticeDraftStoreError, validate_snapshot
from .report_v2_integrity import canonical


class ReportNoticeError(RuntimeError):
    def __init__(self, code, reason):
        self.code, self.reason = code, reason
        super().__init__(reason)


class ReportNoticeReader:
    def __init__(self, store):
        self.store = store

    def read(self, scan_id, assessment_id, reference):
        try:
            return self.store.get(scan_id, assessment_id, reference.draft_id)
        except NoticeDraftStoreError as error:
            raise ReportNoticeError('upstream_unavailable', 'notice_store_unavailable') from error


def validate_notice_content(draft):
    """Same strict Notice semantics, also require all persisted fields present."""
    validate_snapshot(draft)
    parsed = P1NoticeDraft.model_validate_json(canonical(draft), strict=True).model_dump(mode='json')
    if canonical(parsed) != canonical(draft):
        raise ValueError('notice_content_incomplete')


def validate_notice_binding(draft, reference, scan_ref, assessment_ref, scan):
    # Task/Graph refs on the report are deliberately NOT part of this comparison.
    if (draft['draft_id'] != reference['draft_id']
            or draft['content_hash'] != reference['content_hash']
            or draft['binding']['scan_ref'] != scan_ref
            or draft['binding']['assessment_ref'] != assessment_ref):
        raise ValueError('notice_binding_mismatch')
    resources = {r['id'] for r in scan['components'] + scan['ai_assets']}
    evidence = {e['id'] for e in scan['evidence']}
    for entry in draft['entries']:
        if (not set(entry['resource_ids']) <= resources
                or any(e['namespace'] != 'scan' or e['scan_id'] != scan['id']
                       or e['evidence_id'] not in evidence for e in entry['evidence_refs'])):
            raise ValueError('notice_source_reference_mismatch')
