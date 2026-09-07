"""Implementation-side regression tests for the frozen A5-0 AI boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.ai import AIProviderError, apply_ai_remediations
from app.domain.models import ProducerRef, ProducerType, ScanRun


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174000"
LICENSE_EVIDENCE_ID = "evd_323e4567-e89b-12d3-a456-426614174000"


def _producer() -> ProducerRef:
    return ProducerRef(
        type=ProducerType.AI,
        name="openguard-ai-provider",
        version="0.1.0",
        provider="ollama",
        model_id="qwen3-test@sha256:fixture",
        prompt_schema_digest={"algorithm": "sha256", "value": "a" * 64},
    )


def _run(*, two_findings: bool = False) -> ScanRun:
    value = copy.deepcopy(json.loads((ROOT / "examples/sample-scan-result.json").read_text()))
    value["findings"][0]["remediation_id"] = None
    value["remediations"] = []
    if two_findings:
        second = copy.deepcopy(value["findings"][0])
        second["id"] = "rsk_223e4567-e89b-12d3-a456-426614174000"
        second["title"] = "Second review"
        value["findings"].append(second)
        value["summary"]["finding_counts"]["review_required"] = 2
    return ScanRun.model_validate(value)


def _response(payload: str, *, evidence_id: str = EVIDENCE_ID) -> str:
    finding = json.loads(payload)["finding"]
    return json.dumps(
        {
            "schema_version": "openguard.ai-remediation/v1",
            "finding_id": finding["id"],
            "summary": "Review the cited evidence.",
            "steps": ["Record the human review.", "Verify the distribution context."],
            "evidence_ids": [evidence_id],
        }
    )


class FakeProvider:
    def __init__(self, *, mode: str = "local", replies: list[object] | None = None) -> None:
        self.mode = mode
        self.producer = _producer()
        self.replies = list(replies or [])
        self.calls: list[tuple[dict[str, object], float]] = []

    def generate(self, payload: str, timeout_seconds: float) -> str:
        self.calls.append((json.loads(payload), timeout_seconds))
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            if callable(reply):
                return reply(payload)
            return reply  # type: ignore[return-value]
        return _response(payload)


def _review_run(*, distinct_context=False):
    value = _run(two_findings=True).model_dump(mode="json")
    value["obligations"] = []
    for f in value["findings"]:
        f.update(rule_id="license-evidence-gate", obligation_ids=[], evidence_ids=[EVIDENCE_ID])
    component = copy.deepcopy(value["components"][0])
    component.update(id="cmp_223e4567-e89b-12d3-a456-426614174000", name="second", purl=None,
                     evidence_ids=["evd_423e4567-e89b-12d3-a456-426614174000"])
    if distinct_context:
        component["ecosystem"] = "npm"
    value["components"].append(component)
    evidence = copy.deepcopy(value["evidence"][0])
    evidence["id"] = component["evidence_ids"][0]
    evidence["locator"] = "second.txt"
    value["evidence"].append(evidence)
    value["findings"][1].update(resource_id=component["id"], evidence_ids=component["evidence_ids"])
    value["summary"]["component_count"] = 2
    value["summary"]["evidence_count"] = len(value["evidence"])
    return ScanRun.model_validate(value)


def _plan_reply(payload):
    from app.ai.provider import REVIEW_PLAN_SUMMARY
    request = json.loads(payload)
    return json.dumps({"schema_version": "openguard.ai-review-plan/v1", "plan_id": request["plan_id"],
                       "summary": REVIEW_PLAN_SUMMARY,
                       "steps": ["查找对应版本的许可原文和来源。", "对照拟定使用和分发方式核对许可要求。", "保存原文、版本及人工核验记录。"]}, ensure_ascii=False)


def test_review_plan_shares_workflow_but_never_another_resources_evidence():
    run = _review_run()
    provider = FakeProvider(replies=[_plan_reply])
    provider.review_plan_mode = True
    result = apply_ai_remediations(run, provider)
    assert result.status == "generated" and len(provider.calls) == 1
    assert len(result.run.remediations) == 2
    for f in result.run.findings:
        remediation = next(m for m in result.run.remediations if m.finding_id == f.id)
        assert remediation.evidence_ids == f.evidence_ids
        assert "同类风险" in remediation.summary and remediation.verification_status.value == "pending"
    _assert_deterministic_facts_preserved(run, result.run)
    request = provider.calls[0][0]
    assert "evidence" not in request and "finding" not in request
    assert "second.txt" not in json.dumps(request)


def test_review_plans_separate_contexts_and_keep_success_when_one_group_fails():
    run = _review_run(distinct_context=True)
    provider = FakeProvider(replies=[_plan_reply, RuntimeError("secret")])
    provider.review_plan_mode = True
    result = apply_ai_remediations(run, provider)
    assert len(provider.calls) == 2 and result.status == "degraded"
    assert len(result.run.remediations) == 1
    assert result.run.findings[0].remediation_id and result.run.findings[1].remediation_id is None
    assert result.run.errors[-1].code == "ai_provider_unavailable"
    assert "secret" not in result.run.model_dump_json()
    _assert_deterministic_facts_preserved(run, result.run)


@pytest.mark.parametrize("change", [
    {"summary": "已经合规，可以商用。"}, {"plan_id": "wrong"},
    {"steps": ["Review license."] * 3},
    {"steps": ["查找许可原文。", "记录核验结果。"]},
    {"steps": ["该资源可商用，无需进一步核验。", "必须删除资源才能完成合规。", "保留授权核验的相关记录。"]},
    {"steps": ["核验 review the license and confirm all distribution conditions.", "对照 compare your intended use and deployment scope.", "记录 keep evidence and a review decision."]},
    {"steps": ["将原文和NOASSERTION对照。", "核对具体使用方式。", "记录核验结果和依据。"]},
    {"evidence_ids": [EVIDENCE_ID]},
])
def test_invalid_shared_plan_is_rejected_once_without_fake_success(change):
    def reply(payload):
        data = json.loads(_plan_reply(payload)); data.update(change); return json.dumps(data)
    provider = FakeProvider(replies=[reply]); provider.review_plan_mode = True
    result = apply_ai_remediations(_review_run(), provider)
    assert result.status == "degraded" and not result.run.remediations
    assert len(provider.calls) == 1 and result.run.errors[-1].code == "ai_response_invalid"


def test_individual_failure_cannot_discard_successful_shared_plan():
    value = _review_run().model_dump(mode="json")
    value["findings"][1]["rule_id"] = "special-review"
    run = ScanRun.model_validate(value)
    provider = FakeProvider(replies=[_plan_reply, TimeoutError("offline")]); provider.review_plan_mode = True
    result = apply_ai_remediations(run, provider)
    assert result.status == "degraded" and len(result.run.remediations) == 1
    assert result.run.findings[0].remediation_id and result.run.findings[1].remediation_id is None
    _assert_deterministic_facts_preserved(run, result.run)


def _assert_deterministic_facts_preserved(before: ScanRun, after: ScanRun) -> None:
    for field in (
        "project",
        "components",
        "ai_assets",
        "licenses",
        "evidence",
        "obligations",
        "summary",
        "report_links",
    ):
        assert getattr(after, field) == getattr(before, field)
    for old, new in zip(before.findings, after.findings, strict=True):
        old_value = old.model_dump(mode="python", exclude={"remediation_id"})
        new_value = new.model_dump(mode="python", exclude={"remediation_id"})
        assert new_value == old_value


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_valid_local_and_remote_responses_generate_pending_stable_remediation(mode: str) -> None:
    run = _run()
    first_provider = FakeProvider(mode=mode)
    first = apply_ai_remediations(run, first_provider, timeout_seconds=3)
    second = apply_ai_remediations(run, FakeProvider(mode=mode), timeout_seconds=3.0)

    assert first.status == "generated"
    assert first.run.remediations == second.run.remediations
    remediation = first.run.remediations[0]
    assert remediation.verification_status.value == "pending"
    assert remediation.generated_by == _producer()
    assert first.run.findings[0].remediation_id == remediation.id
    assert first.run.provenance.ai_enabled is True
    assert first.run.provenance.ai_model == _producer()
    assert _producer() in first.run.provenance.tool_versions
    assert first_provider.calls[0][1] == 3.0
    _assert_deterministic_facts_preserved(run, first.run)


def test_payload_contains_only_bound_license_facts_and_allows_their_evidence() -> None:
    provider = FakeProvider(replies=[lambda payload: _response(payload, evidence_id=LICENSE_EVIDENCE_ID)])
    result = apply_ai_remediations(_run(), provider)
    payload = provider.calls[0][0]

    assert result.status == "generated"
    assert [item["id"] for item in payload["licenses"]] == [
        "lic_123e4567-e89b-12d3-a456-426614174000"
    ]
    references = [item["id"] for item in payload["evidence"] + payload["license_evidence"]]
    assert references.count(LICENSE_EVIDENCE_ID) == 1
    assert LICENSE_EVIDENCE_ID in payload["licenses"][0]["evidence_ids"]
    assert result.run.remediations[0].evidence_ids == [LICENSE_EVIDENCE_ID]


def test_skipped_and_disabled_never_call_provider() -> None:
    completed = ScanRun.model_validate(
        json.loads((ROOT / "examples/sample-scan-result.json").read_text())
    )
    skipped_provider = FakeProvider()
    skipped = apply_ai_remediations(completed, skipped_provider)
    disabled_input = _run()
    disabled = apply_ai_remediations(disabled_input, None, enabled=False)

    assert skipped.status == "skipped" and skipped.run is completed
    assert skipped_provider.calls == []
    assert disabled.status == "disabled"
    assert disabled.run.provenance.ai_enabled is False
    assert disabled.run.provenance.ai_model is None
    _assert_deterministic_facts_preserved(disabled_input, disabled.run)


def test_provider_failure_is_sanitized_and_does_not_publish_partial_batch() -> None:
    run = _run(two_findings=True)
    provider = FakeProvider(
        replies=[lambda payload: _response(payload), RuntimeError("token=leak /tmp/x")]
    )
    result = apply_ai_remediations(run, provider)

    assert result.status == "degraded"
    assert result.run.remediations == run.remediations == []
    assert [item.remediation_id for item in result.run.findings] == [None, None]
    assert result.run.errors[-1].code == "ai_provider_unavailable"
    assert result.run.errors[-1].message == "AI remediation provider was unavailable."
    assert "leak" not in result.run.model_dump_json()
    _assert_deterministic_facts_preserved(run, result.run)


def _invalid_reply(case: str):
    def reply(payload: str) -> str:
        valid = json.loads(_response(payload))
        if case == "not_json":
            return "not-json"
        if case == "duplicate":
            return json.dumps(valid)[:-1] + ',"summary":"duplicate"}'
        if case == "nonfinite":
            return json.dumps(valid)[:-1] + ',"extra":NaN}'
        if case == "extra":
            valid["extra"] = "no"
        elif case == "wrong_finding":
            valid["finding_id"] = "rsk_223e4567-e89b-12d3-a456-426614174000"
        elif case == "unknown_evidence":
            valid["evidence_ids"] = ["evd_223e4567-e89b-12d3-a456-426614174999"]
        elif case == "blank":
            valid["summary"] = "   "
        elif case == "path":
            valid["steps"] = ["Inspect (/etc/passwd)."]
        elif case == "json_pointer_in_prose":
            valid["steps"] = ["Review /packages/node_modules~1@e2b~1cli/license."]
        elif case == "secret":
            valid["summary"] = "authorization=secret"
        elif case == "empty_steps":
            valid["steps"] = []
        elif case == "long_step":
            valid["steps"] = ["x" * 1001]
        elif case == "duplicate_evidence":
            valid["evidence_ids"] = [EVIDENCE_ID, EVIDENCE_ID]
        elif case == "too_large":
            valid["padding"] = "x" * (64 * 1024)
        return json.dumps(valid, ensure_ascii=False)

    return reply


@pytest.mark.parametrize(
    "case",
    [
        "not_json",
        "duplicate",
        "nonfinite",
        "extra",
        "wrong_finding",
        "unknown_evidence",
        "blank",
        "path",
        "json_pointer_in_prose",
        "secret",
        "empty_steps",
        "long_step",
        "duplicate_evidence",
        "too_large",
    ],
)
def test_invalid_model_responses_degrade_without_changing_facts(case: str) -> None:
    run = _run()
    result = apply_ai_remediations(run, FakeProvider(replies=[_invalid_reply(case)]))

    assert result.status == "degraded"
    assert result.run.remediations == []
    assert result.run.findings[0].remediation_id is None
    assert result.run.errors[-1].code == "ai_response_invalid"
    assert result.run.errors[-1].message == "AI remediation response was rejected."
    _assert_deterministic_facts_preserved(run, result.run)


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf"), "10"])
def test_invalid_timeout_is_rejected_before_provider_call(timeout: object) -> None:
    provider = FakeProvider()
    with pytest.raises(AIProviderError, match="ai_invalid_argument") as raised:
        apply_ai_remediations(_run(), provider, timeout_seconds=timeout)  # type: ignore[arg-type]
    assert raised.value.code == "ai_invalid_argument"
    assert raised.value.__cause__ is None
    assert provider.calls == []


@pytest.mark.parametrize("provider", [None, object()])
def test_invalid_enabled_provider_is_rejected(provider: object) -> None:
    with pytest.raises(AIProviderError, match="ai_invalid_argument"):
        apply_ai_remediations(_run(), provider)  # type: ignore[arg-type]


def test_invalid_provider_properties_are_sanitized() -> None:
    class Broken:
        @property
        def mode(self):
            raise RuntimeError("secret=do-not-copy")

    with pytest.raises(AIProviderError) as raised:
        apply_ai_remediations(_run(), Broken())  # type: ignore[arg-type]
    assert raised.value.code == "ai_invalid_argument"
    assert raised.value.__cause__ is None


def test_mutated_p0_aggregate_is_rejected_before_provider_call() -> None:
    run = _run()
    run.summary.component_count += 1
    provider = FakeProvider()

    with pytest.raises(AIProviderError) as raised:
        apply_ai_remediations(run, provider)
    assert raised.value.code == "ai_invalid_argument"
    assert raised.value.__cause__ is None
    assert provider.calls == []


def test_provider_identity_is_snapshotted_before_generation() -> None:
    provider = FakeProvider()

    def mutate(payload: str) -> str:
        provider.producer = provider.producer.model_copy(update={"model_id": "changed"})
        return _response(payload)

    provider.replies = [mutate]
    result = apply_ai_remediations(_run(), provider)
    assert result.run.remediations[0].generated_by.model_id == "qwen3-test@sha256:fixture"


def test_repeated_degradation_does_not_duplicate_the_same_diagnostic() -> None:
    provider = FakeProvider(replies=[RuntimeError(), RuntimeError()])
    first = apply_ai_remediations(_run(), provider)
    second = apply_ai_remediations(first.run, provider)
    assert [item.code for item in second.run.errors].count("ai_provider_unavailable") == 1
