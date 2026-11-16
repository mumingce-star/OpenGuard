import { ApiError, request } from "./scans";
import type {
  ProfileEvidenceRef,
  ProfileMetadataObservation,
  ProfileVerification,
  ProfileRefreshJob,
  ProfileRefreshStatus,
  ResourceProfile,
} from "../types/p1ResourceProfile";

const profileStatuses: ProfileVerification[] = [
  "verified",
  "pending",
  "not_applicable",
  "rejected",
];
const scanStatuses = [
  "queued",
  "running",
  "completed",
  "partial",
  "failed",
  "cancelled",
];
const hash = /^[0-9a-f]{64}$/;

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("资源 Profile 不符合 P1 契约。");
  return value as Record<string, unknown>;
}
function text(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}
function nullableText(value: unknown): value is string | null {
  return value === null || text(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}
function status(value: unknown): value is ProfileVerification {
  return typeof value === "string" && profileStatuses.includes(value as ProfileVerification);
}
function exact(value: Record<string, unknown>, keys: string[]) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index]))
    throw new Error("资源 Profile 包含未声明字段或缺少必需字段。");
}
function evidenceRef(value: unknown): ProfileEvidenceRef {
  const ref = object(value);
  if (ref.namespace === "scan") {
    exact(ref, ["namespace", "scan_id", "evidence_id"]);
    if (!text(ref.scan_id) || !text(ref.evidence_id)) throw new Error("资源 Profile 的扫描证据引用无效。");
  } else if (ref.namespace === "profile_observation") {
    exact(ref, ["namespace", "observation_id"]);
    if (!text(ref.observation_id)) throw new Error("资源 Profile 的观测证据引用无效。");
  } else throw new Error("资源 Profile 的证据命名空间无效。");
  return ref as unknown as ProfileEvidenceRef;
}
function metadataObservation(value: unknown): ProfileMetadataObservation {
  const item = object(value);
  exact(item, [
    "observation_id", "provider", "resource_identity_key", "requested_revision",
    "resolved_revision", "source_url", "fetched_at", "content_hash", "parser_version",
    "bounded_excerpt", "fields", "verification_status", "coverage_gaps", "producer",
    "provenance", "full_response_replay_available",
  ]);
  if (!text(item.observation_id) || !text(item.provider) || !text(item.resource_identity_key) ||
      !nullableText(item.requested_revision) || !nullableText(item.resolved_revision) ||
      !text(item.source_url) || !item.source_url.startsWith("https://") ||
      !text(item.fetched_at) || !Number.isFinite(Date.parse(item.fetched_at)) || !item.fetched_at.endsWith("Z") ||
      !text(item.content_hash) || !hash.test(item.content_hash) || !text(item.parser_version) ||
      typeof item.bounded_excerpt !== "string" || item.bounded_excerpt.length > 1000 ||
      !status(item.verification_status) || !strings(item.coverage_gaps) ||
      item.full_response_replay_available !== false || !Array.isArray(item.fields))
    throw new Error("资源 Profile 的 metadata observation 无效。");
  for (const rawField of item.fields) {
    const field = object(rawField);
    exact(field, ["name", "value", "locator", "verification_status"]);
    if (!text(field.name) || !nullableText(field.value) || !text(field.locator) || !status(field.verification_status))
      throw new Error("资源 Profile 的 metadata 字段无效。");
  }
  object(item.producer);
  object(item.provenance);
  return item as unknown as ProfileMetadataObservation;
}

export function parseResourceProfile(raw: unknown, scanId: string, resourceId: string): ResourceProfile {
  const profile = object(raw);
  exact(profile, [
    "schema_version", "profile_id", "scan_ref", "resource_ref", "identity",
    "license_observations", "authorization_fact", "metadata_observations",
    "coverage_gaps", "evidence_refs", "provenance",
  ]);
  const scanRef = object(profile.scan_ref), resourceRef = object(profile.resource_ref), identity = object(profile.identity);
  exact(scanRef, ["scan_id", "revision", "facts_hash", "input_hash", "inventory_hash", "status", "registry_revision"]);
  exact(resourceRef, ["scan_id", "resource_kind", "resource_id", "resource_identity_key", "resource_instance_key"]);
  exact(identity, ["name", "version", "ecosystem", "provider", "source_url"]);
  if (profile.schema_version !== "1.0" || !text(profile.profile_id) || scanRef.scan_id !== scanId ||
      resourceRef.scan_id !== scanId || resourceRef.resource_id !== resourceId ||
      !["component", "ai_asset"].includes(String(resourceRef.resource_kind)) ||
      !nullableText(resourceRef.resource_identity_key) || !nullableText(resourceRef.resource_instance_key) ||
      !nullableText(scanRef.revision) || !text(scanRef.facts_hash) || !hash.test(scanRef.facts_hash) ||
      !text(scanRef.input_hash) || !hash.test(scanRef.input_hash) ||
      !(scanRef.inventory_hash === null || (text(scanRef.inventory_hash) && hash.test(scanRef.inventory_hash))) ||
      !scanStatuses.includes(String(scanRef.status)) || !Number.isInteger(scanRef.registry_revision) || Number(scanRef.registry_revision) < 1 ||
      !text(identity.name) || !nullableText(identity.version) || !nullableText(identity.ecosystem) ||
      !nullableText(identity.provider) || !nullableText(identity.source_url) || !strings(profile.coverage_gaps) ||
      !Array.isArray(profile.license_observations) || !Array.isArray(profile.metadata_observations) || !Array.isArray(profile.evidence_refs))
    throw new Error("资源 Profile 不符合 P1 契约或与当前扫描不匹配。");
  for (const rawLicense of profile.license_observations) {
    const license = object(rawLicense);
    exact(license, ["license_expression_id", "expression", "relation_scope", "evidence_refs", "verification_status"]);
    if (!text(license.license_expression_id) || !text(license.expression) || !text(license.relation_scope) ||
        !status(license.verification_status) || !Array.isArray(license.evidence_refs))
      throw new Error("资源 Profile 的许可观测无效。");
    license.evidence_refs.map(evidenceRef);
  }
  if (profile.authorization_fact !== null) {
    const authorization = object(profile.authorization_fact), source = object(authorization.source_ref);
    exact(authorization, ["status", "source_ref"]); exact(source, ["scan_id", "pointer"]);
    if (!status(authorization.status) || source.scan_id !== scanId || !text(source.pointer) || !source.pointer.startsWith("/"))
      throw new Error("资源 Profile 的授权事实无效。");
  }
  profile.metadata_observations.map(metadataObservation);
  profile.evidence_refs.map(evidenceRef);
  object(profile.provenance);
  return profile as unknown as ResourceProfile;
}

export async function getResourceProfile(scanId: string, resourceId: string, signal?: AbortSignal): Promise<ResourceProfile | null> {
  try {
    const raw = await request(`/scans/${encodeURIComponent(scanId)}/resources/${encodeURIComponent(resourceId)}/profile`, {}, signal);
    return parseResourceProfile(raw, scanId, resourceId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

const refreshStatuses: ProfileRefreshStatus[] = ["pending", "succeeded", "failed"];

export function parseProfileRefreshJob(raw: unknown, scanId: string, resourceIds?: string[]): ProfileRefreshJob {
  const job = object(raw);
  exact(job, [
    "schema_version", "job_id", "scan_id", "facts_hash", "resource_ids", "status",
    "items", "created_at", "completed_at", "algorithm_version",
  ]);
  if (job.schema_version !== "1.0" || !text(job.job_id) || job.scan_id !== scanId ||
      !text(job.facts_hash) || !hash.test(job.facts_hash) || !strings(job.resource_ids) ||
      !refreshStatuses.includes(job.status as ProfileRefreshStatus) || !Array.isArray(job.items) ||
      !text(job.created_at) || !Number.isFinite(Date.parse(job.created_at)) ||
      !(job.completed_at === null || (text(job.completed_at) && Number.isFinite(Date.parse(job.completed_at)))) ||
      !text(job.algorithm_version)) throw new Error("元数据刷新任务不符合 P1 契约。");
  const jobResourceIds = job.resource_ids as string[];
  if (new Set(jobResourceIds).size !== jobResourceIds.length ||
      (resourceIds && (jobResourceIds.length !== resourceIds.length || resourceIds.some(id => !jobResourceIds.includes(id)))))
    throw new Error("元数据刷新任务与请求资源不匹配。");
  for (const rawItem of job.items) {
    const item = object(rawItem);
    exact(item, ["resource_id", "status", "observation_id", "error_code"]);
    if (!text(item.resource_id) || !jobResourceIds.includes(item.resource_id) ||
        !refreshStatuses.includes(item.status as ProfileRefreshStatus) || !nullableText(item.observation_id) ||
        !nullableText(item.error_code)) throw new Error("元数据刷新明细不符合 P1 契约。");
  }
  if (job.items.length !== job.resource_ids.length || new Set(job.items.map(item => object(item).resource_id)).size !== job.items.length)
    throw new Error("元数据刷新明细不完整。" );
  return job as unknown as ProfileRefreshJob;
}

export async function refreshResourceProfile(
  scanId: string,
  resourceId: string,
  expectedFactsHash: string,
  idempotencyKey: string,
): Promise<ProfileRefreshJob> {
  if (!text(resourceId) || !hash.test(expectedFactsHash) || !idempotencyKey.trim())
    throw new Error("元数据刷新参数无效。");
  try {
    const raw = await request(`/scans/${encodeURIComponent(scanId)}/resource-profiles/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resource_ids: [resourceId], expected_facts_hash: expectedFactsHash, idempotency_key: idempotencyKey }),
    });
    return parseProfileRefreshJob(raw, scanId, [resourceId]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 503)
      throw new Error("真实元数据刷新尚未在当前后端启用，请后端开启 Profile Metadata 生产接线。");
    if (error instanceof ApiError && error.status === 409)
      throw new Error("扫描事实版本已变化，请刷新页面后重新读取 Resource Profile。");
    if (error instanceof ApiError && (error.status === 400 || error.status === 422))
      throw new Error("该资源不能进行可信元数据刷新，已保持原有未知或待核验状态。");
    throw error;
  }
}

export async function getProfileRefreshJob(scanId: string, jobId: string, signal?: AbortSignal): Promise<ProfileRefreshJob> {
  const raw = await request(`/scans/${encodeURIComponent(scanId)}/resource-profiles/jobs/${encodeURIComponent(jobId)}`, {}, signal);
  return parseProfileRefreshJob(raw, scanId);
}

export function resolvedProfileRevision(profile: ResourceProfile | null): { value: string | null; conflicted: boolean } {
  if (!profile) return { value: null, conflicted: false };
  const values = [...new Set(profile.metadata_observations.flatMap(item =>
    item.resolved_revision ? [item.resolved_revision] : []
  ))];
  return values.length === 1 ? { value: values[0], conflicted: false } : { value: null, conflicted: values.length > 1 };
}
