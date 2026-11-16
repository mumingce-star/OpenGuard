"""SYNTHETIC_TEST_ONLY prior failures; no real model, HTTP, or source adoption."""
from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.assessment.engine import build_assessment
from app.p2.action_plan import ANALYSIS_PROTOCOL, PROMPT_VERSION
from app.p2.contract import CreateRequest, canonical, digest
from app.p2.official_sources import ExplicitAnalysisRequest, OfficialSourceService
from test_action_plan_runner import flow, no_network, PlanModel
from test_official_sources import ready


def prior_failure(flow, monkeypatch):
    svc, run, a, old_result, fetcher, old_model, app, root = flow
    doc = ready(flow)
    usage = a.usage.model_copy(update={'commercial': True, 'distributed': True, 'source_disclosure': True})
    newer = build_assessment(run, usage, version=2)
    app.state.assessment_service.store.create(newer, idempotency_key='synthetic-revalidation-usage', run=run)
    binding = svc.p2.context(run.id, newer.id)[2]
    result = svc.p2.write(run.id, newer.id, CreateRequest(binding=binding, expected_revision=0,
        parent_result_id=None, idempotency_key='synthetic-revalidation-result'), 'create')['result']
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '1')
    class OldChangeModel(PlanModel):
        model = {**PlanModel.model, 'prompt_version': 'p2-bound-action-plan/8'}
        def generate(self, payload):
            value = json.loads(super().generate(payload))
            value['change_explanations'][0]['kind'] = 'resource_change'
            return json.dumps(value)
    svc.ai.provider = OldChangeModel()
    import app.p2.action_plan_runner as runner
    monkeypatch.setattr(runner, 'PROMPT_VERSION', 'p2-bound-action-plan/8')
    svc.on_result(run.id, newer.id, result)
    assert svc.wait_idle()
    previous = svc.status(run.id, newer.id, 2, result['result_id'])
    preview = previous['analysis']['preview']
    assert preview['status'] == 'failed' and preview['model_calls'] == 2
    assert all(x['validation']['code'] == 'plan_change_kind' for x in preview['attempts'])
    monkeypatch.setattr(runner, 'PROMPT_VERSION', PROMPT_VERSION)
    svc.ai.provider = PlanModel()
    svc.analysis_repair_scan_id = run.id
    app.state.p2_service.official_sources = svc
    payload = svc._preview_input(result, result['resources'][0], previous['candidate'])
    version, sha = svc._analysis_prompt_identity(payload, ANALYSIS_PROTOCOL)
    body = {'binding': result['binding'], 'result_id': result['result_id'], 'result_sha256': result['result_sha256'],
        'candidate_id': previous['candidate']['candidate_id'], 'previous_preview_id': preview['preview_id'],
        'prompt_version': version, 'prompt_sha256': sha, 'idempotency_key': 'synthetic-revalidation-v9',
        'analysis_protocol': ANALYSIS_PROTOCOL}
    return newer, result, previous, body


def endpoint(run, newer):
    return f'/api/v1/scans/{run.id}/assessments/{newer.id}/p2/official-sources'


def test_exact_failed_v2_new_schema_event_one_call_preserves_old_failed_preview_and_result(flow, monkeypatch):
    svc, run, _, old_result, fetcher, _, app, root = flow
    newer, result, previous, body = prior_failure(flow, monkeypatch)
    assert body['prompt_version'] == 'p2-bound-action-plan/9'
    with svc.store.connection() as db:
        before_job = db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?', ('analysis', result['result_id'])).fetchone()
        before_preview = db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?', (body['previous_preview_id'],)).fetchone()
    p2_before = svc.p2.store.path.read_bytes()
    with TestClient(app) as client:
        response = client.post(endpoint(run, newer)+'/analyze', json=body)
        assert response.status_code == 202, response.text
        assert svc.wait_idle()
        doc = client.get(endpoint(run, newer), params={'result_id': result['result_id'], 'assessment_version': 2}).json()
        assert doc['analysis']['state'] == 'ready', doc
        assert doc['analysis']['preview']['status'] == 'succeeded'
        receipt = doc['analysis']['analysis_attempt']
        assert receipt['prior_issues'] and all(x['code'] == 'plan_change_kind' for x in receipt['prior_issues'])
        assert receipt['max_model_calls'] == 1 and len(receipt['schema_sha256']) == 64
        assert len(receipt['plan_input_sha256']) == len(receipt['context_sha256']) == 64
        assert doc['analysis']['preview']['validation_details']['model_call_limit'] == 1
        assert len(svc.ai.provider.calls) == 1 and fetcher.calls == 1
        assert client.post(endpoint(run, newer)+'/analyze', json=body).status_code == 202
        assert client.post(endpoint(run, newer)+'/analyze', json={**body, 'idempotency_key': 'different-key'}).status_code == 409
        for _ in range(3):
            assert client.get(endpoint(run, newer), params={'result_id': result['result_id'], 'assessment_version': 2}).status_code == 200
        assert len(svc.ai.provider.calls) == 1
    with svc.store.connection() as db:
        assert db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?', (body['previous_preview_id'],)).fetchone() == before_preview
        assert db.execute('SELECT payload,sha256 FROM official_job_history WHERE kind=? AND key=? AND sha256=?',
            ('analysis', result['result_id'], before_job[1])).fetchone() == before_job
    assert svc.p2.store.path.read_bytes() == p2_before
    assert svc.p2.read(run.id, old_result['binding']['assessment_id'], old_result['result_id'], 1) == old_result
    assert svc.p2.read(run.id, newer.id, result['result_id'], 2) == result


@pytest.mark.parametrize('wrong', ['success', 'same_prompt', 'three_calls', 'context_hash', 'raw_hash',
    'parsed_plan', 'validation_code', 'audit_context', 'current_prompt_hash', 'job_ready'])
def test_invalid_revalidation_never_archives_or_generates(flow, monkeypatch, wrong):
    svc, run, _, _, fetcher, _, app, root = flow
    newer, result, previous, body = prior_failure(flow, monkeypatch)
    preview = deepcopy(previous['analysis']['preview'])
    if wrong == 'current_prompt_hash': body['prompt_sha256'] = 'f'*64
    elif wrong == 'audit_context':
        path = svc.store.path.parent/'action-plan-attempts'/(preview['attempts'][0]['audit_id']+'-intent.json')
        value = json.loads(path.read_text()); value['request']['plan_context']['context_sha256'] = 'f'*64
        path.write_bytes(canonical(value))
    elif wrong != 'job_ready':
        if wrong == 'success': preview['status'] = 'succeeded'
        elif wrong == 'same_prompt': preview['model']['prompt_version'] = PROMPT_VERSION
        elif wrong == 'three_calls': preview['model_calls'] = 3
        elif wrong == 'context_hash': preview['plan_input_sha256'] = 'f'*64
        elif wrong == 'raw_hash': preview['attempts'][0]['raw_output_sha256'] = 'f'*64
        elif wrong == 'parsed_plan': preview['attempts'][0]['parsed_plan']['actions'][0]['target_id'] = 'wrong_target'
        else: preview['attempts'][0]['validation']['code'] = 'plan_other_error'
        preview.pop('preview_id'); preview.pop('preview_sha256')
        sha = digest(preview); preview.update(preview_id='p2preview_'+sha, preview_sha256=sha)
        raw = canonical(preview)
        with svc.store.connection(write=True) as db:
            db.execute('INSERT INTO official_previews VALUES(?,?,?)', (preview['preview_id'], raw, hashlib.sha256(raw).hexdigest()))
            job = svc.store.job(db, 'analysis', result['result_id']); job['preview_id'] = preview['preview_id']
            svc.store.put_job(db, 'analysis', result['result_id'], job)
        body['previous_preview_id'] = preview['preview_id']
    if wrong == 'job_ready':
        with svc.store.connection(write=True) as db:
            job = svc.store.job(db, 'analysis', result['result_id']); job['state'] = 'ready'
            svc.store.put_job(db, 'analysis', result['result_id'], job)
    with TestClient(app) as client:
        response = client.post(endpoint(run, newer)+'/analyze', json=body)
        assert response.status_code == 409, response.text
    assert svc.ai.provider.calls == [] and fetcher.calls == 1
    with svc.store.connection() as db:
        assert db.execute('SELECT count(*) FROM official_explicit_analysis_requests').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM official_job_history').fetchone()[0] == 0


def test_new_version_reservation_restart_and_one_call_failure_do_not_replay(flow, monkeypatch):
    svc, run, _, _, fetcher, _, app, root = flow
    newer, result, previous, body = prior_failure(flow, monkeypatch)
    original = svc._submit
    svc._submit = lambda *args: None
    doc = svc.request_analysis(run.id, newer.id, ExplicitAnalysisRequest.model_validate(body))
    assert doc['analysis']['state'] == 'queued'
    svc.close()
    resumed = OfficialSourceService(svc.p2, root/'official', fetcher, svc.ai, analysis_repair_scan_id=run.id)
    try:
        again = resumed.request_analysis(run.id, newer.id, ExplicitAnalysisRequest.model_validate(body))
        assert again['analysis']['state'] == 'outcome_unknown'
        assert resumed.wait_idle() and svc.ai.provider.calls == [] and fetcher.calls == 1
    finally:
        resumed.close()


def test_explicit_single_call_limit_never_uses_automatic_correction(flow):
    from app.p2.action_plan_runner import run_plan
    from test_action_plan_runner import payload_for
    model = PlanModel(('semantic', 'good'))
    value = run_plan(model, payload_for(flow), audit_root=flow[-1]/'single-call-test', max_model_calls=1)
    assert value['status'] == 'failed' and value['error_code'] == 'p2_ai_output_rejected'
    assert value['model_calls'] == 1 and len(model.calls) == len(value['attempts']) == 1
    assert value['validation_details']['corrective_attempt_used'] is False
    assert value['actions'] == [] and value['plan'] is None
