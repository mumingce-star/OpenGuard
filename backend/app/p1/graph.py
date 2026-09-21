"""Read-only, deterministic projection of one ScanRun into the P1 fact graph."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.api.service import ApiError
from app.assessment.engine import facts_digest
from app.domain.models import ScanStatus
from app.persistence import ScanRegistryError
from .history import canonical, utc


ALGORITHM = "resource-graph/1.0"
_RESOURCE_KINDS = frozenset({"component", "ai_asset"})


class GraphCapacityError(ApiError):
    """Capacity rejection with the contract's safe, graph-specific counts."""

    def __init__(self, capacity_details: dict) -> None:
        super().__init__(status_code=413, code="graph_capacity_exceeded", message="资源图超过当前容量。",
                         reason="graph_capacity_exceeded")
        self.capacity_details = capacity_details


def _fail(code: str, status: int, message: str, *, reason: str | None = None) -> None:
    error = ApiError(status_code=status, code=code, message=message, reason=reason or code)
    raise error


def _node_id(scan_id: str, kind: str, source_id: str) -> str:
    return f"{scan_id}:{kind}:{source_id}"


def _edge_id(scan_id: str, edge_type: str, source: str, target: str, refs: list[dict]) -> str:
    value = canonical({"scan_id": scan_id, "type": edge_type, "source": source, "target": target, "source_refs": refs})
    return "edge_" + hashlib.sha256(value).hexdigest()[:32]


class GraphReader:
    def __init__(self, registry, max_nodes: int = 20_000, max_edges: int = 60_000):
        if not isinstance(max_nodes, int) or isinstance(max_nodes, bool) or max_nodes < 1:
            raise ValueError("max_nodes must be a positive integer")
        if not isinstance(max_edges, int) or isinstance(max_edges, bool) or max_edges < 1:
            raise ValueError("max_edges must be a positive integer")
        self.registry, self.max_nodes, self.max_edges = registry, max_nodes, max_edges

    def _stored(self, scan_id):
        if self.registry is None:
            _fail("upstream_unavailable", 503, "扫描存储暂不可用。")
        try:
            return self.registry.get(scan_id)
        except ScanRegistryError as error:
            if error.code in {"registry_not_found", "registry_invalid_argument"}:
                _fail("not_found", 404, "扫描记录不存在。")
            _fail("upstream_unavailable", 503, "扫描存储暂不可用。")

    @staticmethod
    def _ref(stored):
        run = stored.run
        return dict(scan_id=run.id, revision=run.project.revision, facts_hash=facts_digest(run),
                    input_hash=run.provenance.input_digest.value,
                    inventory_hash=run.provenance.inventory_digest.value if run.provenance.inventory_digest else None,
                    status=run.status, registry_revision=stored.revision)

    @staticmethod
    def _filters(resource_ids, resource_kinds):
        def normalize(values, allowed=None):
            if values is None:
                return []
            if not isinstance(values, (list, tuple)):
                _fail("invalid_argument", 400, "资源筛选参数无效。", reason="resource_filter_invalid")
            result = []
            for value in values:
                if not isinstance(value, str) or not value or not value.strip() or (allowed is not None and value not in allowed):
                    _fail("invalid_argument", 400, "资源筛选参数无效。", reason="resource_filter_invalid")
                result.append(value)
            return sorted(set(result))
        return normalize(resource_ids), normalize(resource_kinds, _RESOURCE_KINDS)

    @staticmethod
    def _scan_gaps(run):
        if run.status is not ScanStatus.PARTIAL:
            return []
        # P0 already validates error messages as safe, but Graph needs only a
        # minimal coverage diagnosis, not an operational error transcript.
        return sorted({f"scan gap: {item.code}" for item in run.errors}) or ["scan partial"]

    def read(self, scan_id: str, resource_ids: list[str], resource_kinds: list[str]) -> dict:
        if not isinstance(scan_id, str) or not scan_id:
            _fail("invalid_argument", 400, "扫描标识无效。")
        ids, kinds = self._filters(resource_ids, resource_kinds)
        stored = self._stored(scan_id)
        run = stored.run
        if run.status in {ScanStatus.QUEUED, ScanStatus.RUNNING}:
            _fail("not_ready", 409, "扫描尚未完成，暂不能生成资源图。")
        if run.status not in {ScanStatus.COMPLETED, ScanStatus.PARTIAL}:
            _fail("not_comparable", 409, "扫描状态不可用于资源图。")
        resources = [("component", index, item) for index, item in enumerate(run.components)]
        resources += [("ai_asset", index, item) for index, item in enumerate(run.ai_assets)]
        by_resource_id = {item.id: (kind, index, item) for kind, index, item in resources}
        if any(resource_id not in by_resource_id for resource_id in ids):
            _fail("invalid_argument", 400, "资源筛选参数无效。", reason="resource_filter_invalid")

        filtered = bool(ids or kinds)
        id_filter, kind_filter = set(ids), set(kinds)
        selected_resources = [row for row in resources if (not id_filter or row[2].id in id_filter)
                              and (not kind_filter or row[0] in kind_filter)]
        license_by_id = {item.id: (index, item) for index, item in enumerate(run.licenses)}
        evidence_by_id = {item.id: (index, item) for index, item in enumerate(run.evidence)}
        obligation_by_id = {item.id: (index, item) for index, item in enumerate(run.obligations)}

        if filtered:
            selected_resource_ids = {item.id for _, _, item in selected_resources}
            finding_rows = [(index, item) for index, item in enumerate(run.findings) if item.resource_id in selected_resource_ids]
            selected_license_ids = {item.license_expression_id for _, _, item in selected_resources if item.license_expression_id}
            selected_obligation_ids = {oid for _, finding in finding_rows for oid in finding.obligation_ids}
            # P0 validates every finding obligation and every obligation license
            # reference.  Thus finding-referenced obligations add their one
            # license endpoint once, then one scan selects all rule obligations
            # for the resulting license set; no transitive relation exists.
            selected_license_ids.update(obligation_by_id[item_id][1].license_expression_id
                                        for item_id in selected_obligation_ids)
            selected_obligation_ids.update(item_id for item_id, (_, obligation) in obligation_by_id.items()
                                           if obligation.license_expression_id in selected_license_ids)
            selected_evidence_ids = {eid for _, _, item in selected_resources for eid in item.evidence_ids}
            selected_evidence_ids.update(eid for _, finding in finding_rows for eid in finding.evidence_ids)
            license_rows = [license_by_id[item_id] for item_id in selected_license_ids]
            obligation_rows = [obligation_by_id[item_id] for item_id in selected_obligation_ids]
            evidence_rows = [evidence_by_id[item_id] for item_id in selected_evidence_ids]
        else:
            selected_resources = resources
            finding_rows = list(enumerate(run.findings))
            license_rows = list(enumerate(run.licenses))
            obligation_rows = list(enumerate(run.obligations))
            evidence_rows = list(enumerate(run.evidence))

        nodes = [dict(id=_node_id(run.id, "project", run.project.id), kind="project", source_id=run.project.id, label=run.project.name)]
        nodes += [dict(id=_node_id(run.id, kind, item.id), kind=kind, source_id=item.id, label=item.name) for kind, _, item in selected_resources]
        nodes += [dict(id=_node_id(run.id, "license_observation", item.id), kind="license_observation", source_id=item.id, label=item.expression) for _, item in license_rows]
        # Do not emit a locator: even valid P0 locators can disclose unnecessary
        # file layout or URL details in a graph summary.
        nodes += [dict(id=_node_id(run.id, "evidence", item.id), kind="evidence", source_id=item.id, label=item.kind.value) for _, item in evidence_rows]
        nodes += [dict(id=_node_id(run.id, "finding", item.id), kind="finding", source_id=item.id, label=item.title) for _, item in finding_rows]
        nodes += [dict(id=_node_id(run.id, "obligation", item.id), kind="obligation", source_id=item.id, label=item.action) for _, item in obligation_rows]
        nodes.sort(key=lambda item: (item["kind"], item["source_id"]))

        selected_ids = {item["id"] for item in nodes}
        project_id = _node_id(run.id, "project", run.project.id)
        edges = []
        def add(edge_type, source, target, pointer):
            if source not in selected_ids or target not in selected_ids:
                return
            refs = [dict(scan_id=run.id, pointer=pointer)]
            edges.append(dict(id=_edge_id(run.id, edge_type, source, target, refs), type=edge_type, source=source, target=target, source_refs=refs))

        for kind, index, resource in selected_resources:
            resource_id = _node_id(run.id, kind, resource.id)
            collection = "components" if kind == "component" else "ai_assets"
            add("PROJECT_HAS_RESOURCE", project_id, resource_id, f"/{collection}/{index}")
            if resource.license_expression_id:
                add("RESOURCE_HAS_LICENSE_OBSERVATION", resource_id, _node_id(run.id, "license_observation", resource.license_expression_id), f"/{collection}/{index}/license_expression_id")
            for evidence_index, evidence_id in enumerate(resource.evidence_ids):
                add("RESOURCE_SUPPORTED_BY_EVIDENCE", resource_id, _node_id(run.id, "evidence", evidence_id), f"/{collection}/{index}/evidence_ids/{evidence_index}")
        for finding_index, finding in finding_rows:
            resource = by_resource_id[finding.resource_id]
            source = _node_id(run.id, resource[0], finding.resource_id)
            finding_id = _node_id(run.id, "finding", finding.id)
            add("RESOURCE_HAS_FINDING", source, finding_id, f"/findings/{finding_index}/resource_id")
            for evidence_index, evidence_id in enumerate(finding.evidence_ids):
                add("FINDING_SUPPORTED_BY_EVIDENCE", finding_id, _node_id(run.id, "evidence", evidence_id), f"/findings/{finding_index}/evidence_ids/{evidence_index}")
            for obligation_index, obligation_id in enumerate(finding.obligation_ids):
                add("FINDING_REFERENCES_OBLIGATION", finding_id, _node_id(run.id, "obligation", obligation_id), f"/findings/{finding_index}/obligation_ids/{obligation_index}")
        for obligation_index, obligation in obligation_rows:
            add("LICENSE_HAS_RULE_OBLIGATION", _node_id(run.id, "license_observation", obligation.license_expression_id), _node_id(run.id, "obligation", obligation.id), f"/obligations/{obligation_index}/license_expression_id")
        edges.sort(key=lambda item: (item["type"], item["source"], item["target"], item["id"]))

        node_count, edge_count = len(nodes), len(edges)
        if node_count > self.max_nodes or edge_count > self.max_edges:
            raise GraphCapacityError({
                "count_basis": "actual", "node_count": node_count, "edge_count": edge_count,
                "configured_capacity": {"max_nodes": self.max_nodes, "max_edges": self.max_edges},
            })
        scan_ref = self._ref(stored)
        normalized_filter = {"resource_ids": ids, "resource_kinds": kinds}
        parameters_hash = hashlib.sha256(canonical({"algorithm": ALGORITHM, "scan_ref": scan_ref, "filter": normalized_filter,
                                                     "capacity": {"max_nodes": self.max_nodes, "max_edges": self.max_edges}})).hexdigest()
        return dict(schema_version="1.0", view_id="graph_" + parameters_hash[:32], formal=False, scan_ref=scan_ref,
                    filter=normalized_filter, nodes=nodes, edges=edges,
                    coverage=dict(view_complete=True, scope="filtered" if filtered else "all", node_count=node_count,
                                  edge_count=edge_count, scan_gaps=self._scan_gaps(run)),
                    capacity=dict(max_nodes=self.max_nodes, max_edges=self.max_edges),
                    provenance=dict(producer={"name": "openguard-graph", "version": "1.0"}, source_refs=[scan_ref],
                                    assessment_refs=[], generated_at=utc(datetime.now(timezone.utc)), algorithm_version=ALGORITHM,
                                    parameters_hash=parameters_hash))
