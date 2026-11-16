"""SYNTHETIC_TEST_ONLY model transports; actual typed validator and ASGI sidecar."""
from copy import deepcopy
import hashlib
import json
import socket

import pytest
from fastapi.testclient import TestClient

from app.ai.p2_analysis import BudgetError
from app.p2.action_plan import ANALYSIS_PROTOCOL, PROMPT_VERSION, prepare_plan_payload
from app.p2.action_plan_runner import run_plan
from app.p2.contract import canonical
from test_official_sources import flow, ready, adopt_body


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('SYNTHETIC_TEST_ONLY_SOCKET_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', blocked)
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '0')


def selection(payload):
    context = prepare_plan_payload(payload)['plan_context']
    condition = next(q for q in context['quote_catalog'] if q['quote'].startswith('The above copyright notice'))
    chosen = [context['action_catalog'][0]]
    gap = next((a for a in context['action_catalog'] if a['basis_kind'] == 'usage_gap'), None)
    if gap is not None: chosen.append(gap)
    return {'clauses': [{'quote_id': condition['quote_id'], 'category': 'condition'}],
        'actions': [{k: a[k] for k in ('kind', 'target_id', 'basis_kind')} | {'basis_ids': a['eligible_basis_ids']} for a in chosen],
        'change_explanations': [{'index': i, 'kind': 'usage_change' if row['field'].startswith('usage.') else 'resource_change'}
                                for i, row in enumerate(payload.get('changes', []))]}


def payload_for(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    doc = ready(flow)
    row = next(x for x in result['resources'] if x['subject'] == doc['candidate']['subject'])
    return svc._preview_input(result, row, doc['candidate'])


class PlanModel:
    model = {'name': 'SYNTHETIC_TEST_ONLY', 'prompt_version': PROMPT_VERSION}
    model_calls = 0
    last_metrics = {}

    def __init__(self, modes=('good',)):
        self.calls = []
        self.modes = modes

    def generate(self, payload):
        self.calls.append(deepcopy(payload)); self.model_calls = 1
        mode = self.modes[min(len(self.calls)-1, len(self.modes)-1)]
        if mode == 'timeout': raise TimeoutError('SYNTHETIC_TEST_ONLY')
        if mode == 'budget':
            self.model_calls = 0
            raise BudgetError('p2_ai_budget_exhausted')
        if mode == 'malformed': return '{incomplete'
        value = selection(payload)
        if mode == 'semantic': value['clauses'][0]['category'] = 'disclaimer'
        if mode == 'shape': value['actions'][0]['text'] = 'SYNTHETIC_UNKNOWN_FIELD'
        return json.dumps(value, ensure_ascii=False)


def test_one_semantic_correction_uses_exact_feedback_and_preserves_both_raws(flow):
    payload = payload_for(flow); model = PlanModel(('semantic', 'good'))
    out = run_plan(model, payload, audit_root=flow[-1]/'typed-audit')
    assert out['status'] == 'succeeded' and out['model_calls'] == 2
    assert len(model.calls) == len(out['attempts']) == 2
    first, second = out['attempts']
    feedback = model.calls[1]['plan_feedback']
    assert feedback['parent_output_sha256'] == first['raw_output_sha256']
    assert feedback['parent_input_sha256'] == first['input_sha256']
    assert feedback['code'] == 'plan_clause_role' and feedback['details']['expected'] == 'condition'
    assert model.calls[0]['usage'] == model.calls[1]['usage'] == payload['usage']
    assert second['correction_of_sha256'] == first['raw_output_sha256']
    assert first['raw_output'] != second['raw_output']
    assert out['validation_details']['corrective_attempt_used'] is True
    gap = next(x for x in out['actions'] if x['basis_kind'] == 'usage_gap')
    assert gap['source_material_ids'] == []
    files = sorted((flow[-1]/'typed-audit').glob('*.json'))
    assert len(files) == 4
    saved = [json.loads(p.read_text()) for p in files if p.name.endswith('-result.json')]
    assert {r['raw_output_sha256'] for r in saved} == {first['raw_output_sha256'], second['raw_output_sha256']}


@pytest.mark.parametrize('mode,calls,error', [('timeout', 1, 'p2_ai_model_unavailable'),
    ('budget', 0, 'p2_ai_budget_exhausted'), ('malformed', 1, 'p2_ai_output_rejected'), ('shape', 1, 'p2_ai_output_rejected')])
def test_no_automatic_retry_for_nonrecoverable_or_uncertain_outcomes(flow, mode, calls, error):
    model = PlanModel((mode, 'good'))
    out = run_plan(model, payload_for(flow), audit_root=flow[-1]/'typed-audit')
    assert out['status'] == 'failed' and out['error_code'] == error
    assert len(model.calls) == 1 and out['model_calls'] == calls
    assert out['clauses'] == out['actions'] == out['changes'] == []
    assert len(out['attempts']) == 1


def test_two_semantic_rejections_stop_without_third_request(flow):
    model = PlanModel(('semantic', 'semantic', 'good'))
    out = run_plan(model, payload_for(flow), audit_root=flow[-1]/'typed-audit')
    assert out['status'] == 'failed' and out['model_calls'] == 2
    assert len(model.calls) == len(out['attempts']) == 2
    assert out['actions'] == [] and out['plan'] is None


def legacy_ready_with_real_issue(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    model.model = {**model.model, 'prompt_version': 'p2-bound-material-actions/7'}
    model.mutate = lambda value: value['actions'][0].update(text='检查已交付文件中的本组件版权与许可声明保留位置。')
    doc = ready(flow)
    assert doc['analysis']['state'] == 'ready'
    assert doc['analysis']['preview']['status'] == 'succeeded'
    with svc.store.connection() as db:
        job_raw = db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?', ('analysis', result['result_id'])).fetchone()
        preview_raw = db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?', (doc['analysis']['preview_id'],)).fetchone()
    return doc, job_raw, preview_raw


def test_v2_actual_asgi_reviews_ready_legacy_without_faking_failure_and_preserves_p2(flow, monkeypatch):
    svc, run, a, result, fetcher, old_model, app, root = flow
    doc, old_job, old_preview = legacy_ready_with_real_issue(flow)
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '1')
    svc.analysis_repair_scan_id = run.id
    svc.ai.provider = PlanModel()
    app.state.p2_service.official_sources = svc
    row = result['resources'][0]
    payload = svc._preview_input(result, row, doc['candidate'])
    version, sha = svc._analysis_prompt_identity(payload, ANALYSIS_PROTOCOL)
    body = {'binding': result['binding'], 'result_id': result['result_id'], 'result_sha256': result['result_sha256'],
        'candidate_id': doc['candidate']['candidate_id'], 'previous_preview_id': doc['analysis']['preview_id'],
        'prompt_version': version, 'prompt_sha256': sha, 'idempotency_key': 'synthetic-v2-plan-repair', 'analysis_protocol': ANALYSIS_PROTOCOL}
    before = svc.p2.store.path.read_bytes()
    url = f'/api/v1/scans/{run.id}/assessments/{a.id}/p2/official-sources'
    with TestClient(app) as client:
        # New validation is a read-only projection; it must not rewrite the old ready bytes.
        projected = client.get(url, params={'result_id': result['result_id'], 'assessment_version': 1}).json()
        assert projected['analysis']['state'] == 'failed'
        with svc.store.connection() as db:
            assert db.execute('SELECT payload,sha256 FROM official_jobs WHERE kind=? AND key=?', ('analysis', result['result_id'])).fetchone() == old_job
        response = client.post(url+'/analyze', json=body)
        assert response.status_code == 202, response.text
        assert svc.wait_idle()
        saved = client.get(url, params={'result_id': result['result_id'], 'assessment_version': 1}).json()
        preview = saved['analysis']['preview']
        assert saved['analysis']['state'] == 'ready', saved
        assert preview['analysis_protocol'] == ANALYSIS_PROTOCOL and preview['status'] == 'succeeded'
        assert preview['validation_details']['status'] == 'validated'
        assert preview['actions'][1]['basis_kind'] == 'usage_gap' and preview['actions'][1]['source_candidate_ids'] == []
        assert saved['analysis']['analysis_attempt']['legacy_review_issues']
        assert client.post(url+'/analyze', json=body).status_code == 202
        assert svc.wait_idle() and len(svc.ai.provider.calls) == 1 and fetcher.calls == 1
        for _ in range(3):
            assert client.get(url, params={'result_id': result['result_id'], 'assessment_version': 1}).status_code == 200
        assert len(svc.ai.provider.calls) == 1
    with svc.store.connection() as db:
        assert db.execute('SELECT payload,sha256 FROM official_job_history WHERE kind=? AND key=? AND sha256=?',
            ('analysis', result['result_id'], old_job[1])).fetchone() == old_job
        assert db.execute('SELECT payload,sha256 FROM official_previews WHERE id=?', (doc['analysis']['preview_id'],)).fetchone() == old_preview
    assert svc.p2.store.path.read_bytes() == before
    assert canonical(svc.p2.read(run.id, a.id, result['result_id'], 1)) == canonical(result)


def test_same_v2_runner_saves_material_analysis_and_validates_fixed_get(flow, monkeypatch):
    svc, run, a, result, fetcher, old_model, app, root = flow
    doc = ready(flow)
    before = canonical(result)
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '1')
    model = PlanModel(); svc.ai.provider = model
    saved = svc.adopt(run.id, a.id, adopt_body(result, doc['candidate']['candidate_id']))
    assert saved['material']['source_level'] == 'user_supplied_unverified'
    assert saved['material']['verification_state'] == 'pending'
    assert svc.wait_idle()
    current = saved['result']
    status = svc.status(run.id, a.id, 1, current['result_id'])
    assert status['analysis']['state'] == 'ready', status
    analysis = svc.ai.read(run.id, a.id, status['analysis']['analysis_id'], current['result_id'], 1)
    assert analysis['analysis_protocol'] == ANALYSIS_PROTOCOL and analysis['status'] == 'succeeded'
    assert analysis['model_calls'] == 1 and len(model.calls) == 1
    assert analysis['actions'][0]['source_material_ids'] == [saved['material']['material_id']]
    assert canonical(svc.p2.read(run.id, a.id, result['result_id'], 1)) == before


def test_durable_16_budget_preserves_13_and_counts_three_new_failures_or_successes(flow, monkeypatch):
    from app.ai.p2_analysis import BoundQwen
    from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
    root = flow[-1]
    path = root/'new-task-model-budget.json'
    history = [{'number': i+1, 'state': 'SYNTHETIC_TEST_ONLY_PRIOR_INTENT'} for i in range(13)]
    path.write_text(json.dumps({'version': 1, 'max_generations': 16, 'intents': history})); path.chmod(0o600)
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '1')
    provider = BoundQwen(path, max_generations=16, intent_ceiling=16)
    enriched = prepare_plan_payload(payload_for(flow))
    calls = []
    def transport(endpoint, **kwargs):
        calls.append(endpoint)
        if endpoint == '/api/version': return {'version': OLLAMA_VERSION}
        if endpoint == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        if calls.count('/api/generate') == 2: raise TimeoutError('SYNTHETIC_TEST_ONLY_COUNTS_FAILURE')
        body = kwargs['body']
        assert body['system'] and 'format' in body and body['format']['properties']['actions']
        assert provider.model['prompt_version'] == PROMPT_VERSION
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': json.dumps(selection(enriched))}
    provider.transport._request_json = transport
    provider.generate(enriched)
    with pytest.raises(TimeoutError): provider.generate(enriched)
    provider.generate(enriched)
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'): provider.generate(enriched)
    saved = json.loads(path.read_text())
    assert len(saved['intents']) == 16 and saved['intents'][:13] == history
    assert calls.count('/api/generate') == 3


def test_locked_ceiling_never_uses_old_unused_slot(flow, monkeypatch):
    from app.ai.p2_analysis import BoundQwen
    root = flow[-1]; path = root/'locked-budget.json'
    history = [{'number': i+1, 'state': 'SYNTHETIC_TEST_ONLY_PRIOR_INTENT'} for i in range(13)]
    path.write_text(json.dumps({'version': 1, 'max_generations': 16, 'intents': history})); path.chmod(0o600)
    before = path.read_bytes()
    monkeypatch.setenv('OPENGUARD_P2_ACTION_PLAN', '1')
    provider = BoundQwen(path, max_generations=16, intent_ceiling=13)
    provider.transport._request_json = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('LOCKED_NO_TRANSPORT'))
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'):
        provider.generate(prepare_plan_payload(payload_for(flow)))
    assert provider.model_calls == 0 and path.read_bytes() == before
