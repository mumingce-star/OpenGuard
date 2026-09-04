"""The intentionally explicit A4-0 single-process ScanRun worker."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.domain.models import ReportFormat, ScanError, ScanRun, ScanStage, ScanStatus
from app.persistence import SQLiteScanRunRegistry, ScanRegistryError, StoredScanRun


_STAGES = (
    (ScanStage.INGESTION, 5),
    (ScanStage.INVENTORY, 15),
    (ScanStage.SCAN, 35),
    (ScanStage.NORMALIZE, 55),
    (ScanStage.RULES, 70),
    (ScanStage.AI_ASSIST, 85),
    (ScanStage.REPORT, 95),
)
_FAILURE_CODE = re.compile(r"[a-z][a-z0-9_]{0,99}")
_UNEXPECTED_MESSAGE = "Pipeline stage failed unexpectedly."


class PipelineError(RuntimeError):
    """Stable, deliberately context-free error exposed by this internal API."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PipelineStageFailure(RuntimeError):
    """An adapter's explicit, sanitized failure declaration."""

    def __init__(self, code: str, public_message: str, recoverable: bool) -> None:
        self.code = code
        self.public_message = public_message
        self.recoverable = recoverable
        super().__init__(code)


@dataclass(frozen=True)
class PipelineStep:
    stage: ScanStage
    handler: Callable[[ScanRun], ScanRun]


@dataclass(frozen=True)
class PipelinePlan:
    steps: tuple[PipelineStep, ...]


def _fail(code: str) -> None:
    raise PipelineError(code) from None


class ScanPipelineWorker:
    """Run one supplied plan; this class never polls or consumes API queues."""

    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        *,
        clock: Callable[[], datetime] | None = None,
        terminal_publisher: Callable[[ScanRun], ScanRun] | None = None,
    ) -> None:
        if not isinstance(registry, SQLiteScanRunRegistry):
            _fail("pipeline_invalid_argument")
        if (clock is not None and not callable(clock)) or (
            terminal_publisher is not None and not callable(terminal_publisher)
        ):
            _fail("pipeline_invalid_argument")
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._terminal_publisher = terminal_publisher

    @staticmethod
    def _validate_plan(plan: object) -> PipelinePlan:
        if type(plan) is not PipelinePlan or type(plan.steps) is not tuple or len(plan.steps) != len(_STAGES):
            _fail("pipeline_invalid_argument")
        for step, (stage, _) in zip(plan.steps, _STAGES, strict=True):
            if type(step) is not PipelineStep or step.stage is not stage or not callable(step.handler):
                _fail("pipeline_invalid_argument")
        return plan

    def _now(self, *, minimum: datetime) -> datetime:
        try:
            value = self._clock()
        except Exception:
            _fail("pipeline_invalid_argument")
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            _fail("pipeline_invalid_argument")
        value = value.astimezone(timezone.utc)
        if value < minimum:
            _fail("pipeline_invalid_argument")
        return value

    @staticmethod
    def _with_control(run: ScanRun, *, status: ScanStatus, stage: ScanStage, progress: int, started_at: datetime | None, finished_at: datetime | None, errors: list[ScanError] | None = None) -> ScanRun:
        payload = run.model_dump(mode="python")
        payload.update(status=status, stage=stage, progress=progress, started_at=started_at, finished_at=finished_at)
        if errors is not None:
            payload["errors"] = errors
        try:
            return ScanRun.model_validate(payload)
        except Exception:
            _fail("pipeline_stage_failed")
        raise AssertionError("unreachable")

    def _replace(self, run: ScanRun, *, expected_revision: int) -> StoredScanRun:
        try:
            return self._registry.replace(run, expected_revision=expected_revision)
        except ScanRegistryError as error:
            if error.code != "registry_revision_conflict":
                _fail("pipeline_registry_failure")
        try:
            latest = self._registry.get(run.id)
        except ScanRegistryError:
            _fail("pipeline_registry_failure")
        if latest.run.status is ScanStatus.CANCELLED:
            return latest
        _fail("pipeline_state_conflict")
        raise AssertionError("unreachable")

    @staticmethod
    def _has_aggregate(run: ScanRun) -> bool:
        return bool(run.components or run.ai_assets or run.evidence or run.findings or run.report_links)

    @staticmethod
    def _only_report_links_changed(before: ScanRun, after: ScanRun) -> bool:
        before_payload = before.model_dump(mode="python")
        after_payload = after.model_dump(mode="python")
        before_links = before_payload.pop("report_links")
        after_links = after_payload.pop("report_links")
        formats = [link.format for link in after.report_links]
        return (
            not before_links
            and before_payload == after_payload
            and bool(after_links)
            and len(formats) == len(set(formats))
            and set(formats) == set(ReportFormat)
        )

    def _commit_terminal(self, current: StoredScanRun, terminal: ScanRun) -> StoredScanRun:
        publisher = self._terminal_publisher
        if publisher is None or terminal.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL}:
            return self._replace(terminal, expected_revision=current.revision)
        try:
            published = publisher(terminal)
            if type(published) is not ScanRun or not self._only_report_links_changed(terminal, published):
                raise TypeError
        except Exception:
            if terminal.status is ScanStatus.PARTIAL:
                basis = terminal
                stage = terminal.stage
                progress = terminal.progress
            else:
                basis = current.run
                stage = ScanStage.REPORT
                progress = 95
            is_partial = self._has_aggregate(basis)
            error = ScanError(
                code="report_publish_failed",
                stage=ScanStage.REPORT,
                message="Report publishing failed.",
                recoverable=is_partial,
            )
            failed = self._with_control(
                basis,
                status=ScanStatus.PARTIAL if is_partial else ScanStatus.FAILED,
                stage=stage,
                progress=progress,
                started_at=terminal.started_at,
                finished_at=terminal.finished_at,
                errors=[*basis.errors, error],
            )
            return self._replace(failed, expected_revision=current.revision)
        return self._replace(published, expected_revision=current.revision)

    @staticmethod
    def _preserves_a3_identity(previous: ScanRun, candidate: ScanRun) -> bool:
        if (
            candidate.id != previous.id
            or candidate.idempotency_key != previous.idempotency_key
            or candidate.created_at != previous.created_at
            or candidate.project.id != previous.project.id
            or candidate.project.name != previous.project.name
            or candidate.project.source_type != previous.project.source_type
            or candidate.project.source != previous.project.source
            or candidate.project.created_at != previous.project.created_at
        ):
            return False
        if previous.project.revision is not None and candidate.project.revision != previous.project.revision:
            return False
        return previous.project.root_digest is None or candidate.project.root_digest == previous.project.root_digest

    def _stage_failure(self, current: StoredScanRun, failure: PipelineStageFailure | None) -> StoredScanRun:
        try:
            if (
                failure is None
                or type(failure.code) is not str
                or _FAILURE_CODE.fullmatch(failure.code) is None
                or type(failure.public_message) is not str
                or type(failure.recoverable) is not bool
            ):
                raise ValueError
            error = ScanError(code=failure.code, stage=current.run.stage, message=failure.public_message, recoverable=failure.recoverable)
        except Exception:
            error = ScanError(code="pipeline_stage_failed", stage=current.run.stage, message=_UNEXPECTED_MESSAGE, recoverable=False)
        is_partial = error.recoverable and self._has_aggregate(current.run)
        finished = self._now(minimum=current.run.started_at or current.run.created_at)
        terminal = self._with_control(
            current.run,
            status=ScanStatus.PARTIAL if is_partial else ScanStatus.FAILED,
            stage=current.run.stage,
            progress=current.run.progress,
            started_at=current.run.started_at,
            finished_at=finished,
            errors=[*current.run.errors, error.model_copy(update={"recoverable": is_partial and error.recoverable})],
        )
        return self._commit_terminal(current, terminal)

    def run(self, scan_id: str, plan: PipelinePlan) -> StoredScanRun:
        if type(scan_id) is not str:
            _fail("pipeline_invalid_argument")
        plan = self._validate_plan(plan)
        try:
            queued = self._registry.get(scan_id)
        except ScanRegistryError as error:
            if error.code == "registry_invalid_argument":
                _fail("pipeline_invalid_argument")
            if error.code == "registry_not_found":
                _fail("pipeline_not_claimable")
            _fail("pipeline_registry_failure")
        if queued.run.status is not ScanStatus.QUEUED or queued.run.stage is not ScanStage.QUEUED or queued.run.progress != 0:
            _fail("pipeline_not_claimable")

        started_at = self._now(minimum=queued.run.created_at)
        claimed_run = self._with_control(
            queued.run,
            status=ScanStatus.RUNNING,
            stage=ScanStage.INGESTION,
            progress=5,
            started_at=started_at,
            finished_at=None,
        )
        try:
            current = self._registry.replace(claimed_run, expected_revision=queued.revision)
        except ScanRegistryError as error:
            if error.code == "registry_revision_conflict":
                _fail("pipeline_not_claimable")
            _fail("pipeline_registry_failure")

        for index, (step, (stage, progress)) in enumerate(zip(plan.steps, _STAGES, strict=True)):
            if index:
                staged = self._with_control(current.run, status=ScanStatus.RUNNING, stage=stage, progress=progress, started_at=started_at, finished_at=None)
                current = self._replace(staged, expected_revision=current.revision)
                if current.run.status is ScanStatus.CANCELLED:
                    return current
            try:
                candidate = step.handler(current.run)
                if type(candidate) is not ScanRun:
                    raise TypeError
                if not self._preserves_a3_identity(current.run, candidate):
                    raise TypeError
                candidate = self._with_control(candidate, status=ScanStatus.RUNNING, stage=stage, progress=progress, started_at=started_at, finished_at=None)
            except PipelineStageFailure as failure:
                return self._stage_failure(current, failure)
            except Exception:
                return self._stage_failure(current, None)
            current = self._replace(candidate, expected_revision=current.revision)
            if current.run.status is ScanStatus.CANCELLED:
                return current

        finished_at = self._now(minimum=started_at)
        completed = self._with_control(current.run, status=ScanStatus.COMPLETED, stage=ScanStage.COMPLETED, progress=100, started_at=started_at, finished_at=finished_at)
        return self._commit_terminal(current, completed)
