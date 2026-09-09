"""Independent V2 security checks for the real group-plan application path."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.ai import OllamaProvider
from app.ai.group_plan import clear_group_cache, get_group_progress
from app.ai.provider import apply_ai_remediations
from app.domain.models import ProducerRef, ProducerType, ScanRun
from test_a5_ollama_transport_independent import (
    EXPECTED_MODEL_NAME,
    _LoopbackFixture,
    _Scenario,
)


ROOT = Path(__file__).resolve().parents[2]


def _run(*, two_findings: bool = False) -> ScanRun:
    value = json.loads((ROOT / "examples/sample-scan-result.json").read_text())
    value["findings"][0]["remediation_id"] = None
    value["remediations"] = []
    if two_findings:
        second = copy.deepcopy(value["findings"][0])
        second["id"] = "rsk_223e4567-e89b-12d3-a456-426614174000"
        second["title"] = "Second review"
        value["findings"].append(second)
        value["summary"]["finding_counts"]["review_required"] = 2
    return ScanRun.model_validate(value)


def _producer() -> ProducerRef:
    return ProducerRef(
        type=ProducerType.AI,
        name="openguard-ai-provider",
        version="0.1.0",
        provider="ollama",
        model_id="qwen3-test@sha256:fixture",
        prompt_schema_digest={"algorithm": "sha256", "value": "a" * 64},
    )


class _Provider:
    group_plan_mode = True

    def __init__(self, *, mode: str = "local", reply=None) -> None:
        self.mode = mode
        self.producer = _producer()
        self.calls: list[dict] = []
        self.reply = reply or self._valid_reply

    def generate(self, payload: str, timeout_seconds: float) -> str:
        request = json.loads(payload)
        self.calls.append(request)
        return self.reply(request)

    @staticmethod
    def _valid_reply(request: dict) -> str:
        scope = request["context"]["scope"]
        return json.dumps(
            {
                "group_id": request["group_id"],
                "summary": f"本组核验{scope}记录与适用许可之间的关系。",
                "steps": [
                    "依据逐项证据核对资源版本和声明位置。",
                    "查阅对应版本官方来源的许可原文并记录位置。",
                    "结合实际使用和分发条件逐条比对许可义务。",
                ],
                "limitations": "实际用途及授权仍需人工核验，不能据此判定合规。",
            },
            ensure_ascii=False,
        )


@pytest.fixture(autouse=True)
def _cache_boundary():
    clear_group_cache()
    yield
    clear_group_cache()


def test_group_plan_binds_each_member_to_its_own_evidence_on_real_apply_path():
    run = _run(two_findings=True)
    provider = _Provider()
    result = apply_ai_remediations(run, provider)

    assert result.status == "generated"
    assert len(result.run.remediations) == 2
    assert len(result.run.remediations[0].evidence_ids) > 0
    for remediation in result.run.remediations:
        finding = next(item for item in run.findings if item.id == remediation.finding_id)
        assert remediation.evidence_ids == finding.evidence_ids
    request_text = json.dumps(provider.calls)
    assert run.id not in request_text
    assert run.findings[0].id not in request_text
    assert run.components[0].name not in request_text


@pytest.mark.parametrize(
    "claim",
    [
        "本组核验声明记录已经合规，可以商用。",
        "本组核验声明已审阅所有成员，许可已验证。",
        "本组核验声明记录<b>可继续使用</b>。",
    ],
)
def test_group_plan_rejects_injected_or_unauthorized_model_claims(claim: str):
    def malicious(request: dict) -> str:
        value = json.loads(_Provider._valid_reply(request))
        value["summary"] = claim
        return json.dumps(value, ensure_ascii=False)

    result = apply_ai_remediations(_run(), _Provider(reply=malicious))

    assert result.status == "degraded"
    assert result.run.remediations == []
    assert result.run.findings[0].remediation_id is None
    assert result.run.errors[-1].code == "ai_response_invalid"


def test_group_plan_cache_invalidates_when_provider_mode_changes():
    run = _run()
    local = _Provider(mode="local")
    remote = _Provider(mode="remote")

    assert apply_ai_remediations(run, local).status == "generated"
    assert apply_ai_remediations(run, remote).status == "generated"

    # Transport mode is runtime configuration. A plan generated under local
    # must not silently serve a remote provider with the same producer label.
    assert len(local.calls) == 1
    assert len(remote.calls) == 1


class _OllamaGroupScenario(_Scenario):
    def response(self, method: str, path: str, body: bytes):
        if path == "/api/generate" and method == "POST":
            request = json.loads(body)
            group = request["prompt"]
            value = json.loads(group)
            context = value["context"]
            response = {
                "group_id": value["group_id"],
                "summary": f"本组核验{context['scope']}记录与适用许可之间的关系。",
                "steps": {
                    "locate": "核对本组成员的原始证据与版本差异记录。",
                    "source": "查阅对应版本官方来源的许可原文并记录位置。",
                    "record": "记录许可条款与实际用途对照及尚缺信息。",
                },
                "limitations": "实际用途及授权仍需人工核验，不能据此判定合规。",
            }
            return 200, "application/json; charset=utf-8", json.dumps(
                {"model": EXPECTED_MODEL_NAME, "done": True,
                 "response": json.dumps(response, ensure_ascii=False)},
                ensure_ascii=False,
            ).encode()
        return super().response(method, path, body)


def test_default_ollama_group_path_uses_real_tcp_once_and_binds_two_members():
    run = _run(two_findings=True)
    scenario = _OllamaGroupScenario()
    with _LoopbackFixture(scenario) as fixture:
        provider = OllamaProvider(fixture.origin)
        first = apply_ai_remediations(run, provider)
        second = apply_ai_remediations(run, provider)

    generate_requests = [body for method, path, body in scenario.requests
                         if method == "POST" and path == "/api/generate"]
    assert first.status == second.status == "generated"
    assert len(generate_requests) == 1
    request = json.loads(generate_requests[0])
    assert request["format"]["properties"]["steps"]["type"] == "object"
    prompt = json.loads(request["prompt"])
    prompt_text = json.dumps(prompt, ensure_ascii=False)
    assert run.id not in prompt_text and run.findings[0].id not in prompt_text
    assert run.components[0].name not in prompt_text
    assert len(first.run.remediations) == 2
    for remediation in first.run.remediations:
        finding = next(item for item in run.findings if item.id == remediation.finding_id)
        assert remediation.evidence_ids == finding.evidence_ids


def test_group_progress_counts_completed_and_failed_requests_without_fake_completion():
    value = _run(two_findings=True).model_dump(mode="json")
    value["findings"].append(copy.deepcopy(value["findings"][0]))
    value["findings"][1]["rule_version"] = "0.1.1"
    value["findings"][2]["id"] = "rsk_323e4567-e89b-12d3-a456-426614174000"
    value["findings"][2]["rule_version"] = "0.1.2"
    value["summary"]["finding_counts"]["review_required"] = 3
    run = ScanRun.model_validate(value)

    class FailingProvider(_Provider):
        def generate(self, payload: str, timeout_seconds: float) -> str:
            if len(self.calls) == 2:
                raise RuntimeError("fixture failure")
            return super().generate(payload, timeout_seconds)

    provider = FailingProvider()
    result = apply_ai_remediations(run, provider)
    progress = get_group_progress(run.id)
    assert result.status == "degraded"
    assert progress is not None
    assert progress["groups_total"] == 3
    assert progress["groups_done"] == 3
    assert progress["requests"] == 3
    assert progress["successful_groups"] == 2
    assert progress["groups_done"] == progress["groups_total"]
    assert len(result.run.remediations) == 2


def test_group_progress_drops_stale_eta_instead_of_reporting_unbounded_estimate():
    value = _run(two_findings=True).model_dump(mode="json")
    value["findings"].append(copy.deepcopy(value["findings"][0]))
    value["findings"][1]["rule_version"] = "0.1.1"
    value["findings"][2]["id"] = "rsk_323e4567-e89b-12d3-a456-426614174000"
    value["findings"][2]["rule_version"] = "0.1.2"
    value["summary"]["finding_counts"]["review_required"] = 3
    run = ScanRun.model_validate(value)
    observed = {}

    class SlowProvider(_Provider):
        def generate(self, payload: str, timeout_seconds: float) -> str:
            import time as _time
            if len(self.calls) == 2:
                _time.sleep(0.05)
                observed.update(get_group_progress(run.id) or {})
            return super().generate(payload, timeout_seconds)

    result = apply_ai_remediations(run, SlowProvider())
    assert result.status == "generated"
    assert observed.get("eta_seconds") is None
    assert observed.get("estimate_insufficient") is True
