"""Actual P2/Assessment SQLite; synthetic fetch and model, zero external HTTP."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import threading

import pytest
from app.api.main import create_default_app
from app.assessment.engine import build_assessment
from app.domain.models import ScanRun
from app.domain.usage import UsageDeclaration
from app.p2.ai_analysis import AnalysisStore, P2AnalysisService
from app.p2.contract import CreateRequest, P2Error, canonical, digest
from app.p2.official_sources import (OfficialSourceService, AdoptRequest, COMMIT, LICENSE_SHA, GIT_URL, NPM_URL)
from test_p2_contract import seed
from test_v4_assessment_core import controlled
from test_p2_ai_analysis import Model

LICENSE = Path(__file__).parents[1] / 'fixtures/official-http-server/LICENSE'


class Fetcher:
    calls = 0
    mutate = None
    fail = None

    def __init__(self, root):
        self.root = root
        root.mkdir(mode=0o700)

    def fetch(self, job_id):
        self.calls += 1
        if self.fail:
            return {'job_id': job_id, 'status': self.fail, 'error_code': 'synthetic_transport_failure',
                    'http_intents': 1, 'http_dispatched': 1, 'http_responses': 0, 'sources': []}
        directory = self.root / job_id; directory.mkdir(mode=0o700)
        sources = []
        for kind, url, raw in [('git_license', GIT_URL, LICENSE.read_bytes()), ('npm_metadata', NPM_URL, b'{"name":"http-server","version":"14.1.2","license":"MIT"}')]:
            path = directory / (kind+'.body'); path.write_bytes(raw)
            sources.append({'kind': kind, 'status': 'observed', 'url': url, 'body_path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                            'byte_count': len(raw), 'content_type': 'text/plain' if kind == 'git_license' else 'application/json',
                            'source_level': 'official_repository_bytes_observed' if kind == 'git_license' else 'provider_declared_unverified', 'verification_state': 'pending',
                            'name': 'http-server', 'version': '14.1.2', 'commit': COMMIT if kind == 'git_license' else None,
                            'retrieved_at': '2026-10-23T00:00:00Z'})
        reply = {'job_id': job_id, 'status': 'succeeded', 'error_code': None, 'http_intents': 6, 'http_dispatched': 6, 'http_responses': 6, 'sources': sources}
        if self.mutate: self.mutate(reply)
        return reply


@pytest.fixture
def flow(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    for k, v in {'OPENGUARD_DATA_DIR': str(tmp_path), 'OPENGUARD_ENABLE_ASSESSMENTS': '1', 'OPENGUARD_ENABLE_P2': '1',
                 'OPENGUARD_P2_READONLY': '0', 'OPENGUARD_P2_DATA_SCOPE': 'TEST_ONLY', 'OPENGUARD_ENABLE_P2_AI': '0',
                 'OPENGUARD_OFFICIAL_SOURCE_AUTO': '0', 'OPENGUARD_ENABLE_AI': '0', 'OPENGUARD_ENABLE_PUBLIC_GIT': '0',
                 'OPENGUARD_ENABLE_DURABLE_ZIP': '0', 'OPENGUARD_ENABLE_PROFILE_METADATA': '0', 'OPENGUARD_ENABLE_EXTERNAL_SCANNERS': '0'}.items():
        monkeypatch.setenv(k, v)
    app = create_default_app()
    payload = controlled(scope=False, verified=False).model_dump(mode='json')
    payload['project'].update(source_type='git', source='https://github.com/http-party/http-server', revision=COMMIT)
    payload['components'][0].update(name='http-server', version='14.1.2')
    run = ScanRun.model_validate(payload)
    usage = UsageDeclaration(commercial=False, modified=True, distributed=False, network_service=True,
                             training=False, redistributed_assets=False, source_disclosure=False)
    assessment = seed(app, run, usage)
    p2 = app.state.p2_service
    binding = p2.context(run.id, assessment.id)[2]
    result = p2.write(run.id, assessment.id, CreateRequest(binding=binding, expected_revision=0, parent_result_id=None,
                       idempotency_key='synthetic-test-initial'), 'create')['result']
    ai_store = AnalysisStore(tmp_path/'p2-ai.db'); ai_store.initialize()
    model = Model(); model.calls = 0
    ai = P2AnalysisService(p2, ai_store, model)
    fetcher = Fetcher(tmp_path/'fetch')
    service = OfficialSourceService(p2, tmp_path/'official', fetcher, ai)
    yield service, run, assessment, result, fetcher, model, app, tmp_path
    service.close()
    app.state.scan_api_service._registry.close()


def ready(flow):
    service, run, a, result, fetcher, model, _, _ = flow
    service.on_result(run.id, a.id, result)
    service.on_terminal(run)
    assert service.wait_idle()
    return service.status(run.id, a.id, 1, result['result_id'])


def adopt_body(result, candidate_id, key='adopt-test-same-key'):
    return AdoptRequest(binding=result['binding'], candidate_id=candidate_id, result_id=result['result_id'],
                        result_sha256=result['result_sha256'], expected_revision=result['revision'],
                        parent_result_id=result['result_id'], idempotency_key=key)


def test_automatic_preview_namespace_no_material_write_and_dedup(flow):
    svc, run, a, result, fetcher, model, _, root = flow
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')}
    out = ready(flow)
    assert out['fetch']['state'] == 'ready' and fetcher.calls == 1
    assert out['analysis']['state'] == 'ready' and out['analysis']['mode'] == 'unadopted_preview'
    p = out['analysis']['preview']; assert p['status'] == 'succeeded' and model.calls == 1
    assert p['clauses'][0]['source_candidate_id'] == out['candidate']['candidate_id']
    assert 'material_id' not in p['clauses'][0] and 'material_ids' not in p
    assert p['actions'][0]['source_candidate_ids'] == [out['candidate']['candidate_id']]
    assert out['candidate']['license_text'].encode() == LICENSE.read_bytes()
    assert out['adopted_material_ids'] == [] and svc.p2.read(run.id, a.id, result['result_id'], 1) == result
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')}
    for _ in range(5):
        svc.on_terminal(run); svc.on_result(run.id, a.id, result)
        assert svc.status(run.id, a.id, 1, result['result_id']) == out
    assert svc.wait_idle() and model.calls == 1 and fetcher.calls == 1


def test_adopt_real_service_cas_pending_saved_model_and_old_immutable(flow):
    svc, run, a, old, fetcher, model, _, _ = flow
    out = ready(flow); cid = out['candidate']['candidate_id']
    old_summary = svc.p2.summary(run.id, a.id, old['result_id'], 1)
    request = adopt_body(old, cid)
    receipt = svc.adopt(run.id, a.id, request)
    new = receipt['result']; material = receipt['material']
    assert new['revision'] == 2 and new['previous_result_id'] == old['result_id']
    assert new['binding'] == old['binding'] and material['source_level'] == 'user_supplied_unverified'
    assert material['verification_state'] == 'pending' and new['resources'][0]['state'] == 'pending'
    assert svc.wait_idle() and model.calls == 2 and fetcher.calls == 1
    new_status = svc.status(run.id, a.id, 1, new['result_id'])
    assert new_status['analysis']['mode'] == 'saved_material' and new_status['analysis']['state'] == 'ready'
    assert new_status['adopted_material_ids'] == [material['material_id']]
    analysis = svc.ai.read(run.id, a.id, new_status['analysis']['analysis_id'], new['result_id'], 1)
    assert analysis['changes'] and analysis['source_refs'][0]['material_id'] == material['material_id']
    assert svc.adopt(run.id, a.id, request) == receipt
    assert svc.wait_idle() and model.calls == 2
    with pytest.raises(P2Error, match='p2_revision_conflict'):
        svc.adopt(run.id, a.id, adopt_body(old, cid, 'different-cas-key'))
    assert svc.p2.read(run.id, a.id, old['result_id'], 1) == old
    assert svc.p2.summary(run.id, a.id, old['result_id'], 1) == old_summary
    summary = svc.p2.summary(run.id, a.id, new['result_id'], 1)
    assert summary['result_sha256'] == new['result_sha256'] and summary['binding'] == new['binding']


@pytest.mark.parametrize('field', ['binding', 'result_sha256', 'candidate', 'revision', 'parent', 'result'])
def test_adopt_wrong_binding_hash_candidate_cas_no_write(flow, field):
    svc, run, a, result, _, model, _, root = flow
    out = ready(flow); value = adopt_body(result, out['candidate']['candidate_id']).model_dump()
    if field == 'binding': value['binding']['usage_hash'] = 'f'*64
    elif field == 'result_sha256': value['result_sha256'] = 'f'*64
    elif field == 'candidate': value['candidate_id'] = 'p2src_wrong'
    elif field == 'revision': value['expected_revision'] += 1
    elif field == 'parent': value['parent_result_id'] = 'p2res_wrong'
    else: value['result_id'] = 'p2res_wrong'
    before = (root/'p2.db').read_bytes()
    with pytest.raises(P2Error): svc.adopt(run.id, a.id, AdoptRequest.model_validate(value))
    assert (root/'p2.db').read_bytes() == before and model.calls == 1


@pytest.mark.parametrize('failure', ['failed', 'outcome_unknown'])
def test_failed_retrieval_no_model_no_retry(flow, failure):
    svc, run, a, result, fetcher, model, _, _ = flow
    fetcher.fail = failure
    out = ready(flow)
    assert out['fetch']['state'] == failure and out['candidate'] is None
    assert out['analysis']['state'] == 'failed' and model.calls == 0
    svc.on_terminal(run); svc.on_result(run.id, a.id, result); assert svc.wait_idle()
    assert fetcher.calls == 1 and model.calls == 0


@pytest.mark.parametrize('failure', ['wrong_hash', 'wrong_name', 'wrong_version', 'wrong_commit', 'source_escape', 'source_symlink', 'bad_count', 'accepted_claim', 'unordered_count'])
def test_failed_candidate_validation_no_model(flow, failure):
    svc, run, a, result, fetcher, model, _, root = flow
    def mutate(receipt):
        source = receipt['sources'][0]
        if failure == 'wrong_hash': source['sha256'] = 'a'*64
        elif failure == 'wrong_name': source['name'] = 'is-number'
        elif failure == 'wrong_version': source['version'] = '7.0.0'
        elif failure == 'wrong_commit': source['commit'] = 'a'*40
        elif failure == 'source_escape': source['body_path'] = str(LICENSE.absolute())
        elif failure == 'accepted_claim': source['source_level'] = 'accepted'
        elif failure == 'unordered_count': receipt['http_responses'] = 6; receipt['http_dispatched'] = 5
        elif failure == 'source_symlink':
            path = Path(source['body_path']); alias = path.with_name('alias'); alias.symlink_to(path); source['body_path'] = str(alias)
        else: receipt['http_intents'] = True
    fetcher.mutate = mutate
    out = ready(flow)
    assert out['fetch']['state'] == 'failed' and out['candidate'] is None and model.calls == 0


def test_get_readonly_and_fixed_revision_do_not_schedule(flow):
    svc, run, a, result, fetcher, model, _, root = flow
    out = svc.status(run.id, a.id, 1, result['result_id'])
    assert out['fetch']['state'] == 'not_scheduled' and fetcher.calls == model.calls == 0
    svc.p2.readonly = True
    svc.on_terminal(run); svc.on_result(run.id, a.id, result)
    with pytest.raises(P2Error, match='p2_read_only'): svc.adopt(run.id, a.id, adopt_body(result, 'p2src_unused'))
    assert svc.status(run.id, a.id, 1, result['result_id']) == out
    with pytest.raises(P2Error): svc.status(run.id, a.id, 2, result['result_id'])
    assert fetcher.calls == model.calls == 0


def test_unknown_running_reservation_is_not_replayed_on_restart(flow):
    svc, run, a, result, fetcher, model, _, root = flow
    svc.on_result(run.id, a.id, result)
    svc.close()
    restarted = OfficialSourceService(svc.p2, root/'official', fetcher, svc.ai)
    try:
        restarted.on_result(run.id, a.id, result)
        out = restarted.status(run.id, a.id, 1, result['result_id'])
        assert out['analysis']['state'] == 'outcome_unknown' and model.calls == 0
    finally: restarted.close()


def test_model_rejection_keeps_candidate_and_does_not_repeat(flow):
    svc, run, a, result, fetcher, model, _, _ = flow
    model.mutate = lambda obj: obj['actions'][0].update(text='确认该项目已经合规并允许商业使用。')
    out = ready(flow)
    assert out['fetch']['state'] == 'ready' and out['analysis']['state'] == 'failed'
    assert out['analysis']['preview']['actions'] == []
    svc.on_result(run.id, a.id, result); assert svc.wait_idle() and model.calls == 1


def test_usage_new_version_preview_explicit_previous_and_no_material_carry(flow):
    svc, run, a, old, fetcher, model, app, _ = flow
    ready(flow)
    usage = a.usage.model_copy(update={'commercial': True, 'source_disclosure': True})
    newer = build_assessment(run, usage, version=2)
    app.state.assessment_service.store.create(newer, idempotency_key='synthetic-usage-v2', run=run)
    binding = svc.p2.context(run.id, newer.id)[2]
    result = svc.p2.write(run.id, newer.id, CreateRequest(binding=binding, expected_revision=0, parent_result_id=None, idempotency_key='new-usage-result'), 'create')['result']
    svc.on_terminal(run); svc.on_result(run.id, newer.id, result); assert svc.wait_idle()
    out = svc.status(run.id, newer.id, 2, result['result_id'])
    assert out['analysis']['state'] == 'ready' and out['analysis']['mode'] == 'unadopted_preview'
    preview = out['analysis']['preview']
    assert preview['previous_result']['result_id'] == old['result_id']
    assert {r['field'] for r in preview['changes']} == {'usage.commercial', 'usage.source_disclosure'}
    assert preview['binding'] == result['binding'] and out['adopted_material_ids'] == []
    assert fetcher.calls == 1 and model.calls == 2
    assert svc.status(run.id, a.id, 1, old['result_id'])['analysis']['preview']['changes'] == []


def test_task_budget_ten_is_explicit_and_failed_generation_consumes(tmp_path):
    from app.ai.p2_analysis import BoundQwen, BudgetError
    from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION
    tmp_path.chmod(0o700)
    qwen = BoundQwen(tmp_path/'SYNTHETIC_TEN_BUDGET.json', max_generations=10)
    calls = []
    def transport(path, **kwargs):
        calls.append(path)
        if path == '/api/version': return {'version': OLLAMA_VERSION}
        if path == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        raise TimeoutError('SYNTHETIC_FAILURE_NO_EXTERNAL_HTTP')
    qwen.transport._request_json = transport
    payload = {'materials': [{'material_id': 'SYNTHETIC_TEST_ONLY', 'quote_candidates': ['This is a synthetic test-only quote.']}], 'changes': []}
    for _ in range(10):
        with pytest.raises(TimeoutError): qwen.generate(payload)
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'): qwen.generate(payload)
    assert calls.count('/api/generate') == 10
    ledger = json.loads(qwen.path.read_text())
    assert ledger['max_generations'] == 10 and len(ledger['intents']) == 10
    with pytest.raises(BudgetError, match='p2_ai_budget_invalid'):
        BoundQwen(qwen.path, max_generations=20).generate(payload)
    for invalid in (True, 0, 21, 1.5):
        with pytest.raises(ValueError): BoundQwen(tmp_path/'bad', max_generations=invalid)


def test_public_preview_self_hash_corruption_is_rejected(flow):
    svc, run, a, result, _, _, _, _ = flow
    out = ready(flow)
    value = out['analysis']['preview']; value['actions'][0]['text'] = '核对被修改的记录。'
    raw = canonical(value)
    with svc.store.connection(write=True) as db:
        db.execute('UPDATE official_previews SET payload=?,sha256=? WHERE id=?', (raw, hashlib.sha256(raw).hexdigest(), value['preview_id']))
    with pytest.raises(P2Error, match='official_source_preview_integrity_error'):
        svc.status(run.id, a.id, 1, result['result_id'])


def test_foreign_scan_or_resource_never_schedules(flow):
    svc, run, a, result, fetcher, model, _, _ = flow
    for field, value in [('revision', 'e'*40), ('source', 'https://github.com/other/http-server')]:
        other = run.model_copy(deep=True); setattr(other.project, field, value)
        svc.on_terminal(other)
    other = run.model_copy(deep=True); other.components[0].name = 'is-number'; svc.on_terminal(other)
    assert svc.status(run.id, a.id, 1, result['result_id'])['fetch']['state'] == 'not_scheduled'
    assert svc.wait_idle() and fetcher.calls == model.calls == 0


def partial_404_receipt(receipt):
    """SYNTHETIC transport ledger: not evidence of any real HTTP response."""
    receipt.update(status='failed', error_code='upstream_404', http_sendall_completed=6)
    receipt['sources'] = receipt['sources'][:1]
    doh='https://cloudflare-dns.com/dns-query'
    plan=[('POST',doh,'raw.githubusercontent.com',1),('POST',doh,'raw.githubusercontent.com',28),
          ('GET',GIT_URL,None,None),('POST',doh,'registry.npmjs.org',1),
          ('POST',doh,'registry.npmjs.org',28),('GET',NPM_URL,None,None)]
    receipt['requests']=[{'job_id':receipt['job_id'],'job_number':i,'number':i,'method':method,'url':url,
                          'dns_host':host,'dns_type':kind,'timed_out':False,'dispatch_attempt_utc':'2026-10-23T00:00:00Z',
                          'first_sendall_completed_utc':'2026-10-23T00:00:00Z','finished_utc':'2026-10-23T00:00:01Z',
                          'state':'RESPONSE_COMPLETE' if i<6 else 'FAILED_NO_RETRY',
                          'http_status':200 if i<6 else 404,'error_code':None if i<6 else 'upstream_404'}
                         for i,(method,url,host,kind) in enumerate(plan,1)]


def test_limited_git_404_preview_adoption_and_new_usage_keep_npm_gap(flow):
    svc, run, a, old, fetcher, model, app, _ = flow
    svc.allow_git_only_404=True; fetcher.mutate=partial_404_receipt
    out=ready(flow)
    assert out['fetch']['state']=='partial' and out['fetch']['retrieval_status']=='failed'
    assert out['fetch']['error_code']=='upstream_404' and out['fetch']['http_dispatched']==6
    candidate=out['candidate']; preview=out['analysis']['preview']
    assert candidate['coverage']=='partial_git_license_only' and candidate['npm_metadata_status']=='missing_404'
    assert len(candidate['sources'])==1 and candidate['sources'][0]['kind']=='git_license'
    assert candidate['source_failures']==[{'kind':'npm_metadata','url':NPM_URL,'http_status':404,'error_code':'upstream_404','request_number':6,'retrieved_at':'2026-10-23T00:00:01Z'}]
    assert out['analysis']['state']=='ready' and model.payload['npm_metadata_status']=='missing_404'
    assert model.payload['source_limitations']==candidate['limitations'] and preview['source_failures']==candidate['source_failures']
    assert '404' in '\n'.join(preview['limitations']) and out['adopted_material_ids']==[]
    receipt=svc.adopt(run.id,a.id,adopt_body(old,candidate['candidate_id']))
    assert receipt['material']['source_level']=='user_supplied_unverified' and receipt['material']['verification_state']=='pending'
    assert svc.wait_idle() and model.calls==2
    assert model.payload['retrieval_source_context']['npm_metadata_status']=='missing_404'
    assert model.payload['retrieval_source_context']['source_failures']==candidate['source_failures']
    after=svc.status(run.id,a.id,1,receipt['result']['result_id'])
    assert after['fetch']['state']=='partial' and after['analysis']['mode']=='saved_material'
    saved_ai=svc.ai.read(run.id,a.id,after['analysis']['analysis_id'],receipt['result']['result_id'],1)
    assert saved_ai['retrieval_source_context']['candidate_id']==candidate['candidate_id']
    assert saved_ai['retrieval_source_context']['npm_metadata_status']=='missing_404' and '404' in '\n'.join(saved_ai['limitations'])
    assert svc.p2.read(run.id,a.id,old['result_id'],1)==old
    usage=a.usage.model_copy(update={'source_disclosure':True})
    next_a=build_assessment(run,usage,version=2)
    app.state.assessment_service.store.create(next_a,idempotency_key='partial-usage-v2',run=run)
    binding=svc.p2.context(run.id,next_a.id)[2]
    result=svc.p2.write(run.id,next_a.id,CreateRequest(binding=binding,expected_revision=0,parent_result_id=None,idempotency_key='partial-new-result'),'create')['result']
    svc.on_result(run.id,next_a.id,result); assert svc.wait_idle()
    again=svc.status(run.id,next_a.id,2,result['result_id'])
    assert again['analysis']['preview']['npm_metadata_status']=='missing_404' and again['adopted_material_ids']==[]
    assert fetcher.calls==1 and model.calls==3


@pytest.mark.parametrize('failure',['not_enabled','short_count','bool_count','not_sent','no_requests','wrong_url','wrong_job','wrong_step','wrong_dns_type','dns_404','timeout','missing_timeout','illegal_timeout','redirect','access','rate','server_error','unknown','wrong_error','git_hash','wrong_version','extra_source'])
def test_partial_404_never_accepts_other_failure(flow,failure):
    svc, run, a, old, fetcher, model, _, _=flow
    svc.allow_git_only_404=failure!='not_enabled'
    def mutate(receipt):
        partial_404_receipt(receipt)
        last=receipt['requests'][-1]
        if failure=='short_count':receipt['http_intents']=5
        elif failure=='bool_count':receipt['http_dispatched']=True
        elif failure=='not_sent':receipt['http_sendall_completed']=5
        elif failure=='no_requests':receipt['requests']=[]
        elif failure=='wrong_url':last['url']='https://registry.npmjs.org/http-server/14.1.1'
        elif failure=='wrong_job':last['job_id']='other_scan_job'
        elif failure=='wrong_step':last['job_number']=True
        elif failure=='wrong_dns_type':receipt['requests'][0]['dns_type']=True
        elif failure=='dns_404':receipt['requests'][4]['http_status']=404
        elif failure=='timeout':last['timed_out']=True
        elif failure=='missing_timeout':del last['timed_out']
        elif failure=='illegal_timeout':last['timed_out']=0
        elif failure=='redirect':last['http_status']=302
        elif failure=='access':last['http_status']=403
        elif failure=='rate':last['http_status']=429
        elif failure=='server_error':last['http_status']=503
        elif failure=='unknown':receipt['status']='outcome_unknown'
        elif failure=='wrong_error':last['error_code']='tls_failed'
        elif failure=='git_hash':receipt['sources'][0]['sha256']='b'*64
        elif failure=='wrong_version':receipt['sources'][0]['version']='14.1.1'
        elif failure=='extra_source':receipt['sources'].append(dict(receipt['sources'][0],kind='npm_metadata'))
    fetcher.mutate=mutate
    out=ready(flow)
    assert out['fetch']['state'] in {'failed','outcome_unknown'} and out['candidate'] is None
    assert out['analysis']['state']=='failed' and model.calls==0
    svc.on_terminal(run);svc.on_result(run.id,a.id,old);assert svc.wait_idle()
    assert fetcher.calls==1 and model.calls==0


def test_enabling_limited_404_does_not_reinterpret_prior_failed_job(flow):
    svc,run,a,result,fetcher,model,_,root=flow
    fetcher.mutate=partial_404_receipt
    old=ready(flow)
    assert old['fetch']['state']=='failed' and old['candidate'] is None and model.calls==0
    svc.close()
    restarted=OfficialSourceService(svc.p2,root/'official',fetcher,svc.ai,allow_git_only_404=True)
    try:
        restarted.on_terminal(run);restarted.on_result(run.id,a.id,result);assert restarted.wait_idle()
        assert restarted.status(run.id,a.id,1,result['result_id'])==old
        assert fetcher.calls==1 and model.calls==0
    finally:restarted.close()


@pytest.mark.parametrize('field',['scan_id','subject','license_text','coverage','self_hash'])
def test_saved_analysis_rejects_wrong_internal_source_context(flow,field):
    from app.p2.ai_analysis import AnalysisRequest
    svc,run,a,old,fetcher,model,_,_=flow
    svc.allow_git_only_404=True;fetcher.mutate=partial_404_receipt
    out=ready(flow);candidate=out['candidate']
    receipt=svc.adopt(run.id,a.id,adopt_body(old,candidate['candidate_id']));assert svc.wait_idle()
    result=receipt['result'];wrong=deepcopy(candidate)
    if field=='scan_id':wrong['scan_id']='scn_other'
    elif field=='subject':wrong['subject']['resource_id']='cmp_other'
    elif field=='license_text':wrong['license_text']+='unrelated text'
    elif field=='coverage':wrong['coverage']='accepted'
    else:wrong['candidate_sha256']='0'*64
    if field!='self_hash':
        check={k:v for k,v in wrong.items() if k not in {'candidate_id','candidate_sha256'}}
        sha=digest(check);wrong.update(candidate_sha256=sha,candidate_id='p2src_'+sha)
    body=AnalysisRequest(binding=result['binding'],result_id=result['result_id'],result_sha256=result['result_sha256'],
                         material_ids=[receipt['material']['material_id']],idempotency_key='invalid-internal-source-context',
                         previous_result_id=old['result_id'])
    with pytest.raises(P2Error,match='p2_ai_source_context_invalid'):
        svc.ai.create(run.id,a.id,body,source_context=wrong)
    assert model.calls==2
