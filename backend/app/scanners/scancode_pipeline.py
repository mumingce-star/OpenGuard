"""Trusted ScanCode orchestration for a sealed A2 ZIP tree."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

    execution = run_scancode_license_scan(executable, tree.proc_target(), pass_fds=tree.inherited_fds)
    payload = parse_json_output(execution)
    if payload is None:
        raise IngestionSecurityError("scanner_failed", execution.error_code or "external_scanner_invalid_output")
    try:
        entries = {entry.relative_path: entry for entry in inventory.entries}
        observed_paths = set()
        for item in payload.get("files", []):
            if not isinstance(item, dict) or item.get("scan_errors"):
                raise ValueError("invalid file observation")
            if item.get("type") == "directory":
                continue
            entry = entries.get(item.get("path"))
            if entry is None or (item.get("sha256") is not None and item["sha256"] != entry.sha256):
                raise ValueError("observation outside inventory")
            observed_paths.add(item["path"])
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
