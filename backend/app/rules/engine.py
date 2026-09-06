"""Offline, YAML-data-driven license obligation and risk prompts.

This module produces compliance reminders, never a legal conclusion.  A rule
can only promote a recognized license when its P0 license object and at least
one supporting evidence item are both verified.  Unsupported, ambiguous, or
insufficiently evidenced inputs are represented as ``unknown`` or
``review_required`` rather than guessed as a pass.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.domain.models import (
    AIAsset,
    Component,
    Evidence,
    FindingOutcome,
    LicenseExpression,
    Obligation,
    ProducerRef,
    ProducerType,
    Remediation,
    RiskFinding,
    Severity,
    VerificationStatus,
)


_NAMESPACE = uuid.UUID("5c8e3f3c-9811-5feb-9ec5-2c6ae7c90c6e")
_RULE_DIRECTORY = Path(__file__).resolve().parents[3] / "rules"
_DEFAULT_RULE_FILE = _RULE_DIRECTORY / "license-obligations.yaml"


@dataclass(frozen=True)
class LicenseRule:
    id: str
    version: str
    license_ids: tuple[str, ...]
    severity: Severity
    title: str
    obligation_action: str
    obligation_trigger: str
    obligation_description: str
    remediation_summary: str
    remediation_steps: tuple[str, ...]


@dataclass(frozen=True)
class RuleSet:
    version: str
    source_digest: str
    rules: tuple[LicenseRule, ...]


@dataclass(frozen=True)
class RuleEvaluationResult:
    obligations: tuple[Obligation, ...]
    findings: tuple[RiskFinding, ...]
    remediations: tuple[Remediation, ...]


def _id(prefix: str, parts: Sequence[object]) -> str:
    material = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{prefix}_{uuid.uuid5(_NAMESPACE, material)}"


def _require_string(value: object, field: str, *, maximum: int = 2_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"invalid rule {field}")
    return value


def _require_string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"invalid rule {field}")
    items = tuple(_require_string(item, field) for item in value)
    if len(set(items)) != len(items):
        raise ValueError(f"duplicate rule {field}")
    return items


def load_ruleset(path: str | Path = _DEFAULT_RULE_FILE) -> RuleSet:
    """Load a strict JSON subset of YAML from a repository-owned rule file.

    JSON is valid YAML 1.2 and avoids a new parser dependency in the P0
    scanner.  The format is intentionally data-only: no tags, anchors,
    interpolation, includes, or executable expressions are accepted.
    """

    file_path = Path(path)
    try:
        raw = file_path.read_bytes()
        document = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid ruleset document") from error
    if not isinstance(document, Mapping) or set(document) != {"ruleset_version", "rules"}:
        raise ValueError("invalid ruleset document")
    version = _require_string(document["ruleset_version"], "ruleset_version", maximum=100)
    raw_rules = document["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("invalid ruleset rules")
    rules: list[LicenseRule] = []
    required = {
        "id", "version", "license_ids", "severity", "title", "obligation", "remediation"
    }
    for item in raw_rules:
        if not isinstance(item, Mapping) or set(item) != required:
            raise ValueError("invalid ruleset rule")
        obligation = item["obligation"]
        remediation = item["remediation"]
        if not isinstance(obligation, Mapping) or set(obligation) != {"action", "trigger", "description"}:
            raise ValueError("invalid rule obligation")
        if not isinstance(remediation, Mapping) or set(remediation) != {"summary", "steps"}:
            raise ValueError("invalid rule remediation")
        try:
            severity = Severity(_require_string(item["severity"], "severity", maximum=20))
        except ValueError as error:
            raise ValueError("invalid rule severity") from error
        rules.append(LicenseRule(
            id=_require_string(item["id"], "id", maximum=200),
            version=_require_string(item["version"], "version", maximum=100),
            license_ids=_require_string_list(item["license_ids"], "license_ids"),
            severity=severity,
            title=_require_string(item["title"], "title", maximum=300),
            obligation_action=_require_string(obligation["action"], "obligation.action", maximum=200),
            obligation_trigger=_require_string(obligation["trigger"], "obligation.trigger", maximum=1_000),
            obligation_description=_require_string(obligation["description"], "obligation.description"),
            remediation_summary=_require_string(remediation["summary"], "remediation.summary", maximum=1_000),
            remediation_steps=_require_string_list(remediation["steps"], "remediation.steps"),
        ))
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError("duplicate rule id")
    return RuleSet(version=version, source_digest=hashlib.sha256(raw).hexdigest(), rules=tuple(sorted(rules, key=lambda rule: rule.id)))


def _resource_fields(resource: Component | AIAsset) -> tuple[str, str]:
    if isinstance(resource, Component):
        return "component", resource.id
    if isinstance(resource, AIAsset):
        return "ai_asset", resource.id
    raise TypeError("resource must be Component or AIAsset")


def _producer(ruleset: RuleSet) -> ProducerRef:
    return ProducerRef(
        type=ProducerType.RULE_ENGINE,
        name="openguard-license-rules",
        version=ruleset.version,
        config_digest={"algorithm": "sha256", "value": ruleset.source_digest},
    )


def _finding(
    *, resource_kind: str, resource_id: str, outcome: FindingOutcome, severity: Severity,
    title: str, rule_id: str, rule_version: str, trigger: str, evidence_ids: Sequence[str], confidence: float,
) -> RiskFinding:
    return RiskFinding(
        id=_id("rsk", [resource_kind, resource_id, rule_id, rule_version, outcome, sorted(evidence_ids)]),
        resource_kind=resource_kind, resource_id=resource_id, outcome=outcome, severity=severity,
        title=title,
        description="This is an evidence-based compliance reminder, not legal advice. Review the license text and the intended distribution before acting.",
        rule_id=rule_id, rule_version=rule_version, trigger=trigger,
        evidence_ids=list(sorted(set(evidence_ids))), obligation_ids=[], remediation_id=None, confidence=confidence,
    )


def evaluate(
    resource: Component | AIAsset,
    license_expression: LicenseExpression,
    evidence: Sequence[Evidence],
    *,
    ruleset: RuleSet | None = None,
) -> RuleEvaluationResult:
    """Evaluate one resource/license relationship using verified evidence only.

    License normalization is deliberately supplied by B4 through
    ``normalized_ids``.  This evaluator does not parse SPDX expressions or
    infer a license from scanner text.
    """

    resource_kind, resource_id = _resource_fields(resource)
    if resource.license_expression_id != license_expression.id:
        raise ValueError("resource and license expression are not linked")
    selected = ruleset or load_ruleset()
    evidence_by_id = {item.id: item for item in evidence}
    if len(evidence_by_id) != len(evidence):
        raise ValueError("duplicate evidence id")
    source_evidence = [evidence_by_id[item] for item in license_expression.evidence_ids if item in evidence_by_id]
    source_ids = [item.id for item in source_evidence]
    verified = (
        license_expression.verification_status is VerificationStatus.VERIFIED
        and bool(source_evidence)
        and all(item.verification_status is VerificationStatus.VERIFIED for item in source_evidence)
    )
    normalized = set(license_expression.normalized_ids)
    matching = [rule for rule in selected.rules if normalized.intersection(rule.license_ids)]
    if not verified:
        finding = _finding(
            resource_kind=resource_kind, resource_id=resource_id, outcome=FindingOutcome.REVIEW_REQUIRED,
            severity=Severity.INFO, title="License evidence requires verification", rule_id="license-evidence-gate",
            rule_version=selected.version, trigger="License or supporting evidence is pending verification",
            evidence_ids=source_ids, confidence=0.0,
        ) if source_ids else _finding(
            resource_kind=resource_kind, resource_id=resource_id, outcome=FindingOutcome.UNKNOWN,
            severity=Severity.INFO, title="License evidence is unavailable", rule_id="license-evidence-gate",
            rule_version=selected.version, trigger="No supporting evidence is available for the linked license",
            evidence_ids=(), confidence=0.0,
        )
        return RuleEvaluationResult((), (finding,), ())
    if not matching:
        finding = _finding(
            resource_kind=resource_kind, resource_id=resource_id, outcome=FindingOutcome.UNKNOWN,
            severity=Severity.INFO, title="No rule for normalized license", rule_id="license-rule-coverage",
            rule_version=selected.version, trigger="No loaded rule matches the verified normalized license identifier",
            evidence_ids=source_ids, confidence=0.0,
        )
        return RuleEvaluationResult((), (finding,), ())

    obligations: list[Obligation] = []
    findings: list[RiskFinding] = []
    remediations: list[Remediation] = []
    producer = _producer(selected)
    for rule in matching:
        obligation_id = _id("obl", [license_expression.id, rule.id, rule.version, source_ids])
        obligation = Obligation(
            id=obligation_id, license_expression_id=license_expression.id, action=rule.obligation_action,
            trigger=rule.obligation_trigger, description=rule.obligation_description, source_evidence_ids=source_ids,
            rule_id=rule.id, rule_version=rule.version, verification_status=VerificationStatus.PENDING,
        )
        finding = _finding(
            resource_kind=resource_kind, resource_id=resource_id, outcome=FindingOutcome.REVIEW_REQUIRED,
            severity=rule.severity, title=rule.title, rule_id=rule.id, rule_version=rule.version,
            trigger=rule.obligation_trigger, evidence_ids=source_ids, confidence=0.8,
        ).model_copy(update={"obligation_ids": [obligation_id]})
        remediation_id = _id("rem", [finding.id, rule.id, rule.version])
        remediation = Remediation(
            id=remediation_id, finding_id=finding.id, summary=rule.remediation_summary,
            steps=list(rule.remediation_steps), evidence_ids=source_ids, generated_by=producer,
            verification_status=VerificationStatus.PENDING,
        )
        findings.append(finding.model_copy(update={"remediation_id": remediation_id}))
        obligations.append(obligation)
        remediations.append(remediation)
    return RuleEvaluationResult(tuple(obligations), tuple(findings), tuple(remediations))
