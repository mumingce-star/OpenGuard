"""Real ASGI/store analysis repair; all source/model transport is SYNTHETIC_TEST_ONLY."""
from copy import deepcopy
import hashlib
import json
import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.p2.contract import canonical, P2Error
from app.p2.official_sources import ExplicitAnalysisRequest, OfficialSourceService
from app.ai.p2_analysis import PROMPT_VERSION, prompt_for
from test_official_sources import flow, ready


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('OFFLINE_TEST_SOCKET_FORBIDDEN')
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket.socket, 'connect', blocked)


def eligible(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    model.model = {**model.model, 'prompt_version': 'p2-bound-material-actions/6'}
    def invalid(value):
        value['actions'][0]['text'] = '核对许可条款中是否包含对分发的明确限制。'
    model.mutate = invalid
    previous = ready(flow)
    assert previous['analysis']['state'] == 'failed'
    assert previous['analysis']['error_code'] == 'p2_ai_output_rejected'
    old_preview = previous['analysis']['preview']
    assert old_preview['model_calls'] == 1
    model.mutate = None
    model.model = {**model.model, 'prompt_version': PROMPT_VERSION}
    svc.analysis_repair_scan_id = run.id
    app.state.p2_service.official_sources = svc
    with svc.store.connection() as db:
        old_job_raw, old_job_sha = db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?',
                                             ('analysis', result['result_id'])).fetchone()
        old_preview_raw, old_preview_sha = db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?',
                                                     (old_preview['preview_id'],)).fetchone()
    row = next(x for x in result['resources'] if x['subject'] == previous['candidate']['subject'])
    body = {'binding': result['binding'], 'result_id': result['result_id'], 'result_sha256': result['result_sha256'],
            'candidate_id': previous['candidate']['candidate_id'], 'previous_preview_id': old_preview['preview_id'],
            'prompt_version': PROMPT_VERSION,
            'prompt_sha256': hashlib.sha256(prompt_for(svc._preview_input(result, row, previous['candidate'])).encode()).hexdigest(),
            'idempotency_key': 'synthetic-analysis-repair-001'}
    return body, old_job_raw, old_job_sha, old_preview_raw, old_preview_sha


def url(run, a):
    return f'/api/v1/scans/{run.id}/assessments/{a.id}/p2/official-sources'


def test_actual_asgi_repair_202_once_no_fetch_no_result_write_preserves_failed_bytes(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    body, old_job_raw, old_job_sha, old_preview_raw, old_preview_sha = eligible(flow)
    result_raw = canonical(result)
    p2_before = svc.p2.store.path.read_bytes()
    with TestClient(app) as client:
        rejected = client.post(url(run, a)+'/analyze', json=body, headers={'Origin': 'https://evil.example'})
        assert rejected.status_code == 403
        duplicate = json.dumps(body)[:-1] + ',"result_id":"p2res_duplicate"}'
        assert client.post(url(run, a)+'/analyze', content=duplicate,
                           headers={'Content-Type': 'application/json'}).status_code == 422
        assert model.calls == fetcher.calls == 1
        response = client.post(url(run, a)+'/analyze', json=body)
        assert response.status_code == 202, response.text
        assert svc.wait_idle()
        saved = client.get(url(run, a), params={'assessment_version': 1, 'result_id': result['result_id']}).json()
        assert saved['analysis']['state'] == 'ready', saved
        assert saved['analysis']['preview']['status'] == 'succeeded'
        assert saved['analysis']['preview_id'] != body['previous_preview_id']
        assert saved['analysis']['analysis_attempt']['prompt_version'] == PROMPT_VERSION
        assert saved['analysis']['analysis_attempt']['previous_preview_id'] == body['previous_preview_id']
        assert fetcher.calls == 1 and model.calls == 2
        assert not saved['adopted_material_ids']
        again = client.post(url(run, a)+'/analyze', json=body)
        assert again.status_code == 202
        assert svc.wait_idle() and model.calls == 2 and fetcher.calls == 1
        changed = {**body, 'idempotency_key': 'synthetic-analysis-repair-002'}
        assert client.post(url(run, a)+'/analyze', json=changed).status_code == 409
        for _ in range(3):
            assert client.get(url(run, a), params={'assessment_version': 1, 'result_id': result['result_id']}).status_code == 200
        svc.on_result(run.id, a.id, result); svc.on_terminal(run)
        assert svc.wait_idle() and model.calls == 2 and fetcher.calls == 1
    with svc.store.connection() as db:
        original = db.execute('SELECT payload,sha256 FROM official_job_history WHERE kind=? AND key=? AND sha256=?',
                              ('analysis', result['result_id'], old_job_sha)).fetchone()
        assert original == (old_job_raw, old_job_sha)
        assert db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?',
                          (body['previous_preview_id'],)).fetchone() == (old_preview_raw, old_preview_sha)
        assert db.execute('SELECT count(*) FROM official_explicit_analysis_requests').fetchone()[0] == 1
    assert canonical(svc.p2.read(run.id, a.id, result['result_id'], 1)) == result_raw
    assert svc.p2.store.path.read_bytes() == p2_before


@pytest.mark.parametrize('wrong', ['binding', 'result_hash', 'candidate', 'previous_preview', 'prompt_hash',
    'prompt_version', 'scope', 'read_only', 'jobs_disabled', 'not_current', 'ready_job', 'uncertain_job',
    'wrong_error', 'saved_material', 'zero_model_calls', 'same_prompt', 'preview_binding'])
def test_exact_gate_rejects_before_model_without_archiving_or_fetch(flow, monkeypatch, wrong):
    svc, run, a, result, fetcher, model, app, root = flow
    original, *_ = eligible(flow)
    body = deepcopy(original)
    if wrong == 'binding': body['binding']['usage_hash'] = 'f'*64
    elif wrong == 'result_hash': body['result_sha256'] = 'f'*64
    elif wrong == 'candidate': body['candidate_id'] = 'p2src_wrong'
    elif wrong == 'previous_preview': body['previous_preview_id'] = 'p2preview_wrong'
    elif wrong == 'prompt_hash': body['prompt_sha256'] = 'f'*64
    elif wrong == 'prompt_version': body['prompt_version'] = 'p2-bound-material-actions/6'
    elif wrong == 'scope': svc.analysis_repair_scan_id = 'scn_other'
    elif wrong == 'read_only': svc.p2.readonly = True
    elif wrong == 'jobs_disabled': svc.jobs_enabled = False
    elif wrong == 'not_current': monkeypatch.setattr(svc.p2.assessments, 'latest', lambda sid: None)
    else:
        with svc.store.connection(write=True) as db:
            job = svc.store.job(db, 'analysis', result['result_id'])
            if wrong == 'ready_job': job['state'] = 'ready'
            elif wrong == 'uncertain_job': job['state'] = 'outcome_unknown'
            elif wrong == 'wrong_error': job['error_code'] = 'p2_ai_model_unavailable'
            elif wrong == 'saved_material': job['mode'] = 'saved_material'
            else:
                old_id = job['preview_id']
                value = svc.store.decode(db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?', (old_id,)).fetchone())
                value.pop('preview_id'); value.pop('preview_sha256')
                if wrong == 'zero_model_calls': value['model_calls'] = 0
                elif wrong == 'same_prompt': value['model']['prompt_version'] = PROMPT_VERSION
                else: value['binding']['usage_hash'] = 'e'*64
                from app.p2.contract import digest
                sha = digest(value); value.update(preview_id='p2preview_'+sha, preview_sha256=sha)
                raw = canonical(value)
                db.execute('INSERT INTO official_previews VALUES(?,?,?)', (value['preview_id'], raw, hashlib.sha256(raw).hexdigest()))
                job['preview_id'] = value['preview_id']; body['previous_preview_id'] = value['preview_id']
            svc.store.put_job(db, 'analysis', result['result_id'], job)
    with TestClient(app) as client:
        response = client.post(url(run, a)+'/analyze', json=body)
        assert response.status_code in {403, 409}, response.text
    assert fetcher.calls == model.calls == 1
    with svc.store.connection() as db:
        assert db.execute('SELECT count(*) FROM official_explicit_analysis_requests').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM official_job_history').fetchone()[0] == 0


def test_same_rejected_generation_is_not_retried_even_after_corrected_attempt_fails(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    body, *_ = eligible(flow)
    model.error = TimeoutError('SYNTHETIC_TEST_ONLY')
    with TestClient(app) as client:
        assert client.post(url(run, a)+'/analyze', json=body).status_code == 202
        assert svc.wait_idle()
        assert client.get(url(run, a), params={'assessment_version': 1, 'result_id': result['result_id']}).json()['analysis']['state'] == 'failed'
        assert client.post(url(run, a)+'/analyze', json=body).status_code == 202
        assert svc.wait_idle() and model.calls == 2 and fetcher.calls == 1


def test_restart_freezes_reserved_analysis_and_never_replays(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    body, *_ = eligible(flow)
    svc._submit = lambda *args: None  # SYNTHETIC process exit between durable intent and dispatch.
    response = svc.request_analysis(run.id, a.id, ExplicitAnalysisRequest.model_validate(body))
    assert response['analysis']['state'] == 'queued'
    svc.close()
    restarted = OfficialSourceService(svc.p2, root/'official', fetcher, svc.ai, analysis_repair_scan_id=run.id)
    try:
        restarted.on_result(run.id, a.id, result); restarted.on_terminal(run)
        again = restarted.request_analysis(run.id, a.id, ExplicitAnalysisRequest.model_validate(body))
        assert again['analysis']['state'] == 'outcome_unknown'
        assert restarted.wait_idle() and model.calls == fetcher.calls == 1
    finally:
        restarted.close()


def test_prompt_drift_after_reservation_refuses_generation(flow, monkeypatch):
    svc, run, a, result, fetcher, model, app, root = flow
    body, *_ = eligible(flow)
    submit = svc._submit
    svc._submit = lambda *args: None
    svc.request_analysis(run.id, a.id, ExplicitAnalysisRequest.model_validate(body))
    import app.p2.official_sources as module
    monkeypatch.setattr(module, 'prompt_for', lambda payload: 'SYNTHETIC_UNREVIEWED_PROMPT_DRIFT')
    submit(svc._analyze, result['result_id'])
    assert svc.wait_idle()
    saved = svc.status(run.id, a.id, 1, result['result_id'])
    assert saved['analysis']['error_code'] == 'official_source_analysis_repair_prompt_conflict'
    assert model.calls == fetcher.calls == 1


def test_runtime_accepts_explicit_14_generation_cap_and_exact_repair_scan(tmp_path, monkeypatch):
    from app.api.official_runtime import configure_official_sources
    import app.p2.official_sources as module
    seen = []
    values = {'OPENGUARD_OFFICIAL_SOURCE_AUTO': '1', 'OPENGUARD_P2_AI_MAX_GENERATIONS': '14',
              'OPENGUARD_OFFICIAL_HTTP_MAX_TASK': '35', 'OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH': str(tmp_path/'http.json'),
              'OPENGUARD_OFFICIAL_ANALYSIS_REPAIR_SCAN_ID': 'scn_exact_repair_test'}
    for key, value in values.items(): monkeypatch.setenv(key, value)
    monkeypatch.setattr(module, 'OfficialSourceService', lambda *args, **kwargs: seen.append(kwargs) or SimpleNamespace())
    configure_official_sources(SimpleNamespace(readonly=False, data_scope='TEST_ONLY', ai_analysis=object()),
                               SimpleNamespace(assessment_saved_observer=None), None, tmp_path)
    assert seen[0]['analysis_repair_scan_id'] == values['OPENGUARD_OFFICIAL_ANALYSIS_REPAIR_SCAN_ID']
    assert not (tmp_path/'http.json').exists()
