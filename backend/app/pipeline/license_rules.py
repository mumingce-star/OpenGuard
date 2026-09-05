"""A4 adapter for the teammate-owned B5 license rule engine."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.models import FindingOutcome, ScanRun, ScanSummary
from app.pipeline.worker import PipelineStageFailure
from app.rules import RuleEvaluationResult, RuleSet, evaluate, load_ruleset


RuleEvaluator = Callable[..., RuleEvaluationResult]


def _fail(code: str, message: str, *, recoverable: bool = False) -> None:
    raise PipelineStageFailure(code, message, recoverable) from None


def apply_license_rules(
    run: ScanRun,
    *,
    ruleset: RuleSet | None = None,
    evaluator: RuleEvaluator = evaluate,
) -> ScanRun:
    """Evaluate already-linked license facts without implementing B5 logic."""

    if type(run) is not ScanRun or (ruleset is not None and type(ruleset) is not RuleSet) or not callable(evaluator):
        _fail("license_rules_invalid_argument", "License rule evaluation could not start.")
    if run.obligations or run.findings or run.remediations:
        _fail("license_rule_state_conflict", "License rule evaluation found conflicting prior results.")

    resources = [*run.components, *run.ai_assets]
    linked_resources = [item for item in resources if item.license_expression_id is not None]
    if not resources or len(linked_resources) != len(resources) or not run.licenses:
        _fail(
            "license_facts_unavailable",
            "License facts are unavailable for rule evaluation.",
            recoverable=True,
        )

    licenses = {item.id: item for item in run.licenses}
    selected_ruleset = ruleset
    try:
        if selected_ruleset is None:
            selected_ruleset = load_ruleset()
        results = []
        for resource in sorted(linked_resources, key=lambda item: item.id):
            license_expression = licenses.get(resource.license_expression_id)
            if license_expression is None:
                raise ValueError
            result = evaluator(
                resource,
                license_expression,
                run.evidence,
                ruleset=selected_ruleset,
            )
            if type(result) is not RuleEvaluationResult:
                raise TypeError
            results.append(result)
    except Exception:
        _fail("license_rules_failed", "License rule evaluation failed.")

    obligations = [item for result in results for item in result.obligations]
    findings = [item for result in results for item in result.findings]
    remediations = [item for result in results for item in result.remediations]
    aggregate_ids = [item.id for item in [*obligations, *findings, *remediations]]
    if len(aggregate_ids) != len(set(aggregate_ids)):
        _fail("license_rule_state_conflict", "License rule evaluation found conflicting results.")

    finding_counts = {outcome: 0 for outcome in FindingOutcome}
    for finding in findings:
        finding_counts[finding.outcome] += 1
    summary = ScanSummary(
        component_count=len(run.components),
        ai_asset_count=len(run.ai_assets),
        evidence_count=len(run.evidence),
        finding_counts=finding_counts,
    )
    provenance = run.provenance.model_copy(
        update={"ruleset_version": selected_ruleset.version}
    )
    payload = run.model_dump(mode="python")
    payload.update(
        obligations=sorted(obligations, key=lambda item: item.id),
        findings=sorted(findings, key=lambda item: item.id),
        remediations=sorted(remediations, key=lambda item: item.id),
        summary=summary,
        provenance=provenance,
    )
    try:
        return ScanRun.model_validate(payload)
    except Exception:
        _fail("license_rules_failed", "License rule evaluation failed.")
    raise AssertionError("unreachable")


__all__ = ["apply_license_rules"]
