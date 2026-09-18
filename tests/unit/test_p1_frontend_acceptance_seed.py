"""Synthetic facts exercise real registry, services and FastAPI, never fake DTOs."""
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def seed(tmp_path, monkeypatch):
    from app.frontend_acceptance import initialize, create_acceptance_app
    root = tmp_path / 'output/manual-fixes/p1-frontend-acceptance-test'
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS', 'http://127.0.0.1:15174')
    manifest = initialize(root, repository_root=tmp_path, code_version='synthetic-test')
    with TestClient(create_acceptance_app(root, repository_root=tmp_path,
                        origins=('http://127.0.0.1:15174',))) as client:
        yield root, manifest, client


def test_history_205_real_cursor(seed):
    _, manifest, client = seed
    page = client.get('/api/v1/scans?limit=20').json()
    assert len(page['items']) == 20 and page['next_cursor']
    ids = []
    cursor = None
    while True:
        params = {'limit': 100}
        if cursor:
            params['cursor'] = cursor
        page = client.get('/api/v1/scans', params=params).json()
        ids += [r['scan_id'] for r in page['items']]
        cursor = page['next_cursor']
        if not cursor:
            break
    assert len(ids) == len(set(ids)) == manifest['history']['count'] == 205


@pytest.mark.parametrize('tier', [100, 300, 500])
def test_graph_exact_actual_projection(seed, tier):
    _, manifest, client = seed
    row = manifest['graphs'][str(tier)]
    response = client.get(row['href'])
    assert response.status_code == 200
    graph = response.json()
    ids = {n['id'] for n in graph['nodes']}
    assert len(ids) == len(graph['nodes']) == tier
    assert len({e['id'] for e in graph['edges']}) == len(graph['edges'])
    assert all(e['source'] in ids and e['target'] in ids for e in graph['edges'])


def test_manifest_synthetic_and_unsupported(seed):
    root, manifest, client = seed
    assert manifest['synthetic'] is True
    assert manifest['seed_version'] == 'p1-frontend-acceptance/1'
    assert json.loads((root / 'frontend-acceptance-manifest.json').read_text()) == manifest
    for value in manifest['unsupported'].values():
        assert value['status'] == 'not_available_on_current_baseline'
        assert client.get(value['href']).status_code == 404


def test_tasks_obligation_and_reports_repeat_prepare(seed):
    from app.frontend_acceptance import prepare
    root, manifest, client = seed
    tasks = client.get(manifest['tasks']['populated']['href']).json()['items']
    assert 'obligation' in {t['origin']['kind'] for t in tasks}
    assert len({t['origin']['kind'] for t in tasks}) > 1
    assert any(t['resource_ids'] and t['evidence_refs'] for t in tasks)
    assert all(t['status'] == 'todo' for t in tasks)
    assert len(manifest['reports']) == 4
    repeated = prepare(root, repository_root=root.parents[2])
    assert repeated['reports'] == manifest['reports']
    for report in manifest['reports'].values():
        for artifact in report['artifacts']:
            assert client.get(artifact['href']).status_code == 200


def test_get_logical_state_unchanged(seed):
    from app.frontend_acceptance import logical_state
    root, manifest, client = seed
    before = logical_state(root, repository_root=root.parents[2])
    paths = ['/api/v1/scans']
    paths += [g['href'] for g in manifest['graphs'].values()]
    paths += [d['href'] for d in manifest['diff'].values()]
    paths += [t['href'] for t in manifest['tasks'].values()]
    paths += [a['href'] for r in manifest['reports'].values() for a in r['artifacts']]
    for path in paths:
        assert client.get(path).status_code == 200
    assert logical_state(root, repository_root=root.parents[2]) == before


def test_external_network_guard(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'deploy'))
    from p1_frontend_acceptance import network_guard
    for owner, attr in ((socket.socket,'connect'), (socket.socket,'connect_ex'), (socket,'getaddrinfo')):
        monkeypatch.setattr(owner, attr, getattr(owner, attr))
    attempts = network_guard()
    for method in ('connect', 'connect_ex'):
        with socket.socket() as sock, pytest.raises(ValueError, match='external network forbidden'):
            getattr(sock, method)(('203.0.113.10', 443))
    with pytest.raises(ValueError, match='external resolution forbidden'):
        socket.getaddrinfo('synthetic.invalid', 443)
    assert len(attempts) == 3


def test_full_http_semantics_and_cas_immutability(seed, monkeypatch):
    import hashlib
    from app.frontend_acceptance import logical_state
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'deploy'))
    from p1_frontend_acceptance import verify_http, prepare_http
    root, manifest, client = seed
    class Adapter:
        def call(self, method, path, body=None, expected=200):
            response = client.request(method, path, json=body,
                headers={'Origin':'http://127.0.0.1:15174'})
            assert response.status_code == expected, response.text
            return response.content
        def json(self, *args, **kwargs):
            return json.loads(self.call(*args, **kwargs))
    adapter = Adapter()
    prepare_http(adapter, manifest)
    before = logical_state(root, repository_root=root.parents[2])
    result = verify_http(adapter, manifest)
    assert result['history']['pages'] == [100,100,5]
    assert logical_state(root, repository_root=root.parents[2]) == before
    row = manifest['tasks']['populated']
    bound_id = manifest['reports']['task']['task_refs'][0]['task_id']
    task = next(t for t in adapter.json('GET', row['href'] + '?limit=100')['items'] if t['task_id'] == bound_id)
    path = row['href'] + '/' + task['task_id']
    active = adapter.json('PATCH', path, {'expected_version':1,'status':'in_progress'})
    adapter.json('PATCH', path, {'expected_version':1,'status':'done','note':'stale'},409)
    adapter.json('PATCH', path, {'expected_version':active['version'],'status':'done','note':'Synthetic only'})
    for report in manifest['reports'].values():
        for artifact in report['artifacts']:
            assert hashlib.sha256(adapter.call('GET', artifact['href'])).hexdigest() == artifact['content_hash']
    after = logical_state(root, repository_root=root.parents[2])
    for name in ('scans.db','assessment.db','report_v2.db'):
        assert before[name] == after[name]


def test_task_sources_resolve_and_hash(seed):
    from app.p1.remediation import digest
    _, manifest, client = seed
    row = manifest['tasks']['populated']
    assessment = client.get(manifest['assessments'][row['scan_id']]['href']).json()
    for task in client.get(row['href'] + '?limit=100').json()['items']:
        value = assessment
        for part in task['origin']['source_pointer'].strip('/').split('/'):
            key = part.replace('~1','/').replace('~0','~')
            value = value[int(key)] if isinstance(value,list) else value[key]
        assert digest(value) == task['origin']['source_hash']
        assert set(task['resource_ids']) <= set(assessment['resource_ids'])
        assert all(e['evidence_id'] in assessment['evidence_ids'] for e in task['evidence_refs'])


def test_capacity_error_without_changing_product_default(seed):
    from app.p1.graph import GraphReader, GraphCapacityError
    _, manifest, client = seed
    registry = client.app.state.assessment_service.registry
    # A small test-only reader budget exercises refusal, never changes API capacity.
    with pytest.raises(GraphCapacityError) as error:
        GraphReader(registry, max_nodes=99).read(manifest['graphs']['100']['scan_id'],[],[])
    assert error.value.capacity_details['node_count'] == 100
    assert error.value.capacity_details['configured_capacity']['max_nodes'] == 99
