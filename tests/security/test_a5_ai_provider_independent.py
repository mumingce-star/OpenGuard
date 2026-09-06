"""Independent security and reliability tests for the frozen A5-0 boundary."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pytest

from app.ai import AIProviderError, apply_ai_remediations
from app.domain.models import (
    Component,
    ComponentType,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    FindingOutcome,
    HashValue,
    LicenseExpression,
    ProducerRef,
    ProducerType,
    Project,
    Remediation,
    RiskFinding,
    RunEnvironment,
    RunProvenance,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    Severity,
    SourceType,
    VerificationStatus,
)


_NOW = datetime(2026, 9, 4, 3, 0, tzinfo=timezone.utc)
_PROJECT_ID = "prj_123e4567-e89b-12d3-a456-426614174000"
_RUN_ID = "scn_123e4567-e89b-12d3-a456-426614174000"
_BOUND_COMPONENT_ID = "cmp_123e4567-e89b-12d3-a456-426614174000"
_UNBOUND_COMPONENT_ID = "cmp_223e4567-e89b-12d3-a456-426614174000"
_BOUND_EVIDENCE_ID = "evd_123e4567-e89b-12d3-a456-426614174000"
_BOUND_LICENSE_EVIDENCE_ID = "evd_223e4567-e89b-12d3-a456-426614174000"
_UNBOUND_EVIDENCE_ID = "evd_323e4567-e89b-12d3-a456-426614174000"
_UNBOUND_LICENSE_EVIDENCE_ID = "evd_423e4567-e89b-12d3-a456-426614174000"
_BOUND_LICENSE_ID = "lic_123e4567-e89b-12d3-a456-426614174000"
_UNBOUND_LICENSE_ID = "lic_223e4567-e89b-12d3-a456-426614174000"
_FINDING_ID = "rsk_123e4567-e89b-12d3-a456-426614174000"
_SECOND_FINDING_ID = "rsk_223e4567-e89b-12d3-a456-426614174000"
_PREBOUND_REMEDIATION_ID = "rem_323e4567-e89b-12d3-a456-426614174000"


def _hash(character: str) -> HashValue:
    return HashValue(algorithm="sha256", value=character * 64)


def _ai_producer(*, model_id: str = "independent-model@sha256:fixture") -> ProducerRef:
    return ProducerRef(
        type=ProducerType.AI,
        name="independent-a5-provider",
        version="0.1.0",
        provider="injected-test-provider",
        model_id=model_id,
        prompt_schema_digest=_hash("a"),
    )


def _human_producer() -> ProducerRef:
    return ProducerRef(type=ProducerType.HUMAN, name="independent-review", version="0.1.0")


def _parser_producer() -> ProducerRef:
    return ProducerRef(type=ProducerType.PARSER, name="independent-parser", version="0.1.0")


def _project() -> Project:
    return Project(
        id=_PROJECT_ID,
        name="A5 independent project",
        source_type=SourceType.ZIP,
        source="a5-independent.zip",
        root_digest=_hash("b"),
        created_at=_NOW,
    )


def _evidence(
    evidence_id: str,
    *,
    kind: EvidenceKind,
    locator: str,
    excerpt: str,
    detected_by: DetectionMethod,
    producer: ProducerRef,
    content_hash: HashValue,
) -> Evidence:
    return Evidence(
        id=evidence_id,
        kind=kind,
        locator=locator,
        excerpt=excerpt,
        start_line=1 if kind is EvidenceKind.MANIFEST_FIELD else None,
        end_line=1 if kind is EvidenceKind.MANIFEST_FIELD else None,
        content_hash=content_hash,
        detected_by=detected_by,
        producer=producer,
        observed_at=_NOW,
        verification_status=VerificationStatus.VERIFIED,
    )


def _all_evidence() -> list[Evidence]:
    return [
        _evidence(
            _BOUND_EVIDENCE_ID,
            kind=EvidenceKind.MANIFEST_FIELD,
            locator="requirements.txt:1",
            excerpt="requests==2.32.5",
            detected_by=DetectionMethod.MANIFEST_PARSER,
            producer=_parser_producer(),
            content_hash=_hash("c"),
        ),
        _evidence(
            _BOUND_LICENSE_EVIDENCE_ID,
            kind=EvidenceKind.LICENSE_TEXT,
            locator="LICENSE",
            excerpt="Apache License 2.0",
            detected_by=DetectionMethod.MANUAL,
            producer=_human_producer(),
            content_hash=_hash("d"),
        ),
        _evidence(
            _UNBOUND_EVIDENCE_ID,
            kind=EvidenceKind.MANIFEST_FIELD,
            locator="other-package.txt:1",
            excerpt="other-package==1.0.0",
            detected_by=DetectionMethod.MANIFEST_PARSER,
            producer=_parser_producer(),
            content_hash=_hash("e"),
        ),
        _evidence(
            _UNBOUND_LICENSE_EVIDENCE_ID,
            kind=EvidenceKind.LICENSE_TEXT,
            locator="OTHER-LICENSE",
            excerpt="MIT License",
            detected_by=DetectionMethod.MANUAL,
            producer=_human_producer(),
            content_hash=_hash("f"),
        ),
    ]


def _all_licenses() -> list[LicenseExpression]:
    return [
        LicenseExpression(
            id=_BOUND_LICENSE_ID,
            expression="Apache-2.0",
            normalized_ids=["Apache-2.0"],
            source_url="https://spdx.org/licenses/Apache-2.0.html",
            evidence_ids=[_BOUND_LICENSE_EVIDENCE_ID],
            confidence=1.0,
            verification_status=VerificationStatus.VERIFIED,
        ),
        LicenseExpression(
            id=_UNBOUND_LICENSE_ID,
            expression="MIT",
            normalized_ids=["MIT"],
            source_url="https://spdx.org/licenses/MIT.html",
            evidence_ids=[_UNBOUND_LICENSE_EVIDENCE_ID],
            confidence=1.0,
            verification_status=VerificationStatus.VERIFIED,
        ),
    ]


def _all_components() -> list[Component]:
    return [
        Component(
            id=_BOUND_COMPONENT_ID,
            name="requests",
            version="2.32.5",
            ecosystem="pypi",
            component_type=ComponentType.LIBRARY,
            purl="pkg:pypi/requests@2.32.5",
            source_url="https://pypi.org/project/requests/",
            license_expression_id=_BOUND_LICENSE_ID,
            evidence_ids=[_BOUND_EVIDENCE_ID],
            detected_by=[DetectionMethod.MANIFEST_PARSER],
            confidence=1.0,
        ),
        Component(
            id=_UNBOUND_COMPONENT_ID,
            name="other-package",
            version="1.0.0",
            ecosystem="npm",
            component_type=ComponentType.LIBRARY,
            purl="pkg:npm/other-package@1.0.0",
            source_url="https://www.npmjs.com/package/other-package",
            license_expression_id=_UNBOUND_LICENSE_ID,
            evidence_ids=[_UNBOUND_EVIDENCE_ID],
            detected_by=[DetectionMethod.MANIFEST_PARSER],
            confidence=1.0,
        ),
    ]


def _finding(
    finding_id: str = _FINDING_ID,
    *,
    resource_id: str = _BOUND_COMPONENT_ID,
    evidence_ids: list[str] | None = None,
    outcome: FindingOutcome = FindingOutcome.REVIEW_REQUIRED,
    remediation_id: str | None = None,
) -> RiskFinding:
    return RiskFinding(
        id=finding_id,
        resource_kind="component",
        resource_id=resource_id,
        outcome=outcome,
        severity=Severity.MEDIUM,
        title="License review required",
        description="The deterministic scan requires a human review of the cited license.",
        rule_id="license.review",
        rule_version="rules-test-1",
        trigger="license evidence requires review",
        evidence_ids=evidence_ids
        if evidence_ids is not None
        else [_BOUND_EVIDENCE_ID],
        obligation_ids=[],
        remediation_id=remediation_id,
        confidence=0.9,
    )


def _prebound_remediation() -> Remediation:
    return Remediation(
        id=_PREBOUND_REMEDIATION_ID,
        finding_id=_SECOND_FINDING_ID,
        summary="Existing human review",
        steps=["Keep the existing review record."],
        evidence_ids=[_UNBOUND_EVIDENCE_ID],
        generated_by=_human_producer(),
        verification_status=VerificationStatus.VERIFIED,
    )


def _provenance() -> RunProvenance:
    return RunProvenance(
        input_digest=_hash("1"),
        inventory_digest=_hash("2"),
        tool_versions=[_parser_producer()],
        ruleset_version="rules-test-1",
        contract_version="0.1.1",
        ai_enabled=False,
        ai_model=None,
        run_environment=RunEnvironment(
            python_version="3.12-test",
            platform="independent-test-platform",
            openguard_version="test",
        ),
    )


def _run(
    *,
    findings: list[RiskFinding] | None = None,
    remediations: list[Remediation] | None = None,
    components: list[Component] | None = None,
    licenses: list[LicenseExpression] | None = None,
    evidence: list[Evidence] | None = None,
) -> ScanRun:
    actual_findings = findings if findings is not None else [_finding()]
    actual_components = components if components is not None else _all_components()
    actual_licenses = licenses if licenses is not None else _all_licenses()
    actual_evidence = evidence if evidence is not None else _all_evidence()
    actual_remediations = remediations if remediations is not None else []
    counts = {outcome: 0 for outcome in FindingOutcome}
    for finding in actual_findings:
        counts[finding.outcome] += 1
    return ScanRun(
        contract_version="0.1.1",
        id=_RUN_ID,
        idempotency_key="a5-independent-key",
        status=ScanStatus.COMPLETED,
        stage=ScanStage.COMPLETED,
        progress=100,
        project=_project(),
        components=actual_components,
        ai_assets=[],
        licenses=actual_licenses,
        evidence=actual_evidence,
        obligations=[],
        findings=actual_findings,
        remediations=actual_remediations,
        summary=ScanSummary(
            component_count=len(actual_components),
            ai_asset_count=0,
            evidence_count=len(actual_evidence),
            finding_counts=counts,
        ),
        provenance=_provenance(),
        errors=[],
        report_links=[],
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
    )


def _empty_run() -> ScanRun:
    return _run(components=[], licenses=[], evidence=[], findings=[], remediations=[])


def _valid_response(payload: str, *, evidence_id: str = _BOUND_EVIDENCE_ID) -> str:
    finding_id = json.loads(payload)["finding"]["id"]
    return json.dumps(
        {
            "schema_version": "openguard.ai-remediation/v1",
            "finding_id": finding_id,
            "summary": "Human review is required for the cited evidence.",
            "steps": [
                "Record the human review decision.",
                "Verify the applicable distribution context.",
            ],
            "evidence_ids": [evidence_id],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


class IndependentProvider:
    def __init__(
        self,
        *,
        mode: str = "local",
        replies: list[object] | None = None,
        producer: ProducerRef | object | None = None,
    ) -> None:
        self.mode = mode
        self.producer = _ai_producer() if producer is None else producer
        self.replies = list(replies or [])
        self.calls: list[tuple[str, float]] = []

    def generate(self, payload: str, timeout_seconds: float) -> object:
        self.calls.append((payload, timeout_seconds))
        if not self.replies:
            return _valid_response(payload)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if callable(reply):
            return reply(payload)
        return reply


def _assert_deterministic_facts_unchanged(before: ScanRun, after: ScanRun) -> None:
    for field in (
        "project",
        "components",
        "ai_assets",
        "licenses",
        "evidence",
        "obligations",
        "summary",
        "report_links",
        "created_at",
        "started_at",
        "finished_at",
    ):
        assert getattr(after, field) == getattr(before, field)
    for old, new in zip(before.findings, after.findings, strict=True):
        assert old.model_dump(mode="python", exclude={"remediation_id"}) == new.model_dump(
            mode="python", exclude={"remediation_id"}
        )


def _assert_degraded_invalid(before: ScanRun, result: object) -> None:
    assert result.status == "degraded"  # type: ignore[attr-defined]
    after = result.run  # type: ignore[attr-defined]
    assert after.status is ScanStatus.COMPLETED
    assert after.remediations == []
    assert all(finding.remediation_id is None for finding in after.findings)
    ai_errors = [error for error in after.errors if error.stage is ScanStage.AI_ASSIST]
    assert len(ai_errors) == 1
    assert ai_errors[0].code == "ai_response_invalid"
    assert ai_errors[0].message == "AI remediation response was rejected."
    assert ai_errors[0].recoverable is True
    assert after.errors[:-1] == before.errors
    _assert_deterministic_facts_unchanged(before, after)


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_valid_local_remote_generate_pending_remediation_with_stable_id(mode: str) -> None:
    run = _run()
    provider = IndependentProvider(mode=mode)
    first = apply_ai_remediations(run, provider, timeout_seconds=3)
    repeat = apply_ai_remediations(_run(), IndependentProvider(mode=mode), timeout_seconds=3.0)

    assert first.status == "generated"
    assert len(provider.calls) == 1
    assert provider.calls[0][1] == 3.0
    remediation = first.run.remediations[0]
    assert remediation.verification_status is VerificationStatus.PENDING
    assert remediation.generated_by == _ai_producer()
    assert remediation.finding_id == _FINDING_ID
    assert first.run.findings[0].remediation_id == remediation.id
    assert first.run.status is ScanStatus.COMPLETED
    assert first.run.remediations == repeat.run.remediations
    assert first.run.provenance.ai_enabled is True
    assert first.run.provenance.ai_model == _ai_producer()
    _assert_deterministic_facts_unchanged(run, first.run)


def test_canonical_payload_only_contains_bound_resource_license_and_evidence() -> None:
    provider = IndependentProvider(
        replies=[lambda payload: _valid_response(payload, evidence_id=_BOUND_LICENSE_EVIDENCE_ID)]
    )
    result = apply_ai_remediations(_run(), provider)
    raw_payload = provider.calls[0][0]
    payload = json.loads(raw_payload)

    assert result.status == "generated"
    assert raw_payload == json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert payload["schema_version"] == "openguard.ai-remediation-input/v1"
    assert payload["language"] == "en"
    assert payload["finding"]["resource_id"] == _BOUND_COMPONENT_ID
    assert [item["id"] for item in payload["evidence"]] == [_BOUND_EVIDENCE_ID]
    assert [item["id"] for item in payload["licenses"]] == [_BOUND_LICENSE_ID]
    assert [item["id"] for item in payload["license_evidence"]] == [_BOUND_LICENSE_EVIDENCE_ID]
    for forbidden_id in (
        _UNBOUND_COMPONENT_ID,
        _UNBOUND_EVIDENCE_ID,
        _UNBOUND_LICENSE_ID,
        _UNBOUND_LICENSE_EVIDENCE_ID,
    ):
        assert forbidden_id not in raw_payload
    assert result.run.remediations[0].evidence_ids == [_BOUND_LICENSE_EVIDENCE_ID]


def test_only_eligible_unbound_findings_are_called_and_prebound_is_preserved() -> None:
    prebound = _finding(
        _SECOND_FINDING_ID,
        resource_id=_UNBOUND_COMPONENT_ID,
        evidence_ids=[_UNBOUND_EVIDENCE_ID],
        outcome=FindingOutcome.UNKNOWN,
        remediation_id=_PREBOUND_REMEDIATION_ID,
    )
    run = _run(findings=[_finding(), prebound], remediations=[_prebound_remediation()])
    provider = IndependentProvider()
    result = apply_ai_remediations(run, provider)

    assert result.status == "generated"
    assert len(provider.calls) == 1
    assert result.run.findings[1].remediation_id == _PREBOUND_REMEDIATION_ID
    assert len(result.run.remediations) == 2
    assert result.run.remediations[1].id != _PREBOUND_REMEDIATION_ID


def test_zero_candidates_skips_without_generate_call() -> None:
    run = _empty_run()
    provider = IndependentProvider()
    result = apply_ai_remediations(run, provider)

    assert result.status == "skipped"
    assert result.run is run
    assert provider.calls == []


def test_disabled_ai_is_no_error_and_preserves_deterministic_run() -> None:
    run = _run()
    result = apply_ai_remediations(run, None, enabled=False)

    assert result.status == "disabled"
    assert result.run.model_dump(mode="json") == run.model_dump(mode="json")
    assert result.run.provenance.ai_enabled is False
    assert result.run.provenance.ai_model is None


def test_provider_metadata_is_snapshotted_before_generation() -> None:
    class MutatingProvider(IndependentProvider):
        def generate(self, payload: str, timeout_seconds: float) -> object:
            self.producer.model_id = "mutated-after-snapshot"  # type: ignore[union-attr]
            self.mode = "remote"
            return super().generate(payload, timeout_seconds)

    provider = MutatingProvider()
    result = apply_ai_remediations(_run(), provider)
    remediation = result.run.remediations[0]

    assert remediation.generated_by.model_id == "independent-model@sha256:fixture"
    assert result.run.provenance.ai_model == _ai_producer()
    assert _ai_producer() in result.run.provenance.tool_versions
    provider.producer.model_id = "mutated-again"  # type: ignore[union-attr]
    assert remediation.generated_by.model_id == "independent-model@sha256:fixture"


def test_invalid_provider_and_timeout_fail_before_generate_and_are_sanitized() -> None:
    class RaisingMode:
        @property
        def mode(self) -> str:
            raise RuntimeError("authorization=synthetic /tmp/provider")

    class RaisingProducer:
        mode = "local"

        @property
        def producer(self) -> ProducerRef:
            raise RuntimeError("token=synthetic")

    invalid_providers: list[object] = [
        object(),
        IndependentProvider(mode="edge"),
        IndependentProvider(producer=_human_producer()),
        RaisingMode(),
        RaisingProducer(),
    ]
    for candidate in invalid_providers:
        with pytest.raises(AIProviderError) as raised:
            apply_ai_remediations(_run(), candidate)  # type: ignore[arg-type]
        assert raised.value.code == "ai_invalid_argument"
        assert raised.value.__cause__ is None
        assert "synthetic" not in str(raised.value)

    for timeout in (True, 0, -1, float("nan"), float("inf"), "10", None):
        provider = IndependentProvider()
        with pytest.raises(AIProviderError) as raised:
            apply_ai_remediations(_run(), provider, timeout_seconds=timeout)  # type: ignore[arg-type]
        assert raised.value.code == "ai_invalid_argument"
        assert provider.calls == []


def test_invalid_p0_aggregate_fails_before_provider_execution() -> None:
    run = _run()
    run.summary.component_count += 1
    provider = IndependentProvider()

    with pytest.raises(AIProviderError) as raised:
        apply_ai_remediations(run, provider)
    assert raised.value.code == "ai_invalid_argument"
    assert raised.value.__cause__ is None
    assert provider.calls == []


def _invalid_response(case: str, payload: str) -> object:
    finding_id = json.loads(payload)["finding"]["id"]
    valid = json.loads(_valid_response(payload))
    if case == "duplicate_key":
        return (
            '{"schema_version":"openguard.ai-remediation/v1",'
            f'"finding_id":{json.dumps(finding_id)},"summary":"one",'
            '"summary":"two","steps":["one"],'
            f'"evidence_ids":[{json.dumps(_BOUND_EVIDENCE_ID)}]}}'
        )
    if case == "nonfinite":
        return (
            '{"schema_version":"openguard.ai-remediation/v1",'
            f'"finding_id":{json.dumps(finding_id)},"summary":NaN,'
            '"steps":["one"],'
            f'"evidence_ids":[{json.dumps(_BOUND_EVIDENCE_ID)}]}}'
        )
    if case == "truncated":
        return _valid_response(payload)[:-1]
    if case == "non_string":
        return {"schema_version": "openguard.ai-remediation/v1"}
    if case == "not_object":
        return "[]"
    if case == "too_large":
        valid["summary"] = "x" * (64 * 1024)
    elif case == "extra":
        valid["extra"] = "reject"
    elif case == "wrong_finding":
        valid["finding_id"] = _SECOND_FINDING_ID
    elif case == "unknown_evidence":
        valid["evidence_ids"] = ["evd_523e4567-e89b-12d3-a456-426614174000"]
    elif case == "duplicate_evidence":
        valid["evidence_ids"] = [_BOUND_EVIDENCE_ID, _BOUND_EVIDENCE_ID]
    elif case == "blank_summary":
        valid["summary"] = "   "
    elif case == "long_summary":
        valid["summary"] = "x" * 1001
    elif case == "empty_steps":
        valid["steps"] = []
    elif case == "long_step":
        valid["steps"] = ["x" * 1001]
    elif case == "non_string_step":
        valid["steps"] = ["valid", 7]
    elif case == "wrong_schema":
        valid["schema_version"] = "wrong/v1"
    elif case == "missing_field":
        del valid["summary"]
    else:
        raise AssertionError(f"unknown response case: {case}")
    return json.dumps(valid, ensure_ascii=False, separators=(",", ":"))


@pytest.mark.parametrize("case", ["shape", "reference", "limits"])
def test_invalid_response_shape_reference_and_limits_degrade_without_partial_publish(case: str) -> None:
    cases = {
        "shape": [
            "duplicate_key",
            "nonfinite",
            "truncated",
            "non_string",
            "not_object",
            "extra",
            "wrong_schema",
            "missing_field",
        ],
        "reference": ["wrong_finding", "unknown_evidence", "duplicate_evidence"],
        "limits": ["blank_summary", "long_summary", "empty_steps", "long_step", "non_string_step", "too_large"],
    }
    failures: list[str] = []
    for response_case in cases[case]:
        before = _run()
        provider = IndependentProvider(
            replies=[lambda payload, response_case=response_case: _invalid_response(response_case, payload)]
        )
        try:
            result = apply_ai_remediations(before, provider)
            _assert_degraded_invalid(before, result)
        except Exception as exc:  # keep all independent cases visible in one high-value test
            failures.append(f"{response_case}: {exc}")
    assert not failures, "\n".join(failures)


def test_sensitive_unix_windows_and_unc_output_fragments_are_rejected_and_not_leaked() -> None:
    cases = {
        "credential": "authorization=synthetic-value",
        "unix_path": "Inspect /etc/passwd before distribution.",
        "windows_path": r"Inspect C:\Windows\System32\config.",
        "unc_path": r"Inspect \\server\share\license.txt.",
    }
    failures: list[str] = []
    for case, text in cases.items():
        before = _run()

        def reply(payload: str, *, text: str = text) -> str:
            value = json.loads(_valid_response(payload))
            value["summary"] = text
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

        try:
            result = apply_ai_remediations(before, IndependentProvider(replies=[reply]))
            _assert_degraded_invalid(before, result)
            serialized = result.run.model_dump_json()
            assert text not in serialized
        except Exception as exc:
            failures.append(f"{case}: {exc}")
    assert not failures, "\n".join(failures)


def test_provider_exception_and_timeout_degrade_with_fixed_error_and_preserve_completed_chain() -> None:
    failures: list[str] = []
    for label, exception in (
        ("provider", RuntimeError("token=synthetic /tmp/provider")),
        ("timeout", TimeoutError("authorization=synthetic /tmp/provider")),
    ):
        before = _run()
        provider = IndependentProvider(replies=[exception])
        try:
            result = apply_ai_remediations(before, provider)
            assert result.status == "degraded"
            assert result.run.status is ScanStatus.COMPLETED
            assert result.run.remediations == []
            assert result.run.errors[-1].code == "ai_provider_unavailable"
            assert result.run.errors[-1].message == "AI remediation provider was unavailable."
            assert result.run.errors[-1].stage is ScanStage.AI_ASSIST
            assert "synthetic" not in result.run.model_dump_json()
            assert result.run.errors[:-1] == before.errors
            _assert_deterministic_facts_unchanged(before, result.run)
        except Exception as exc:
            failures.append(f"{label}: {exc}")
    assert not failures, "\n".join(failures)


def test_second_batch_failure_is_atomic_and_does_not_publish_first_remediation() -> None:
    second = _finding(
        _SECOND_FINDING_ID,
        resource_id=_UNBOUND_COMPONENT_ID,
        evidence_ids=[_UNBOUND_EVIDENCE_ID],
        outcome=FindingOutcome.UNKNOWN,
    )
    before = _run(findings=[_finding(), second])
    provider = IndependentProvider(
        replies=[lambda payload: _valid_response(payload), RuntimeError("token=synthetic")]
    )
    result = apply_ai_remediations(before, provider)

    assert result.status == "degraded"
    assert len(provider.calls) == 2
    assert result.run.remediations == []
    assert [finding.remediation_id for finding in result.run.findings] == [None, None]
    assert result.run.errors[-1].code == "ai_provider_unavailable"
    assert result.run.errors[:-1] == before.errors
    _assert_deterministic_facts_unchanged(before, result.run)


def test_repeated_same_degradation_does_not_duplicate_diagnostic() -> None:
    first = apply_ai_remediations(
        _run(), IndependentProvider(replies=[RuntimeError("secret=synthetic")])
    )
    second = apply_ai_remediations(
        first.run, IndependentProvider(replies=[RuntimeError("secret=synthetic-again")])
    )

    assert first.status == second.status == "degraded"
    assert [error.code for error in first.run.errors].count("ai_provider_unavailable") == 1
    assert [error.code for error in second.run.errors].count("ai_provider_unavailable") == 1
    assert second.run.errors == first.run.errors
    assert second.run.remediations == []
    assert second.run.status is ScanStatus.COMPLETED
