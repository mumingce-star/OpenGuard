from pathlib import Path
import json,threading
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.api.service import ScanApiService
from app.api.models import GitScanCreateRequest
from app.domain.models import ScanRun
from app.persistence import SQLiteScanRunRegistry
from app.assessment.store import AssessmentStore,AssessmentStoreError
from app.assessment.service import AssessmentService
from app.ai.project import context,validate
from app.assessment.engine import build_assessment

class LocalFake:
    calls=0
    def generate_project(self,payload,timeout):
        self.calls+=1;p=json.loads(payload)
        return json.dumps({'assessment_id':p['assessment_id'],'state_digest':p['state_digest'],'answer':'当前证据不足，需要核对该版本的许可原文和实际交付范围。仅公司内部使用属于场景讨论，正式用途尚未改变。','evidence_ids':[p['evidence'][0]['id']] if p['evidence'] else []})

@pytest.fixture
def harness(tmp_path):
    tmp_path.chmod(0o700);reg=SQLiteScanRunRegistry(tmp_path/'scans.db')
    api=ScanApiService(reg);sample=json.loads(Path('examples/sample-scan-result.json').read_text())
    ids=[]
    for i in range(2):
        accepted=api.create_git_scan(GitScanCreateRequest(source_type='git',source=f'https://github.com/example/repo{i}'))
        row=reg.get(accepted.scan_id);p=row.run.model_dump(mode='json');p.update(status='running',stage='ingestion',progress=5,started_at=p['created_at']);reg.replace(ScanRun.model_validate(p),expected_revision=1)
        q=dict(sample);q.update(id=row.run.id,idempotency_key=row.run.idempotency_key,project=p['project'],created_at=p['created_at'],started_at=p['created_at'],finished_at=p['created_at'],report_links=[])
        reg.replace(ScanRun.model_validate(q),expected_revision=2);ids.append(row.run.id)
    provider=LocalFake();svc=AssessmentService(reg,AssessmentStore(tmp_path/'assessment.db',min_free_bytes=0),provider);svc.initialize()
    with TestClient(create_app(reg,assessment_service=svc)) as c:yield c,svc,provider,ids
    reg.close()

def assess(c,sid,**usage):
    rid=str(uuid4());r=c.post(f'/api/v1/scans/{sid}/assessments',json={'request_id':rid,'usage':usage});assert r.status_code==202,r.text
    job=c.get(f'/api/v1/scans/{sid}/assessments/jobs/{rid}').json();assert job['status']=='succeeded',job
    return job['assessment_id'],rid

def test_explicit_assessment_get_cache_and_old_facts(harness):
    c,s,p,ids=harness;sid=ids[0];before=s.run(sid).model_dump_json();base=f'/api/v1/scans/{sid}'
    assert c.get(base+'/assessments').json()['items']==[];assert p.calls==0
    aid,rid=assess(c,sid,preset='internal');assert p.calls==1
    for _ in range(3):
        a=c.get(base+'/assessments/'+aid).json();assert a['id']==aid
        report=c.get(base+'/assessments/'+aid+'/report?format=json');assert report.status_code==200
        assert report.json()['assessment']==a
        assert c.get(base+'/chat').status_code==200
    assert p.calls==1;assert s.run(sid).model_dump_json()==before
    again=c.post(base+'/assessments',json={'request_id':rid,'usage':{'preset':'internal'}});assert again.status_code==202;assert p.calls==1
    c.post(base+'/assessments',json={'request_id':'second','usage':{'preset':'internal'}})
    assert p.calls==1
    assert c.post(base+'/assessments',json={'request_id':rid,'usage':{'preset':'personal'}}).status_code==409

def test_chat_isolated_idempotent_persistent_and_clear(harness):
    c,s,p,ids=harness;sid,other=ids;aid,_=assess(c,sid);base=f'/api/v1/scans/{sid}'
    payload={'assessment_id':aid,'request_id':'q1','message':'仅公司内部使用呢？','generation':0}
    old=s.store.get(sid,aid).model_dump_json()
    assert c.post(base+'/chat',json=payload).status_code==202
    assert c.post(base+'/chat',json=payload).status_code==202;assert p.calls==2
    row=c.get(base+'/chat').json()['items'][0];assert row['status']=='succeeded';assert row['answer']
    assert s.store.get(sid,aid).model_dump_json()==old
    assert c.post(base+'/chat',json={**payload,'message':'different'}).status_code==409
    assert c.get(f'/api/v1/scans/{other}/assessments/{aid}').status_code==404
    assert c.post(f'/api/v1/scans/{other}/chat',json=payload).status_code==404
    assert s.chat.history(other)['items']==[]
    from app.assessment.chat import ChatStore
    reopened=ChatStore(s.store);assert reopened.history(sid)['items'][0]['answer']==row['answer']
    assert c.delete(base+'/chat?generation=0').status_code==422
    assert c.delete(base+'/chat?generation=0&confirmed=true').status_code==200
    assert c.post(base+'/chat',json=payload).status_code==409
    assert s.store.get(sid,aid).model_dump_json()==old
    assert not s.chat.finish(sid,'q1',0,answer='迟到答复不可以写回')
    assert s.chat.history(sid)['items']==[]

def test_capacity_reservation_and_pending_recovery(harness):
    c,s,p,ids=harness;aid,_=assess(c,ids[0]);s.chat.limits['max_turns']=1
    turn,_=s.chat.reserve(ids[0],aid,'pending','问题',0)
    with pytest.raises(AssessmentStoreError):s.chat.reserve(ids[0],aid,'new','问题',0)
    s.chat.initialize();assert s.chat.history(ids[0])['items'][0]['status']=='failed'
    assert p.calls==1
    with pytest.raises(AssessmentStoreError,match='capacity'):s.chat.reserve(ids[0],aid,'new','问题',0)

def test_clear_while_generation_is_inflight(harness):
    c,s,p,ids=harness;aid,_=assess(c,ids[0]);s.chat.reserve(ids[0],aid,'race','问题',0)
    s.chat.clear(ids[0],0)
    assert not s.chat.finish(ids[0],'race',0,answer='这个迟到回答不应出现。')
    assert s.chat.history(ids[0])['items']==[]

def test_origin_input_and_no_ai(harness):
    c,s,p,ids=harness;url=f'/api/v1/scans/{ids[0]}/assessments'
    assert c.post(url,json={'request_id':'a'},headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post(url,content='x'*20000,headers={'Content-Type':'application/json'}).status_code==413
    aid,_=assess(c,ids[0]);s.provider=None
    assert c.post(f'/api/v1/scans/{ids[0]}/chat',json={'assessment_id':aid,'request_id':'a','message':'问题','generation':0}).status_code==503

@pytest.mark.parametrize('change',[{'evidence_ids':['evd_other']},{'answer':'可以直接商用，无需核验。'},{'answer':'<script>alert(1)</script>'},{'assessment_id':'other'},{'answer':'https://fake.example/license'}])
def test_model_adversarial_output_rejected(harness,change):
    c,s,p,ids=harness;a=build_assessment(s.run(ids[0]));payload=context(s.run(ids[0]),a,'许可证在哪',[])
    valid=json.loads(p.generate_project(payload,30));valid.update(change)
    with pytest.raises(ValueError):validate(json.dumps(valid),payload)

def test_optional_usage_survives_scan_registry_without_rewriting_old(harness):
    c,s,p,ids=harness
    old=s.run(ids[0]);assert 'usage' not in old.project.model_dump()
    api=ScanApiService(s.registry)
    req=GitScanCreateRequest(source_type='git',source='https://github.com/example/new',idempotency_key='usage',usage={'preset':'internal'})
    first=api.create_git_scan(req);assert s.run(first.scan_id).project.usage.preset=='internal'
    again=api.create_git_scan(GitScanCreateRequest.model_validate(req.model_dump(exclude={'usage'})|{'usage':{'preset':'internal'}}))
    assert again.scan_id==first.scan_id

@pytest.mark.parametrize('answer', ['商业销售和闭源分发均获许可，直接发布即可。','当前项目允许商业收费并闭源出售，不必准备任何许可材料。','该项目的全部授权均已确认，企业内部或公开部署没有限制。'])
def test_permission_paraphrase_rejected(harness,answer):
    c,s,p,ids=harness
    payload=context(s.run(ids[0]),build_assessment(s.run(ids[0])),'能商用吗',[])
    reply=json.loads(p.generate_project(payload,30));reply['answer']=answer
    with pytest.raises(ValueError):validate(json.dumps(reply),payload)

def test_explicit_retry_after_fallback_preserves_old(harness):
    c,s,p,ids=harness
    original=p.generate_project
    p.generate_project=lambda *_: 'invalid'
    first,_=assess(c,ids[0])
    assert s.store.get(ids[0],first).ai_status=='fallback'
    p.generate_project=original
    c.post(f'/api/v1/scans/{ids[0]}/assessments',json={'request_id':'explicit-retry'})
    second=s.store.latest(ids[0])
    assert second.id!=first and second.ai_status=='succeeded'
    assert s.store.get(ids[0],first).ai_status=='fallback'

def test_license_declaration_is_not_observed_license_text(harness):
    c,s,p,ids=harness
    payload=json.loads(context(s.run(ids[0]),build_assessment(s.run(ids[0])),'需要核验吗',[]))
    for e in payload['evidence']:e['kind']='manifest'
    raw=json.dumps(payload)
    reply=json.loads(p.generate_project(raw,30));reply['answer']='尽管已获取MIT许可文本，但当前证据不足，还需人工核验。'
    with pytest.raises(ValueError,match='unobserved_license_text'):validate(json.dumps(reply),raw)

@pytest.mark.parametrize('answer',['证据不足，因此不支持任何商业或公开用途。','该组件属于开发示例范畴，许可仍待核验。'])
def test_unknown_does_not_invent_prohibition_or_scope(harness,answer):
    c,s,p,ids=harness
    raw=context(s.run(ids[0]),build_assessment(s.run(ids[0])),'还能使用吗',[])
    reply=json.loads(p.generate_project(raw,30));reply['answer']=answer
    with pytest.raises(ValueError):validate(json.dumps(reply),raw)

def test_disabled_git_rejected_without_queued_record(harness):
    c,s,provider,ids=harness
    before=s.registry.active_count() if hasattr(s,'registry') else None
    response=c.post('/api/v1/scans',json={'source_type':'git','source':'https://github.com/pallets/flask'})
    assert response.status_code==503
    assert response.json()['error']['code']=='git_scanning_unavailable'
    if before is not None: assert s.registry.active_count()==before
