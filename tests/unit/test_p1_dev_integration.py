"""Dev-only wiring exercised through real P1 services and synthetic SQLite stores."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import dev_integration as dev
from app.api.models import ErrorEnvelope
from app.assessment.engine import facts_digest
from app.p1.report_v2_graph import graph_content_hash

ORIGIN = 'http://127.0.0.1:15174'


def database_hashes(root):
    # SHM read marks and empty WAL files are connection-lifecycle state, not data.
    # Include any nonempty WAL so pending durable writes remain detectable.
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.glob('*.db*') if p.is_file()
            and (p.name.endswith('.db') or
                 (p.name.endswith('.db-wal') and p.stat().st_size > 0))}


@pytest.fixture
def dev_space(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENGUARD_WEB_ORIGINS', ORIGIN)
    repository = tmp_path / 'repository'
    parent = repository / 'output' / 'manual-fixes'
    parent.mkdir(parents=True, mode=0o700)
    (repository / 'examples').mkdir()
    (repository / 'examples/sample-scan-result.json').write_bytes(
        (Path(__file__).resolve().parents[2] / 'examples/sample-scan-result.json').read_bytes())
    root = parent / 'p1-dev-fixture'
    manifest = dev.initialize(root, repository_root=repository).to_dict()
    return SimpleNamespace(root=root, repository=repository, manifest=manifest)


@pytest.fixture
def dev_http(dev_space):
    env = dev_space
    app = dev.create_dev_app(env.root, origins=(ORIGIN,), repository_root=env.repository)
    with TestClient(app) as client:
        env.app, env.client = app, client
        env.scan_id = env.manifest['scans']['completed_target']
        env.assessment = env.manifest['assessments'][env.scan_id]
        env.prefix = f'/api/v1/scans/{env.scan_id}/assessments/{env.assessment["assessment_id"]}'
        yield env


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    payload = response.json()['error']
    assert payload['code'] == code
    assert payload['request_id'] == response.headers['x-request-id']
    return payload


def derive(env, key='dev-test-derive'):
    response = env.client.post(env.prefix + '/remediation-tasks/derive',
        headers={'origin': ORIGIN}, json={'idempotency_key': key,
        'expected_facts_hash': env.assessment['facts_hash']})
    assert response.status_code == 200, response.text
    assert response.json()['items']
    return response.json()


def create_report(env, key='dev-test-report', **changes):
    body = {'idempotency_key': key, 'task_refs': [], 'algorithm_refs': [], 'notice_refs': []}
    body.update(changes)
    response = env.client.post(env.prefix + '/report-v2', headers={'origin': ORIGIN}, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_seed_is_explicit_private_and_contains_comparable_fixed_records(dev_space):
    env = dev_space
    manifest = dev.read_manifest(env.root, repository_root=env.repository).to_dict()
    assert manifest == env.manifest
    assert manifest['synthetic'] is True
    assert manifest['seed_version'] == dev.SEED_VERSION
    assert manifest['root_id']
    assert len(set(manifest['scans'].values())) == 3
    assert set(manifest['scans']) == {'completed_base', 'completed_target', 'partial'}
    assert manifest['comparisons'] == {
        'base_scan_id': manifest['scans']['completed_base'],
        'target_scan_id': manifest['scans']['completed_target']}
    assert env.root.stat().st_mode & 0o777 == 0o700
    for name in ('scans.db', 'assessment.db', 'remediation.db', 'report_v2.db'):
        assert (env.root / name).stat().st_mode & 0o777 == 0o600


def test_history_diff_fixed_assessment_and_partial_graph(dev_http):
    env = dev_http
    rows = env.client.get('/api/v1/scans').json()['items']
    assert {row['scan_id'] for row in rows} == set(env.manifest['scans'].values())
    response = env.client.get(f'/api/v1/scans/{env.scan_id}/diff',
                             params={'base_scan_id': env.manifest['comparisons']['base_scan_id']})
    assert response.status_code == 200, response.text
    fixed = env.client.get(env.prefix)
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()['id'] == env.assessment['assessment_id']
    assert fixed.json()['facts_hash'] == env.assessment['facts_hash']
    assert fixed.json()['formal'] is True
    run = env.app.state.assessment_service.registry.get(env.scan_id).run
    assert facts_digest(run) == env.assessment['facts_hash']
    for name, sid in env.manifest['scans'].items():
        status = env.client.get(f'/api/v1/scans/{sid}').json()
        assert status['status'] == ('partial' if name == 'partial' else 'completed')
        response = env.client.get(f'/api/v1/scans/{sid}/graph')
        assert response.status_code == 200, response.text
        graph = response.json()
        assert graph['nodes'] and graph['edges']
        assert graph['coverage']['view_complete'] is True
        assert bool(graph['coverage']['scan_gaps']) == (name == 'partial')
        ids = {node['id'] for node in graph['nodes']}
        assert all(edge['source'] in ids and edge['target'] in ids for edge in graph['edges'])
        assert graph_content_hash(graph) == env.manifest['graph_refs'][sid]['content_hash']
    filtered = env.client.get(f'/api/v1/scans/{env.scan_id}/graph',
                             params={'resource_ids': run.components[0].id})
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()['coverage']['scope'] == 'filtered'
    assert_error(env.client.get(f'/api/v1/scans/{env.scan_id}/diff',
                 params={'base_scan_id': env.scan_id}), 400, 'invalid_argument')


def test_graph_capacity_uses_actual_reader_limit(dev_http):
    env = dev_http
    env.app.state.p1_graph_max_nodes = 1
    assert_error(env.client.get(f'/api/v1/scans/{env.scan_id}/graph'),
                 413, 'graph_capacity_exceeded')


def test_task_report_replay_bytes_and_restart_persistence(dev_http):
    env = dev_http
    source_before = {k: v for k, v in database_hashes(env.root).items()
                     if k.startswith(('scans.db', 'assessment.db'))}
    collection = derive(env)
    assert derive(env) == collection
    task = collection['items'][0]
    path = env.prefix + '/remediation-tasks/' + task['task_id']
    response = env.client.patch(path, headers={'origin': ORIGIN},
        json={'expected_version': task['version'], 'status': 'in_progress'})
    assert response.status_code == 200, response.text
    active = response.json()
    assert active['version'] == task['version'] + 1
    assert_error(env.client.patch(path, json={'expected_version': task['version'], 'note': 'stale'}),
                 409, 'conflict')
    response = env.client.patch(path, headers={'origin': ORIGIN}, json={
        'expected_version': active['version'], 'status': 'done', 'note': '  合成联调人工记录  '})
    assert response.status_code == 200, response.text
    done = response.json()
    assert done['note'] == '  合成联调人工记录  '
    refs = [{'task_id': done['task_id'], 'version': done['version']}]
    report = create_report(env, task_refs=refs)
    assert create_report(env, task_refs=refs) == report
    saved = {}
    for artifact in report['artifacts']:
        response = env.client.get(artifact['href'])
        assert response.status_code == 200, response.text
        assert hashlib.sha256(response.content).hexdigest() == artifact['content_hash']
        assert len(response.content) == artifact['size_bytes']
        saved[artifact['href']] = response.content
    document = env.client.get(env.prefix + '/report-v2/' + report['snapshot_id'] + '?format=json').json()
    assert document['binding'] == report['binding']
    assert all('content' in section for section in document['sections'])
    assert all('content' not in section for section in report['sections'])
    assert env.client.patch(path, json={'expected_version': done['version'],
        'note': '新的合成备注，不改变原报告'}).status_code == 200
    assert {url: env.client.get(url).content for url in saved} == saved
    assert {k: v for k, v in database_hashes(env.root).items()
            if k.startswith(('scans.db', 'assessment.db'))} == source_before
    # A second independent factory over the same data is a restart-read check;
    # process exclusivity belongs to the launcher, not TestClient.
    with TestClient(dev.create_dev_app(env.root, origins=(ORIGIN,),
                                      repository_root=env.repository)) as restarted:
        assert {url: restarted.get(url).content for url in saved} == saved
        rows = restarted.get(env.prefix + '/remediation-tasks').json()['items']
        assert next(row for row in rows if row['task_id'] == task['task_id'])['note'].startswith('新的')


def test_full_graph_in_report_and_reference_tampering(dev_http):
    env = dev_http
    ref = env.manifest['graph_refs'][env.scan_id]
    report = create_report(env, 'graph-good', algorithm_refs=[ref])
    doc = env.client.get(env.prefix + '/report-v2/' + report['snapshot_id'] + '?format=json').json()
    observations = [s for s in doc['sections'] if s['authority'] == 'observation']
    assert len(observations) == 1
    assert report['binding']['algorithm_refs'] == [ref]
    for key, value, code in [('content_hash', '0' * 64, 'conflict'),
                             ('version', 'unavailable', 'not_ready')]:
        altered = dict(ref, **{key: value})
        assert_error(env.client.post(env.prefix + '/report-v2', json={
            'idempotency_key': 'bad-' + key, 'algorithm_refs': [altered]}), 409, code)
    env.app.state.report_v2_service.graph_reader = None
    assert_error(env.client.post(env.prefix + '/report-v2', json={
        'idempotency_key': 'no-reader', 'algorithm_refs': [ref]}), 409, 'not_ready')


def test_notice_profile_not_faked(dev_http):
    env = dev_http
    assert_error(env.client.post(env.prefix + '/report-v2', json={
        'idempotency_key': 'notice', 'notice_refs': [{'draft_id': 'ntc_unavailable', 'content_hash': 'a' * 64}]}),
        409, 'not_ready')
    assert_error(env.client.post(env.prefix + '/report-v2', json={
        'idempotency_key': 'profile', 'algorithm_refs': [{'kind': 'profile', 'version': '1.0', 'content_hash': 'a' * 64}]}),
        409, 'not_ready')
