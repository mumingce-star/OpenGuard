"""Owner R1/R2/T1: real provenance, projection-only unknown, narrow messages."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import pytest
from test_p1_profile_backend import profile_env,env,request_for
import sqlite3

def logical(root):
    result={}
    for path in root.glob('*.db'):
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
            result[path.name]={name:db.execute('SELECT * FROM "'+name+'"').fetchall()
                for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    return result

def stable(value):
    value=deepcopy(value);value['provenance'].pop('generated_at');return value

def test_profile_actual_generation_and_stable_read(profile_env,monkeypatch):
    import app.p1.profile as module
    e=profile_env;at=datetime(2030,1,1,tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return at
    monkeypatch.setattr(module,'datetime',Clock)
    before=logical(e.path)
    def forbidden(*a,**k):raise AssertionError('GET side effect')
    monkeypatch.setattr(e.profile.transport,'fetch',forbidden);monkeypatch.setattr(e.profile.parser,'parse',forbidden)
    a=e.profile.get(e.run.id,e.run.ai_assets[0].id)
    assert a['provenance']['generated_at']=='2030-01-01T00:00:00Z'
    at+=timedelta(seconds=3)
    b=e.profile.get(e.run.id,e.run.ai_assets[0].id)
    assert b['provenance']['generated_at']=='2030-01-01T00:00:03Z'
    assert stable(a)==stable(b) and logical(e.path)==before

def test_profile_identity_excludes_only_generation(profile_env):
    from app.p1.profile_store import digest
    e=profile_env;value=e.profile.get(e.run.id,e.run.ai_assets[0].id)
    content=stable(value);content.pop('profile_id')
    assert value['profile_id']=='profile_'+digest(content)

def test_observation_generation_is_not_fetch_time(profile_env):
    e=profile_env;start=datetime.now(timezone.utc)
    e.profile.refresh(e.run.id,request_for(e))
    value=e.profile.get(e.run.id,e.run.ai_assets[0].id)['metadata_observations'][0]
    assert value['fetched_at']=='2026-09-18T00:00:00Z'
    assert start<=datetime.fromisoformat(value['provenance']['generated_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc)

def test_empty_provider_only_projection(env):
    from app.frontend_acceptance import _facts,_persist
    from app.assessment.engine import facts_digest
    from app.p1.profile import ProfileService
    value=_facts(1);value['ai_assets'][0]['provider']=''
    run=_persist(env.registry,value,'completed');before=logical(env.path)
    digest_before=facts_digest(run)
    class NoActions:
        def __getattr__(self,name):raise AssertionError('Unexpected action '+name)
    env.app.state.profile_service=ProfileService(env.registry,transport=NoActions(),parser=NoActions())
    response=env.client.get(f'/api/v1/scans/{run.id}/resources/{run.ai_assets[0].id}/profile')
    assert response.status_code==200,response.text
    assert response.json()['identity']['provider'] is None
    assert 'identity_provider_empty_normalized_to_unknown' in response.json()['coverage_gaps']
    assert env.registry.get(run.id).run.ai_assets[0].provider==''
    assert facts_digest(env.registry.get(run.id).run)==digest_before and logical(env.path)==before

@pytest.mark.parametrize('kind',['profile','report','p0'])
def test_validation_message_scope(env,kind):
    paths={'profile':'/api/v1/scans/s/resource-profiles/refresh',
        'report':'/api/v1/scans/s/assessments/a/report-v2','p0':'/api/v1/scans'}
    response=env.client.post(paths[kind],json={})
    error=response.json()['error']
    if kind=='p0':assert response.status_code==422
    else:
        assert response.status_code==400 and error['code']=='invalid_argument'
        assert error['details']['reason']=='request_invalid'
        assert error['message']==('Profile刷新请求参数无效。' if kind=='profile' else '报告请求参数无效。')
