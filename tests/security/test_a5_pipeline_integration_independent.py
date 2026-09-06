"""Independent A5-1c acceptance checks for the B5 -> AI_ASSIST -> A6 path.

The fixtures, provider, expected values and SQLite/report assertions in this
module are constructed independently of the implementation-side A5 tests.
The real Ollama case is opt-in and never starts a service or downloads a model.
"""

from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import OllamaProvider
from app.api import create_default_app
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
    ReportFormat,
    RunEnvironment,
    RunProvenance,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    SourceType,
    VerificationStatus,
)
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import (
    PipelineError,
    PipelinePlan,
    PipelineStep,
    ScanPipelineWorker,
    apply_license_rules,
    build_local_zip_dependency_plan,
    build_public_git_dependency_plan,
)
from app.pipeline.dependency_plan import DependencyPlanState, build_dependency_plan
from app.reporting import PipelineReportPublisher, ReportArtifactStore


NOW = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
REAL_OLLAMA_GATE = "OPENGUARD_RUN_REAL_OLLAMA_A5_1C"
PIPELINE_STAGES = (
    ScanStage.INGESTION,
    ScanStage.INVENTORY,
    ScanStage.SCAN,
    ScanStage.NORMALIZE,
    ScanStage.RULES,
    ScanStage.AI_ASSIST,
    ScanStage.REPORT,
)


def _id(prefix: str, number: int) -> str:
    return f"{prefix}_00000000-0000-4000-8000-{number:012x}"


def _hash(character: str) -> HashValue:
    return HashValue(algorithm="sha256", value=character * 64)


def _human_producer() -> ProducerRef:
    return ProducerRef(type=ProducerType.HUMAN, name="independent-a5-review", version="1.0")


def _parser_producer() -> ProducerRef:
    return ProducerRef(type=ProducerType.PARSER, name="independent-a5-parser", version="1.0")


def _ai_producer() -> ProducerRef:
    return ProducerRef(
        type=ProducerType.AI,
        name="independent-a5-provider",
        version="1.0",
        provider="independent-fixture",
        model_id="fixture-model@sha256:" + "a" * 64,
        prompt_schema_digest=_hash("b"),
        config_digest=_hash("c"),
    )


class IndependentProvider:
    """A small provider double with no dependency on implementation fixtures."""

    mode = "local"

    def __init__(self, behavior: str = "valid") -> None:
        self.producer = _ai_producer()
        self.behavior = behavior
        self.calls = 0
        self.timeouts: list[float] = []
        self.rule_ids: list[str] = []

    def generate(self, payload: str, timeout_seconds: float) -> str:
        request = json.loads(payload)
        self.calls += 1
        self.timeouts.append(timeout_seconds)
        self.rule_ids.append(request["finding"]["rule_id"])
        if self.behavior == "raise":
            raise RuntimeError("provider-private-detail")

        finding = request["finding"]
        evidence_id = finding["evidence_ids"][0]
        if self.behavior == "invalid":
            evidence_id = _id("evd", 99)
        return json.dumps(
            {
                "schema_version": "openguard.ai-remediation/v1",
                "finding_id": finding["id"],
                "summary": "Review the cited license evidence before distribution.",
                "steps": ["Verify the cited evidence with a human reviewer."],
                "evidence_ids": [evidence_id],
            },
            ensure_ascii=False,
        )


def _scan_fixture(*, verified: bool, queued: bool = False) -> ScanRun:
    verification = VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
    project_id = _id("prj", 1)
    component_id = _id("cmp", 2)
    manifest_evidence_id = _id("evd", 3)
    license_evidence_id = _id("evd", 4)
    license_id = _id("lic", 5)
    run_id = _id("scn", 6)
    parser = _parser_producer()
    reviewer = _human_producer()

    component = Component(
        id=component_id,
        name="independent-demo",
        version="1.0.0",
        ecosystem="pypi",
        component_type=ComponentType.LIBRARY,
        purl="pkg:pypi/independent-demo@1.0.0",
        source_url="https://pypi.org/project/independent-demo/",
        license_expression_id=license_id,
        evidence_ids=[manifest_evidence_id],
        detected_by=[DetectionMethod.MANIFEST_PARSER],
        confidence=1.0,
    )
    evidence = [
        Evidence(
            id=manifest_evidence_id,
            kind=EvidenceKind.MANIFEST_FIELD,
            locator="pyproject.toml:project.dependencies",
            excerpt="independent-demo==1.0.0",
            start_line=1,
            end_line=1,
            content_hash=_hash("d"),
            detected_by=DetectionMethod.MANIFEST_PARSER,
            producer=parser,
            observed_at=NOW,
            verification_status=VerificationStatus.VERIFIED,
        ),
        Evidence(
            id=license_evidence_id,
            kind=EvidenceKind.LICENSE_TEXT,
            locator="LICENSE",
            excerpt="MIT License",
            content_hash=_hash("e"),
            detected_by=DetectionMethod.MANUAL,
            producer=reviewer,
            observed_at=NOW,
            verification_status=verification,
        ),
    ]
    license_expression = LicenseExpression(
        id=license_id,
        expression="MIT",
        normalized_ids=["MIT"],
        source_url="https://spdx.org/licenses/MIT.html",
        evidence_ids=[license_evidence_id],
        confidence=1.0,
        verification_status=verification,
    )
    return ScanRun(
        contract_version="0.1.1",
        id=run_id,
        idempotency_key="independent-a5-pipeline-fixture",
        status=ScanStatus.QUEUED if queued else ScanStatus.RUNNING,
        stage=ScanStage.QUEUED if queued else ScanStage.RULES,
        progress=0 if queued else 70,
        project=Project(
            id=project_id,
            name="independent-a5-pipeline",
            source_type=SourceType.ZIP,
            source="independent-a5-pipeline.zip",
            created_at=NOW,
        ),
        components=[component],
        ai_assets=[],
        licenses=[license_expression],
        evidence=evidence,
        obligations=[],
        findings=[],
        remediations=[],
        summary=ScanSummary(
            component_count=1,
            ai_asset_count=0,
            evidence_count=2,
            finding_counts={outcome: 0 for outcome in FindingOutcome},
        ),
        provenance=RunProvenance(
            input_digest=_hash("f"),
            inventory_digest=None,
            tool_versions=[parser, reviewer],
            ruleset_version="independent-before-rules",
            contract_version="0.1.1",
            ai_enabled=False,
            ai_model=None,
            run_environment=RunEnvironment(
                python_version="3.12-independent",
                platform="independent-test-platform",
                openguard_version="independent-a5",
            ),
        ),
        errors=[],
        report_links=[],
        created_at=NOW,
        started_at=None if queued else NOW,
        finished_at=None,
    )


def _rules_result(*, verified: bool) -> ScanRun:
    return apply_license_rules(_scan_fixture(verified=verified))


def _ai_handler(provider: object, *, enabled: bool = True, timeout: float = 7.25):
    plan = build_dependency_plan(
        lambda run: run,
        DependencyPlanState(),
        ingestion_error_code="independent_ingestion_failed",
        ingestion_error_message="Independent ingestion failed.",
        ai_provider=provider,
        ai_enabled=enabled,
        ai_timeout_seconds=timeout,
    )
    return plan.steps[5].handler


def _fact_snapshot(run: ScanRun) -> tuple[object, ...]:
    return (
        run.project,
        tuple(run.components),
        tuple(run.ai_assets),
        tuple(run.licenses),
        tuple(run.evidence),
        tuple(run.obligations),
        tuple(item.model_copy(update={"remediation_id": None}) for item in run.findings),
        run.summary,
    )


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def _pipeline_with_ai(ai_handler):
    def identity(run: ScanRun) -> ScanRun:
        return run

    handlers = {
        ScanStage.RULES: apply_license_rules,
        ScanStage.AI_ASSIST: ai_handler,
    }
    return PipelinePlan(
        steps=tuple(
            PipelineStep(stage, handlers.get(stage, identity)) for stage in PIPELINE_STAGES
        )
    )


def test_ai_default_disabled_makes_no_call_and_preserves_pending_b5() -> None:
    provider = IndependentProvider()
    rules_result = _rules_result(verified=False)

    result = _ai_handler(provider, enabled=False)(rules_result)

    assert result == rules_result
    assert result.provenance.ai_enabled is False
    assert result.provenance.ai_model is None
    assert result.findings[0].rule_id == "license-evidence-gate"
    assert result.findings[0].remediation_id is None
    assert provider.calls == 0


def test_pending_b5_finding_gets_pending_ai_remediation_without_fact_rewrite() -> None:
    provider = IndependentProvider()
    rules_result = _rules_result(verified=False)
    facts_before = _fact_snapshot(rules_result)

    result = _ai_handler(provider)(rules_result)

    assert provider.calls == 1
    assert provider.timeouts == [7.25]
    assert provider.rule_ids == ["license-evidence-gate"]
    assert result.provenance.ai_enabled is True
    assert result.provenance.ai_model == provider.producer
    assert len(result.remediations) == 1
    assert result.remediations[0].generated_by == provider.producer
    assert result.remediations[0].verification_status is VerificationStatus.PENDING
    assert result.findings[0].rule_id == "license-evidence-gate"
    assert result.findings[0].outcome is FindingOutcome.REVIEW_REQUIRED
    assert result.findings[0].remediation_id == result.remediations[0].id
    assert _fact_snapshot(result) == facts_before


def test_verified_b5_deterministic_remediation_is_not_duplicated() -> None:
    provider = IndependentProvider()
    rules_result = _rules_result(verified=True)
    existing_ids = [item.id for item in rules_result.remediations]

    result = _ai_handler(provider)(rules_result)

    assert result == rules_result
    assert existing_ids
    assert [item.id for item in result.remediations] == existing_ids
    assert all(item.generated_by.type is ProducerType.RULE_ENGINE for item in result.remediations)
    assert provider.calls == 0


@pytest.mark.parametrize("source_kind", ["zip", "git"])
def test_zip_and_git_plans_forward_the_same_ai_configuration(
    tmp_path: Path, source_kind: str
) -> None:
    provider = IndependentProvider()
    if source_kind == "zip":
        plan = build_local_zip_dependency_plan(
            tmp_path / "independent.zip",
            tmp_path / "workspace",
            clock=lambda: NOW,
            ai_provider=provider,
            ai_enabled=True,
            ai_timeout_seconds=4.5,
        )
    else:
        plan = build_public_git_dependency_plan(
            "https://github.com/example/independent-a5.git",
            tmp_path / "workspace",
            clock=lambda: NOW,
            ai_provider=provider,
            ai_enabled=True,
            ai_timeout_seconds=4.5,
        )

    result = plan.steps[5].handler(_rules_result(verified=False))

    assert result.provenance.ai_model == provider.producer
    assert len(result.remediations) == 1
    assert provider.timeouts == [4.5]


@pytest.mark.parametrize(
    ("behavior", "error_code", "error_message"),
    [
        ("raise", "ai_provider_unavailable", "AI remediation provider was unavailable."),
        ("invalid", "ai_response_invalid", "AI remediation response was rejected."),
    ],
)
def test_ai_degradation_commits_sqlite_and_all_four_a6_reports(
    tmp_path: Path, behavior: str, error_code: str, error_message: str
) -> None:
    provider = IndependentProvider(behavior=behavior)
    queued = _scan_fixture(verified=False, queued=True)
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    registry.create(
        queued,
        idempotency_fingerprint=hashlib.sha256(
            b"independent-a5-pipeline-fixture"
        ).hexdigest(),
    )
    report_root = _private_directory(tmp_path / "reports")
    store = ReportArtifactStore(report_root, clock=lambda: NOW)

    try:
        result = ScanPipelineWorker(
            registry,
            clock=lambda: NOW,
            terminal_publisher=PipelineReportPublisher(store).publish,
        ).run(queued.id, _pipeline_with_ai(_ai_handler(provider, timeout=8.0)))

        assert (result.run.status, result.run.stage, result.run.progress) == (
            ScanStatus.COMPLETED,
            ScanStage.COMPLETED,
            100,
        )
        assert provider.calls == 1
        assert [error.code for error in result.run.errors] == [error_code]
        assert result.run.errors[0].message == error_message
        assert result.run.findings[0].rule_id == "license-evidence-gate"
        assert result.run.findings[0].remediation_id is None
        assert result.run.remediations == []
        assert result.run.provenance.ai_model == provider.producer
        assert [link.format for link in result.run.report_links] == list(ReportFormat)
        assert registry.get(queued.id).run == result.run

        report = json.loads(store.get(queued.id, ReportFormat.JSON).content)
        serialized_report = json.dumps(report, ensure_ascii=False)
        assert report["scan_run"]["errors"][0]["code"] == error_code
        assert "provider-private-detail" not in serialized_report
        for report_format in ReportFormat:
            assert store.get(queued.id, report_format).link.format is report_format
    finally:
        registry.close()


def test_invalid_provider_response_degrades_without_partial_ai_remediation() -> None:
    provider = IndependentProvider(behavior="invalid")
    rules_result = _rules_result(verified=False)
    facts_before = _fact_snapshot(rules_result)

    result = _ai_handler(provider)(rules_result)

    assert provider.calls == 1
    assert [error.code for error in result.errors] == ["ai_response_invalid"]
    assert result.errors[0].message == "AI remediation response was rejected."
    assert result.remediations == []
    assert result.findings[0].remediation_id is None
    assert _fact_snapshot(result) == facts_before
    assert result.provenance.ai_model == provider.producer


def test_pipeline_rejects_missing_provider_and_non_finite_timeout() -> None:
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        _ai_handler(None, enabled=True)
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        build_dependency_plan(
            lambda run: run,
            DependencyPlanState(),
            ingestion_error_code="independent_ingestion_failed",
            ingestion_error_message="Independent ingestion failed.",
            ai_timeout_seconds=float("nan"),
        )
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        build_dependency_plan(
            lambda run: run,
            DependencyPlanState(),
            ingestion_error_code="independent_ingestion_failed",
            ingestion_error_message="Independent ingestion failed.",
            ai_enabled=True,
            ai_provider=IndependentProvider(),
            ai_timeout_seconds=0,
        )


def test_default_app_has_closed_ai_toggle_and_rejects_ambiguous_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    disabled_root = _private_directory(tmp_path / "disabled-runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(disabled_root))
    monkeypatch.delenv("OPENGUARD_ENABLE_AI", raising=False)
    with TestClient(create_default_app()) as client:
        runtime = client.app.state.zip_scan_runtime
        assert runtime._ai_enabled is False
        assert runtime._ai_provider is None

    enabled_root = _private_directory(tmp_path / "enabled-runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(enabled_root))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "1")
    with TestClient(create_default_app()) as client:
        runtime = client.app.state.zip_scan_runtime
        assert runtime._ai_enabled is True
        assert runtime._ai_provider.producer.name == "ollama"

    invalid_root = _private_directory(tmp_path / "invalid-runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(invalid_root))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "true")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_AI"):
        create_default_app()


@pytest.mark.skipif(
    os.environ.get(REAL_OLLAMA_GATE) != "1",
    reason=f"set {REAL_OLLAMA_GATE}=1 for an explicit local Ollama/Qwen3 run",
)
def test_explicit_real_ollama_pending_b5_to_sqlite_and_a6_reports(tmp_path: Path) -> None:
    """Run only against an already-running, already-installed locked Ollama model."""

    provider = OllamaProvider()
    queued = _scan_fixture(verified=False, queued=True)
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    registry.create(
        queued,
        idempotency_fingerprint=hashlib.sha256(
            b"independent-a5-pipeline-fixture"
        ).hexdigest(),
    )
    report_root = _private_directory(tmp_path / "reports")
    store = ReportArtifactStore(report_root, clock=lambda: NOW)

    try:
        result = ScanPipelineWorker(
            registry,
            clock=lambda: NOW,
            terminal_publisher=PipelineReportPublisher(store).publish,
        ).run(queued.id, _pipeline_with_ai(_ai_handler(provider, timeout=60.0)))

        assert result.run.status is ScanStatus.COMPLETED
        assert result.run.stage is ScanStage.COMPLETED
        assert result.run.provenance.ai_model == provider.producer
        assert len(result.run.remediations) == 1
        assert result.run.remediations[0].generated_by == provider.producer
        assert result.run.remediations[0].verification_status is VerificationStatus.PENDING
        assert result.run.findings[0].remediation_id == result.run.remediations[0].id
        assert [link.format for link in result.run.report_links] == list(ReportFormat)
        assert registry.get(queued.id).run == result.run
        assert json.loads(store.get(queued.id, ReportFormat.JSON).content)["scan_run"]["stage"] == "completed"
    finally:
        registry.close()
