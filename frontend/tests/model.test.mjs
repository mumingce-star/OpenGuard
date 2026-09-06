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
const state = (status = "completed") => ({ scan_id: "real", status, stage: status === "completed" ? "completed" : "rules", progress: status === "completed" ? 100 : 70, errors: [] });
const resources = { items: [{ kind: "component", resource: { id: "cmp_a", name: "demo", version: "1.0.0", purl: "pkg:npm/demo@1.0.0", license_expression_id: "lic_a", evidence_ids: ["evd_a"] } }], total: 1 };
const risks = { items: [{ id: "rsk_a", title: "License declaration requires review", resource_id: "cmp_a", severity: "info", outcome: "review_required", evidence_ids: ["evd_a"], trigger: "license=MIT", description: "Declaration is not verified authorization", remediation_id: "rem_a" }], total: 1 };
const evidence = [{ id: "evd_a", kind: "manifest_field", locator: "package-lock.json#/packages/demo/license", excerpt: "MIT", detected_by: "manifest_parser" }];
const run = { id: "real", status: "completed", project: { name: "demo.zip", source: "demo.zip" }, created_at: "2026-09-05T01:00:00Z", finished_at: "2026-09-05T01:00:02Z", contract_version: "0.1.1", licenses: [{ id: "lic_a", expression: "MIT", verification_status: "pending" }], evidence, remediations: [{ id: "rem_a", finding_id: "rsk_a", summary: "Review license", steps: ["Check source"], generated_by: { type: "rule_engine" } }] };
test("real DTO adapter preserves pending, info, evidence and actual times", () => {
  const s = runtime().load("services/scans.ts");
  const scan = s.adaptApiScan("real", state(), resources, risks, evidence, run, ["json"]);
  assert.equal(scan.resources[0].license, "MIT");
  assert.equal(scan.resources[0].licenseStatus, "review_required");
  assert.equal(scan.risks[0].severity, "info");
  assert.equal(scan.risks[0].outcome, "review_required");
  assert.equal(scan.risks[0].verification, "unverified");
  assert.equal(scan.risks[0].ai.status, "unavailable");
  assert.equal(scan.evidence[0].kind, "code");
  assert.equal(scan.evidence[0].text, "MIT");
  assert.equal(scan.createdAt, run.created_at);
  assert.equal(model.summarize(scan).high, 0);
  assert.throws(() => s.adaptApiScan("other", state(), resources, risks, evidence), /契约/);
  assert.throws(() => s.adaptApiScan("real", state(), { ...resources, total: 2 }, risks, evidence), /不完整/);
});
test("unavailable report does not invent licenses or timestamps; cancelled remains terminal", () => {
  const s = runtime().load("services/scans.ts");
  const scan = s.adaptApiScan("real", state("cancelled"), resources, risks, evidence);
  assert.equal(scan.status, "cancelled");
  assert.equal(scan.createdAt, null);
  assert.equal(scan.resources[0].license, null);
  assert.equal(scan.resources[0].licenseStatus, "unknown");
});
test("API create uses frozen JSON and multipart body fields, not header or scopes", async () => {
  const r = runtime(), s = r.load("services/scans.ts"), calls = [];
  r.setFetch(async (url, options) => { calls.push({ url, ...options }); return Response.json({ scan_id: "real", status: "queued", status_url: "/api/v1/scans/real" }, { status: 202 }); });
  assert.equal(s.defaultMode, "api");
  assert.equal((await s.createApiScan({ kind: "github", url: "https://github.com/a/b" }, "request-1")).id, "real");
  assert.deepEqual(JSON.parse(calls[0].body), { source_type: "git", source: "https://github.com/a/b", idempotency_key: "request-1" });
  assert.equal(calls[0].headers["Idempotency-Key"], undefined);
  await s.createApiScan({ kind: "zip", file: new File(["zip"], "demo.zip") }, "request-2");
  const form = calls[1].body;
  assert.equal(form.get("source_type"), "zip");
  assert.equal(form.get("idempotency_key"), "request-2");
  assert.equal(form.get("file").name, "demo.zip");
  assert.equal(form.get("scopes"), null);
});
test("read-only API rejects handling changes without any request", async () => {
  const r = runtime(), s = r.load("services/scans.ts");
  let calls = 0; r.setFetch(async () => { calls++; return Response.json({}); });
  await assert.rejects(s.updateHandling("real", "rsk_a", "resolved", "api"), /只读/);
  assert.equal(calls, 0);
});
test("real scan composes frozen endpoints, ignores malicious report href, and never POSTs on refresh", async () => {
  const r = runtime(), s = r.load("services/scans.ts"), calls = [];
  r.setFetch(async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/resources")) return Response.json(resources);
    if (url.endsWith("/risks")) return Response.json(risks);
    if (url.includes("/evidence/")) return Response.json(evidence[0]);
    if (url.includes("download=true")) return Response.json({ scan_run: run });
    if (url.includes("/report?")) return Response.json({ format: new URL(url, "http://localhost").searchParams.get("format"), href: "https://evil.test/private" });
    return Response.json(state());
  });
  const scan = await s.getScan("real", "api");
  assert.equal(scan.resources[0].license, "MIT");
  assert.equal(scan.reportFormats.length, 4);
  assert.ok(calls.every(c => c.url.startsWith("/api/v1/scans/real") && !c.options.method));
  assert.equal(s.reportDownloadUrl("real", "html"), "/api/v1/scans/real/report?format=html&download=true");
  assert.throws(() => s.reportDownloadUrl("real", "invalid"));
});
test("queued/running/failed/cancelled only read status; terminal then reads results", async () => {
  const r = runtime(), s = r.load("services/scans.ts");
  for (const status of ["queued", "running", "failed", "cancelled"]) {
    const calls=[];
    r.setFetch(async url => { calls.push(url); assert.equal(url,"/api/v1/scans/real"); return Response.json(state(status)); });
    const scan=await s.getScan("real","api");
    assert.equal(scan.status,status); assert.equal(scan.resultsReady,false); assert.equal(calls.length,1);
    assert.equal(scan.resources.length,0); assert.equal(scan.createdAt,null);
  }
});
test("partial without generated reports retains facts; storage errors are not hidden", async () => {
  const r = runtime(), s = r.load("services/scans.ts");
  let responseStatus=409, code="report_not_ready", reason="not_generated";
  r.setFetch(async url => {
    if (url.endsWith("/resources")) return Response.json(resources);
    if (url.endsWith("/risks")) return Response.json(risks);
    if (url.includes("/evidence/")) return Response.json(evidence[0]);
    if (url.includes("/report?")) return Response.json({error:{code,message:"No report",details:{reason}}},{status:responseStatus});
    return Response.json(state("partial"));
  });
  const scan=await s.getScan("real","api");
  assert.equal(scan.resultsReady,true); assert.equal(scan.resources.length,1); assert.equal(scan.reportFormats.length,0); assert.equal(scan.createdAt,null);
  responseStatus=500; code="internal_error"; reason="report_storage_failure";
  await assert.rejects(s.getScan("real","api"),/500/);
  responseStatus=404; code="scan_not_found"; reason="not_found";
  await assert.rejects(s.getScan("real","api"),/404/);
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
