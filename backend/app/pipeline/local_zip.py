"""One-shot A2/B1 local-ZIP dependency plan; no parser logic lives here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable

from app.domain.models import (
    Component,
    Evidence,
    FindingOutcome,
    HashValue,
    Project,
    RunProvenance,
    ScanError,
    ScanRun,
    ScanStage,
    ScanSummary,
    SourceType,
)
from app.ingestion import ReadOnlyScanSession, ScanReadLimits, ZipIngestionService
from app.pipeline.worker import PipelineError, PipelinePlan, PipelineStageFailure, PipelineStep
from app.scanners import (
    JavascriptP0MappingResult,
    JavascriptParseStatus,
    ParseStatus,
    PythonP0MappingResult,
    map_javascript_manifest_result,
    map_python_manifest_result,
    parse_javascript_manifests,
    parse_python_manifests,
)


_READ_LIMITS = ScanReadLimits(
    single_file_max_bytes=2 * 1024 * 1024,
    total_max_bytes=12 * 1024 * 1024,
)
_ZERO_FINDINGS = {outcome: 0 for outcome in FindingOutcome}


@dataclass(frozen=True)
class _LaneResult:
    name: str
    mapping: PythonP0MappingResult | JavascriptP0MappingResult | None


@dataclass(frozen=True)
class _ConsumerResult:
    lanes: tuple[_LaneResult, _LaneResult]


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


def _failure(code: str, message: str, *, recoverable: bool = False) -> None:
    raise PipelineStageFailure(code, message, recoverable) from None


def _replace(run: ScanRun, **changes: object) -> ScanRun:
    payload = run.model_dump(mode="python")
    payload.update(changes)
    return ScanRun.model_validate(payload)


def _is_pristine(run: ScanRun) -> bool:
    summary = run.summary
    return (
        run.project.root_digest is None
        and run.provenance.inventory_digest is None
        and not run.provenance.ai_enabled
        and run.provenance.ai_model is None
        and not any(
            (
                run.components,
                run.ai_assets,
                run.licenses,
                run.evidence,
                run.obligations,
                run.findings,
                run.remediations,
                run.errors,
                run.report_links,
            )
        )
        and summary.component_count == 0
        and summary.ai_asset_count == 0
        and summary.evidence_count == 0
        and summary.finding_counts == _ZERO_FINDINGS
    )


def _consume_dependencies(
    session: ReadOnlyScanSession,
    clock: Callable[[], datetime],
) -> _ConsumerResult:
    try:
        python_mapping = map_python_manifest_result(
            parse_python_manifests(session),
            root_digest=session.inventory.root_digest,
            observed_at=clock(),
        )
        if type(python_mapping) is not PythonP0MappingResult:
            raise TypeError
    except Exception:
        python_mapping = None

    try:
        javascript_mapping = map_javascript_manifest_result(
            parse_javascript_manifests(session),
            root_digest=session.inventory.root_digest,
            observed_at=clock(),
        )
        if type(javascript_mapping) is not JavascriptP0MappingResult:
            raise TypeError
    except Exception:
        javascript_mapping = None

    return _ConsumerResult(
        lanes=(
            _LaneResult("python", python_mapping),
            _LaneResult("javascript", javascript_mapping),
        )
    )


def _deduplicate(items: list[Component] | list[Evidence]) -> list[Component] | list[Evidence]:
    values: dict[str, Component | Evidence] = {}
    for item in items:
        prior = values.get(item.id)
        if prior is not None and prior != item:
            _failure("dependency_scan_failed", "Dependency scanning failed.")
        values[item.id] = item
    return list(values.values())


def _producer_key(evidence: Evidence) -> str:
    return json.dumps(
        evidence.producer.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_local_zip_dependency_plan(
    archive_path: Path,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
) -> PipelinePlan:
    """Build one explicit plan for one queued ZIP ScanRun."""

    if not isinstance(archive_path, Path) or not isinstance(workspace_root, Path) or not callable(clock):
        raise PipelineError("pipeline_invalid_argument") from None

    used = False
    consumer_result: _ConsumerResult | None = None
    root_digest: str | None = None

    def ingestion(run: ScanRun) -> ScanRun:
        nonlocal used, consumer_result, root_digest
        if used:
            _failure("local_zip_plan_reused", "Local ZIP plan was already used.")
        used = True
        if (
            run.project.source_type is not SourceType.ZIP
            or run.project.source != archive_path.name
            or not _is_pristine(run)
        ):
            _failure(
                "local_zip_plan_incompatible",
                "Queued scan is incompatible with this local ZIP plan.",
            )

        try:
            raw = archive_path.open("rb")
        except OSError:
            _failure("local_zip_unavailable", "Local ZIP is unavailable.")

        service: ZipIngestionService | None = None
        result = None
        failed = False
        reader: _DigestingReader | None = None
        try:
            with raw:
                reader = _DigestingReader(raw)
                service = ZipIngestionService(workspace_root)
                result = service.ingest_with_consumer(
                    reader,
                    lambda session: _consume_dependencies(session, clock),
                    read_limits=_READ_LIMITS,
                )
        except Exception:
            failed = True
        finally:
            if service is not None:
                try:
                    service.close()
                except Exception:
                    failed = True

        if failed or result is None or reader is None or type(result.consumer_result) is not _ConsumerResult:
            _failure("zip_ingestion_failed", "Local ZIP ingestion failed.")
        if reader.digest.hexdigest() != run.provenance.input_digest.value:
            _failure("input_digest_mismatch", "Local ZIP input digest did not match.")

        consumer_result = result.consumer_result
        root_digest = result.inventory.root_digest
        digest = HashValue(algorithm="sha256", value=root_digest)
        project = Project.model_validate(
            {**run.project.model_dump(mode="python"), "root_digest": digest}
        )
        provenance = RunProvenance.model_validate(
            {**run.provenance.model_dump(mode="python"), "inventory_digest": digest}
        )
        return _replace(run, project=project, provenance=provenance)

    def inventory(run: ScanRun) -> ScanRun:
        if (
            consumer_result is None
            or root_digest is None
            or run.project.root_digest is None
            or run.provenance.inventory_digest is None
            or run.project.root_digest != run.provenance.inventory_digest
            or run.project.root_digest.value != root_digest
        ):
            _failure("zip_ingestion_failed", "Local ZIP ingestion failed.")
        return run

    def scan(run: ScanRun) -> ScanRun:
        if consumer_result is None:
            _failure("dependency_scan_failed", "Dependency scanning failed.")
        mappings = [lane.mapping for lane in consumer_result.lanes if lane.mapping is not None]
        if not mappings:
            _failure("dependency_scan_failed", "Dependency scanning failed.")

        components = _deduplicate([item for mapping in mappings for item in mapping.components])
        evidence = _deduplicate([item for mapping in mappings for item in mapping.evidence])
        components.sort(
            key=lambda item: (
                item.ecosystem.encode("utf-8"),
                item.name.encode("utf-8"),
                (item.version or "").encode("utf-8"),
                item.id,
            )
        )
        evidence.sort(key=lambda item: (item.locator.encode("utf-8"), item.id))
        if not components or not evidence:
            _failure("dependency_manifest_not_found", "No dependency manifest was found.")

        errors: list[ScanError] = []
        for lane in consumer_result.lanes:
            mapping = lane.mapping
            title = "Python" if lane.name == "python" else "JavaScript"
            if mapping is None:
                errors.append(
                    ScanError(
                        code=f"{lane.name}_dependency_scan_failed",
                        stage=ScanStage.SCAN,
                        message=f"{title} dependency scan failed.",
                        recoverable=True,
                    )
                )
            elif (
                mapping.status is ParseStatus.PARTIAL
                if type(mapping) is PythonP0MappingResult
                else mapping.status is JavascriptParseStatus.PARTIAL
            ):
                errors.append(
                    ScanError(
                        code=f"{lane.name}_dependency_scan_partial",
                        stage=ScanStage.SCAN,
                        message=f"{title} dependency scan was partial.",
                        recoverable=True,
                    )
                )

        producers = {_producer_key(item): item.producer for item in evidence}
        provenance = RunProvenance.model_validate(
            {
                **run.provenance.model_dump(mode="python"),
                "tool_versions": [producers[key] for key in sorted(producers)],
            }
        )
        summary = ScanSummary(
            component_count=len(components),
            ai_asset_count=0,
            evidence_count=len(evidence),
            finding_counts=dict(_ZERO_FINDINGS),
        )
        return _replace(
            run,
            components=components,
            evidence=evidence,
            errors=errors,
            summary=summary,
            provenance=provenance,
        )

    def normalize(run: ScanRun) -> ScanRun:
        return ScanRun.model_validate(run.model_dump(mode="python"))

    def rules(run: ScanRun) -> ScanRun:
        _failure(
            "rules_stage_not_connected",
            "License rules are not connected for this scan.",
            recoverable=True,
        )

    def unreachable(run: ScanRun) -> ScanRun:
        _failure("pipeline_stage_failed", "Pipeline stage failed unexpectedly.")

    return PipelinePlan(
        steps=(
            PipelineStep(ScanStage.INGESTION, ingestion),
            PipelineStep(ScanStage.INVENTORY, inventory),
            PipelineStep(ScanStage.SCAN, scan),
            PipelineStep(ScanStage.NORMALIZE, normalize),
            PipelineStep(ScanStage.RULES, rules),
            PipelineStep(ScanStage.AI_ASSIST, unreachable),
            PipelineStep(ScanStage.REPORT, unreachable),
        )
    )
