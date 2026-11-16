"""Acceptance root isolation and transport identity refusal, no external I/O."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import frontend_acceptance as seed


@pytest.mark.parametrize('name', ['data','p1-dev-old','../p1-frontend-acceptance-escape'])
def test_reject_root_names(tmp_path, name):
    with pytest.raises(seed.dev.DevIntegrationError):
        seed.initialize(tmp_path/'output/manual-fixes'/name, repository_root=tmp_path)


def test_symlink_and_unknown_existing_database(tmp_path):
    parent = tmp_path/'output/manual-fixes'
    parent.mkdir(parents=True)
    root = parent/'p1-frontend-acceptance-unknown'
    root.mkdir(mode=0o700)
    (root/'scans.db').write_bytes(b'unknown')
    with pytest.raises(seed.dev.DevIntegrationError):
        seed.initialize(root, repository_root=tmp_path)
    alias = parent/'p1-frontend-acceptance-link'
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(seed.dev.DevIntegrationError):
        seed.initialize(alias, repository_root=tmp_path)
    assert (root/'scans.db').read_bytes() == b'unknown'


def test_seed_mismatch_and_wrong_instance_prevent_writes(tmp_path, monkeypatch):
    root = tmp_path/'output/manual-fixes/p1-frontend-acceptance-identity'
    manifest = seed.initialize(root, repository_root=tmp_path)
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS','http://127.0.0.1:15174')
    before = seed.logical_state(root, repository_root=tmp_path)
    with TestClient(seed.create_acceptance_app(root, repository_root=tmp_path,
            origins=('http://127.0.0.1:15174',))) as client:
        identity = {k:manifest[k] for k in ('root_id','synthetic','seed_version')}
        identity['root_id'] = 'dev_other_instance'
        response = client.post(manifest['tasks']['populated']['href']+'/derive',
            json={'idempotency_key':'refused','expected_facts_hash':manifest['tasks']['populated']['facts_hash']},
            headers={'Origin':'http://127.0.0.1:15174','X-OpenGuard-Dev-Identity':json.dumps(identity)})
        assert response.status_code == 409
    assert seed.logical_state(root, repository_root=tmp_path) == before
    marker = root/seed.MARKER
    value = json.loads(marker.read_text())
    value['seed_version'] = 'p1-dev-integration/2'
    marker.write_text(json.dumps(value))
    with pytest.raises(seed.dev.DevIntegrationError):
        seed.create_acceptance_app(root, repository_root=tmp_path, origins=('http://127.0.0.1:15174',))


@pytest.mark.parametrize('code', [301,302,307,308])
def test_acceptance_client_redirect_refused(code, monkeypatch):
    import urllib.request
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'deploy'))
    from p1_dev_smoke import Client
    client = Client('http://127.0.0.1:18011','http://127.0.0.1:15174',
        {'synthetic':True,'seed_version':seed.SEED_VERSION,'root_id':'dev_synthetic'}, seed_version=seed.SEED_VERSION)
    handler = next(h for h in client.opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
    request = urllib.request.Request('http://127.0.0.1:18011/api/v1/scans')
    with pytest.raises(ValueError, match='redirect refused'):
        handler.redirect_request(request,None,code,'redirect',{},'https://synthetic.invalid/outside')
    with pytest.raises(ValueError, match='verified before writes'):
        client.call('POST','/api/v1/scans',{})


def test_launcher_acceptance_identity_and_command(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/'deploy'))
    import p1_dev as launcher
    root = tmp_path/'output/manual-fixes/p1-frontend-acceptance-safe'
    root.mkdir(parents=True, mode=0o700)
    assert launcher.safe_root(root, repository=tmp_path) == root
    manifest = {'synthetic':True,'root_id':'dev_'+'a'*32,'seed_version':seed.SEED_VERSION}
    (root/seed.MANIFEST).write_text(json.dumps(manifest))
    name, labels = launcher.identity(root, manifest)
    assert name.startswith('openguard-p1-acceptance-')
    assert launcher.serve_command(root,18011,15174)[2] == 'app.frontend_acceptance_server'
    assert launcher.marker(root) == manifest
    with pytest.raises(launcher.LaunchError):
        launcher.check_owned({'Id':'a'*64,'Config':{'Labels':{}}}, labels)
    manifest['seed_version'] = 'p1-dev-integration/2'
    (root/seed.MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(launcher.LaunchError, match='seed version mismatch'):
        launcher.marker(root)
