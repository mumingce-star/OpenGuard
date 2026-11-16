"""Opt-in TASK-only wiring. Observers are future write events, never read/startup replays."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import threading

from app.p2.contract import CreateRequest, P2Error


def configure_official_sources(p2, assessments, registry, data_dir):
    enabled = os.environ.get('OPENGUARD_OFFICIAL_SOURCE_AUTO', '0')
    if enabled not in {'0', '1'}:
        raise RuntimeError('invalid official-source configuration')
    if enabled == '0':
        return
    if (p2 is None or assessments is None or p2.readonly or p2.data_scope != 'TEST_ONLY'
            or getattr(p2, 'ai_analysis', None) is None
            or os.environ.get('OPENGUARD_P2_AI_MAX_GENERATIONS') not in {'10', '11', '12', '14', '16', '17'}):
        raise RuntimeError('automatic official sources require writable isolated TEST_ONLY and bounded local AI')
    budget = os.environ.get('OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH')
    if not budget or not Path(budget).is_absolute():
        raise RuntimeError('official HTTP requires an explicit task-shared budget')
    max_task_http = os.environ.get('OPENGUARD_OFFICIAL_HTTP_MAX_TASK', '18')
    if max_task_http not in {'18', '24', '29', '35'}:
        raise RuntimeError('invalid official HTTP task limit')
    jobs_enabled = os.environ.get('OPENGUARD_OFFICIAL_JOBS_ENABLED', '1')
    if jobs_enabled not in {'0', '1'}:
        raise RuntimeError('invalid official jobs configuration')
    from app.ingestion.official_http_server import FixedOfficialFetcher
    from app.p2.official_sources import OfficialSourceService
    fetcher = FixedOfficialFetcher(Path(data_dir)/'official-source-http', budget_path=Path(budget),
                                   max_task_http=int(max_task_http))
    # Owner approved only the exact Git-success / npm-version-404 limited branch.
    # Existing failed fetch jobs stay frozen; no startup or GET re-evaluation.
    official = OfficialSourceService(p2, Path(data_dir)/'official-sources', fetcher, p2.ai_analysis,
                                     allow_git_only_404=True, jobs_enabled=jobs_enabled == '1',
                                     explicit_fetch_scan_id=os.environ.get('OPENGUARD_OFFICIAL_EXPLICIT_SCAN_ID') or None,
                                     analysis_repair_scan_id=os.environ.get('OPENGUARD_OFFICIAL_ANALYSIS_REPAIR_SCAN_ID') or None)
    p2.official_sources = official
    previous = assessments.assessment_saved_observer
    event_lock = threading.Lock()

    def record_error(assessment, exc):
        # No user text/credential data, and no mutation of the committed Assessment.
        row = {'utc': datetime.now(timezone.utc).isoformat(), 'assessment_id': assessment.id,
               'scan_id': assessment.scan_id, 'state': 'automatic_initial_result_not_established',
               'code': getattr(exc, 'code', type(exc).__name__), 'retry': 'NONE_AUTOMATIC'}
        path = Path(data_dir)/'official-integration-events.jsonl'
        with event_lock:
            fd = os.open(path, os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'a') as out:
                out.write(json.dumps(row)+'\n')

    def saved(assessment):
        # Preserve the existing NOTICE sidecar, independently from this observer.
        if previous is not None:
            try:
                previous(assessment)
            except Exception as exc:
                record_error(assessment, exc)
        try:
            run, _, binding, _ = p2.context(assessment.scan_id, assessment.id)
            official.on_terminal(run)  # Persistent per-scan reservation: usage changes never refetch.
            body = CreateRequest(binding=binding, expected_revision=0, parent_result_id=None,
                                 idempotency_key='auto_initial_'+assessment.id)
            try:
                receipt = p2.write(assessment.scan_id, assessment.id, body, 'create')
                official.safe_on_result(assessment.scan_id, assessment.id, receipt)
            except P2Error as exc:
                if exc.code != 'p2_revision_conflict':
                    raise
                # A concurrently explicit initial save won. Read its actual fixed identity.
                index = p2.index(assessment.scan_id, assessment.id, assessment.version)
                rid = index['head_result_id']
                if rid is None:
                    raise
                result = p2.read(assessment.scan_id, assessment.id, rid, assessment.version)
                official.safe_on_result(assessment.scan_id, assessment.id, result)
        except Exception as exc:
            record_error(assessment, exc)

    assessments.assessment_saved_observer = saved
