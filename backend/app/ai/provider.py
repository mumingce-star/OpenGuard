"""Strict, deterministic boundary for injected AI remediation providers."""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.domain.models import (
    Evidence,
    FindingOutcome,
    ProducerRef,
    ProducerType,
    Remediation,
    RiskFinding,
    ScanError,
    ScanRun,
    ScanStage,
    VerificationStatus,
)


_INPUT_SCHEMA = "openguard.ai-remediation-input/v1"
_OUTPUT_SCHEMA = "openguard.ai-remediation/v1"
_MAX_RESPONSE_BYTES = 64 * 1024
_NAMESPACE = uuid.UUID("92e3059e-f59c-4b2b-960d-44d9e91c0b51")
_SENSITIVE_FRAGMENT = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|authorization|bearer)\s*[=:]"
)
_ABSOLUTE_PATH_FRAGMENT = re.compile(
    r"(?:(?<![A-Za-z0-9_./])/(?!/)|(?<![A-Za-z0-9_])[A-Za-z]:[\\/]|(?<![A-Za-z0-9_])\\\\)"
)
_ELIGIBLE_OUTCOMES = frozenset(
    {FindingOutcome.WARNING, FindingOutcome.REVIEW_REQUIRED, FindingOutcome.UNKNOWN}
)


class Provider(Protocol):
    """Transport-neutral provider implemented by a later local or remote adapter."""

    mode: Literal["local", "remote"]
    producer: ProducerRef

    def generate(self, payload: str, timeout_seconds: float) -> str: ...


class AIProviderError(RuntimeError):
    """Stable caller/configuration failure at the A5 boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AIProviderResult:
    status: Literal["generated", "skipped", "disabled", "degraded"]
    run: ScanRun


@dataclass(frozen=True)
class _ProviderSnapshot:
    mode: Literal["local", "remote"]
    producer: ProducerRef
    generate: Any


def _fail(code: str) -> None:
    raise AIProviderError(code) from None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _snapshot_provider(provider: object) -> _ProviderSnapshot:
    try:
        mode = provider.mode  # type: ignore[attr-defined]
        producer = provider.producer  # type: ignore[attr-defined]
        generate = provider.generate  # type: ignore[attr-defined]
        if type(mode) is not str or mode not in {"local", "remote"}:
            raise ValueError
        if type(producer) is not ProducerRef or producer.type is not ProducerType.AI:
            raise ValueError
        if not callable(generate):
            raise ValueError
        producer_snapshot = ProducerRef.model_validate(producer.model_dump(mode="python"))
    except Exception:
        _fail("ai_invalid_argument")
    return _ProviderSnapshot(mode=mode, producer=producer_snapshot, generate=generate)


def _unsafe_text(value: object) -> bool:
    return (
        type(value) is not str
        or _SENSITIVE_FRAGMENT.search(value) is not None
        or _ABSOLUTE_PATH_FRAGMENT.search(value) is not None
    )


def _request_payload(run: ScanRun, finding: RiskFinding) -> tuple[str, set[str]]:
    evidence_by_id = {item.id: item for item in run.evidence}
    resource_by_id = {item.id: item for item in [*run.components, *run.ai_assets]}
    license_by_id = {item.id: item for item in run.licenses}

    resource = resource_by_id[finding.resource_id]
    licenses = []
    if resource.license_expression_id is not None:
        licenses.append(license_by_id[resource.license_expression_id])

    finding_evidence = [evidence_by_id[item_id] for item_id in finding.evidence_ids]
    license_evidence_ids = sorted(
        {item_id for license_ in licenses for item_id in license_.evidence_ids}
    )
    license_evidence = [evidence_by_id[item_id] for item_id in license_evidence_ids]
    allowed_evidence_ids = {item.id for item in [*finding_evidence, *license_evidence]}

    def dump_evidence(items: list[Evidence]) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in sorted(items, key=lambda item: item.id)]

    payload = {
        "schema_version": _INPUT_SCHEMA,
        "language": "en",
        "finding": finding.model_dump(mode="json"),
        "evidence": dump_evidence(finding_evidence),
        "licenses": [
            item.model_dump(mode="json") for item in sorted(licenses, key=lambda item: item.id)
        ],
        "license_evidence": dump_evidence(license_evidence),
        "forbidden": "Do not add or modify resource, license, obligation, rule, outcome, or severity facts.",
    }
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        allowed_evidence_ids,
    )


def _decode_response(
    raw: object, *, finding_id: str, allowed_evidence_ids: set[str]
) -> dict[str, Any]:
    if type(raw) is not str:
        raise ValueError("response must be text")
    try:
        if len(raw.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
        )
    except (TypeError, UnicodeError, ValueError):
        raise ValueError("invalid JSON response") from None

    required = {"schema_version", "finding_id", "summary", "steps", "evidence_ids"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("invalid response shape")
    if value["schema_version"] != _OUTPUT_SCHEMA or value["finding_id"] != finding_id:
        raise ValueError("response identity mismatch")

    summary = value["summary"]
    steps = value["steps"]
    evidence_ids = value["evidence_ids"]
    if _unsafe_text(summary) or not summary.strip() or len(summary) > 1000:
        raise ValueError("invalid summary")
    if (
        type(steps) is not list
        or not 1 <= len(steps) <= 8
        or any(_unsafe_text(item) or not item.strip() or len(item) > 1000 for item in steps)
    ):
        raise ValueError("invalid steps")
    if (
        type(evidence_ids) is not list
        or not 1 <= len(evidence_ids) <= 32
        or any(type(item) is not str for item in evidence_ids)
        or len(set(evidence_ids)) != len(evidence_ids)
        or not set(evidence_ids).issubset(allowed_evidence_ids)
    ):
        raise ValueError("invalid evidence references")

    return {
        "schema_version": _OUTPUT_SCHEMA,
        "finding_id": finding_id,
        "summary": summary,
        "steps": sorted(set(steps)),
        "evidence_ids": sorted(evidence_ids),
    }


def _with_ai_provenance(run: ScanRun, producer: ProducerRef) -> dict[str, Any]:
    payload = run.model_dump(mode="python")
    payload["provenance"] = run.provenance.model_copy(
        update={"ai_enabled": True, "ai_model": producer}
    )
    return payload


def _degraded(run: ScanRun, provider: _ProviderSnapshot, code: str) -> AIProviderResult:
    messages = {
        "ai_provider_unavailable": "AI remediation provider was unavailable.",
        "ai_response_invalid": "AI remediation response was rejected.",
    }
    payload = _with_ai_provenance(run, provider.producer)
    already_recorded = any(
        item.code == code and item.stage is ScanStage.AI_ASSIST for item in run.errors
    )
    if not already_recorded:
        payload["errors"] = [
            *run.errors,
            ScanError(
                code=code,
                stage=ScanStage.AI_ASSIST,
                message=messages[code],
                recoverable=True,
            ),
        ]
    return AIProviderResult(status="degraded", run=ScanRun.model_validate(payload))


def apply_ai_remediations(
    run: ScanRun,
    provider: Provider | None,
    *,
    enabled: bool = True,
    timeout_seconds: float = 10.0,
) -> AIProviderResult:
    """Generate pending remediations without promoting model output to facts."""

    if (
        type(run) is not ScanRun
        or type(enabled) is not bool
        or type(timeout_seconds) not in {int, float}
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        _fail("ai_invalid_argument")
    try:
        ScanRun.model_validate(run.model_dump(mode="python"))
    except Exception:
        _fail("ai_invalid_argument")

    if not enabled:
        payload = run.model_dump(mode="python")
        payload["provenance"] = run.provenance.model_copy(
            update={"ai_enabled": False, "ai_model": None}
        )
        return AIProviderResult(status="disabled", run=ScanRun.model_validate(payload))

    provider_snapshot = _snapshot_provider(provider)
    eligible = [
        item
        for item in run.findings
        if item.outcome in _ELIGIBLE_OUTCOMES and item.remediation_id is None
    ]
    if not eligible:
        return AIProviderResult(status="skipped", run=run)

    remediations: list[Remediation] = []
    for finding in eligible:
        request, allowed_evidence_ids = _request_payload(run, finding)
        try:
            raw_response = provider_snapshot.generate(request, float(timeout_seconds))
        except Exception:
            return _degraded(run, provider_snapshot, "ai_provider_unavailable")
        try:
            response = _decode_response(
                raw_response,
                finding_id=finding.id,
                allowed_evidence_ids=allowed_evidence_ids,
            )
            identity = json.dumps(
                [finding.id, provider_snapshot.producer.model_dump(mode="json"), response],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            remediations.append(
                Remediation(
                    id=f"rem_{uuid.uuid5(_NAMESPACE, identity)}",
                    finding_id=finding.id,
                    summary=response["summary"],
                    steps=response["steps"],
                    evidence_ids=response["evidence_ids"],
                    generated_by=provider_snapshot.producer,
                    verification_status=VerificationStatus.PENDING,
                )
            )
        except Exception:
            return _degraded(run, provider_snapshot, "ai_response_invalid")

    payload = _with_ai_provenance(run, provider_snapshot.producer)
    payload["remediations"] = [*run.remediations, *remediations]
    remediation_ids = {item.finding_id: item.id for item in remediations}
    payload["findings"] = [
        item.model_copy(update={"remediation_id": remediation_ids.get(item.id, item.remediation_id)})
        for item in run.findings
    ]
    if provider_snapshot.producer not in run.provenance.tool_versions:
        payload["provenance"] = payload["provenance"].model_copy(
            update={"tool_versions": [*run.provenance.tool_versions, provider_snapshot.producer]}
        )
    try:
        generated = ScanRun.model_validate(payload)
    except Exception:
        return _degraded(run, provider_snapshot, "ai_response_invalid")
    return AIProviderResult(status="generated", run=generated)
