import test from "node:test";
import assert from "node:assert/strict";
import { runtime } from "./runtime.mjs";

const digest = "a".repeat(64);
const validProfile = () => ({
  schema_version: "1.0",
  profile_id: "rpf_real_model",
  scan_ref: {
    scan_id: "scan-real",
    revision: "git-revision",
    facts_hash: digest,
    input_hash: digest,
    inventory_hash: digest,
    status: "completed",
    registry_revision: 3,
  },
  resource_ref: {
    scan_id: "scan-real",
    resource_kind: "ai_asset",
    resource_id: "ast_" + "long-".repeat(30),
    resource_identity_key: "model:huggingface:org/model",
    resource_instance_key: "model:huggingface:org/model@rev-1",
  },
  identity: {
    name: "org/model",
    version: "v1",
    ecosystem: null,
    provider: "huggingface",
    source_url: "https://huggingface.co/org/model",
  },
  license_observations: [{
    license_expression_id: "lic_real",
    expression: "Apache-2.0",
    relation_scope: "resource",
    evidence_refs: [{ namespace: "scan", scan_id: "scan-real", evidence_id: "evd_real" }],
    verification_status: "verified",
  }],
  authorization_fact: {
    status: "pending",
    source_ref: { scan_id: "scan-real", pointer: "/ai_assets/0/authorization_status" },
  },
  metadata_observations: [{
    observation_id: "obs_real",
    provider: "huggingface",
    resource_identity_key: "model:huggingface:org/model",
    requested_revision: "main",
    resolved_revision: "rev-1",
    source_url: "https://huggingface.co/org/model",
    fetched_at: "2026-09-16T00:00:00Z",
    content_hash: digest,
    parser_version: "profile/1.0",
    bounded_excerpt: "Model card metadata",
    fields: [{ name: "license", value: "apache-2.0", locator: "/cardData/license", verification_status: "pending" }],
    verification_status: "pending",
    coverage_gaps: ["dataset relation unavailable"],
    producer: { name: "fixture", version: "1.0" },
    provenance: {},
    full_response_replay_available: false,
  }],
  coverage_gaps: ["dataset relation unavailable"],
  evidence_refs: [{ namespace: "scan", scan_id: "scan-real", evidence_id: "evd_real" }],
  provenance: {},
});

test("ResourceProfile parser preserves verified, pending, revision and long IDs", () => {
  const service = runtime().load("services/p1ResourceProfiles.ts");
  const raw = validProfile();
  const parsed = service.parseResourceProfile(raw, "scan-real", raw.resource_ref.resource_id);
  assert.equal(parsed.resource_ref.resource_id, raw.resource_ref.resource_id);
  assert.equal(parsed.license_observations[0].verification_status, "verified");
  assert.equal(parsed.authorization_fact.status, "pending");
  assert.equal(JSON.stringify(service.resolvedProfileRevision(parsed)), JSON.stringify({ value: "rev-1", conflicted: false }));
  const requestedOnly = validProfile();
  requestedOnly.metadata_observations[0].resolved_revision = null;
  const parsedRequestedOnly = service.parseResourceProfile(requestedOnly, "scan-real", requestedOnly.resource_ref.resource_id);
  assert.equal(service.resolvedProfileRevision(parsedRequestedOnly).value, null);
});

test("malformed, unknown-status, extra-field and cross-scan profiles fail closed", () => {
  const service = runtime().load("services/p1ResourceProfiles.ts");
  for (const mutate of [
    profile => { profile.schema_version = "2.0"; },
    profile => { profile.scan_ref.scan_id = "other"; },
    profile => { profile.authorization_fact.status = "unknown"; },
    profile => { profile.metadata_observations[0].unexpected = true; },
    profile => { profile.metadata_observations[0].source_url = "http://example.test"; },
  ]) {
    const profile = validProfile(); mutate(profile);
    assert.throws(() => service.parseResourceProfile(profile, "scan-real", validProfile().resource_ref.resource_id), /Profile|核验|metadata/);
  }
});

test("card facts use only Resource, Profile and Evidence fields", () => {
  const r = runtime(), service = r.load("services/p1ResourceProfiles.ts"), presentation = r.load("services/resourceCardPresentation.ts");
  const raw = validProfile(), profile = service.parseResourceProfile(raw, "scan-real", raw.resource_ref.resource_id);
  const resource = {
    id: raw.resource_ref.resource_id,
    name: "org/model",
    type: "Model",
    version: null,
    origin: raw.identity.source_url,
    license: null,
    licenseStatus: "unknown",
    evidenceIds: ["evd_real", "evd_missing"],
    provider: null,
    authorizationStatus: "unknown",
    licenseVerification: "unknown",
  };
  const evidence = [{ id: "evd_real", kind: "code", label: "src/model.py", source: "static_pattern", path: "src/model.py", text: "org/model", verificationStatus: "pending" }];
  const facts = presentation.resourceCardFacts(resource, profile, evidence);
  assert.equal(facts.provider, "huggingface");
  assert.equal(facts.version, "v1");
  assert.equal(facts.revision, "rev-1");
  assert.equal(facts.license, "Apache-2.0");
  assert.equal(facts.licenseConflicted, false);
  assert.equal(facts.licenseVerification, "verified");
  assert.equal(facts.authorization, "pending");
  assert.equal(facts.association, null);
  assert.deepEqual(facts.missingEvidenceIds, ["evd_missing"]);
  assert.ok(facts.missing.includes("模型与数据集关联未获取"));
  assert.equal(JSON.stringify(presentation.evidenceSources(evidence)), JSON.stringify(["static_pattern"]));
});

test("conflicting Profile license observations do not select an arbitrary license", () => {
  const r = runtime(), parser = r.load("services/p1ResourceProfiles.ts"), presentation = r.load("services/resourceCardPresentation.ts");
  const raw = validProfile();
  raw.license_observations.push({ ...raw.license_observations[0], expression: "MIT" });
  const profile = parser.parseResourceProfile(raw, "scan-real", raw.resource_ref.resource_id);
  const resource = {
    id: raw.resource_ref.resource_id, name: "org/model", type: "Model", version: null,
    origin: null, license: "NOASSERTION", licenseStatus: "pending", evidenceIds: [],
    provider: "huggingface", authorizationStatus: "pending", licenseVerification: "pending",
  };
  const facts = presentation.resourceCardFacts(resource, profile, []);
  assert.equal(facts.license, null);
  assert.equal(facts.licenseVerification, "unknown");
  assert.equal(facts.licenseConflicted, true);
  assert.ok(facts.missing.includes("许可观测冲突，证据不足"));
});

test("no Profile never invents provider, revision, license, authorization or association", () => {
  const presentation = runtime().load("services/resourceCardPresentation.ts");
  const facts = presentation.resourceCardFacts({
    id: "ast_unknown", name: "unknown", type: "Dataset", version: null,
    origin: "https://huggingface.co/datasets/org/data", license: null,
    licenseStatus: "unknown", evidenceIds: [], provider: null,
    authorizationStatus: "unknown", licenseVerification: "unknown",
  }, null, []);
  assert.equal(facts.provider, null);
  assert.equal(facts.revision, null);
  assert.equal(facts.license, null);
  assert.equal(facts.authorization, "unknown");
  assert.equal(facts.association, null);
  assert.ok(facts.missing.includes("Resource Profile 未提供"));
  assert.ok(facts.missing.includes("Profile 身份键未获取"));
  assert.ok(facts.missing.includes("Profile 实例键未获取"));
  assert.ok(facts.missing.includes("Evidence 证据不足"));
});

test("the three verification states retain distinct user-facing labels", () => {
  const { factVerificationLabels } = runtime().load("types/domain.ts");
  assert.equal(factVerificationLabels.unknown, "未知");
  assert.equal(factVerificationLabels.pending, "待核验");
  assert.equal(factVerificationLabels.verified, "已核验");
});

test("Profile GET is read-only, 404 is explicit absence, and 503 never returns mock data", async () => {
  const r = runtime(), service = r.load("services/p1ResourceProfiles.ts"), calls = [];
  r.setFetch(async (url, options) => {
    calls.push({ url, options });
    return Response.json({ error: { code: "not_found", message: "Missing", details: { reason: "not_found" } } }, { status: 404 });
  });
  assert.equal(await service.getResourceProfile("scan-real", "ast_real"), null);
  assert.equal(calls[0].url, "/api/v1/scans/scan-real/resources/ast_real/profile");
  assert.equal(calls[0].options.method, undefined);
  r.setFetch(async () => Response.json({ error: { code: "upstream_unavailable", message: "Unavailable" } }, { status: 503 }));
  await assert.rejects(service.getResourceProfile("scan-real", "ast_real"), /503/);
});

test("explicit Profile refresh binds facts and resource, validates the job, and stores nothing locally", async () => {
  const r = runtime({ VITE_API_BASE_URL: "/api/v1" }), service = r.load("services/p1ResourceProfiles.ts"), calls = [];
  const job = {
    schema_version: "1.0", job_id: "prj_1", scan_id: "scan-real", facts_hash: digest,
    resource_ids: ["ast_real"], status: "succeeded",
    items: [{ resource_id: "ast_real", status: "succeeded", observation_id: "obs_real", error_code: null }],
    created_at: "2026-09-23T00:00:00Z", completed_at: "2026-09-23T00:00:01Z",
    algorithm_version: "profile-refresh/1",
  };
  r.setFetch(async (url, options) => { calls.push({ url, options }); return Response.json(job); });
  const result = await service.refreshResourceProfile("scan-real", "ast_real", digest, "refresh-key");
  assert.equal(result.items[0].observation_id, "obs_real");
  assert.equal(calls[0].url, "/api/v1/scans/scan-real/resource-profiles/refresh");
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].options.body), { resource_ids: ["ast_real"], expected_facts_hash: digest, idempotency_key: "refresh-key" });
  assert.equal(r.storage.size, 0);
  assert.throws(() => service.parseProfileRefreshJob({ ...job, items: [] }, "scan-real", ["ast_real"]), /不完整/);
});

test("Profile refresh 503 and conflict remain explicit backend states", async () => {
  const r = runtime(), service = r.load("services/p1ResourceProfiles.ts");
  r.setFetch(async () => Response.json({ error: { code: "feature_disabled", details: { reason: "feature_disabled" } } }, { status: 503 }));
  await assert.rejects(service.refreshResourceProfile("scan-real", "ast_real", digest, "key"), /尚未在当前后端启用/);
  r.setFetch(async () => Response.json({ error: { code: "conflict", details: { reason: "conflict" } } }, { status: 409 }));
  await assert.rejects(service.refreshResourceProfile("scan-real", "ast_real", digest, "key"), /事实版本已变化/);
});

test("real DTO adapter preserves provider and exact evidence/license/authorization statuses", () => {
  const scans = runtime().load("services/scans.ts");
  const raw = validProfile(), id = raw.resource_ref.resource_id;
  const resources = { items: [{ kind: "ai_asset", resource: {
    id, asset_type: "model", name: "org/model", provider: "huggingface", version: null,
    source_url: "https://huggingface.co/org/model", license_expression_id: "lic_real",
    authorization_status: "pending", evidence_ids: ["evd_real"], detected_by: ["static_pattern"], confidence: 0.8,
  }}], total: 1 };
  const evidence = [{ id: "evd_real", kind: "url", locator: "https://huggingface.co/org/model", excerpt: "org/model", detected_by: "static_pattern", verification_status: "pending" }];
  const state = { scan_id: "scan-real", status: "completed", stage: "completed", progress: 100, errors: [] };
  const run = { id: "scan-real", status: "completed", project: { name: "real", source: "real" }, contract_version: "0.1.1", licenses: [{ id: "lic_real", expression: "NOASSERTION", verification_status: "pending" }], remediations: [] };
  const scan = scans.adaptApiScan("scan-real", state, resources, { items: [], total: 0 }, evidence, run);
  assert.equal(scan.resources[0].provider, "huggingface");
  assert.equal(scan.resources[0].authorizationStatus, "pending");
  assert.equal(scan.resources[0].licenseVerification, "pending");
  assert.equal(scan.resources[0].license, "NOASSERTION");
  assert.equal(scan.evidence[0].verificationStatus, "pending");
});
