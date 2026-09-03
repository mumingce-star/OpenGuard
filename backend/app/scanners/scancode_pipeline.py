"""Trusted ScanCode orchestration for a sealed A2 ZIP tree."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.ingestion import TrustedTreeScan
from app.ingestion.inventory import Inventory
from app.security.errors import IngestionSecurityError

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
        mapping = map_scancode_output(
            payload, root_digest=inventory.root_digest, observed_at=observed_at, tool_version=tool_version
        )
    except (TypeError, ValueError) as error:
        raise IngestionSecurityError("scanner_failed", "external_scanner_invalid_output") from error
    return ScanCodePipelineResult(mapping=mapping, tool_version=tool_version)
