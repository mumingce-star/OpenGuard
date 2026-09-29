export const graphNodeKinds = [
  "project",
  "component",
  "ai_asset",
  "license_observation",
  "evidence",
  "finding",
  "obligation",
] as const;

export type GraphNodeKind = (typeof graphNodeKinds)[number];

export const graphEdgeTypes = [
  "PROJECT_HAS_RESOURCE",
  "RESOURCE_HAS_LICENSE_OBSERVATION",
  "RESOURCE_SUPPORTED_BY_EVIDENCE",
  "RESOURCE_HAS_FINDING",
  "FINDING_SUPPORTED_BY_EVIDENCE",
  "FINDING_REFERENCES_OBLIGATION",
  "LICENSE_HAS_RULE_OBLIGATION",
] as const;

export type GraphEdgeType = (typeof graphEdgeTypes)[number];

export type GraphNode = {
  id: string;
  kind: GraphNodeKind;
  source_id: string;
  label: string;
};

export type SourcePointer = { scan_id: string; pointer: string };

export type GraphEdge = {
  id: string;
  type: GraphEdgeType;
  source: string;
  target: string;
  source_refs: SourcePointer[];
};

export type GraphScanRef = {
  scan_id: string;
  revision: string | null;
  facts_hash: string;
  input_hash: string;
  inventory_hash: string | null;
  status: "queued" | "running" | "completed" | "partial" | "failed" | "cancelled";
  registry_revision: number;
};

export type ResourceGraphView = {
  schema_version: "1.0";
  view_id: string;
  formal: false;
  scan_ref: GraphScanRef;
  filter: { resource_ids: string[]; resource_kinds: ("component" | "ai_asset")[] };
  nodes: GraphNode[];
  edges: GraphEdge[];
  coverage: {
    view_complete: true;
    scope: "all" | "filtered";
    node_count: number;
    edge_count: number;
    scan_gaps: string[];
  };
  capacity: { max_nodes: number; max_edges: number };
  provenance: {
    producer: { name: string; version: string };
    source_refs: GraphScanRef[];
    assessment_refs: never[];
    generated_at: string;
    algorithm_version: string;
    parameters_hash: string;
  };
};

export type PositionedGraphNode = GraphNode & { x: number; y: number };
