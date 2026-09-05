"""Safe, deterministic adapters for ScanCode and Syft JSON output.

The adapters never execute project code.  They accept tool JSON as data and
provide an optional subprocess wrapper which uses an argument vector (never a
shell), a timeout, and bounded captured output. The ZIP pipeline supplies
a sealed directory descriptor to the fixed wrappers; ``ReadOnlyScanSession``
remains a parser-only capability.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import time
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


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Stop inherited workers too, even when their group leader has exited."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # The leader can exit before a worker; never use poll() to decide
        # whether the remaining process group still needs termination.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def run_json_tool(
    tool: str,
    arguments: Sequence[str],
    *,
    timeout_seconds: int = 120,
    max_output_bytes: int = _MAX_OUTPUT_BYTES,
    pass_fds: Sequence[int] = (),
    disable_update_check: bool = False,
    scancode_runtime: bool = False,
    working_directory: str | None = None,
) -> ToolExecution:
    """Capture incrementally under a byte/deadline budget, without a shell.

    The trusted orchestrator supplies a fixed invocation after filesystem
    isolation. POSIX process groups include workers in failure cleanup.
    """

    if (
        not tool or timeout_seconds <= 0 or max_output_bytes <= 0 or max_output_bytes > _MAX_OUTPUT_BYTES
        or type(disable_update_check) is not bool or type(scancode_runtime) is not bool
        or (working_directory is not None and type(working_directory) is not str)
        or any(type(fd) is not int or fd < 0 for fd in pass_fds)
    ):
        raise ValueError("invalid external tool limits")
    if os.name != "posix":
        return ToolExecution(tool, "unavailable", None, "external_scanner_unavailable")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "TMPDIR", "TEMP", "TMP")
        if key in os.environ
    }
    if disable_update_check:
        environment["SYFT_CHECK_FOR_APP_UPDATE"] = "false"
    if scancode_runtime:
        # Fixed writable locations for the read-only scanner image. No
        # caller-provided ScanCode configuration or credentials are forwarded.
        environment["SCANCODE_CACHE"] = "/tmp/scancode-cache"
        environment["SCANCODE_TEMP"] = "/tmp"
    process = None
    try:
        deadline = time.monotonic() + timeout_seconds
        process = subprocess.Popen(
            [tool, *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, close_fds=True,
            start_new_session=True, pass_fds=tuple(pass_fds), env=environment, cwd=working_directory,
        )
        assert process.stdout is not None
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ToolExecution(tool, "timeout", None, "scanner_timeout")
                if not selector.select(remaining):
                    return ToolExecution(tool, "timeout", None, "scanner_timeout")
                try:
                    # At most one byte beyond the budget is ever read; it is
                    # discarded and never appended to the bounded accumulator.
                    chunk = os.read(process.stdout.fileno(), min(65536, max_output_bytes - len(output) + 1))
                except BlockingIOError:
                    continue
                if not chunk:
                    break
                if len(output) + len(chunk) > max_output_bytes:
                    return ToolExecution(tool, "failed", None, "tool_output_limit_exceeded")
                output.extend(chunk)
        process.wait(timeout=max(0, deadline - time.monotonic()))
        if process.returncode != 0:
            return ToolExecution(tool, "failed", None, "scanner_failed")
        return ToolExecution(tool, "complete", bytes(output))
    except FileNotFoundError:
        return ToolExecution(tool, "unavailable", None, "tool_unavailable")
    except subprocess.TimeoutExpired:
        return ToolExecution(tool, "timeout", None, "scanner_timeout")
    except OSError:
        return ToolExecution(tool, "failed", None, "scanner_failed")
    finally:
        if process is not None:
            _stop_process_group(process)
            if process.stdout is not None:
                process.stdout.close()


def _validate_proc_target(target: str, pass_fds: Sequence[int]) -> None:
    match = re.fullmatch(r"/proc/self/fd/(0|[1-9][0-9]*)", target)
    if (
        match is None or len(pass_fds) != 1 or type(pass_fds[0]) is not int
        or pass_fds[0] != int(match[1])
    ):
        raise ValueError("scanner target must match its sole inherited proc descriptor")


def run_scancode_license_scan(tool: str, target: str, *, pass_fds: Sequence[int]) -> ToolExecution:
    """Run fixed license-only ScanCode JSON over a trusted proc-FD target."""

    _validate_proc_target(target, pass_fds)
    # Resolve the trusted directory in the child before launching ScanCode;
    # scanning the proc symlink itself does not reliably traverse its files.
    return run_json_tool(
        tool, ("--processes", "1", "--license", "--strip-root", "--json", "-", "."),
        timeout_seconds=120, max_output_bytes=_MAX_OUTPUT_BYTES,
        pass_fds=pass_fds, scancode_runtime=True, working_directory=target,
    )


def run_syft_sbom_scan(tool: str, target: str, *, pass_fds: Sequence[int]) -> ToolExecution:
    """Run fixed Syft JSON over a trusted proc-FD target."""

    _validate_proc_target(target, pass_fds)
    return run_json_tool(
        tool, ("scan", f"dir:{target}", "-o", "syft-json"), timeout_seconds=120,
        max_output_bytes=_MAX_OUTPUT_BYTES, pass_fds=pass_fds, disable_update_check=True,
    )


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
