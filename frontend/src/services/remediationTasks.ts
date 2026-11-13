import { ApiError, request } from './scans';
import type { Assessment } from './assessments';

export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'dismissed';
export type EvidenceRef = { namespace: 'scan'; scan_id: string; evidence_id: string } | { namespace: 'profile_observation'; observation_id: string };
export type RemediationTask = {
  schema_version: '1.0'; task_id: string; scan_id: string;
  assessment_ref: { assessment_id: string; version: number; scan_id: string; facts_hash: string; usage_hash: string; rule_version: string; formal: true };
  origin: { kind: 'condition' | 'restriction' | 'gap' | 'next_step' | 'obligation'; source_pointer: string; source_hash: string };
  resource_ids: string[]; evidence_refs: EvidenceRef[]; title: string; status: TaskStatus;
  note: string; version: number; superseded: boolean; created_at: string; updated_at: string;
};
const statuses: TaskStatus[] = ['todo', 'in_progress', 'done', 'dismissed'];
const kinds = ['condition', 'restriction', 'gap', 'next_step', 'obligation'];
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && !!v;
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
function fail(): never { throw new Error('整改任务响应不符合冻结 Task API 契约。'); }
export function validateTask(v: unknown, scanId: string, assessmentId: string): RemediationTask {
  if (!record(v) || v.schema_version !== '1.0' || !text(v.task_id) || v.scan_id !== scanId || !record(v.assessment_ref) || v.assessment_ref.assessment_id !== assessmentId || v.assessment_ref.scan_id !== scanId || v.assessment_ref.formal !== true || !Number.isInteger(v.assessment_ref.version) || !text(v.assessment_ref.facts_hash) || !text(v.assessment_ref.usage_hash) || !text(v.assessment_ref.rule_version) || !record(v.origin) || !kinds.includes(String(v.origin.kind)) || !text(v.origin.source_pointer) || !v.origin.source_pointer.startsWith('/') || !text(v.origin.source_hash) || !strings(v.resource_ids) || !Array.isArray(v.evidence_refs) || !v.evidence_refs.every(ref => record(ref) && (ref.namespace === 'scan' ? ref.scan_id === scanId && text(ref.evidence_id) : ref.namespace === 'profile_observation' && text(ref.observation_id))) || !text(v.title) || !statuses.includes(v.status as TaskStatus) || typeof v.note !== 'string' || v.note.length > 2000 || (['done', 'dismissed'].includes(String(v.status)) && !v.note.trim()) || !Number.isInteger(v.version) || Number(v.version) < 1 || typeof v.superseded !== 'boolean' || !text(v.created_at) || !text(v.updated_at) || !Number.isFinite(Date.parse(v.updated_at))) fail();
  return v as RemediationTask;
}
function prefix(scanId: string, assessmentId: string) { return '/scans/' + encodeURIComponent(scanId) + '/assessments/' + encodeURIComponent(assessmentId) + '/remediation-tasks'; }
export async function listTaskPage(scanId: string, assessmentId: string, cursor?: string, signal?: AbortSignal) {
  const url = prefix(scanId, assessmentId) + '?limit=100' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : '');
  const raw = await request(url, { method: 'GET' }, signal);
  if (!record(raw) || raw.schema_version !== '1.0' || !Array.isArray(raw.items) || !(raw.next_cursor === null || text(raw.next_cursor))) fail();
  return { items: raw.items.map(item => validateTask(item, scanId, assessmentId)), next_cursor: raw.next_cursor as string | null };
}
export async function listAllTasks(scanId: string, assessmentId: string, signal?: AbortSignal) {
  const items: RemediationTask[] = [], seen = new Set<string>(), cursors = new Set<string>();
  let cursor: string | undefined;
  do {
    const page = await listTaskPage(scanId, assessmentId, cursor, signal);
    for (const task of page.items) { if (seen.has(task.task_id)) fail(); seen.add(task.task_id); items.push(task); }
    if (page.next_cursor && (cursors.has(page.next_cursor) || !page.items.length)) fail();
    cursor = page.next_cursor ?? undefined;
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return items;
}
export async function deriveTasks(scanId: string, assessment: Assessment & { facts_hash: string }, requestKey: string) {
  const raw = await request(prefix(scanId, assessment.id) + '/derive', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idempotency_key: requestKey, expected_facts_hash: assessment.facts_hash }) });
  if (!record(raw) || raw.schema_version !== '1.0' || !Array.isArray(raw.items)) fail();
  return raw.items.map(item => validateTask(item, scanId, assessment.id));
}
export async function patchTask(scanId: string, assessmentId: string, task: RemediationTask, changes: { status?: TaskStatus; note?: string }) {
  if (!('status' in changes || 'note' in changes) || (changes.status && !statuses.includes(changes.status)) || (changes.note !== undefined && changes.note.length > 2000)) throw new Error('任务更新内容无效。');
  const raw = await request(prefix(scanId, assessmentId) + '/' + encodeURIComponent(task.task_id), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_version: task.version, ...changes }) });
  const updated = validateTask(raw, scanId, assessmentId);
  if (updated.task_id !== task.task_id || updated.version <= task.version) fail();
  return updated;
}
export function optimisticTask(task: RemediationTask, changes: { status?: TaskStatus; note?: string }): RemediationTask { return { ...task, ...changes }; }
export function isVersionConflict(error: unknown): boolean { return error instanceof ApiError && error.status === 409 && error.reason === 'stale_version'; }
export function taskLinks(task: RemediationTask, assessment: Assessment) {
  const pointer = task.origin.source_pointer;
  const obligationIndex = /^\/obligations\/(\d+)$/.exec(pointer);
  const resourceIndex = /^\/resource_evaluations\/(\d+)(?:\/|$)/.exec(pointer);
  const obligation = obligationIndex ? assessment.obligations[Number(obligationIndex[1])] : undefined;
  const resource = resourceIndex ? assessment.resource_evaluations?.[Number(resourceIndex[1])] : undefined;
  return { obligation: obligation && task.origin.kind === 'obligation' ? obligation : undefined, findingIds: resource && task.resource_ids.includes(resource.resource_id) ? resource.finding_ids : [] };
}
