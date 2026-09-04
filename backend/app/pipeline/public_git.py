"""One-shot public-Git dependency plan backed by A2 TrustedEgress."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.domain.models import HashValue, ProducerRef, ProducerType, Project, RunProvenance, ScanRun, SourceType
from app.ingestion import GitIngestionService
from app.pipeline.dependency_plan import (
    DependencyConsumerResult,
    DependencyPlanState,
    READ_LIMITS,
    build_dependency_plan,
    consume_dependencies,
    fail,
    is_pristine,
    replace_run,
)
from app.pipeline.worker import PipelineError, PipelinePlan
from app.security.errors import IngestionSecurityError


GitIngestionFactory = Callable[[Path], GitIngestionService]


def build_public_git_dependency_plan(
    source: str,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
    ingestion_factory: GitIngestionFactory | None = None,
) -> PipelinePlan:
    """Build a real HTTPS Git→inventory→B1→partial-report plan."""

    if type(source) is not str or not source or not isinstance(workspace_root, Path) or not callable(clock):
        raise PipelineError("pipeline_invalid_argument") from None
    factory = ingestion_factory or (lambda root: GitIngestionService(root))
    if not callable(factory):
        raise PipelineError("pipeline_invalid_argument") from None
    state = DependencyPlanState()
    used = False

    def ingestion(run: ScanRun) -> ScanRun:
        nonlocal used
        if used:
            fail("public_git_plan_reused", "Public Git plan was already used.")
        used = True
        if run.project.source_type is not SourceType.GIT or run.project.source != source or not is_pristine(run):
            fail("public_git_plan_incompatible", "Queued scan is incompatible with this public Git plan.")

        service: GitIngestionService | None = None
        result = None
        try:
            service = factory(workspace_root)
            result = service.ingest_with_consumer(
                source,
                lambda session: consume_dependencies(session, clock),
                read_limits=READ_LIMITS,
            )
        except IngestionSecurityError as error:
            if error.code == "scanner_timeout":
                fail("scanner_timeout", "Public Git ingestion timed out.")
            if error.code == "scanner_failed":
                fail("scanner_failed", "Public Git ingestion failed.")
            fail("invalid_source", "Public Git ingestion failed.")
        except Exception:
            fail("scanner_failed", "Public Git ingestion failed.")
        finally:
            if service is not None:
                try:
                    service.close()
                except Exception:
                    fail("scanner_failed", "Public Git ingestion failed.")
        if result is None or type(result.consumer_result) is not DependencyConsumerResult:
            fail("scanner_failed", "Public Git ingestion failed.")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != run.provenance.input_digest.value:
            fail("input_digest_mismatch", "Public Git input digest did not match.")

        state.consumer_result = result.consumer_result
        state.root_digest = result.inventory.root_digest
        digest = HashValue(algorithm="sha256", value=state.root_digest)
        state.ingestion_producers = [
            ProducerRef(
                type=ProducerType.SCANNER,
                name="git-client",
                version=result.runtime_identity.version,
                config_digest=HashValue(algorithm="sha256", value=result.runtime_identity.config_digest),
            )
        ]
        project = Project.model_validate(
            {
                **run.project.model_dump(mode="python"),
                "revision": result.revision,
                "root_digest": digest,
            }
        )
        provenance = RunProvenance.model_validate(
            {**run.provenance.model_dump(mode="python"), "inventory_digest": digest}
        )
        return replace_run(run, project=project, provenance=provenance)

    return build_dependency_plan(
        ingestion,
        state,
        ingestion_error_code="scanner_failed",
        ingestion_error_message="Public Git ingestion failed.",
    )


__all__ = ["GitIngestionFactory", "build_public_git_dependency_plan"]
