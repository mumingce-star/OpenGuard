"""Real offline ASGI v4 integration; only the model transport is synthetic."""

from copy import deepcopy
import json
import os
from pathlib import Path
import socket

import pytest

from app.ai.ollama import MANIFEST_DIGEST, MODEL_NAME, OLLAMA_VERSION
from app.p1.dependency_evidence import project_dependency_evidence
from app.p2.contract import digest
from test_p2_ai_analysis import flow as legacy_flow
from test_p2_contract import create, setup as base_setup
from test_p2_contract import setup as parent_setup
from test_task33_material_claims import get as read_claims
from test_task37_real_material_chain import database_state
from test_task39_p4_closure import (
    APACHE, MIT, NOTICE, _scan_zip_into_assessment, _task43_endpoint, _task44_uv,
    _task44_zip, _task49_original, upload,
)

ANALYSIS_PROTOCOL = "openguard-qwen-v4-plan/3"
PLAN_PROTOCOL = "openguard-action-plan/3"
PROMPT_VERSION = "p2-v4-structured-plan/1"
ORIGIN = "PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION"
PERMISSIVE = "VERIFY_PERMISSIVE_OBLIGATIONS"
MISSING = "SUPPLY_MISSING_LICENSE_MATERIAL"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("TEST_ONLY ASGI must not use live model networking")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setenv("OPENGUARD_P2_ACTION_PLAN", "0")


@pytest.fixture
def v4_settings(tmp_path, monkeypatch, request):
    for key, value in {
        "OPENGUARD_ENABLE_P2_AI": "1",
        "OPENGUARD_P2_AI_INPUT_SCOPE": "bound_materials",
        "OPENGUARD_P2_AI_USAGE_MODE": "bounded",
        "OPENGUARD_P2_AI_MAX_GENERATIONS": str(getattr(request, "param", 20)),
        "OPENGUARD_P2_AI_BUDGET_PATH": str(tmp_path / "task50-budget.json"),
        "OPENGUARD_P2_AI_V4_PLAN": "1",
    }.items():
        monkeypatch.setenv(key, value)
    yield tmp_path


@pytest.fixture
def v4_app(v4_settings, base_setup):
    return base_setup


def select(context):
    rows = context["action_catalog"]
    actions = [row for row in rows if row["required"]]
    # Explicitly exercise the optional conflict action when present; the
    # transport substitute never invents it in an unrelated scenario.
    actions += [row for row in rows if not row["required"]
                and row["action_kind"] == "RESOLVE_DEPENDENCY_VERSION_CONFLICT"][:4-len(actions)]
    if not actions:
        actions = rows[:1]
    return {
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "prompt_version": PROMPT_VERSION,
        "selected_actions": [{"action_kind": row["action_kind"], "basis_ids": row["basis_ids"]}
                             for row in actions],
        "selected_quotes": [{"quote_id": row["quote_id"], "category": row["kind"]}
                            for row in context["quote_catalog"][:1]],
        "selected_change_indices": (
            [0] if context["incremental_impact_summary"]["changed_claims"] else []
        ),
    }


class OfflineModel:
    def __init__(self, service, response_modes=()):
        self.service = service
        self.generation_bodies = []
        self.payloads = []
        self.paths = []
        self.response_modes = response_modes
        service.provider.transport._request_json = self.request

    def request(self, path, *, body=None, **kwargs):
        self.paths.append(path)
        if path == "/api/version":
            return {"version": OLLAMA_VERSION}
        if path == "/api/tags":
            return {"models": [{"name": MODEL_NAME, "digest": MANIFEST_DIGEST}]}
        assert path == "/api/generate"
        self.generation_bodies.append(deepcopy(body))
        payload = json.loads(body["prompt"])
        self.payloads.append(payload)
        assert payload["analysis_protocol"] == ANALYSIS_PROTOCOL
        assert body["model"] == MODEL_NAME and body["format"]["additionalProperties"] is False
        number = len(self.payloads) - 1
        mode = self.response_modes[number] if number < len(self.response_modes) else "valid"
        if mode == "timeout":
            raise TimeoutError("TEST_ONLY timeout")
        model = select(payload["context"])
        if mode == "omit":
            assert len(model["selected_actions"]) >= 2
            model["selected_actions"].pop()
        if mode == "forged":
            model["selected_actions"] = [{"action_kind": PERMISSIVE, "basis_ids": ["invented"]}]
        if mode == "authorization":
            model["selected_actions"][0]["text"] = "已授权商用"
        raw = "{not JSON" if mode == "invalid" else json.dumps(model, ensure_ascii=False)
        return {"model": MODEL_NAME, "done": True, "done_reason": "stop", "response": raw,
                "prompt_eval_count": 151, "eval_count": 51, "total_duration": 302000}


def request_for(result, subject, *, key="task50-v4-creation", material_ids=None):
    saved = next(row for row in result["resources"] if row["subject"] == subject)
    return {
        "binding": result["binding"], "result_id": result["result_id"],
        "result_sha256": result["result_sha256"], "subject": subject,
        "material_ids": saved["material_ids"] if material_ids is None else material_ids,
        "previous_result_id": result["previous_result_id"], "idempotency_key": key,
    }


def read_analysis(client, route, saved):
    return client.get(
        route + "/ai-analyses/" + saved["analysis_id"],
        params={"result_id": saved["result_id"], "assessment_version": saved["binding"]["assessment_version"]},
    )


def protected(root):
    all_databases = database_state(root)
    return {name: data for name, data in all_databases.items()
            if Path(name).name not in {"p2-ai.db"}}


def check_context(value, result, subject, view):
    assert value["analysis_protocol"] == ANALYSIS_PROTOCOL and value["formal_effect"] == "none"
    assert value["model"]["prompt_version"] == PROMPT_VERSION
    assert value["material_claims_view_id"] == view["view_id"]
    assert value["context_sha256"] == digest(value["context"])
    context = value["context"]
    actual, = [row for row in result["resources"] if row["subject"] == subject]
    assert context["protocol"] == PLAN_PROTOCOL and context["material_claims_view_id"] == view["view_id"]
    assert context["result_sha256"] == result["result_sha256"] and context["binding"] == result["binding"]
    assert {k: context["subject"][k] for k in subject} == actual["subject"]
    return context


def create_analysis(harness, result, subject, *, response_modes=()):
    client, app, route, _, root = harness
    model = OfflineModel(app.state.p2_service.ai_analysis, response_modes)
    view = read_claims(harness, result)
    source_before = protected(root)
    body = request_for(result, subject)
    reply = client.post(route + "/ai-analyses", json=body)
    assert reply.status_code == 201, reply.text
    value = reply.json()
    context = check_context(value, result, subject, view)
    assert protected(root) == source_before and read_claims(harness, result) == view
    return value, context, model, body


def test_task50_real_mit_r2_explanation_replays_immutable_context(v4_app):
    harness, old, subject = _task43_endpoint(v4_app, "MIT", MIT)
    current = upload(harness, old, subject, MIT)
    value, context, model, body = create_analysis(harness, current, subject)
    client, _, route, _, root = harness
    assert value["status"] == "succeeded" and value["model_calls"] == 1
    assert value["display_origin"] == ORIGIN and value["selection_sha256"] == digest(value["plan"])
    assert context["declared_spdx"] == "MIT" and set(context["claim_states"].values()) == {"SUPPORT"}
    assert context["subject"]["component_name"] == "task39-apache-test" and context["subject"]["ecosystem"] == "npm"
    assert context["quote_catalog"] and context["incremental_impact_summary"]["changed_claims"]
    assert PERMISSIVE in {row["action_kind"] for row in value["actions"]}
    assert len(model.generation_bodies) == 1
    before = database_state(root)
    index = client.get(route + "/ai-analyses", params={
        "result_id": current["result_id"], "assessment_version": current["binding"]["assessment_version"],
    }).json()
    assert index == {"result_id": current["result_id"], "analysis_ids": [value["analysis_id"]],
                     "v4_plan_enabled": True}
    assert read_analysis(client, route, value).json() == value
    assert client.post(route + "/ai-analyses", json=body).json() == value
    assert len(model.generation_bodies) == 1 and database_state(root) == before
    # A summary has no credentials, raw model text, or unaudited external source.
    if os.environ.get("TASK50_CAPTURE_V4_MIT_JSON") == "1":
        output = Path(os.environ["TASK50_OUTPUT_DIRECTORY"]) / "logs/v4-mit-r2-authoritative-context.json"
        with output.open("x", encoding="utf-8") as stream:
            json.dump({"source": "SYNTHETIC_TRANSPORT_REAL_ASGI", "context": context,
                       "context_sha256": value["context_sha256"], "payload": model.payloads[0]},
                      stream, ensure_ascii=False, indent=2)


def test_task50_exact_empty_r1_keeps_unknown_and_legacy_empty_is_rejected(v4_app):
    harness, result, subject = _task43_endpoint(v4_app, "MIT", MIT)
    client, _, route, _, _ = harness
    body = request_for(result, subject, material_ids=[])
    without = {k: v for k, v in body.items() if k != "subject"}
    assert client.post(route + "/ai-analyses", json=without).status_code == 422
    value, context, model, _ = create_analysis(harness, result, subject)
    assert value["status"] == "succeeded" and len(model.generation_bodies) == 1
    assert context["quote_catalog"] == [] and set(context["claim_states"].values()) == {"UNKNOWN"}
    assert {x["action_kind"] for x in value["actions"]} >= {MISSING}
    assert PERMISSIVE not in {x["action_kind"] for x in context["action_catalog"]}


@pytest.mark.parametrize(("declared","observed","required"), [
    ("MPL-2.0", "MPL-2.0", "REVIEW_WEAK_COPYLEFT_FILE_SCOPE"),
    ("GPL-3.0-only", "GPL-3.0", "REVIEW_STRONG_COPYLEFT_DISCLOSURE"),
    ("MIT", "MPL-2.0", "RESOLVE_SPDX_TEXT_CONFLICT"),
    ("Apache-2.0", "Apache-2.0", "REVIEW_APACHE_NOTICE_SECTION_4D"),
])
def test_task50_real_copyleft_conflict_and_notice_never_upgrade_terms(v4_app, declared, observed, required):
    is_notice = declared == "Apache-2.0"
    raw = APACHE if is_notice else _task49_original(observed)
    harness, old, subject = _task43_endpoint(v4_app, declared, raw, pinned=is_notice, notice=NOTICE if is_notice else None)
    current = upload(harness, old, subject, raw)
    if is_notice:
        current = upload(harness, current, subject, NOTICE, "NOTICE")
    value, context, _, _ = create_analysis(harness, current, subject)
    assert value["status"] == "succeeded"
    assert required in {x["action_kind"] for x in value["actions"]}
    assert PERMISSIVE not in {x["action_kind"] for x in context["action_catalog"]}
    assert "SUPPORT" not in set(context["claim_states"].values())


def test_task50_python_root_observation_and_b58_dependency_use_real_scanned_subjects(v4_app):
    files = {
        "pyproject.toml": b'[project]\nname="task50-python-root"\nversion="1.2rc1"\nlicense="MIT"\n'
                          b'dependencies=["task50-dependent==1.2.3"]\n',
        "uv.lock": _task44_uv("task50-dependent", "2.3.4"),
    }
    harness, run = _scan_zip_into_assessment(v4_app, _task44_zip(v4_app, files), index=5050)
    root, = [entry for entry in run.components if entry.name == "task50-python-root"]
    result = create(harness)
    python_subject = {"resource_id": root.id, "version": root.version}
    current = upload(harness, result, python_subject, MIT)
    output, context, _, _ = create_analysis(harness, current, python_subject)
    assert output["status"] == "succeeded"
    assert context["subject"]["component_name"] == root.name and context["subject"]["ecosystem"] == "pypi"
    assert context["subject"]["version"] == "1.2rc1"
    assert context["source_binding"] == "NOT_ESTABLISHED" and context["dependency_conflicts"] is None
    assert set(context["claim_states"].values()) == {"UNKNOWN"}

    dependencies, _, _ = project_dependency_evidence(run, source=None, after=None, limit=100)
    dep = next(item for item in dependencies if item.name == "task50-dependent" and item.version=="1.2.3")
    assert dep.conflicts and dep.conflicts[0].code == "lock_version_conflict"
    target = {"resource_id": dep.resource_id, "version": dep.version}
    client, _, route, _, _ = harness
    cross_subject = request_for(current, python_subject, key="task50-cross-subject") | {"subject": target}
    rejected = client.post(route + "/ai-analyses", json=cross_subject)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "p2_ai_material_binding_conflict"
    wrong_version = request_for(current, python_subject, key="task50-wrong-version") | {
        "subject": {"resource_id": root.id, "version": "1.2rc2"},
    }
    rejected = client.post(route + "/ai-analyses", json=wrong_version)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "p2_ai_subject_binding_conflict"
    dep_reply = client.post(route + "/ai-analyses", json=request_for(result, target, key="task50-pypi-dependency"))
    assert dep_reply.status_code == 201, dep_reply.text
    value = dep_reply.json()
    assert value["status"] == "succeeded"
    assert value["context"]["dependency_conflicts"]["resource_id"] == dep.resource_id
    assert value["context"]["dependency_conflicts"]["conflicts"][0]["code"] == "lock_version_conflict"
    assert {x["action_kind"] for x in value["context"]["action_catalog"]} >= {"RESOLVE_DEPENDENCY_VERSION_CONFLICT"}
    assert {x["action_kind"] for x in value["actions"]} >= {"RESOLVE_DEPENDENCY_VERSION_CONFLICT"}


@pytest.mark.parametrize(("modes","status","calls"), [
    (("omit", "valid"), "succeeded", 2),
    (("omit", "omit", "valid"), "failed", 2),
    (("forged","valid"), "failed", 1),
    (("authorization", "valid"), "failed", 1),
    (("invalid", "valid"), "failed", 1),
    (("timeout", "valid"), "failed", 1),
])
def test_task50_only_omissions_can_be_corrected_once_without_fact_mutation(v4_app, modes, status, calls):
    harness, result, subject = _task43_endpoint(v4_app, "MPL-2.0", MIT, pinned=False)
    value, context, model, body = create_analysis(harness, result, subject, response_modes=modes)
    assert value["status"] == status and value["model_calls"] == calls == len(model.generation_bodies)
    if status == "failed":
        assert value["error_code"] and not value["actions"] and not value["clauses"] and not value["changes"]
    client, _, route, _, _ = harness
    assert client.post(route + "/ai-analyses", json=body).json() == value
    assert len(model.generation_bodies) == calls


@pytest.mark.parametrize("v4_settings", [1], indirect=True)
def test_task50_corrective_attempt_cannot_bypass_persisted_generation_budget(v4_app):
    harness, result, subject = _task43_endpoint(v4_app, "MPL-2.0", MIT, pinned=False)
    value, _, model, _ = create_analysis(harness, result, subject, response_modes=("omit","valid"))
    assert value["status"] == "failed" and value["error_code"] == "p2_ai_budget_exhausted"
    assert value["model_calls"] == len(model.generation_bodies) == 1
    ledger = json.loads((harness[-1]/"task50-budget.json").read_text())
    assert len(ledger["intents"]) == 1


def test_task50_read_revalidates_current_view_without_model_generation(v4_app, monkeypatch):
    harness, result, subject = _task43_endpoint(v4_app, "MIT", MIT)
    current = upload(harness, result, subject, MIT)
    value, _, model, _ = create_analysis(harness, current, subject)
    assert value["status"] == "succeeded"
    client, app, route, _, root = harness
    service = app.state.p2_service
    current_projection = service.material_claims

    def different_view(*args):
        return {**current_projection(*args), "view_id": "p2_changed_frozen_fact"}

    monkeypatch.setattr(service, "material_claims", different_view)
    baseline = database_state(root)
    response = read_analysis(client, route, value)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "p2_ai_saved_output_rejected"
    assert len(model.generation_bodies) == 1 and database_state(root) == baseline


def test_task50_disabled_subject_request_never_reaches_transport(v4_app, monkeypatch):
    harness, result, subject = _task43_endpoint(v4_app, "MIT", MIT)
    client, app, route, _, _ = harness
    service = app.state.p2_service.ai_analysis
    monkeypatch.setenv("OPENGUARD_P2_AI_V4_PLAN", "0")
    monkeypatch.setattr(service, "v4_plan_enabled", False, raising=False)
    model = OfflineModel(service)
    reply = client.post(route + "/ai-analyses", json=request_for(result, subject))
    assert reply.status_code == 403 and not model.paths


def test_task50_legacy_idempotency_fingerprint_survives_new_optional_subject(legacy_flow):
    client, app, route, _, _, _, _, model, legacy_body = legacy_flow
    first = client.post(route + "/ai-analyses", json=legacy_body)
    assert first.status_code == 201 and first.json()["status"] == "succeeded"
    assert model.calls == 1
    service = app.state.p2_service.ai_analysis
    # Restore the precise fingerprint stored before optional subject existed.
    with service.store.connection(write=True) as db:
        db.execute("UPDATE ai_requests SET fingerprint=?", (digest(legacy_body),))
    assert client.post(route + "/ai-analyses", json=legacy_body).json() == first.json()
    assert model.calls == 1
