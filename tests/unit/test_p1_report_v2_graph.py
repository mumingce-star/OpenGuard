"""A06 optional graph inclusion: fixed sources, hashes and saved artifacts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.p1.graph import ALGORITHM, GraphReader
from app.p1.report_v2 import ReportV2Service
from app.p1.report_v2_graph import ReportGraphReader, graph_content_hash
from test_p1_contract_schema import validator
from test_p1_report_v2_service import report_env
from test_p1_history_api import seed
from test_p1_diff_api import assessment as make_assessment


@pytest.fixture
def graph_http(report_env, monkeypatch):
    env = report_env
    monkeypatch.setenv("OPENGUARD_WEB_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080")
    reader = ReportGraphReader()
    service = ReportV2Service(env.registry, env.assessment_store,
                             env.task_store, env.report_store, graph_reader=reader)
    app = create_app(env.registry, report_v2_service=service)
    reference, graph = reader.capture(env.registry.get(env.run.id))
    with TestClient(app) as client:
        yield SimpleNamespace(env=env, reader=reader, service=service, client=client,
                              reference=reference, graph=graph,
                              base=f"/api/v1/scans/{env.run.id}/assessments/{env.assessment.id}/report-v2")


def post(http, *, key="graph-report", refs=None):
    refs = [http.reference.model_dump(mode="json")] if refs is None else refs
    return http.client.post(http.base, json={"idempotency_key": key, "algorithm_refs": refs})


def db_hash(http):
    return hashlib.sha256(http.env.report_store.path.read_bytes()).hexdigest()


def error(response, status, code, reason):
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code
    assert body["details"]["reason"] == reason
    assert body["request_id"] == response.headers["x-request-id"]


def document(http, snapshot):
    response = http.client.get(f'{http.base}/{snapshot["snapshot_id"]}?format=json')
    assert response.status_code == 200, response.text
    return response.json()


def test_full_graph_is_saved_as_an_observation(graph_http):
    http = graph_http
    response = post(http)
    assert response.status_code == 200, response.text
    snapshot = response.json()
    validator("ReportV2Snapshot").validate(snapshot)
    assert snapshot["binding"]["algorithm_refs"] == [http.reference.model_dump(mode="json")]
    doc = document(http, snapshot)
    sections = [section for section in doc["sections"] if section["authority"] == "observation"]
    assert len(sections) == 1
    section, = sections
    saved = section["content"]
    validator("ResourceGraphView").validate(saved)
    assert saved["formal"] is False
    assert saved["scan_ref"] == doc["binding"]["scan_ref"]
    assert saved["filter"] == {"resource_ids": [], "resource_kinds": []}
    assert saved["coverage"]["scope"] == "all"
    assert saved["nodes"] == http.graph["nodes"]
    assert saved["edges"] == http.graph["edges"]
    assert graph_content_hash(saved) == http.reference.content_hash
    assert section["source_ids"] == [saved["view_id"]]
    content = json.dumps(saved, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert hashlib.sha256(content).hexdigest() == section["content_hash"]
    pointer = section["snapshot_ref"].split("#", 1)[1].split("/")[1:]
    value = doc
    for token in pointer:
        value = value[int(token)] if isinstance(value, list) else value[token]
    assert value == saved


def test_graph_semantic_hash_ignores_only_read_time(graph_http):
    original = graph_http.graph
    changed = deepcopy(original)
    changed["provenance"]["generated_at"] = "2030-01-01T00:00:00Z"
    assert graph_content_hash(original) == graph_content_hash(changed)
    changed["nodes"][0]["label"] += "changed"
    assert graph_content_hash(original) != graph_content_hash(changed)
    assert original["provenance"]["generated_at"] != "2030-01-01T00:00:00Z"


def test_graph_hash_normalizes_set_order_without_mutating_input(graph_http):
    original = graph_http.graph
    changed = deepcopy(original)
    changed["nodes"].reverse()
    changed["edges"].reverse()
    before = deepcopy(changed)
    assert graph_content_hash(original) == graph_content_hash(changed)
    assert changed == before


def test_graph_replay_keeps_first_bytes(graph_http, monkeypatch):
    http = graph_http
    first = post(http).json()
    before = {meta["format"]: http.client.get(meta["href"]).content for meta in first["artifacts"]}
    monkeypatch.setattr("app.p1.graph.utc", lambda _: "2030-01-01T00:00:00Z")
    second = post(http)
    assert second.status_code == 200, second.text
    assert second.json() == first
    assert before == {meta["format"]: http.client.get(meta["href"]).content for meta in first["artifacts"]}


def test_get_never_rebuilds_graph(graph_http, monkeypatch):
    http = graph_http
    snapshot = post(http).json()
    before = document(http, snapshot)
    def forbidden(*args, **kwargs):
        raise AssertionError("GET must not read graph or live source stores")
    monkeypatch.setattr(http.reader, "capture", forbidden)
    monkeypatch.setattr(GraphReader, "read", forbidden)
    monkeypatch.setattr(http.env.registry, "get", forbidden)
    assert document(http, snapshot) == before


@pytest.mark.parametrize("field,value,code,reason", [
    ("version", "resource-graph/unavailable", "not_ready", "graph_algorithm_version_unavailable"),
    ("content_hash", "0" * 64, "conflict", "graph_content_hash_mismatch"),
])
def test_graph_reference_mismatch_is_zero_write(graph_http, field, value, code, reason):
    http = graph_http
    ref = http.reference.model_dump(mode="json")
    ref[field] = value
    before = db_hash(http)
    error(post(http, refs=[ref]), 409, code, reason)
    assert db_hash(http) == before


def test_duplicate_graph_reference_is_zero_write(graph_http):
    http = graph_http
    ref = http.reference.model_dump(mode="json")
    before = db_hash(http)
    error(post(http, refs=[ref, ref]), 400, "invalid_argument", "duplicate_algorithm_ref")
    assert db_hash(http) == before


def test_profile_remains_unwired(graph_http):
    http = graph_http
    before = db_hash(http)
    error(post(http, refs=[{"kind": "profile", "version": "profile/1.0", "content_hash": "a" * 64}]),
          409, "not_ready", "observation_snapshot_reader_not_available")
    assert db_hash(http) == before


def test_graph_requires_explicit_reader_configuration(graph_http):
    http = graph_http
    disabled = ReportV2Service(http.env.registry, http.env.assessment_store,
                              http.env.task_store, http.env.report_store)
    with TestClient(create_app(http.env.registry, report_v2_service=disabled)) as client:
        response = client.post(http.base, json={"idempotency_key": "unwired", "algorithm_refs": [http.reference.model_dump(mode="json")]})
    error(response, 409, "not_ready", "observation_snapshot_reader_not_available")


def test_graph_capacity_is_413_without_partial_report(graph_http):
    http = graph_http
    http.service.graph_reader = ReportGraphReader(max_nodes=1)
    before = db_hash(http)
    response = post(http)
    error(response, 413, "graph_capacity_exceeded", "graph_capacity_exceeded")
    assert response.json()["error"]["details"]["configured_capacity"]["max_nodes"] == 1
    assert db_hash(http) == before


def test_reader_uses_captured_scan_not_live_registry(graph_http, monkeypatch):
    http = graph_http
    stored = http.env.registry.get(http.env.run.id)
    before = stored.run.model_dump(mode="json")
    def forbidden(*args, **kwargs):
        raise AssertionError("Reader cannot reread the mutable registry")
    monkeypatch.setattr(http.env.registry, "get", forbidden)
    ref, graph = http.reader.read(stored, http.reference)
    assert ref == http.reference
    assert graph["scan_ref"]["registry_revision"] == stored.revision
    assert stored.run.model_dump(mode="json") == before


def test_filtered_view_hash_is_not_misrepresented_as_full_graph(graph_http):
    http = graph_http
    filtered = GraphReader(http.env.registry).read(http.env.run.id,
                         [http.env.run.components[0].id], [])
    ref = {"kind": "graph", "version": ALGORITHM, "content_hash": graph_content_hash(filtered)}
    before = db_hash(http)
    error(post(http, refs=[ref]), 409, "conflict", "graph_content_hash_mismatch")
    assert db_hash(http) == before


def test_partial_scan_stays_partial_with_complete_fact_graph(graph_http):
    http = graph_http
    env = http.env
    partial = seed(env, 2, "partial")
    assessment = make_assessment(env, partial)
    ref, _ = http.reader.capture(env.registry.get(partial.id))
    report = http.service.create(partial.id, assessment.id, idempotency_key="partial-graph", algorithm_refs=[ref])
    doc = json.loads(http.service.artifact(partial.id, assessment.id, report.snapshot_id, "json"))
    graph = next(section["content"] for section in doc["sections"] if section["authority"] == "observation")
    assert doc["binding"]["scan_ref"]["status"] == "partial"
    assert graph["coverage"]["view_complete"] is True
    assert graph["coverage"]["scan_gaps"]
    assert graph["formal"] is False


def test_html_shows_graph_summary_without_turning_it_into_authorization(graph_http):
    http = graph_http
    snapshot = post(http).json()
    href = next(meta["href"] for meta in snapshot["artifacts"] if meta["format"] == "html")
    text = http.client.get(href).text
    assert "本报告的资源关系" in text
    assert "资源图只展示已有事实关系，不代表授权已确认" in text
    assert "完整固定快照" in text


def test_default_request_still_does_not_include_graph(graph_http):
    http = graph_http
    response = post(http, refs=[])
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["binding"]["algorithm_refs"] == []
    assert all(section["authority"] != "observation" for section in document(http, snapshot)["sections"])


def test_saved_graph_replay_survives_reader_and_renderer_unavailability(graph_http,monkeypatch):
    http=graph_http
    first=post(http,key='graph-offline')
    assert first.status_code==200,first.text
    before=db_hash(http)
    http.service.graph_reader=None
    http.service.max_included_items=1
    def forbidden(*args,**kwargs):raise AssertionError('graph replay read live source or rendered')
    monkeypatch.setattr(http.env.registry,'get',forbidden)
    monkeypatch.setattr(http.env.assessment_store,'get',forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_json',forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_html',forbidden)
    second=post(http,key='graph-offline')
    assert second.status_code==200,second.text
    assert second.json()==first.json()
    changed=http.reference.model_dump(mode='json');changed['content_hash']='0'*64
    error(post(http,key='graph-offline',refs=[changed]),409,'conflict','idempotency_conflict')
    assert db_hash(http)==before
