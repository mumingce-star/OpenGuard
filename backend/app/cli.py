"""Offline command-line demonstration for the secure local ZIP intake slice."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence, TextIO

from app.ingestion.inventory import Inventory
from app.ingestion.zip_stream import ZipIngestionService
from app.security.errors import IngestionSecurityError

if TYPE_CHECKING:
    from app.ingestion import ReadOnlyScanSession
    from app.scanners import JavascriptP0MappingResult, PythonP0MappingResult
    from app.scanners import ScanCodePipelineResult


_SCHEMA = "openguard.zip-inventory"
_VERSION = "1"
_USAGE_ERROR = IngestionSecurityError("invalid_request", "invalid_arguments")
_INPUT_ERROR = IngestionSecurityError("invalid_request", "input_file_unavailable")
_RUNTIME_ERROR = IngestionSecurityError("scanner_failed", "cli_runtime_failed")


@dataclass(frozen=True)
class _PythonDependenciesFailure:
    """A private value lets the scan service perform its mandatory final checks."""

    code: str
    reason: str


@dataclass(frozen=True)
class _JavascriptDependenciesFailure:
    code: str
    reason: str


def inventory_payload(inventory: Inventory) -> dict[str, object]:
    """Build the sole successful CLI representation from the stable inventory DTO."""

    return {
        "schema": _SCHEMA,
        "version": _VERSION,
        "root_digest": inventory.root_digest,
        "entries": [
            {
                "relative_path": entry.relative_path,
                "size_bytes": entry.size_bytes,
                "sha256": entry.sha256,
            }
            for entry in inventory.entries
        ],
    }


def run_local_zip(archive_path: Path, workspace_root: Path) -> Inventory:
    """Ingest one local archive without exposing workspace or parser details."""

    try:
        archive_stream = archive_path.open("rb")
    except OSError as error:
        raise _INPUT_ERROR from error

    service: ZipIngestionService | None = None
    try:
        service = ZipIngestionService(workspace_root)
        with archive_stream:
            return service.ingest(archive_stream)
    finally:
        if service is not None:
            service.close()


def python_dependency_payload(inventory: Inventory, mapping: PythonP0MappingResult) -> dict[str, object]:
    """Serialize the frozen B1 parser/mapper outcome without eliding null fields."""

    # These imports intentionally remain inside the new CLI mode.  The legacy
    # inventory command must not load or execute either B1 stage.
    from app.scanners import PythonP0MappingResult

    if type(mapping) is not PythonP0MappingResult:
        raise _RUNTIME_ERROR
    return {
        "schema": "openguard.python-dependencies",
        "version": "1",
        "root_digest": inventory.root_digest,
        "mapper_schema_version": mapping.schema_version,
        "parser_schema_version": "b1-python-manifest/v1",
        "status": mapping.status.value,
        "components": [item.model_dump(mode="json") for item in mapping.components],
        "evidence": [item.model_dump(mode="json") for item in mapping.evidence],
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity,
                "manifest_path": item.manifest_path,
                "field_locator": item.field_locator,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "message": item.message,
            }
            for item in mapping.diagnostics
        ],
    }


def run_local_zip_python_dependencies(
    archive_path: Path,
    workspace_root: Path,
    *,
    clock: Callable[[], datetime],
) -> tuple[Inventory, PythonP0MappingResult]:
    """Run the sealed A2 intake, B1 parser, and P0 mapper in one read session."""

    from app.ingestion import ScanReadLimits
    from app.scanners import map_python_manifest_result, parse_python_manifests

    try:
        archive_stream = archive_path.open("rb")
    except OSError as error:
        raise _INPUT_ERROR from error

    service: ZipIngestionService | None = None
    try:
        service = ZipIngestionService(workspace_root)

        def consume(session: ReadOnlyScanSession) -> PythonP0MappingResult | _PythonDependenciesFailure:
            try:
                parsed = parse_python_manifests(session)
                observed_at = clock()
                return map_python_manifest_result(
                    parsed,
                    root_digest=session.inventory.root_digest,
                    observed_at=observed_at,
                )
            except IngestionSecurityError as error:
                return _PythonDependenciesFailure(error.code, error.reason)
            except Exception:
                return _PythonDependenciesFailure(_RUNTIME_ERROR.code, _RUNTIME_ERROR.reason)

        with archive_stream:
            result = service.ingest_with_consumer(
                archive_stream,
                consume,
                read_limits=ScanReadLimits(single_file_max_bytes=262_144, total_max_bytes=4_194_304),
            )
        if isinstance(result.consumer_result, _PythonDependenciesFailure):
            raise IngestionSecurityError(result.consumer_result.code, result.consumer_result.reason)
        return result.inventory, result.consumer_result
    finally:
        if service is not None:
            service.close()


def javascript_dependency_payload(inventory: Inventory, mapping: JavascriptP0MappingResult) -> dict[str, object]:
    """Serialize the frozen JavaScript parser/mapper output with P0 null fields."""
    from app.scanners import JavascriptP0MappingResult

    if type(mapping) is not JavascriptP0MappingResult:
        raise _RUNTIME_ERROR
    return {
        "schema": "openguard.javascript-dependencies", "version": "1", "root_digest": inventory.root_digest,
        "mapper_schema_version": mapping.schema_version, "parser_schema_version": "b1-javascript-manifest/v1",
        "status": mapping.status.value,
        "components": [item.model_dump(mode="json") for item in mapping.components],
        "evidence": [item.model_dump(mode="json") for item in mapping.evidence],
        "diagnostics": [{"code": item.code, "severity": item.severity, "manifest_path": item.manifest_path, "field_locator": item.field_locator, "start_line": item.start_line, "end_line": item.end_line, "message": item.message} for item in mapping.diagnostics],
    }


def scancode_license_payload(inventory: Inventory, result: ScanCodePipelineResult) -> dict[str, object]:
    """Serialize pending ScanCode license evidence without SPDX conclusions."""
    return {
        "schema": "openguard.scancode-license-evidence", "version": "1", "root_digest": inventory.root_digest,
        "tool_version": result.tool_version,
        "license_candidates": list(result.mapping.license_candidates),
        "evidence": [item.model_dump(mode="json") for item in result.mapping.evidence],
    }


def run_local_zip_scancode_licenses(
    archive_path: Path, workspace_root: Path, *, executable: str, tool_version: str, clock: Callable[[], datetime]
) -> tuple[Inventory, ScanCodePipelineResult]:
    """Run ScanCode only through the sealed descriptor-backed ZIP tree flow."""
    from app.scanners import scan_sealed_tree
    try:
        archive_stream = archive_path.open("rb")
    except OSError as error:
        raise _INPUT_ERROR from error
    service: ZipIngestionService | None = None
    try:
        service = ZipIngestionService(workspace_root)
        with archive_stream:
            result = service.ingest_with_tree_consumer(
                archive_stream,
                lambda tree, inventory: scan_sealed_tree(
                    tree, inventory, executable=executable, tool_version=tool_version, observed_at=clock()
                ),
            )
        return result.inventory, result.consumer_result
    finally:
        if service is not None:
            service.close()


def run_local_zip_javascript_dependencies(
    archive_path: Path, workspace_root: Path, *, clock: Callable[[], datetime]
) -> tuple[Inventory, JavascriptP0MappingResult]:
    """Run JS parsing only as a bounded A2-2 trusted consumer."""
    from app.ingestion import ScanReadLimits
    from app.scanners import map_javascript_manifest_result, parse_javascript_manifests

    try:
        archive_stream = archive_path.open("rb")
    except OSError as error:
        raise _INPUT_ERROR from error
    service: ZipIngestionService | None = None
    try:
        service = ZipIngestionService(workspace_root)

        def consume(session: ReadOnlyScanSession) -> JavascriptP0MappingResult | _JavascriptDependenciesFailure:
            try:
                parsed = parse_javascript_manifests(session)
                return map_javascript_manifest_result(parsed, root_digest=session.inventory.root_digest, observed_at=clock())
            except IngestionSecurityError as error:
                return _JavascriptDependenciesFailure(error.code, error.reason)
            except Exception:
                return _JavascriptDependenciesFailure(_RUNTIME_ERROR.code, _RUNTIME_ERROR.reason)

        with archive_stream:
            result = service.ingest_with_consumer(archive_stream, consume, read_limits=ScanReadLimits(single_file_max_bytes=2 * 1024 * 1024, total_max_bytes=8 * 1024 * 1024))
        if isinstance(result.consumer_result, _JavascriptDependenciesFailure):
            raise IngestionSecurityError(result.consumer_result.code, result.consumer_result.reason)
        return result.inventory, result.consumer_result
    finally:
        if service is not None:
            service.close()


def _write_error(error: IngestionSecurityError, stream: TextIO) -> None:
    stream.write(f"{error.code}:{error.reason}\n")


def main(
    arguments: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int:
    """Run the local-only demonstration and return a process-compatible status."""

    args = list(sys.argv[1:] if arguments is None else arguments)
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    if args == ["--help"]:
        output.write("usage: python -m app.cli LOCAL_ZIP\n")
        return 0
    python_dependencies = len(args) == 2 and args[0] == "--python-dependencies"
    javascript_dependencies = len(args) == 2 and args[0] == "--javascript-dependencies"
    scancode_licenses = len(args) == 2 and args[0] == "--scancode-licenses"
    if not python_dependencies and not javascript_dependencies and not scancode_licenses and len(args) != 1:
        _write_error(_USAGE_ERROR, errors)
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="openguard-zip-cli-") as directory:
            if python_dependencies:
                now = clock or (lambda: datetime.now(timezone.utc))
                inventory, mapping = run_local_zip_python_dependencies(Path(args[1]), Path(directory), clock=now)
            elif javascript_dependencies:
                now = clock or (lambda: datetime.now(timezone.utc))
                inventory, mapping = run_local_zip_javascript_dependencies(Path(args[1]), Path(directory), clock=now)
            elif scancode_licenses:
                executable = os.environ.get("OPENGUARD_SCANCODE_BIN")
                if not executable:
                    raise IngestionSecurityError("scanner_failed", "external_scanner_unavailable")
                now = clock or (lambda: datetime.now(timezone.utc))
                inventory, mapping = run_local_zip_scancode_licenses(
                    Path(args[1]), Path(directory), executable=executable, tool_version="32.5.0", clock=now
                )
            else:
                inventory = run_local_zip(Path(args[0]), Path(directory))
    except IngestionSecurityError as error:
        _write_error(error, errors)
        return 1 if error.code != "invalid_request" else 2
    except (OSError, RuntimeError):
        _write_error(_RUNTIME_ERROR, errors)
        return 1

    payload = (
        python_dependency_payload(inventory, mapping) if python_dependencies else
        javascript_dependency_payload(inventory, mapping) if javascript_dependencies else
        scancode_license_payload(inventory, mapping) if scancode_licenses else inventory_payload(inventory)
    )
    json.dump(payload, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
