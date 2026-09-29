import { request } from "./scans";
import {
  graphEdgeTypes,
  graphNodeKinds,
  type GraphEdge,
  type GraphEdgeType,
  type GraphNode,
  type GraphNodeKind,
  type GraphScanRef,
  type PositionedGraphNode,
  type ResourceGraphView,
  type SourcePointer,
} from "../types/p1Graph";

const hash = /^[0-9a-f]{64}$/;
const utc = /Z$/;
const statuses = ["queued", "running", "completed", "partial", "failed", "cancelled"] as const;

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  return value as Record<string, unknown>;
}

function exact(value: unknown, keys: string[]) {
  const row = object(value);
  if (Object.keys(row).length !== keys.length || keys.some((key) => !(key in row))) fail();
  return row;
}

function text(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function texts(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}

function fail(): never {
  throw new Error("资源关系图响应不符合冻结 Graph API 契约，已拒绝展示。");
}

function scanRef(value: unknown, scanId: string): GraphScanRef {
  const row = exact(value, ["scan_id", "revision", "facts_hash", "input_hash", "inventory_hash", "status", "registry_revision"]);
  if (
    row.scan_id !== scanId ||
    !(row.revision === null || text(row.revision)) ||
    !text(row.facts_hash) || !hash.test(row.facts_hash) ||
    !text(row.input_hash) || !hash.test(row.input_hash) ||
    !(row.inventory_hash === null || (text(row.inventory_hash) && hash.test(row.inventory_hash))) ||
    !statuses.includes(row.status as (typeof statuses)[number]) ||
    !Number.isInteger(row.registry_revision) || Number(row.registry_revision) < 1
  ) fail();
  return row as GraphScanRef;
}

function node(value: unknown): GraphNode {
  const row = exact(value, ["id", "kind", "source_id", "label"]);
  if (!text(row.id) || !graphNodeKinds.includes(row.kind as GraphNodeKind) || !text(row.source_id) || !text(row.label)) fail();
  return row as GraphNode;
}

function pointer(value: unknown, scanId: string): SourcePointer {
  const row = exact(value, ["scan_id", "pointer"]);
  if (row.scan_id !== scanId || !text(row.pointer) || !row.pointer.startsWith("/")) fail();
  return row as SourcePointer;
}

function edge(value: unknown, scanId: string): GraphEdge {
  const row = exact(value, ["id", "type", "source", "target", "source_refs"]);
  if (!text(row.id) || !graphEdgeTypes.includes(row.type as GraphEdgeType) || !text(row.source) || !text(row.target) || !Array.isArray(row.source_refs) || !row.source_refs.length) fail();
  return { ...row, source_refs: row.source_refs.map((item) => pointer(item, scanId)) } as GraphEdge;
}

export function parseResourceGraph(value: unknown, scanId: string): ResourceGraphView {
  const row = exact(value, ["schema_version", "view_id", "formal", "scan_ref", "filter", "nodes", "edges", "coverage", "capacity", "provenance"]);
  if (row.schema_version !== "1.0" || !text(row.view_id) || row.formal !== false || !Array.isArray(row.nodes) || !Array.isArray(row.edges)) fail();
  const ref = scanRef(row.scan_ref, scanId);
  const filter = exact(row.filter, ["resource_ids", "resource_kinds"]);
  if (!texts(filter.resource_ids) || !Array.isArray(filter.resource_kinds) || !filter.resource_kinds.every((kind) => kind === "component" || kind === "ai_asset")) fail();
  const nodes = row.nodes.map(node), edges = row.edges.map((item) => edge(item, scanId));
  const nodeIds = new Set(nodes.map((item) => item.id));
  if (nodeIds.size !== nodes.length || new Set(edges.map((item) => item.id)).size !== edges.length || edges.some((item) => !nodeIds.has(item.source) || !nodeIds.has(item.target))) fail();
  const coverage = exact(row.coverage, ["view_complete", "scope", "node_count", "edge_count", "scan_gaps"]);
  if (coverage.view_complete !== true || (coverage.scope !== "all" && coverage.scope !== "filtered") || coverage.node_count !== nodes.length || coverage.edge_count !== edges.length || !texts(coverage.scan_gaps)) fail();
  const capacity = exact(row.capacity, ["max_nodes", "max_edges"]);
  if (!Number.isInteger(capacity.max_nodes) || Number(capacity.max_nodes) < nodes.length || !Number.isInteger(capacity.max_edges) || Number(capacity.max_edges) < edges.length) fail();
  const provenance = exact(row.provenance, ["producer", "source_refs", "assessment_refs", "generated_at", "algorithm_version", "parameters_hash"]);
  const producer = exact(provenance.producer, ["name", "version"]);
  if (!text(producer.name) || !text(producer.version) || !Array.isArray(provenance.source_refs) || !provenance.source_refs.length || !Array.isArray(provenance.assessment_refs) || provenance.assessment_refs.length || !text(provenance.generated_at) || !utc.test(provenance.generated_at) || !Number.isFinite(Date.parse(provenance.generated_at)) || !text(provenance.algorithm_version) || !text(provenance.parameters_hash) || !hash.test(provenance.parameters_hash)) fail();
  const sourceRefs = provenance.source_refs.map((item) => scanRef(item, scanId));
  if (!sourceRefs.some((item) => item.scan_id === ref.scan_id && item.facts_hash === ref.facts_hash)) fail();
  return { ...row, scan_ref: ref, filter: filter as ResourceGraphView["filter"], nodes, edges, coverage: coverage as ResourceGraphView["coverage"], capacity: capacity as ResourceGraphView["capacity"], provenance: { ...provenance, producer, source_refs: sourceRefs, assessment_refs: [] } } as ResourceGraphView;
}

export async function getResourceGraph(scanId: string, signal?: AbortSignal) {
  const raw = await request("/scans/" + encodeURIComponent(scanId) + "/graph", { method: "GET" }, signal);
  return parseResourceGraph(raw, scanId);
}

export function filterResourceGraph(view: ResourceGraphView, query: string, kinds: GraphNodeKind[]) {
  const needle = query.trim().toLocaleLowerCase();
  const allowed = new Set(kinds.length ? kinds : graphNodeKinds);
  const nodes = view.nodes.filter((item) => allowed.has(item.kind) && (!needle || item.label.toLocaleLowerCase().includes(needle) || item.source_id.toLocaleLowerCase().includes(needle)));
  const ids = new Set(nodes.map((item) => item.id));
  return { nodes, edges: view.edges.filter((item) => ids.has(item.source) && ids.has(item.target)) };
}

export type EdgeAppearance = "solid" | "dashed" | "dotted";
export function edgeAppearance(type: GraphEdgeType): EdgeAppearance {
  if (type === "PROJECT_HAS_RESOURCE") return "solid";
  if (type === "RESOURCE_SUPPORTED_BY_EVIDENCE" || type === "FINDING_SUPPORTED_BY_EVIDENCE") return "dotted";
  return "dashed";
}

const columns: Record<GraphNodeKind, number> = { project: 0, component: 1, ai_asset: 1, license_observation: 2, finding: 2, evidence: 3, obligation: 3 };
export function layoutResourceGraph(nodes: GraphNode[]): { nodes: PositionedGraphNode[]; width: number; height: number } {
  const grouped = new Map<number, GraphNode[]>();
  for (const item of nodes) grouped.set(columns[item.kind], [...(grouped.get(columns[item.kind]) ?? []), item]);
  const gapX = 270, gapY = 78, margin = 70;
  const largest = Math.max(1, ...Array.from(grouped.values(), (items) => items.length));
  const indexes = new Map<number, number>();
  const positioned = nodes.map((item) => {
    const group = grouped.get(columns[item.kind]) ?? [];
    const index = indexes.get(columns[item.kind]) ?? 0;
    indexes.set(columns[item.kind], index + 1);
    const offset = ((largest - group.length) * gapY) / 2;
    return { ...item, x: margin + columns[item.kind] * gapX, y: margin + offset + index * gapY };
  });
  return { nodes: positioned, width: margin * 2 + gapX * 3 + 180, height: margin * 2 + Math.max(0, largest - 1) * gapY + 60 };
}

export const graphKindLabels: Record<GraphNodeKind, string> = { project: "项目", component: "组件", ai_asset: "AI 资源", license_observation: "许可观测", evidence: "证据", finding: "待核查线索", obligation: "义务" };
export const graphEdgeLabels: Record<GraphEdgeType, string> = { PROJECT_HAS_RESOURCE: "项目包含资源", RESOURCE_HAS_LICENSE_OBSERVATION: "资源具有许可观测", RESOURCE_SUPPORTED_BY_EVIDENCE: "资源由证据支持", RESOURCE_HAS_FINDING: "资源具有待核查线索", FINDING_SUPPORTED_BY_EVIDENCE: "线索由证据支持", FINDING_REFERENCES_OBLIGATION: "线索引用义务", LICENSE_HAS_RULE_OBLIGATION: "许可规则包含义务" };
