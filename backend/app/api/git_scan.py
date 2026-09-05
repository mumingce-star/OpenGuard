"""In-process public Git execution for the frozen scan creation route."""

from __future__ import annotations

import math
import os
import stat
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks

from app.ai import Provider
from app.api.models import GitScanCreateRequest, ScanCreateAccepted
from app.api.service import ScanApiService
from app.persistence import SQLiteScanRunRegistry
from app.pipeline import ScanPipelineWorker, build_public_git_dependency_plan
from app.pipeline.public_git import GitIngestionFactory
from app.reporting import PipelineReportPublisher


def _validate_private_root(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("Git runtime root must be absolute")
    try:
        info = path.lstat()
    except OSError as error:
        raise ValueError("Git runtime root is unavailable") from error
    if (
        os.name != "posix"
        or stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Git runtime root must be a private POSIX directory")
    return path


class GitScanRuntime:
    """Create one durable run, then execute public Git ingestion after response."""

    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        *,
        workspace_root: Path,
        clock: Callable[[], datetime] | None = None,
        report_publisher: PipelineReportPublisher | None = None,
        ingestion_factory: GitIngestionFactory | None = None,
        ai_provider: Provider | None = None,
        ai_enabled: bool = False,
        ai_timeout_seconds: float = 10.0,
    ) -> None:
        if (
            not isinstance(registry, SQLiteScanRunRegistry)
            or (clock is not None and not callable(clock))
            or (report_publisher is not None and type(report_publisher) is not PipelineReportPublisher)
            or (ingestion_factory is not None and not callable(ingestion_factory))
            or type(ai_enabled) is not bool
            or type(ai_timeout_seconds) not in {int, float}
            or isinstance(ai_timeout_seconds, bool)
            or not math.isfinite(ai_timeout_seconds)
            or ai_timeout_seconds <= 0
            or (ai_enabled and ai_provider is None)
        ):
            raise ValueError("invalid Git runtime")
        self._registry = registry
        self._workspace_root = _validate_private_root(workspace_root)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._report_publisher = report_publisher
        self._ingestion_factory = ingestion_factory
        self._ai_provider = ai_provider
        self._ai_enabled = ai_enabled
        self._ai_timeout_seconds = float(ai_timeout_seconds)

    def submit(
        self,
        request: GitScanCreateRequest,
        service: ScanApiService,
        background_tasks: BackgroundTasks,
    ) -> ScanCreateAccepted:
        accepted, created = service.create_git_scan_record(request)
        if created:
            source = self._registry.get(accepted.scan_id).run.project.source
            background_tasks.add_task(self._execute, accepted.scan_id, source)
        return accepted

    def _execute(self, scan_id: str, source: str) -> None:
        plan = build_public_git_dependency_plan(
            source,
            self._workspace_root,
            clock=self._clock,
            ingestion_factory=self._ingestion_factory,
            ai_provider=self._ai_provider,
            ai_enabled=self._ai_enabled,
            ai_timeout_seconds=self._ai_timeout_seconds,
        )
        publisher = self._report_publisher
        ScanPipelineWorker(
            self._registry,
            clock=self._clock,
            terminal_publisher=publisher.publish if publisher is not None else None,
        ).run(scan_id, plan)


__all__ = ["GitScanRuntime"]
