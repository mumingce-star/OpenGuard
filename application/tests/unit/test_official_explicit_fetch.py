"""TASK-only explicit fixed-source restart: actual ASGI, synthetic transport only."""
from copy import deepcopy
import hashlib
import json
import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.p2.contract import canonical, P2Error
from test_official_sources import flow, LICENSE


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('OFFLINE_TEST_EXTERNAL_SOCKET_FORBIDDEN')
    monkeypatch.setattr(socket, 'create_connection', blocked)
    monkeypatch.setattr(socket.socket, 'connect', blocked)


def eligible(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    svc.explicit_fetch_scan_id = run.id
    svc.on_result(run.id, a.id, result)
    with svc.store.connection(write=True) as db:
        old = {'scan_id': run.id, 'job_id': 'historical-zero-budget-job', 'state': 'failed',
               'subject': result['resources'][0]['subject'], 'commit': run.project.revision,
               'http_intents': 0, 'http_dispatched': 0, 'http_responses': 0,
               'retrieval_status': 'failed', 'error_code': 'official_source_http_budget_exhausted',
               'created_at': '2026-10-24T00:00:00Z', 'updated_at': '2026-10-24T00:00:00Z'}
        svc.store.put_job(db, 'fetch', run.id, old)
        analysis = svc.store.job(db, 'analysis', result['result_id'])
        analysis.update(state='failed', error_code='official_source_retrieval_unavailable')
        svc.store.put_job(db, 'analysis', result['result_id'], analysis)
    app.state.p2_service.official_sources = svc
    return old, analysis


def body(result):
    return {'binding': result['binding'], 'result_id': result['result_id'],
            'result_sha256': result['result_sha256'], 'idempotency_key': 'explicit-test-only-fetch-001'}


def base(run, a):
    return f'/api/v1/scans/{run.id}/assessments/{a.id}/p2/official-sources'


def test_explicit_actual_asgi_202_once_audit_and_readonly_get_no_replay(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    old, old_analysis = eligible(flow)
    before_result = canonical(result)
    with TestClient(app) as client:
        url = base(run, a)
        status = client.get(url, params={'assessment_version': 1, 'result_id': result['result_id']})
        assert status.status_code == 200
        assert status.json().get('explicit_fetch', {}).get('allowed') is True
        response = client.post(url+'/fetch', json=body(result))
        assert response.status_code == 202, response.text
        assert svc.wait_idle()
        saved = client.get(url, params={'assessment_version': 1, 'result_id': result['result_id']}).json()
        assert saved['fetch']['state'] == 'ready' and saved['analysis']['state'] == 'ready'
        assert saved['explicit_fetch']['allowed'] is False
        assert saved['explicit_fetch']['reason'] == 'already_requested'
        assert saved['explicit_fetch']['request']['idempotency_key'] == body(result)['idempotency_key']
        assert saved['fetch']['job_id'] != old['job_id']
        assert fetcher.calls == model.calls == 1
        again = client.post(url+'/fetch', json=body(result))
        assert again.status_code == 202 and again.json()['explicit_fetch']['request'] == saved['explicit_fetch']['request']
        assert svc.wait_idle() and fetcher.calls == model.calls == 1
        changed = {**body(result), 'idempotency_key': 'explicit-test-only-fetch-002'}
        assert client.post(url+'/fetch', json=changed).status_code == 409
        for _ in range(3):
            assert client.get(url, params={'assessment_version': 1, 'result_id': result['result_id']}).status_code == 200
        svc.on_terminal(run); svc.on_result(run.id, a.id, result)
        assert svc.wait_idle() and fetcher.calls == model.calls == 1
    with svc.store.connection() as db:
        rows = db.execute('SELECT kind,payload,sha256 FROM official_job_history ORDER BY kind').fetchall()
    originals = {'fetch': old, 'analysis': old_analysis}
    assert len(rows) == 2
    for kind, raw, sha in rows:
        assert bytes(raw) == canonical(originals[kind]) and sha == hashlib.sha256(raw).hexdigest()
    assert canonical(svc.p2.read(run.id, a.id, result['result_id'], 1)) == before_result
    assert not svc.p2.read(run.id, a.id, result['result_id'], 1)['material_ids']


@pytest.mark.parametrize('wrong', ['binding', 'hash', 'scope', 'read_only', 'jobs_disabled', 'sent', 'intent', 'uncertain', 'analysis_generated', 'not_budget_failure'])
def test_explicit_invalid_or_uncertain_request_is_refused_without_fetch_or_model(flow, wrong):
    svc, run, a, result, fetcher, model, app, root = flow
    eligible(flow); request = deepcopy(body(result))
    if wrong == 'binding': request['binding']['usage_hash'] = 'f'*64
    elif wrong == 'hash': request['result_sha256'] = 'f'*64
    elif wrong == 'scope': svc.explicit_fetch_scan_id = 'scn_another'
    elif wrong == 'read_only': svc.p2.readonly = True
    elif wrong == 'jobs_disabled': svc.jobs_enabled = False
    else:
        with svc.store.connection(write=True) as db:
            fetch = svc.store.job(db, 'fetch', run.id)
            if wrong == 'sent': fetch.update(http_intents=1, http_dispatched=1)
            elif wrong == 'intent': fetch['http_intents'] = 1
            elif wrong == 'uncertain': fetch['state'] = 'outcome_unknown'
            elif wrong == 'not_budget_failure': fetch['error_code'] = 'official_source_busy'
            else:
                analysis = svc.store.job(db, 'analysis', result['result_id']); analysis['preview_id'] = 'p2preview_not_retryable'
                svc.store.put_job(db, 'analysis', result['result_id'], analysis)
            svc.store.put_job(db, 'fetch', run.id, fetch)
    with TestClient(app) as client:
        response = client.post(base(run, a)+'/fetch', json=request)
        assert response.status_code in {403, 409}, response.text
    assert fetcher.calls == model.calls == 0
    with svc.store.connection() as db:
        assert db.execute('SELECT count(*) FROM official_explicit_fetch_requests').fetchone()[0] == 0


def test_explicit_restart_does_not_repeat_reserved_request(flow):
    svc, run, a, result, fetcher, model, app, root = flow
    eligible(flow)
    # Simulate a committed request whose process could not schedule: no retry at startup.
    original_submit = svc._submit
    svc._submit = lambda *args: (_ for _ in ()).throw(P2Error('official_source_closed', 503))
    from app.p2.official_sources import ExplicitFetchRequest, OfficialSourceService
    out = svc.request_fetch(run.id, a.id, ExplicitFetchRequest.model_validate(body(result)))
    assert out['explicit_fetch']['request'] and fetcher.calls == model.calls == 0
    svc._submit = original_submit
    svc.close()
    restarted = OfficialSourceService(svc.p2, root/'official', fetcher, svc.ai, explicit_fetch_scan_id=run.id)
    try:
        restarted.on_terminal(run); restarted.on_result(run.id, a.id, result)
        again = restarted.request_fetch(run.id, a.id, ExplicitFetchRequest.model_validate(body(result)))
        assert again['explicit_fetch']['allowed'] is False
        assert restarted.wait_idle() and fetcher.calls == model.calls == 0
    finally:
        restarted.close()


def test_http_35_preserves_29_history_and_allows_only_one_new_six(tmp_path):
    from app.ingestion import official_http_server as api
    from test_official_http_server import Driver
    from test_official_http_budget_24 import seed
    driver = Driver(); fetcher = api.FixedOfficialFetcher(tmp_path, max_task_http=35, _wire_factory=driver.factory)
    history = seed(fetcher, 29, 35)
    out = fetcher.fetch('explicit-authorized-new-job')
    assert out['http_intents'] == out['http_dispatched'] == out['http_responses'] == 6
    assert out['task_http_intents'] == 35
    saved = json.loads(fetcher.budget_path.read_text())
    assert saved['requests'][:29] == history['requests']
    refused = fetcher.fetch('not-authorized-second-job')
    assert refused['error_code'] == 'official_source_http_budget_exhausted' and refused['http_intents'] == 0
    assert len(driver.requests) == 6


def test_runtime_accepts_exact_35_http_12_model_and_explicit_scan(tmp_path, monkeypatch):
    from app.api.official_runtime import configure_official_sources
    import app.p2.official_sources as module
    seen = []
    values = {'OPENGUARD_OFFICIAL_SOURCE_AUTO':'1', 'OPENGUARD_P2_AI_MAX_GENERATIONS':'12',
              'OPENGUARD_OFFICIAL_HTTP_MAX_TASK':'35', 'OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH':str(tmp_path/'ledger.json'),
              'OPENGUARD_OFFICIAL_EXPLICIT_SCAN_ID':'scn_exact_current_test'}
    for key, value in values.items(): monkeypatch.setenv(key, value)
    monkeypatch.setattr(module, 'OfficialSourceService', lambda *args, **kwargs: seen.append(kwargs) or SimpleNamespace())
    configure_official_sources(SimpleNamespace(readonly=False,data_scope='TEST_ONLY',ai_analysis=object()),
                               SimpleNamespace(assessment_saved_observer=None),None,tmp_path)
    assert seen[0]['explicit_fetch_scan_id'] == values['OPENGUARD_OFFICIAL_EXPLICIT_SCAN_ID']
    assert not (tmp_path/'ledger.json').exists()


def test_actual_account_gateway_auth_csrf_and_tenant_isolation(tmp_path, monkeypatch):
    from test_local_accounts import gateway, register, request, ORIGIN
    from test_p2_contract import seed
    from test_v4_assessment_core import controlled
    from test_official_sources import Fetcher
    from test_p2_ai_analysis import Model
    from app.domain.models import ScanRun
    from app.domain.usage import UsageDeclaration
    from app.p2.ai_analysis import AnalysisStore, P2AnalysisService
    from app.p2.contract import CreateRequest
    from app.p2.official_sources import OfficialSourceService, COMMIT
    monkeypatch.setenv('OPENGUARD_OFFICIAL_SOURCE_AUTO', '0')
    monkeypatch.setenv('OPENGUARD_ENABLE_P2_AI', '0')
    app = gateway(tmp_path/'accounts', monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        assert request(client,'POST','/api/v1/scans/scn_none/assessments/asm_none/p2/official-sources/fetch',body={}).status_code == 401
        user = register(client,'synthetic_explicit_a'); csrf = user['csrf_token']
        assert request(client,'GET','/api/v1/scans').status_code == 200
        tenant = app.observed_apps[0]
        payload = controlled(scope=False,verified=False).model_dump(mode='json')
        payload['project'].update(source_type='git',source='https://github.com/http-party/http-server',revision=COMMIT)
        payload['components'][0].update(name='http-server',version='14.1.2')
        run = ScanRun.model_validate(payload)
        usage = UsageDeclaration(commercial=False,modified=True,distributed=False,network_service=True,
                                 training=False,redistributed_assets=False,source_disclosure=False)
        a = seed(tenant,run,usage); p2 = tenant.state.p2_service
        binding = p2.context(run.id,a.id)[2]
        result = p2.write(run.id,a.id,CreateRequest(binding=binding,expected_revision=0,parent_result_id=None,
                          idempotency_key='synthetic-account-explicit-result'),'create')['result']
        working = tmp_path/'synthetic-explicit'; working.mkdir(mode=0o700)
        ai_store=AnalysisStore(working/'p2-ai.db');ai_store.initialize()
        model=Model();model.calls=0
        fetcher=Fetcher(working/'fetch')
        svc=OfficialSourceService(p2,working/'official',fetcher,P2AnalysisService(p2,ai_store,model),explicit_fetch_scan_id=run.id)
        try:
            eligible((svc,run,a,result,fetcher,model,tenant,working))
            url=base(run,a)+'/fetch'
            assert request(client,'POST',url,body=body(result)).status_code == 403
            assert request(client,'POST',url,csrf='0'*64,body=body(result)).status_code == 403
            assert request(client,'POST',url,csrf=csrf,body=body(result),headers={'Origin':'https://evil.example'}).status_code == 403
            assert fetcher.calls == model.calls == 0
            accepted=request(client,'POST',url,csrf=csrf,body=body(result))
            assert accepted.status_code == 202,accepted.text
            assert svc.wait_idle() and fetcher.calls == model.calls == 1
            request(client,'POST','/api/v1/auth/logout',csrf=csrf,body={})
            other=register(client,'synthetic_explicit_b')
            # A different authenticated account cannot access A's source receipt
            # or spend its single explicit reservation through an isolated tenant.
            out=request(client,'POST',url,csrf=other['csrf_token'],body=body(result))
            assert out.status_code in {404,503}
            assert fetcher.calls == model.calls == 1
        finally:
            svc.close()


def test_local_model_12_preserves_11_and_failed_attempt_consumes_last(tmp_path):
    from app.ai.p2_analysis import BoundQwen, BudgetError
    from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
    tmp_path.chmod(0o700)
    path=tmp_path/'model.json'
    prior=[{'number':i+1,'state':'SYNTHETIC_HISTORICAL_INTENT'} for i in range(11)]
    path.write_text(json.dumps({'version':1,'max_generations':12,'intents':prior}));path.chmod(0o600)
    provider=BoundQwen(path,max_generations=12)
    calls=[]
    def transport(endpoint,**kwargs):
        calls.append(endpoint)
        if endpoint=='/api/version': return {'version':OLLAMA_VERSION}
        if endpoint=='/api/tags': return {'models':[{'name':MODEL_NAME,'digest':MANIFEST_DIGEST}]}
        raise TimeoutError('SYNTHETIC_TEST_ONLY_MODEL_FAILURE')
    provider.transport._request_json=transport
    payload={'materials':[{'material_id':'SYNTHETIC_TEST_ONLY','quote_candidates':['Synthetic original text.']}],'changes':[]}
    with pytest.raises(TimeoutError): provider.generate(payload)
    with pytest.raises(BudgetError,match='p2_ai_budget_exhausted'): provider.generate(payload)
    saved=json.loads(path.read_text())
    assert saved['intents'][:11]==prior and len(saved['intents'])==12
    assert calls.count('/api/generate')==1
