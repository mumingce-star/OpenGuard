import type { ScanStatus } from "../types/domain";
import type {
  HistoryAssessmentRef,
  HistoryPage,
  HistoryProjectIdentity,
  HistoryQuery,
  HistorySourceType,
  ScanHistoryItem,
} from "../types/p1History";
import { request } from "./scans";

const statuses: ScanStatus[] = [
  "queued",
  "running",
  "completed",
  "partial",
  "failed",
  "cancelled",
];
const sourceTypes: HistorySourceType[] = ["git", "zip", "local"];
const stages = [
  "queued",
  "ingestion",
  "inventory",
  "scan",
  "normalize",
  "rules",
  "ai_assist",
  "report",
  "completed",
] as const;
const hashPattern = /^[0-9a-f]{64}$/;

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail();
  return value as Record<string, unknown>;
}

function fail(): never {
  throw new Error("历史数据结构不符合 P1 History 契约。");
}

function exact(value: Record<string, unknown>, names: string[]) {
  const actual = Object.keys(value).sort();
  const expected = [...names].sort();
  if (actual.length !== expected.length || actual.some((name, i) => name !== expected[i])) fail();
}

function text(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function integer(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0;
}

function hash(value: unknown): value is string {
  return typeof value === "string" && hashPattern.test(value);
}

function utc(value: unknown): value is string {
  return typeof value === "string" && value.endsWith("Z") && Number.isFinite(Date.parse(value));
}

function status(value: unknown): value is ScanStatus {
  return typeof value === "string" && statuses.includes(value as ScanStatus);
}

function assessmentRef(value: unknown, scanId: string): HistoryAssessmentRef {
  const raw = object(value);
  exact(raw, ["assessment_id", "version", "scan_id", "facts_hash", "usage_hash", "rule_version", "formal"]);
  if (
    !text(raw.assessment_id) ||
    !Number.isInteger(raw.version) ||
    Number(raw.version) < 1 ||
    raw.scan_id !== scanId ||
    !hash(raw.facts_hash) ||
    !hash(raw.usage_hash) ||
    !text(raw.rule_version) ||
    raw.formal !== true
  ) fail();
  return raw as unknown as HistoryAssessmentRef;
}

function projectIdentity(value: unknown): HistoryProjectIdentity {
  const raw = object(value);
  exact(raw, ["method", "key", "source_project_id"]);
  if (
    !["canonical_github_repo_v1", "scan_only"].includes(String(raw.method)) ||
    !text(raw.key) ||
    !text(raw.source_project_id)
  ) fail();
  if (
    raw.method === "canonical_github_repo_v1" &&
    !/^github\.com\/[^/?#]+\/[^/?#]+$/.test(raw.key)
  ) fail();
  return raw as unknown as HistoryProjectIdentity;
}

function validateItem(value: unknown): ScanHistoryItem {
  const raw = object(value);
  exact(raw, [
    "schema_version", "scan_id", "project_identity", "source_type", "source",
    "revision", "input_hash", "inventory_hash", "status", "stage", "created_at",
    "finished_at", "component_count", "ai_asset_count", "finding_count", "summary",
    "latest_assessment", "provenance",
  ]);
  if (
    raw.schema_version !== "1.0" ||
    !text(raw.scan_id) ||
    !sourceTypes.includes(raw.source_type as HistorySourceType) ||
    !text(raw.source) ||
    !(raw.revision === null || text(raw.revision)) ||
    !hash(raw.input_hash) ||
    !(raw.inventory_hash === null || hash(raw.inventory_hash)) ||
    !status(raw.status) ||
    !stages.includes(raw.stage as (typeof stages)[number]) ||
    !utc(raw.created_at) ||
    !(raw.finished_at === null || utc(raw.finished_at)) ||
    !integer(raw.component_count) ||
    !integer(raw.ai_asset_count) ||
    !integer(raw.finding_count)
  ) fail();
  const scanId = raw.scan_id;
  projectIdentity(raw.project_identity);

  const summary = object(raw.summary);
  exact(summary, ["component_count", "ai_asset_count", "evidence_count", "finding_counts"]);
  const counts = object(summary.finding_counts);
  exact(counts, ["pass", "warning", "review_required", "unknown"]);
  if (
    !integer(summary.component_count) ||
    !integer(summary.ai_asset_count) ||
    !integer(summary.evidence_count) ||
    !integer(counts.pass) ||
    !integer(counts.warning) ||
    !integer(counts.review_required) ||
    !integer(counts.unknown) ||
    summary.component_count !== raw.component_count ||
    summary.ai_asset_count !== raw.ai_asset_count ||
    Number(counts.pass) + Number(counts.warning) + Number(counts.review_required) + Number(counts.unknown) !== raw.finding_count
  ) fail();

  if (raw.latest_assessment !== null) assessmentRef(raw.latest_assessment, scanId);
  const provenance = object(raw.provenance);
  exact(provenance, ["producer", "source_refs", "assessment_refs", "generated_at", "algorithm_version", "parameters_hash"]);
  const producer = object(provenance.producer);
  exact(producer, ["name", "version"]);
  if (
    !text(producer.name) ||
    !text(producer.version) ||
    !Array.isArray(provenance.source_refs) ||
    provenance.source_refs.length < 1 ||
    !Array.isArray(provenance.assessment_refs) ||
    !utc(provenance.generated_at) ||
    !text(provenance.algorithm_version) ||
    !hash(provenance.parameters_hash)
  ) fail();
  for (const value of provenance.source_refs) {
    const ref = object(value);
    exact(ref, ["scan_id", "revision", "facts_hash", "input_hash", "inventory_hash", "status", "registry_revision"]);
    if (
      ref.scan_id !== scanId ||
      !(ref.revision === null || text(ref.revision)) ||
      !hash(ref.facts_hash) ||
      !hash(ref.input_hash) ||
      !(ref.inventory_hash === null || hash(ref.inventory_hash)) ||
      !status(ref.status) ||
      !Number.isInteger(ref.registry_revision) ||
      Number(ref.registry_revision) < 1
    ) fail();
  }
  const refs = provenance.assessment_refs.map((ref) => assessmentRef(ref, scanId));
  if (raw.latest_assessment !== null && !refs.some((ref) => ref.assessment_id === object(raw.latest_assessment).assessment_id)) fail();
  return raw as unknown as ScanHistoryItem;
}

export function validateHistoryPage(value: unknown): HistoryPage {
  const raw = object(value);
  exact(raw, ["schema_version", "items", "next_cursor"]);
  if (
    raw.schema_version !== "1.0" ||
    !Array.isArray(raw.items) ||
    !(raw.next_cursor === null || text(raw.next_cursor))
  ) fail();
  const items = raw.items.map(validateItem);
  if (new Set(items.map((item) => item.scan_id)).size !== items.length) fail();
  return { schema_version: "1.0", items, next_cursor: raw.next_cursor as string | null };
}

export function historyQueryFromSearch(search: URLSearchParams): HistoryQuery {
  const rawLimit = search.get("limit") ?? "20";
  const limit = Number(rawLimit);
  const rawStatus = search.get("status");
  const rawSource = search.get("source_type");
  const cursor = search.get("cursor");
  if (!Number.isInteger(limit) || limit < 1 || limit > 100 || String(limit) !== rawLimit) {
    throw new Error("历史链接中的每页数量无效，请重置筛选条件。");
  }
  if (rawStatus && !statuses.includes(rawStatus as ScanStatus)) {
    throw new Error("历史链接中的扫描状态无效，请重置筛选条件。");
  }
  if (rawSource && !sourceTypes.includes(rawSource as HistorySourceType)) {
    throw new Error("历史链接中的来源类型无效，请重置筛选条件。");
  }
  if (cursor !== null && cursor.length === 0) {
    throw new Error("历史链接中的分页游标无效，请返回筛选首页。");
  }
  const q = search.get("q")?.trim() || undefined;
  const projectKey = search.get("project_key")?.trim() || undefined;
  return {
    limit,
    ...(cursor !== null ? { cursor } : {}),
    ...(rawStatus ? { status: rawStatus as ScanStatus } : {}),
    ...(rawSource ? { sourceType: rawSource as HistorySourceType } : {}),
    ...(q ? { q } : {}),
    ...(projectKey ? { projectKey } : {}),
  };
}

export function historySearch(query: HistoryQuery): URLSearchParams {
  const search = new URLSearchParams();
  search.set("limit", String(query.limit));
  if (query.status) search.set("status", query.status);
  if (query.sourceType) search.set("source_type", query.sourceType);
  if (query.q) search.set("q", query.q);
  if (query.projectKey) search.set("project_key", query.projectKey);
  if (query.cursor) search.set("cursor", query.cursor);
  return search;
}

export async function getHistory(query: HistoryQuery, signal?: AbortSignal): Promise<HistoryPage> {
  return validateHistoryPage(await request("/scans?" + historySearch(query), {}, signal));
}

export function historyTarget(item: ScanHistoryItem): {
  page: "assessment" | "overview" | "progress";
  assessmentId?: string;
} {
  if (["queued", "running", "failed", "cancelled"].includes(item.status)) return { page: "progress" };
  if (item.latest_assessment) return { page: "assessment", assessmentId: item.latest_assessment.assessment_id };
  return { page: "overview" };
}

export const historyStatuses = statuses;
export const historySourceTypes = sourceTypes;
