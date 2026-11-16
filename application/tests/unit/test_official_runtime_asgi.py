"""Actual default ASGI + account + local fixed-source pipeline.
Remote acquisition and model transports alone are SYNTHETIC_TEST_ONLY.
"""
import hashlib
import json
from pathlib import Path

from starlette.testclient import TestClient
from test_local_accounts import gateway, register, request, ORIGIN
from test_p2_ai_analysis import Model
from app.p2.contract import canonical

TASK = Path(__file__).resolve().parents[4]


def test_default_app_automatic_scan_preview_adoption_usage_and_account_isolation(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    calls = {'fetch': [], 'model': []}
    class SyntheticModel(Model):
        def __init__(self, *args, **kwargs):
            self.calls = 0
        def generate(self, payload):
            calls['model'].append(payload['result_id'])
            return super().generate(payload)
    from app.p2 import ai_analysis
    from app.ingestion.official_http_server import FixedOfficialFetcher, COMMIT, GIT_HOST, GIT_PATH, NPM_HOST, NPM_PATH
    monkeypatch.setattr(ai_analysis, 'BoundQwen', SyntheticModel)
    def fetch(self, job_id):
        calls['fetch'].append(job_id)
        sources=[]
        for kind, raw, url, commit in (
            ('git_license', (TASK/'delivery/recording-materials/LICENSE.txt').read_bytes(), f'https://{GIT_HOST}{GIT_PATH}', COMMIT),
            ('npm_metadata', b'{"name":"http-server","version":"14.1.2","fixture":"SYNTHETIC_TEST_ONLY"}', f'https://{NPM_HOST}{NPM_PATH}', None)):
            path=self.root/(kind+'.body');path.write_bytes(raw)
            sources.append({'kind':kind,'url':url,'name':'http-server','version':'14.1.2','commit':commit,
                'sha256':hashlib.sha256(raw).hexdigest(),'byte_count':len(raw),'body_path':str(path),
                'source_level':'official_repository_bytes_observed' if kind=='git_license' else 'provider_declared_unverified','verification_state':'pending','status':'observed',
                'content_type':'text/plain' if kind=='git_license' else 'application/json','retrieved_at':'2026-10-23T00:00:00Z'})
        return {'job_id':job_id,'status':'succeeded','error_code':None,'sources':sources,
                'http_intents':6,'http_dispatched':6,'http_responses':6,'fixture':'SYNTHETIC_TEST_ONLY_NO_EXTERNAL_HTTP'}
    monkeypatch.setattr(FixedOfficialFetcher, 'fetch', fetch)
    for key,value in {'OPENGUARD_OFFICIAL_SOURCE_AUTO':'1','OPENGUARD_ENABLE_P2_AI':'1',
        'OPENGUARD_P2_AI_MAX_GENERATIONS':'10','OPENGUARD_P2_AI_BUDGET_PATH':str(tmp_path/'model.json'),
        'OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH':str(tmp_path/'http.json')}.items():monkeypatch.setenv(key,value)
    app=gateway(tmp_path/'accounts',monkeypatch)
    with TestClient(app,base_url=ORIGIN) as client:
        user=register(client,'official_owner_a');csrf=user['csrf_token']
        usage={'preset':'open_source','commercial':False,'modified':True,'distributed':False,
               'network_service':True,'training':False,'redistributed_assets':False,'source_disclosure':True,
               'declared_at':'2026-10-23T00:00:00+00:00'}
        created=request(client,'POST','/api/v1/scans',csrf=csrf,body={
            'source_type':'git','source':'https://github.com/http-party/http-server',
            'idempotency_key':'official_test_scan','usage':usage})
        assert created.status_code==202,created.text
        sid=created.json()['scan_id'];scan='/api/v1/scans/'+sid
        a=request(client,'GET',scan+'/assessments').json()['items'][0]
        base=scan+'/assessments/'+a['id']+'/p2'
        official=app.observed_apps[0].state.p2_service.official_sources
        assert official.wait_idle(15)
        index=request(client,'GET',base+'/results?assessment_version=1').json()
        assert index['head_revision']==1
        rid=index['head_result_id'];fixed=base+'/results/'+rid+'?assessment_version=1'
        old=request(client,'GET',fixed);oldraw=old.content;r1=old.json()
        summary=request(client,'GET',base+'/results/'+rid+'/summary?assessment_version=1').content
        url=base+'/official-sources?assessment_version=1&result_id='+rid
        status=request(client,'GET',url)
        assert status.status_code==200,status.text
        doc=status.json();assert doc['fetch']['state']=='ready' and doc['analysis']['state']=='ready',doc
        assert doc['analysis']['mode']=='unadopted_preview' and not doc['adopted_material_ids']
        assert len(calls['fetch'])==1 and len(calls['model'])==1
        assert not r1['material_ids']
        for _ in range(3):assert request(client,'GET',url).json()==doc
        assert len(calls['model'])==1
        body={'binding':r1['binding'],'candidate_id':doc['candidate']['candidate_id'],'result_id':rid,
              'result_sha256':r1['result_sha256'],'expected_revision':1,'parent_result_id':rid,'idempotency_key':'confirmed_license'}
        before=list(calls['model'])
        bad={**body,'result_sha256':'0'*64}
        assert request(client,'POST',base+'/official-sources/adopt',csrf=csrf,body=bad).status_code==409
        assert calls['model']==before
        adopted=request(client,'POST',base+'/official-sources/adopt',csrf=csrf,body=body)
        assert adopted.status_code==201,adopted.text
        result=adopted.json()['result'];material=adopted.json()['material']
        assert material['source_level']=='user_supplied_unverified' and material['verification_state']=='pending'
        assert result['revision']==2 and result['previous_result_id']==rid
        assert result['binding']==r1['binding']
        assert official.wait_idle(15)
        newurl=base+'/official-sources?assessment_version=1&result_id='+result['result_id']
        nextdoc=request(client,'GET',newurl).json()
        assert nextdoc['analysis']['mode']=='saved_material' and nextdoc['analysis']['state']=='ready',nextdoc
        assert len(calls['model'])==2
        assert request(client,'POST',base+'/official-sources/adopt',csrf=csrf,body=body).json()==adopted.json()
        assert official.wait_idle(10) and len(calls['model'])==2
        assert request(client,'GET',fixed).content==oldraw
        assert request(client,'GET',base+'/results/'+rid+'/summary?assessment_version=1').content==summary
        forbidden={'binding':result['binding'],'result_id':result['result_id'],'result_sha256':result['result_sha256'],
                   'material_ids':result['material_ids'],'idempotency_key':'bypass_auto_duplicate'}
        assert request(client,'POST',base+'/ai-analyses',csrf=csrf,body=forbidden).status_code==403
        # Strict JSON check applies also to the nested adoption endpoint.
        dup='{"candidate_id":"a","candidate_id":"b"}'
        assert request(client,'POST',base+'/official-sources/adopt',csrf=csrf,content=dup,headers={'Content-Type':'application/json'}).status_code==422
        root=app.observed_apps[0].state.p2_service
        root.readonly=True
        assert request(client,'POST',base+'/official-sources/adopt',csrf=csrf,body=body).status_code==403
        root.readonly=False
        # Same scan / new usage gets a new Assessment and initial Result with no copied Material.
        changed={**usage,'distributed':True}
        svc=app.observed_apps[0].state.assessment_service
        from app.domain.usage import UsageDeclaration
        _,work=svc.reserve_assessment(sid,UsageDeclaration.model_validate(changed),'explicit_usage_save')
        assert work is not None;svc.generate_assessment(*work)
        a2=svc.store.latest(sid);assert a2.version==2
        assert official.wait_idle(15)
        b2=scan+'/assessments/'+a2.id+'/p2'
        i2=request(client,'GET',b2+'/results?assessment_version=2').json()
        d2=request(client,'GET',b2+'/official-sources?assessment_version=2&result_id='+i2['head_result_id']).json()
        assert d2['analysis']['state']=='ready' and d2['analysis']['mode']=='unadopted_preview',d2
        assert len(calls['fetch'])==1 and len(calls['model'])==3
        assert d2['binding']['usage_hash']!=doc['binding']['usage_hash'] and not d2['adopted_material_ids']
        request(client,'POST','/api/v1/auth/logout',csrf=csrf,body={})
        register(client,'official_owner_b')
        assert request(client,'GET',url).status_code==404
        assert len(calls['fetch'])==1 and len(calls['model'])==3
