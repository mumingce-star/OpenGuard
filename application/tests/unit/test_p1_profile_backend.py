"""A07-2 offline Profile, refresh and storage boundaries."""
import pytest
from test_p1_history_api import env, seed
from test_p1_contract_schema import validator
from copy import deepcopy
from datetime import datetime,timezone


def profile_semantic(value):
    value=deepcopy(value)
    at=value['provenance'].pop('generated_at')
    assert at.endswith('Z')
    assert datetime.fromisoformat(at.replace('Z','+00:00'))<=datetime.now(timezone.utc)
    return value


def test_profile_route_and_empty_observation(env):
    run=seed(env,1,'completed')
    response=env.client.get(f'/api/v1/scans/{run.id}/resources/{run.components[0].id}/profile')
    assert response.status_code==200,response.text
    validator('ResourceProfile').validate(response.json())
    assert response.json()['metadata_observations']==[]


def test_refresh_default_disabled(env):
    run=seed(env,1,'completed')
    response=env.client.post(f'/api/v1/scans/{run.id}/resource-profiles/refresh',json={
        'resource_ids':[run.components[0].id],'expected_facts_hash':'0'*64,'idempotency_key':'synthetic'})
    assert response.status_code==503 and response.json()['error']['code']=='feature_disabled'


@pytest.mark.parametrize('symbol',['ParsedMetadataObservation','MetadataParser','ProfileService','MetadataStore'])
def test_profile_internal_boundaries_exist(symbol):
    from app.p1 import profile
    assert getattr(profile,symbol)


def test_acceptance_v2_explicit_path_exists():
    from app import frontend_acceptance
    assert callable(frontend_acceptance.initialize_v2)


@pytest.fixture
def profile_env(env):
    from app.frontend_acceptance import _facts,_persist
    from app.frontend_acceptance_profile import add_facts,service
    value=_facts(9,empty=True); add_facts(value)
    run=_persist(env.registry,value,'completed')
    svc=service(env.path,env.registry);svc.store.initialize()
    env.app.state.profile_service=svc
    env.profile=svc;env.run=run
    return env


def request_for(env,key='synthetic',ids=None):
    from app.p1.profile_models import RefreshRequest
    from app.assessment.engine import facts_digest
    return RefreshRequest(resource_ids=ids or [a.id for a in env.run.ai_assets],
        expected_facts_hash=facts_digest(env.run),idempotency_key=key)


def test_refresh_projection_schema_authority_and_dedup(profile_env):
    e=profile_env;s=e.profile;r=e.run
    before=r.model_dump(mode='json')
    initial=s.get(r.id,r.ai_assets[0].id)
    assert initial['metadata_observations']==[]
    job=s.refresh(r.id,request_for(e));assert job['status']=='succeeded'
    assert len(job['items'])==5 and s.transport.calls==5
    same=s.refresh(r.id,request_for(e,ids=list(reversed([a.id for a in r.ai_assets]))))
    assert same==job and s.transport.calls==5
    s.refresh(r.id,request_for(e,key='new-key'))
    for asset in r.ai_assets:
        value=s.get(r.id,asset.id);validator('ResourceProfile').validate(value)
        assert len(value['metadata_observations'])==1
        assert value['authorization_fact']['status']=='pending'
        assert value['license_observations']==[]
        assert profile_semantic(value)==profile_semantic(s.get(r.id,asset.id))
    assert s.transport.calls==10
    unconfirmed=s.get(r.id,r.ai_assets[2].id)
    assert unconfirmed['metadata_observations'][0]['resolved_revision'] is None
    assert unconfirmed['metadata_observations'][0]['verification_status']=='pending'
    assert 'metadata_revision_unconfirmed' in unconfirmed['coverage_gaps']
    assert e.registry.get(r.id).run.model_dump(mode='json')==before


def test_refresh_input_conflicts(profile_env):
    from app.p1.profile_store import ProfileError
    e=profile_env;r=request_for(e)
    e.profile.refresh(e.run.id,r)
    with pytest.raises(ProfileError,match='conflict'):
        e.profile.refresh(e.run.id,request_for(e,ids=[e.run.ai_assets[0].id]))
    r=request_for(e,key='hash');r.expected_facts_hash='0'*64
    with pytest.raises(ProfileError,match='conflict'):e.profile.refresh(e.run.id,r)
    with pytest.raises(ProfileError,match='invalid_argument'):
        e.profile.refresh(e.run.id,request_for(e,key='missing',ids=['ast_missing']))


def test_http_new_observation_explicit_refresh_and_readonly_get(profile_env):
    e=profile_env;rid=e.run.ai_assets[0].id;path=f'/api/v1/scans/{e.run.id}'
    href=path+f'/resources/{rid}/profile'
    assert e.client.get(href).json()['metadata_observations']==[]
    response=e.client.post(path+'/resource-profiles/refresh',json=request_for(e,ids=[rid]).model_dump())
    assert response.status_code==200,response.text
    job=response.json();assert job['status']=='succeeded'
    observed=e.client.get(href).json();validator('ResourceProfile').validate(observed)
    assert len(observed['metadata_observations'])==1 and e.profile.transport.calls==1
    assert e.client.get(path+'/resource-profiles/jobs/'+job['job_id']).json()==job
    assert profile_semantic(e.client.get(href).json())==profile_semantic(observed) and e.profile.transport.calls==1


def test_sqlite_two_connections_concurrent_reservation(profile_env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.p1.profile_store import MetadataStore
    e=profile_env; barrier=Barrier(2)
    def reserve(_):
        store=MetadataStore(e.path/'metadata.db',min_free_bytes=0)
        barrier.wait()
        return store.reserve(e.run.id,request_for(e))
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,range(2)))
    assert len({j['job_id'] for j,new in results})==1
    assert sum(new for _,new in results)==1
    with e.profile.store.connection() as db:
        assert db.execute('SELECT count(*) FROM profile_refresh_jobs').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM profile_refresh_requests').fetchone()[0]==1


@pytest.mark.parametrize('fault',['extra','bad','raise','revision','body_hash','complete_raw'])
def test_parser_and_transport_fail_safely(profile_env,fault):
    from app.profile_synthetic import SENTINEL
    from app.p1.profile_models import ParsedMetadataObservation
    from dataclasses import replace
    e=profile_env;s=e.profile
    if fault in {'revision','body_hash'}:
        original=s.transport.fetch
        def fetch(req):
            temporary=original(req)
            temporary.source=replace(temporary.source,**({'resolved_revision':'bad'} if fault=='revision' else {'body_sha256':'0'*64}))
            return temporary
        s.transport.fetch=fetch
    else:
        def parse(**kw):
            if fault=='raise':raise RuntimeError(SENTINEL)
            if fault=='extra':return {'raw':SENTINEL}
            if fault=='complete_raw':return ParsedMetadataObservation(parser_version='test',bounded_excerpt=kw['temporary_metadata'].bounded_bytes().decode(),fields=[],verification_status='pending',coverage_gaps=[])
            return ParsedMetadataObservation(parser_version='test',bounded_excerpt='x'*1001,fields=[],verification_status='verified',coverage_gaps=[])
        s.parser.parse=parse
    job=s.refresh(e.run.id,request_for(e))
    assert job['status']=='failed'
    assert {i['error_code'] for i in job['items']}=={'metadata_invalid'}
    assert SENTINEL not in str(job)
    assert s.get(e.run.id,e.run.ai_assets[0].id)['metadata_observations']==[]


def test_failure_preserves_success_and_partial_job(profile_env):
    from app.ingestion.metadata_types import MetadataError,ErrorCode
    e=profile_env;s=e.profile;original=s.transport.fetch
    s.refresh(e.run.id,request_for(e))
    before=s.get(e.run.id,e.run.ai_assets[0].id)
    def fetch(req):
        if req.resource_kind=='model':raise MetadataError(ErrorCode.TIMEOUT)
        return original(req)
    s.transport.fetch=fetch
    job=s.refresh(e.run.id,request_for(e,key='partial'))
    assert job['status']=='failed' and {i['status'] for i in job['items']}=={'succeeded','failed'}
    assert profile_semantic(s.get(e.run.id,e.run.ai_assets[0].id))==profile_semantic(before)


def test_observation_collision_rejected(profile_env):
    from app.p1.profile_store import ProfileError
    e=profile_env;s=e.profile;s.refresh(e.run.id,request_for(e))
    rid=e.run.ai_assets[0].id
    observation=s.get(e.run.id,rid)['metadata_observations'][0]
    job,_=s.store.reserve(e.run.id,request_for(e,key='collision',ids=[rid]))
    observation['bounded_excerpt']='different'
    with pytest.raises(ProfileError,match='conflict'):
        s.store.finish_item(e.run.id,job['job_id'],rid,observation=observation)


@pytest.mark.parametrize('status,code',[('queued','not_ready'),('running','not_ready'),('failed','not_comparable'),('cancelled','not_comparable')])
def test_scan_status_gate(env,status,code):
    run=seed(env,1,status)
    response=env.client.get(f'/api/v1/scans/{run.id}/resources/unknown/profile')
    assert response.status_code==409 and response.json()['error']['code']==code
    from app.p1.profile import ProfileService
    env.app.state.profile_service=ProfileService(env.registry,store=object(),transport=object(),parser=object())
    response=env.client.post(f'/api/v1/scans/{run.id}/resource-profiles/refresh',json={
        'resource_ids':['unknown'],'expected_facts_hash':'0'*64,'idempotency_key':'gate'})
    assert response.status_code==409 and response.json()['error']['code']==code


def test_empty_version_only_projection(env):
    from app.frontend_acceptance import _facts,_persist
    from app.assessment.engine import facts_digest
    value=_facts(1);value['components'][0]['version']='';value['ai_assets'][0]['version']=''
    run=_persist(env.registry,value,'partial');before=facts_digest(run)
    for resource in [run.components[0],run.ai_assets[0]]:
        value=env.client.get(f'/api/v1/scans/{run.id}/resources/{resource.id}/profile').json()
        assert value['identity']['version'] is None
        assert 'identity_version_empty_normalized_to_unknown' in value['coverage_gaps']
        assert any('scan' in gap for gap in value['coverage_gaps'])
    assert env.registry.get(run.id).run.components[0].version==''
    assert facts_digest(env.registry.get(run.id).run)==before


@pytest.mark.parametrize('change,status',[
    ({'headers':{'Origin':'https://evil.invalid'}},403),
    ({'headers':{'Sec-Fetch-Site':'cross-site'}},403),
    ({'content':'not-json','headers':{'Content-Type':'text/plain'}},400),
    ({'content':'x'*17000,'headers':{'Content-Type':'application/json'}},413),
    ({'json':{'bad':'x'}},400)])
def test_profile_write_boundary(profile_env,change,status):
    e=profile_env;args={'json':request_for(e).model_dump()}
    if 'content' in change:args.pop('json')
    args.update(change)
    response=e.client.post(f'/api/v1/scans/{e.run.id}/resource-profiles/refresh',**args)
    assert response.status_code==status,response.text
    assert response.json()['error']['request_id']
    assert e.profile.transport.calls==0


def test_no_db_created_by_empty_read(env):
    from app.p1.profile import ProfileService,MetadataStore
    r=seed(env,1,'completed');path=env.path/'absent'/'metadata.db'
    assert ProfileService(env.registry,MetadataStore(path)).get(r.id,r.components[0].id)['metadata_observations']==[]
    assert not path.parent.exists()


def test_new_fetch_time_reuses_original_observation(profile_env):
    from dataclasses import replace
    e=profile_env;s=e.profile;s.refresh(e.run.id,request_for(e))
    before=s.get(e.run.id,e.run.ai_assets[0].id)
    original=s.transport.fetch
    def fetch(req):
        value=original(req);value.source=replace(value.source,fetched_at='2026-09-19T00:00:00Z');return value
    s.transport.fetch=fetch;s.refresh(e.run.id,request_for(e,key='later'))
    assert profile_semantic(s.get(e.run.id,e.run.ai_assets[0].id))==profile_semantic(before)


@pytest.mark.parametrize('case',['duplicate','empty','url','empty_value','nonfinite','unicode_excerpt'])
def test_strict_request_and_parser_dtos(case):
    from app.p1.profile_models import RefreshRequest,ParsedMetadataObservation
    from pydantic import ValidationError
    if case in {'duplicate','empty','url'}:
        value=dict(resource_ids=['a','a'] if case=='duplicate' else [],expected_facts_hash='0'*64,idempotency_key='test')
        if case=='url':value.update(resource_ids=['a'],url='https://evil.invalid')
        with pytest.raises(ValidationError):RefreshRequest.model_validate(value)
    else:
        value=dict(parser_version='test',bounded_excerpt='界'*1000,fields=[],verification_status='pending',coverage_gaps=[])
        if case=='unicode_excerpt':
            assert len(ParsedMetadataObservation(**value).bounded_excerpt)==1000
            value['bounded_excerpt']+='界'
        else:value['fields']=[dict(name='license',value='' if case=='empty_value' else float('nan'),locator='/license',verification_status='pending')]
        with pytest.raises(ValidationError):ParsedMetadataObservation.model_validate(value)


# AUDIT-003 regression fixtures deliberately use the normal synthetic ScanRun
# persistence path.  The two selected IDs are part of add_facts' five legal
# assets; only their valid frozen fact values differ between cases.
def _audit003_run(e, *, same_identity=False):
    from app.frontend_acceptance import _facts, _persist
    from app.frontend_acceptance_profile import add_facts
    value=_facts(30 if same_identity else 31,empty=True);add_facts(value)
    a,b=value['ai_assets'][:2]
    if same_identity:
        for item,revision in ((a,'a'*40),(b,'b'*40)):
            item.update(asset_type='model',name='synthetic/audit003-shared',version=revision,
                source_url='https://huggingface.co/synthetic/audit003-shared')
    else:
        a.update(asset_type='model',name='synthetic/audit003-a',version='a'*40,
            source_url='https://huggingface.co/synthetic/audit003-a')
        b.update(asset_type='dataset',name='synthetic/audit003-b',version='b'*40,
            source_url='https://huggingface.co/datasets/synthetic/audit003-b')
    run=_persist(e.registry,value,'completed');e.run=run
    return run,a['id'],b['id']


def _audit003_rows(path,*tables):
    import sqlite3
    with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
        return {table:db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() for table in tables}


def _audit003_rejects_corrupt_get(e,resource_id,business_before):
    from app.p1.profile_store import ProfileError
    calls=e.profile.transport.calls
    sidecar_before=_audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    def forbidden(*args,**kwargs): raise AssertionError('corrupt GET must not fetch or parse')
    e.profile.transport.fetch=forbidden;e.profile.parser.parse=forbidden
    with pytest.raises(ProfileError) as error:e.profile.get(e.run.id,resource_id)
    assert error.value.code=='upstream_unavailable'
    response=e.client.get(f'/api/v1/scans/{e.run.id}/resources/{resource_id}/profile')
    assert response.status_code==503 and response.json()['error']['code']=='upstream_unavailable'
    assert e.profile.transport.calls==calls
    assert _audit003_rows(e.path/'scans.db','scan_runs')==business_before
    assert _audit003_rows(e.path/'metadata.db',*sidecar_before)==sidecar_before


@pytest.mark.parametrize('same_identity',[False,True],ids=['different_identity_and_instance','same_identity_different_instance'])
def test_audit003a_resource_id_rebinding_fails_closed_for_resource_identity_and_instance(profile_env,same_identity):
    import sqlite3
    e=profile_env;run,a_id,b_id=_audit003_run(e,same_identity=same_identity)
    stored=e.profile._stored(run.id)
    a_ref=e.profile._row(stored,a_id)['ref'];b_ref=e.profile._row(stored,b_id)['ref']
    assert a_id!=b_id and a_ref['resource_instance_key']!=b_ref['resource_instance_key']
    assert (a_ref['resource_identity_key']==b_ref['resource_identity_key']) is same_identity
    e.profile.refresh(run.id,request_for(e,key='audit003a',ids=[a_id]))
    sidecar_before=_audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    assert len(e.profile.get(run.id,a_id)['metadata_observations'])==1
    assert e.profile.get(run.id,b_id)['metadata_observations']==[]
    assert _audit003_rows(e.path/'metadata.db',*sidecar_before)==sidecar_before
    business_before=_audit003_rows(e.path/'scans.db','scan_runs')
    with sqlite3.connect(e.path/'metadata.db') as db:
        db.execute('UPDATE metadata_observations SET resource_id=? WHERE scan_id=? AND resource_id=?',(b_id,run.id,a_id))
    moved=_audit003_rows(e.path/'metadata.db',*sidecar_before)
    assert moved['profile_refresh_jobs']==sidecar_before['profile_refresh_jobs']
    assert moved['profile_refresh_requests']==sidecar_before['profile_refresh_requests']
    old=sidecar_before['metadata_observations'][0];new=moved['metadata_observations'][0]
    assert old[:2]+old[3:]==new[:2]+new[3:] and (old[2],new[2])==(a_id,b_id)
    _audit003_rejects_corrupt_get(e,b_id,business_before)


@pytest.mark.parametrize('tamper',['observation_id','parameters_hash'])
def test_audit003a_observation_id_and_request_parameters_binding_fail_closed(profile_env,tamper):
    import sqlite3
    from app.p1.profile_store import ALGORITHM,canonical,digest,semantic
    e=profile_env;run,a_id,_=_audit003_run(e)
    e.profile.refresh(run.id,request_for(e,key='audit003a-binding',ids=[a_id]))
    observation=e.profile.get(run.id,a_id)['metadata_observations'][0]
    old_id=observation['observation_id']
    if tamper=='observation_id':
        observation['observation_id']='obs_'+'f'*64
    else:
        observation['provenance']['parameters_hash']='0'*64
        row=e.profile._row(e.profile._stored(run.id),a_id)
        observation['observation_id']='obs_'+digest({'scan_id':run.id,'resource':row['ref'],
            'revision_mode':e.profile.metadata_request(row).revision_mode,'algorithm':ALGORITHM,
            'observation':semantic(observation)})
    data=canonical(observation).decode()
    business_before=_audit003_rows(e.path/'scans.db','scan_runs')
    with sqlite3.connect(e.path/'metadata.db') as db:
        db.execute('UPDATE metadata_observations SET observation_id=?,observation_json=?,observation_hash=?,semantic_hash=? WHERE observation_id=?',
            (observation['observation_id'],data,digest(observation),digest(semantic(observation)),old_id))
    _audit003_rejects_corrupt_get(e,a_id,business_before)


def _audit003_replay_requests(e):
    run,a_id,b_id=_audit003_run(e)
    request_a=request_for(e,key='audit003b-a',ids=[a_id])
    request_b=request_for(e,key='audit003b-b',ids=[b_id])
    job_a,created_a=e.profile.store.reserve(run.id,request_a)
    job_b,created_b=e.profile.store.reserve(run.id,request_b)
    assert created_a and created_b
    assert e.profile.store.reserve(run.id,request_a)==(job_a,False)
    assert e.profile.store.reserve(run.id,request_b)==(job_b,False)
    return run,a_id,b_id,request_a,request_b,job_a,job_b


def test_audit003b_request_replay_cannot_be_rebound_to_other_legal_job(profile_env):
    import sqlite3
    from app.p1.profile_store import ProfileError
    e=profile_env;run,_,_,request_a,_,job_a,job_b=_audit003_replay_requests(e)
    baseline=_audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    with sqlite3.connect(e.path/'metadata.db') as db:
        db.execute('UPDATE profile_refresh_requests SET job_id=? WHERE scan_id=? AND request_key=?',
            (job_b['job_id'],run.id,request_a.idempotency_key))
    before=_audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    assert before['metadata_observations']==baseline['metadata_observations']
    assert before['profile_refresh_jobs']==baseline['profile_refresh_jobs']
    assert [r[:3] for r in before['profile_refresh_requests']]==[r[:3] for r in baseline['profile_refresh_requests']]
    with pytest.raises(ProfileError) as error:e.profile.store.reserve(run.id,request_a)
    assert error.value.code=='upstream_unavailable'
    assert _audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')==before
    assert job_a['job_id']!=job_b['job_id'] and job_a['resource_ids']!=job_b['resource_ids']


@pytest.mark.parametrize('tamper',['facts_hash','items'])
def test_audit003b_replay_rejects_legal_hashed_job_fact_and_item_inconsistency(profile_env,tamper):
    import sqlite3
    from app.p1.profile_models import RefreshJob
    from app.p1.profile_store import ProfileError,canonical,digest
    e=profile_env;run,_,b_id,request_a,_,job_a,_=_audit003_replay_requests(e)
    job=deepcopy(job_a)
    if tamper=='facts_hash': job['facts_hash']='0'*64
    else: job['items']=[dict(resource_id=b_id,status='pending',observation_id=None,error_code=None)]
    job=RefreshJob.model_validate(job).model_dump(mode='json')
    with sqlite3.connect(e.path/'metadata.db') as db:
        db.execute('UPDATE profile_refresh_jobs SET job_json=?,job_hash=? WHERE job_id=?',
            (canonical(job).decode(),digest(job),job['job_id']))
    before=_audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    with pytest.raises(ProfileError) as error:e.profile.store.reserve(run.id,request_a)
    assert error.value.code=='upstream_unavailable'
    assert _audit003_rows(e.path/'metadata.db','metadata_observations','profile_refresh_jobs','profile_refresh_requests')==before


def _audit003r1_same_request_jobs(e):
    a=request_for(e,key='audit003-r1-a',ids=[e.run.ai_assets[0].id])
    b=request_for(e,key='audit003-r1-b',ids=a.resource_ids)
    assert a.expected_facts_hash==b.expected_facts_hash
    assert a.resource_ids==b.resource_ids
    assert a.model_dump(exclude={'idempotency_key'})==b.model_dump(exclude={'idempotency_key'})
    ja,created=e.profile.store.reserve(e.run.id,a);assert created
    jb,created=e.profile.store.reserve(e.run.id,b);assert created
    assert ja['job_id']!=jb['job_id']
    assert ja['facts_hash']==jb['facts_hash'] and ja['resource_ids']==jb['resource_ids']
    assert [i['resource_id'] for i in ja['items']]==[i['resource_id'] for i in jb['items']]
    assert e.profile.store.reserve(e.run.id,a)==(ja,False)
    assert e.profile.store.reserve(e.run.id,b)==(jb,False)
    return a,b,ja,jb


def test_audit003r1_same_request_different_keys_keep_distinct_jobs(profile_env):
    e=profile_env;a,b,ja,jb=_audit003r1_same_request_jobs(e)
    before=_audit003_rows(e.profile.store.path,'metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    assert e.profile.store.reserve(e.run.id,b)==(jb,False)
    assert e.profile.store.reserve(e.run.id,a)==(ja,False)
    assert _audit003_rows(e.profile.store.path,*before)==before


def test_audit003r1_same_request_different_keys_cannot_cross_bind_jobs(profile_env):
    import sqlite3
    from app.p1.profile_store import ProfileError
    e=profile_env;a,b,ja,jb=_audit003r1_same_request_jobs(e)
    baseline=_audit003_rows(e.profile.store.path,'metadata_observations','profile_refresh_jobs','profile_refresh_requests')
    with sqlite3.connect(e.profile.store.path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        assert db.execute('UPDATE profile_refresh_requests SET job_id=? WHERE scan_id=? AND request_key=?',
            (jb['job_id'],e.run.id,a.idempotency_key)).rowcount==1
    before=_audit003_rows(e.profile.store.path,*baseline)
    assert before['metadata_observations']==baseline['metadata_observations']
    assert before['profile_refresh_jobs']==baseline['profile_refresh_jobs']
    for old,new in zip(baseline['profile_refresh_requests'],before['profile_refresh_requests']):
        assert old[:3]==new[:3]
        if old[1]==a.idempotency_key:assert old[3]==ja['job_id'] and new[3]==jb['job_id']
        else:assert new==old and new[1]==b.idempotency_key
    try:
        result=e.profile.store.reserve(e.run.id,a)
    except ProfileError as error:
        assert error.code=='upstream_unavailable'
    else:
        assert result==(jb,False)
        pytest.fail('old code accepted Job B for key-a: '+jb['job_id'])
    assert _audit003_rows(e.profile.store.path,*before)==before
