"""Capture a full A04 graph from one already-read scan for Report V2.

No live registry, HTTP, scanner, AI or persistence is used here. The caller
supplies StoredScanRun. A report service must opt in to this reader explicitly.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .models import P1AlgorithmRef, P1ResourceGraphView, P1ScanRef


class ReportGraphError(RuntimeError):
    def __init__(self, code: str, reason: str):
        self.code, self.reason = code, reason
        super().__init__(reason)


def graph_content_hash(graph: dict) -> str:
    """Hash a graph's semantics, excluding only its read-time generated_at.

    Known set-like arrays are sorted without dropping any member. Section
    hashes are separate: the report also hashes the full captured content,
    including the original generated_at, when it creates its section.
    """
    value = P1ResourceGraphView.model_validate(graph).model_dump(mode="json")
    value["provenance"].pop("generated_at")
    value["nodes"].sort(key=lambda node: node["id"])
    value["edges"].sort(key=lambda edge: edge["id"])
    for edge in value["edges"]:
        edge["source_refs"].sort(key=lambda ref: (ref["scan_id"], ref["pointer"]))
    for key in ("resource_ids", "resource_kinds"):
        value["filter"][key].sort()
    value["coverage"]["scan_gaps"].sort()
    value["provenance"]["source_refs"].sort(key=lambda ref: ref["scan_id"])
    value["provenance"]["assessment_refs"].sort(
        key=lambda ref: (ref["scan_id"], ref["assessment_id"], ref["version"])
    )
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class _CapturedRegistry:
    """An in-memory adapter, deliberately not a database registry."""
    def __init__(self, stored):
        self.stored = stored

    def get(self, scan_id):
        if scan_id != self.stored.run.id:
            raise ReportGraphError("conflict", "graph_scan_mismatch")
        return self.stored


class ReportGraphReader:
    def __init__(self, *, max_nodes: int = 20_000, max_edges: int = 60_000):
        if any(type(value) is not int or value < 1 for value in (max_nodes, max_edges)):
            raise ValueError("invalid report graph capacity")
        self.max_nodes, self.max_edges = max_nodes, max_edges

    def capture(self, stored) -> tuple[P1AlgorithmRef, dict]:
        """Return a server-built reference and complete full-scope graph.

        A04 stays the only graph algorithm. The adapter freezes its input, not
        the whole project database, and never obtains a newer scan version.
        """
        # Deferred import avoids app.api/__init__ import cycles.
        from .graph import ALGORITHM, GraphReader

        captured = deepcopy(stored)
        reader = GraphReader(_CapturedRegistry(captured),
                             max_nodes=self.max_nodes, max_edges=self.max_edges)
        raw = reader.read(captured.run.id, [], [])
        graph = P1ResourceGraphView.model_validate(raw).model_dump(mode="json")
        expected = P1ScanRef.model_validate(GraphReader._ref(captured)).model_dump(mode="json")
        if (graph["scan_ref"] != expected
                or graph["provenance"]["source_refs"] != [expected]
                or graph["provenance"]["algorithm_version"] != ALGORITHM
                or graph["formal"] is not False
                or graph["filter"] != {"resource_ids": [], "resource_kinds": []}
                or graph["coverage"]["scope"] != "all"
                or graph["coverage"]["view_complete"] is not True
                or graph["coverage"]["node_count"] != len(graph["nodes"])
                or graph["coverage"]["edge_count"] != len(graph["edges"])):
            raise ReportGraphError("upstream_unavailable", "graph_source_integrity")
        reference = P1AlgorithmRef(kind="graph", version=ALGORITHM,
                                   content_hash=graph_content_hash(graph))
        return reference, graph

    def read(self, stored, requested: P1AlgorithmRef) -> tuple[P1AlgorithmRef, dict]:
        """Verify the requested algorithm/hash against server-derived facts."""
        from .graph import ALGORITHM

        if not isinstance(requested, P1AlgorithmRef) or requested.kind != "graph":
            raise ReportGraphError("invalid_argument", "graph_reference_invalid")
        if requested.version != ALGORITHM:
            raise ReportGraphError("not_ready", "graph_algorithm_version_unavailable")
        reference, graph = self.capture(stored)
        if requested.content_hash != reference.content_hash:
            raise ReportGraphError("conflict", "graph_content_hash_mismatch")
        return reference, graph
