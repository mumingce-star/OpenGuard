"""A06 HTTP tests using temporary stores; no live server or production database."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.report_v2 import PREFIX, ReportV2CreateRequest
from test_p1_contract_schema import validator
from test_p1_report_v2_service import report_env


@pytest.fixture
def http_env(report_env, monkeypatch):
    env = report_env
    monkeypatch.setenv("OPENGUARD_WEB_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080")
    # Deliberately leave assessment_service unset: report writes must still be protected.
    app = create_app(env.registry, report_v2_service=env.service)
    with TestClient(app) as client:
        yield SimpleNamespace(env=env, app=app, client=client,
                              base=f"/api/v1/scans/{env.run.id}/assessments/{env.assessment.id}/report-v2")


def create(http, key="http-report", **changes):
    body = {"idempotency_key": key}
    body.update(changes)
    return http.client.post(http.base, json=body)


def report_hash(http):
    return hashlib.sha256(http.env.report_store.path.read_bytes()).hexdigest()


def error(response, expected_status, code, reason=None):
    assert response.status_code == expected_status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    assert body["request_id"] == response.headers["x-request-id"]
    if reason is not None:
        assert body["details"]["reason"] == reason


def test_http_create_replay_and_download(http_env):
    http = http_env
    response = create(http)
    assert response.status_code == 200, response.text
    snapshot = response.json()
    validator("ReportV2Snapshot").validate(snapshot)
    assert create(http).json() == snapshot
    for meta in snapshot["artifacts"]:
        downloaded = http.client.get(meta["href"])
        assert downloaded.status_code == 200, downloaded.text
        assert len(downloaded.content) == meta["size_bytes"]
        assert hashlib.sha256(downloaded.content).hexdigest() == meta["content_hash"]
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert "attachment;" in downloaded.headers["content-disposition"]
        assert "Content-Security-Policy" in downloaded.headers
        assert "sha-256=:" in downloaded.headers["content-digest"]
    saved = http.client.get(f'{http.base}/{snapshot["snapshot_id"]}?format=json')
    document = saved.json()
    assert document["snapshot_id"] == snapshot["snapshot_id"]
    assert document["binding"] == snapshot["binding"]
    assert all("content" in section for section in document["sections"])


@pytest.mark.parametrize("body", [
    {}, {"idempotency_key": None}, {"idempotency_key": "   "},
    {"idempotency_key": "x", "latest": True},
    {"idempotency_key": "x", "task_refs": None},
    {"idempotency_key": "x", "task_refs": [{"task_id": "tsk_x", "version": True}]},
    {"idempotency_key": "x", "task_refs": [{"task_id": "tsk_x", "version": "1"}]},
    {"idempotency_key": "x", "task_refs": [{"task_id": "tsk_x", "version": 0}]},
    {"idempotency_key": "x", "task_refs": [{"task_id": "tsk_x", "version": 1}] * 2},
])
def test_invalid_body_is_400_without_write(http_env, body):
    http = http_env
    before = report_hash(http)
    error(http.client.post(http.base, json=body), 400, "invalid_argument", "request_invalid")
    assert report_hash(http) == before


def test_malformed_json_is_400_without_write(http_env):
    http = http_env
    before = report_hash(http)
    response = http.client.post(http.base, content=b'{"idempotency_key":',
                                headers={"content-type": "application/json"})
    error(response, 400, "invalid_argument", "request_invalid")
    assert report_hash(http) == before


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded"])
def test_non_json_is_400_without_write(http_env, content_type):
    http = http_env
    before = report_hash(http)
    response = http.client.post(http.base, content=b'{}', headers={"content-type": content_type})
    error(response, 400, "invalid_argument", "request_invalid")
    assert report_hash(http) == before


@pytest.mark.parametrize("headers", [{"origin": "https://evil.example"}, {"sec-fetch-site": "cross-site"}])
def test_cross_site_is_403_without_write(http_env, headers):
    http = http_env
    before = report_hash(http)
    response = http.client.post(http.base, json={"idempotency_key": "x"}, headers=headers)
    error(response, 403, "origin_rejected")
    assert report_hash(http) == before


def test_exact_16k_body_is_accepted(http_env):
    http = http_env
    body = b'{"idempotency_key":"exact-boundary"}'
    body += b' ' * (16384 - len(body))
    response = http.client.post(http.base, content=body, headers={"content-type": "application/json"})
    assert response.status_code == 200, response.text


def test_streamed_body_over_16k_is_413_without_write(http_env):
    http = http_env
    before = report_hash(http)
    def chunks():
        yield b'{"idempotency_key":"too-large"}'
        yield b' ' * 16384
    response = http.client.post(http.base, content=chunks(), headers={"content-type": "application/json"})
    error(response, 413, "request_too_large")
    assert report_hash(http) == before


@pytest.mark.parametrize("query", ["format=pdf", "format=json&format=html", "latest=true"])
def test_invalid_get_query_is_400(http_env, query):
    http = http_env
    snapshot = create(http).json()
    before = report_hash(http)
    response = http.client.get(f'{http.base}/{snapshot["snapshot_id"]}?{query}')
    error(response, 400, "invalid_argument", "request_invalid")
    assert report_hash(http) == before


def test_get_uses_saved_bytes_without_source_reads(http_env, monkeypatch):
    http = http_env
    snapshot = create(http).json()
    url = f'{http.base}/{snapshot["snapshot_id"]}?format=json'
    original = http.client.get(url).content
    before = report_hash(http)
    def forbidden(*args, **kwargs):
        raise AssertionError("GET must not reload source stores or create reports")
    for owner, name in [(http.env.registry, "get"), (http.env.assessment_store, "get"),
                        (http.env.assessment_store, "latest"), (http.env.task_store, "history"),
                        (http.env.service, "create")]:
        monkeypatch.setattr(owner, name, forbidden)
    response = http.client.get(url, headers={"origin": "https://external.example"})
    assert response.status_code == 200, response.text
    assert response.content == original
    assert report_hash(http) == before


def test_missing_report_and_cross_assessment_are_404(http_env):
    http = http_env
    snapshot = create(http).json()
    error(http.client.get(f'{http.base}/rptv2_missing?format=json'), 404, "not_found")
    other = http.base.replace(http.env.assessment.id, "asm_other")
    error(http.client.get(f'{other}/{snapshot["snapshot_id"]}?format=json'), 404, "not_found")


def test_changed_task_set_with_same_key_is_409(http_env):
    http = http_env
    assert create(http).status_code == 200
    before = report_hash(http)
    response = create(http, task_refs=[{"task_id": http.env.task.task_id, "version": 1}])
    error(response, 409, "conflict", "idempotency_conflict")
    assert report_hash(http) == before


@pytest.mark.parametrize("field,refs,reason", [
    ("notice_refs", [{"draft_id": "ntc_unwired", "content_hash": "a" * 64}], "notice_snapshot_reader_not_available"),
    ("algorithm_refs", [{"kind": "graph", "version": "1.0", "content_hash": "b" * 64}], "observation_snapshot_reader_not_available"),
])
def test_unwired_optional_sources_are_explicitly_409(http_env, field, refs, reason):
    http = http_env
    before = report_hash(http)
    error(create(http, **{field: refs}), 409, "not_ready", reason)
    assert report_hash(http) == before


def test_unconfigured_report_service_does_not_initialize_store(http_env, monkeypatch):
    http = http_env
    def forbidden(*args, **kwargs):
        raise AssertionError("factory must not initialize the report store")
    monkeypatch.setattr(http.env.report_store.__class__, "initialize", forbidden)
    before = report_hash(http)
    with TestClient(create_app(http.env.registry)) as client:
        error(client.post(http.base, json={"idempotency_key": "disabled"}), 503, "feature_disabled")
        error(client.get(f'{http.base}/rptv2_missing'), 503, "feature_disabled")
    assert report_hash(http) == before


def test_p0_invalid_scan_stays_422(http_env):
    error(http_env.client.post('/api/v1/scans', json={}), 422, "invalid_source")


def test_openapi_publishes_post_get_and_request_contract(http_env):
    paths = http_env.client.get('/openapi.json').json()['paths']
    assert set(paths[PREFIX]) == {'post'}
    assert set(paths[PREFIX + '/{snapshot_id}']) == {'get'}
    schema = ReportV2CreateRequest.model_json_schema()
    assert schema['additionalProperties'] is False
    assert schema['required'] == ['idempotency_key']
    assert '400' in paths[PREFIX]['post']['responses']
