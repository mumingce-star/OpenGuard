"""NoticeDraft permanent HTTP and frozen route boundary tests."""
import importlib

import pytest
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.persistence import SQLiteScanRunRegistry
from test_p1_notice_draft_backend import notice_env, hashes
from test_p1_contract_schema import validator


@pytest.mark.parametrize('module,name', [
    ('app.p1.models', 'P1NoticeDraft'),
    ('app.p1.notice_draft_store', 'NoticeDraftStore'),
    ('app.p1.notice_draft', 'NoticeDraftService'),
])
def test_notice_product_boundary_exists(module, name):
    assert getattr(importlib.import_module(module), name)


def test_notice_routes_public_but_default_disabled(tmp_path):
    registry = SQLiteScanRunRegistry(tmp_path / 'scans.db')
    app = create_app(registry)
    base = '/api/v1/scans/scn_missing/assessments/asm_missing/notice-drafts'
    with TestClient(app) as client:
        response = client.get(base + '/ntc_missing')
        assert response.status_code == 404, response.text
        assert response.json()['error']['code'] == 'not_found'
        response = client.post(base, json={'idempotency_key': 'x'})
        assert response.status_code == 503
        paths = client.get('/openapi.json').json()['paths']
        prefix = '/api/v1/scans/{scan_id}/assessments/{assessment_id}/notice-drafts'
        assert set(paths[prefix]) == {'post'}
        assert set(paths[prefix + '/{draft_id}']) == {'get'}
    assert not list(tmp_path.glob('notice*'))
    registry.close()


@pytest.fixture
def notice_http(notice_env):
    env = notice_env
    app = create_app(env.registry, notice_draft_service=env.service)
    with TestClient(app) as client:
        yield client, f'/api/v1/scans/{env.run.id}/assessments/{env.assessment.id}/notice-drafts', env


def test_http_saved_bytes_no_get_side_effects(notice_http, monkeypatch):
    client, base, env = notice_http
    def forbidden(*a, **kw):
        raise AssertionError('unexpected dependency call')
    import socket
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    response = client.post(base, json={'idempotency_key':'http-create'})
    assert response.status_code == 200, response.text
    snapshot = response.json()
    validator('NoticeDraft').validate(snapshot)
    assert client.post(base, json={'idempotency_key':'http-create'}).json() == snapshot
    before = hashes(env)
    for obj, attr in ((env.registry, 'get'), (env.store, 'get'), (env.reader, 'read'), (env.notice_store, 'create'), (env.notice_store, 'initialize')):
        monkeypatch.setattr(obj, attr, forbidden)
    responses = [client.get(base + '/' + snapshot['draft_id']) for _ in range(5)]
    assert all(r.status_code == 200 and r.json() == snapshot for r in responses)
    assert len({r.content for r in responses}) == 1
    assert hashes(env) == before


@pytest.mark.parametrize('body', [{}, {'idempotency_key':None}, {'idempotency_key':True},
    {'idempotency_key':' '}, {'idempotency_key':'x'*201}, {'idempotency_key':'x','path':'/tmp/x'},
    {'idempotency_key':'x','url':'https://example.org'}, {'idempotency_key':'x','latest':True}])
def test_invalid_post_body_no_write(notice_http, body):
    client, base, env = notice_http
    before = hashes(env)
    response = client.post(base, json=body)
    assert response.status_code == 400, response.text
    assert response.json()['error']['code'] == 'invalid_argument'
    assert hashes(env) == before and env.reader.calls == 0


@pytest.mark.parametrize('headers,status', [({'origin':'https://evil.example'},403),
    ({'sec-fetch-site':'cross-site'},403), ({'content-type':'text/plain'},400)])
def test_write_security(notice_http, headers, status):
    client, base, env = notice_http
    before = hashes(env)
    response = client.post(base, content='{"idempotency_key":"write"}', headers={'content-type':'application/json',**headers})
    assert response.status_code == status, response.text
    assert hashes(env) == before and env.reader.calls == 0


def test_exact_body_limit_and_oversize(notice_http):
    client, base, env = notice_http
    raw = b'{"idempotency_key":"limit"}'
    raw += b' '*(16384-len(raw))
    assert client.post(base, content=raw, headers={'content-type':'application/json'}).status_code == 200
    before = hashes(env)
    assert client.post(base, content=raw+b' ', headers={'content-type':'application/json'}).status_code == 413
    assert hashes(env) == before


def test_malformed_query_and_missing(notice_http):
    client, base, env = notice_http
    assert client.post(base, content=b'{', headers={'content-type':'application/json'}).status_code == 400
    assert client.get(base+'/ntc_missing').status_code == 404
    assert client.get(base+'/ntc_missing?latest=true').status_code == 400
    assert client.post(base+'?source=x', json={'idempotency_key':'x'}).status_code == 400


def test_owner_r1_malformed_scan_id_is_400_without_reader_or_write(notice_http, monkeypatch):
    client, base, env = notice_http
    before = hashes(env)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('facts reader must not be called')
    monkeypatch.setattr(env.reader, 'read', forbidden)
    response = client.post(base.replace(env.run.id, 'malformed-scan-id'),
                           json={'idempotency_key':'invalid-scan'})
    assert response.status_code == 400, response.text
    error = response.json()['error']
    assert error['code'] == 'invalid_argument'
    assert error['details']['reason'] == 'scan_id_invalid'
    assert not calls and hashes(env) == before
