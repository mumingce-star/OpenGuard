"""Dev entry safety; all paths, databases and records are synthetic and temporary."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from app.api.models import ErrorEnvelope

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'unit'))
from test_p1_dev_integration import (  # noqa: E402
    dev, dev_space, dev_http, ORIGIN, database_hashes, assert_error, derive, create_report,
)


def test_missing_root_serve_never_initializes(tmp_path):
    repository = tmp_path / 'repository'
    root = repository / 'output/manual-fixes/p1-dev-absent'
    repository.mkdir()
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(root, origins=(ORIGIN,), repository_root=repository)
    assert not root.exists()


def test_import_never_initializes_default_or_environment_data(tmp_path, monkeypatch):
    production = tmp_path / 'synthetic-production'
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(production))
    def forbidden(*args, **kwargs):
        pytest.fail('import initialized a database or production factory')
    monkeypatch.setattr('app.persistence.SQLiteScanRunRegistry.__init__', forbidden)
    monkeypatch.setattr('app.api.main.create_default_app', forbidden)
    importlib.reload(dev)
    assert not production.exists()


@pytest.mark.parametrize('kind', ['wrong-parent', 'production', 'traversal', 'symlink-parent', 'symlink-root'])
def test_rejects_paths_outside_dedicated_root(tmp_path, kind):
    repository = tmp_path / 'repository'
    parent = repository / 'output/manual-fixes'
    parent.mkdir(parents=True, mode=0o700)
    production = repository / 'data'
    production.mkdir(mode=0o700)
    sentinel = production / 'scans.db'
    sentinel.write_bytes(b'synthetic never-open-or-rewrite sentinel')
    if kind == 'wrong-parent':
        root = repository / 'p1-dev-bad'
    elif kind == 'production':
        root = production
    elif kind == 'traversal':
        root = parent / 'p1-dev-escape' / '..' / '..' / '..' / 'data'
    elif kind == 'symlink-parent':
        alias = repository / 'alias'
        alias.symlink_to(parent, target_is_directory=True)
        root = alias / 'p1-dev-alias'
    else:
        root = parent / 'p1-dev-link'
        root.symlink_to(production, target_is_directory=True)
    before = sentinel.read_bytes()
    with pytest.raises(dev.DevIntegrationError):
        dev.initialize(root, repository_root=repository)
    assert sentinel.read_bytes() == before
    assert list(production.iterdir()) == [sentinel]


def test_foreign_unmarked_database_rejected_without_read_or_rewrite(tmp_path):
    repository = tmp_path / 'repository'
    root = repository / 'output/manual-fixes/p1-dev-foreign'
    root.mkdir(parents=True, mode=0o700)
    db = root / 'scans.db'
    db.write_bytes(b'not-a-dev-database')
    for operation in (dev.initialize, dev.validate_root):
        with pytest.raises(dev.DevIntegrationError):
            operation(root, repository_root=repository)
    assert db.read_bytes() == b'not-a-dev-database'
    assert not (root / dev.MARKER_NAME).exists()


@pytest.mark.parametrize('corruption', ['marker', 'manifest', 'db-symlink', 'db-missing', 'permissions'])
def test_corrupt_or_unsafe_existing_space_fails_closed(dev_space, corruption):
    env = dev_space
    if corruption == 'marker':
        (env.root / dev.MARKER_NAME).write_text('{"synthetic":false}')
    elif corruption == 'manifest':
        (env.root / dev.MANIFEST_NAME).write_text('{"root_id":"wrong"}')
    elif corruption == 'db-symlink':
        db = env.root / 'report_v2.db'
        target = env.root.parent / 'synthetic-foreign.db'
        db.rename(target)
        db.symlink_to(target)
    elif corruption == 'db-missing':
        (env.root / 'report_v2.db').unlink()
    else:
        env.root.chmod(0o777)
    before = database_hashes(env.root)
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    assert database_hashes(env.root) == before


def test_seed_failure_leaves_no_success_marker(tmp_path, monkeypatch):
    repository = tmp_path / 'repository'
    root = repository / 'output/manual-fixes/p1-dev-failure'
    root.parent.mkdir(parents=True, mode=0o700)
    (repository / 'examples').mkdir()
    (repository / 'examples/sample-scan-result.json').write_bytes(
        (Path(__file__).resolve().parents[2] / 'examples/sample-scan-result.json').read_bytes())
    def failed(*args, **kwargs):
        raise OSError('synthetic seed fault')
    monkeypatch.setattr('app.assessment.store.AssessmentStore.create', failed)
    with pytest.raises((dev.DevIntegrationError, OSError)):
        dev.initialize(root, repository_root=repository)
    assert not (root / dev.MARKER_NAME).exists()
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(root, origins=(ORIGIN,), repository_root=repository)


def test_repeat_seed_cannot_overwrite_existing_tasks_reports(dev_http):
    env = dev_http
    derive(env)
    create_report(env)
    before = database_hashes(env.root)
    try:
        result = dev.initialize(env.root, repository_root=env.repository)
    except dev.DevIntegrationError:
        pass  # explicit refusal or verified read-only idempotence are both authorized.
    else:
        assert result.to_dict() == env.manifest
    assert database_hashes(env.root) == before


@pytest.mark.parametrize('headers', [
    {'origin': 'https://external.example'}, {'origin': 'null'},
    {'origin': 'http://127.0.0.1:15174.external.example'},
    {'origin': 'http://127.0.0.1:8080'}, {'sec-fetch-site': 'cross-site'},
    {'origin': ORIGIN, 'sec-fetch-site': 'cross-site'},
])
def test_dev_writes_keep_precise_origin_guard(dev_http, headers):
    env = dev_http
    before = database_hashes(env.root)
    response = env.client.post(env.prefix + '/remediation-tasks/derive', headers=headers,
        json={'idempotency_key': 'blocked', 'expected_facts_hash': env.assessment['facts_hash']})
    assert_error(response, 403, 'origin_rejected')
    assert database_hashes(env.root) == before


@pytest.mark.parametrize('route', ['remediation-tasks/derive', 'report-v2'])
@pytest.mark.parametrize('content_type', ['text/plain', 'application/x-www-form-urlencoded'])
def test_dev_non_json_keeps_400_and_no_writes(dev_http, route, content_type):
    env = dev_http
    before = database_hashes(env.root)
    response = env.client.post(env.prefix + '/' + route, content='{}',
        headers={'origin': ORIGIN, 'content-type': content_type})
    body = assert_error(response, 400, 'invalid_argument')
    assert body['details']['reason'] == 'request_invalid'
    assert database_hashes(env.root) == before


@pytest.mark.parametrize('route', ['remediation-tasks/derive', 'report-v2'])
def test_dev_actual_stream_limit_keeps_413_no_writes(dev_http, route):
    env = dev_http
    before = database_hashes(env.root)
    body = json.dumps({'idempotency_key': 'oversize', 'expected_facts_hash': env.assessment['facts_hash']}).encode()
    body += b' ' * (16385 - len(body))
    response = env.client.post(env.prefix + '/' + route, content=iter([body[:100], body[100:]]),
        headers={'origin': ORIGIN, 'content-type': 'application/json'})
    assert_error(response, 413, 'request_too_large')
    assert database_hashes(env.root) == before


def test_forbidden_runtime_writes_cannot_scan_reassess_or_chat(dev_http, monkeypatch):
    env = dev_http
    def forbidden(*args, **kwargs):
        pytest.fail('dev runtime invoked an unauthorized writer')
    svc = env.app.state.assessment_service
    for name in ('reserve_assessment', 'generate_assessment', 'reserve_chat', 'generate_chat', 'on_terminal'):
        monkeypatch.setattr(svc, name, forbidden)
    monkeypatch.setattr(svc.chat, 'clear', forbidden)
    assert env.app.state.zip_scan_runtime is None
    assert env.app.state.git_scan_runtime is None
    assert env.app.state.zip_dispatcher is None
    assert svc.provider is None
    before = database_hashes(env.root)
    requests = [
        ('POST', '/api/v1/scans', {'source_type': 'git', 'source': 'https://github.com/example/synthetic'}),
        ('POST', f'/api/v1/scans/{env.scan_id}/assessments', {'request_id': 'blocked'}),
        ('POST', f'/api/v1/scans/{env.scan_id}/chat', {'message': 'blocked'}),
        ('DELETE', f'/api/v1/scans/{env.scan_id}/chat?confirmed=true&generation=0', None),
    ]
    for method, path, body in requests:
        response = env.client.request(method, path, json=body, headers={'origin': ORIGIN})
        assert_error(response, 503, 'feature_disabled')
        ErrorEnvelope.model_validate(response.json())
    assert database_hashes(env.root) == before


def test_gets_do_not_seed_scan_model_or_render(dev_http, monkeypatch):
    env = dev_http
    report = create_report(env)
    def forbidden(*args, **kwargs):
        pytest.fail('GET executed a scanner/model/seed/report creation')
    for target in ['app.ai.ollama.OllamaProvider.generate',
                   'app.ai.ollama.OllamaProvider.generate_project',
                   'app.scanners.scancode_pipeline.scan_sealed_tree',
                   'app.scanners.syft_pipeline.scan_sealed_tree',
                   'app.assessment.service.AssessmentService.generate_assessment',
                   'app.assessment.store.AssessmentStore.create',
                   'app.p1.report_v2.ReportV2Service.create']:
        monkeypatch.setattr(target, forbidden)
    monkeypatch.setattr(dev, 'initialize', forbidden)
    before = database_hashes(env.root)
    paths = ['/api/v1/scans', f'/api/v1/scans/{env.scan_id}/graph', env.prefix,
             env.prefix + '/remediation-tasks',
             f'/api/v1/scans/{env.scan_id}/diff?base_scan_id=' + env.manifest['scans']['completed_base']]
    paths.extend(meta['href'] for meta in report['artifacts'])
    for path in paths:
        response = env.client.get(path)
        assert response.status_code == 200, response.text
    assert database_hashes(env.root) == before


@pytest.mark.parametrize('field', ['facts_hash', 'usage_hash', 'version'])
def test_manifest_fixed_assessment_binding_tampering_is_rejected(dev_space, field):
    env = dev_space
    path = env.root / dev.MANIFEST_NAME
    value = json.loads(path.read_text())
    sid = value['scans']['completed_target']
    value['assessments'][sid][field] = 99 if field == 'version' else '0' * 64
    path.write_text(json.dumps(value))
    before = database_hashes(env.root)
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    assert database_hashes(env.root) == before


def test_serve_does_not_initialize_or_generate_assessment(dev_space, monkeypatch):
    env = dev_space
    def forbidden(*args, **kwargs):
        pytest.fail('serve initialized or reseeded data')
    for target in ['app.assessment.service.AssessmentService.initialize',
                   'app.assessment.store.AssessmentStore.initialize',
                   'app.p1.remediation_store.RemediationTaskStore.initialize',
                   'app.p1.report_v2_store.ReportV2Store.initialize',
                   'app.assessment.service.AssessmentService.on_terminal',
                   'app.api.main.create_default_app']:
        monkeypatch.setattr(target, forbidden)
    monkeypatch.setattr(dev, 'initialize', forbidden)
    monkeypatch.setattr(dev, 'build_assessment', forbidden)
    with TestClient(dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)) as client:
        assert client.get('/api/v1/scans').status_code == 200


@pytest.mark.parametrize('origin', ['*', 'https://external.example', 'http://0.0.0.0:15174',
    'http://127.0.0.1:15174/path', 'http://user@localhost:15174'])
def test_invalid_origin_configuration_is_rejected(dev_space, origin):
    env = dev_space
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(origin,), repository_root=env.repository)


def test_factory_rejects_mismatched_origin_environment_without_mutation(dev_space, monkeypatch):
    env = dev_space
    import os
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS', 'http://127.0.0.1:8080')
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    assert os.environ['OPENGUARD_WEB_ORIGINS'] == 'http://127.0.0.1:8080'


@pytest.mark.parametrize('name', [dev.MARKER_NAME, dev.MANIFEST_NAME])
def test_marker_manifest_symlinks_are_rejected_without_writes(dev_space, name):
    env = dev_space
    original = env.root / name
    target = env.root.parent / ('synthetic-target-' + name)
    original.rename(target)
    original.symlink_to(target)
    before = database_hashes(env.root)
    target_before = target.read_bytes()
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    assert database_hashes(env.root) == before
    assert target.read_bytes() == target_before


@pytest.mark.parametrize('corruption', ['empty-sqlite', 'missing-scan-table'])
def test_foreign_registry_schema_rejected_before_constructor_writes(dev_space, corruption):
    import sqlite3
    from contextlib import closing
    env = dev_space
    path = env.root / 'scans.db'
    if corruption == 'empty-sqlite':
        # Replacing only this test-owned file leaves a valid dev marker in place.
        path.unlink()
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('PRAGMA user_version=17')
            connection.commit()
        path.chmod(0o600)
    else:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('DROP TABLE scan_runs')
            connection.commit()
    with closing(sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)) as connection:
        tables_before = connection.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    before = database_hashes(env.root)
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    assert database_hashes(env.root) == before
    with closing(sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)) as connection:
        assert connection.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall() == tables_before


def test_old_seed_version_refused_without_automatic_migration(dev_space):
    env = dev_space
    marker = env.root / dev.MARKER_NAME
    data = json.loads(marker.read_text())
    data['seed_version'] = 'p1-dev-integration/1'
    assert data['seed_version'] != dev.SEED_VERSION
    marker.write_text(json.dumps(data))
    marker_before = marker.read_bytes()
    manifest_before = (env.root / dev.MANIFEST_NAME).read_bytes()
    before = database_hashes(env.root)
    with pytest.raises(dev.DevIntegrationError):
        dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    assert database_hashes(env.root) == before
    assert marker.read_bytes() == marker_before
    assert (env.root / dev.MANIFEST_NAME).read_bytes() == manifest_before
