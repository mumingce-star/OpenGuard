"""Shared deterministic dependency stages after a trusted A2 ingestion."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.models import (
    Component,
    Evidence,
    FindingOutcome,
    ProducerRef,
    RunProvenance,
    ScanError,
    ScanRun,
    ScanStage,
    ScanSummary,
)
from app.ai import Provider, apply_ai_remediations
from app.ingestion import ReadOnlyScanSession, ScanReadLimits
from app.pipeline.worker import PipelineError, PipelinePlan, PipelineStageFailure, PipelineStep
from app.pipeline.license_rules import apply_license_rules
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


READ_LIMITS = ScanReadLimits(single_file_max_bytes=2 * 1024 * 1024, total_max_bytes=12 * 1024 * 1024)
ZERO_FINDINGS = {outcome: 0 for outcome in FindingOutcome}


@dataclass(frozen=True)
class LaneResult:
    name: str
    mapping: PythonP0MappingResult | JavascriptP0MappingResult | None


@dataclass(frozen=True)
class DependencyConsumerResult:
    lanes: tuple[LaneResult, LaneResult]


@dataclass
class DependencyPlanState:
    consumer_result: DependencyConsumerResult | None = None
    root_digest: str | None = None
    ingestion_producers: list[ProducerRef] = field(default_factory=list)


def fail(code: str, message: str, *, recoverable: bool = False) -> None:
    raise PipelineStageFailure(code, message, recoverable) from None


def replace_run(run: ScanRun, **changes: object) -> ScanRun:
    payload = run.model_dump(mode="python")
    payload.update(changes)
    return ScanRun.model_validate(payload)


def is_pristine(run: ScanRun) -> bool:
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
        and summary.finding_counts == ZERO_FINDINGS
    )


def consume_dependencies(session: ReadOnlyScanSession, clock: Callable[[], datetime]) -> DependencyConsumerResult:
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
    return DependencyConsumerResult(
        lanes=(LaneResult("python", python_mapping), LaneResult("javascript", javascript_mapping))
    )


def _deduplicate(items: list[Component] | list[Evidence]) -> list[Component] | list[Evidence]:
    values: dict[str, Component | Evidence] = {}
    for item in items:
        prior = values.get(item.id)
        if prior is not None and prior != item:
            fail("dependency_scan_failed", "Dependency scanning failed.")
        values[item.id] = item
    return list(values.values())


def _producer_key(producer: ProducerRef) -> str:
    return json.dumps(producer.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_dependency_plan(
    ingestion: Callable[[ScanRun], ScanRun],
    state: DependencyPlanState,
    *,
    ingestion_error_code: str,
    ingestion_error_message: str,
    ai_provider: Provider | None = None,
    ai_enabled: bool = False,
    ai_timeout_seconds: float = 10.0,
) -> PipelinePlan:
    """Attach the existing B1/A4 tail to one source-specific ingestion stage."""

    if (
        type(ai_enabled) is not bool
        or type(ai_timeout_seconds) not in {int, float}
        or isinstance(ai_timeout_seconds, bool)
        or not math.isfinite(ai_timeout_seconds)
        or ai_timeout_seconds <= 0
        or (ai_enabled and ai_provider is None)
    ):
        raise PipelineError("pipeline_invalid_argument") from None

    def inventory(run: ScanRun) -> ScanRun:
        if (
            state.consumer_result is None
            or state.root_digest is None
            or run.project.root_digest is None
            or run.provenance.inventory_digest is None
            or run.project.root_digest != run.provenance.inventory_digest
            or run.project.root_digest.value != state.root_digest
        ):
            fail(ingestion_error_code, ingestion_error_message)
        return run

    def scan(run: ScanRun) -> ScanRun:
        if state.consumer_result is None:
            fail("dependency_scan_failed", "Dependency scanning failed.")
        mappings = [lane.mapping for lane in state.consumer_result.lanes if lane.mapping is not None]
        if not mappings:
            fail("dependency_scan_failed", "Dependency scanning failed.")
        components = _deduplicate([item for mapping in mappings for item in mapping.components])
        evidence = _deduplicate([item for mapping in mappings for item in mapping.evidence])
        components.sort(key=lambda item: (item.ecosystem.encode(), item.name.encode(), (item.version or "").encode(), item.id))
        evidence.sort(key=lambda item: (item.locator.encode(), item.id))
        if not components or not evidence:
            fail("dependency_manifest_not_found", "No dependency manifest was found.")

        errors: list[ScanError] = []
        for lane in state.consumer_result.lanes:
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

        producers = {_producer_key(item.producer): item.producer for item in evidence}
        producers.update({_producer_key(item): item for item in state.ingestion_producers})
        provenance = RunProvenance.model_validate(
            {**run.provenance.model_dump(mode="python"), "tool_versions": [producers[key] for key in sorted(producers)]}
        )
        summary = ScanSummary(
            component_count=len(components),
            ai_asset_count=0,
            evidence_count=len(evidence),
            finding_counts=dict(ZERO_FINDINGS),
        )
        return replace_run(run, components=components, evidence=evidence, errors=errors, summary=summary, provenance=provenance)

    def normalize(run: ScanRun) -> ScanRun:
        return ScanRun.model_validate(run.model_dump(mode="python"))

    def rules(run: ScanRun) -> ScanRun:
        if not run.licenses:
            fail("rules_stage_not_connected", "License rules are not connected for this scan.", recoverable=True)
        return apply_license_rules(run)

    def ai_assist(run: ScanRun) -> ScanRun:
        return apply_ai_remediations(
            run,
            ai_provider,
            enabled=ai_enabled,
            timeout_seconds=float(ai_timeout_seconds),
        ).run

    def report(run: ScanRun) -> ScanRun:
        return ScanRun.model_validate(run.model_dump(mode="python"))

    return PipelinePlan(
        steps=(
            PipelineStep(ScanStage.INGESTION, ingestion),
            PipelineStep(ScanStage.INVENTORY, inventory),
            PipelineStep(ScanStage.SCAN, scan),
            PipelineStep(ScanStage.NORMALIZE, normalize),
            PipelineStep(ScanStage.RULES, rules),
            PipelineStep(ScanStage.AI_ASSIST, ai_assist),
            PipelineStep(ScanStage.REPORT, report),
        )
    )


__all__ = [
    "DependencyConsumerResult",
    "DependencyPlanState",
    "LaneResult",
    "READ_LIMITS",
    "ZERO_FINDINGS",
    "build_dependency_plan",
    "consume_dependencies",
    "fail",
    "is_pristine",
    "replace_run",
]
