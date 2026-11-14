import test from "node:test";
import assert from "node:assert/strict";
import { runtime } from "./runtime.mjs";

const hash = (char) => char.repeat(64);
function item(index, overrides = {}) {
  const scanId = `scn_history_${String(index).padStart(3, "0")}`;
  const assessment = overrides.assessment
    ? {
        assessment_id: `asm_${index}`,
        version: 2,
        scan_id: scanId,
        facts_hash: hash("c"),
        usage_hash: hash("d"),
        rule_version: "rules/1",
        formal: true,
      }
    : null;
  return {
    schema_version: "1.0",
    scan_id: scanId,
    project_identity: {
      method: "canonical_github_repo_v1",
      key: `github.com/example/project-${index}`,
      source_project_id: `prj_${index}`,
    },
    source_type: "git",
    source: `https://github.com/example/project-${index}`,
    revision: `revision-${index}`,
    input_hash: hash("a"),
    inventory_hash: hash("b"),
    status: "completed",
    stage: "completed",
    created_at: "2026-09-15T12:00:00Z",
    finished_at: "2026-09-15T12:01:00Z",
    component_count: index,
    ai_asset_count: 1,
    finding_count: 3,
    summary: {
      component_count: index,
      ai_asset_count: 1,
      evidence_count: 4,
      finding_counts: { pass: 0, warning: 1, review_required: 1, unknown: 1 },
    },
    latest_assessment: assessment,
    provenance: {
      producer: { name: "openguard-history", version: "1.0" },
      source_refs: [
        {
          scan_id: scanId,
          revision: `revision-${index}`,
          facts_hash: hash("c"),
          input_hash: hash("a"),
          inventory_hash: hash("b"),
          status: "completed",
          registry_revision: 1,
        },
      ],
      assessment_refs: assessment ? [assessment] : [],
      generated_at: "2026-09-15T12:02:00Z",
      algorithm_version: "history/1.0",
      parameters_hash: hash("e"),
    },
    ...overrides,
  };
}

test("205 real-history DTOs traverse first, middle and final cursor pages without duplicates", async () => {
  const r = runtime(), service = r.load("services/p1History.ts"), calls = [];
  const all = Array.from({ length: 205 }, (_, index) => item(index + 1));
  r.setFetch(async (url, init) => {
    calls.push({ url, method: init.method ?? "GET" });
    const search = new URL(url, "http://local").searchParams;
    const cursor = search.get("cursor");
    const offset = cursor === "cursor-2" ? 200 : cursor === "cursor-1" ? 100 : 0;
    const rows = all.slice(offset, offset + 100);
    return Response.json({
      schema_version: "1.0",
      items: rows,
      next_cursor: offset === 0 ? "cursor-1" : offset === 100 ? "cursor-2" : null,
    });
  });
  const query = {
    limit: 100,
    status: "completed",
    sourceType: "git",
    q: "example",
    projectKey: "github.com/example/project-1",
  };
  const first = await service.getHistory(query);
  const middle = await service.getHistory({ ...query, cursor: first.next_cursor });
  const last = await service.getHistory({ ...query, cursor: middle.next_cursor });
  const ids = [...first.items, ...middle.items, ...last.items].map((row) => row.scan_id);
  assert.equal(ids.length, 205);
  assert.equal(new Set(ids).size, 205);
  assert.equal(first.items[0].scan_id, "scn_history_001");
  assert.equal(last.items.at(-1).scan_id, "scn_history_205");
  assert.equal(last.next_cursor, null);
  assert.ok(calls.every((call) => call.method === "GET"));
  assert.match(calls[0].url, /limit=100/);
  assert.match(calls[0].url, /status=completed/);
  assert.match(calls[0].url, /source_type=git/);
  assert.match(calls[1].url, /cursor=cursor-1/);
});

test("history query restores all URL filters and never reuses a cursor for a new filter set", () => {
  const service = runtime().load("services/p1History.ts");
  const restored = service.historyQueryFromSearch(
    new URLSearchParams("limit=50&status=partial&source_type=zip&q=%20demo%20&project_key=scan-key&cursor=opaque"),
  );
  assert.deepEqual(JSON.parse(JSON.stringify(restored)), {
    limit: 50,
    cursor: "opaque",
    status: "partial",
    sourceType: "zip",
    q: "demo",
    projectKey: "scan-key",
  });
  const changed = service.historySearch({ limit: 50, status: "completed", q: "next" });
  assert.equal(changed.get("cursor"), null);
  assert.equal(changed.get("status"), "completed");
  assert.equal(changed.get("q"), "next");
});

test("invalid URL filters stop before fetch and malformed history facts are rejected", async () => {
  const r = runtime(), service = r.load("services/p1History.ts");
  for (const query of ["limit=0", "limit=101", "limit=01", "status=success", "source_type=http", "cursor="]) {
    assert.throws(() => service.historyQueryFromSearch(new URLSearchParams(query)), /历史链接/);
  }
  const invalid = item(1);
  invalid.finding_count = 99;
  assert.throws(
    () => service.validateHistoryPage({ schema_version: "1.0", items: [invalid], next_cursor: null }),
    /History 契约/,
  );
  let calls = 0;
  r.setFetch(async () => {
    calls++;
    return new Response(JSON.stringify({ error: { code: "upstream_unavailable", message: "unavailable" } }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  });
  await assert.rejects(service.getHistory({ limit: 20 }), /503/);
  assert.equal(calls, 1);
  assert.equal(r.storage.size, 0);
});

test("empty results stay empty and do not synthesize scans or assessments", async () => {
  const r = runtime(), service = r.load("services/p1History.ts");
  r.setFetch(async () => Response.json({ schema_version: "1.0", items: [], next_cursor: null }));
  const page = await service.getHistory({ limit: 20, q: "absent" });
  assert.deepEqual(JSON.parse(JSON.stringify(page)), { schema_version: "1.0", items: [], next_cursor: null });
  assert.equal(r.storage.size, 0);
});

test("old scans open existing progress, overview or formal assessment routes without creation", () => {
  const service = runtime().load("services/p1History.ts");
  assert.deepEqual(JSON.parse(JSON.stringify(service.historyTarget(item(1, { status: "running", stage: "scan", finished_at: null })))), { page: "progress" });
  assert.deepEqual(JSON.parse(JSON.stringify(service.historyTarget(item(2, { status: "failed", stage: "scan" })))), { page: "progress" });
  assert.deepEqual(JSON.parse(JSON.stringify(service.historyTarget(item(3)))), { page: "overview" });
  assert.deepEqual(JSON.parse(JSON.stringify(service.historyTarget(item(4, { assessment: true })))), { page: "assessment", assessmentId: "asm_4" });
});

test("history route and copied URL restore filters while scan routes remain unchanged", () => {
  const r = runtime(), route = r.load("hooks/useRoute.ts");
  r.shared.window.location = {
    pathname: "/app/history",
    search: "?status=partial&source_type=git&q=demo&cursor=opaque&limit=50&mode=mock",
  };
  const parsed = route.readRoute();
  assert.equal(parsed.page, "history");
  assert.equal(parsed.scanId, "");
  assert.equal(parsed.mode, "api");
  assert.equal(parsed.query.get("cursor"), "opaque");
  const copied = route.historyPath(parsed.query);
  assert.match(copied, /^\/app\/history\?/);
  assert.doesNotMatch(copied, /mode=/);
  assert.match(copied, /cursor=opaque/);
  assert.equal(route.scanPath("old/id", "overview", "api"), "/app/scans/old%2Fid/overview?mode=api");
});
