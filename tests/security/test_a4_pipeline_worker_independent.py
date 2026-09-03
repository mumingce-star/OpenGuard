"""Independent A4-0 security regression for the explicit pipeline worker.

Expected states, aggregates, plans and failure assertions are built here from
the frozen A4-0/P0 contracts.  The tests do not import or call Terra's unit
test helpers and use only temporary SQLite databases.
"""

from __future__ import annotations

import os
import threading
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from app.domain.models import (
    Component,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    FindingOutcome,
    HashValue,
    ProducerRef,
    ProducerType,
    Project,
    RunEnvironment,
    RunProvenance,
    ScanError,
    ScanRun,
    ScanStage,
    ScanStatus,
    ScanSummary,
    SourceType,
    VerificationStatus,
)
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError
from app.pipeline import (
    PipelineError,
    PipelinePlan,
    PipelineStageFailure,
    PipelineStep,
    ScanPipelineWorker,
)


BASE_TIME = datetime(2026, 9, 3, 4, 0, tzinfo=timezone.utc)
STAGES = (
    (ScanStage.INGESTION, 5),
    (ScanStage.INVENTORY, 15),
    (ScanStage.SCAN, 35),
    (ScanStage.NORMALIZE, 55),
    (ScanStage.RULES, 70),
    (ScanStage.AI_ASSIST, 85),
    (ScanStage.REPORT, 95),
)


def _id(prefix: str, number: int) -> str:
    return f"{prefix}_00000000-0000-0000-0000-{number:012x}"


def _hash(digit: str) -> HashValue:
    return HashValue(algorithm="sha256", value=digit * 64)


def _summary(*, components: int = 0, evidence: int = 0) -> ScanSummary:
    return ScanSummary(
        component_count=components,
        ai_asset_count=0,
        evidence_count=evidence,
        finding_counts={
            FindingOutcome.PASS: 0,
            FindingOutcome.WARNING: 0,
            FindingOutcome.REVIEW_REQUIRED: 0,
            FindingOutcome.UNKNOWN: 0,
        },
    )


def _queued_run(number: int = 1) -> ScanRun:
    created_at = BASE_TIME + timedelta(seconds=number)
    return ScanRun(
        contract_version="0.1.1",
        id=_id("scn", number),
        idempotency_key=f"independent-a4-{number}",
        status=ScanStatus.QUEUED,
        stage=ScanStage.QUEUED,
        progress=0,
        project=Project(
            id=_id("prj", number),
            name=f"a4-independent-{number}",
            source_type=SourceType.GIT,
            source="https://github.com/example/openguard-a4",
            created_at=created_at,
        ),
        summary=_summary(),
        provenance=RunProvenance(
            input_digest=_hash("a"),
            tool_versions=[],
            ruleset_version="independent-a4-rules",
            contract_version="0.1.1",
            ai_enabled=False,
            ai_model=None,
            run_environment=RunEnvironment(
                python_version="3.12-independent",
                platform="macos-independent-a4",
                openguard_version="independent-a4",
            ),
        ),
        created_at=created_at,
    )


def _fingerprint(run: ScanRun) -> str:
    return hashlib.sha256(f"independent-a4:{run.idempotency_key}".encode("utf-8")).hexdigest()


def _create(registry: SQLiteScanRunRegistry, run: ScanRun):
    return registry.create(run, idempotency_fingerprint=_fingerprint(run))


def _rebuild(run: ScanRun, **changes: object) -> ScanRun:
    payload = run.model_dump(mode="python")
    payload.update(changes)
    return ScanRun.model_validate(payload)


def _running(run: ScanRun, *, stage: ScanStage = ScanStage.INGESTION, progress: int = 5) -> ScanRun:
    return _rebuild(
        run,
        status=ScanStatus.RUNNING,
        stage=stage,
        progress=progress,
        started_at=BASE_TIME + timedelta(days=1),
        finished_at=None,
    )


def _registry(tmp_path: Path, name: str = "runs.sqlite") -> SQLiteScanRunRegistry:
    os.chmod(tmp_path, 0o700)
    return SQLiteScanRunRegistry(tmp_path / name)


def _plan_for(callback: Callable[[ScanStage, ScanRun], ScanRun]) -> PipelinePlan:
    steps: list[PipelineStep] = []
    for stage, _ in STAGES:
        def handler(run: ScanRun, stage: ScanStage = stage) -> ScanRun:
            return callback(stage, run)

        steps.append(PipelineStep(stage=stage, handler=handler))
    return PipelinePlan(steps=tuple(steps))


def _identity_plan() -> PipelinePlan:
    return _plan_for(lambda _stage, run: run)


def _assert_error(callable_: Callable[[], object], code: str) -> PipelineError:
    with pytest.raises(PipelineError) as raised:
        callable_()
    assert raised.value.code == code
    assert raised.value.__cause__ is None
    return raised.value


def _aggregate(run: ScanRun, number: int) -> ScanRun:
    producer = ProducerRef(type=ProducerType.PARSER, name="independent-a4-parser", version="1")
    evidence = Evidence(
        id=_id("evd", number),
        kind=EvidenceKind.MANIFEST_FIELD,
        locator="pyproject.toml:project.dependencies[0]",
        excerpt="requests>=2.0",
        start_line=1,
        end_line=1,
        content_hash=_hash("b"),
        detected_by=DetectionMethod.MANIFEST_PARSER,
        producer=producer,
        observed_at=run.created_at,
        verification_status=VerificationStatus.VERIFIED,
    )
    component = Component(
        id=_id("cmp", number),
        name="requests",
        version="2.0.0",
        ecosystem="pypi",
        purl="pkg:pypi/requests@2.0.0",
        evidence_ids=[evidence.id],
        detected_by=[DetectionMethod.MANIFEST_PARSER],
        confidence=1.0,
    )
    return _rebuild(
        run,
        components=[component],
        evidence=[evidence],
        summary=_summary(components=1, evidence=1),
    )


def _persist_status(registry: SQLiteScanRunRegistry, run: ScanRun, status: ScanStatus) -> None:
    stored = _create(registry, run)
    if status is ScanStatus.QUEUED:
        return
    if status is ScanStatus.CANCELLED:
        cancelled = _rebuild(
            run,
            status=ScanStatus.CANCELLED,
            stage=ScanStage.QUEUED,
            progress=0,
            finished_at=run.created_at + timedelta(seconds=1),
        )
        registry.replace(cancelled, expected_revision=stored.revision)
        return

    running = _running(run)
    stored = registry.replace(running, expected_revision=stored.revision)
    finished_at = running.started_at + timedelta(seconds=1)  # type: ignore[operator]
    if status is ScanStatus.RUNNING:
        return
    if status is ScanStatus.FAILED:
        failed = _rebuild(
            running,
            status=ScanStatus.FAILED,
            stage=ScanStage.INGESTION,
            progress=5,
            errors=[ScanError(code="preexisting_failure", stage=ScanStage.INGESTION, message="controlled failure", recoverable=False)],
            finished_at=finished_at,
        )
    elif status is ScanStatus.PARTIAL:
        partial = _aggregate(running, int(run.id[-2:], 16) + 200)
        failed = _rebuild(
            partial,
            status=ScanStatus.PARTIAL,
            stage=ScanStage.SCAN,
            progress=35,
            errors=[ScanError(code="preexisting_partial", stage=ScanStage.SCAN, message="controlled partial", recoverable=True)],
            finished_at=finished_at,
        )
    elif status is ScanStatus.COMPLETED:
        failed = _rebuild(
            running,
            status=ScanStatus.COMPLETED,
            stage=ScanStage.COMPLETED,
            progress=100,
            finished_at=finished_at,
        )
    else:  # pragma: no cover - protects the test helper from silently broadening
        raise AssertionError(status)
    registry.replace(failed, expected_revision=stored.revision)


def test_pos_a4_001_full_plan_executes_each_stage_once_and_completes(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run())
    seen: list[tuple[ScanStage, int, ScanStatus]] = []

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        seen.append((stage, run.progress, run.status))
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    assert result.run.status is ScanStatus.COMPLETED
    assert result.run.stage is ScanStage.COMPLETED
    assert result.run.progress == 100
    assert seen == [(stage, progress, ScanStatus.RUNNING) for stage, progress in STAGES]


def test_pos_a4_002_aggregate_survives_stages_and_sqlite_restart(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(2))
    aggregate_seen: list[tuple[ScanStage, str, str]] = []

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.INGESTION:
            run = _aggregate(run, 2)
        aggregate_seen.append((stage, run.components[0].id, run.evidence[0].id))
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    assert result.run.components and result.run.evidence
    assert len(aggregate_seen) == len(STAGES)
    assert all(item[1:] == (result.run.components[0].id, result.run.evidence[0].id) for item in aggregate_seen)
    database = tmp_path / "runs.sqlite"
    registry.close()
    reopened = SQLiteScanRunRegistry(database)
    try:
        assert reopened.get(queued.run.id).run == result.run
    finally:
        reopened.close()


def test_pos_a4_003_claim_and_stage_progress_are_durable_before_each_handler(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(3))
    fixed_start = BASE_TIME + timedelta(days=1)
    observations: list[tuple[ScanStage, int, ScanStage, int, datetime | None]] = []

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        durable = registry.get(run.id).run
        observations.append((stage, run.progress, durable.stage, durable.progress, durable.started_at))
        return run

    result = ScanPipelineWorker(registry, clock=lambda: fixed_start).run(queued.run.id, _plan_for(callback))
    assert [(stage, progress) for stage, progress, _, _, _ in observations] == [(stage, progress) for stage, progress in STAGES]
    assert all(stage is durable_stage and progress == durable_progress for stage, progress, durable_stage, durable_progress, _ in observations)
    assert all(started_at == fixed_start for *_, started_at in observations)
    assert result.run.started_at == fixed_start
    assert result.run.finished_at == fixed_start


def test_pos_a4_004_recoverable_failure_with_aggregate_is_partial(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(4))

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.INGESTION:
            return _aggregate(run, 4)
        if stage is ScanStage.INVENTORY:
            raise PipelineStageFailure("inventory_timeout", "Inventory adapter timed out.", True)
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    assert result.run.status is ScanStatus.PARTIAL
    assert result.run.stage is ScanStage.INVENTORY
    assert result.run.progress == 15
    assert result.run.components
    assert result.run.errors[-1].code == "inventory_timeout"
    assert result.run.errors[-1].stage is ScanStage.INVENTORY
    assert result.run.errors[-1].recoverable is True
    assert result.run.finished_at is not None


def test_pos_a4_005_cancelled_winner_is_returned_without_later_handlers(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(5))
    seen: list[ScanStage] = []

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        seen.append(stage)
        if stage is ScanStage.SCAN:
            current = registry.get(run.id)
            cancelled = _rebuild(
                run,
                status=ScanStatus.CANCELLED,
                finished_at=run.started_at,
            )
            registry.replace(cancelled, expected_revision=current.revision)
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    assert result.run.status is ScanStatus.CANCELLED
    assert seen == [ScanStage.INGESTION, ScanStage.INVENTORY, ScanStage.SCAN]
    assert registry.get(queued.run.id).run.status is ScanStatus.CANCELLED


def test_neg_a4_001_missing_duplicate_ordered_illegal_and_noncallable_plans_run_no_handler(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(10))
    calls = 0

    def handler(_: ScanRun) -> ScanRun:
        nonlocal calls
        calls += 1
        return _

    valid_steps = [PipelineStep(stage, handler) for stage, _ in STAGES]
    invalid_plans: list[object] = [
        None,
        PipelinePlan(steps=()),
        PipelinePlan(steps=tuple(valid_steps[:-1] + [PipelineStep(ScanStage.AI_ASSIST, handler)])),
        PipelinePlan(steps=tuple(valid_steps[1:2] + valid_steps[1:])),
        PipelinePlan(steps=tuple(reversed(valid_steps))),
        PipelinePlan(steps=tuple([PipelineStep(ScanStage.QUEUED, handler), *valid_steps[1:]])),
        PipelinePlan(steps=tuple([PipelineStep(ScanStage.COMPLETED, handler), *valid_steps[1:]])),
        PipelinePlan(steps=tuple([PipelineStep(ScanStage.INGESTION, None), *valid_steps[1:]])),  # type: ignore[arg-type]
        PipelinePlan(steps=list(valid_steps)),  # type: ignore[arg-type]
        object(),
    ]
    for plan in invalid_plans:
        _assert_error(lambda plan=plan: ScanPipelineWorker(registry).run(queued.run.id, plan), "pipeline_invalid_argument")  # type: ignore[arg-type]
    assert calls == 0
    assert registry.get(queued.run.id).run.status is ScanStatus.QUEUED


@pytest.mark.parametrize(
    "status",
    [
        ScanStatus.RUNNING,
        ScanStatus.COMPLETED,
        ScanStatus.PARTIAL,
        ScanStatus.FAILED,
        ScanStatus.CANCELLED,
    ],
)
def test_neg_a4_002_all_nonqueued_states_are_not_claimable_and_run_no_handler(
    tmp_path: Path,
    status: ScanStatus,
) -> None:
    registry = _registry(tmp_path, f"{status.value}.sqlite")
    queued = _queued_run(20 + list(ScanStatus).index(status))
    _persist_status(registry, queued, status)
    calls = 0

    def callback(_stage: ScanStage, run: ScanRun) -> ScanRun:
        nonlocal calls
        calls += 1
        return run

    _assert_error(lambda: ScanPipelineWorker(registry).run(queued.id, _plan_for(callback)), "pipeline_not_claimable")
    assert calls == 0


def test_neg_a4_003_two_workers_claim_at_most_once(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.sqlite"
    first_registry = _registry(tmp_path, database.name)
    second_registry = SQLiteScanRunRegistry(database)
    queued = _create(first_registry, _queued_run(30))
    entered = threading.Event()
    release = threading.Event()
    count_lock = threading.Lock()
    calls = 0

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        nonlocal calls
        if stage is ScanStage.INGESTION:
            with count_lock:
                calls += 1
            entered.set()
            assert release.wait(timeout=3)
        return run

    plan = _plan_for(callback)
    outcomes: list[object] = []
    start = threading.Barrier(2)

    def invoke(worker: ScanPipelineWorker) -> None:
        start.wait()
        try:
            outcomes.append(worker.run(queued.run.id, plan))
        except Exception as error:  # assertions below classify the exact error
            outcomes.append(error)

    threads = [
        threading.Thread(target=invoke, args=(ScanPipelineWorker(first_registry),)),
        threading.Thread(target=invoke, args=(ScanPipelineWorker(second_registry),)),
    ]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=3)
    release.set()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert calls == 1
    assert len(outcomes) == 2
    assert sum(isinstance(outcome, PipelineError) and outcome.code == "pipeline_not_claimable" for outcome in outcomes) == 1
    assert sum(not isinstance(outcome, (PipelineError, Exception)) for outcome in outcomes) == 1
    assert first_registry.get(queued.run.id).run.status is ScanStatus.COMPLETED
    first_registry.close()
    second_registry.close()


def test_neg_a4_004_recoverable_failure_without_aggregate_is_failed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(40))

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.INGESTION:
            raise PipelineStageFailure("ingestion_timeout", "Ingestion timed out.", True)
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    assert result.run.status is ScanStatus.FAILED
    assert result.run.stage is ScanStage.INGESTION
    assert result.run.errors[-1].code == "ingestion_timeout"
    assert result.run.errors[-1].recoverable is False
    assert not result.run.components and not result.run.evidence


def test_neg_a4_005_unknown_exception_with_path_url_secret_is_generic_and_terminal(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(50))
    secret_text = "/private/project https://evil.example/repo?token=secret token=secret"

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.NORMALIZE:
            raise RuntimeError(secret_text)
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    stored_text = result.run.model_dump_json()
    assert result.run.status is ScanStatus.FAILED
    assert result.run.errors[-1].code == "pipeline_stage_failed"
    assert result.run.errors[-1].message == "Pipeline stage failed unexpectedly."
    assert secret_text not in stored_text
    assert "/private/project" not in stored_text
    assert "evil.example" not in stored_text
    assert "token=secret" not in stored_text


def test_neg_a4_006_non_scan_run_output_becomes_sanitized_failed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(60))

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.SCAN:
            return {"id": "not-a-scan-run"}  # type: ignore[return-value]
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        queued.run.id, _plan_for(callback)
    )
    assert result.run.status is ScanStatus.FAILED
    assert result.run.stage is ScanStage.SCAN
    assert result.run.progress == 35
    assert result.run.errors[-1].code == "pipeline_stage_failed"
    assert result.run.errors[-1].message == "Pipeline stage failed unexpectedly."


@pytest.mark.parametrize("mutation", ["id", "project_name", "project_source"])
def test_neg_a4_007_id_or_project_identity_tampering_never_persists(
    tmp_path: Path,
    mutation: str,
) -> None:
    registry = _registry(tmp_path, f"{mutation}.sqlite")
    queued = _create(registry, _queued_run(70 + ["id", "project_name", "project_source"].index(mutation)))
    original_id = queued.run.id
    original_project = queued.run.project

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.INGESTION:
            payload = run.model_dump(mode="python")
            if mutation == "id":
                payload["id"] = _id("scn", 999)
            elif mutation == "project_name":
                payload["project"] = {**payload["project"], "name": "tampered-project"}
            else:
                payload["project"] = {**payload["project"], "source": "https://evil.example/tampered"}
            return ScanRun.model_validate(payload)
        return run

    result = ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
        original_id, _plan_for(callback)
    )
    assert result.run.status is ScanStatus.FAILED
    persisted = registry.get(original_id).run
    assert persisted.id == original_id
    assert persisted.project == original_project
    assert "tampered" not in persisted.model_dump_json()
    assert result.run.errors[-1].message == "Pipeline stage failed unexpectedly."


def test_neg_a4_008_non_cancel_cas_conflict_does_not_overwrite_winner(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(80))

    def callback(stage: ScanStage, run: ScanRun) -> ScanRun:
        if stage is ScanStage.INGESTION:
            current = registry.get(run.id)
            winner = _rebuild(run, stage=ScanStage.INVENTORY, progress=15)
            registry.replace(winner, expected_revision=current.revision)
        return run

    _assert_error(
        lambda: ScanPipelineWorker(registry, clock=lambda: BASE_TIME + timedelta(days=1)).run(
            queued.run.id, _plan_for(callback)
        ),
        "pipeline_state_conflict",
    )
    winner = registry.get(queued.run.id).run
    assert winner.status is ScanStatus.RUNNING
    assert winner.stage is ScanStage.INVENTORY
    assert winner.progress == 15
    assert winner.finished_at is None


@pytest.mark.parametrize("clock_kind", ["raises", "naive", "non_utc", "backwards"])
def test_neg_a4_009_invalid_initial_clock_keeps_queued(tmp_path: Path, clock_kind: str) -> None:
    registry = _registry(tmp_path, f"{clock_kind}.sqlite")
    queued = _create(registry, _queued_run(90 + ["raises", "naive", "non_utc", "backwards"].index(clock_kind)))
    calls = 0

    def callback(_stage: ScanStage, run: ScanRun) -> ScanRun:
        nonlocal calls
        calls += 1
        return run

    def clock() -> datetime:
        if clock_kind == "raises":
            raise RuntimeError("clock secret")
        if clock_kind == "naive":
            return datetime(2026, 9, 4, 4, 0)
        if clock_kind == "non_utc":
            return datetime(2026, 9, 4, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        return BASE_TIME - timedelta(seconds=1)

    _assert_error(lambda: ScanPipelineWorker(registry, clock=clock).run(queued.run.id, _plan_for(callback)), "pipeline_invalid_argument")
    assert calls == 0
    stored = registry.get(queued.run.id)
    assert stored.revision == 1
    assert stored.run.status is ScanStatus.QUEUED
    assert stored.run.stage is ScanStage.QUEUED
    assert stored.run.progress == 0


def test_neg_a4_009_late_clock_backwards_never_forges_completed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    queued = _create(registry, _queued_run(95))
    values = iter([BASE_TIME + timedelta(days=1), BASE_TIME - timedelta(seconds=1)])

    def clock() -> datetime:
        return next(values)

    _assert_error(lambda: ScanPipelineWorker(registry, clock=clock).run(queued.run.id, _identity_plan()), "pipeline_invalid_argument")
    stored = registry.get(queued.run.id).run
    assert stored.status is ScanStatus.RUNNING
    assert stored.stage is ScanStage.REPORT
    assert stored.progress == 95
    assert stored.finished_at is None


def test_neg_a4_010_registry_get_and_replace_failures_stop_without_handlers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_registry = _registry(tmp_path, "get-failure.sqlite")
    get_run = _create(get_registry, _queued_run(100))
    get_calls = 0

    def get_callback(_stage: ScanStage, run: ScanRun) -> ScanRun:
        nonlocal get_calls
        get_calls += 1
        return run

    def broken_get(_: str) -> object:
        raise ScanRegistryError("registry_io_failed")

    monkeypatch.setattr(get_registry, "get", broken_get)
    _assert_error(lambda: ScanPipelineWorker(get_registry).run(get_run.run.id, _identity_plan()), "pipeline_registry_failure")
    assert get_calls == 0

    replace_registry = _registry(tmp_path, "replace-failure.sqlite")
    replace_run = _create(replace_registry, _queued_run(101))
    replace_calls = 0

    def replace_callback(_stage: ScanStage, run: ScanRun) -> ScanRun:
        nonlocal replace_calls
        replace_calls += 1
        return run

    def broken_replace(_: ScanRun, *, expected_revision: int) -> object:
        raise ScanRegistryError("registry_corrupt")

    monkeypatch.setattr(replace_registry, "replace", broken_replace)
    _assert_error(
        lambda: ScanPipelineWorker(replace_registry).run(replace_run.run.id, _plan_for(replace_callback)),
        "pipeline_registry_failure",
    )
    assert replace_calls == 0
    get_registry.close()
    replace_registry.close()
