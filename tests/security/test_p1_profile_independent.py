"""Offline negative tests, real SQLite bytes and schema; no external network."""
import json
import hashlib
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_p1_profile_backend import profile_env, env, request_for


def logical(root):
    result={}
    for path in root.glob('*.db'):
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
            result[path.name]={name:db.execute('SELECT * FROM "'+name+'"').fetchall()
                for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
    return result


def test_raw_sentinel_no_persistence_and_get_no_effect(profile_env,monkeypatch,capsys):
    from app.profile_synthetic import SENTINEL
    e=profile_env;s=e.profile
    job=s.refresh(e.run.id,request_for(e))
    before=logical(e.path)
    def forbidden(*a,**k):raise AssertionError('GET called external action')
    monkeypatch.setattr(s.transport,'fetch',forbidden);monkeypatch.setattr(s.parser,'parse',forbidden)
    outputs=[]
    for a in e.run.ai_assets:
        outputs.append(e.client.get(f'/api/v1/scans/{e.run.id}/resources/{a.id}/profile').content)
    outputs.append(e.client.get(f'/api/v1/scans/{e.run.id}/resource-profiles/jobs/{job["job_id"]}').content)
    assert logical(e.path)==before
    for path in e.path.glob('metadata.db*'):
        assert SENTINEL.encode() not in path.read_bytes()
    assert all(SENTINEL.encode() not in value for value in outputs)
    assert SENTINEL not in str(job)+repr(s)+capsys.readouterr().out
    with s.store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            names={r[1] for r in db.execute(f'PRAGMA table_info({table})')}
            assert not names&{'raw','payload','body','response','response_blob','headers','cookie','token','raw_json','raw_bytes'}


def test_raw_sentinel_with_live_nonempty_wal(profile_env):
    from app.profile_synthetic import SENTINEL
    e=profile_env
    # Keep a real connection open so WAL/SHM survive until assertions. Never
    # delete/checkpoint the evidence before examining the physical files.
    with sqlite3.connect(e.profile.store.path) as keeper:
        assert keeper.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        keeper.execute('PRAGMA wal_autocheckpoint=0')
        keeper.execute('BEGIN')
        keeper.execute('SELECT count(*) FROM metadata_observations').fetchone()
        job=e.profile.refresh(e.run.id,request_for(e,key='wal'))
        assert job['status']=='succeeded'
        for suffix in ('','-wal','-shm'):
            path=Path(str(e.profile.store.path)+suffix)
            assert path.exists() and path.stat().st_size>0
            assert SENTINEL.encode() not in path.read_bytes()
        assert SENTINEL not in repr(logical(e.path))


def test_observation_corruption_rejected_readonly(profile_env):
    from app.p1.profile_store import ProfileError
    e=profile_env;e.profile.refresh(e.run.id,request_for(e))
    with sqlite3.connect(e.profile.store.path) as db:
        db.execute("UPDATE metadata_observations SET observation_hash=?",('0'*64,))
    before=e.profile.store.path.read_bytes()
    with pytest.raises(ProfileError):e.profile.get(e.run.id,e.run.ai_assets[0].id)
    assert e.profile.store.path.read_bytes()==before


@pytest.mark.parametrize('fault',['column','index','version','constraint','trigger'])
def test_wrong_schema_rejected_without_modification(tmp_path,fault):
    from app.p1.profile_store import MetadataStore,ProfileError
    tmp_path.chmod(0o700);store=MetadataStore(tmp_path/'metadata.db',min_free_bytes=0);store.initialize()
    with sqlite3.connect(store.path) as db:
        if fault=='column':db.execute('ALTER TABLE metadata_observations ADD COLUMN extra TEXT')
        elif fault=='index':db.execute('DROP INDEX observation_scope')
        elif fault=='version':db.execute('PRAGMA user_version=999')
        elif fault=='constraint':
            db.execute('DROP TABLE profile_refresh_requests')
            db.execute('CREATE TABLE profile_refresh_requests (scan_id TEXT,request_key TEXT,fingerprint TEXT,job_id TEXT)')
        else:db.execute('CREATE TRIGGER extra AFTER INSERT ON metadata_observations BEGIN SELECT 1; END')
    before=store.path.read_bytes()
    for op in (store.initialize,lambda:store.observations('s','r','f')):
        with pytest.raises(ProfileError):op()
        assert store.path.read_bytes()==before


@pytest.mark.parametrize('fault',['symlink','permissions','capacity'])
def test_private_path_capacity_fail_closed(tmp_path,fault):
    from app.p1.profile_store import MetadataStore,ProfileError
    root=tmp_path/'private';root.mkdir(mode=0o700)
    store=MetadataStore(root/'metadata.db',min_free_bytes=0)
    if fault=='symlink':store.path.symlink_to(tmp_path/'outside.db')
    elif fault=='permissions':root.chmod(0o755)
    else:store.min_free_bytes=10**30
    with pytest.raises(ProfileError):store.initialize()
    assert not (tmp_path/'outside.db').exists()


@pytest.fixture(scope='module')
def v2(tmp_path_factory):
    from app.frontend_acceptance import initialize_v2
    repo=tmp_path_factory.mktemp('profile-v2')
    root=repo/'output/manual-fixes/p1-frontend-acceptance-profile-v2'
    manifest=initialize_v2(root,repository_root=repo,code_version='synthetic-test')
    return repo,root,manifest


def test_v2_scenarios_real_services(v2,monkeypatch):
    from app.frontend_acceptance import create_acceptance_app,logical_state
    from test_p1_contract_schema import validator
    repo,root,manifest=v2
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS','http://127.0.0.1:15174')
    app=create_acceptance_app(root,repository_root=repo,origins=('http://127.0.0.1:15174',))
    with TestClient(app) as client:
        before=logical_state(root,repository_root=repo)
        assert set(manifest['profiles'])=={'P1','P2','P3','P4','P5'}
        assert set(manifest['unsupported'])=={'notice'}
        for row in manifest['profiles'].values():
            response=client.get(row['href']);assert response.status_code==200,response.text
            p=response.json();validator('ResourceProfile').validate(p)
            assert len(p['metadata_observations'])==row['expected_metadata_count']
            assert p['coverage_gaps']==row['expected_gaps']
        assert logical_state(root,repository_root=repo)==before
        assert client.get(manifest['unsupported']['notice']['href']).status_code==404


def test_v2_unfetched_probe_uses_real_refresh(v2,monkeypatch):
    from app import frontend_acceptance as seed
    repo,root,manifest=v2
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS','http://127.0.0.1:15174')
    with TestClient(seed.create_acceptance_app(root,repository_root=repo,origins=('http://127.0.0.1:15174',))) as client:
        sid=manifest['profiles']['P2']['scan_id'];base=f'/api/v1/scans/{sid}'
        rows=client.get(base+'/resources?kind=ai_asset').json()['items']
        resource=next(r['resource'] for r in rows if r['resource']['name']=='synthetic/unfetched')
        href=base+'/resources/'+resource['id']+'/profile'
        before=client.get(href).json();assert before['metadata_observations']==[]
        result=client.post(base+'/resource-profiles/refresh',json=dict(resource_ids=[resource['id']],
            expected_facts_hash=before['scan_ref']['facts_hash'],idempotency_key='probe'))
        assert result.status_code==200 and result.json()['status']=='succeeded'
        assert len(client.get(href).json()['metadata_observations'])==1
        assert seed.read_manifest(root,repository_root=repo)==manifest


@pytest.mark.parametrize('field,value',[('resource_id','ast_wrong'),('scenario','wrong'),('expected_metadata_count',0)])
def test_v2_manifest_tamper_refused_readonly(v2,field,value):
    from app import frontend_acceptance as seed
    repo,root,manifest=v2;path=root/seed.MANIFEST;original=path.read_bytes()
    changed=json.loads(original);changed['profiles']['P2'][field]=value
    before=logical(root)
    try:
        path.write_text(json.dumps(changed))
        with pytest.raises(seed.dev.DevIntegrationError):seed.read_manifest(root,repository_root=repo)
        assert logical(root)==before
    finally:path.write_bytes(original)


def test_v1_remains_unavailable_without_metadata(tmp_path,monkeypatch):
    from app import frontend_acceptance as seed
    root=tmp_path/'output/manual-fixes/p1-frontend-acceptance-v1'
    manifest=seed.initialize(root,repository_root=tmp_path)
    assert manifest['seed_version']=='p1-frontend-acceptance/1'
    assert not (root/'metadata.db').exists()
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS','http://127.0.0.1:15174')
    with TestClient(seed.create_acceptance_app(root,repository_root=tmp_path,origins=('http://127.0.0.1:15174',))) as client:
        assert client.get(manifest['unsupported']['profile']['href']).status_code==404
        seed.read_manifest(root,repository_root=tmp_path)
    assert not (root/'metadata.db').exists()


def test_default_production_factory_has_no_metadata_network(tmp_path,monkeypatch):
    from app.api.main import create_default_app
    from app.ingestion.metadata_egress import MetadataTransport
    def forbidden(*a,**k):raise AssertionError('default factory constructed metadata transport')
    monkeypatch.setattr(MetadataTransport,'__init__',forbidden)
    monkeypatch.setenv('OPENGUARD_DATA_DIR',str(tmp_path/'default-private'))
    for key in ('EXTERNAL_SCANNERS','DURABLE_ZIP','AI','ASSESSMENTS','PUBLIC_GIT'):
        monkeypatch.setenv('OPENGUARD_ENABLE_'+key,'0')
    app=create_default_app()
    with TestClient(app) as client:
        assert app.state.profile_service.transport is None
        assert app.state.profile_service.parser is None
        response=client.post('/api/v1/scans/scn_missing/resource-profiles/refresh',json={
            'resource_ids':['ast_missing'],'expected_facts_hash':'0'*64,'idempotency_key':'disabled'})
        assert response.status_code==503 and response.json()['error']['code']=='feature_disabled'
    assert not list(tmp_path.rglob('metadata.db'))
