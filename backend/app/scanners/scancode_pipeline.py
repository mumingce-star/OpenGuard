"""Trusted ScanCode orchestration for a sealed A2 ZIP tree."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time

from app.ingestion import TrustedTreeScan
from app.ingestion.inventory import Inventory
from app.security.errors import IngestionSecurityError
from app.domain.models import HashValue

from .external_tools import ScanCodeMappingResult, map_scancode_output, parse_json_output, run_scancode_license_scan


@dataclass(frozen=True)
class ScanCodePipelineResult:
    mapping: ScanCodeMappingResult
    tool_version: str


def scan_sealed_tree(
    tree: TrustedTreeScan,
    inventory: Inventory,
    *,
    executable: str,
    tool_version: str,
    observed_at: datetime,
) -> ScanCodePipelineResult:
    """Run the fixed ScanCode command and map its bounded JSON output."""

    deadline = time.monotonic() + 120
    remaining_bytes = 8 * 1024 * 1024

    def invoke(relative_file=None):
        nonlocal remaining_bytes
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise IngestionSecurityError("scanner_failed", "scanner_timeout")
        if remaining_bytes <= 0:
            raise IngestionSecurityError("scanner_failed", "tool_output_limit_exceeded")
        execution = run_scancode_license_scan(
            executable, tree.proc_target(), pass_fds=tree.inherited_fds,
            relative_file=relative_file, timeout_seconds=remaining_seconds,
            max_output_bytes=remaining_bytes,
        )
        remaining_bytes -= len(execution.stdout or b"")
        if remaining_bytes < 0:
            raise IngestionSecurityError("scanner_failed", "tool_output_limit_exceeded")
        if time.monotonic() > deadline:
            raise IngestionSecurityError("scanner_failed", "scanner_timeout")
        result = parse_json_output(execution)
        if result is None:
            raise IngestionSecurityError("scanner_failed", execution.error_code or "external_scanner_invalid_output")
        return result

    payload = invoke()
    try:
        entries = {entry.relative_path: entry for entry in inventory.entries}
        observed_paths = set()
        files = payload.get("files")
        if not isinstance(files, list):
            raise ValueError("invalid file observations")
        for item in files:
            if not isinstance(item, dict) or item.get("scan_errors"):
                raise ValueError("invalid file observation")
            if item.get("type") == "directory":
                continue
            entry = entries.get(item.get("path"))
            if entry is None or (item.get("sha256") is not None and item["sha256"] != entry.sha256):
                raise ValueError("observation outside inventory")
            observed_paths.add(item["path"])
        missing = sorted(set(entries) - observed_paths)
        if len(missing) > 8:
            raise ValueError("too many missing file observations")
        # ScanCode excludes VCS-related names during its recursive walk. A
        # bounded single-file root scan covers those files without weakening
        # the inventory, path, scan-error or content-hash gates.
        for path in missing:
            supplement = invoke(path).get("files")
            if not isinstance(supplement, list) or len(supplement) != 1:
                raise ValueError("invalid single-file observation")
            item = supplement[0]
            if (
                not isinstance(item, dict) or item.get("type") != "file"
                or item.get("scan_errors")
                or item.get("path") != path.rsplit("/", 1)[-1]
                or item.get("sha256") != entries[path].sha256
            ):
                raise ValueError("single-file observation does not match inventory")
            files.append({**item, "path": path})
            observed_paths.add(path)
        if observed_paths != set(entries):
            raise ValueError("incomplete file coverage")
        mapping = map_scancode_output(
            payload, root_digest=inventory.root_digest, observed_at=observed_at, tool_version=tool_version
        )
        mapping = ScanCodeMappingResult(
            tuple(item.model_copy(update={"content_hash": HashValue(algorithm="sha256", value=entries[item.locator].sha256)})
                  for item in mapping.evidence), mapping.license_candidates,
        )
    except (TypeError, ValueError) as error:
        raise IngestionSecurityError("scanner_failed", "external_scanner_invalid_output") from error
    return ScanCodePipelineResult(mapping=mapping, tool_version=tool_version)
