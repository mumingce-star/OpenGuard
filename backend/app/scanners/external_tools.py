"""Safe, deterministic adapters for ScanCode and Syft JSON output.

The adapters never execute project code.  They accept tool JSON as data and
provide an optional subprocess wrapper which uses an argument vector (never a
shell), a timeout, and a bounded captured output.  Passing a materialized
directory to a third-party tool is deliberately left to a future trusted
pipeline boundary; ``ReadOnlyScanSession`` must remain a parser-only
capability.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.domain.models import (
    Component,
    ComponentType,
    DetectionMethod,
    Evidence,
    EvidenceKind,
    HashValue,
    ProducerRef,
    ProducerType,
    VerificationStatus,
)


ADAPTER_VERSION = "b2-b3-external-tools/v1"
_NAMESPACE = uuid.UUID("14e5b272-a2b3-5c27-a5fd-e1e152c7c80d")
_MAX_OUTPUT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ToolExecution:
    """A sanitized external-tool execution result suitable for a later ScanError."""

    tool: str
    status: str
    stdout: bytes | None
    error_code: str | None = None


@dataclass(frozen=True)
class ScanCodeMappingResult:
    evidence: tuple[Evidence, ...]
    license_candidates: tuple[str, ...]


@dataclass(frozen=True)
class SyftMappingResult:
    components: tuple[Component, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class ComponentMergeDiagnostic:
    code: str
    component_ids: tuple[str, ...]


@dataclass(frozen=True)
class ComponentMergeResult:
    components: tuple[Component, ...]
    diagnostics: tuple[ComponentMergeDiagnostic, ...]


def _id(prefix: str, material: Sequence[object]) -> str:
    canonical = json.dumps(list(material), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{prefix}_{uuid.uuid5(_NAMESPACE, canonical)}"


def _valid_root_digest(root_digest: str) -> bool:
    return len(root_digest) == 64 and all(character in "0123456789abcdef" for character in root_digest)


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("observed_at must be UTC")


def _relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")) or "\\" in value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return value


def _sha256(value: object) -> HashValue | None:
    if isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value):
        return HashValue(algorithm="sha256", value=value)
    return None


def _producer(name: str, version: str, root_digest: str) -> ProducerRef:
    return ProducerRef(
        type=ProducerType.SCANNER,
        name=name,
        version=version,
        config_digest=HashValue(algorithm="sha256", value=root_digest),
    )


def run_json_tool(
    tool: str,
    arguments: Sequence[str],
    *,
    timeout_seconds: int = 120,
    max_output_bytes: int = _MAX_OUTPUT_BYTES,
) -> ToolExecution:
    """Run a preconstructed tool command without a shell or leaked diagnostics.

    This low-level helper intentionally does not accept a project path.  A
    trusted orchestrator must construct a fixed ScanCode/Syft invocation after
    enforcing its own filesystem isolation policy.
    """

    if not tool or timeout_seconds <= 0 or max_output_bytes <= 0 or max_output_bytes > _MAX_OUTPUT_BYTES:
        raise ValueError("invalid external tool limits")
    try:
        completed = subprocess.run(
            [tool, *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            # Do not forward process credentials.  These are the minimum
            # platform variables required to locate an already-installed tool.
            env={
                key: os.environ[key]
                for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "TMPDIR", "TEMP", "TMP")
                if key in os.environ
            },
        )
    except FileNotFoundError:
        return ToolExecution(tool, "unavailable", None, "tool_unavailable")
    except subprocess.TimeoutExpired:
        return ToolExecution(tool, "timeout", None, "scanner_timeout")
    except OSError:
        return ToolExecution(tool, "failed", None, "scanner_failed")
    if len(completed.stdout) > max_output_bytes:
        return ToolExecution(tool, "failed", None, "tool_output_limit_exceeded")
    if completed.returncode != 0:
        return ToolExecution(tool, "failed", None, "scanner_failed")
    return ToolExecution(tool, "complete", completed.stdout)


def parse_json_output(execution: ToolExecution) -> Mapping[str, Any] | None:
    """Decode one bounded tool output, returning ``None`` for invalid JSON."""

    if execution.status != "complete" or execution.stdout is None:
        return None
    try:
        value = json.loads(execution.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def map_scancode_output(
    payload: Mapping[str, Any], *, root_digest: str, observed_at: datetime, tool_version: str
) -> ScanCodeMappingResult:
    """Map ScanCode file-level license observations to evidence, not conclusions.

    SPDX normalization is intentionally deferred to B4, so candidate strings
    are retained separately and no ``LicenseExpression`` is manufactured here.
    """

    if not _valid_root_digest(root_digest) or not tool_version:
        raise ValueError("invalid ScanCode mapping input")
    _utc(observed_at)
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("invalid ScanCode output")
    producer = _producer("scancode", tool_version, root_digest)
    evidence: dict[str, Evidence] = {}
    candidates: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping):
            continue
        path = _relative_path(item.get("path"))
        if path is None:
            continue
        raw_detections = item.get("license_detections", [])
        expressions: list[str] = []
        if isinstance(item.get("detected_license_expression"), str):
            expressions.append(item["detected_license_expression"])
        if isinstance(raw_detections, list):
            expressions.extend(
                detection.get("license_expression")
                for detection in raw_detections
                if isinstance(detection, Mapping) and isinstance(detection.get("license_expression"), str)
            )
        for expression in sorted({value.strip() for value in expressions if value.strip()}, key=str.encode):
            evidence_id = _id("evd", ["scancode", root_digest, path, expression])
            evidence[evidence_id] = Evidence(
                id=evidence_id,
                kind=EvidenceKind.LICENSE_TEXT,
                locator=path,
                excerpt=expression[:1000],
                content_hash=_sha256(item.get("sha256")),
                detected_by=DetectionMethod.SCANCODE,
                producer=producer,
                observed_at=observed_at,
                verification_status=VerificationStatus.PENDING,
            )
            candidates.add(expression)
    return ScanCodeMappingResult(
        tuple(sorted(evidence.values(), key=lambda value: (value.locator.encode(), value.id))),
        tuple(sorted(candidates, key=str.encode)),
    )


def _ecosystem_from_purl(purl: str | None) -> str:
    if not purl:
        return "unknown"
    if purl.startswith("pkg:pypi/"):
        return "pypi"
    if purl.startswith("pkg:npm/"):
        return "npm"
    return "unknown"


def map_syft_output(
    payload: Mapping[str, Any], *, root_digest: str, observed_at: datetime, tool_version: str
) -> SyftMappingResult:
    """Map Syft SBOM artifacts to P0 components plus locatable tool evidence."""

    if not _valid_root_digest(root_digest) or not tool_version:
        raise ValueError("invalid Syft mapping input")
    _utc(observed_at)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("invalid Syft output")
    producer = _producer("syft", tool_version, root_digest)
    components: dict[tuple[str, str, str | None], Component] = {}
    evidence: dict[str, Evidence] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("name"), str) or not artifact["name"].strip():
            continue
        name = artifact["name"].strip()
        version = artifact.get("version") if isinstance(artifact.get("version"), str) and artifact.get("version") else None
        purl = artifact.get("purl") if isinstance(artifact.get("purl"), str) and artifact["purl"].startswith("pkg:") else None
        locations = artifact.get("locations") if isinstance(artifact.get("locations"), list) else []
        evidence_ids: list[str] = []
        for location in locations:
            path = _relative_path(location.get("path")) if isinstance(location, Mapping) else None
            if path is None:
                continue
            evidence_id = _id("evd", ["syft", root_digest, name, version, purl, path])
            evidence[evidence_id] = Evidence(
                id=evidence_id,
                kind=EvidenceKind.TOOL_OUTPUT,
                locator=path,
                excerpt=f"Syft artifact: {name}"[:1000],
                content_hash=None,
                detected_by=DetectionMethod.SYFT,
                producer=producer,
                observed_at=observed_at,
                verification_status=VerificationStatus.PENDING,
            )
            evidence_ids.append(evidence_id)
        if not evidence_ids:
            continue
        ecosystem = _ecosystem_from_purl(purl)
        key = (ecosystem, name, version)
        existing = components.get(key)
        all_evidence = sorted(set((existing.evidence_ids if existing else []) + evidence_ids))
        component_id = _id("cmp", ["syft", root_digest, ecosystem, name, version, purl])
        components[key] = Component(
            id=component_id,
            name=name,
            version=version,
            ecosystem=ecosystem,
            component_type=ComponentType.LIBRARY,
            purl=purl,
            source_url=None,
            license_expression_id=None,
            evidence_ids=all_evidence,
            detected_by=[DetectionMethod.SYFT],
            confidence=0.8,
        )
    return SyftMappingResult(
        tuple(sorted(components.values(), key=lambda value: (value.ecosystem, value.name, value.version or "", value.id))),
        tuple(sorted(evidence.values(), key=lambda value: (value.locator.encode(), value.id))),
    )


def merge_components(*sources: Sequence[Component]) -> ComponentMergeResult:
    """Conservatively merge components by PURL, then canonical P0 identity.

    Conflicting license/source values are cleared rather than silently chosen;
    evidence and detection methods are retained and a diagnostic is emitted.
    """

    grouped: dict[tuple[str, ...], list[Component]] = {}
    for component in (item for source in sources for item in source):
        key = ("purl", component.purl) if component.purl else ("identity", component.ecosystem, component.name, component.version or "")
        grouped.setdefault(key, []).append(component)
    merged: list[Component] = []
    diagnostics: list[ComponentMergeDiagnostic] = []
    for key, values in grouped.items():
        values = sorted(values, key=lambda value: value.id)
        first = values[0]
        source_urls = {value.source_url for value in values}
        licenses = {value.license_expression_id for value in values}
        if len(source_urls) > 1 or len(licenses) > 1:
            diagnostics.append(ComponentMergeDiagnostic("component_metadata_conflict", tuple(value.id for value in values)))
        merged.append(first.model_copy(update={
            "evidence_ids": sorted({evidence_id for value in values for evidence_id in value.evidence_ids}),
            "detected_by": sorted({method for value in values for method in value.detected_by}, key=str),
            "confidence": min(value.confidence for value in values),
            "source_url": first.source_url if len(source_urls) == 1 else None,
            "license_expression_id": first.license_expression_id if len(licenses) == 1 else None,
        }))
    return ComponentMergeResult(
        tuple(sorted(merged, key=lambda value: (value.ecosystem, value.name, value.version or "", value.id))),
        tuple(sorted(diagnostics, key=lambda value: value.component_ids)),
    )
