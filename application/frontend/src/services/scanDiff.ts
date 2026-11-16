import { request } from './scans';

export type ScanStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled';
export type ScanRef = { scan_id: string; revision: string | null; facts_hash: string; input_hash: string; inventory_hash: string | null; status: ScanStatus; registry_revision: number };
export type AssessmentRef = { assessment_id: string; version: number; scan_id: string; facts_hash: string; usage_hash: string; rule_version: string; formal: true };
export type HistoryItem = { schema_version: '1.0'; scan_id: string; project_identity: { method: 'scan_only' | 'canonical_github_repo_v1'; key: string; source_project_id: string }; source_type: 'git' | 'zip' | 'local'; source: string; revision: string | null; status: ScanStatus; stage: string; created_at: string; finished_at: string | null; component_count: number; ai_asset_count: number; finding_count: number; latest_assessment: AssessmentRef | null };
export type EvidenceRef = { namespace: 'scan'; scan_id: string; evidence_id: string };
export type FieldChange = { path: string; before: string | null; after: string | null };
export type FactChange = FieldChange & { source_ids_before: string[]; source_ids_after: string[]; evidence_refs: EvidenceRef[] };
export type ResourceRef = { scan_id: string; resource_kind: 'component' | 'ai_asset'; resource_id: string; resource_identity_key: string | null; resource_instance_key: string | null };
export type ResourceChange = { kind: 'added' | 'not_observed_in_target' | 'changed' | 'ambiguous' | 'unmatched'; before: ResourceRef | null; after: ResourceRef | null; field_changes: FieldChange[]; evidence_refs: EvidenceRef[]; removal_confirmed: boolean | null };
export type ScanDiff = { schema_version: '1.0'; view_id: string; base: ScanRef; target: ScanRef; project_identity_key: string; resources: ResourceChange[]; license_observation_changes: FactChange[]; verification_changes: FactChange[]; finding_changes: FactChange[]; assessment_diff: { status: 'compared' | 'not_comparable' | 'unavailable'; base: AssessmentRef | null; target: AssessmentRef | null; reason: string | null; changes: FactChange[] }; coverage: { gaps: string[]; base_complete: boolean; target_complete: boolean } };
export type EvidenceDetail = { id: string; kind: string; locator: string; excerpt: string | null; verification_status: 'unknown' | 'pending' | 'verified'; start_line?: number | null; end_line?: number | null };

const obj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const nullable = (v: unknown): v is string | null => v === null || typeof v === 'string';
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
const integer = (v: unknown): v is number => Number.isInteger(v) && Number(v) >= 0;
const statuses = ['queued', 'running', 'completed', 'partial', 'failed', 'cancelled'];
const kinds = ['added', 'not_observed_in_target', 'changed', 'ambiguous', 'unmatched'];
const fail = (): never => { throw new Error('历史或差异响应不符合冻结 P1 契约。'); };
function scanRef(v: unknown): v is ScanRef { return obj(v) && text(v.scan_id) && nullable(v.revision) && text(v.facts_hash) && text(v.input_hash) && nullable(v.inventory_hash) && statuses.includes(String(v.status)) && integer(v.registry_revision) && v.registry_revision > 0; }
function assessmentRef(v: unknown): v is AssessmentRef { return obj(v) && text(v.assessment_id) && integer(v.version) && v.version > 0 && text(v.scan_id) && text(v.facts_hash) && text(v.usage_hash) && text(v.rule_version) && v.formal === true; }
function evidenceRefs(v: unknown): v is EvidenceRef[] { return Array.isArray(v) && v.every(r => obj(r) && r.namespace === 'scan' && text(r.scan_id) && text(r.evidence_id)); }
function field(v: unknown): v is FieldChange { return obj(v) && text(v.path) && nullable(v.before) && nullable(v.after); }
function fact(v: unknown): v is FactChange { return obj(v) && text(v.path) && nullable(v.before) && nullable(v.after) && strings(v.source_ids_before) && strings(v.source_ids_after) && evidenceRefs(v.evidence_refs); }
function resourceRef(v: unknown): v is ResourceRef { return obj(v) && text(v.scan_id) && ['component', 'ai_asset'].includes(String(v.resource_kind)) && text(v.resource_id) && nullable(v.resource_identity_key) && nullable(v.resource_instance_key); }
function resource(v: unknown): v is ResourceChange { return obj(v) && kinds.includes(String(v.kind)) && (v.before === null || resourceRef(v.before)) && (v.after === null || resourceRef(v.after)) && Array.isArray(v.field_changes) && v.field_changes.every(field) && evidenceRefs(v.evidence_refs) && (v.removal_confirmed === null || typeof v.removal_confirmed === 'boolean'); }
export function validateHistoryItem(v: unknown): HistoryItem {
  if (!obj(v) || v.schema_version !== '1.0' || !text(v.scan_id) || !obj(v.project_identity) || !['scan_only', 'canonical_github_repo_v1'].includes(String(v.project_identity.method)) || !text(v.project_identity.key) || !text(v.project_identity.source_project_id) || !['git', 'zip', 'local'].includes(String(v.source_type)) || !text(v.source) || !nullable(v.revision) || !statuses.includes(String(v.status)) || !text(v.stage) || !text(v.created_at) || !nullable(v.finished_at) || !integer(v.component_count) || !integer(v.ai_asset_count) || !integer(v.finding_count) || !(v.latest_assessment === null || assessmentRef(v.latest_assessment))) fail();
  return v as HistoryItem;
}
export function validateDiff(v: unknown, baseId: string, targetId: string): ScanDiff {
  if (!obj(v) || v.schema_version !== '1.0' || !text(v.view_id) || !scanRef(v.base) || v.base.scan_id !== baseId || !scanRef(v.target) || v.target.scan_id !== targetId || !text(v.project_identity_key) || !Array.isArray(v.resources) || !v.resources.every(resource) || !['license_observation_changes', 'verification_changes', 'finding_changes'].every(key => Array.isArray(v[key]) && (v[key] as unknown[]).every(fact)) || !obj(v.assessment_diff) || !['compared', 'not_comparable', 'unavailable'].includes(String(v.assessment_diff.status)) || !(v.assessment_diff.base === null || assessmentRef(v.assessment_diff.base)) || !(v.assessment_diff.target === null || assessmentRef(v.assessment_diff.target)) || !nullable(v.assessment_diff.reason) || !Array.isArray(v.assessment_diff.changes) || !v.assessment_diff.changes.every(fact) || !obj(v.coverage) || !strings(v.coverage.gaps) || typeof v.coverage.base_complete !== 'boolean' || typeof v.coverage.target_complete !== 'boolean') fail();
  const diff = v as ScanDiff;
  if (diff.resources.some(row => (row.before && row.before.scan_id !== baseId) || (row.after && row.after.scan_id !== targetId) || row.evidence_refs.some(ref => ![baseId, targetId].includes(ref.scan_id))) || [diff.license_observation_changes, diff.verification_changes, diff.finding_changes, diff.assessment_diff.changes].flat().some(row => row.evidence_refs.some(ref => ![baseId, targetId].includes(ref.scan_id)))) fail();
  if ((diff.assessment_diff.base && diff.assessment_diff.base.scan_id !== baseId) || (diff.assessment_diff.target && diff.assessment_diff.target.scan_id !== targetId)) fail();
  return diff;
}
export async function listAllHistory(signal?: AbortSignal): Promise<HistoryItem[]> {
  const items: HistoryItem[] = [], seen = new Set<string>(), cursors = new Set<string>();
  let cursor: string | undefined;
  do {
    const raw = await request('/scans?limit=100' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), { method: 'GET' }, signal);
    if (!obj(raw)) throw new Error('历史响应不符合冻结 P1 契约。');
    if (raw.schema_version !== '1.0' || !Array.isArray(raw.items) || !(raw.next_cursor === null || text(raw.next_cursor))) throw new Error('历史响应不符合冻结 P1 契约。');
    for (const value of raw.items) { const item = validateHistoryItem(value); if (seen.has(item.scan_id)) fail(); seen.add(item.scan_id); items.push(item); }
    if (raw.next_cursor && (cursors.has(raw.next_cursor) || !raw.items.length)) fail();
    cursor = raw.next_cursor ?? undefined;
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return items;
}
export function comparisonGate(base: HistoryItem | undefined, target: HistoryItem | undefined): string | null {
  if (!target) return '目标扫描不在当前历史记录中。';
  if (!base) return '请选择基准扫描。';
  if (base.scan_id === target.scan_id) return '不能比较同一次扫描；请选择不同的基准和目标。';
  if (!['completed', 'partial'].includes(base.status) || !['completed', 'partial'].includes(target.status)) return '仅 completed 或 partial 扫描可比较；失败或执行中的扫描不能作为差异结论。';
  if (base.project_identity.key !== target.project_identity.key || base.project_identity.method !== target.project_identity.method) return '两次扫描不属于同一后端项目身份，不能推断为同项目变化。ZIP 扫描默认仅有 scan_only 身份。';
  return null;
}
export async function getScanDiff(baseId: string, targetId: string, signal?: AbortSignal): Promise<ScanDiff> {
  if (!baseId || !targetId || baseId === targetId) throw new Error('请选择两次不同的真实扫描。');
  return validateDiff(await request('/scans/' + encodeURIComponent(targetId) + '/diff?base_scan_id=' + encodeURIComponent(baseId), { method: 'GET' }, signal), baseId, targetId);
}
export async function getDiffEvidence(ref: EvidenceRef, signal?: AbortSignal): Promise<EvidenceDetail> {
  const raw = await request('/scans/' + encodeURIComponent(ref.scan_id) + '/evidence/' + encodeURIComponent(ref.evidence_id), { method: 'GET' }, signal);
  if (!obj(raw) || raw.id !== ref.evidence_id || !text(raw.kind) || !text(raw.locator) || !nullable(raw.excerpt) || !['unknown', 'pending', 'verified'].includes(String(raw.verification_status))) fail();
  return raw as EvidenceDetail;
}
export function resourceSlice(rows: ResourceChange[], page: number, size = 50) { return rows.slice(Math.max(0, page) * size, (Math.max(0, page) + 1) * size); }
