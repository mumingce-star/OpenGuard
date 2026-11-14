import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const node = (id, kind, label = id) => ({ id, kind, label, source_id: `original-${id}` });
const edge = (id, source, target, type) => ({ id, source, target, type, source_refs: [{ scan_id: 'scan', pointer: `/facts/${id}` }] });
function fixture() {
  return {
    nodes: [node('project', 'project'), node('a', 'component', 'Alpha@1'), node('b', 'component', 'Beta@2'), node('c', 'ai_asset', 'Model'), node('license', 'license_observation'), node('finding', 'finding'), node('a-evidence', 'evidence'), node('shared-evidence', 'evidence'), node('b-evidence', 'evidence'), node('obligation', 'obligation')],
    edges: [edge('pa', 'project', 'a', 'PROJECT_HAS_RESOURCE'), edge('pb', 'project', 'b', 'PROJECT_HAS_RESOURCE'), edge('pc', 'project', 'c', 'PROJECT_HAS_RESOURCE'), edge('al', 'a', 'license', 'RESOURCE_HAS_LICENSE_OBSERVATION'), edge('bl', 'b', 'license', 'RESOURCE_HAS_LICENSE_OBSERVATION'), edge('ae', 'a', 'a-evidence', 'RESOURCE_SUPPORTED_BY_EVIDENCE'), edge('be', 'b', 'b-evidence', 'RESOURCE_SUPPORTED_BY_EVIDENCE'), edge('af', 'a', 'finding', 'RESOURCE_HAS_FINDING'), edge('fe', 'finding', 'shared-evidence', 'FINDING_SUPPORTED_BY_EVIDENCE'), edge('fo', 'finding', 'obligation', 'FINDING_REFERENCES_OBLIGATION'), edge('lo', 'license', 'obligation', 'LICENSE_HAS_RULE_OBLIGATION')],
  };
}
const ids = rows => Array.from(rows, row => row.id).sort();

test('focused resource includes project and its recorded evidence/obligation closure without importing a neighbouring resource', () => {
  const service = runtime().load('services/p1Graph.ts');
  const view = fixture(), before = JSON.stringify(view);
  const actual = service.focusResourceGraph(view, 'a');
  assert.deepEqual(ids(actual.nodes), ['a', 'a-evidence', 'finding', 'license', 'obligation', 'project', 'shared-evidence']);
  assert.deepEqual(ids(actual.edges), ['ae', 'af', 'al', 'fe', 'fo', 'lo', 'pa']);
  assert.equal(JSON.stringify(view), before);
  for (const row of [...actual.nodes, ...actual.edges]) assert.ok([...view.nodes, ...view.edges].includes(row));
});

test('switching resource cannot retain evidence from the previous resource', () => {
  const service = runtime().load('services/p1Graph.ts');
  const actual = service.focusResourceGraph(fixture(), 'b');
  assert.deepEqual(ids(actual.nodes), ['b', 'b-evidence', 'license', 'obligation', 'project']);
  assert.ok(!actual.nodes.some(row => row.id === 'a-evidence' || row.id === 'shared-evidence'));
});

test('unknown or non-resource focus does not silently show a different resource', () => {
  const service = runtime().load('services/p1Graph.ts');
  for (const id of ['missing', 'license', 'project', '']) {
    const actual = service.focusResourceGraph(fixture(), id);
    assert.equal(actual.nodes.length, 0); assert.equal(actual.edges.length, 0);
  }
});

test('resource with only a project relation remains available, without invented evidence', () => {
  const service = runtime().load('services/p1Graph.ts');
  const actual = service.focusResourceGraph(fixture(), 'c');
  assert.deepEqual(ids(actual.nodes), ['c', 'project']);
  assert.deepEqual(ids(actual.edges), ['pc']);
});

test('resource choices search actual name and exact original identity, returning all resources', () => {
  const service = runtime().load('services/p1Graph.ts');
  assert.deepEqual(ids(service.resourceGraphChoices(fixture())), ['a', 'b', 'c']);
  assert.deepEqual(ids(service.resourceGraphChoices(fixture(), ' ALPHA ')), ['a']);
  assert.deepEqual(ids(service.resourceGraphChoices(fixture(), 'original-b')), ['b']);
  assert.equal(service.resourceGraphChoices(fixture(), 'missing').length, 0);
});

test('resource ranking and layout are deterministic when server node/edge order changes', () => {
  const service = runtime().load('services/p1Graph.ts');
  const a = fixture(), b = { nodes: [...a.nodes].reverse(), edges: [...a.edges].reverse() };
  assert.deepEqual(Array.from(service.resourceGraphChoices(a), row => row.id), Array.from(service.resourceGraphChoices(b), row => row.id));
  assert.equal(JSON.stringify(service.layoutResourceGraph(a.nodes)), JSON.stringify(service.layoutResourceGraph(b.nodes)));
});

test('focused layout gives every node a non-overlapping card inside its measured canvas', () => {
  const service = runtime().load('services/p1Graph.ts');
  const actual = service.layoutResourceGraph(service.focusResourceGraph(fixture(), 'a').nodes);
  const { width, height } = service.graphNodeSize;
  for (const n of actual.nodes) {
    assert.ok(n.x >= 0 && n.y >= 0 && n.x + width <= actual.width && n.y + height <= actual.height);
    for (const other of actual.nodes) if (n.id !== other.id) assert.ok(n.x + width <= other.x || other.x + width <= n.x || n.y + height <= other.y || other.y + height <= n.y);
  }
});

test('graph routes independently restore resource and node focus without changing scan context', () => {
  const r = runtime();
  r.shared.window.location = { pathname: '/app/scans/scan/graph', search: '?mode=api&graph_resource=a&graph_node=a-evidence&p2_result=old-result' };
  const route = r.load('hooks/useRoute.ts').readRoute();
  assert.equal(route.page, 'graph'); assert.equal(route.scanId, 'scan');
  assert.equal(route.query.get('graph_resource'), 'a'); assert.equal(route.query.get('graph_node'), 'a-evidence'); assert.equal(route.query.get('p2_result'), 'old-result');
});
