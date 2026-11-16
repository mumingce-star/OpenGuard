"""Fixed official byte observations and asynchronous, immutable Qwen explanations.

Only explicit event hooks schedule work. GETs never fetch, generate, adopt or repair.
The candidate namespace is independent of P2 Material/Result and is not admission.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import os
import re
from pathlib import Path
import sqlite3
import stat
import threading
import time
from typing import Literal

from pydantic import Field
from app.ai.p2_analysis import BudgetError, PROMPT_VERSION, material_quote_candidates, prompt_for
from .ai_analysis import AnalysisRequest, LIMITATIONS, validate_output, validate_saved_semantics
from .contract import Binding, DTO, ID, SHA, MaterialRequest, P2Error, canonical, digest
from .store import P2Store

COMMIT = '0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b'
LICENSE_SHA = 'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6'
GIT_URL = f'https://raw.githubusercontent.com/http-party/http-server/{COMMIT}/LICENSE'
NPM_URL = 'https://registry.npmjs.org/http-server/14.1.2'
# One process-wide queue includes every tenant and both fetch/model work. The
# provider additionally holds its durable global task budget and model mutex.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='fixed-official-source')


def utc():
    return datetime.now(timezone.utc).isoformat()


class ExplicitFetchRequest(DTO):
    binding: Binding
    result_id: ID
    result_sha256: SHA
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


class ExplicitAnalysisRequest(DTO):
    binding: Binding
    result_id: ID
    result_sha256: SHA
    candidate_id: ID
    previous_preview_id: ID
    prompt_version: str = Field(min_length=1, max_length=100)
    prompt_sha256: SHA
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    analysis_protocol: Literal['legacy-v1', 'openguard-qwen-action-plan/2'] = 'legacy-v1'


class AdoptRequest(DTO):
    binding: Binding
    candidate_id: ID
    result_id: ID
    result_sha256: SHA
    expected_revision: int = Field(ge=1)
    parent_result_id: ID
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


class OfficialSourceStore(P2Store):
    def guard(self):
        if self.path.name != 'official-sources.db':
            raise P2Error('official_source_storage_invalid', 503)
        for path in (self.path.parent, self.path):
            info = path.lstat()
            if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077
                    or (path == self.path and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))):
                raise P2Error('official_source_storage_invalid', 503)

    def initialize(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        with self.connection(write=True) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS official_jobs(
                kind TEXT NOT NULL, key TEXT NOT NULL, scan_id TEXT NOT NULL,
                payload BLOB NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(kind,key));
                CREATE TABLE IF NOT EXISTS official_candidates(
                scan_id TEXT PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS official_previews(
                id TEXT PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS official_job_history(
                kind TEXT NOT NULL, key TEXT NOT NULL, payload BLOB NOT NULL, sha256 TEXT NOT NULL,
                archived_at TEXT NOT NULL, PRIMARY KEY(kind,key,sha256));
                CREATE TABLE IF NOT EXISTS official_explicit_fetch_requests(
                scan_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
                payload BLOB NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS official_explicit_analysis_requests(
                scan_id TEXT NOT NULL, result_id TEXT NOT NULL, prompt_version TEXT NOT NULL,
                request_sha256 TEXT NOT NULL, payload BLOB NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(scan_id,result_id,prompt_version));''')
            # A process restart does not replay an uncertain external operation.
            # Also freeze queued work: proof of an unissued operation is not used
            # to silently reinterpret the user's once-per-input event.
            rows = db.execute('SELECT kind,key,payload,sha256 FROM official_jobs').fetchall()
            for kind, key, raw, sha in rows:
                value = self.decode((raw, sha))
                if value['state'] in {'queued', 'running', 'waiting_source'}:
                    value.update(state='outcome_unknown', error_code='official_source_process_interrupted', updated_at=utc())
                    self.put_job(db, kind, key, value)

    def job(self, db, kind, key):
        return self.decode(db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?', (kind, key)).fetchone())

    def put_job(self, db, kind, key, value):
        raw = canonical(value)
        db.execute('INSERT INTO official_jobs VALUES(?,?,?,?,?) ON CONFLICT(kind,key) DO UPDATE SET payload=excluded.payload,sha256=excluded.sha256',
                   (kind, key, value['scan_id'], raw, hashlib.sha256(raw).hexdigest()))

    def candidate(self, db, sid):
        return self.decode(db.execute('SELECT payload,sha256 FROM official_candidates WHERE scan_id=?', (sid,)).fetchone())


class OfficialSourceService:
    def __init__(self, p2, root, fetcher, ai_service, *, allow_git_only_404=False, jobs_enabled=True, explicit_fetch_scan_id=None, analysis_repair_scan_id=None):
        if p2.data_scope != 'TEST_ONLY' or ai_service is None:
            raise ValueError('official sources require isolated TEST_ONLY P2 and AI services')
        if type(allow_git_only_404) is not bool:
            raise ValueError('Git-only 404 capability must be explicit bool')
        if type(jobs_enabled) is not bool:
            raise ValueError('automatic jobs capability must be explicit bool')
        if explicit_fetch_scan_id is not None and (type(explicit_fetch_scan_id) is not str or not re.fullmatch(r'scn_[A-Za-z0-9_-]{1,96}', explicit_fetch_scan_id)):
            raise ValueError('explicit official-source scan identity invalid')
        if analysis_repair_scan_id is not None and (type(analysis_repair_scan_id) is not str or not re.fullmatch(r'scn_[A-Za-z0-9_-]{1,96}', analysis_repair_scan_id)):
            raise ValueError('explicit analysis-repair scan identity invalid')
        self.explicit_fetch_scan_id = explicit_fetch_scan_id
        self.analysis_repair_scan_id = analysis_repair_scan_id
        self.allow_git_only_404 = allow_git_only_404
        self.jobs_enabled = jobs_enabled
        self.p2, self.fetcher, self.ai = p2, fetcher, ai_service
        self.store = OfficialSourceStore(Path(root) / 'official-sources.db')
        self.store.initialize()
        self._lock = threading.RLock()
        self._futures = set()
        self._closed = False

    def _submit(self, callback, *args):
        with self._lock:
            if not self.jobs_enabled:
                raise P2Error('official_source_jobs_disabled', 403)
            if self._closed:
                raise P2Error('official_source_closed', 503)
            future = _EXECUTOR.submit(callback, *args)
            self._futures.add(future)
            future.add_done_callback(self._forget)

    def _forget(self, future):
        with self._lock:
            self._futures.discard(future)

    def close(self):
        # The lifespan must finish bounded in-flight work before closing the
        # parent's registry. Child analyses released by a fetch are included.
        while True:
            with self._lock:
                futures = tuple(self._futures)
                if not futures:
                    self._closed = True
                    return
            wait(futures)

    def wait_idle(self, timeout=10):
        """Test/lifecycle synchronization; never exposed as a product endpoint."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                futures = tuple(self._futures)
            if not futures:
                return True
            if time.monotonic() >= deadline:
                return False
            wait(futures, timeout=max(.001, deadline-time.monotonic()))

    @staticmethod
    def _target(run):
        if (run.project.revision != COMMIT or run.status.value != 'completed'
                or not str(run.project.source or '').rstrip('/').removesuffix('.git') == 'https://github.com/http-party/http-server'):
            raise P2Error('official_source_fixed_sample_required', 403)
        matches = [r for r in run.components if r.name == 'http-server' and r.version == '14.1.2']
        if len(matches) != 1:
            raise P2Error('official_source_exact_resource_required', 409)
        return matches[0]

    def _bound_result(self, sid, aid, version, rid):
        result = self.p2.read(sid, aid, rid, version)
        run, _, binding, resources = self.p2.context(sid, aid)
        resource = self._target(run)
        if result['binding'] != binding or result['data_scope'] != 'TEST_ONLY':
            raise P2Error('official_source_binding_conflict', 409)
        subject = {'resource_id': resource.id, 'version': resource.version}
        row = next((r for r in result['resources'] if r['subject'] == subject), None)
        if row is None:
            raise P2Error('official_source_resource_conflict', 409)
        _, _, allowed = self.p2._evidence(run, resource)
        if not row['evidence_ids'] or sorted(row['evidence_ids']) != sorted(allowed):
            raise P2Error('official_source_evidence_conflict', 409)
        return result, row

    def _explicit_request(self, db, sid):
        row = db.execute('SELECT request_sha256,payload,sha256 FROM official_explicit_fetch_requests WHERE scan_id=?', (sid,)).fetchone()
        if row is None:
            return None
        saved = self.store.decode((row[1], row[2]))
        if saved.get('request_sha256') != row[0] or not isinstance(saved.get('receipt'), dict):
            raise P2Error('official_source_explicit_request_integrity_error', 503)
        return row[0], saved['receipt']

    def _explicit_gate(self, db, sid, aid, result):
        # This is a one-task, exact-scan capability. A zero-dispatch budget
        # refusal is the only historical attempt that can gain a new intent.
        # It is never a retry of a sent, uncertain, rejected or generated input.
        if self._explicit_request(db, sid) is not None:
            return 'already_requested'
        if self.explicit_fetch_scan_id != sid:
            return 'not_enabled_for_scan'
        if self.p2.readonly:
            return 'read_only'
        if not self.jobs_enabled:
            return 'jobs_disabled'
        latest = self.p2.assessments.latest(sid)
        index = self.p2.index(sid, aid, result['binding']['assessment_version'])
        if latest is None or latest.id != aid or index['head_result_id'] != result['result_id']:
            return 'not_current_result'
        fetch = self.store.job(db, 'fetch', sid)
        if (fetch is None or fetch.get('state') != 'failed'
                or fetch.get('error_code') != 'official_source_http_budget_exhausted'
                or fetch.get('retrieval_status') != 'failed'
                or any(type(fetch.get(k)) is not int or fetch[k] != 0
                       for k in ('http_intents', 'http_dispatched', 'http_responses'))):
            return 'fetch_not_zero_dispatch_budget_failure'
        if self.store.candidate(db, sid) is not None:
            return 'saved_source_already_present'
        analysis = self.store.job(db, 'analysis', result['result_id'])
        if (analysis is None or analysis.get('state') != 'failed'
                or analysis.get('error_code') != 'official_source_retrieval_unavailable'
                or analysis.get('analysis_id') is not None or analysis.get('preview_id') is not None
                or analysis.get('mode') is not None
                or analysis.get('binding') != result['binding']
                or analysis.get('result_sha256') != result['result_sha256']):
            return 'analysis_already_started_or_not_source_failure'
        return None

    def request_fetch(self, sid, aid, body):
        if self.p2.readonly:
            raise P2Error('p2_read_only', 403)
        if not self.jobs_enabled or self.explicit_fetch_scan_id != sid:
            raise P2Error('official_source_explicit_fetch_not_enabled', 403)
        result, row = self._bound_result(sid, aid, body.binding.assessment_version, body.result_id)
        if body.binding.model_dump() != result['binding'] or body.result_sha256 != result['result_sha256']:
            raise P2Error('official_source_explicit_fetch_binding_conflict', 409)
        request_sha = digest(body.model_dump(mode='json'))
        dispatch = False
        with self.store.connection(write=True) as db:
            prior = self._explicit_request(db, sid)
            if prior is not None:
                if prior[0] != request_sha:
                    raise P2Error('official_source_explicit_fetch_idempotency_conflict', 409)
            else:
                reason = self._explicit_gate(db, sid, aid, result)
                if reason is not None:
                    raise P2Error('official_source_explicit_fetch_not_eligible', 409, reason=reason)
                now = utc()
                job_id = 'official-explicit-' + digest([sid, body.result_id, request_sha])[:48]
                # Archive the exact original stored bytes, not a reconstructed
                # projection. No update or delete path exists for this table.
                for kind, key in (('fetch', sid), ('analysis', body.result_id)):
                    raw, sha = db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?', (kind, key)).fetchone()
                    self.store.decode((raw, sha))
                    db.execute('INSERT INTO official_job_history VALUES(?,?,?,?,?)', (kind, key, raw, sha, now))
                self.store.put_job(db, 'fetch', sid, {'scan_id': sid, 'job_id': job_id, 'state': 'queued',
                    'subject': row['subject'], 'commit': COMMIT, 'http_intents': 0, 'http_dispatched': 0,
                    'http_responses': 0, 'retrieval_status': None, 'error_code': None,
                    'explicit_result_id': body.result_id, 'created_at': now, 'updated_at': now})
                self.store.put_job(db, 'analysis', body.result_id, {'scan_id': sid, 'assessment_id': aid,
                    'assessment_version': body.binding.assessment_version, 'result_id': body.result_id,
                    'result_sha256': body.result_sha256, 'binding': result['binding'], 'state': 'waiting_source',
                    'mode': None, 'preview_id': None, 'analysis_id': None, 'error_code': None,
                    'created_at': now, 'updated_at': now})
                receipt = {'idempotency_key': body.idempotency_key, 'state': 'accepted', 'requested_at': now,
                           'job_id': job_id, 'result_id': body.result_id, 'result_sha256': body.result_sha256}
                raw = canonical({'request_sha256': request_sha, 'receipt': receipt})
                db.execute('INSERT INTO official_explicit_fetch_requests VALUES(?,?,?,?)',
                           (sid, request_sha, raw, hashlib.sha256(raw).hexdigest()))
                dispatch = True
        if dispatch:
            try:
                self._submit(self._fetch, sid)
            except Exception as exc:
                # Reservation is final even if scheduling fails. GET reconciles
                # the saved receipt; neither a new key nor restart replays it.
                self._finish_error('fetch', sid, getattr(exc, 'code', 'official_source_schedule_failed'))
                self._release_waiting(sid, False)
        return self.status(sid, aid, body.binding.assessment_version, body.result_id)

    def _analysis_request(self, db, sid, rid, version):
        row = db.execute('SELECT request_sha256,payload,sha256 FROM official_explicit_analysis_requests WHERE scan_id=? AND result_id=? AND prompt_version=?',
                         (sid, rid, version)).fetchone()
        if row is None:
            return None
        value = self.store.decode((row[1], row[2]))
        if (value.get('request_sha256') != row[0] or digest(value.get('request')) != row[0]
                or not isinstance(value.get('receipt'), dict)):
            raise P2Error('official_source_analysis_request_integrity_error', 503)
        return row[0], value['receipt']

    def request_analysis(self, sid, aid, body):
        """One explicit corrected-prompt event, not a fetch, GET or restart retry."""
        if self.p2.readonly:
            raise P2Error('p2_read_only', 403)
        if not self.jobs_enabled or self.analysis_repair_scan_id != sid:
            raise P2Error('official_source_analysis_repair_not_enabled', 403)
        result, row = self._bound_result(sid, aid, body.binding.assessment_version, body.result_id)
        if body.binding.model_dump() != result['binding'] or body.result_sha256 != result['result_sha256']:
            raise P2Error('official_source_analysis_repair_binding_conflict', 409)
        requested = body.model_dump(mode='json') if body.analysis_protocol != 'legacy-v1' else body.model_dump(mode='json', exclude={'analysis_protocol'})
        request_sha = digest(requested)
        dispatch = False
        with self.store.connection(write=True) as db:
            prior = self._analysis_request(db, sid, body.result_id, body.prompt_version)
            if prior is not None:
                if prior[0] != request_sha:
                    raise P2Error('official_source_analysis_repair_idempotency_conflict', 409)
            else:
                latest = self.p2.assessments.latest(sid)
                index = self.p2.index(sid, aid, body.binding.assessment_version)
                if latest is None or latest.id != aid or index['head_result_id'] != body.result_id:
                    raise P2Error('official_source_analysis_repair_not_current', 409)
                candidate = self.store.candidate(db, sid)
                if candidate is None or candidate['candidate_id'] != body.candidate_id:
                    raise P2Error('official_source_analysis_repair_candidate_conflict', 409)
                self._check_candidate(candidate, sid, row['subject'])
                fetch = self.store.job(db, 'fetch', sid)
                job = self.store.job(db, 'analysis', body.result_id)
                protocol_two = body.analysis_protocol == 'openguard-qwen-action-plan/2'
                if (fetch is None or fetch['state'] not in {'ready', 'partial'} or job is None
                        or job.get('state') not in ({'ready', 'failed'} if protocol_two else {'failed'})
                        or (not protocol_two and job.get('error_code') != 'p2_ai_output_rejected')
                        or job.get('mode') != 'unadopted_preview' or job.get('analysis_id') is not None
                        or job.get('preview_id') != body.previous_preview_id
                        or job.get('binding') != result['binding'] or job.get('result_sha256') != body.result_sha256):
                    raise P2Error('official_source_analysis_repair_not_eligible', 409)
                preview = self.store.decode(db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?',
                                                      (body.previous_preview_id,)).fetchone())
                if preview is None:
                    raise P2Error('official_source_analysis_repair_preview_conflict', 409)
                checked = dict(preview)
                identity, sha = checked.pop('preview_id', None), checked.pop('preview_sha256', None)
                if (digest(checked) != sha or identity != 'p2preview_' + str(sha)
                        or identity != body.previous_preview_id
                        or (not protocol_two and (preview.get('status') != 'failed' or preview.get('error_code') != 'p2_ai_output_rejected'))
                        or preview.get('candidate_id') != body.candidate_id or preview.get('binding') != result['binding']
                        or preview.get('result_id') != body.result_id or preview.get('result_sha256') != body.result_sha256
                        or type(preview.get('model_calls')) is not int
                        or preview['model_calls'] not in ({1, 2} if protocol_two and preview.get('analysis_protocol') == body.analysis_protocol else {1})
                        or preview.get('model', {}).get('prompt_version') == body.prompt_version):
                    raise P2Error('official_source_analysis_repair_preview_conflict', 409)
                payload = self._preview_input(result, row, candidate)
                legacy_issues = []
                prior_issues, plan_identity = [], {}
                if protocol_two:
                    from .action_plan_runner import enabled
                    from .action_plan import review_legacy_output
                    if not enabled():
                        raise P2Error('official_source_analysis_repair_not_eligible', 409)
                    if preview.get('analysis_protocol') == body.analysis_protocol:
                        if job.get('state') != 'failed' or job.get('error_code') != 'p2_ai_output_rejected':
                            raise P2Error('official_source_analysis_repair_not_eligible', 409)
                        from .plan_revalidation import prior_v2_issues
                        try:
                            prior_issues, plan_identity = prior_v2_issues(preview, payload,
                                audit_root=self.store.path.parent/'action-plan-attempts')
                        except (OSError, ValueError, TypeError, KeyError):
                            raise P2Error('official_source_analysis_repair_prior_proof_conflict', 409) from None
                    else:
                        legacy_issues = review_legacy_output(preview, payload)
                        if preview.get('status') == 'succeeded' and not legacy_issues:
                            raise P2Error('official_source_analysis_repair_no_semantic_issue', 409)
                        if preview.get('status') == 'failed' and preview.get('error_code') != 'p2_ai_output_rejected':
                            raise P2Error('official_source_analysis_repair_not_eligible', 409)
                actual_prompt_version, actual_prompt_sha = self._analysis_prompt_identity(payload, body.analysis_protocol)
                if (body.prompt_version != actual_prompt_version
                        or body.prompt_sha256 != actual_prompt_sha
                        or self.ai.provider.model.get('prompt_version') != actual_prompt_version):
                    raise P2Error('official_source_analysis_repair_prompt_conflict', 409)
                now = utc()
                raw, old_sha = db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?',
                                         ('analysis', body.result_id)).fetchone()
                self.store.decode((raw, old_sha))
                db.execute('INSERT INTO official_job_history VALUES(?,?,?,?,?)', ('analysis', body.result_id, raw, old_sha, now))
                receipt = {'state': 'accepted', 'requested_at': now, 'idempotency_key': body.idempotency_key,
                    'attempt_id': 'official-analysis-' + request_sha[:48], 'result_id': body.result_id,
                    'result_sha256': body.result_sha256, 'candidate_id': body.candidate_id,
                    'previous_preview_id': body.previous_preview_id,
                    'prompt_version': body.prompt_version, 'prompt_sha256': body.prompt_sha256}
                if protocol_two:
                    receipt.update(analysis_protocol=body.analysis_protocol, legacy_review_issues=legacy_issues)
                    if prior_issues:
                        receipt.update(prior_issues=prior_issues, max_model_calls=1, **plan_identity)
                saved = canonical({'request_sha256': request_sha, 'request': requested, 'receipt': receipt})
                db.execute('INSERT INTO official_explicit_analysis_requests VALUES(?,?,?,?,?,?)',
                           (sid, body.result_id, body.prompt_version, request_sha, saved, hashlib.sha256(saved).hexdigest()))
                self.store.put_job(db, 'analysis', body.result_id, {**job, 'state': 'queued', 'mode': None,
                    'preview_id': None, 'analysis_id': None, 'error_code': None, 'updated_at': now,
                    'analysis_attempt': receipt})
                dispatch = True
        if dispatch:
            try:
                self._submit(self._analyze, body.result_id)
            except Exception as exc:
                self._finish_error('analysis', body.result_id, getattr(exc, 'code', 'official_source_schedule_failed'))
        return self.status(sid, aid, body.binding.assessment_version, body.result_id)

    @staticmethod
    def _analysis_prompt_identity(payload, protocol='legacy-v1'):
        if protocol == 'openguard-qwen-action-plan/2':
            from .action_plan import ANALYSIS_PROTOCOL, PROMPT_VERSION as PLAN_VERSION, prepare_plan_payload, plan_prompt
            enriched = prepare_plan_payload({**payload, 'analysis_protocol': ANALYSIS_PROTOCOL})
            return PLAN_VERSION, hashlib.sha256(plan_prompt(enriched).encode('utf-8')).hexdigest()
        return PROMPT_VERSION, hashlib.sha256(prompt_for(payload).encode('utf-8')).hexdigest()

    def on_terminal(self, run):
        if self.p2.readonly or not self.jobs_enabled:
            return
        try:
            resource = self._target(run)
        except P2Error:
            return  # unsupported scans never acquire a network capability
        sid = run.id
        job_id = 'official-' + digest([sid, resource.id, COMMIT])[:48]
        with self.store.connection(write=True) as db:
            if self.store.job(db, 'fetch', sid) is not None:
                return
            self.store.put_job(db, 'fetch', sid, {'scan_id': sid, 'job_id': job_id, 'state': 'queued',
                'subject': {'resource_id': resource.id, 'version': resource.version}, 'commit': COMMIT,
                'http_intents': 0, 'http_dispatched': 0, 'http_responses': 0, 'retrieval_status': None,
                'error_code': None, 'created_at': utc(), 'updated_at': utc()})
        self._submit(self._fetch, sid)

    def on_result(self, sid, aid, receipt_or_result):
        if self.p2.readonly or not self.jobs_enabled:
            return
        result = receipt_or_result.get('result', receipt_or_result)
        version, rid = result['binding']['assessment_version'], result['result_id']
        actual, _ = self._bound_result(sid, aid, version, rid)
        if actual != result:
            raise P2Error('official_source_result_conflict', 409)
        with self.store.connection(write=True) as db:
            if self.store.job(db, 'analysis', rid) is not None:
                return
            fetch = self.store.job(db, 'fetch', sid)
            state = 'queued' if fetch and fetch['state'] in {'ready', 'partial'} else 'waiting_source'
            error = None
            if fetch and fetch['state'] in {'failed', 'outcome_unknown'}:
                state, error = 'failed', 'official_source_retrieval_unavailable'
            self.store.put_job(db, 'analysis', rid, {'scan_id': sid, 'assessment_id': aid,
                'assessment_version': version, 'result_id': rid, 'result_sha256': actual['result_sha256'],
                'binding': actual['binding'], 'state': state, 'mode': None, 'preview_id': None,
                'analysis_id': None, 'error_code': error, 'created_at': utc(), 'updated_at': utc()})
        if state == 'queued':
            self._submit(self._analyze, rid)

    def safe_on_result(self, sid, aid, receipt_or_result):
        """A committed Result remains successful even if auto scheduling fails."""
        try:
            self.on_result(sid, aid, receipt_or_result)
        except Exception as exc:
            result = receipt_or_result.get('result', receipt_or_result)
            try:
                with self.store.connection(write=True) as db:
                    if self.store.job(db, 'analysis', result['result_id']) is None:
                        self.store.put_job(db, 'analysis', result['result_id'], {
                            'scan_id': sid, 'assessment_id': aid, 'assessment_version': result['binding']['assessment_version'],
                            'result_id': result['result_id'], 'result_sha256': result['result_sha256'], 'binding': result['binding'],
                            'state': 'failed', 'mode': None, 'analysis_id': None, 'preview_id': None,
                            'error_code': getattr(exc, 'code', 'official_source_schedule_failed'), 'created_at': utc(), 'updated_at': utc()})
            except Exception:
                # A sidecar storage failure must not turn a committed P2 write
                # into a falsely failed write. Status GET will report storage
                # unavailable, rather than claiming an analysis was scheduled.
                return False
        return True

    def _finish_error(self, kind, key, code, state='failed'):
        with self.store.connection(write=True) as db:
            value = self.store.job(db, kind, key)
            if value is not None:
                value.update(state=state, error_code=code, updated_at=utc())
                self.store.put_job(db, kind, key, value)

    def _body(self, source):
        path = Path(source['body_path'])
        root = Path(self.fetcher.root).resolve(strict=True)
        # Every path segment below the private fetch root must be a real file or
        # directory; resolve containment alone would still permit a symlink alias.
        absolute = path.absolute()
        try:
            relative = absolute.relative_to(root)
        except ValueError:
            raise P2Error('official_source_body_path_invalid', 503) from None
        current = root
        for part in relative.parts:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise P2Error('official_source_body_path_invalid', 503)
        fd = os.open(absolute, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 32768:
                raise P2Error('official_source_body_invalid', 503)
            raw = os.read(fd, 32769)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != source['byte_count'] or hashlib.sha256(raw).hexdigest() != source['sha256']:
                raise P2Error('official_source_body_invalid', 503)
            return raw
        finally:
            os.close(fd)

    def _limited_git_candidate(self, job, receipt):
        """Only the explicitly approved fixed npm 404 permits a partial candidate.

        This does not relabel the transport receipt, recover prior failed jobs,
        accept arbitrary failures, or turn npm 404 into package/source evidence.
        """
        if not self.allow_git_only_404 or receipt.get('status') != 'failed' or receipt.get('error_code') != 'upstream_404' or receipt.get('job_id') != job['job_id']:
            return False
        if any(type(receipt.get(k)) is not int or receipt[k] != 6 for k in ('http_intents', 'http_dispatched', 'http_responses', 'http_sendall_completed')):
            return False
        sources = receipt.get('sources')
        requests = receipt.get('requests')
        if not isinstance(sources, list) or len(sources) != 1 or sources[0].get('kind') != 'git_license' or not isinstance(requests, list) or len(requests) != 6:
            return False
        doh = 'https://cloudflare-dns.com/dns-query'
        plan = [('POST', doh, 'raw.githubusercontent.com', 1), ('POST', doh, 'raw.githubusercontent.com', 28),
                ('GET', GIT_URL, None, None), ('POST', doh, 'registry.npmjs.org', 1),
                ('POST', doh, 'registry.npmjs.org', 28), ('GET', NPM_URL, None, None)]
        for number, (request, identity) in enumerate(zip(requests, plan), 1):
            if (not isinstance(request, dict) or request.get('job_id') != job['job_id']
                    or type(request.get('job_number')) is not int or request['job_number'] != number
                    or tuple(request.get(k) for k in ('method', 'url', 'dns_host', 'dns_type')) != identity
                    or (identity[3] is not None and type(request.get('dns_type')) is not int)
                    or request.get('timed_out') is not False
                    or not isinstance(request.get('dispatch_attempt_utc'), str) or not request['dispatch_attempt_utc']
                    or not isinstance(request.get('first_sendall_completed_utc'), str) or not request['first_sendall_completed_utc']
                    or not isinstance(request.get('finished_utc'), str) or not request['finished_utc']
                    or type(request.get('http_status')) is not int):
                return False
            if number < 6:
                if request.get('state') != 'RESPONSE_COMPLETE' or request['http_status'] != 200:
                    return False
            elif request.get('state') != 'FAILED_NO_RETRY' or request['http_status'] != 404 or request.get('error_code') != 'upstream_404':
                return False
        return True

    def _make_candidate(self, job, receipt):
        partial = self._limited_git_candidate(job, receipt)
        if (receipt.get('status') != 'succeeded' and not partial) or receipt.get('job_id') != job['job_id']:
            raise P2Error('official_source_retrieval_not_succeeded', 503)
        sources = receipt.get('sources')
        expected_kinds = ['git_license'] if partial else ['git_license', 'npm_metadata']
        if not isinstance(sources, list) or [s.get('kind') for s in sources] != expected_kinds:
            raise P2Error('official_source_source_set_invalid', 503)
        if any(receipt.get(k) != 6 for k in ('http_intents', 'http_dispatched', 'http_responses')):
            raise P2Error('official_source_request_ledger_invalid', 503)
        public = []
        for source, expected_url in zip(sources, (GIT_URL, NPM_URL)):
            if (source.get('url') != expected_url or source.get('name') != 'http-server' or source.get('version') != '14.1.2'
                    or source.get('verification_state') != 'pending' or source.get('status') != 'observed'
                    or source.get('source_level') != ('official_repository_bytes_observed' if source['kind'] == 'git_license' else 'provider_declared_unverified')):
                raise P2Error('official_source_identity_invalid', 503)
            raw = self._body(source)
            if source['kind'] == 'git_license':
                if source.get('commit') != COMMIT or len(raw) != 1124 or hashlib.sha256(raw).hexdigest() != LICENSE_SHA:
                    raise P2Error('official_source_license_hash_conflict', 409)
                text = raw.decode('utf-8')
            else:
                from .contract import strict_json
                metadata = strict_json(raw)
                if not isinstance(metadata, dict) or metadata.get('name') != 'http-server' or metadata.get('version') != '14.1.2':
                    raise P2Error('official_source_npm_identity_conflict', 409)
            keys = ('kind', 'url', 'sha256', 'byte_count', 'content_type', 'source_level', 'verification_state', 'name', 'version', 'commit', 'retrieved_at')
            public.append({k: source.get(k) for k in keys})
        value = {'schema_version': 'openguard-official-source-candidate/1', 'scan_id': job['scan_id'],
                 'subject': job['subject'], 'commit': COMMIT, 'sources': public, 'license_text': text,
                 'coverage': 'partial_git_license_only' if partial else 'complete_fixed_sources',
                 'npm_metadata_status': 'missing_404' if partial else 'observed',
                 'source_failures': ([{'kind': 'npm_metadata', 'url': NPM_URL, 'http_status': 404, 'error_code': 'upstream_404',
                                      'request_number': 6, 'retrieved_at': receipt['requests'][-1]['finished_utc']}] if partial else []),
                 'adoption_status': 'not_adopted', 'verification_state': 'pending', 'formal_effect': 'none',
                 'created_at': utc(), 'limitations': [
                     '官方端点取回原字节仅是来源观察，尚未正式接纳；采用前不属于已保存Material。',
                     'Git提交根LICENSE与npm元数据分别记录；未获取npm发行包，不证明发行包LICENSE或实际安装、交付范围。',
                     '采用后仍保持user_supplied_unverified/pending，不自动生成肯定许可结论。']}
        if partial:
            value['limitations'][1] = '仅取得固定Git提交根LICENSE；npm 14.1.2元数据端点明确返回404，版本发行信息缺失。不得视为npm发行包LICENSE、来源接纳或实际交付范围已确认。'
        sha = digest(value)
        value.update(candidate_id='p2src_' + sha, candidate_sha256=sha)
        return value

    def _fetch(self, sid):
        if not self.jobs_enabled:
            return
        try:
            with self.store.connection(write=True) as db:
                job = self.store.job(db, 'fetch', sid)
                if job is None or job['state'] != 'queued': return
                if self.p2.readonly:
                    job.update(state='failed', error_code='p2_read_only', updated_at=utc())
                    self.store.put_job(db, 'fetch', sid, job); return
                job.update(state='running', updated_at=utc()); self.store.put_job(db, 'fetch', sid, job)
            receipt = self.fetcher.fetch(job['job_id'])
            for key in ('http_intents', 'http_dispatched', 'http_responses'):
                value = receipt.get(key)
                if type(value) is not int or not 0 <= value <= 6:
                    raise P2Error('official_source_request_ledger_invalid', 503)
                job[key] = value
            if not job['http_responses'] <= job['http_dispatched'] <= job['http_intents']:
                raise P2Error('official_source_request_ledger_invalid', 503)
            job['error_code'] = receipt.get('error_code')
            job['retrieval_status'] = receipt.get('status')
            with self.store.connection(write=True) as db:
                self.store.put_job(db, 'fetch', sid, job)  # retain real dispatch counts even if candidate validation rejects
            if receipt.get('status') != 'succeeded' and not self._limited_git_candidate(job, receipt):
                job.update(state='outcome_unknown' if receipt.get('status') == 'outcome_unknown' else 'failed', updated_at=utc())
                with self.store.connection(write=True) as db: self.store.put_job(db, 'fetch', sid, job)
                self._release_waiting(sid, False)
                return
            candidate = self._make_candidate(job, receipt)
            raw = canonical(candidate)
            with self.store.connection(write=True) as db:
                db.execute('INSERT INTO official_candidates VALUES(?,?,?)', (sid, raw, hashlib.sha256(raw).hexdigest()))
                job.update(state='partial' if candidate['coverage'] == 'partial_git_license_only' else 'ready',
                           error_code='upstream_404' if candidate['coverage'] == 'partial_git_license_only' else None, updated_at=utc())
                self.store.put_job(db, 'fetch', sid, job)
            self._release_waiting(sid, True)
        except Exception as exc:
            self._finish_error('fetch', sid, exc.code if isinstance(exc, P2Error) else 'official_source_fetch_failed')
            self._release_waiting(sid, False)

    def _release_waiting(self, sid, ready):
        keys = []
        with self.store.connection(write=True) as db:
            for key, raw, sha in db.execute("SELECT key,payload,sha256 FROM official_jobs WHERE kind='analysis' AND scan_id=?", (sid,)).fetchall():
                value = self.store.decode((raw, sha))
                fetch = self.store.job(db, 'fetch', sid)
                if fetch and fetch.get('explicit_result_id') not in (None, key):
                    continue
                if value['state'] == 'waiting_source':
                    value.update(state='queued' if ready else 'failed', error_code=None if ready else 'official_source_retrieval_unavailable', updated_at=utc())
                    self.store.put_job(db, 'analysis', key, value)
                    if ready: keys.append(key)
        for key in keys:
            self._submit(self._analyze, key)

    def _previous_usage_result(self, result, subject):
        # This is an explicit historical selection from durable event identities,
        # never an unqualified latest GET and never a cross-scan Material carry.
        choices = []
        with self.store.connection() as db:
            rows = db.execute("SELECT payload,sha256 FROM official_jobs WHERE kind='analysis' AND scan_id=?", (result['binding']['scan_id'],)).fetchall()
            for raw, sha in rows:
                job = self.store.decode((raw, sha))
                if job['assessment_version'] < result['binding']['assessment_version']:
                    old, old_row = self._bound_result(job['scan_id'], job['assessment_id'], job['assessment_version'], job['result_id'])
                    if (old['result_sha256'] != job['result_sha256'] or old_row['subject'] != subject
                            or old['binding']['project_revision'] != result['binding']['project_revision']):
                        raise P2Error('official_source_previous_binding_conflict', 409)
                    choices.append(old)
        return max(choices, key=lambda r: (r['binding']['assessment_version'], r['revision'])) if choices else None

    def _preview_input(self, result, row, candidate):
        # Existing validator uses a `materials` internal shape. IDs here are the
        # genuine p2src namespace, converted back on output; no fake Material is
        # inserted into Store, Result or emitted by the public preview DTO.
        cid = candidate['candidate_id']
        previous = self._previous_usage_result(result, row['subject'])
        changes = [{'field': 'usage.' + key, 'before': previous['usage'][key], 'after': value}
                   for key, value in result['usage'].items() if previous and previous['usage'][key] != value]
        payload = {'schema_version': 'openguard-official-source-preview-input/1', 'source_candidate_inputs': True,
                   'source_namespace': 'OFFICIAL_RETRIEVED_UNADOPTED_CANDIDATE',
                   'coverage': candidate.get('coverage', 'complete_fixed_sources'),
                   'npm_metadata_status': candidate.get('npm_metadata_status', 'observed'),
                   'source_failures': candidate.get('source_failures', []),
                   'source_limitations': candidate['limitations'],
                   'result_id': result['result_id'], 'result_sha256': result['result_sha256'], 'binding': result['binding'],
                   'subject': row['subject'], 'usage': result['usage'], 'usage_assumption': 'DEMO_USAGE_ASSUMPTION',
                   'resource_state': row['state'], 'gaps': row['gaps'], 'saved_advice': row['advice'],
                   'materials': [{'material_id': cid, 'subject': row['subject'], 'source_sha256': LICENSE_SHA,
                      'byte_count': 1124, 'source_level': 'retrieved_unadopted_candidate', 'verification_state': 'pending',
                      'text': candidate['license_text'], 'quote_candidates': material_quote_candidates(candidate['license_text'])}],
                   'changes': changes, 'change_facts': [{'index': i, 'field': r['field'], 'change_kind': 'value_changed', 'added': None, 'removed': None} for i, r in enumerate(changes)]}
        if previous:
            payload['previous_result'] = {'result_id': previous['result_id'], 'result_sha256': previous['result_sha256'],
                'binding': previous['binding'], 'selection': 'MAX_SAVED_LOWER_ASSESSMENT_VERSION_THEN_REVISION_IN_THIS_SCAN_EVENT_LEDGER'}
        return payload

    def _preview(self, result, row, candidate, *, max_model_calls=2):
        cid = candidate['candidate_id']
        payload = self._preview_input(result, row, candidate)
        start = time.monotonic(); clauses, actions, changes = [], [], []
        status, error = 'failed', None
        protocol_fields = {}
        model_calls = None
        try:
            from .action_plan_runner import enabled, run_plan
            if enabled():
                planned = run_plan(self.ai.provider, payload, audit_root=self.store.path.parent/'action-plan-attempts',
                                   max_model_calls=max_model_calls)
                status, error = planned['status'], planned['error_code']
                clauses, actions, changes = planned['clauses'], planned['actions'], planned['changes']
                model_calls = planned['model_calls']
                protocol_fields = {k: v for k, v in planned.items() if k not in {'status', 'error_code', 'clauses', 'actions', 'changes', 'model_calls'}}
            else:
                raw = self.ai.provider.generate(payload)
                clauses, actions, changes = validate_output(raw, payload)
                status = 'succeeded'
        except BudgetError as exc:
            error = str(exc) if str(exc) in {'p2_ai_budget_invalid', 'p2_ai_budget_exhausted', 'p2_ai_busy', 'p2_ai_input_too_large'} else 'p2_ai_unavailable'
        except (ValueError, TypeError, KeyError):
            error = 'p2_ai_output_rejected'
        except Exception:
            error = 'p2_ai_model_unavailable'
        value = {'schema_version': 'openguard-official-source-preview/1', 'status': status, 'error_code': error,
                 'candidate_id': cid, 'binding': result['binding'], 'result_id': result['result_id'],
                 'coverage': payload['coverage'], 'npm_metadata_status': payload['npm_metadata_status'],
                 'source_failures': payload['source_failures'],
                 'result_revision': result['revision'], 'result_sha256': result['result_sha256'],
                 'usage': result['usage'], 'usage_assumption': 'DEMO_USAGE_ASSUMPTION', 'data_scope': 'TEST_ONLY',
                 'previous_result': payload.get('previous_result'),
                 'created_at': utc(), 'model': dict(self.ai.provider.model), 'input_sha256': digest(payload),
                 'model_calls': model_calls if model_calls is not None else getattr(self.ai.provider, 'model_calls', 0),
                 'metrics': {'elapsed_ms': round((time.monotonic()-start)*1000), **getattr(self.ai.provider, 'last_metrics', {})},
                 'source_refs': [{'candidate_id': cid, 'subject': row['subject'], 'source_sha256': LICENSE_SHA,
                                  'source_level': 'retrieved_unadopted_candidate', 'verification_state': 'pending'}],
                 'clauses': [{('source_candidate_id' if k == 'material_id' else k): v for k, v in c.items()} for c in clauses],
                 'actions': [{('source_candidate_ids' if k == 'source_material_ids' else k): v for k, v in a.items()} for a in actions],
                 'changes': changes, 'formal_effect': 'none', 'quote_index_unit': 'unicode_code_point',
                 'limitations': ['这是尚未采用资料的Qwen预览，不代表Material已保存；确认采用后才更新P2 Result。',
                                *candidate['limitations'], *[x for x in LIMITATIONS if not x.startswith('材料保持')]]}
        value.update(protocol_fields)
        sha = digest(value); value.update(preview_id='p2preview_' + sha, preview_sha256=sha)
        raw = canonical(value)
        with self.store.connection(write=True) as db:
            db.execute('INSERT INTO official_previews VALUES(?,?,?)', (value['preview_id'], raw, hashlib.sha256(raw).hexdigest()))
        return value

    @staticmethod
    def _check_candidate(candidate, sid, subject):
        check = dict(candidate); cid, sha = check.pop('candidate_id'), check.pop('candidate_sha256')
        if (digest(check) != sha or cid != 'p2src_' + sha or candidate['subject'] != subject
                or candidate['scan_id'] != sid or candidate['commit'] != COMMIT
                or len(candidate['license_text'].encode('utf-8')) != 1124
                or hashlib.sha256(candidate['license_text'].encode('utf-8')).hexdigest() != LICENSE_SHA):
            raise P2Error('official_source_candidate_integrity_error', 503)

    def _analyze(self, rid):
        if not self.jobs_enabled:
            return
        try:
            with self.store.connection(write=True) as db:
                job = self.store.job(db, 'analysis', rid)
                if job is None or job['state'] != 'queued': return
                if self.p2.readonly:
                    job.update(state='failed', error_code='p2_read_only'); self.store.put_job(db, 'analysis', rid, job); return
                job.update(state='running', updated_at=utc()); self.store.put_job(db, 'analysis', rid, job)
                candidate = self.store.candidate(db, job['scan_id'])
            result, row = self._bound_result(job['scan_id'], job['assessment_id'], job['assessment_version'], rid)
            if result['result_sha256'] != job['result_sha256'] or candidate is None or candidate['subject'] != row['subject']:
                raise P2Error('official_source_binding_conflict', 409)
            self._check_candidate(candidate, job['scan_id'], row['subject'])
            attempt = job.get('analysis_attempt')
            if attempt is not None:
                payload = self._preview_input(result, row, candidate)
                current_version, current_sha = self._analysis_prompt_identity(payload, attempt.get('analysis_protocol', 'legacy-v1'))
                if (attempt.get('candidate_id') != candidate['candidate_id'] or attempt.get('prompt_version') != current_version
                        or attempt.get('prompt_sha256') != current_sha
                        or self.ai.provider.model.get('prompt_version') != current_version):
                    raise P2Error('official_source_analysis_repair_prompt_conflict', 409)
                if attempt.get('prior_issues'):
                    from .action_plan import ANALYSIS_PROTOCOL, prepare_plan_payload, plan_schema
                    enriched = prepare_plan_payload({**payload, 'analysis_protocol': ANALYSIS_PROTOCOL})
                    if (attempt.get('max_model_calls') != 1 or attempt.get('schema_sha256') != digest(plan_schema(enriched))
                            or attempt.get('plan_input_sha256') != digest(enriched)
                            or attempt.get('context_sha256') != enriched['plan_context']['context_sha256']):
                        raise P2Error('official_source_analysis_repair_prompt_conflict', 409)
            materials = [self.p2.record(job['scan_id'], job['assessment_id'], 'material', mid, job['assessment_version']) for mid in row['material_ids']]
            mids = [m['material_id'] for m in materials if m['source_sha256'] == LICENSE_SHA and m['subject'] == row['subject']]
            if mids:
                body = AnalysisRequest(binding=result['binding'], result_id=rid, result_sha256=result['result_sha256'],
                     material_ids=mids[:4], idempotency_key='official-auto-' + digest([rid, result['result_sha256']])[:48],
                     previous_result_id=result['previous_result_id'])
                analysis = self.ai.create(job['scan_id'], job['assessment_id'], body, source_context=candidate)
                job.update(mode='saved_material', analysis_id=analysis['analysis_id'])
            else:
                analysis = self._preview(result, row, candidate, max_model_calls=attempt.get('max_model_calls', 2) if attempt else 2)
                job.update(mode='unadopted_preview', preview_id=analysis['preview_id'])
            job.update(state='ready' if analysis['status'] == 'succeeded' else 'failed', error_code=analysis['error_code'], updated_at=utc())
            with self.store.connection(write=True) as db: self.store.put_job(db, 'analysis', rid, job)
        except Exception as exc:
            self._finish_error('analysis', rid, exc.code if isinstance(exc, P2Error) else 'official_source_analysis_failed')

    def status(self, sid, aid, version, result_id):
        result, row = self._bound_result(sid, aid, version, result_id)
        with self.store.connection() as db:
            fetch = self.store.job(db, 'fetch', sid)
            candidate = self.store.candidate(db, sid)
            analysis = self.store.job(db, 'analysis', result_id)
            explicit_request = self._explicit_request(db, sid)
            explicit_reason = self._explicit_gate(db, sid, aid, result)
            explicit_fetch = {'allowed': explicit_reason is None, 'reason': explicit_reason or 'eligible_zero_dispatch_budget_failure',
                              'request': explicit_request[1] if explicit_request else None}
            preview = None
            if analysis and analysis['preview_id']:
                preview = self.store.decode(db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?', (analysis['preview_id'],)).fetchone())
                if (preview is None or preview['preview_id'] != analysis['preview_id'] or preview['result_id'] != result_id or preview['result_sha256'] != result['result_sha256']
                        or preview['binding'] != result['binding']):
                    raise P2Error('official_source_preview_binding_conflict', 503)
                check = dict(preview); identity, expected = check.pop('preview_id'), check.pop('preview_sha256')
                if digest(check) != expected or identity != 'p2preview_' + expected:
                    raise P2Error('official_source_preview_integrity_error', 503)
        if candidate:
            self._check_candidate(candidate, sid, row['subject'])
        if analysis and (analysis['binding'] != result['binding'] or analysis['result_sha256'] != result['result_sha256']):
            raise P2Error('official_source_analysis_binding_conflict', 503)
        if preview:
            try:
                if preview.get('analysis_protocol') == 'openguard-qwen-action-plan/2':
                    from .action_plan_runner import validate_saved_plan
                    validate_saved_plan(preview, self._preview_input(result, row, candidate))
                else:
                    validate_saved_semantics(preview, result['usage'])
                    from .action_plan_runner import enabled
                    if enabled():
                        from .action_plan import review_legacy_output
                        issues = review_legacy_output(preview, self._preview_input(result, row, candidate))
                        if issues:
                            raise ValueError('legacy action plan semantic review rejected')
            except (ValueError, TypeError, KeyError) as exc:
                # A read-only projection; original preview, digest, job and model
                # budget are preserved. Old inputs are never regenerated here.
                analysis = {**analysis, 'state': 'failed', 'error_code': 'p2_ai_saved_output_rejected',
                            'preview_sha256': preview['preview_sha256'], 'validation_error': str(exc)}
                preview = None
        elif analysis and analysis.get('analysis_id'):
            try:
                self.ai.read(sid, aid, analysis['analysis_id'], result_id, version)
            except P2Error as exc:
                if exc.code != 'p2_ai_saved_output_rejected':
                    raise
                analysis = {**analysis, 'state': 'failed', 'error_code': exc.code}
        from .local_actions import build_local_actions
        local_actions = build_local_actions(self.p2, result, row, candidate)
        return {'schema_version': 'openguard-official-sources/1', 'binding': result['binding'], 'result_id': result_id,
                'runtime_jobs_enabled': self.jobs_enabled, 'explicit_fetch': explicit_fetch,
                'result_sha256': result['result_sha256'], 'fetch': fetch or {'state': 'not_scheduled', 'job_id': None, 'error_code': None, 'http_intents': 0, 'http_dispatched': 0, 'http_responses': 0},
                'candidate': candidate, 'analysis': {**(analysis or {'state': 'not_scheduled', 'mode': None, 'error_code': None, 'analysis_id': None, 'preview_id': None}), 'preview': preview},
                'adopted_material_ids': [mid for mid in row['material_ids'] if self.p2.record(sid, aid, 'material', mid, version)['source_sha256'] == LICENSE_SHA],
                'local_actions': local_actions}

    def adopt(self, sid, aid, body):
        if self.p2.readonly:
            raise P2Error('p2_read_only', 403)
        result, row = self._bound_result(sid, aid, body.binding.assessment_version, body.result_id)
        if (body.binding.model_dump() != result['binding'] or body.result_sha256 != result['result_sha256']
                or body.parent_result_id != result['result_id'] or body.expected_revision != result['revision']):
            raise P2Error('official_source_adoption_binding_conflict', 409)
        status = self.status(sid, aid, body.binding.assessment_version, body.result_id)
        candidate = status['candidate']
        if status['fetch']['state'] not in {'ready', 'partial'} or candidate is None or candidate['candidate_id'] != body.candidate_id:
            raise P2Error('official_source_candidate_not_ready', 409)
        raw = candidate['license_text'].encode('utf-8')
        if len(raw) != 1124 or hashlib.sha256(raw).hexdigest() != LICENSE_SHA:
            raise P2Error('official_source_license_hash_conflict', 409)
        request = MaterialRequest(binding=body.binding, expected_revision=body.expected_revision,
            parent_result_id=body.parent_result_id, idempotency_key=body.idempotency_key,
            subject=row['subject'], evidence_ids=row['evidence_ids'], filename='LICENSE',
            content_base64=base64.b64encode(raw).decode(), source_sha256=LICENSE_SHA,
            source_description='User confirmed adoption of automatically retrieved Git root LICENSE; '+GIT_URL+'; not npm archive scope or formal source admission.'+(' Fixed npm metadata GET returned 404; npm release information missing.' if candidate.get('npm_metadata_status') == 'missing_404' else ''),
            completeness='FULL_TEXT_CLAIMED')
        receipt = self.p2.write(sid, aid, request, 'material')
        # The router also calls on_result after successful writes; durable dedup
        # makes that safe. A scheduling error must never mislabel a saved result.
        self.safe_on_result(sid, aid, receipt)
        return receipt
