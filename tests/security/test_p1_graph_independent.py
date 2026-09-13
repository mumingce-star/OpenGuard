"""Independent A04 security gates for the read-only resource graph API."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_p1_diff_api import asset, component, snapshot  # noqa: E402
from test_p1_history_api import SAMPLE, env  # noqa: E402,F401


def get_graph(env, run, **params):
    return env.client.get(f"/api/v1/scans/{run.id}/graph", params=params)


def error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert "request_id" in body["error"]


def rich_facts():
    c = component(1)
    a = asset(2)
    value = {"components": [c], "ai_assets": [a], "findings": copy.deepcopy(SAMPLE["findings"]),
             "obligations": copy.deepcopy(SAMPLE["obligations"])}
    value["findings"][0].update(resource_id=c["id"], resource_kind="component")
    value["findings"][0]["evidence_ids"] = [c["evidence_ids"][0]]
    value["findings"][0]["obligation_ids"] = [value["obligations"][0]["id"]]
    value["findings"][0]["remediation_id"] = None
    value["obligations"][0]["license_expression_id"] = c["license_expression_id"]
    return value


def rich_run(env):
    return snapshot(env, 1, lambda p: p.update(**rich_facts()))


def _pointer_exists(document, pointer):
    value = document
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def test_graph_has_only_contract_nodes_edges_and_resolved_source_pointers(env):
    run = rich_run(env)
    response = get_graph(env, run)
    assert response.status_code == 200, response.text
    graph = response.json()
    assert graph["formal"] is False
    assert graph["scan_ref"]["scan_id"] == run.id
    assert graph["filter"] == {"resource_ids": [], "resource_kinds": []}
    assert graph["coverage"]["scope"] == "all"
    assert {node["kind"] for node in graph["nodes"]} <= {
        "project", "component", "ai_asset", "license_observation", "evidence", "finding", "obligation"
    }
    ids = {node["id"] for node in graph["nodes"]}
    assert all(edge["source"] in ids and edge["target"] in ids for edge in graph["edges"])
    assert {edge["type"] for edge in graph["edges"]} == {
        "PROJECT_HAS_RESOURCE", "RESOURCE_HAS_LICENSE_OBSERVATION", "RESOURCE_SUPPORTED_BY_EVIDENCE",
        "RESOURCE_HAS_FINDING", "FINDING_SUPPORTED_BY_EVIDENCE", "FINDING_REFERENCES_OBLIGATION",
        "LICENSE_HAS_RULE_OBLIGATION",
    }
    for edge in graph["edges"]:
        for ref in edge["source_refs"]:
            assert ref["scan_id"] == run.id
            assert ref["pointer"].startswith("/")
            _pointer_exists(run.model_dump(mode="json"), ref["pointer"])


def test_graph_does_not_propagate_root_license_or_create_assessment_nodes(env):
    run = snapshot(env, 1, lambda p: p.update(components=[], ai_assets=[], findings=[], obligations=[]))
    graph = get_graph(env, run).json()
    assert {node["kind"] for node in graph["nodes"]} >= {"project", "license_observation", "evidence"}
    assert not any(edge["type"] == "RESOURCE_HAS_LICENSE_OBSERVATION" for edge in graph["edges"])
    assert not any(node["kind"] == "assessment" for node in graph["nodes"])


def test_shared_license_and_evidence_do_not_pull_unselected_resource_or_finding(env):
    first, second = component(1), component(2)
    second["license_expression_id"] = first["license_expression_id"]
    second["evidence_ids"] = first["evidence_ids"]
    first_finding = copy.deepcopy(SAMPLE["findings"][0])
    first_finding.update(remediation_id=None, obligation_ids=[], resource_id=first["id"],
                         resource_kind="component", evidence_ids=first["evidence_ids"])
    finding = copy.deepcopy(SAMPLE["findings"][0])
    finding.update(id=SAMPLE["findings"][0]["id"][:-1] + "1", resource_id=second["id"], resource_kind="component",
                   evidence_ids=first["evidence_ids"], obligation_ids=[], remediation_id=None)
    run = snapshot(env, 1, lambda p: p.update(components=[first, second], findings=[first_finding, finding],
                                               obligations=[], remediations=[]))
    selected = get_graph(env, run, resource_ids=first["id"])
    assert selected.status_code == 200, selected.text
    graph = selected.json()
    assert {n["source_id"] for n in graph["nodes"] if n["kind"] == "component"} == {first["id"]}
    assert {n["source_id"] for n in graph["nodes"] if n["kind"] == "finding"} == {first_finding["id"]}
    assert any(n["kind"] == "license_observation" for n in graph["nodes"])
    assert any(n["kind"] == "evidence" for n in graph["nodes"])


def test_each_edge_pointer_value_matches_its_endpoint_fact(env):
    run = rich_run(env)
    graph = get_graph(env, run).json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    document = run.model_dump(mode="json")
    for edge in graph["edges"]:
        values = [_pointer_exists(document, ref["pointer"]) for ref in edge["source_refs"]]
        source, target = nodes[edge["source"]]["source_id"], nodes[edge["target"]]["source_id"]
        value = values[0]
        if edge["type"] == "PROJECT_HAS_RESOURCE":
            assert source == run.project.id and target == value["id"]
        elif edge["type"] == "RESOURCE_HAS_LICENSE_OBSERVATION":
            assert target == value
        elif edge["type"] == "RESOURCE_SUPPORTED_BY_EVIDENCE":
            assert target == value
        elif edge["type"] == "RESOURCE_HAS_FINDING":
            assert source == value
        elif edge["type"] == "FINDING_SUPPORTED_BY_EVIDENCE":
            assert target == value
        elif edge["type"] == "FINDING_REFERENCES_OBLIGATION":
            assert target == value
        elif edge["type"] == "LICENSE_HAS_RULE_OBLIGATION":
            assert source == value


@pytest.mark.parametrize("values", [["cmp_"], ["cmp_", "missing"]])
def test_unknown_ids_are_request_errors(env, values):
    run = rich_run(env)
    error(get_graph(env, run, resource_ids=values), 400, "invalid_argument")


def test_one_unknown_id_invalidates_the_whole_request(env):
    run = rich_run(env)
    error(get_graph(env, run, resource_ids=[run.components[0].id, "missing"]), 400, "invalid_argument")


def test_comma_encoded_ids_are_one_unknown_id(env):
    run = rich_run(env)
    error(get_graph(env, run, resource_ids=f"{run.components[0].id},{run.ai_assets[0].id}"), 400, "invalid_argument")


def test_id_and_kind_filter_is_intersection_and_empty_selection_is_project_only(env):
    run = rich_run(env)
    cid = run.components[0].id
    response = get_graph(env, run, resource_ids=cid, resource_kinds="ai_asset")
    assert response.status_code == 200, response.text
    graph = response.json()
    assert graph["filter"] == {"resource_ids": [cid], "resource_kinds": ["ai_asset"]}
    assert graph["coverage"]["scope"] == "filtered"
    assert graph["nodes"] == [next(n for n in graph["nodes"] if n["kind"] == "project")]
    assert graph["edges"] == []


def test_filter_normalization_is_stable_for_duplicates_and_order(env):
    run = rich_run(env)
    first = get_graph(env, run, resource_ids=[run.components[0].id, run.ai_assets[0].id, run.components[0].id],
                      resource_kinds=["ai_asset", "component", "component"])
    second = get_graph(env, run, resource_ids=[run.ai_assets[0].id, run.components[0].id],
                       resource_kinds=["component", "ai_asset"])
    assert first.status_code == second.status_code == 200
    a, b = first.json(), second.json()
    assert a["filter"] == b["filter"]
    assert a["view_id"] == b["view_id"]
    assert a["provenance"]["parameters_hash"] == b["provenance"]["parameters_hash"]


@pytest.mark.parametrize("params", [{"resource_ids": ""}, {"resource_ids": "   "},
                                     {"resource_kinds": ""}, {"resource_kinds": "   "},
                                     {"resource_kinds": "Component"}, {"resource_kinds": "dependency"},
                                     {"limit": 1}, {"cursor": "x"}, {"page": 1}, {"offset": 0},
                                     {"assessment_id": "x"}, {"severity": "low"}])
def test_blank_invalid_and_unknown_query_parameters_rejected(env, params):
    run = rich_run(env)
    error(get_graph(env, run, **params), 400, "invalid_argument")


@pytest.mark.parametrize("status,code", [("queued", "not_ready"), ("running", "not_ready"),
                                          ("failed", "not_comparable"), ("cancelled", "not_comparable")])
def test_non_graphable_scan_statuses(env, status, code):
    from test_p1_history_api import seed
    run = seed(env, 1, status)
    error(get_graph(env, run), 409, code)


def test_partial_graph_keeps_gaps_and_is_selector_complete(env):
    run = snapshot(env, 1, lambda p: p.update(components=[component()]), status="partial")
    response = get_graph(env, run)
    assert response.status_code == 200, response.text
    graph = response.json()
    assert graph["coverage"]["view_complete"] is True
    assert graph["coverage"]["scan_gaps"]


def test_graph_get_is_read_only_and_does_not_start_generators(env, monkeypatch):
    run = rich_run(env)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.iterdir() if p.is_file()}
    revision = env.registry.get(run.id).revision
    def forbidden(*args, **kwargs):
        raise AssertionError("Graph GET attempted a write or generator")
    monkeypatch.setattr(env.registry, "create", forbidden)
    monkeypatch.setattr(env.registry, "replace", forbidden)
    monkeypatch.setattr(env.store, "create", forbidden)
    monkeypatch.setattr(env.store, "latest", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    for _ in range(2):
        assert get_graph(env, run).status_code == 200
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.iterdir() if p.is_file()}
    assert before == after
    assert env.registry.get(run.id).revision == revision
