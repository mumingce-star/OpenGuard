import test from "node:test";
import assert from "node:assert/strict";
import { runtime } from "./runtime.mjs";
const rt = runtime(),
  model = rt.load("services/model.ts"),
  { createSnapshot } = rt.load("mocks/data.ts");
const fixture = () => createSnapshot("DEMO-test", "standard");
test("snapshot metrics are derived from the full snapshot", () => {
  assert.equal(
    JSON.stringify(model.summarize(fixture())),
    JSON.stringify({ resources: 7, risks: 4, pending: 3, high: 2, unknown: 7 }),
  );
  const subset = model.filterRisks(
    fixture(),
    new URLSearchParams("severity=high&handling=open&type=Package"),
  );
  assert.equal(subset.length, 1);
  assert.equal(subset[0].id, "RISK-001");
  assert.equal(model.summarize(fixture()).risks, 4);
});
test("resource combined search and filters", () => {
  assert.equal(
    model.filterResources(
      fixture(),
      new URLSearchParams("type=Model&unknown=1&risk=high&q=demo"),
    ).length,
    1,
  );
  assert.equal(
    model.filterResources(fixture(), new URLSearchParams("q=nonexistent"))
      .length,
    0,
  );
});
test("zero risk, zero resource and missing evidence are real empty states", () => {
  assert.equal(createSnapshot("a", "clean").risks.length, 0);
  assert.equal(createSnapshot("a", "empty").resources.length, 0);
  const missing = createSnapshot("a", "missing");
  assert.equal(missing.evidence.length, 0);
  assert.equal(missing.risks[0].ai.status, "failed");
  assert.notEqual(
    fixture().risks[0].evidenceIds.join(),
    fixture().risks[1].evidenceIds.join(),
  );
});
test("GitHub format rejects credentials, queries, spoofed domains and non-repositories", () => {
  assert.equal(
    model.validateGithub(" https://github.com/mumingce-star/OpenGuard "),
    null,
  );
  for (const value of [
    "",
    "https://github.com/owner",
    "http://github.com/a/b",
    "https://github.com.evil.test/a/b",
    "https://user:secret@github.com/a/b",
    "https://github.com/a/b?token=secret",
    "javascript:alert(1)",
  ])
    assert.ok(model.validateGithub(value));
});
test("ZIP size is configured, extension and empty files rejected", () => {
  assert.ok(model.validateZip(null, null));
  assert.ok(model.validateZip({ name: "a.txt", size: 5 }, null));
  assert.ok(model.validateZip({ name: "a.zip", size: 0 }, null));
  assert.ok(model.validateZip({ name: "a.zip", size: 11 }, 10));
  assert.equal(model.validateZip({ name: "A.ZIP", size: 10 }, 10), null);
});
test("untrusted links and CSV formulas are neutralized", () => {
  assert.equal(model.safeUrl("javascript:alert(1)"), null);
  assert.equal(model.safeUrl("https://u:p@example.com"), null);
  assert.equal(model.safeUrl("https://example.com"), "https://example.com/");
  assert.equal(model.csvCell("=1+1"), '"\'=1+1"');
  assert.equal(model.csvCell('a"b'), '"a""b"');
});
test("exports contain snapshot identity and exact requested resource scope", () => {
  const scan = fixture(),
    report = model.reportPayload(scan);
  assert.equal(report.id, scan.id);
  assert.equal(report.mode, "mock");
  assert.equal(report.summary.risks, scan.risks.length);
  const csv = model.resourceCsv(scan, [scan.resources[0]]);
  assert.equal(csv.split("\r\n").length, 2);
  assert.ok(csv.includes("transformers"));
  assert.ok(!csv.includes("DemoResearch"));
});
test("snapshot contract rejects mismatched IDs, pagination, bad statuses and associations", () => {
  const { validateSnapshot } = rt.load("services/scans.ts");
  validateSnapshot(fixture(), "mock");
  for (const mutate of [
    (s) => (s.id = "wrong"),
    (s) => (s.completeness = "page"),
    (s) => (s.status = "success"),
    (s) => (s.risks[0].resourceId = "absent"),
    (s) => (s.resources[0].type = null),
    (s) => (s.evidence[0].startLine = -1),
    (s) => s.risks.push(s.risks[0]),
  ]) {
    const scan = fixture();
    mutate(scan);
    assert.throws(() => validateSnapshot(scan, "mock", "DEMO-test"), /契约/);
  }
  validateSnapshot(createSnapshot("m", "missing"), "mock", "m");
});
test("demo persists ID, stage state, handling without claiming verification", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts"),
    scan = s.createDemo();
  assert.equal((await s.getScan(scan.id, "mock")).status, "queued");
  s.skipDemo(scan.id);
  const completed = await s.getScan(scan.id, "mock");
  assert.equal(completed.status, "completed");
  await s.updateHandling(scan.id, "RISK-001", "resolved", "mock");
  const changed = await s.getScan(scan.id, "mock");
  assert.equal(changed.risks[0].handling, "resolved");
  assert.equal(changed.risks[0].verification, "unverified");
  s.restartDemo(scan.id);
  assert.equal((await s.getScan(scan.id, "mock")).id, scan.id);
  assert.equal((await s.getScan(scan.id, "mock")).status, "queued");
});
test("failed and partial demos do not claim all stages succeeded", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts");
  for (const scenario of ["failed", "partial"]) {
    const scan = s.createDemo(scenario);
    s.skipDemo(scan.id);
    const result = await s.getScan(scan.id, "mock");
    assert.equal(result.status, scenario);
    assert.ok(result.stageIndex < result.stages.length);
    assert.ok(result.error);
  }
  await assert.rejects(s.getScan("missing", "mock"), /未找到/);
});
test("corrupt local snapshot gives a recoverable error", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts");
  r.storage.set("openguard:scan:v2:x", "not json");
  await assert.rejects(s.getScan("x", "mock"), /无法读取/);
});
test("API failures never return mock data", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts");
  await assert.rejects(s.getScan("real", "api"), /不会自动切换演示/);
  r.setFetch(async () => new Response("{}", { status: 404 }));
  await assert.rejects(s.getScan("real", "api"), /404/);
  r.setFetch(async () => Response.json({ id: "real" }));
  await assert.rejects(s.getScan("real", "api"), /契约/);
  assert.equal(r.storage.size, 0);
});
test("API create uses Idempotency-Key and refresh only GETs same ID", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts"),
    calls = [];
  const response = { ...fixture(), id: "REAL-1", mode: "api" };
  r.setFetch(async (url, options) => {
    calls.push({ url, ...options });
    return Response.json(response);
  });
  const result = await s.createApiScan(
    { kind: "github", url: "https://github.com/a/b", scopes: ["LICENSE"] },
    "request-1",
  );
  await s.getScan(result.id, "api");
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].headers["Idempotency-Key"], "request-1");
  assert.equal(calls[1].method, undefined);
  assert.ok(calls[1].url.endsWith("/scans/REAL-1"));
});
test("repository accessibility is confirmed only by explicit backend true", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts");
  r.setFetch(async () => Response.json({ accessible: false }));
  await assert.rejects(
    s.validateRepository("https://github.com/a/b"),
    /未确认/,
  );
  r.setFetch(async () => Response.json({ accessible: true }));
  await s.validateRepository("https://github.com/a/b");
});
test("PATCH accepts 204 and absent ZIP limit prevents real upload", async () => {
  const r = runtime(),
    s = r.load("services/scans.ts");
  r.setFetch(async () => new Response(null, { status: 204 }));
  await s.updateHandling("REAL-1", "RISK-1", "reviewing", "api");
  await assert.rejects(
    s.createApiScan(
      { kind: "zip", file: { name: "test.zip", size: 10 }, scopes: [] },
      "x",
    ),
    /尚未配置/,
  );
});
test("route IDs, filters and invalid paths are handled explicitly", () => {
  const r = runtime(),
    route = r.load("hooks/useRoute.ts");
  r.shared.window.location = {
    pathname: "/app/scans/DEMO-test/risks/RISK-002",
    search: "?mode=mock&severity=high",
  };
  let parsed = route.readRoute();
  assert.equal(parsed.riskId, "RISK-002");
  assert.equal(parsed.query.get("severity"), "high");
  r.shared.window.location = { pathname: "/app/scans/x/nonsense", search: "" };
  assert.equal(route.readRoute().page, "not-found");
  r.shared.window.location = { pathname: "/app/overview", search: "" };
  assert.equal(route.readRoute().page, "new-scan");
});
