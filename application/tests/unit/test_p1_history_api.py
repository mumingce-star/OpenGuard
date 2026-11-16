"""Isolated A02 API, privacy, read-only and frozen schema regression gates."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.api.main import create_app
from app.domain.models import ScanRun
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError
from app.assessment.engine import build_assessment
from app.assessment.models import Assessment
from app.assessment.store import AssessmentStore, AssessmentStoreError
from app.domain.usage import UsageDeclaration
from app.p1.models import P1ScanHistoryItem
from test_p1_contract_schema import validator

SAMPLE = json.loads(Path('examples/sample-scan-result.json').read_text())
NOW = '2026-09-13T00:00:00Z'

@pytest.fixture
def env(tmp_path):
    tmp_path.chmod(0o700)
    registry = SQLiteScanRunRegistry(tmp_path/'scans.db')
    store = AssessmentStore(tmp_path/'assessment.db', min_free_bytes=0)
    store.initialize()
    app = create_app(registry, assessment_service=SimpleNamespace(store=store))
    with TestClient(app) as client:
        yield SimpleNamespace(registry=registry,store=store,app=app,client=client,path=tmp_path)
    registry.close()


def seed(env, number, status='queued', source='https://github.com/Owner/Repo', name='Repo', source_type='git', revision=None):
    p=copy.deepcopy(SAMPLE)
    p.update(id='scn_'+str(UUID(int=number)),idempotency_key=None,status='queued',stage='queued',progress=0,created_at=NOW,started_at=None,finished_at=None,report_links=[],errors=[])
    p['project'].update(id='prj_'+str(UUID(int=number)),source=source,source_type=source_type,name=name,revision=revision,created_at=NOW)
    for field in ['components','ai_assets','licenses','evidence','obligations','findings','remediations']:
        p[field]=[]
    p['summary']={'component_count':0,'ai_asset_count':0,'evidence_count':0,'finding_counts':{k:0 for k in ['pass','warning','review_required','unknown']}}
    run=ScanRun.model_validate(p);env.registry.create(run)
    if status=='queued':return run
    if status=='cancelled':
        p.update(status=status,finished_at=NOW)
        run=ScanRun.model_validate(p);env.registry.replace(run,expected_revision=1);return run
    p.update(status='running',stage='ingestion',progress=5,started_at=NOW)
    run=ScanRun.model_validate(p);env.registry.replace(run,expected_revision=1)
    if status=='running':return run
    q=copy.deepcopy(SAMPLE)
    q.update(id=p['id'],idempotency_key=None,project=p['project'],created_at=NOW,started_at=NOW,finished_at=NOW,report_links=[],status=status)
    q.update(stage='completed' if status=='completed' else 'report',progress=100 if status=='completed' else 95)
    if status in ('failed','partial'):
        q['errors']=[{'code':'scanner_failed','stage':'scan','message':'fixture coverage gap','recoverable':True}]
    run=ScanRun.model_validate(q);env.registry.replace(run,expected_revision=2);return run


def get(env,**params):
    response=env.client.get('/api/v1/scans',params=params)
    assert response.status_code==200,response.text
    data=response.json()
    for item in data['items']:validator('ScanHistoryItem').validate(item)
    return data


def test_empty(env):
    assert get(env)=={'schema_version':'1.0','items':[],'next_cursor':None}


def test_statuses_old_facts_and_schema(env):
    states=['queued','running','completed','partial','failed','cancelled']
    for i,status in enumerate(states,1):seed(env,i,status)
    rows=get(env)['items'];assert [x['status'] for x in rows]==states
    for row in rows:
        assert row['latest_assessment'] is None
        assert row['finding_count']==sum(row['summary']['finding_counts'].values())
        assert row['provenance']['source_refs'][0]['registry_revision'] in (1,2,3)
    bad={**rows[0],'extra':'invalid'}
    with pytest.raises(ValidationError):P1ScanHistoryItem.model_validate(bad)
    assert list(validator('ScanHistoryItem').iter_errors(bad))


def test_stable_sparse_filtered_paging(env):
    for i in range(1,107):seed(env,i,name='needle' if i%3==0 else 'other')
    all_ids=[];cursor=None
    while True:
        page=get(env,limit=7,q='needle',**({'cursor':cursor} if cursor else {}))
        all_ids.extend(x['scan_id'] for x in page['items'])
        cursor=page['next_cursor']
        if cursor is None:break
    assert all_ids==['scn_'+str(UUID(int=i)) for i in range(3,107,3)]
    assert len(all_ids)==len(set(all_ids))


def test_q_semantics_and_cursor_binding(env):
    for i in range(1,4):seed(env,i,name='OpenGuard')
    p=get(env,limit=1,q=' OpenGuard ');cursor=p['next_cursor'];assert cursor
    assert get(env,limit=1,q='openguard',cursor=cursor)['items'][0]['scan_id']!=p['items'][0]['scan_id']
    for q in ['smolagents','']:
        r=env.client.get('/api/v1/scans',params={'q':q,'cursor':cursor});assert r.status_code==400 and r.json()['error']['code']=='cursor_invalid'
    assert len(get(env,q='  ')['items'])==len(get(env)['items'])==3
    assert len(get(env,q='pEnGu')['items'])==3
    assert len(get(env,q='github.com/owner')['items'])==3
    assert get(env,q='.*')['items']==[]


@pytest.mark.parametrize('change', [{'status':'queued'},{'source_type':'git'},{'project_key':'github.com/owner/repo'}])
def test_other_filters_bound_to_cursor(env,change):
    seed(env,1);seed(env,2)
    cursor=get(env,limit=1)['next_cursor']
    r=env.client.get('/api/v1/scans',params={'cursor':cursor,**change});assert r.status_code==400


def test_filters_identity_and_zip_privacy(env):
    for i,source in enumerate(['https://github.com/Owner/Repo','https://github.com/Owner/Repo/','https://github.com/Owner/Repo.git'],1):
        seed(env,i,source=source,revision=str(i))
    for i in [4,5]:seed(env,i,'partial',source='container/SECRETPATH/upload.zip',source_type='zip',name='Upload')
    seed(env,6,source='workspace/LOCALHIDDEN',source_type='local',name='Local')
    rows=get(env)['items'];assert len({x['project_identity']['key'] for x in rows[:3]})==1
    assert rows[3]['project_identity']['key']!=rows[4]['project_identity']['key']
    assert all(x['project_identity']['method']=='scan_only' for x in rows[3:])
    assert len(get(env,project_key='github.com/owner/repo')['items'])==3
    assert len(get(env,status='partial',source_type='zip')['items'])==2
    for word in ['SECRETPATH','LOCALHIDDEN','upload.zip']:
        assert get(env,q=word)['items']==[]
        assert word not in json.dumps(rows)


def test_excludes_nonpublic_search_fields_and_reads_latest(env):
    run=seed(env,1,'partial',revision='REVISIONSECRET')
    assessment=build_assessment(run,UsageDeclaration(preset='internal'))
    payload=assessment.model_dump(mode='json');payload.update(summary='ASSESSMENTSECRET',ai_summary='QWENSECRET')
    a=Assessment.model_validate(payload);env.store.create(a,idempotency_key='fixture',run=run)
    row=get(env)['items'][0];assert row['latest_assessment']['assessment_id']==a.id
    assert row['latest_assessment']['version']==a.version
    for word in ['ASSESSMENTSECRET','QWENSECRET','REVISIONSECRET',run.id,run.project.id,run.evidence[0].excerpt]:
        assert get(env,q=word)['items']==[]


@pytest.mark.parametrize('cursor',['invalid','', 'x'*2050])
def test_invalid_cursor(env,cursor):
    r=env.client.get('/api/v1/scans',params={'cursor':cursor});assert r.status_code==400;assert r.json()['error']['code']=='cursor_invalid'


@pytest.mark.parametrize('params',[{'limit':'0'},{'limit':'101'},{'limit':'abc'},{'status':'invented'},{'source_type':'http'}])
def test_invalid_arguments(env,params):
    r=env.client.get('/api/v1/scans',params=params);assert r.status_code==400 and r.json()['error']['code']=='invalid_argument'


def test_storage_failure_not_cursor_invalid(env,monkeypatch):
    seed(env,1);seed(env,2);cursor=get(env,limit=1)['next_cursor']
    def broken(*a,**k):raise ScanRegistryError('registry_io_failed')
    monkeypatch.setattr(env.registry,'get',broken)
    r=env.client.get('/api/v1/scans',params={'cursor':cursor});assert r.status_code==503 and r.json()['error']['code']=='upstream_unavailable'


def test_assessment_unavailable_not_missing(env,monkeypatch):
    seed(env,1)
    def broken(*a,**k):raise AssessmentStoreError('assessment_store_unavailable')
    monkeypatch.setattr(env.store,'latest',broken)
    r=env.client.get('/api/v1/scans');assert r.status_code==503


def test_read_only_get(env,monkeypatch):
    run=seed(env,1,'partial')
    env.store.create(build_assessment(run,UsageDeclaration()),idempotency_key='fixture',run=run)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.iterdir() if p.is_file()}
    revisions=env.registry.get(run.id).revision
    def forbidden(*args,**kwargs):raise AssertionError('GET invoked a write or generator')
    for name in ['create','replace']:
        monkeypatch.setattr(env.registry,name,forbidden)
    monkeypatch.setattr(env.store,'create',forbidden)
    monkeypatch.setattr('subprocess.Popen',forbidden)
    monkeypatch.setattr('socket.create_connection',forbidden)
    monkeypatch.setattr('app.assessment.service.AssessmentService.generate_assessment',forbidden)
    monkeypatch.setattr('app.ai.OllamaProvider.generate',forbidden)
    monkeypatch.setattr('app.ai.OllamaProvider.generate_project',forbidden)
    monkeypatch.setattr('app.assessment.engine.build_assessment',forbidden)
    for _ in range(3):get(env)
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.iterdir() if p.is_file()}
    assert before==after and env.registry.get(run.id).revision==revisions


def test_defensive_local_absolute_path_projection():
    from app.p1.history import public_source
    from app.domain.models import SourceType
    source,searchable=public_source(SimpleNamespace(project=SimpleNamespace(source_type=SourceType.LOCAL,source='/private/SECRET/workspace')))
    assert source=='Source withheld' and searchable is False


def test_cursor_tamper_restart_and_missing_anchor(env,monkeypatch):
    seed(env,1);seed(env,2)
    token=get(env,limit=1)['next_cursor']
    altered=('A' if token[0]!='A' else 'B')+token[1:]
    assert env.client.get('/api/v1/scans',params={'cursor':altered}).status_code==400
    def missing(*args,**kwargs):raise ScanRegistryError('registry_not_found')
    with monkeypatch.context() as patch:
        patch.setattr(env.registry,'get',missing)
        r=env.client.get('/api/v1/scans',params={'cursor':token})
        assert r.status_code==400 and r.json()['error']['code']=='cursor_invalid'
    env.app.state.history_cursor_key=b'different-process-key'
    assert env.client.get('/api/v1/scans',params={'cursor':token}).status_code==400


def test_insertion_requires_first_page_refresh(env):
    seed(env,10);seed(env,20)
    first=get(env,limit=1);seed(env,1)
    second=get(env,limit=1,cursor=first['next_cursor'])
    assert second['items'][0]['scan_id']=='scn_'+str(UUID(int=20))
    assert get(env,limit=1)['items'][0]['scan_id']=='scn_'+str(UUID(int=1))


def test_unicode_casefold(env):
    seed(env,1,name='Straße');seed(env,2,name='Straße')
    first=get(env,limit=1,q=' STRASSE ')
    assert first['next_cursor']
    assert len(get(env,limit=1,q='straße',cursor=first['next_cursor'])['items'])==1
