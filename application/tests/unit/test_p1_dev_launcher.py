"""Lifecycle command safety without sockets, Docker daemon or subprocesses."""
import importlib.util
from pathlib import Path
import json
import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('p1_dev_launcher', REPO / 'deploy/p1_dev.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize('path', ['data/p1-dev-x', 'output/manual-fixes/other',
    'output/manual-fixes/p1-dev-x/../p1-dev-y', '/tmp/p1-dev-x'])
def test_launcher_root_confined(tmp_path, path):
    with pytest.raises(launcher.LaunchError):
        launcher.safe_root(path, tmp_path)


def test_launcher_symlink_parent_and_public_root_rejected(tmp_path):
    (tmp_path / 'output').mkdir()
    other = tmp_path / 'other'; other.mkdir()
    (tmp_path / 'output/manual-fixes').symlink_to(other, target_is_directory=True)
    with pytest.raises(launcher.LaunchError):
        launcher.safe_root('output/manual-fixes/p1-dev-x', tmp_path)


@pytest.mark.parametrize('port', [0, 80, 8000, 8011, 8080, 5174, 65536])
def test_reserved_ports_rejected(port):
    with pytest.raises(launcher.LaunchError):
        launcher.port_number(port)


def test_mounts_are_public_sources_and_single_dev_root(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'REPOSITORY', tmp_path)
    root = tmp_path / 'output/manual-fixes/p1-dev-x'
    args = launcher.common_args(root, 'sha256:test', 'linux/amd64')
    mounts = [args[i+1] for i,v in enumerate(args) if v == '--mount']
    assert len(mounts) == 6
    assert all(x.endswith(',readonly') for x in mounts[:-1])
    assert 'source=' + str(root) + ',' in mounts[-1]
    assert '--read-only' in args and '--cap-drop=ALL' in args
    assert not any(x in ' '.join(args) for x in ('docker.sock', '--privileged', '--network=host'))


def setup_instance(tmp_path, monkeypatch, info):
    root = tmp_path / 'output/manual-fixes/p1-dev-x'
    root.mkdir(parents=True, mode=0o700)
    manifest = {'synthetic':True,'root_id':'123abc'}
    (root / 'dev-manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(launcher, 'safe_root', lambda value:root)
    monkeypatch.setattr(launcher, 'inspect_owned', lambda name:info)
    monkeypatch.setattr(launcher, 'local_image', lambda image:('sha256:test','linux/amd64'))
    calls = []
    monkeypatch.setattr(launcher, 'docker', lambda *a, **kw:calls.append(a) or 'ok')
    return root, manifest, calls


def test_stop_mismatched_label_never_calls_docker(tmp_path, monkeypatch):
    info = {'Id':'unrelated','Config':{'Labels':{}},'State':{'Running':True}}
    _,_,calls = setup_instance(tmp_path,monkeypatch,info)
    with pytest.raises(launcher.LaunchError, match='identity mismatch'):
        launcher.main(['stop','--root','ignored'])
    assert not calls


def test_stop_exact_owned_id_only(tmp_path,monkeypatch):
    info = {'Id':'a' * 64,'Config':{'Labels':{}},'State':{'Running':True}}
    root,manifest,calls = setup_instance(tmp_path,monkeypatch,info)
    _,labels = launcher.identity(root,manifest)
    info['Config']['Labels'] = labels
    launcher.main(['stop','--root','ignored'])
    assert calls == [('stop','--time','15','a' * 64)]


def test_duplicate_start_does_not_spawn(tmp_path,monkeypatch):
    info = {'Id':'a' * 64,'Config':{'Labels':{}},'State':{'Running':True}}
    root,manifest,calls = setup_instance(tmp_path,monkeypatch,info)
    _,labels = launcher.identity(root,manifest)
    import hashlib
    labels[launcher.LABEL+'.config'] = hashlib.sha256(json.dumps(['sha256:test',18011,15174]).encode()).hexdigest()
    info['Config']['Labels'] = labels
    with pytest.raises(launcher.LaunchError,match='already running'):
        launcher.main(['start','--root','ignored','--image','sha256:test'])
    assert not calls


def test_occupied_port_never_spawns_or_stops(tmp_path,monkeypatch):
    _,_,calls = setup_instance(tmp_path,monkeypatch,None)
    def fail(port):
        raise launcher.LaunchError('port unavailable')
    monkeypatch.setattr(launcher,'check_port',fail)
    with pytest.raises(launcher.LaunchError,match='port unavailable'):
        launcher.main(['start','--root','ignored','--image','sha256:test'])
    assert not calls


def test_inspect_failure_not_treated_as_absence(monkeypatch):
    def fail(*a,**k): raise launcher.LaunchError('daemon unavailable')
    monkeypatch.setattr(launcher,'docker',fail)
    with pytest.raises(launcher.LaunchError,match='daemon unavailable'):
        launcher.inspect_owned('anything')


@pytest.mark.parametrize('base,origin,expected', [
    ('http://127.0.0.1:18011','http://127.0.0.1:15174','same-site'),
    ('http://127.0.0.1:15174','http://127.0.0.1:15174','same-origin'),
    ('http://127.0.0.1:18011','http://localhost:15174','cross-site'),
])
def test_smoke_headers_describe_actual_origin_relationship(base,origin,expected):
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('p1_dev_smoke', REPO / 'deploy/p1_dev_smoke.py')
    smoke = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoke)
    captured = []
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):return b'{}'
    def request(req,**kwargs):
        captured.append(req)
        return Response()
    client=smoke.Client(base,origin)
    client.opener=SimpleNamespace(open=request)
    client.json('GET','/api/v1/scans')
    assert captured[0].get_header('Sec-fetch-site') == expected
    assert captured[0].get_header('Origin') == origin
