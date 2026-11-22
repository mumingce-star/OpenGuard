"""Map sealed lock/SBOM observations to existing P0 objects without admission.

Graph edges stay private until A/Sol approve a public graph mapping. Component
identity includes the document and instance, so workspaces never merge by name.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.models import (
    Component, DetectionMethod, Evidence, EvidenceKind, HashValue,
    ProducerRef, ProducerType, VerificationStatus,
)
from .dependency_observations import Edge, Gap, read_dependency_observations

_NAMESPACE = uuid.UUID("1e91b3a5-47bb-45aa-aeb1-b06f837f92ef")


@dataclass(frozen=True)
class ObservationMapping:
    components: tuple[Component, ...]
    evidence: tuple[Evidence, ...]
    edges: tuple[Edge, ...]
    gaps: tuple[Gap, ...]
    status: str


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
    source_kind = "sbom" if result.format.startswith(("cyclonedx-", "spdx-")) else "lock"
    for node in result.nodes:
        if len(node.name) > 200 or node.version is not None and len(node.version) > 200 or len(node.locator) > 2048:
            gaps.append(Gap("component_contract_limit", node.locator)); continue
        component_id, evidence_id = identifier("cmp", node.instance_id), identifier("evd", node.locator)
        identities[node.instance_id] = component_id
        line = int(node.locator.rsplit("#L", 1)[1]) if result.format.startswith("spdx-tag-value/") else None
        ecosystem = ("pypi" if result.format.startswith(("uv/", "poetry/", "pdm/", "pipfile/"))
                     else "npm" if result.format.startswith("npm-lock/")
                     else "npm" if node.purl and node.purl.startswith("pkg:npm/")
                     else "pypi" if node.purl and node.purl.startswith("pkg:pypi/") else "unknown")
        evidence.append(Evidence(
            id=evidence_id, kind=EvidenceKind.FILE if line else EvidenceKind.MANIFEST_FIELD,
            locator=path if line else node.locator, start_line=line, end_line=line,
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
                              tuple(sorted(set(gaps))), "partial" if gaps else "complete")
