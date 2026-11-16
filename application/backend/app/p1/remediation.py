"""Deterministic task workflow over explicit, immutable Formal Assessment facts."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from uuid import NAMESPACE_URL, uuid5
from functools import wraps

from pydantic import ValidationError
from app.api.service import ApiError
from app.assessment.engine import canonical_bytes, facts_digest
from app.assessment.store import AssessmentStoreError
from app.persistence import ScanRegistryError
from .graph import GraphReader
from .history import utc
from .models import P1AssessmentRef, P1RemediationTask, P1TaskPage, P1TaskCollection
from .remediation_store import RemediationTaskStore, RemediationStoreError

ALGORITHM = 'remediation-tasks/1.0'
SORT = 'created_at:asc,task_id:asc'


def fail(code, status=400, reason=None):
    raise ApiError(status_code=status, code=code, message='整改任务请求无法完成。', reason=reason or code)


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def guarded(method):
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except RemediationStoreError as error:
            if error.code == 'not_found':
                fail('not_found', 404)
            if error.code in {'stale_version', 'idempotency_conflict'}:
                fail('conflict', 409, error.code)
            if error.code == 'invalid_argument':
                fail('invalid_argument')
            fail('upstream_unavailable', 503, error.code)
        except ScanRegistryError as error:
            if error.code in {'registry_not_found', 'registry_invalid_argument'}:
                fail('not_found', 404)
            fail('upstream_unavailable', 503)
        except (AssessmentStoreError, ValidationError):
            fail('upstream_unavailable', 503, 'task_source_integrity')
    return call


class RemediationService:
    def __init__(self, registry, assessment_store, store: RemediationTaskStore, *, cursor_key=None):
        self.registry, self.assessments, self.store = registry, assessment_store, store
        self.cursor_key = cursor_key if cursor_key is not None else secrets.token_bytes(32)

    def _assessment(self, scan_id, assessment_id):
        value = self.assessments.get_by_id(assessment_id)
        if value is None:
            fail('not_found', 404)
        if value.scan_id != scan_id:
            fail('conflict', 409, 'assessment_scan_mismatch')
        if not value.formal:
            fail('conflict', 409, 'assessment_not_formal')
        return value

    def _latest_formal(self, scan_id):
        # Read-only overlay. Derivation never selects a latest assessment.
        offset = 0
        while True:
            values = self.assessments.list(scan_id, limit=100, offset=offset)
            for value in values:
                if value.formal:
                    return value
            if len(values) < 100:
                return None
            offset += len(values)

    @staticmethod
    def _assessment_ref(value):
        return P1AssessmentRef(assessment_id=value.id, version=value.version, scan_id=value.scan_id,
            facts_hash=value.facts_hash, usage_hash=value.usage_hash, rule_version=value.rule_version,
            formal=value.formal).model_dump(mode='json')

    @staticmethod
    def _sources(assessment):
        for index, row in enumerate(assessment.resource_evaluations):
            prefix = f'/resource_evaluations/{index}'
            for field, kind in [('conditions','condition'), ('gaps','gap'), ('next_steps','next_step')]:
                for item_index, text in enumerate(getattr(row, field)):
                    yield kind, f'{prefix}/{field}/{item_index}', text, text, [row.resource_id], row.evidence_ids
            for dimension in sorted(row.restrictions):
                key = dimension.replace('~', '~0').replace('/', '~1')
                for item_index, text in enumerate(row.restrictions[dimension]):
                    yield 'restriction', f'{prefix}/restrictions/{key}/{item_index}', text, text, [row.resource_id], row.evidence_ids
        for index, obligation in enumerate(assessment.obligations):
            yield 'obligation', f'/obligations/{index}', obligation.model_dump(mode='json'), obligation.action, obligation.resource_ids, obligation.evidence_ids

    @guarded
    def derive(self, scan_id, assessment_id, request):
        assessment = self._assessment(scan_id, assessment_id)
        fingerprint = digest(dict(scan_id=scan_id, assessment_id=assessment_id, expected_facts_hash=request.expected_facts_hash))
        prior = self.store.request_fingerprint(scan_id, assessment_id, request.idempotency_key)
        if prior is not None and prior != fingerprint:
            fail('conflict', 409, 'idempotency_conflict')
        if assessment.facts_hash != request.expected_facts_hash:
            fail('conflict', 409, 'facts_hash_mismatch')
        stored = self.registry.get(scan_id)
        run = stored.run
        if facts_digest(run) != assessment.facts_hash:
            fail('conflict', 409, 'scan_snapshot_mismatch')
        scan_ref = GraphReader._ref(stored)
        assessment_ref = self._assessment_ref(assessment)
        resource_ids = {r.id for r in run.components} | {r.id for r in run.ai_assets}
        evidence_ids = {e.id for e in run.evidence}
        now = utc(datetime.now(timezone.utc))
        tasks = []
        for kind, pointer, value, text, resources, evidence in self._sources(assessment):
            if not set(resources) <= resource_ids or not set(evidence) <= evidence_ids:
                fail('upstream_unavailable', 503, 'task_source_integrity')
            origin = dict(kind=kind, source_pointer=pointer, source_hash=digest(value))
            identity = dict(scan_id=scan_id, assessment_id=assessment_id, version=assessment.version, origin=origin)
            task_id = 'tsk_' + str(uuid5(NAMESPACE_URL, 'openguard:task:' + digest(identity)))
            parameters_hash = digest(dict(algorithm=ALGORITHM, scan_ref=scan_ref, assessment_ref=assessment_ref, origin=origin))
            task = P1RemediationTask(schema_version='1.0', task_id=task_id, scan_id=scan_id,
                assessment_ref=assessment_ref, origin=origin, resource_ids=sorted(set(resources)),
                evidence_refs=[dict(namespace='scan', scan_id=scan_id, evidence_id=e) for e in sorted(set(evidence))],
                title=text[:500] or kind, status='todo', note='', version=1, superseded=False,
                created_at=now, updated_at=now, provenance=dict(producer={'name':'openguard-remediation','version':'1.0'},
                source_refs=[scan_ref], assessment_refs=[assessment_ref], generated_at=now,
                algorithm_version=ALGORITHM, parameters_hash=parameters_hash))
            tasks.append(task.model_dump(mode='json'))
        saved = self.store.derive(scan_id, assessment_id, request.idempotency_key, fingerprint, tasks)
        return P1TaskCollection(items=[P1RemediationTask.model_validate(t) for t in saved])

    def _encode(self, item, binding):
        payload = canonical_bytes(dict(v=1, sort=SORT, filters=binding, anchor=item['task_id'], created_at=item['created_at']))
        return base64.urlsafe_b64encode(hmac.digest(self.cursor_key, payload, 'sha256') + payload).decode().rstrip('=')

    def _decode(self, token, binding, scan_id, assessment_id):
        try:
            if not isinstance(token, str) or len(token) > 2048:
                raise ValueError()
            data = base64.b64decode(token+'='*(-len(token)%4), altchars=b'-_', validate=True)
            sig, payload = data[:32], data[32:]
            if not hmac.compare_digest(sig, hmac.digest(self.cursor_key, payload, 'sha256')):
                raise ValueError()
            value = json.loads(payload)
            if set(value) != {'v','sort','filters','anchor','created_at'} or value['v'] != 1 or value['sort'] != SORT or value['filters'] != binding:
                raise ValueError()
            item = self.store.get(scan_id, assessment_id, value['anchor'])
            if item is None or item['created_at'] != value['created_at']:
                raise ValueError()
            return value['created_at'], value['anchor']
        except (ValueError, TypeError, KeyError, UnicodeError):
            fail('cursor_invalid')

    @guarded
    def page(self, scan_id, assessment_id, *, cursor=None, limit='20'):
        try:
            size = int(limit)
            if not 1 <= size <= 100 or str(size) != str(limit):
                raise ValueError()
        except (TypeError, ValueError):
            fail('invalid_argument')
        self._assessment(scan_id, assessment_id)
        binding = digest(dict(scan_id=scan_id, assessment_id=assessment_id))
        anchor = self._decode(cursor, binding, scan_id, assessment_id) if cursor is not None else None
        rows = self.store.page(scan_id, assessment_id, limit=size, after=anchor)
        latest = self._latest_formal(scan_id)
        items = []
        for row in rows[:size]:
            value = dict(row, superseded=latest is not None and latest.version > row['assessment_ref']['version'])
            items.append(P1RemediationTask.model_validate(value))
        return P1TaskPage(items=items, next_cursor=self._encode(rows[size-1], binding) if len(rows)>size else None)

    @guarded
    def patch(self, scan_id, assessment_id, task_id, request):
        self._assessment(scan_id, assessment_id)
        changes = request.model_dump(include={'status','note'}, exclude_unset=True)
        value = self.store.patch(scan_id, assessment_id, task_id, request.expected_version, changes)
        return P1RemediationTask.model_validate(value)
