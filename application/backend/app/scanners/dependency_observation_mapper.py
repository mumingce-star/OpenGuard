"""Map sealed lock/SBOM observations to existing P0 objects without admission.

Graph edges stay private until A/Sol approve a public graph mapping. Component
identity includes the document and instance, so workspaces never merge by name.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.domain.models import (
    Component, DetectionMethod, Evidence, EvidenceKind, HashValue,
    ProducerRef, ProducerType, VerificationStatus,
)
from app.ingestion import ReadOnlyScanSession
from app.ingestion.inventory import Inventory, InventoryEntry
from .dependency_observations import MAX_BYTES, Edge, Gap, RootObservation, read_dependency_observations, relative_path
from .ecosystem_coordinates import MANIFEST_FORMATS, MULTI_ECOSYSTEMS

_NAMESPACE = uuid.UUID("1e91b3a5-47bb-45aa-aeb1-b06f837f92ef")
_MULTI_FORMATS = {
    "go.mod": "go-mod", "go.sum": "go-sum", "Cargo.toml": "cargo-toml",
    "Cargo.lock": "cargo-lock", "pom.xml": "maven-pom", "gradle.lockfile": "gradle-lock",
}
_FORMATS_BY_NAME = {
    **_MULTI_FORMATS,
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "pdm.lock": "pdm",
    "Pipfile.lock": "pipfile",
    "package-lock.json": "npm-v1",
    "npm-shrinkwrap.json": "npm-v1",
    "bom.json": "cyclonedx-json",
    "bom.xml": "cyclonedx-xml",
}
_FORMATS_BY_SUFFIX = (
    (".cdx.json", "cyclonedx-json"),
    (".cdx.xml", "cyclonedx-xml"),
    (".spdx.json", "spdx-json"),
    (".spdx", "spdx-tag-value"),
)
_READ_BATCH_LIMIT = 4096


@dataclass(frozen=True)
class ObservationMapping:
    components: tuple[Component, ...]
    evidence: tuple[Evidence, ...]
    edges: tuple[Edge, ...]
    gaps: tuple[Gap, ...]
    status: str
    format: str = ""
    source_path: str = ""
    source_sha256: str = ""
    root: RootObservation | None = None


@dataclass(frozen=True)
class _SealedDocument:
    inventory: Inventory
    raw: bytes

    def read_bytes(self, path: str, *, max_bytes: int) -> bytes:
        if path != self.inventory.entries[0].relative_path or len(self.raw) > max_bytes:
            raise ValueError("inventory_entry_invalid")
        return self.raw


def _rejected_mapping(entry, format, root, observed_at, reason):
    identity = uuid.uuid5(_NAMESPACE, f"{root}:{entry.relative_path}:{entry.sha256}:document")
    evidence = Evidence(
        id=f"evd_{identity}", kind=EvidenceKind.FILE, locator=entry.relative_path,
        content_hash=HashValue(algorithm="sha256", value=entry.sha256),
        detected_by=DetectionMethod.MANIFEST_PARSER,
        producer=ProducerRef(type=ProducerType.PARSER, name="openguard.dependency-observations.diagnostic",
                             version="b58/1", config_digest=HashValue(algorithm="sha256", value=root)),
        observed_at=observed_at, verification_status=VerificationStatus.PENDING,
    )
    return ObservationMapping((), (evidence,), (), (Gap(reason, entry.relative_path),), "partial",
                              format, entry.relative_path, entry.sha256)


def collect_dependency_observations(
    session: ReadOnlyScanSession,
    observed_at: datetime,
    *,
    remaining_budget: int,
    reserve_for_existing_root: int = 0,
) -> tuple[ObservationMapping, ...]:
    """Read recognized documents after the existing dependency lanes."""
    available = min(remaining_budget, session.remaining_read_bytes)
    inventory = session.inventory
    selected: list[tuple[InventoryEntry, str]] = []
    mappings = []
    rejected_count = 0
    entries = sorted(inventory.entries, key=lambda item: (
        item.relative_path.rsplit("/", 1)[-1] in _MULTI_FORMATS, item.relative_path))
    for entry in entries:
        name = entry.relative_path.rsplit("/", 1)[-1]
        format = _FORMATS_BY_NAME.get(name)
        if format is None:
            format = next((kind for suffix, kind in _FORMATS_BY_SUFFIX if name.endswith(suffix)), None)
        if format is None:
            continue
        try:
            relative_path(entry.relative_path)
        except ValueError:
            continue
        new_format = name in _MULTI_FORMATS
        budget = available - reserve_for_existing_root if new_format else available
        if not 0 < entry.size_bytes <= min(MAX_BYTES, budget):
            if new_format and rejected_count < 64:
                reason = "input_limit_exceeded" if not 0 < entry.size_bytes <= MAX_BYTES else "read_budget_exhausted"
                mappings.append(_rejected_mapping(entry, format, inventory.root_digest, observed_at, reason))
                rejected_count += 1
            continue
        selected.append((entry, format))
        available -= entry.size_bytes

    for start in range(0, len(selected), _READ_BATCH_LIMIT):
        batch = selected[start:start + _READ_BATCH_LIMIT]
        paths = tuple(entry.relative_path for entry, _ in batch)
        raw_by_path = session.read_many_bytes(paths, max_bytes=MAX_BYTES)
        for entry, format in batch:
            path = entry.relative_path
            document = _SealedDocument(Inventory((entry,), inventory.root_digest), raw_by_path[path])
            try:
                mapping = map_sealed_dependency_document(document, path, format=format, observed_at=observed_at)
            except ValueError as error:
                if format not in _MULTI_FORMATS.values():
                    continue
                reason = str(error)
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason):
                    reason = "invalid_document"
                mapping = _rejected_mapping(entry, format, inventory.root_digest, observed_at, reason)
            if (format in _MULTI_FORMATS.values() and mapping.gaps
                    and not any(item.locator == path for item in mapping.evidence)):
                diagnostic = _rejected_mapping(entry, format, inventory.root_digest, observed_at, mapping.gaps[0].code)
                mapping = replace(mapping, evidence=(*mapping.evidence, *diagnostic.evidence))
            mappings.append(mapping)
    return tuple(mappings)


def map_sealed_dependency_document(session, path: str, *, format: str,
                                   observed_at: datetime) -> ObservationMapping:
    root = session.inventory.root_digest
    if type(root) is not str or not re.fullmatch(r"[0-9a-f]{64}", root):
        raise ValueError("invalid_root_digest")
    if (type(observed_at) is not datetime or observed_at.tzinfo is None
            or observed_at.utcoffset() != timezone.utc.utcoffset(observed_at)):
        raise ValueError("observation_time_not_utc")
    result = read_dependency_observations(session, path, format=format)
    def identifier(prefix, key):
        material = json.dumps([root, path, result.source_sha256, result.format, key], separators=(",", ":"))
        return f"{prefix}_{uuid.uuid5(_NAMESPACE, material)}"
    components, evidence, gaps, identities = [], [], list(result.gaps), {}
    kind = result.format.split("/", 1)[0]
    source_kind = ("sbom" if result.format.startswith(("cyclonedx-", "spdx-"))
                   else "manifest" if kind in MANIFEST_FORMATS else "lock")
    format_ecosystems = {
        "uv": "pypi", "poetry": "pypi", "pdm": "pypi", "pipfile": "pypi", "npm-lock": "npm",
        "go-mod": "golang", "go-sum": "golang", "cargo-toml": "cargo", "cargo-lock": "cargo",
        "maven-pom": "maven", "gradle-lock": "maven",
    }
    for node in result.nodes:
        if len(node.name) > 200 or node.version is not None and len(node.version) > 200 or len(node.locator) > 2048:
            gaps.append(Gap("component_contract_limit", node.locator)); continue
        component_id, evidence_id = identifier("cmp", node.instance_id), identifier("evd", node.locator)
        identities[node.instance_id] = component_id
        line = int(node.locator.rsplit("#L", 1)[1]) if result.format.startswith("spdx-tag-value/") else None
        purl_type = node.purl.partition("/")[0].removeprefix("pkg:") if node.purl else "unknown"
        ecosystem = format_ecosystems.get(kind, purl_type if purl_type in MULTI_ECOSYSTEMS | {"pypi", "npm"} else "unknown")
        excerpt = json.dumps(node.excerpt, ensure_ascii=False) if node.excerpt is not None else None
        if excerpt and (len(excerpt) > 1000 or re.search(r"(?i)(?:api[_-]?key|secret|token|password)\s*[=:]", excerpt)):
            gaps.append(Gap("selector_excerpt_withheld", node.locator))
            excerpt = None
        evidence.append(Evidence(
            id=evidence_id, kind=EvidenceKind.FILE if line else EvidenceKind.MANIFEST_FIELD,
            locator=path if line else node.locator, start_line=line, end_line=line, excerpt=excerpt,
            content_hash=HashValue(algorithm="sha256", value=result.source_sha256),
            detected_by=DetectionMethod.MANIFEST_PARSER,
            producer=ProducerRef(type=ProducerType.PARSER, name=f"openguard.dependency-observations.{source_kind}",
                                 version="b58/1", config_digest=HashValue(algorithm="sha256", value=root)),
            observed_at=observed_at, verification_status=VerificationStatus.PENDING,
        ))
        components.append(Component(
            id=component_id, name=node.name, version=node.version, ecosystem=ecosystem,
            purl=node.purl, evidence_ids=[evidence_id], detected_by=[DetectionMethod.MANIFEST_PARSER],
            confidence=1.0,  # Exact parsed field, not authorization or runtime confidence.
        ))
    edges = []
    for edge in result.edges:
        if edge.parent not in identities or edge.child not in identities:
            gaps.append(Gap("mapped_edge_endpoint_missing", edge.locator))
        else:
            edges.append(Edge(identities[edge.parent], identities[edge.child], edge.locator))
    return ObservationMapping(tuple(components), tuple(evidence), tuple(edges),
                              tuple(sorted(set(gaps))), "partial" if gaps else "complete",
                              format, result.source_path, result.source_sha256, result.root)
