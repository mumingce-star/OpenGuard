import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import { runtime } from "./runtime.mjs";

const H = "a".repeat(64);
function graph(scanId = "scan-real") {
  const project = { id: `${scanId}:project:p`, kind: "project", source_id: "p", label: "Project" };
  const resource = { id: `${scanId}:component:c1`, kind: "component", source_id: "c1", label: "Component" };
  return {
    schema_version: "1.0", view_id: "view-1", formal: false,
    scan_ref: { scan_id: scanId, revision: null, facts_hash: H, input_hash: H, inventory_hash: null, status: "completed", registry_revision: 1 },
    filter: { resource_ids: [], resource_kinds: [] }, nodes: [project, resource],
    edges: [{ id: "edge-1", type: "PROJECT_HAS_RESOURCE", source: project.id, target: resource.id, source_refs: [{ scan_id: scanId, pointer: "/components/0" }] }],
    coverage: { view_complete: true, scope: "all", node_count: 2, edge_count: 1, scan_gaps: [] },
    capacity: { max_nodes: 20000, max_edges: 60000 },
    provenance: { producer: { name: "OpenGuard", version: "1" }, source_refs: [{ scan_id: scanId, revision: null, facts_hash: H, input_hash: H, inventory_hash: null, status: "completed", registry_revision: 1 }], assessment_refs: [], generated_at: "2026-09-17T00:00:00Z", algorithm_version: "resource-graph/1.0", parameters_hash: H },
  };
}

test("strictly accepts the frozen facts-only graph contract", () => {
  const service = runtime().load("services/p1Graph.ts");
  const parsed = service.parseResourceGraph(graph(), "scan-real");
  assert.equal(parsed.nodes.length, 2);
  assert.equal(parsed.edges[0].type, "PROJECT_HAS_RESOURCE");
  assert.equal(parsed.formal, false);
});

test("rejects invented edges, dangling endpoints, count drift and formal graphs", () => {
  const service = runtime().load("services/p1Graph.ts");
  for (const mutate of [
    (value) => value.edges[0].type = "depends_on",
    (value) => value.edges[0].target = "missing",
    (value) => value.coverage.node_count = 3,
    (value) => value.formal = true,
    (value) => value.provenance.assessment_refs.push({ assessment_id: "invented" }),
    (value) => value.scan_ref.scan_id = "another-scan",
  ]) {
    const value = graph(); mutate(value);
    assert.throws(() => service.parseResourceGraph(value, "scan-real"), /冻结 Graph API 契约/);
  }
});

test("real loader performs one GET and never falls back to mock", async () => {
  const run = runtime({ VITE_API_BASE_URL: "http://api.test/api/v1" });
  const service = run.load("services/p1Graph.ts");
  const calls = [];
  run.setFetch(async (url, options) => { calls.push([String(url), options.method]); return Response.json(graph()); });
  const parsed = await service.getResourceGraph("scan-real");
  assert.equal(parsed.view_id, "view-1");
  assert.equal(calls.length, 1);
  assert.match(calls[0][0], /\/scans\/scan-real\/graph$/);
  assert.equal(calls[0][1], "GET");
  run.setFetch(async () => new Response("", { status: 503 }));
  await assert.rejects(service.getResourceGraph("scan-real"), /HTTP 503/);
});

test("client search and kind filters retain only returned nodes and connecting backend edges", () => {
  const service = runtime().load("services/p1Graph.ts");
  const view = service.parseResourceGraph(graph(), "scan-real");
  const result = service.filterResourceGraph(view, "component", ["component"]);
  assert.equal(result.nodes.length, 1);
  assert.equal(result.nodes[0].source_id, "c1");
  assert.equal(result.edges.length, 0);
  assert.ok(result.nodes.every((node) => view.nodes.some((source) => source.id === node.id)));
  assert.ok(result.edges.every((edge) => view.edges.some((source) => source.id === edge.id)));
});

test("empty and partial graph payloads preserve explicit backend coverage", () => {
  const service = runtime().load("services/p1Graph.ts");
  const value = graph();
  value.nodes = []; value.edges = [];
  value.coverage = { view_complete: true, scope: "all", node_count: 0, edge_count: 0, scan_gaps: ["source coverage incomplete"] };
  value.scan_ref.status = "partial";
  value.provenance.source_refs[0].status = "partial";
  const parsed = service.parseResourceGraph(value, "scan-real");
  assert.equal(parsed.nodes.length, 0);
  assert.equal(parsed.coverage.scan_gaps[0], "source coverage incomplete");
  assert.equal(parsed.scan_ref.status, "partial");
});

test("edge line styles communicate frozen semantics without confidence inference", () => {
  const service = runtime().load("services/p1Graph.ts");
  assert.equal(service.edgeAppearance("PROJECT_HAS_RESOURCE"), "solid");
  assert.equal(service.edgeAppearance("RESOURCE_HAS_LICENSE_OBSERVATION"), "dashed");
  assert.equal(service.edgeAppearance("RESOURCE_HAS_FINDING"), "dashed");
  assert.equal(service.edgeAppearance("RESOURCE_SUPPORTED_BY_EVIDENCE"), "dotted");
  assert.equal(service.edgeAppearance("FINDING_SUPPORTED_BY_EVIDENCE"), "dotted");
});

for (const count of [100, 300, 500]) test(`${count}-node layout is complete, finite and interactive-budget friendly`, (context) => {
  const service = runtime().load("services/p1Graph.ts");
  const kinds = ["project", "component", "ai_asset", "license_observation", "evidence", "finding", "obligation"];
  const nodes = Array.from({ length: count }, (_, index) => ({ id: `n${index}`, kind: kinds[index % kinds.length], source_id: `s${index}`, label: `Node ${index}` }));
  const started = performance.now();
  const result = service.layoutResourceGraph(nodes);
  const elapsed = performance.now() - started;
  assert.equal(result.nodes.length, count);
  assert.ok(result.width > 0 && result.height > 0);
  assert.ok(result.nodes.every((node) => Number.isFinite(node.x) && Number.isFinite(node.y)));
  assert.equal(new Set(result.nodes.map((node) => `${node.x}:${node.y}`)).size, count);
  assert.ok(elapsed < 1000, `layout took ${elapsed.toFixed(1)}ms`);
  context.diagnostic(`pure layout: ${elapsed.toFixed(3)} ms`);
});

test("graph route restores scan id and URL filters", () => {
  const run = runtime();
  run.shared.window.location = { pathname: "/app/scans/scan%2Fid/graph", search: "?mode=api&graph_q=license&graph_kinds=evidence,finding&graph_zoom=1.25" };
  const route = run.load("hooks/useRoute.ts").readRoute();
  assert.equal(route.page, "graph");
  assert.equal(route.scanId, "scan/id");
  assert.equal(route.query.get("graph_q"), "license");
  assert.equal(route.query.get("graph_kinds"), "evidence,finding");
  assert.equal(route.query.get("graph_zoom"), "1.25");
});
