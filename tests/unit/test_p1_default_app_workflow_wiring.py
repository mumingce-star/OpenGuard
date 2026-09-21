"""Production factory wiring with real, private sidecars and synthetic facts."""
from types import SimpleNamespace
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.api import main
from test_p1_history_api import seed
from test_p1_contract_schema import validator


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(tmp_path / 'data'))
    for key, value in {
        'ASSESSMENTS': '1', 'AI': '0', 'PUBLIC_GIT': '0',
        'EXTERNAL_SCANNERS': '0', 'DURABLE_ZIP': '0',
    }.items():
        monkeypatch.setenv('OPENGUARD_ENABLE_' + key, value)
    app = main.create_default_app()
    service = app.state.assessment_service
    assert service is not None
    env = SimpleNamespace(app=app, registry=service.registry, data=tmp_path / 'data')
    env.run = seed(env, 9001, 'completed')
    with TestClient(app) as client:
        env.client = client
        response = client.post(f'/api/v1/scans/{env.run.id}/assessments',
                               json={'request_id': 'wiring', 'usage': {'preset': 'internal'}})
        assert response.status_code == 202, response.text
        job = client.get(f'/api/v1/scans/{env.run.id}/assessments/jobs/wiring').json()
        assert job['status'] == 'succeeded', job
        env.assessment = service.store.get(env.run.id, job['assessment_id'])
        assert env.assessment.formal
        env.base = f'/api/v1/scans/{env.run.id}/assessments/{env.assessment.id}'
        yield env


def derive(env):
    return env.client.post(env.base + '/remediation-tasks/derive', json={
        'idempotency_key': 'wiring-tasks', 'expected_facts_hash': env.assessment.facts_hash,
    })


def test_default_remediation_production_wiring(workflow):
    response = derive(workflow)
    assert response.status_code == 200, response.text
    assert response.json()['items']
    assert workflow.app.state.remediation_service is not None


def test_default_report_production_wiring(workflow):
    response = workflow.client.post(workflow.base + '/report-v2',
                                    json={'idempotency_key': 'wiring-report'})
    assert response.status_code == 200, response.text
    assert workflow.app.state.report_v2_service is not None


def test_shared_stores_paths_and_graph_limits(workflow):
    state = workflow.app.state
    assessment, tasks, reports = state.assessment_service, state.remediation_service, state.report_v2_service
    assert assessment.registry is tasks.registry is reports.registry
    assert assessment.store is tasks.assessments is reports.assessment_store
    assert tasks.store is reports.task_store
    for store, name in [(assessment.store, 'assessment.db'), (tasks.store, 'remediation.db'),
                        (reports.report_store, 'report_v2.db')]:
        assert store.path == workflow.data / name
        assert store.path.is_file()
        assert store.path.stat().st_mode & 0o077 == 0
    assert reports.graph_reader.max_nodes == state.p1_graph_max_nodes == 20_000
    assert reports.graph_reader.max_edges == state.p1_graph_max_edges == 60_000
    assert assessment.provider is None
    assert state.git_scan_runtime is None
    assert state.zip_dispatcher is None


@pytest.mark.parametrize('enabled', [None, '0'])
def test_disabled_never_creates_workflow_sidecars(tmp_path, monkeypatch, enabled):
    data = tmp_path / 'disabled'
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(data))
    if enabled is None:
        monkeypatch.delenv('OPENGUARD_ENABLE_ASSESSMENTS', raising=False)
    else:
        monkeypatch.setenv('OPENGUARD_ENABLE_ASSESSMENTS', enabled)
    for flag in ('AI', 'PUBLIC_GIT', 'EXTERNAL_SCANNERS', 'DURABLE_ZIP'):
        monkeypatch.setenv('OPENGUARD_ENABLE_' + flag, '0')
    app = main.create_default_app()
    with TestClient(app) as client:
        for name in ('assessment_service', 'remediation_service', 'report_v2_service'):
            assert getattr(app.state, name) is None
        base = '/api/v1/scans/absent/assessments/absent'
        for url, body in [(base + '/remediation-tasks/derive', {'idempotency_key': 'off', 'expected_facts_hash': 'a' * 64}),
                          (base + '/report-v2', {'idempotency_key': 'off'})]:
            response = client.post(url, json=body)
            assert response.status_code == 503
            assert response.json()['error']['code'] == 'feature_disabled'
    assert not any((data / name).exists() for name in ('assessment.db', 'remediation.db', 'report_v2.db'))


@pytest.mark.parametrize('filename', ['remediation.db', 'report_v2.db'])
@pytest.mark.parametrize('failure', ['symlink', 'capacity'])
def test_sidecar_failure_does_not_publish_partial_app(tmp_path, monkeypatch, filename, failure):
    from app.p1 import remediation_store, report_v2_store
    data = tmp_path / 'failure'
    data.mkdir(mode=0o700)
    monkeypatch.setenv('OPENGUARD_DATA_DIR', str(data))
    monkeypatch.setenv('OPENGUARD_ENABLE_ASSESSMENTS', '1')
    for flag in ('AI', 'PUBLIC_GIT', 'EXTERNAL_SCANNERS', 'DURABLE_ZIP'):
        monkeypatch.setenv('OPENGUARD_ENABLE_' + flag, '0')
    store_class, error_class = ((remediation_store.RemediationTaskStore, remediation_store.RemediationStoreError)
                                if filename == 'remediation.db'
                                else (report_v2_store.ReportV2Store, report_v2_store.ReportV2StoreError))
    sentinel = tmp_path / 'preserved'
    sentinel.write_bytes(b'pre-existing-data-must-not-be-deleted')
    if failure == 'symlink':
        (data / filename).symlink_to(sentinel)
    else:
        def fail_capacity(self):
            raise error_class('storage_capacity_exceeded')
        monkeypatch.setattr(store_class, 'initialize', fail_capacity)
    published = []
    monkeypatch.setattr(main, 'create_app', lambda *args, **kwargs: published.append(kwargs))
    with pytest.raises(error_class):
        main.create_default_app()
    assert published == []
    assert sentinel.read_bytes() == b'pre-existing-data-must-not-be-deleted'
    assert (data / 'assessment.db').is_file()
    if filename == 'report_v2.db':
        assert (data / 'remediation.db').is_file()
    if failure == 'symlink':
        assert (data / filename).is_symlink()


def patch_task(env, task, status, note):
    return env.client.patch(env.base + '/remediation-tasks/' + task['task_id'], json={
        'expected_version': task['version'], 'status': status, 'note': note,
    })


def test_real_task_workflow_cas_and_fixed_report(workflow, monkeypatch):
    env = workflow
    before = env.registry.get(env.run.id).run.model_dump_json()
    formal = env.assessment.model_dump_json()
    response = derive(env)
    assert response.status_code == 200, response.text
    tasks = response.json()['items']
    assert len(tasks) >= 2
    for task in tasks:
        validator('RemediationTask').validate(task)
        assert task['status'] == 'todo'
    page = env.client.get(env.base + '/remediation-tasks?limit=1').json()
    assert len(page['items']) == 1 and page['next_cursor']
    assert env.client.get(env.base + '/remediation-tasks', params={'cursor': page['next_cursor'], 'limit': 1}).status_code == 200
    first, second = tasks[:2]
    assert patch_task(env, first, 'done', '').status_code == 400
    response = patch_task(env, first, 'in_progress', 'reviewing')
    assert response.status_code == 200, response.text
    progressing = response.json()
    assert progressing['version'] == first['version'] + 1
    assert patch_task(env, first, 'done', 'stale attempt').status_code == 409
    response = patch_task(env, progressing, 'done', 'verified supporting material')
    assert response.status_code == 200, response.text
    done = response.json()
    assert done['status'] == 'done' and done['version'] == 3 and done['note']
    assert patch_task(env, second, 'dismissed', '').status_code == 400
    response = patch_task(env, second, 'dismissed', 'not in delivery scope')
    assert response.status_code == 200, response.text
    dismissed = response.json()
    assert dismissed['status'] == 'dismissed' and dismissed['note']
    refs = [{'task_id': t['task_id'], 'version': t['version']} for t in (done, dismissed)]
    response = env.client.post(env.base + '/report-v2', json={'idempotency_key': 'fixed', 'task_refs': refs, 'notice_refs': []})
    assert response.status_code == 200, response.text
    snapshot = response.json()
    validator('ReportV2Snapshot').validate(snapshot)
    assert snapshot['binding']['scan_ref']['scan_id'] == env.run.id
    assert snapshot['binding']['scan_ref']['facts_hash'] == env.assessment.facts_hash
    assert snapshot['binding']['assessment_ref']['assessment_id'] == env.assessment.id
    assert sorted(snapshot['binding']['task_refs'], key=lambda t: t['task_id']) == sorted(refs, key=lambda t: t['task_id'])
    artifacts = {}
    for meta in snapshot['artifacts']:
        downloaded = env.client.get(meta['href'])
        assert downloaded.status_code == 200
        assert len(downloaded.content) == meta['size_bytes']
        assert hashlib.sha256(downloaded.content).hexdigest() == meta['content_hash']
        artifacts[meta['href']] = downloaded.content
    document = json.loads(next(v for v in artifacts.values() if v.startswith(b'{')))
    assert {'formal_assessment', 'workflow', 'ai_explanation'} <= {s['authority'] for s in document['sections']}
    assert document['provenance'] and snapshot['provenance']
    assert patch_task(env, done, 'todo', 'reopen after report').status_code == 200
    assert env.registry.get(env.run.id).run.model_dump_json() == before
    assert env.app.state.assessment_service.store.get(env.run.id, env.assessment.id).model_dump_json() == formal
    db_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in env.data.glob('*.db')}
    def forbidden(*args, **kwargs):
        raise AssertionError('immutable GET must not invoke sources or generators')
    from app.p1 import report_v2
    state = env.app.state
    for owner, name in [(state.report_v2_service, 'create'), (env.registry, 'get'),
                        (state.assessment_service, 'reserve_assessment'), (state.assessment_service, 'generate_assessment'),
                        (state.remediation_service, 'patch'), (state.remediation_service, 'derive'),
                        (state.assessment_service.store, 'get'), (state.remediation_service.store, 'get_version'),
                        (report_v2, '_render_json'), (report_v2, '_render_html')]:
        monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('socket.socket.connect', forbidden)
    for href, original in artifacts.items():
        assert env.client.get(href).content == original
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in env.data.glob('*.db')} == db_hashes


@pytest.mark.parametrize('variant', ['valid', 'hash', 'version', 'notice'])
def test_default_optional_sources(workflow, variant):
    from app.p1.report_v2_graph import graph_content_hash
    env = workflow
    response = env.client.get(f'/api/v1/scans/{env.run.id}/graph')
    assert response.status_code == 200, response.text
    graph = response.json()
    ref = {'kind': 'graph', 'version': graph['provenance']['algorithm_version'], 'content_hash': graph_content_hash(graph)}
    body = {'idempotency_key': variant, 'algorithm_refs': [ref]}
    if variant == 'hash':
        ref['content_hash'] = '0' * 64
    elif variant == 'version':
        ref['version'] = 'unavailable/999'
    elif variant == 'notice':
        body['notice_refs'] = [{'draft_id': 'ntc_unavailable', 'content_hash': 'a' * 64}]
    response = env.client.post(env.base + '/report-v2', json=body)
    if variant != 'valid':
        assert response.status_code == 409, response.text
        error = response.json()['error']
        assert error['code'] == ('conflict' if variant == 'hash' else 'not_ready')
        assert error['details']['reason'] == {'hash': 'graph_content_hash_mismatch', 'version': 'graph_algorithm_version_unavailable',
                                             'notice': 'notice_snapshot_reader_not_available'}[variant]
    else:
        assert response.status_code == 200, response.text
        snapshot = response.json()
        document = env.client.get(next(a['href'] for a in snapshot['artifacts'] if a['format'] == 'json')).json()
        section, = [s for s in document['sections'] if s['authority'] == 'observation']
        assert graph_content_hash(section['content']) == ref['content_hash']
        assert snapshot['binding']['algorithm_refs'] == [ref]


def test_default_restart_keeps_saved_artifacts(workflow):
    env = workflow
    snapshot = env.client.post(env.base + '/report-v2', json={'idempotency_key': 'restart'}).json()
    artifacts = {a['href']: env.client.get(a['href']).content for a in snapshot['artifacts']}
    with TestClient(main.create_default_app()) as restarted:
        for href, data in artifacts.items():
            response = restarted.get(href)
            assert response.status_code == 200
            assert response.content == data
