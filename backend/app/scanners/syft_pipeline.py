"""Trusted Syft orchestration for a sealed A2 ZIP tree."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from app.ingestion import TrustedTreeScan
from app.ingestion.inventory import Inventory
from app.security.errors import IngestionSecurityError
from app.domain.models import HashValue
from .external_tools import SyftMappingResult, map_syft_output, parse_json_output, run_syft_sbom_scan

@dataclass(frozen=True)
class SyftPipelineResult:
    mapping: SyftMappingResult
    tool_version: str

def _relative_locations(payload: Mapping[str, Any], target: str) -> dict[str, Any]:
    """Syft directory scans emit paths rooted at the declared scan source."""
    output = dict(payload)
    artifacts: list[object] = []
    normalized_target = target.replace("\\", "/").rstrip("/")
    prefix = normalized_target + "/"
    source = payload.get("source", {})
    source_is_target = (isinstance(source, Mapping) and source.get("type") == "directory"
                        and isinstance(source.get("metadata"), Mapping)
                        and source["metadata"].get("path") == target)
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, Mapping) or not isinstance(artifact.get("name"), str) or not artifact["name"].strip():
            raise ValueError("invalid artifact")
        if not isinstance(artifact.get("locations"), list) or not artifact["locations"]:
            raise ValueError("artifact missing source")
        copy = dict(artifact); locations: list[object] = []
        for location in artifact.get("locations", []):
            if not isinstance(location, Mapping):
                raise ValueError("invalid location")
            if isinstance(location, Mapping):
                item = dict(location)
                path = item.get("path")
                if isinstance(path, str):
                    if "\\" in path:
                        raise ValueError("invalid path")
                    normalized_path = path
                    if normalized_path.startswith(prefix):
                        item["path"] = normalized_path[len(prefix):]
                    elif source_is_target and normalized_path.startswith("/") and not normalized_path.startswith("//"):
                        item["path"] = normalized_path[1:]
                locations.append(item)
        copy["locations"] = locations; artifacts.append(copy)
    output["artifacts"] = artifacts
    return output

def scan_sealed_tree(tree: TrustedTreeScan, inventory: Inventory, *, executable: str, tool_version: str, observed_at: datetime) -> SyftPipelineResult:
    target = tree.proc_target(); execution = run_syft_sbom_scan(executable, target, pass_fds=tree.inherited_fds)
    payload = parse_json_output(execution)
    if payload is None: raise IngestionSecurityError("scanner_failed", execution.error_code or "external_scanner_invalid_output")
    try:
        normalized = _relative_locations(payload, target)
        entries = {entry.relative_path: entry for entry in inventory.entries}
        for artifact in normalized.get("artifacts", []):
            for location in artifact.get("locations", []):
                if location.get("path") not in entries:
                    raise ValueError("observation outside inventory")
        mapping = map_syft_output(normalized, root_digest=inventory.root_digest, observed_at=observed_at, tool_version=tool_version)
        mapping = SyftMappingResult(mapping.components, tuple(
            item.model_copy(update={"content_hash": HashValue(algorithm="sha256", value=entries[item.locator].sha256)})
            for item in mapping.evidence
        ))
    except (TypeError, ValueError) as error:
        raise IngestionSecurityError("scanner_failed", "external_scanner_invalid_output") from error
    return SyftPipelineResult(mapping=mapping, tool_version=tool_version)
