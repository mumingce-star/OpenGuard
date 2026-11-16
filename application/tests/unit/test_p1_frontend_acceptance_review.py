"""Owner R1/R2: persistent manifest binding and exec configuration boundary."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from app import frontend_acceptance as seed


def hashes(root):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db*')
            if not p.name.endswith('-shm') and p.is_file() and p.stat().st_size}


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    repo = tmp_path_factory.mktemp('acceptance-review')
    root = repo/'output/manual-fixes/p1-frontend-acceptance-review'
    manifest = seed.initialize(root, repository_root=repo, code_version='synthetic-test')
    return repo,root,manifest


@pytest.mark.parametrize('fault', ['graph_missing','history_count','report_id','report_hash',
    'assessment_missing','reports_empty','task_missing','task_hash','diff_target','identity','unsupported',
    'graph_count','graph_resource','assessment_usage','task_deleted','report_size','report_href','d4_assessment','top_missing'])
def test_manifest_tampering_rejected_readonly(prepared, fault, monkeypatch):
    repo,root,original = prepared
    value = copy.deepcopy(original)
    if fault == 'graph_missing': del value['graphs']['500']
    elif fault == 'history_count': value['history']['count'] = 1
    elif fault == 'report_id': value['reports']['basic']['snapshot_id'] = 'rptv2_'+'0'*36
    elif fault == 'report_hash': value['reports']['basic']['artifacts'][0]['content_hash'] = '0'*64
    elif fault == 'assessment_missing': del value['assessments'][next(iter(value['assessments']))]
    elif fault == 'reports_empty': value['reports'] = {}
    elif fault == 'task_missing': value['tasks']['populated'].pop('initial_tasks')
    elif fault == 'task_hash': value['tasks']['populated']['initial_tasks'][0]['origin']['source_hash']='0'*64
    elif fault == 'diff_target': value['diff']['D2']['target_scan_id'] = value['diff']['D1']['target_scan_id']
    elif fault == 'identity': value['identity']['root_id']='dev_'+'0'*32
    elif fault == 'unsupported': value['unsupported']['profile']['status']='available'
    elif fault == 'graph_count': value['graphs']['100']['edge_count']+=1
    elif fault == 'graph_resource': value['graphs']['100']['resource_id']='cmp_unknown'
    elif fault == 'assessment_usage': value['assessments'][next(iter(value['assessments']))]['usage_hash']='0'*64
    elif fault == 'task_deleted': value['tasks']['populated']['initial_tasks'].pop()
    elif fault == 'report_size': value['reports']['basic']['artifacts'][0]['size_bytes']+=1
    elif fault == 'report_href': value['reports']['basic']['artifacts'][0]['href']='/api/v1/wrong'
    elif fault == 'd4_assessment': value['diff']['D4']['base_assessment_id']=value['diff']['D4']['target_assessment_id']
    elif fault == 'top_missing': del value['api']
    before = hashes(root)
    def forbidden(*a,**k): raise AssertionError('validation attempted a write')
    for owner,name in [(seed.dev.AssessmentStore,'create'),(seed.dev.RemediationService,'derive'),
                       (seed.dev.ReportV2Service,'create')]:
        monkeypatch.setattr(owner,name,forbidden)
    try:
        (root/seed.MANIFEST).write_text(json.dumps(value))
        with pytest.raises(seed.dev.DevIntegrationError):
            seed.read_manifest(root, repository_root=repo)
        assert hashes(root) == before
    finally:
        (root/seed.MANIFEST).write_text(json.dumps(original))


def test_failed_prepare_not_startable(tmp_path,monkeypatch):
    root = tmp_path/'output/manual-fixes/p1-frontend-acceptance-failed'
    def fail(*a,**k): raise RuntimeError('synthetic prepare failure')
    monkeypatch.setattr(seed.dev.ReportV2Service,'create',fail)
    with pytest.raises(RuntimeError):
        seed.initialize(root,repository_root=tmp_path)
    before = hashes(root)
    with pytest.raises(seed.dev.DevIntegrationError, match='acceptance_not_prepared'):
        seed.create_acceptance_app(root,repository_root=tmp_path,origins=('http://127.0.0.1:15174',))
    assert hashes(root) == before


@pytest.mark.parametrize('fault',['valid','rootfs','mount','command','network','port','image'])
def test_audit_checks_configuration_before_exec(tmp_path,monkeypatch,fault):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'deploy'))
    import p1_frontend_acceptance as cli
    from test_p1_dev_review import configured
    launch,info,_ = configured(monkeypatch,tmp_path)
    root=tmp_path/'output/manual-fixes/p1-frontend-acceptance-review'
    manifest={'synthetic':True,'root_id':'dev_'+'a'*32,'seed_version':seed.SEED_VERSION,
              'api_base':'http://127.0.0.1:18011','recommended_web_origin':'http://127.0.0.1:15174'}
    info['Config']['Labels']=launch.identity(root,manifest)[1]
    info['Config']['Labels'][launch.LABEL+'.config']=hashlib.sha256(json.dumps([info['Image'],18011,15174]).encode()).hexdigest()
    info['Config']['Cmd']=launch.serve_command(root,18011,15174)
    info['Mounts'][-1].update(Source=str(root),Destination='/workspace/output/manual-fixes/'+root.name)
    info['State'].update(Running=True,Status='running')
    if fault=='rootfs': info['HostConfig']['ReadonlyRootfs']=False
    elif fault=='mount': info['Mounts'][0]['RW']=True
    elif fault=='command': info['Config']['Cmd'][2]='app.dev_integration_server'
    elif fault=='network': info['HostConfig']['NetworkMode']='host'
    elif fault=='port': info['HostConfig']['PortBindings']['18011/tcp'][0]['HostIp']='0.0.0.0'
    elif fault=='image': info['Image']='not-an-image-id'
    monkeypatch.setattr(cli,'launcher',launch)
    calls=[]
    monkeypatch.setattr(launch,'docker',lambda *a,**k:calls.append(a) or '{}')
    if fault=='valid':
        assert cli.audit(root,manifest)=={}
        assert calls[0][:2]==('exec',info['Id'])
    else:
        with pytest.raises(launch.LaunchError): cli.audit(root,manifest)
        assert calls==[]
        root.mkdir(parents=True,mode=0o700)
        (root/seed.MANIFEST).write_text(json.dumps(manifest))
        monkeypatch.setattr(launch,'safe_root',lambda _:root)
        launch.main(['stop','--root','ignored'])
        assert calls == [('stop','--time','15',info['Id'])]


def test_failed_init_launcher_reports_not_prepared(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'deploy'))
    import p1_frontend_acceptance as cli
    root=tmp_path/'output/manual-fixes/p1-frontend-acceptance-incomplete'
    root.mkdir(parents=True,mode=0o700)
    (root/'scans.db').write_bytes(b'failed initialization evidence')
    monkeypatch.setattr(cli.launcher,'safe_root',lambda _:root)
    monkeypatch.setattr(cli.launcher,'docker',lambda *a,**k:pytest.fail('no Docker for incomplete init'))
    for action in ('start','print-manifest'):
        with pytest.raises(cli.launcher.LaunchError,match='acceptance_not_prepared'):
            cli.main([action,'--root','ignored'])


def test_live_readonly_validation_uses_checked_exact_id(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'deploy'))
    from test_p1_dev_review import configured
    launch,info,_=configured(monkeypatch,tmp_path)
    root=tmp_path/'output/manual-fixes/p1-frontend-acceptance-live'
    manifest={'root_id':'dev_'+'a'*32}
    monkeypatch.setattr(launch,'marker',lambda _:manifest)
    info['State']['Running']=True
    calls=[]
    def check(actual,actual_root,actual_manifest):
        assert (actual,actual_root,actual_manifest)==(info,root,manifest)
        calls.append('check')
        return info['Image']
    monkeypatch.setattr(launch,'check_acceptance_configuration',check)
    monkeypatch.setattr(launch,'docker',lambda *a,**k:calls.append(a) or '{}')
    assert launch.validate_acceptance(root,info['Image'],'linux/amd64')=={}
    assert calls[0]=='check' and calls[1][:2]==('exec',info['Id'])
    assert calls[1][5:7]==('app.frontend_acceptance_server','validate')
    calls.clear()
    with pytest.raises(launch.LaunchError,match='Image'):
        launch.validate_acceptance(root,'sha256:'+'f'*64,'linux/amd64')
    assert calls==['check']


def test_successful_validator_opens_only_readonly_connections(prepared,monkeypatch):
    import sqlite3
    repo,root,manifest=prepared
    original=sqlite3.connect
    calls=[]
    def readonly(database,*args,**kwargs):
        assert kwargs.get('uri') is True and str(database).endswith('?mode=ro')
        calls.append(database)
        connection=original(database,*args,**kwargs)
        connection.execute('PRAGMA query_only=ON')
        return connection
    monkeypatch.setattr(sqlite3,'connect',readonly)
    before=hashes(root)
    assert seed.read_manifest(root,repository_root=repo)==manifest
    assert calls and hashes(root)==before


def test_start_and_print_manifest_use_backend_validation(monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'deploy'))
    import p1_frontend_acceptance as cli
    from test_p1_dev_review import configured
    launch,info,_=configured(monkeypatch,tmp_path)
    root=tmp_path/'output/manual-fixes/p1-frontend-acceptance-tampered'
    root.mkdir(parents=True,mode=0o700)
    manifest={'synthetic':True,'root_id':'dev_'+'a'*32,'seed_version':seed.SEED_VERSION}
    (root/seed.MANIFEST).write_text(json.dumps(manifest))
    monkeypatch.setattr(launch,'safe_root',lambda _:root)
    monkeypatch.setattr(launch,'inspect_owned',lambda _:None)
    monkeypatch.setattr(cli,'launcher',launch)
    calls=[]
    def reject(*a,**k):
        calls.append('validation')
        raise launch.LaunchError('acceptance_not_prepared')
    monkeypatch.setattr(launch,'validate_acceptance',reject)
    monkeypatch.setattr(launch,'docker',lambda *a,**k:pytest.fail('must not start/exec'))
    for action in ('start','print-manifest'):
        with pytest.raises(launch.LaunchError,match='acceptance_not_prepared'):
            cli.main([action,'--root','ignored','--image',info['Image']])
    assert calls==['validation','validation']
