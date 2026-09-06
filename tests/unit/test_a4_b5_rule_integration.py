"""A4 integration tests for the teammate-owned B5 rule engine."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.models import ScanRun, ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import (
    PipelinePlan,
    PipelineStageFailure,
    PipelineStep,
    ScanPipelineWorker,
    apply_license_rules,
)
from app.pipeline.dependency_plan import DependencyPlanState, build_dependency_plan
from app.rules import load_ruleset


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "examples" / "sample-scan-result.json").read_text())


def _rules_input(*, verified: bool) -> ScanRun:
    value = copy.deepcopy(SAMPLE)
    value.update(status="running", stage="rules", progress=70, finished_at=None)
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


def test_verified_license_fact_produces_b5_aggregate_and_ruleset_provenance() -> None:
    result = apply_license_rules(_rules_input(verified=True))

    assert len(result.obligations) == len(result.findings) == len(result.remediations) == 1
    assert result.findings[0].rule_id == "LIC-MIT-NOTICE"
    assert result.findings[0].remediation_id == result.remediations[0].id
    assert result.remediations[0].generated_by.name == "openguard-license-rules"
    assert result.summary.finding_counts["review_required"] == 1
    assert result.provenance.ruleset_version == "2026.09.1"


def test_imported_ruleset_retains_fifteen_teammate_rules() -> None:
    ruleset = load_ruleset()

    assert ruleset.version == "2026.09.1"
    assert len(ruleset.rules) == 15


def test_pending_license_fact_remains_review_required_for_later_ai_assist() -> None:
    result = apply_license_rules(_rules_input(verified=False))

    assert not result.obligations
    assert not result.remediations
    assert result.findings[0].rule_id == "license-evidence-gate"
    assert result.findings[0].remediation_id is None
    assert result.summary.finding_counts["review_required"] == 1


def test_missing_license_fact_is_recoverable_and_does_not_invent_results() -> None:
    value = _rules_input(verified=False).model_dump(mode="python")
    value["components"][0]["license_expression_id"] = None
    value["licenses"] = []
    run = ScanRun.model_validate(value)

    with pytest.raises(PipelineStageFailure) as raised:
        apply_license_rules(run)

    assert raised.value.code == "license_facts_unavailable"
    assert raised.value.recoverable is True


def test_existing_rule_results_are_not_overwritten() -> None:
    value = _rules_input(verified=False).model_dump(mode="python")
    value["findings"] = copy.deepcopy(SAMPLE["findings"])
    value["obligations"] = copy.deepcopy(SAMPLE["obligations"])
    value["remediations"] = copy.deepcopy(SAMPLE["remediations"])
    value["summary"]["finding_counts"]["review_required"] = 1
    run = ScanRun.model_validate(value)

    with pytest.raises(PipelineStageFailure) as raised:
        apply_license_rules(run)

    assert raised.value.code == "license_rule_state_conflict"
    assert raised.value.recoverable is False


def test_non_b5_evaluator_result_fails_closed() -> None:
    with pytest.raises(PipelineStageFailure) as raised:
        apply_license_rules(
            _rules_input(verified=True),
            evaluator=lambda *_args, **_kwargs: object(),  # type: ignore[arg-type]
        )

    assert raised.value.code == "license_rules_failed"
    assert raised.value.recoverable is False


def test_shared_dependency_plan_routes_license_facts_to_b5_adapter() -> None:
    plan = build_dependency_plan(
        lambda run: run,
        DependencyPlanState(),
        ingestion_error_code="ingestion_failed",
        ingestion_error_message="Ingestion failed.",
    )

    result = plan.steps[4].handler(_rules_input(verified=True))

    assert plan.steps[4].stage is ScanStage.RULES
    assert result.findings[0].rule_id == "LIC-MIT-NOTICE"
    assert result.provenance.ruleset_version == "2026.09.1"


def test_a4_worker_persists_verified_b5_result(tmp_path: Path) -> None:
    value = _rules_input(verified=True).model_dump(mode="python")
    value.update(status="queued", stage="queued", progress=0, started_at=None, finished_at=None)
    queued = ScanRun.model_validate(value)
    registry = SQLiteScanRunRegistry(tmp_path / "runs.sqlite")
    registry.create(queued)

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
            PipelineStep(stage, apply_license_rules if stage is ScanStage.RULES else lambda run: run)
            for stage in stages
        )
    )
    result = ScanPipelineWorker(
        registry,
        clock=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc),
    ).run(queued.id, plan)

    assert result.run.status is ScanStatus.COMPLETED
    assert result.run.stage is ScanStage.COMPLETED
    assert result.run.findings[0].rule_id == "LIC-MIT-NOTICE"
    assert registry.get(queued.id).run == result.run
