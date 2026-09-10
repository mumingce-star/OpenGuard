import { request } from './scans';
export const presets = { unknown: '暂不确定／跳过', personal: '个人学习', internal: '企业内部使用', open_source: '开源发布', closed_source: '闭源交付', service: '对外在线服务' } as const;
export const usageFields = { commercial: '涉及商业使用', modified: '修改项目代码', distributed: '向他人分发／交付', network_service: '对外提供在线服务', training: '用于模型训练', redistributed_assets: '再分发模型／数据等资源', source_disclosure: '计划公开源代码' } as const;
export type Usage = { preset: keyof typeof presets; declared_at?: string | null } & Partial<Record<keyof typeof usageFields, boolean | null>>;
export const emptyUsage = (): Usage => ({ preset: 'unknown', ...Object.fromEntries(Object.keys(usageFields).map(k => [k, null])) });
export type Dimension = { id: string; title: string; status: 'conditional' | 'restricted' | 'unknown' | 'not_applicable'; conclusion: string; conditions: string[]; restrictions: string[]; unknowns: string[]; resource_ids: string[]; finding_ids: string[]; evidence_ids: string[]; strength: string };
export type Assessment = { id: string; version: number; scan_id: string; project_name: string; generated_at: string; usage: Usage; summary: string; ai_status: string; ai_summary: string | null; ai_evidence_ids?: string[]; dimensions: Dimension[]; coverage_issues: string[]; resource_ids: string[]; finding_ids: string[]; evidence_ids: string[]; rule_version: string; model_version: string; prompt_version: string; obligations: { id: string; action: string; requirement: string; trigger: string; fulfillment: string; resource_ids: string[]; evidence_ids: string[]; rule_id: string; rule_version: string }[] };
export type Job = { request_id: string; status: 'pending' | 'succeeded' | 'failed'; assessment_id?: string; error?: string | null };
export type Turn = { request_id: string; assessment_id: string; question: string; answer: string | null; evidence_ids: string[]; status: Job['status']; error: string | null; created_at: string; elapsed_seconds?: number };
export type Chat = { items: Turn[]; generation: number; limits: { max_message_chars: number; max_turns: number } };
const obj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const strs = (x: unknown): x is string[] => Array.isArray(x) && x.every(y => typeof y === 'string');
const fail = (): never => { throw new Error('评估／问答数据不符合接口契约，请检查运行版本。'); };
export function validateAssessment(x: unknown, scanId: string): Assessment {
 if (!obj(x) || x.scan_id !== scanId || typeof x.id !== 'string' || !x.id || !Number.isInteger(x.version) || Number(x.version) < 1 || !obj(x.usage) || !(String(x.usage.preset) in presets) || typeof x.generated_at !== 'string' || !Number.isFinite(Date.parse(x.generated_at)) || typeof x.ai_status !== 'string' || !(x.ai_summary === null || typeof x.ai_summary === 'string') || (x.ai_evidence_ids !== undefined && !strs(x.ai_evidence_ids)) || typeof x.summary !== 'string' || !Array.isArray(x.dimensions) || !x.dimensions.every(d => obj(d) && typeof d.id === 'string' && typeof d.title === 'string' && typeof d.conclusion === 'string' && ['conditional','restricted','unknown','not_applicable'].includes(String(d.status)) && ['conditions','restrictions','unknowns','resource_ids','finding_ids','evidence_ids'].every(k => strs(d[k]))) || !['coverage_issues','resource_ids','finding_ids','evidence_ids'].every(k => strs(x[k])) || !Array.isArray(x.obligations) || !x.obligations.every(o => obj(o) && typeof o.id === 'string' && typeof o.action === 'string' && typeof o.requirement === 'string' && typeof o.trigger === 'string' && strs(o.evidence_ids))) return fail();
 return x as Assessment;
}
export function validateChat(x: unknown): Chat {
 if (!obj(x) || !Number.isInteger(x.generation) || Number(x.generation) < 0 || !obj(x.limits) || !Number.isInteger(x.limits.max_message_chars) || !Number.isInteger(x.limits.max_turns) || !Array.isArray(x.items) || !x.items.every(t => obj(t) && typeof t.request_id === 'string' && typeof t.assessment_id === 'string' && typeof t.question === 'string' && (t.answer === null || typeof t.answer === 'string') && strs(t.evidence_ids) && ['pending','succeeded','failed'].includes(String(t.status)))) return fail();
 return x as Chat;
}

export function validateJob(x: unknown, requestId: string): Job {
 if (!obj(x) || typeof x.request_id !== 'string' || !x.request_id || x.request_id !== requestId || !['pending', 'succeeded', 'failed'].includes(String(x.status)) || (x.status === 'succeeded' && typeof x.assessment_id !== 'string')) return fail();
 return x as Job;
}
const prefix = (id: string) => '/scans/' + encodeURIComponent(id);
const json = (value: unknown) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
export async function listAssessments(id: string, signal?: AbortSignal) { const x = await request(prefix(id) + '/assessments', {}, signal); if (!obj(x) || !Array.isArray(x.items)) return fail(); return { items: x.items.map(a => validateAssessment(a, id)), usage: x.usage as Usage | null, pending_job: x.pending_job == null ? null : validateJob(x.pending_job, String((x.pending_job as Record<string, unknown>).request_id)) }; }
export async function createAssessment(id: string, usage: Usage, request_id: string) { return validateJob(await request(prefix(id) + '/assessments', json({ usage, request_id })), request_id); }
export async function getJob(id: string, requestId: string, signal?: AbortSignal) { return validateJob(await request(prefix(id) + '/assessments/jobs/' + encodeURIComponent(requestId), {}, signal), requestId); }
export async function getChat(id: string, signal?: AbortSignal) { return validateChat(await request(prefix(id) + '/chat', {}, signal)); }
export async function sendChat(id: string, value: { assessment_id: string; request_id: string; message: string; generation: number }) { return await request(prefix(id) + '/chat', json(value)) as Turn; }
export async function clearChat(id: string, generation: number) { return await request(prefix(id) + '/chat?confirmed=true&generation=' + generation, { method: 'DELETE' }) as { generation: number; items: [] }; }
export function assessmentReportUrl(id: string, aid: string, format: 'html' | 'json') { return (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '') + prefix(id) + '/assessments/' + encodeURIComponent(aid) + '/report?format=' + format; }
