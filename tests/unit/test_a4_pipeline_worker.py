"""Implementation-side regression tests for the frozen A4-0 worker."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.domain.models import ScanRun, ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import PipelineError, PipelinePlan, PipelineStageFailure, PipelineStep, ScanPipelineWorker


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = json.loads((ROOT / "examples" / "sample-scan-result.json").read_text())
BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CASE_IDS = tuple([*(f"POS-A4-{value:03d}" for value in range(1, 6)), *(f"NEG-A4-{value:03d}" for value in range(1, 11))])


def _run(index: int = 1) -> ScanRun:
    value = copy.deepcopy(SAMPLE)
    value["id"] = f"scn_123e4567-e89b-12d3-a456-426614174{index:03d}"
    value["project"]["id"] = f"prj_123e4567-e89b-12d3-a456-426614174{index:03d}"
    value["created_at"] = (BASE_TIME + timedelta(seconds=index)).isoformat().replace("+00:00", "Z")
    value.update(status="queued", stage="queued", progress=0, started_at=None, finished_at=None, errors=[])
    return ScanRun.model_validate(value)


def _changed(run: ScanRun, **changes: object) -> ScanRun:
    value = run.model_dump(mode="python")
    value.update(changes)
    return ScanRun.model_validate(value)


def _empty_run(index: int) -> ScanRun:
    value = _run(index).model_dump(mode="python")
    value.update(
        components=[], ai_assets=[], licenses=[], evidence=[], obligations=[], findings=[], remediations=[], report_links=[],
        summary={"component_count": 0, "ai_asset_count": 0, "evidence_count": 0, "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0}},
    )
    return ScanRun.model_validate(value)


def _registry(tmp_path: Path) -> SQLiteScanRunRegistry:
    return SQLiteScanRunRegistry(tmp_path / "runs.sqlite")


def _plan(*, failure_at: ScanStage | None = None, failure: PipelineStageFailure | None = None, cancel: SQLiteScanRunRegistry | None = None, invalid_output: bool = False) -> PipelinePlan:
    steps: list[PipelineStep] = []
    for stage in (ScanStage.INGESTION, ScanStage.INVENTORY, ScanStage.SCAN, ScanStage.NORMALIZE, ScanStage.RULES, ScanStage.AI_ASSIST, ScanStage.REPORT):
        def handler(run: ScanRun, stage: ScanStage = stage) -> ScanRun:
            if cancel is not None and stage is ScanStage.SCAN:
                cancel.replace(_changed(run, status=ScanStatus.CANCELLED, finished_at=run.started_at), expected_revision=cancel.get(run.id).revision)
            if failure_at is stage:
                assert failure is not None
                raise failure
            if invalid_output and stage is ScanStage.INGESTION:
                return "not-a-run"  # type: ignore[return-value]
            return run
        steps.append(PipelineStep(stage=stage, handler=handler))
    return PipelinePlan(steps=tuple(steps))


def _error(callable_: object, code: str) -> None:
    with pytest.raises(PipelineError) as raised:
        callable_()  # type: ignore[operator]
    assert raised.value.code == code
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_a4_frozen_case_ids_are_discoverable(case_id: str) -> None:
    assert case_id.startswith(("POS-A4-", "NEG-A4-"))


def test_pos_a4_001_002_003_full_plan_persists_completed_across_restart(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_run())
    seen: list[tuple[ScanStage, int, ScanStatus]] = []
    def recording_plan(run: ScanRun) -> ScanRun:
        seen.append((run.stage, run.progress, run.status))
        return run
    plan = PipelinePlan(steps=tuple(PipelineStep(stage, recording_plan) for stage in (ScanStage.INGESTION, ScanStage.INVENTORY, ScanStage.SCAN, ScanStage.NORMALIZE, ScanStage.RULES, ScanStage.AI_ASSIST, ScanStage.REPORT)))
    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(queued.run.id, plan)
    assert result.run.status is ScanStatus.COMPLETED and result.run.stage is ScanStage.COMPLETED and result.run.progress == 100
    assert seen == [(stage, progress, ScanStatus.RUNNING) for stage, progress in ((ScanStage.INGESTION, 5), (ScanStage.INVENTORY, 15), (ScanStage.SCAN, 35), (ScanStage.NORMALIZE, 55), (ScanStage.RULES, 70), (ScanStage.AI_ASSIST, 85), (ScanStage.REPORT, 95))]
    assert result.run.started_at == BASE_TIME + timedelta(days=1)
    registry.close()
    reopened = _registry(tmp_path)
    assert reopened.get(queued.run.id).run == result.run


def test_pos_a4_004_recoverable_failure_with_aggregate_is_partial(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_run())
    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(queued.run.id, _plan(failure_at=ScanStage.RULES, failure=PipelineStageFailure("rules_timeout", "Rules adapter timed out.", True)))
    assert result.run.status is ScanStatus.PARTIAL
    assert result.run.stage is ScanStage.RULES and result.run.progress == 70
    assert result.run.errors[-1].code == "rules_timeout" and result.run.errors[-1].recoverable is True


def test_pos_a4_005_cancelled_winner_is_not_overwritten(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_run())
    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(queued.run.id, _plan(cancel=registry))
    assert result.run.status is ScanStatus.CANCELLED
    assert registry.get(queued.run.id) == result


def test_neg_a4_001_002_rejects_invalid_plan_and_nonqueued_before_handlers(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_run())
    _error(lambda: ScanPipelineWorker(registry).run(queued.run.id, PipelinePlan(steps=())), "pipeline_invalid_argument")
    _error(lambda: ScanPipelineWorker(registry).run("bad", _plan()), "pipeline_invalid_argument")
    running = _changed(queued.run, status=ScanStatus.RUNNING, stage=ScanStage.INGESTION, progress=5, started_at=BASE_TIME + timedelta(days=1))
    registry.replace(running, expected_revision=queued.revision)
    _error(lambda: ScanPipelineWorker(registry).run(queued.run.id, _plan()), "pipeline_not_claimable")


def test_neg_a4_004_005_006_failure_is_sanitized_and_terminal(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_empty_run(1))
    failed = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(queued.run.id, _plan(failure_at=ScanStage.INGESTION, failure=PipelineStageFailure("recoverable", "Safe message.", True)))
    assert failed.run.status is ScanStatus.FAILED and failed.run.errors[-1].recoverable is False
    next_run = registry.create(_run(2))
    unexpected = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(next_run.run.id, _plan(invalid_output=True))
    assert unexpected.run.status is ScanStatus.FAILED and unexpected.run.errors[-1].message == "Pipeline stage failed unexpectedly."


def test_neg_a4_009_invalid_clock_preserves_queued(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = registry.create(_run())
    _error(lambda: ScanPipelineWorker(registry, clock=lambda: datetime(2026, 1, 1)).run(queued.run.id, _plan()), "pipeline_invalid_argument")
    assert registry.get(queued.run.id).run.status is ScanStatus.QUEUED
