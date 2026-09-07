"""One-shot public-Git dependency plan backed by A2 TrustedEgress."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.ai import Provider
from app.domain.models import HashValue, ProducerRef, ProducerType, Project, RunProvenance, ScanRun, SourceType, Evidence, ScanError
from app.ingestion import GitIngestionService
from app.pipeline.dependency_plan import (
    DependencyConsumerResult,
    DependencyPlanState,
    READ_LIMITS,
    build_dependency_plan,
    fail,
    is_pristine,
    replace_run,
)
from app.pipeline.worker import PipelineError, PipelinePlan, PipelineStageFailure
from app.pipeline.local_zip import _consume_dependencies
from app.pipeline.external_scans import collect_external_scans
from app.security.errors import IngestionSecurityError


GitIngestionFactory = Callable[[Path], GitIngestionService]
_CAPACITY_FAILURE_REASONS = {
    "git_fetch_limit_exceeded",
    "git_file_count_limit_exceeded",
    "git_single_file_limit_exceeded",
    "git_materialized_limit_exceeded",
}


def build_public_git_dependency_plan(
    source: str,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
    ingestion_factory: GitIngestionFactory | None = None,
    ai_provider: Provider | None = None,
    ai_enabled: bool = False,
    ai_timeout_seconds: float = 10.0,
    external_scanners: bool = False,
) -> PipelinePlan:
    """Build a real HTTPS Git plan using the existing ZIP fact and report chain."""

    if type(external_scanners) is not bool or type(source) is not str or not source or not isinstance(workspace_root, Path) or not callable(clock):
        raise PipelineError("pipeline_invalid_argument") from None
    factory = ingestion_factory or (lambda root: GitIngestionService(root, bounded=True))
    if not callable(factory):
        raise PipelineError("pipeline_invalid_argument") from None
    state = DependencyPlanState()
    used = False
    coverage_evidence: list[Evidence] = []
    coverage_errors: list[ScanError] = []

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
            options = {}
            if external_scanners:
                def scan_tree(tree, inventory):
                    state.external = collect_external_scans(tree, inventory, clock)
                options["tree_consumer"] = scan_tree
            result = service.ingest_with_consumer(
                source,
                lambda session: _consume_dependencies(session, clock),
                read_limits=READ_LIMITS,
                **options,
            )
        except IngestionSecurityError as error:
            if error.code == "scanner_timeout":
                fail("scanner_timeout", "Public Git ingestion timed out.")
            if error.code == "scanner_failed":
                if error.reason in _CAPACITY_FAILURE_REASONS:
                    fail("scanner_failed", "Public Git repository exceeds the configured scan capacity limit.")
                fail("scanner_failed", "Public Git ingestion failed.")
            messages = {
                "git_fetch_failed": "无法获取公开 Git 仓库。请检查仓库是否仍公开可访问、地址是否为仓库根地址，以及网络连接。",
                "git_entry_unsafe": "Git 仓库包含当前安全边界不支持的路径或对象，已停止读取。",
                "git_object_invalid": "Git 对象不完整或仓库没有可读取的提交，无法建立可信文件清单。",
                "github_repository_url_required": "请填写单个 GitHub 仓库根地址，不支持文件页、分支页或粘连的多个地址。",
            }
            fail("invalid_source", messages.get(error.reason, "Public Git ingestion failed."))
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

        omissions = getattr(result, "omissions", ())
        if omissions:
            producer = ProducerRef(type="scanner", name="git-bounded-selection", version="1",
                config_digest=HashValue(algorithm="sha256", value=result.runtime_identity.config_digest))
            for item in omissions:
                evidence_id = "evd_" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run.id}:{result.revision}:{item.path}:{item.reason}:{item.object_id}"))
                coverage_evidence.append(Evidence(id=evidence_id, kind="metadata", locator=item.path,
                    excerpt=f"未扫描：{item.reason}; Git revision={result.revision}; object={item.object_id}",
                    detected_by="static_pattern", producer=producer, observed_at=clock(), verification_status="verified"))
            coverage_errors.append(ScanError(code="git_scan_coverage_partial", stage="ingestion",
                message=f"有界扫描：仓库共 {getattr(result, 'discovered_entries', 0)} 个条目，本次读取 {len(result.inventory.entries)} 个文件；{len(omissions)} 个条目未扫描。完整路径和原因见报告的扫描覆盖范围。",
                recoverable=True, evidence_ids=[item.id for item in coverage_evidence]))
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
        if coverage_evidence:
            provenance = provenance.model_copy(update={
                "tool_versions": [*provenance.tool_versions, coverage_evidence[0].producer]})
            summary = run.summary.model_copy(update={"evidence_count": len(coverage_evidence)})
            return replace_run(run, project=project, provenance=provenance,
                evidence=list(coverage_evidence), errors=list(coverage_errors), summary=summary)
        return replace_run(run, project=project, provenance=provenance)

    plan = build_dependency_plan(
        ingestion,
        state,
        ingestion_error_code="scanner_failed",
        ingestion_error_message="Public Git ingestion failed.",
        ai_provider=ai_provider,
        ai_enabled=ai_enabled,
        ai_timeout_seconds=ai_timeout_seconds,
    )
    # The shared dependency scan builds its own evidence list; add coverage after
    # it completes so neither that merge nor AI can erase omitted-path records.
    from app.pipeline.worker import PipelineStep
    steps = list(plan.steps)
    original_scan = steps[2].handler

    def scan_with_coverage(run: ScanRun) -> ScanRun:
        try:
            updated = original_scan(run)
        except PipelineStageFailure as error:
            if coverage_errors and error.code == "dependency_manifest_not_found":
                # No resource is invented. Existing partial-report handling can
                # still deliver the trustworthy omitted-path evidence.
                raise PipelineStageFailure(error.code, error.public_message, True) from error
            raise
        if not coverage_errors:
            return updated
        all_evidence = [*updated.evidence, *coverage_evidence]
        summary = updated.summary.model_copy(update={"evidence_count": len(all_evidence)})
        tools = [*updated.provenance.tool_versions, coverage_evidence[0].producer]
        provenance = updated.provenance.model_copy(update={"tool_versions": tools})
        return replace_run(updated, evidence=all_evidence, errors=[*updated.errors, *coverage_errors],
                           summary=summary, provenance=provenance)

    steps[2] = PipelineStep(steps[2].stage, scan_with_coverage)
    return PipelinePlan(tuple(steps))


__all__ = ["GitIngestionFactory", "build_public_git_dependency_plan"]
