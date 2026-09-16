"""Review regressions: real ASGI/SQLite, synthetic Docker inspection only."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient
from app import dev_integration as dev
from test_p1_dev_integration import dev_space, database_hashes, ORIGIN

REPO = Path(__file__).resolve().parents[2]
IDENTITY_HEADER = 'X-OpenGuard-Dev-Identity'


def module(name):
    spec = importlib.util.spec_from_file_location(name, REPO / 'deploy' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def configured(monkeypatch, tmp_path):
    launch = module('p1_dev')
    root = tmp_path / 'output/manual-fixes/p1-dev-review'
    root.mkdir(parents=True, mode=0o700)
    manifest = {'synthetic': True, 'seed_version': dev.SEED_VERSION, 'root_id': 'dev_review'}
    (root / 'dev-manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(launch, 'REPOSITORY', tmp_path)
    monkeypatch.setattr(launch, 'safe_root', lambda _: root)
    image = 'sha256:' + 'a' * 64
    monkeypatch.setattr(launch, 'local_image', lambda _: (image, 'linux/amd64'))
    name, labels = launch.identity(root, manifest)
    labels[launch.LABEL + '.config'] = hashlib.sha256(json.dumps([image, 18011, 15174]).encode()).hexdigest()
    command = ['-B', '-m', 'app.dev_integration_server', 'serve', '--root',
               '/workspace/output/manual-fixes/' + root.name, '--port', '18011',
               '--web-port', '15174', '--api-origin-port', '18011']
    info = {'Id': 'b' * 64, 'Image': image, 'State': {'Running': False, 'Status': 'exited'},
            'Config': {'Labels': labels, 'User': '0:0', 'WorkingDir': '/workspace',
                       'Entrypoint': ['/opt/api/bin/python'], 'Cmd': command},
            'HostConfig': {'PortBindings': {'18011/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18011'}]},
                           'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'CapAdd': None,
                           'SecurityOpt': ['no-new-privileges'], 'Privileged': False,
                           'NetworkMode': 'bridge', 'PublishAllPorts': False,
                           'PidMode': '', 'IpcMode': 'private', 'UTSMode': '',
                           'Devices': [], 'DeviceRequests': None, 'ExtraHosts': None,
                           'PidsLimit': 128, 'NanoCpus': 2000000000, 'Memory': 1073741824,
                           'Tmpfs': {'/tmp': 'rw,nosuid,nodev,noexec,size=64m'},
                           'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}},
            'Mounts': [{'Type': 'bind', 'Source': str(tmp_path / p), 'Destination': '/workspace/' + p,
                        'RW': False, 'Propagation': 'rprivate'}
                       for p in ('backend', 'rules', 'schemas', 'examples', 'tests/fixtures')] +
                      [{'Type': 'bind', 'Source': str(root), 'Destination': '/workspace/output/manual-fixes/' + root.name,
                        'RW': True, 'Propagation': 'rprivate'}]}
    calls = []
    monkeypatch.setattr(launch, 'inspect_owned', lambda _: copy.deepcopy(info))
    monkeypatch.setattr(launch, 'check_port', lambda _: None)
    monkeypatch.setattr(launch.time, 'sleep', lambda _: None)
    def docker(*args, **kwargs):
        calls.append(args)
        if args[0] == 'start':
            info['State'].update(Running=True, Status='running')
        return info['Id']
    monkeypatch.setattr(launch, 'docker', docker)
    class Response(io.BytesIO):
        status = 200
        headers = {IDENTITY_HEADER: json.dumps(manifest)}
    monkeypatch.setattr(launch.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=lambda *a, **k: Response(b'{}')))
    return launch, info, calls


@pytest.mark.parametrize('fault', ['image', 'port', 'data', 'source', 'rootfs', 'cap', 'security', 'privileged', 'network', 'command', 'workdir'])
def test_recovery_rejects_actual_configuration_before_start(monkeypatch, tmp_path, fault):
    launch, info, calls = configured(monkeypatch, tmp_path)
    if fault == 'image': info['Image'] = 'sha256:' + 'c' * 64
    elif fault == 'port': info['HostConfig']['PortBindings']['18011/tcp'][0]['HostIp'] = '0.0.0.0'
    elif fault == 'data': info['Mounts'][-1]['Source'] += '-other'
    elif fault == 'source': info['Mounts'][0]['RW'] = True
    elif fault == 'rootfs': info['HostConfig']['ReadonlyRootfs'] = False
    elif fault == 'cap': info['HostConfig']['CapDrop'] = []
    elif fault == 'security': info['HostConfig']['SecurityOpt'] = []
    elif fault == 'privileged': info['HostConfig']['Privileged'] = True
    elif fault == 'network': info['HostConfig']['NetworkMode'] = 'host'
    elif fault == 'command': info['Config']['Cmd'] = ['-c', 'print(1)']
    elif fault == 'workdir': info['Config']['WorkingDir'] = '/tmp'
    with pytest.raises(launch.LaunchError):
        launch.main(['start', '--root', 'ignored', '--image', info['Image']])
    assert not calls, 'mismatched configuration must never start or auto-repair'


def test_valid_restart_and_stop_unsafe_owned_instance(monkeypatch, tmp_path):
    launch, info, calls = configured(monkeypatch, tmp_path)
    launch.main(['start', '--root', 'ignored', '--image', info['Image']])
    assert calls == [('start', info['Id'])]
    info['HostConfig']['ReadonlyRootfs'] = False
    launch.main(['stop', '--root', 'ignored'])
    assert calls[-1] == ('stop', '--time', '15', info['Id'])


@pytest.mark.parametrize('code', [301, 302, 307, 308])
def test_smoke_redirects_are_not_followed(code):
    smoke = module('p1_dev_smoke')
    client = smoke.Client('http://127.0.0.1:18011', ORIGIN)
    handler = next(h for h in client.opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
    request = urllib.request.Request(client.base + '/api/v1/scans', headers={'Origin': ORIGIN})
    with pytest.raises((ValueError, urllib.error.HTTPError)):
        handler.redirect_request(request, io.BytesIO(), code, 'redirect', {}, 'http://outside.invalid/steal')


def test_same_seed_wrong_actual_app_refused_before_write(dev_space, monkeypatch, tmp_path):
    env = dev_space
    other = env.root.with_name('p1-dev-other')
    manifest_b = dev.initialize(other, repository_root=env.repository).to_dict()
    assert manifest_b['scans'] == env.manifest['scans']
    assert manifest_b['root_id'] != env.manifest['root_id']
    smoke = module('p1_dev_smoke')
    writes = []
    app = dev.create_dev_app(other, origins=(ORIGIN,), repository_root=env.repository)
    with TestClient(app) as http:
        class Response(io.BytesIO):
            def __init__(self, response):
                super().__init__(response.content)
                self.status, self.headers = response.status_code, response.headers
        def request(req, **kwargs):
            if req.method != 'GET': writes.append(req.method)
            return Response(http.request(req.method, req.full_url, content=req.data, headers=dict(req.header_items())))
        monkeypatch.setattr(smoke.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=request))
        receipt = tmp_path / 'wrong-receipt.json'
        before = database_hashes(other)
        with pytest.raises((ValueError, AssertionError), match='identity'):
            smoke.main(['--manifest', str(env.root / 'dev-manifest.json'), '--receipt', str(receipt)])
        assert not writes and not receipt.exists()
        assert database_hashes(other) == before


@pytest.mark.parametrize('filename', ['scans.db', 'assessment.db', 'remediation.db', 'report_v2.db'])
@pytest.mark.parametrize('journal', ['DELETE', 'WAL'])
def test_bad_columns_full_start_rejects_without_db_wal_schema_mutation(dev_space, filename, journal):
    env = dev_space
    db = sqlite3.connect(env.root / filename)
    try:
        db.execute('PRAGMA journal_mode=' + journal)
        db.execute('PRAGMA wal_autocheckpoint=0')
        tables = list(dev._REQUIRED_TABLES[filename])
        for table in tables:
            db.execute('DROP TABLE ' + table)
            db.execute('CREATE TABLE ' + table + '(wrong TEXT)')
        db.commit()
        schema = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        before = database_hashes(env.root)
        if journal == 'WAL': assert (env.root / (filename + '-wal')).stat().st_size > 0
        with pytest.raises(dev.DevIntegrationError):
            dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
        assert database_hashes(env.root) == before
        assert db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == schema
    finally:
        db.close()


@pytest.mark.parametrize('change', ['metadata', 'version', 'revision_constraint', 'unique_key'])
@pytest.mark.parametrize('journal', ['DELETE', 'WAL'])
def test_schema_metadata_versions_and_constraints_rejected_readonly(dev_space, change, journal):
    env = dev_space
    filename = 'remediation.db' if change == 'unique_key' else 'scans.db'
    db = sqlite3.connect(env.root / filename)
    try:
        db.execute('PRAGMA journal_mode=' + journal)
        db.execute('PRAGMA wal_autocheckpoint=0')
        if change == 'metadata': db.execute("UPDATE registry_metadata SET schema_name='wrong'")
        elif change == 'version': db.execute('PRAGMA user_version=999')
        else:
            table = 'tasks' if change == 'unique_key' else 'scan_runs'
            sql = db.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0]
            if change == 'unique_key':
                sql = sql.replace(',\n                    UNIQUE(scan_id, assessment_id, origin_key)', '')
            else:
                import re
                sql = re.sub(r'CHECK\s*\(revision\s*>=\s*1\)', '', sql)
            original = db.execute('SELECT sql FROM sqlite_master WHERE name=?', (table,)).fetchone()[0]
            assert sql != original, 'fixture must actually remove the constraint'
            db.execute('DROP TABLE ' + table)
            db.execute(sql)
            if change == 'unique_key':
                db.execute('CREATE INDEX task_page ON tasks(scan_id, assessment_id, created_at, task_id)')
        db.commit()
        before = database_hashes(env.root)
        schema = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        with pytest.raises(dev.DevIntegrationError):
            dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
        assert database_hashes(env.root) == before
        assert db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall() == schema
    finally:
        db.close()


@pytest.mark.parametrize('fault', ['missing', 'root', 'synthetic', 'seed'])
def test_missing_or_changed_identity_stops_before_next_write(dev_space, fault):
    smoke = module('p1_dev_smoke')
    manifest = dev_space.manifest
    identity = {k: manifest[k] for k in ('root_id', 'synthetic', 'seed_version')}
    client = smoke.Client('http://127.0.0.1:18011', ORIGIN, manifest)
    requests = []
    class Response(io.BytesIO):
        status = 200
        def __init__(self, observed):
            super().__init__(b'{}')
            self.headers = {} if observed is None else {IDENTITY_HEADER: json.dumps(observed)}
    observed = dict(identity)
    def request(req, **kwargs):
        requests.append(req.method)
        return Response(observed)
    client.opener = SimpleNamespace(open=request)
    client.bind()
    if fault == 'missing': observed = None
    elif fault == 'root': observed['root_id'] = 'dev_another'
    elif fault == 'synthetic': observed['synthetic'] = False
    else: observed['seed_version'] = 'p1-dev-integration/999'
    with pytest.raises(ValueError, match='identity'):
        client.call('GET', '/api/v1/scans')
    assert requests == ['GET', 'GET']
    # A failed read must invalidate the prior successful bind too.
    with pytest.raises(ValueError, match='identity'):
        client.call('POST', '/api/v1/scans', {})
    assert requests == ['GET', 'GET']


def test_server_precondition_stops_peer_swap_before_writes(dev_space):
    env = dev_space
    app = dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    wrong = {k: env.manifest[k] for k in ('root_id', 'synthetic', 'seed_version')}
    wrong['root_id'] = 'different_root'
    sid = env.manifest['scans']['completed_target']
    aid = env.manifest['assessments'][sid]['assessment_id']
    with TestClient(app) as client:
        before = database_hashes(env.root)
        response = client.post(f'/api/v1/scans/{sid}/assessments/{aid}/remediation-tasks/derive',
                               headers={'Origin': ORIGIN, IDENTITY_HEADER: json.dumps(wrong)}, json={})
        assert response.status_code == 409
        assert json.loads(response.headers[IDENTITY_HEADER])['root_id'] == env.manifest['root_id']
        assert database_hashes(env.root) == before


def test_proxy_http_adapter_and_verify_preserve_observed_identity(dev_space, monkeypatch, tmp_path, capsys):
    env = dev_space
    smoke = module('p1_dev_smoke')
    app = dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    with TestClient(app) as http:
        class Response(io.BytesIO):
            def __init__(self, response):
                super().__init__(response.content)
                self.status, self.headers = response.status_code, response.headers
        def proxy(req, **kwargs):
            # Same origin proxy forwards actual Origin and every response header unchanged.
            assert req.get_header('Origin') == ORIGIN
            assert req.get_header('Sec-fetch-site') == 'same-origin'
            return Response(http.request(req.method, req.full_url, content=req.data, headers=dict(req.header_items())))
        monkeypatch.setattr(smoke.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=proxy))
        receipt_path = tmp_path / 'proxy-receipt.json'
        args = ['--manifest', str(env.root / 'dev-manifest.json'), '--base', ORIGIN,
                '--origin', ORIGIN, '--receipt', str(receipt_path)]
        smoke.main(args)
        receipt = json.loads(receipt_path.read_text())
        assert receipt['observed_identity'] == receipt['manifest_identity']
        assert receipt['observed_identity']['root_id'] == env.manifest['root_id']
        assert receipt['base'] == receipt['origin'] == ORIGIN
        old = receipt_path.read_bytes()
        capsys.readouterr()
        smoke.main(args + ['--verify'])
        verified = json.loads(capsys.readouterr().out)
        assert verified['observed_identity'] == receipt['observed_identity']
        assert receipt_path.read_bytes() == old


@pytest.mark.parametrize('code', [301, 302, 307, 308])
def test_health_redirect_refused(code):
    launch = module('p1_dev')
    with pytest.raises(launch.LaunchError, match='redirect'):
        launch.NoRedirect().redirect_request(urllib.request.Request('http://127.0.0.1:18011/api/v1/scans'),
                                            io.BytesIO(), code, 'redirect', {}, 'http://127.0.0.1:18012/')


def test_replaced_id_after_start_never_gets_stopped(monkeypatch, tmp_path):
    launch, info, calls = configured(monkeypatch, tmp_path)
    original = info['Id']
    def docker(*args, **kwargs):
        calls.append(args)
        info['Id'] = 'd' * 64
        info['State']['Running'] = True
        return original
    monkeypatch.setattr(launch, 'docker', docker)
    with pytest.raises(launch.LaunchError, match='Id|replaced'):
        launch.main(['start', '--root', 'ignored', '--image', info['Image']])
    assert calls == [('start', original)]


def test_equivalent_docker_defaults_are_normalized(monkeypatch, tmp_path):
    launch, info, calls = configured(monkeypatch, tmp_path)
    info['Config']['User'] = '0'
    info['HostConfig'].update(NetworkMode='default', CapAdd=[], Devices=None,
        SecurityOpt=['no-new-privileges:true'], Tmpfs={'/tmp': 'size=67108864,noexec,nodev,nosuid,rw'})
    launch.main(['start', '--root', 'ignored', '--image', info['Image']])
    assert calls == [('start', info['Id'])]


@pytest.mark.parametrize('value', [None, '{}', 'not-json', '{"root_id":"dev_review","synthetic":1,"seed_version":"p1-dev-integration/2"}'])
def test_unverified_health_never_reports_success_and_stops_owned_id(monkeypatch, tmp_path, value, capsys):
    launch, info, calls = configured(monkeypatch, tmp_path)
    class Response(io.BytesIO):
        status = 200
        headers = {} if value is None else {IDENTITY_HEADER: value}
    monkeypatch.setattr(launch.urllib.request, 'build_opener',
                        lambda *a: SimpleNamespace(open=lambda *a, **k: Response(b'{}')))
    with pytest.raises(launch.LaunchError, match='identity'):
        launch.main(['start', '--root', 'ignored', '--image', info['Image']])
    assert calls == [('start', info['Id']), ('stop', '--time', '15', info['Id'])]
    assert not capsys.readouterr().out
