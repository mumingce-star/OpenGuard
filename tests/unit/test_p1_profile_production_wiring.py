"""Default factory consumes the real B01 parser; only transport is an offline seam."""
from pathlib import Path
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.ingestion.metadata_egress import MetadataTransport
from app.scanners.huggingface_metadata import HuggingFaceMetadataParser
from app.assessment.engine import facts_digest
from app.frontend_acceptance import _facts, _persist
from test_p1_profile_owner_review import logical, stable
from test_p1_contract_schema import validator


def configure(monkeypatch, root, profile='1', assessments='0'):
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(root))
    for key in ('AI', 'PUBLIC_GIT', 'EXTERNAL_SCANNERS', 'DURABLE_ZIP', 'OLLAMA_DOCKER_HOST'):
        monkeypatch.setenv('OPENGUARD_ENABLE_' + key, '0')
    monkeypatch.setenv('OPENGUARD_OLLAMA_DOCKER_HOST', '0')
    monkeypatch.setenv('OPENGUARD_ENABLE_ASSESSMENTS', assessments)
    if profile is None:
        monkeypatch.delenv('OPENGUARD_ENABLE_PROFILE_METADATA', raising=False)
    else:
        monkeypatch.setenv('OPENGUARD_ENABLE_PROFILE_METADATA', profile)


def forbidden(*args, **kwargs):
    raise AssertionError('unexpected side effect')


def test_enabled_factory_uses_real_metadata_chain(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path / 'data')
    monkeypatch.setattr(MetadataTransport, 'fetch', forbidden)
    with TestClient(main.create_default_app()) as client:
        service = client.app.state.profile_service
        assert service.store is not None
        assert service.store.path == tmp_path / 'data' / 'metadata.db'
        assert type(service.transport) is MetadataTransport
        assert type(service.parser) is HuggingFaceMetadataParser


def seed_profile(registry):
    value = _facts(7501)
    value['ai_assets'][0].update(name='google-bert/bert-base-uncased', version=None,
        provider='huggingface', asset_type='model', authorization_status='pending',
        license_expression_id=None, source_url='https://huggingface.co/google-bert/bert-base-uncased')
    return _persist(registry, value, 'completed')


def offline_fetch(self, request):
    from app.ingestion.metadata_types import SourceDescriptor, TemporaryMetadata, build_target
    body = json.dumps({'id': request.repository_id, 'sha': 'a' * 40,
                      'private': False, 'gated': False, 'disabled': False,
                      'cardData': {'license': 'MIT'}}).encode()
    return TemporaryMetadata(SourceDescriptor(
        provider=request.provider, resource_kind=request.resource_kind,
        repository_id=request.repository_id, requested_revision=request.requested_revision,
        revision_mode=request.revision_mode, resolved_revision='a' * 40,
        revision_locator='/sha', version_status='revision_observed',
        source_url=build_target(request), fetched_at='2026-09-22T00:00:00Z',
        content_type='application/json', body_size=len(body),
        body_sha256=hashlib.sha256(body).hexdigest()), body)


@pytest.mark.parametrize('profile', [None, '0', '1'])
@pytest.mark.parametrize('assessments', ['0', '1'])
def test_matrix_refresh_readonly_authority_restart(tmp_path, monkeypatch, profile, assessments):
    root = tmp_path / 'data'
    configure(monkeypatch, root, profile, assessments)
    monkeypatch.setattr(MetadataTransport, 'fetch', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    app = main.create_default_app()
    registry = app.state.profile_service.registry
    assert (app.state.assessment_service is not None) == (assessments == '1')
    assert app.state.git_scan_runtime is None
    assert app.state.zip_scan_runtime._ai_enabled is False
    assert app.state.zip_scan_runtime._external_scanners is False
    if profile == '1':
        with app.state.profile_service.store.connection() as db:
            for name in ('metadata_observations', 'profile_refresh_jobs', 'profile_refresh_requests'):
                assert db.execute('SELECT count(*) FROM ' + name).fetchone()[0] == 0
    run = seed_profile(registry)
    before = registry.get(run.id).run.model_dump_json()
    base = '/api/v1/scans/' + run.id
    href = base + '/resources/' + run.ai_assets[0].id + '/profile'
    body = dict(resource_ids=[run.ai_assets[0].id], expected_facts_hash=facts_digest(run), idempotency_key='wiring')
    with TestClient(app) as client:
        initial = client.get(href)
        assert initial.status_code == 200, initial.text
        validator('ResourceProfile').validate(initial.json())
        assert initial.json()['metadata_observations'] == []
        assert 'metadata_observation_unavailable' in initial.json()['coverage_gaps']
        if profile != '1':
            response = client.post(base + '/resource-profiles/refresh', json=body)
            assert response.status_code == 503
            assert response.json()['error']['code'] == 'feature_disabled'
            assert not (root / 'metadata.db').exists()
            return
        # Persist a real formal Assessment first; metadata must not rewrite it.
        if assessments == '1':
            response = client.post(base + '/assessments', json={'request_id': 'before', 'usage': {'preset': 'internal'}})
            assert response.status_code == 202, response.text
        business = {k: v for k, v in logical(root).items() if k != 'metadata.db'}
        monkeypatch.setattr(MetadataTransport, 'fetch', offline_fetch)
        response = client.post(base + '/resource-profiles/refresh', json=body)
        assert response.status_code == 200, response.text
        job = response.json()
        assert job['status'] == 'succeeded', job
        assert client.get(base + '/resource-profiles/jobs/' + job['job_id']).json() == job
        observed = client.get(href).json()
        validator('ResourceProfile').validate(observed)
        observation, = observed['metadata_observations']
        fields = {f['name']: f['value'] for f in observation['fields']}
        assert fields['canonical_id'] == run.ai_assets[0].name
        assert fields['revision'] == 'a' * 40
        assert fields['visibility'] == 'public' and fields['access_gate'] == 'ungated'
        assert fields['declared_license_raw'] == 'MIT'
        assert observation['parser_version'] == 'openguard-huggingface-metadata/1'
        assert observation['verification_status'] == 'pending'
        assert observed['authorization_fact']['status'] == 'pending'
        assert observed['license_observations'] == []
        after = registry.get(run.id).run
        assert after.model_dump_json() == before
        assert after.ai_assets[0].license_expression_id is None
        assert facts_digest(after) == body['expected_facts_hash']
        assert {k: v for k, v in logical(root).items() if k != 'metadata.db'} == business
        snapshot = logical(root)
        monkeypatch.setattr(MetadataTransport, 'fetch', forbidden)
        monkeypatch.setattr(HuggingFaceMetadataParser, 'parse', forbidden)
        service = app.state.profile_service
        for name in ('reserve', 'claim', 'finish_item', 'initialize'):
            monkeypatch.setattr(service.store, name, forbidden)
        monkeypatch.setattr(service, 'refresh', forbidden)
        if assessments == '1':
            monkeypatch.setattr(app.state.assessment_service, 'reserve_assessment', forbidden)
            monkeypatch.setattr(app.state.assessment_service, 'generate_assessment', forbidden)
        for _ in range(3):
            assert stable(client.get(href).json()) == stable(observed)
        assert logical(root) == snapshot
    with TestClient(main.create_default_app()) as restarted:
        assert stable(restarted.get(href).json()) == stable(observed)
        assert restarted.get(base + '/resource-profiles/jobs/' + job['job_id']).json() == job
    assert logical(root) == snapshot


@pytest.mark.parametrize('value', ['', 'true', 'false', '01', ' 1', '1 ', '2'])
def test_invalid_flag_before_storage(tmp_path, monkeypatch, value):
    root = tmp_path / 'absent'
    configure(monkeypatch, root, value)
    monkeypatch.setattr(MetadataTransport, 'fetch', forbidden)
    with pytest.raises(RuntimeError, match='invalid OPENGUARD_ENABLE_PROFILE_METADATA'):
        main.create_default_app()
    assert not root.exists()


@pytest.mark.parametrize('failure', ['initialize', 'corrupt', 'symlink'])
def test_metadata_failure_preserves_existing_sidecars(tmp_path, monkeypatch, failure):
    from app.p1.profile_store import MetadataStore, ProfileError
    root = tmp_path / 'data'
    configure(monkeypatch, root, '1', '1')
    with TestClient(main.create_default_app()):
        pass
    path = root / 'metadata.db'
    if failure == 'corrupt':
        path.write_bytes(b'controlled invalid database')
    elif failure == 'symlink':
        saved = root / 'saved-metadata.db'
        path.rename(saved)
        path.symlink_to(saved)
    else:
        def reject(self):
            raise ProfileError('upstream_unavailable')
        monkeypatch.setattr(MetadataStore, 'initialize', reject)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')}
    published = []
    monkeypatch.setattr(main, 'create_app', lambda *a, **k: published.append(True))
    with pytest.raises(ProfileError, match='upstream_unavailable'):
        main.create_default_app()
    assert not published
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.db')} == before


@pytest.mark.parametrize('field', ['url', 'endpoint', 'headers', 'token', 'provider_url', 'revision'])
def test_refresh_rejects_client_network_overrides(tmp_path, monkeypatch, field):
    root = tmp_path / 'data'
    configure(monkeypatch, root)
    monkeypatch.setattr(MetadataTransport, 'fetch', forbidden)
    with TestClient(main.create_default_app()) as client:
        run = seed_profile(client.app.state.profile_service.registry)
        before = logical(root)
        body = dict(resource_ids=[run.ai_assets[0].id], expected_facts_hash=facts_digest(run), idempotency_key='invalid')
        body[field] = 'untrusted'
        response = client.post('/api/v1/scans/' + run.id + '/resource-profiles/refresh', json=body)
        assert response.status_code == 400, response.text
        assert response.json()['error']['code'] == 'invalid_argument'
        assert logical(root) == before


def test_compose_default_flag_no_new_volume():
    compose = Path('deploy/compose.yaml').read_text()
    assert 'OPENGUARD_ENABLE_PROFILE_METADATA: "${OPENGUARD_ENABLE_PROFILE_METADATA:-0}"' in compose
    assert compose.endswith('volumes:\n  data:\n')


@pytest.mark.parametrize('case', ['replay', 'facts_conflict', 'invalid_resource', 'upstream'])
def test_default_chain_replay_and_failure_boundaries(tmp_path, monkeypatch, case):
    from app.ingestion.metadata_types import MetadataError, ErrorCode
    root = tmp_path / 'data'
    configure(monkeypatch, root)
    calls = []
    def fetch(self, request):
        calls.append(request)
        if case == 'upstream':
            raise MetadataError(ErrorCode.UPSTREAM)
        return offline_fetch(self, request)
    monkeypatch.setattr(MetadataTransport, 'fetch', fetch)
    with TestClient(main.create_default_app()) as client:
        run = seed_profile(client.app.state.profile_service.registry)
        before = logical(root)
        base = '/api/v1/scans/' + run.id
        body = dict(resource_ids=[run.ai_assets[0].id], expected_facts_hash=facts_digest(run), idempotency_key='boundary')
        if case == 'facts_conflict':
            body['expected_facts_hash'] = '0' * 64
        if case == 'invalid_resource':
            body['resource_ids'] = ['ast_00000000-0000-4000-8000-000000000001']
        response = client.post(base + '/resource-profiles/refresh', json=body)
        if case in ('facts_conflict', 'invalid_resource'):
            assert response.status_code == (409 if case == 'facts_conflict' else 400), response.text
            assert not calls and logical(root) == before
        else:
            assert response.status_code == 200, response.text
            job = response.json()
            assert job['status'] == ('failed' if case == 'upstream' else 'succeeded'), job
            snapshot = logical(root)
            assert client.post(base + '/resource-profiles/refresh', json=body).json() == job
            assert len(calls) == 1 and logical(root) == snapshot
            assert client.get(base + '/resource-profiles/jobs/' + job['job_id']).json() == job
            if case == 'upstream':
                assert client.get(base + '/resources/' + run.ai_assets[0].id + '/profile').json()['metadata_observations'] == []
        saved_run = client.app.state.profile_service.registry.get(run.id).run
        assert saved_run.model_dump(mode='json') == run.model_dump(mode='json')
        assert facts_digest(saved_run) == facts_digest(run)


def test_disabled_preserves_existing_metadata_bytes(tmp_path, monkeypatch):
    root = tmp_path / 'data'
    configure(monkeypatch, root)
    monkeypatch.setattr(MetadataTransport, 'fetch', offline_fetch)
    with TestClient(main.create_default_app()) as client:
        run = seed_profile(client.app.state.profile_service.registry)
        base = '/api/v1/scans/' + run.id
        body = dict(resource_ids=[run.ai_assets[0].id], expected_facts_hash=facts_digest(run), idempotency_key='preserve')
        assert client.post(base + '/resource-profiles/refresh', json=body).json()['status'] == 'succeeded'
    before = {p.name: p.read_bytes() for p in root.glob('metadata.db*')}
    configure(monkeypatch, root, '0')
    monkeypatch.setattr(MetadataTransport, 'fetch', forbidden)
    monkeypatch.setattr(HuggingFaceMetadataParser, 'parse', forbidden)
    with TestClient(main.create_default_app()) as client:
        assert client.get(base + '/resources/' + run.ai_assets[0].id + '/profile').status_code == 200
        assert client.post(base + '/resource-profiles/refresh', json=body).json()['error']['code'] == 'feature_disabled'
    assert {p.name: p.read_bytes() for p in root.glob('metadata.db*')} == before
