"""Offline command-line demonstration for the secure local ZIP intake slice."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, Callable, Iterator, Sequence, TextIO

from app.ingestion.inventory import Inventory
from app.ingestion.zip_stream import ZipIngestionService
from app.security.errors import IngestionSecurityError

if TYPE_CHECKING:
    from app.ingestion import ReadOnlyScanSession
    from app.scanners import JavascriptP0MappingResult, PythonP0MappingResult
    from app.scanners import ScanCodePipelineResult
    from app.scanners import SyftPipelineResult


_SCHEMA = "openguard.zip-inventory"
_VERSION = "1"
_USAGE_ERROR = IngestionSecurityError("invalid_request", "invalid_arguments")
_INPUT_ERROR = IngestionSecurityError("invalid_request", "input_file_unavailable")
_RUNTIME_ERROR = IngestionSecurityError("scanner_failed", "cli_runtime_failed")
_ZIP_MODES = ("--python-dependencies", "--javascript-dependencies", "--scancode-licenses", "--syft-sbom")


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


@contextmanager
def _zip_ingestion(
    archive_path: Path, workspace_root: Path | None,
) -> Iterator[tuple[BinaryIO, ZipIngestionService]]:
    try:
        stream = archive_path.open("rb")
    except OSError as error:
        raise _INPUT_ERROR from error

    with ExitStack() as stack:
        stack.enter_context(stream)
        if workspace_root is None:
            workspace_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="openguard-zip-cli-")))
        service = ZipIngestionService(workspace_root)
        stack.callback(service.close)
        yield stream, service


def run_local_zip(archive_path: Path, workspace_root: Path | None) -> Inventory:
    """Ingest one local archive without exposing workspace or parser details."""
    with _zip_ingestion(archive_path, workspace_root) as (archive_stream, service):
        return service.ingest(archive_stream)


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
    workspace_root: Path | None,
    *,
    clock: Callable[[], datetime],
) -> tuple[Inventory, PythonP0MappingResult]:
    """Run the sealed A2 intake, B1 parser, and P0 mapper in one read session."""

    from app.ingestion import ScanReadLimits
    from app.scanners import map_python_manifest_result, parse_python_manifests

    with _zip_ingestion(archive_path, workspace_root) as (archive_stream, service):

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

        result = service.ingest_with_consumer(
            archive_stream,
            consume,
            read_limits=ScanReadLimits(single_file_max_bytes=262_144, total_max_bytes=4_194_304),
        )
        if isinstance(result.consumer_result, _PythonDependenciesFailure):
            raise IngestionSecurityError(result.consumer_result.code, result.consumer_result.reason)
        return result.inventory, result.consumer_result


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
    archive_path: Path, workspace_root: Path | None, *, executable: str, tool_version: str, clock: Callable[[], datetime]
) -> tuple[Inventory, ScanCodePipelineResult]:
    """Run ScanCode only through the sealed descriptor-backed ZIP tree flow."""
    from app.scanners import scan_sealed_tree

    with _zip_ingestion(archive_path, workspace_root) as (archive_stream, service):
        result = service.ingest_with_tree_consumer(
            archive_stream,
            lambda tree, inventory: scan_sealed_tree(
                tree, inventory, executable=executable, tool_version=tool_version, observed_at=clock()
            ),
        )
        return result.inventory, result.consumer_result


def syft_sbom_payload(inventory: Inventory, result: SyftPipelineResult) -> dict[str, object]:
    return {"schema": "openguard.syft-sbom", "version": "1", "root_digest": inventory.root_digest,
            "tool_version": result.tool_version,
            "components": [item.model_dump(mode="json") for item in result.mapping.components],
            "evidence": [item.model_dump(mode="json") for item in result.mapping.evidence]}


def run_local_zip_syft_sbom(
    archive_path: Path, workspace_root: Path | None, *, executable: str, tool_version: str, clock: Callable[[], datetime],
) -> tuple[Inventory, SyftPipelineResult]:
    from app.scanners import scan_syft_sealed_tree

    with _zip_ingestion(archive_path, workspace_root) as (archive_stream, service):
        result = service.ingest_with_tree_consumer(
            archive_stream,
            lambda tree, inventory: scan_syft_sealed_tree(
                tree, inventory, executable=executable, tool_version=tool_version, observed_at=clock()
            ),
        )
        return result.inventory, result.consumer_result


def run_local_zip_javascript_dependencies(
    archive_path: Path, workspace_root: Path | None, *, clock: Callable[[], datetime]
) -> tuple[Inventory, JavascriptP0MappingResult]:
    """Run JS parsing only as a bounded A2-2 trusted consumer."""
    from app.ingestion import ScanReadLimits
    from app.scanners import map_javascript_manifest_result, parse_javascript_manifests

    with _zip_ingestion(archive_path, workspace_root) as (archive_stream, service):

        def consume(session: ReadOnlyScanSession) -> JavascriptP0MappingResult | _JavascriptDependenciesFailure:
            try:
                parsed = parse_javascript_manifests(session)
                return map_javascript_manifest_result(parsed, root_digest=session.inventory.root_digest, observed_at=clock())
            except IngestionSecurityError as error:
                return _JavascriptDependenciesFailure(error.code, error.reason)
            except Exception:
                return _JavascriptDependenciesFailure(_RUNTIME_ERROR.code, _RUNTIME_ERROR.reason)

        result = service.ingest_with_consumer(archive_stream, consume, read_limits=ScanReadLimits(single_file_max_bytes=2 * 1024 * 1024, total_max_bytes=8 * 1024 * 1024))
        if isinstance(result.consumer_result, _JavascriptDependenciesFailure):
            raise IngestionSecurityError(result.consumer_result.code, result.consumer_result.reason)
        return result.inventory, result.consumer_result


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
    if len(args) == 1 and args[0] and not args[0].startswith("-"):
        mode = None
    elif len(args) == 2 and args[0] in _ZIP_MODES and args[1] and not args[1].startswith("-"):
        mode = args[0]
    else:
        _write_error(_USAGE_ERROR, errors)
        return 2

    archive = Path(args[-1])
    now = clock or (lambda: datetime.now(timezone.utc))
    try:
        if mode == "--python-dependencies":
            inventory, mapping = run_local_zip_python_dependencies(archive, None, clock=now)
            payload = python_dependency_payload(inventory, mapping)
        elif mode == "--javascript-dependencies":
            inventory, mapping = run_local_zip_javascript_dependencies(archive, None, clock=now)
            payload = javascript_dependency_payload(inventory, mapping)
        elif mode == "--scancode-licenses":
            executable = os.environ.get("OPENGUARD_SCANCODE_BIN")
            if not executable:
                raise IngestionSecurityError("scanner_failed", "external_scanner_unavailable")
            inventory, mapping = run_local_zip_scancode_licenses(
                archive, None, executable=executable, tool_version="32.5.0", clock=now
            )
            payload = scancode_license_payload(inventory, mapping)
        elif mode == "--syft-sbom":
            executable = os.environ.get("OPENGUARD_SYFT_BIN")
            if not executable:
                raise IngestionSecurityError("scanner_failed", "external_scanner_unavailable")
            inventory, mapping = run_local_zip_syft_sbom(
                archive, None, executable=executable, tool_version="1.51.0", clock=now
            )
            payload = syft_sbom_payload(inventory, mapping)
        else:
            payload = inventory_payload(run_local_zip(archive, None))
    except IngestionSecurityError as error:
        _write_error(error, errors)
        return 1 if error.code != "invalid_request" else 2
    except (OSError, RuntimeError):
        _write_error(_RUNTIME_ERROR, errors)
        return 1

    json.dump(payload, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
