"""One-shot A2/B1 local-ZIP dependency plan; no parser logic lives here."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable

from app.ai import Provider
from app.domain.models import HashValue, Project, RunProvenance, ScanRun, SourceType
from app.ingestion import ZipIngestionService
from app.pipeline.dependency_plan import (
    DependencyConsumerResult,
    DependencyPlanState,
    LaneResult,
    READ_LIMITS,
    build_dependency_plan,
    fail,
    is_pristine,
    replace_run,
)
from app.pipeline.worker import PipelineError, PipelinePlan
from app.scanners import (
    JavascriptP0MappingResult,
    PythonP0MappingResult,
    map_javascript_manifest_result,
    map_python_manifest_result,
    parse_javascript_manifests,
    parse_python_manifests,
)


class _DigestingReader:
    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self.digest = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        data = self._raw.read(size)
        if type(data) is not bytes:
            raise OSError("invalid binary stream")
        self.digest.update(data)
        return data


def _consume_dependencies(session: object, clock: Callable[[], datetime]) -> DependencyConsumerResult:
    """Keep the established local-ZIP monkeypatch seam for implementation tests."""

    try:
        python_mapping = map_python_manifest_result(
            parse_python_manifests(session),  # type: ignore[arg-type]
            root_digest=session.inventory.root_digest,  # type: ignore[attr-defined]
            observed_at=clock(),
        )
        if type(python_mapping) is not PythonP0MappingResult:
            raise TypeError
    except Exception:
        python_mapping = None
    try:
        javascript_mapping = map_javascript_manifest_result(
            parse_javascript_manifests(session),  # type: ignore[arg-type]
            root_digest=session.inventory.root_digest,  # type: ignore[attr-defined]
            observed_at=clock(),
        )
        if type(javascript_mapping) is not JavascriptP0MappingResult:
            raise TypeError
    except Exception:
        javascript_mapping = None
    return DependencyConsumerResult(
        lanes=(LaneResult("python", python_mapping), LaneResult("javascript", javascript_mapping))
    )


def build_local_zip_dependency_plan(
    archive_path: Path,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
    ai_provider: Provider | None = None,
    ai_enabled: bool = False,
    ai_timeout_seconds: float = 10.0,
) -> PipelinePlan:
    """Build one explicit plan for one queued ZIP ScanRun."""

    if not isinstance(archive_path, Path) or not isinstance(workspace_root, Path) or not callable(clock):
        raise PipelineError("pipeline_invalid_argument") from None
    state = DependencyPlanState()
    used = False

    def ingestion(run: ScanRun) -> ScanRun:
        nonlocal used
        if used:
            fail("local_zip_plan_reused", "Local ZIP plan was already used.")
        used = True
        if run.project.source_type is not SourceType.ZIP or run.project.source != archive_path.name or not is_pristine(run):
            fail("local_zip_plan_incompatible", "Queued scan is incompatible with this local ZIP plan.")
        try:
            raw = archive_path.open("rb")
        except OSError:
            fail("local_zip_unavailable", "Local ZIP is unavailable.")

        service: ZipIngestionService | None = None
        result = None
        reader: _DigestingReader | None = None
        failed = False
        try:
            with raw:
                reader = _DigestingReader(raw)
                service = ZipIngestionService(workspace_root)
                result = service.ingest_with_consumer(
                    reader,
                    lambda session: _consume_dependencies(session, clock),
                    read_limits=READ_LIMITS,
                )
        except Exception:
            failed = True
        finally:
            if service is not None:
                try:
                    service.close()
                except Exception:
                    failed = True
        if failed or result is None or reader is None or type(result.consumer_result) is not DependencyConsumerResult:
            fail("zip_ingestion_failed", "Local ZIP ingestion failed.")
        if reader.digest.hexdigest() != run.provenance.input_digest.value:
            fail("input_digest_mismatch", "Local ZIP input digest did not match.")

        state.consumer_result = result.consumer_result
        state.root_digest = result.inventory.root_digest
        digest = HashValue(algorithm="sha256", value=state.root_digest)
        project = Project.model_validate({**run.project.model_dump(mode="python"), "root_digest": digest})
        provenance = RunProvenance.model_validate(
            {**run.provenance.model_dump(mode="python"), "inventory_digest": digest}
        )
        return replace_run(run, project=project, provenance=provenance)

    return build_dependency_plan(
        ingestion,
        state,
        ingestion_error_code="zip_ingestion_failed",
        ingestion_error_message="Local ZIP ingestion failed.",
        ai_provider=ai_provider,
        ai_enabled=ai_enabled,
        ai_timeout_seconds=ai_timeout_seconds,
    )
