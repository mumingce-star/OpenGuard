"""Trusted Syft orchestration for a sealed A2 ZIP tree."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from app.ingestion import TrustedTreeScan
from app.ingestion.inventory import Inventory
from app.security.errors import IngestionSecurityError
from .external_tools import SyftMappingResult, map_syft_output, parse_json_output, run_syft_sbom_scan

@dataclass(frozen=True)
class SyftPipelineResult:
    mapping: SyftMappingResult
    tool_version: str

def _relative_locations(payload: Mapping[str, Any], target: str) -> dict[str, Any]:
    """Canonicalize Syft location paths into the trusted-root path space.

    The production caller always provides a POSIX ``/proc/self/fd/<n>``
    target.  Syft's direct Windows directory mode is also supported for the
    opt-in real-output regression: it reports root-relative paths with a
    leading backslash.  That fallback is deliberately unavailable to the
    production descriptor target, so it cannot widen the ZIP scanner's trust
    boundary.
    """

    output = dict(payload)
    artifacts: list[object] = []
    normalized_target = target.replace("\\", "/").rstrip("/")
    prefix = normalized_target + "/"
    direct_directory_mode = not normalized_target.startswith("/proc/self/fd/")
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, Mapping): continue
        copy = dict(artifact); locations: list[object] = []
        for location in artifact.get("locations", []):
            if isinstance(location, Mapping):
                item = dict(location)
                path = item.get("path")
                if isinstance(path, str):
                    normalized_path = path.replace("\\", "/")
                    if normalized_path.startswith(prefix):
                        item["path"] = normalized_path[len(prefix):]
                    elif direct_directory_mode and normalized_path.startswith("/"):
                        item["path"] = normalized_path.lstrip("/")
                locations.append(item)
        copy["locations"] = locations; artifacts.append(copy)
    output["artifacts"] = artifacts
    return output

def scan_sealed_tree(tree: TrustedTreeScan, inventory: Inventory, *, executable: str, tool_version: str, observed_at: datetime) -> SyftPipelineResult:
    target = tree.proc_target(); execution = run_syft_sbom_scan(executable, target, pass_fds=tree.inherited_fds)
    payload = parse_json_output(execution)
    if payload is None: raise IngestionSecurityError("scanner_failed", execution.error_code or "external_scanner_invalid_output")
    try:
        mapping = map_syft_output(_relative_locations(payload, target), root_digest=inventory.root_digest, observed_at=observed_at, tool_version=tool_version)
    except (TypeError, ValueError) as error:
        raise IngestionSecurityError("scanner_failed", "external_scanner_invalid_output") from error
    return SyftPipelineResult(mapping=mapping, tool_version=tool_version)
