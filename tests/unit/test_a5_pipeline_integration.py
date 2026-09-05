"""A5-1c implementation tests for the B5 -> AI_ASSIST -> A6 vertical slice."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_default_app
from app.domain.models import (
    ProducerRef,
    ProducerType,
    ReportFormat,
    ScanRun,
    ScanStage,
    ScanStatus,
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


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "examples" / "sample-scan-result.json").read_text())
NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


class RecordingProvider:
    mode = "local"

    def __init__(self, *, fail: bool = False) -> None:
        self.producer = ProducerRef(
            type=ProducerType.AI,
            name="a5-pipeline-test-provider",
            version="1.0.0",
            provider="local-test",
            model_id="test-model@sha256:" + "a" * 64,
            prompt_schema_digest={"algorithm": "sha256", "value": "b" * 64},
            config_digest={"algorithm": "sha256", "value": "c" * 64},
        )
        self.fail = fail
        self.calls: list[tuple[dict[str, object], float]] = []

    def generate(self, payload: str, timeout_seconds: float) -> str:
        request = json.loads(payload)
        self.calls.append((request, timeout_seconds))
        if self.fail:
            raise RuntimeError("provider-private-detail")
        finding = request["finding"]
        evidence_ids = finding["evidence_ids"]
        return json.dumps(
            {
                "schema_version": "openguard.ai-remediation/v1",
                "finding_id": finding["id"],
                "summary": "Review the pending license evidence before distribution.",
                "steps": ["Verify the cited license evidence with a human reviewer."],
                "evidence_ids": [evidence_ids[0]],
            }
        )


def _rules_input(*, verified: bool, queued: bool = False) -> ScanRun:
    value = copy.deepcopy(SAMPLE)
    value.update(
        status="queued" if queued else "running",
        stage="queued" if queued else "rules",
        progress=0 if queued else 70,
        started_at=None if queued else value["started_at"],
        finished_at=None,
    )
    value["ai_assets"] = []
    value["obligations"] = []
    value["findings"] = []
    value["remediations"] = []
    value["errors"] = []
    value["report_links"] = []
    status = "verified" if verified else "pending"
    value["licenses"][0]["verification_status"] = status
    value["evidence"][2]["verification_status"] = status
    value["summary"] = {
        "component_count": 1,
        "ai_asset_count": 0,
        "evidence_count": 3,
        "finding_counts": {
            "pass": 0,
            "warning": 0,
            "review_required": 0,
            "unknown": 0,
        },
    }
    return ScanRun.model_validate(value)


def _plan(provider: RecordingProvider | None, *, enabled: bool) -> PipelinePlan:
    return build_dependency_plan(
        lambda run: run,
        DependencyPlanState(),
        ingestion_error_code="ingestion_failed",
        ingestion_error_message="Ingestion failed.",
        ai_provider=provider,
        ai_enabled=enabled,
        ai_timeout_seconds=7.5,
    )


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    return path


def test_ai_disabled_preserves_pending_b5_result_without_provider_call() -> None:
    provider = RecordingProvider()
    plan = _plan(provider, enabled=False)
    rules_result = plan.steps[4].handler(_rules_input(verified=False))

    result = plan.steps[5].handler(rules_result)

    assert result == rules_result
    assert result.provenance.ai_enabled is False
    assert result.provenance.ai_model is None
    assert provider.calls == []


def test_pending_b5_finding_is_enriched_without_rewriting_facts() -> None:
    provider = RecordingProvider()
    plan = _plan(provider, enabled=True)
    rules_result = plan.steps[4].handler(_rules_input(verified=False))
    immutable_fields = {
        name: getattr(rules_result, name)
        for name in ("components", "ai_assets", "licenses", "evidence", "obligations", "summary")
    }

    result = plan.steps[5].handler(rules_result)

    assert len(provider.calls) == 1
    assert provider.calls[0][1] == 7.5
    assert provider.calls[0][0]["finding"]["rule_id"] == "license-evidence-gate"
    assert result.provenance.ai_enabled is True
    assert result.provenance.ai_model == provider.producer
    assert len(result.remediations) == 1
    assert result.remediations[0].verification_status is VerificationStatus.PENDING
    assert result.findings[0].remediation_id == result.remediations[0].id
    assert result.remediations[0].evidence_ids == result.findings[0].evidence_ids
    for name, expected in immutable_fields.items():
        assert getattr(result, name) == expected


def test_verified_b5_remediation_is_not_duplicated_by_ai() -> None:
    provider = RecordingProvider()
    plan = _plan(provider, enabled=True)
    rules_result = plan.steps[4].handler(_rules_input(verified=True))

    result = plan.steps[5].handler(rules_result)

    assert result == rules_result
    assert len(result.remediations) == 1
    assert result.remediations[0].generated_by.type is ProducerType.RULE_ENGINE
    assert provider.calls == []


@pytest.mark.parametrize("source_type", ["zip", "git"])
def test_source_specific_plans_forward_ai_configuration(tmp_path: Path, source_type: str) -> None:
    provider = RecordingProvider()
    if source_type == "zip":
        plan = build_local_zip_dependency_plan(
            tmp_path / "project.zip",
            tmp_path / "workspace",
            clock=lambda: NOW,
            ai_provider=provider,
            ai_enabled=True,
            ai_timeout_seconds=4.0,
        )
    else:
        plan = build_public_git_dependency_plan(
            "https://github.com/example/project.git",
            tmp_path / "workspace",
            clock=lambda: NOW,
            ai_provider=provider,
            ai_enabled=True,
            ai_timeout_seconds=4.0,
        )
    rules_result = plan.steps[4].handler(_rules_input(verified=False))

    result = plan.steps[5].handler(rules_result)

    assert result.provenance.ai_model == provider.producer
    assert len(result.remediations) == 1
    assert provider.calls[0][1] == 4.0


def test_provider_failure_preserves_b5_and_still_publishes_a6_reports(tmp_path: Path) -> None:
    provider = RecordingProvider(fail=True)
    ai_handler = _plan(provider, enabled=True).steps[5].handler
    queued = _rules_input(verified=False, queued=True)
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    registry.create(queued)
    store = ReportArtifactStore(_private(tmp_path / "reports"), clock=lambda: NOW)
    stages = (
        ScanStage.INGESTION,
        ScanStage.INVENTORY,
        ScanStage.SCAN,
        ScanStage.NORMALIZE,
        ScanStage.RULES,
        ScanStage.AI_ASSIST,
        ScanStage.REPORT,
    )
    plan = PipelinePlan(
        steps=tuple(
            PipelineStep(
                stage,
                apply_license_rules
                if stage is ScanStage.RULES
                else ai_handler
                if stage is ScanStage.AI_ASSIST
                else lambda run: run,
            )
            for stage in stages
        )
    )

    result = ScanPipelineWorker(
        registry,
        clock=lambda: NOW,
        terminal_publisher=PipelineReportPublisher(store).publish,
    ).run(queued.id, plan)

    assert (result.run.status, result.run.stage, result.run.progress) == (
        ScanStatus.COMPLETED,
        ScanStage.COMPLETED,
        100,
    )
    assert [error.code for error in result.run.errors] == ["ai_provider_unavailable"]
    assert result.run.findings[0].rule_id == "license-evidence-gate"
    assert result.run.findings[0].remediation_id is None
    assert result.run.remediations == []
    assert result.run.provenance.ai_model == provider.producer
    assert [link.format for link in result.run.report_links] == list(ReportFormat)
    report = json.loads(store.get(result.run.id, ReportFormat.JSON).content)
    assert report["scan_run"]["errors"][0]["code"] == "ai_provider_unavailable"
    assert "provider-private-detail" not in json.dumps(report)
    registry.close()


def test_enabled_ai_requires_a_provider_and_valid_timeout() -> None:
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        _plan(None, enabled=True)
    with pytest.raises(PipelineError, match="pipeline_invalid_argument"):
        build_dependency_plan(
            lambda run: run,
            DependencyPlanState(),
            ingestion_error_code="ingestion_failed",
            ingestion_error_message="Ingestion failed.",
            ai_timeout_seconds=float("nan"),
        )


def test_default_app_uses_explicit_ai_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _private(tmp_path / "runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "1")
    with TestClient(create_default_app()) as client:
        assert client.app.state.zip_scan_runtime._ai_enabled is True
        assert client.app.state.zip_scan_runtime._ai_provider.producer.name == "ollama"


def test_default_app_rejects_ambiguous_ai_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _private(tmp_path / "runtime")
    monkeypatch.setenv("OPENGUARD_DATA_DIR", str(data))
    monkeypatch.setenv("OPENGUARD_ENABLE_AI", "true")
    with pytest.raises(RuntimeError, match="invalid OPENGUARD_ENABLE_AI"):
        create_default_app()
