import { ApiError, request } from "./scans";

type Row = Record<string, unknown>;
const row = (value: unknown): value is Row => !!value && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string" && value.length > 0;
const hash = (value: unknown): value is string => text(value) && /^[0-9a-f]{64}$/.test(value);

export type NoticeRef = { draft_id: string; content_hash: string };
export type NoticeEntry = {
  entry_id: string;
  resource_ids: string[];
  license_expression_ids: string[];
  obligation_refs: { namespace: "scan" | "assessment"; source_id: string; obligation_id: string }[];
  evidence_refs: unknown[];
  text: string | null;
  missing: string[];
};
export type NoticeDraft = {
  schema_version: "1.0";
  draft_id: string;
  binding: { scan_ref: { scan_id: string }; assessment_ref: { assessment_id: string; version: number } };
  created_at: string;
  generator_version: string;
  entries: NoticeEntry[];
  coverage_gaps: string[];
  content_hash: string;
  provenance: Row;
};

const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(text);

export function parseNoticeDraft(value: unknown, scanId: string, assessmentId: string): NoticeDraft {
  const invalid = () => { throw new Error("NOTICE 草稿不符合冻结契约，未作为正式快照引用。"); };
  if (!row(value) || value.schema_version !== "1.0" || !text(value.draft_id) || !row(value.binding) ||
      !row(value.binding.scan_ref) || !row(value.binding.assessment_ref) ||
      value.binding.scan_ref.scan_id !== scanId || value.binding.assessment_ref.assessment_id !== assessmentId ||
      !Number.isInteger(value.binding.assessment_ref.version) || !text(value.created_at) || !Number.isFinite(Date.parse(value.created_at)) ||
      !text(value.generator_version) || !Array.isArray(value.entries) || !strings(value.coverage_gaps) ||
      !hash(value.content_hash) || !row(value.provenance)) return invalid();
  const ids = new Set<string>();
  for (const rawEntry of value.entries) {
    if (!row(rawEntry) || !text(rawEntry.entry_id) || ids.has(rawEntry.entry_id) || !strings(rawEntry.resource_ids) ||
        !strings(rawEntry.license_expression_ids) || !Array.isArray(rawEntry.obligation_refs) ||
        !Array.isArray(rawEntry.evidence_refs) || !(rawEntry.text === null || text(rawEntry.text)) || !strings(rawEntry.missing)) return invalid();
    ids.add(rawEntry.entry_id);
    for (const rawRef of rawEntry.obligation_refs) {
      if (!row(rawRef) || !["scan", "assessment"].includes(String(rawRef.namespace)) ||
          !text(rawRef.source_id) || !text(rawRef.obligation_id)) return invalid();
    }
  }
  return value as unknown as NoticeDraft;
}

export async function createNoticeDraft(scanId: string, assessmentId: string, idempotencyKey: string): Promise<NoticeDraft> {
  if (!idempotencyKey.trim()) throw new Error("NOTICE 草稿创建参数无效。");
  try {
    const raw = await request(`/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/notice-drafts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    });
    return parseNoticeDraft(raw, scanId, assessmentId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 503)
      throw new Error("NOTICE 草稿生产服务尚未接线；后端需要注入 NoticeDraftService 与真实 NoticeFactsReader。");
    if (error instanceof ApiError && error.status === 409)
      throw new Error("NOTICE 草稿来源尚未就绪或固定绑定发生冲突，请后端检查 facts、Assessment 与存储接线。");
    throw error;
  }
}

export async function getNoticeDraft(scanId: string, assessmentId: string, draftId: string, signal?: AbortSignal): Promise<NoticeDraft> {
  const raw = await request(`/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/notice-drafts/${encodeURIComponent(draftId)}`, {}, signal);
  return parseNoticeDraft(raw, scanId, assessmentId);
}
