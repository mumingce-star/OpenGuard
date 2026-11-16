"""Independent A05 boundary, concurrency and immutable-facts acceptance tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from threading import Barrier

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_p1_remediation_api import (  # noqa: E402,F401
    task_env, base, derive, tasks, patch, check_error,
)
from test_p1_diff_api import assessment  # noqa: E402
from app.p1.remediation import RemediationService  # noqa: E402
from app.p1.remediation_store import RemediationTaskStore, RemediationStoreError  # noqa: E402


def snapshot(path):
    """Capture all sidecar bytes, including journals, without opening SQLite."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.parent.glob(path.name + '*') if p.is_file()}


@pytest.mark.parametrize('headers', [
    {'origin': 'https://attacker.example'},
    {'origin': 'null'},
    {'origin': 'http://localhost:8080.attacker.example'},
    {'sec-fetch-site': 'cross-site'},
    {'origin': 'http://127.0.0.1:8080', 'sec-fetch-site': 'cross-site'},
])
def test_patch_origin_boundary_without_assessment_service(task_env, headers):
    env = task_env
    assert env.app.state.assessment_service is None
    task = tasks(env)[0]
    before = snapshot(env.tasks.path)
    response = env.client.patch(base(env) + '/' + task['task_id'], headers=headers,
                               json={'status': 'done', 'note': 'verified', 'expected_version': 1})
    check_error(response, 403, 'origin_rejected')
    assert snapshot(env.tasks.path) == before
    assert len(env.tasks.history(task['task_id'])) == 1


@pytest.mark.parametrize('content_type', ['', 'text/plain', 'application/x-www-form-urlencoded'])
def test_patch_requires_json_without_assessment_service(task_env, content_type):
    env = task_env
    task = tasks(env)[0]
    before = snapshot(env.tasks.path)
    response = env.client.patch(base(env) + '/' + task['task_id'],
                               headers={'content-type': content_type},
                               content=json.dumps({'status': 'in_progress', 'expected_version': 1}))
    check_error(response, 400, 'request_invalid')
    assert response.json()['error']['code'] == 'invalid_argument'
    assert snapshot(env.tasks.path) == before


@pytest.mark.parametrize('size,expected_status', [(16384, 200), (16385, 413)])
def test_patch_actual_body_byte_limit(task_env, size, expected_status):
    env = task_env
    task = tasks(env)[0]
    body = json.dumps({'status': 'in_progress', 'expected_version': 1}).encode()
    body += b' ' * (size - len(body))
    assert len(body) == size
    before = snapshot(env.tasks.path)
    # Iteration exercises streamed bodies; Content-Length is not trusted.
    response = env.client.patch(base(env) + '/' + task['task_id'],
                               headers={'content-type': 'application/json; charset=utf-8',
                                        'origin': 'http://localhost:8080'},
                               content=iter([body[:100], body[100:]]))
    assert response.status_code == expected_status, response.text
    if expected_status == 413:
        check_error(response, 413, 'request_too_large')
        assert snapshot(env.tasks.path) == before
        assert len(env.tasks.history(task['task_id'])) == 1
    else:
        assert response.json()['version'] == 2


def test_cross_site_get_remains_readonly(task_env):
    env = task_env
    initial = tasks(env)
    before = snapshot(env.tasks.path)
    response = env.client.get(base(env), params={'limit': 100},
                              headers={'origin': 'https://attacker.example',
                                       'sec-fetch-site': 'cross-site', 'content-type': 'text/plain'})
    assert response.status_code == 200, response.text
    assert {t['task_id'] for t in response.json()['items']} == {t['task_id'] for t in initial}
    assert snapshot(env.tasks.path) == before


def test_derive_and_get_cannot_invoke_live_or_implicit_sources(task_env, monkeypatch):
    env = task_env
    def forbidden(*args, **kwargs):
        pytest.fail('A05 called a scanner, AI, process, socket, or implicit Assessment source')
    for target in [
        'app.ai.ollama.OllamaProvider.generate',
        'app.ai.ollama.OllamaProvider.generate_project',
        'app.scanners.scancode_pipeline.scan_sealed_tree',
        'app.scanners.syft_pipeline.scan_sealed_tree',
        'subprocess.Popen', 'socket.socket.connect', 'socket.create_connection',
    ]:
        monkeypatch.setattr(target, forbidden)
    monkeypatch.setattr(env.store, 'latest', forbidden)
    monkeypatch.setattr(env.store, 'create', forbidden)
    monkeypatch.setattr(env.tasks, 'initialize', forbidden)
    # Even list/latest-formal selection is forbidden during explicit derivation.
    with monkeypatch.context() as local:
        local.setattr(env.store, 'list', forbidden)
        values = tasks(env)
    assert values
    assert env.client.get(base(env)).status_code == 200


def test_done_preserves_entire_formal_and_scan_storage(task_env):
    env = task_env
    task = tasks(env)[0]
    before = (snapshot(env.store.path), snapshot(env.path / 'scans.db'))
    formal = env.store.get_by_id(env.assessment.id).model_dump(mode='json')
    note = '  人工记录\n不代表许可证、证据或义务事实改变  '
    response = patch(env, task, status='done', note=note)
    assert response.status_code == 200, response.text
    assert response.json()['note'] == note
    after = env.store.get_by_id(env.assessment.id).model_dump(mode='json')
    assert after == formal
    assert after['obligations'] == formal['obligations']
    assert (snapshot(env.store.path), snapshot(env.path / 'scans.db')) == before


def test_two_independent_store_connections_cas_one_winner(task_env):
    env = task_env
    task = tasks(env)[0]
    barrier = Barrier(2)
    def attempt(note):
        store = RemediationTaskStore(env.tasks.path, min_free_bytes=0)
        barrier.wait(timeout=5)
        try:
            value = store.patch(env.run.id, env.assessment.id, task['task_id'], 1,
                                {'status': 'in_progress', 'note': note})
            return ('success', value)
        except RemediationStoreError as error:
            return (error.code, None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, note) for note in ['client A', 'client B']]
        results = [f.result(timeout=10) for f in futures]
    assert sorted(kind for kind, _ in results) == ['stale_version', 'success']
    winner = next(value for kind, value in results if kind == 'success')
    assert winner['version'] == 2
    history = env.tasks.history(task['task_id'])
    assert [row['version'] for row in history] == [1, 2]
    assert history[0] == task and history[1] == winner
    assert env.tasks.get(env.run.id, env.assessment.id, task['task_id']) == winner


def test_new_nonformal_does_not_supersede_latest_formal_tasks(task_env):
    env = task_env
    task = tasks(env)[0]
    done = patch(env, task, status='done', note='kept').json()
    assessment(env, env.run, version=2, mutate=lambda p: p.update(formal=False))
    before = snapshot(env.tasks.path)
    page = env.client.get(base(env), params={'limit': 100}).json()['items']
    assert all(t['superseded'] is False for t in page)
    assert next(t for t in page if t['task_id'] == task['task_id']) == done
    assessment(env, env.run, version=3)
    assessment(env, env.run, version=4, mutate=lambda p: p.update(formal=False))
    page = env.client.get(base(env), params={'limit': 100}).json()['items']
    old = next(t for t in page if t['task_id'] == task['task_id'])
    assert old == dict(done, superseded=True)
    assert snapshot(env.tasks.path) == before
    assert [t['status'] for t in env.tasks.history(task['task_id'])] == ['todo', 'done']


def test_missing_store_get_and_derive_never_initialize(task_env, monkeypatch):
    env = task_env
    absent = RemediationTaskStore(env.path / 'never-created' / 'remediation.db', min_free_bytes=0)
    def forbidden(*args, **kwargs):
        pytest.fail('Request initialized remediation storage')
    monkeypatch.setattr(absent, 'initialize', forbidden)
    env.app.state.remediation_service = RemediationService(env.registry, env.store, absent)
    response = env.client.get(base(env))
    assert response.status_code == 200 and response.json()['items'] == []
    check_error(derive(env), 503, 'storage_unavailable')
    assert not absent.path.parent.exists()


def test_capacity_failure_rolls_back_and_reads_remain_available(task_env):
    env = task_env
    task = tasks(env)[0]
    env.tasks.max_database_bytes = env.tasks.path.stat().st_size
    before = snapshot(env.tasks.path)
    check_error(patch(env, task, status='in_progress'), 503, 'storage_capacity_exceeded')
    assert snapshot(env.tasks.path) == before
    assert env.tasks.history(task['task_id']) == [task]
    assert env.client.get(base(env)).status_code == 200
    # A replay adds no alias or audit row, even when growth is disallowed.
    replay = derive(env)
    assert replay.status_code == 200, replay.text
    assert snapshot(env.tasks.path) == before


def test_corrupt_task_is_rejected_without_repair_or_overwrite(task_env):
    env = task_env
    task = tasks(env)[0]
    with sqlite3.connect(env.tasks.path) as db:
        db.execute('UPDATE tasks SET payload_hash=? WHERE task_id=?', ('0' * 64, task['task_id']))
    before = snapshot(env.tasks.path)
    check_error(env.client.get(base(env)), 503, 'storage_unavailable')
    check_error(patch(env, task, status='in_progress'), 503, 'storage_unavailable')
    check_error(derive(env), 503, 'storage_unavailable')
    assert snapshot(env.tasks.path) == before
    assert env.tasks.history(task['task_id']) == [task]


def test_derive_cross_site_rejected_without_db_write(task_env):
    env=task_env; before=snapshot(env.tasks.path)
    response=env.client.post(base(env)+'/derive',
        headers={'origin':'https://attacker.example','sec-fetch-site':'cross-site'},
        json={'idempotency_key':'blocked-origin','expected_facts_hash':env.assessment.facts_hash})
    check_error(response,403,'origin_rejected')
    assert snapshot(env.tasks.path)==before
    assert env.client.get(base(env)).json()['items']==[]


def test_derive_actual_stream_over_limit_without_db_write(task_env):
    env=task_env; before=snapshot(env.tasks.path)
    body=json.dumps({'idempotency_key':'blocked-size','expected_facts_hash':env.assessment.facts_hash}).encode()
    body+=b' '*(16385-len(body))
    response=env.client.post(base(env)+'/derive',
        headers={'content-type':'application/json','origin':'http://localhost:8080'},
        content=iter([body[:100],body[100:]]))
    check_error(response,413,'request_too_large')
    assert snapshot(env.tasks.path)==before
    assert env.client.get(base(env)).json()['items']==[]


@pytest.mark.parametrize('content_type', ['text/plain', 'application/x-www-form-urlencoded'])
def test_derive_requires_json_without_assessment_service(task_env, content_type):
    env = task_env
    assert env.app.state.assessment_service is None
    before = snapshot(env.tasks.path)
    response = env.client.post(base(env) + '/derive',
        headers={'content-type': content_type},
        content=json.dumps({'idempotency_key': 'non-json',
                            'expected_facts_hash': env.assessment.facts_hash}))
    check_error(response, 400, 'request_invalid')
    assert response.json()['error']['code'] == 'invalid_argument'
    assert snapshot(env.tasks.path) == before
    assert env.client.get(base(env)).json()['items'] == []
