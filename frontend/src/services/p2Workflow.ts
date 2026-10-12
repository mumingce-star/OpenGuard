import { ApiError, request } from './scans';
import { readP2Binding, readP2Index, readP2Result, sameBinding, validateP2Result } from './p2Advice';
import type { P2Answer, P2AnswerCode, P2AnswerRequest, P2Binding, P2CreateRequest, P2Material, P2MaterialRequest, P2Receipt, P2Result, P2Summary } from '../types/p2Advice';

const obj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const ids = (x: unknown): x is string[] => Array.isArray(x) && x.every(y => typeof y === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(y)) && new Set(x).size === x.length;
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const fail = (): never => { throw new Error('P2 回执身份或字段不符合冻结契约，保存结果待确认。'); };
const prefix = (b: P2Binding) => `/scans/${encodeURIComponent(b.scan_id)}/assessments/${encodeURIComponent(b.assessment_id)}/p2`;
const version = (b: P2Binding) => '?assessment_version=' + b.assessment_version;
const bound = (x: unknown, b: P2Binding) => obj(x) && sameBinding(x as unknown as P2Binding, b);
export const answerLabels: Record<P2AnswerCode, string> = {
  YES_INCLUDE: '包含选中资源', NO_EXCLUDE: '不包含选中资源', NOT_DECIDED: '范围尚未决定',
  FULFILLED: '我声明已履行（未经核验）', NOT_FULFILLED: '我声明尚未履行', NOT_DELIVERED_YET: '尚未交付', UNKNOWN: '未知',
};

export function validateSummary(x: unknown, r: P2Result): P2Summary {
  if (!obj(x) || x.summary_id !== r.companion_summary_id || x.result_id !== r.result_id || x.result_revision !== r.revision ||
    x.result_sha256 !== r.result_sha256 || !bound(x.binding, r.binding) || x.formal_effect !== 'none' ||
    x.report_kind !== 'P2_COMPANION_NOT_FORMAL_REPORT' || x.state !== r.state ||
    !same(x.material_ids, r.material_ids) || !same(x.answer_ids, r.answer_ids) || !obj(x.resource_states) ||
    Object.keys(x.resource_states).length !== r.resources.length || !r.resources.every(resource =>
      (x.resource_states as Record<string, unknown>)[resource.subject.resource_id] === resource.state)) return fail();
  return x as unknown as P2Summary;
}
export async function readP2Summary(r: P2Result, signal?: AbortSignal) {
  return validateSummary(await request(prefix(r.binding) + '/results/' + encodeURIComponent(r.result_id) + '/summary' + version(r.binding), {}, signal), r);
}
export function validateMaterial(x: unknown, r: P2Result, materialId: string): P2Material {
  if (!obj(x) || x.material_id !== materialId || !r.material_ids.includes(materialId) || !bound(x.binding, r.binding) ||
    x.data_scope !== r.data_scope || x.revision !== 1 || x.formal_effect !== 'none' || x.verification_state !== 'pending' ||
    x.source_level !== 'user_supplied_unverified' || x.parse_status !== 'text_observed' || x.adoption_status !== 'adopted_as_unverified_observation' ||
    !obj(x.subject) || !r.resources.some(item => same(item.subject, x.subject)) || !ids(x.evidence_ids) ||
    typeof x.filename !== 'string' || !/^(LICENSE|LICENCE|NOTICE)(\.(txt|md|rst))?$/i.test(x.filename) ||
    typeof x.source_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(x.source_sha256) ||
    !Number.isInteger(x.byte_count) || Number(x.byte_count) < 1 || Number(x.byte_count) > 65536 ||
    !['FULL_TEXT_CLAIMED', 'EXCERPT'].includes(String(x.completeness))) return fail();
  const resource = r.resources.find(item => same(item.subject, x.subject))!;
  if (!resource.material_ids.includes(materialId) || !x.evidence_ids.every(id => resource.evidence_ids.includes(id))) return fail();
  return x as unknown as P2Material;
}
export function validateAnswer(x: unknown, r: P2Result, answerId: string): P2Answer {
  if (!obj(x) || x.answer_id !== answerId || !r.answer_ids.includes(answerId) || !bound(x.binding, r.binding) ||
    x.data_scope !== r.data_scope || x.formal_effect !== 'none' || x.provenance !== 'USER_ASSERTED' ||
    !Number.isInteger(x.revision) || Number(x.revision) < 1 || Number(x.revision) > r.revision ||
    typeof x.question_id !== 'string' || !/^[A-Za-z0-9_.:-]{1,200}$/.test(x.question_id) || !ids(x.evidence_ids) ||
    !Array.isArray(x.subjects) || !x.subjects.length || !x.subjects.every(s => r.resources.some(item => same(item.subject, s))) ||
    !(x.question_code === 'DELIVERY_SCOPE_FOR_RESOURCES' ? ['YES_INCLUDE','NO_EXCLUDE','NOT_DECIDED'] :
      x.question_code === 'OBLIGATION_FULFILLMENT_IN_DELIVERY' ? ['FULFILLED','NOT_FULFILLED','NOT_DELIVERED_YET','UNKNOWN'] : []).includes(String(x.answer_code))) return fail();
  const resources = r.resources.filter(item => (x.subjects as unknown[]).some(s => same(s, item.subject)));
  if (!x.evidence_ids.every(id => resources.some(item => item.evidence_ids.includes(id))) ||
    resources.some(item => !item.answer_ids.includes(answerId))) return fail();
  return x as unknown as P2Answer;
}
export async function readP2Reference(r: P2Result, kind: 'materials' | 'answers', id: string, signal?: AbortSignal) {
  if (!(kind === 'materials' ? r.material_ids : r.answer_ids).includes(id)) return fail();
  const x = await request(prefix(r.binding) + '/' + kind + '/' + encodeURIComponent(id) + version(r.binding), {}, signal);
  return kind === 'materials' ? validateMaterial(x, r, id) : validateAnswer(x, r, id);
}

export function createFields(binding: P2Binding, parent: P2Result | null): P2CreateRequest {
  if (parent && !sameBinding(parent.binding, binding)) return fail();
  return { binding, expected_revision: parent?.revision ?? 0, parent_result_id: parent?.result_id ?? null, idempotency_key: crypto.randomUUID() };
}
export function prepareAnswer(r: P2Result, questionId: string, code: P2AnswerCode, selected: string[]): P2AnswerRequest {
  const q = r.questions.find(item => item.question_id === questionId);
  if (!q || !q.options.includes(code) || !selected.length || selected.length > 1000 || new Set(selected).size !== selected.length ||
    !selected.every(id => q.subjects.some(s => s.resource_id === id))) throw new Error('请选择服务端问题及其明确资源子集，不会默认提交全部资源。');
  return { ...createFields(r.binding, r), question_id: q.question_id, question_code: q.question_code, answer_code: code,
    subjects: q.subjects.filter(s => selected.includes(s.resource_id)), evidence_ids: [] };
}
export async function prepareMaterial(r: P2Result, resourceId: string, evidenceIds: string[], filename: string,
  bytes: Uint8Array, description: string, completeness: 'FULL_TEXT_CLAIMED' | 'EXCERPT'): Promise<P2MaterialRequest> {
  const resource = r.resources.find(item => item.subject.resource_id === resourceId);
  if (!resource || !resource.subject.version) throw new Error('资源版本未精确确认，不能提交材料。');
  if (r.material_ids.length >= 20) throw new Error('当前已达到20份材料上限；最终数量由后端核对。');
  if (!ids(evidenceIds) || !evidenceIds.length || evidenceIds.length > 100 || !evidenceIds.every(id => resource.evidence_ids.includes(id))) throw new Error('必须选择本资源原有 Evidence。');
  if (!/^(LICENSE|LICENCE|NOTICE)(\.(txt|md|rst))?$/i.test(filename)) throw new Error('只允许 LICENSE、LICENCE、NOTICE 及 .txt/.md/.rst 后缀。');
  if (!bytes.length || bytes.length > 65536) throw new Error('材料原字节必须为1–65,536字节。');
  let text: string;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch { throw new Error('材料必须为有效 UTF-8。'); }
  if (!text.trim() || text.includes('\0')) throw new Error('不接受空文本或包含 NUL 的二进制材料。');
  if (!description.trim() || [...description].length > 512) throw new Error('请填写1–512字符的材料来源说明。');
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  let binary = ''; bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  const body: P2MaterialRequest = { ...createFields(r.binding, r), subject: resource.subject, evidence_ids: [...evidenceIds], filename,
    content_base64: btoa(binary), source_sha256: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join(''),
    source_description: description, completeness };
  if (new TextEncoder().encode(JSON.stringify(body)).length > 98304) throw new Error('材料请求体超过98,304字节。');
  return body;
}

export function p2ErrorMessage(error: unknown): string {
  const detail = error instanceof Error ? error.message : '请求失败';
  if (!(error instanceof ApiError)) return '保存结果待确认；请先只读核对，再手动重放原请求。' + detail;
  const messages: Record<number, string> = {
    403: '请求被拒绝，请核对获准环境和来源。', 404: '固定对象未找到，不会替换为最新对象。',
    409: '版本、身份或幂等冲突；需重读服务器状态，不自动合并。',
    413: '材料或容量超限，请按限制修改。', 422: '输入不符合契约，请检查具体原因后修改。',
    503: '服务不可用；保存结果待确认，不能断言未保存。',
  };
  return (messages[error.status] ?? '保存结果待确认。') + ' ' + detail + (error.reason ? '；原因：' + error.reason : '');
}

// One immutable in-memory attempt. No storage, automatic POST, or replacement key on uncertain outcomes.
export class P2WriteAttempt {
  readonly body: string;
  readonly binding: P2Binding;
  readonly input: P2CreateRequest | P2AnswerRequest | P2MaterialRequest;
  state: 'draft' | 'sending' | 'saved' | 'unknown' | 'conflict' | 'rejected' = 'draft';
  recovered = false;
  receipt: P2Receipt | null = null;
  constructor(readonly kind: 'results' | 'answers' | 'materials', input: P2CreateRequest | P2AnswerRequest | P2MaterialRequest) {
    this.body = JSON.stringify(input);
    this.input = JSON.parse(this.body);
    this.binding = this.input.binding;
    const limit = kind === 'materials' ? 98304 : 16384;
    if (new TextEncoder().encode(this.body).length > limit) throw new Error('请求体超过后端大小限制。');
  }
  async recover() {
    this.recovered = false;
    const b = await readP2Binding(this.binding.scan_id, this.binding.assessment_id, this.binding.assessment_version);
    if (!sameBinding(b, this.binding)) throw new Error('父绑定已变化；不能重放或自动替换父身份。');
    const index = await readP2Index(b);
    const head = index.head_result_id ? await readP2Result(b, index.head_result_id, index.head_revision) : null;
    this.recovered = true;
    return head;
  }
  async send(): Promise<P2Receipt> {
    if (this.state !== 'draft' && !(this.state === 'unknown' && this.recovered)) throw new Error('请先核对服务器状态；冲突或拒绝后不可自动重放。');
    this.state = 'sending'; this.recovered = false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
      const response = await fetch(base + prefix(this.binding) + '/' + this.kind, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: this.body, signal: controller.signal,
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const e = obj(payload) && obj(payload.error) ? payload.error : {};
        throw new ApiError(response.status, typeof e.message === 'string' ? e.message : 'P2写入失败',
          typeof e.code === 'string' ? e.code : undefined, obj(e.details) && typeof e.details.reason === 'string' ? e.details.reason : undefined);
      }
      if (response.status !== 201 || !obj(payload)) return fail();
      const result = validateP2Result(payload.result, this.binding);
      if (result.revision < this.input.expected_revision || result.revision > this.input.expected_revision + 1 ||
        (result.revision === this.input.expected_revision && result.result_id !== this.input.parent_result_id) ||
        (result.revision === this.input.expected_revision + 1 && result.previous_result_id !== this.input.parent_result_id)) return fail();
      const answer = payload.answer == null ? null : validateAnswer(payload.answer, result, String((payload.answer as P2Answer).answer_id));
      const material = payload.material == null ? null : validateMaterial(payload.material, result, String((payload.material as P2Material).material_id));
      if (this.kind === 'answers') {
        const sent = this.input as P2AnswerRequest;
        if (!answer || material || answer.question_id !== sent.question_id || answer.question_code !== sent.question_code || answer.answer_code !== sent.answer_code || !same(answer.subjects, sent.subjects) || !same(answer.evidence_ids, sent.evidence_ids)) return fail();
      } else if (this.kind === 'materials') {
        const sent = this.input as P2MaterialRequest;
        if (!material || answer || !same(material.subject, sent.subject) || !same(material.evidence_ids, sent.evidence_ids) || material.source_sha256 !== sent.source_sha256 || material.filename !== sent.filename || material.completeness !== sent.completeness) return fail();
      } else if (answer || material) return fail();
      this.receipt = { result, answer, material }; this.state = 'saved';
      return this.receipt;
    } catch (error) {
      this.state = error instanceof ApiError && error.status === 409 ? 'conflict' :
        error instanceof ApiError && [403,404,413,422].includes(error.status) ? 'rejected' : 'unknown';
      throw error;
    } finally { clearTimeout(timer); }
  }
}

export function p2Selection(query: URLSearchParams, assessmentVersion: number) {
  const id = query.get('p2_result_id'); const revision = query.get('p2_revision'); const av = query.get('assessment_version');
  if (av !== null && (!/^[1-9]\d*$/.test(av) || Number(av) !== assessmentVersion)) throw new Error('URL评估版本与正式对象不一致。');
  if ((id === null) !== (revision === null) || (id !== null && (!/^[A-Za-z0-9_.:-]{1,200}$/.test(id) || !/^[1-9]\d*$/.test(revision!)))) throw new Error('URL必须同时包含完整P2结果ID与有效revision。');
  return id ? { id, revision: Number(revision) } : null;
}
