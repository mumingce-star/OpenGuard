import type { Assessment } from './assessments';
import { appendDependencyEvidencePage, readDependencyEvidencePage, type DependencyEvidenceFeed } from './dependencyEvidence';
import { readMaterialClaims, type ClaimDelta, type ClaimState, type MaterialClaims } from './materialClaims';
import { sameBinding, type Binding, type Result, type Subject } from './p2';
import type { Scan } from '../types/domain';

export const v4AnalysisProtocol = 'openguard-qwen-v4-plan/3';
const v4PlanProtocol = 'openguard-action-plan/3';
const promptVersion = 'p2-v4-structured-plan/1';
const displayOrigin = 'PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION';
const claimUses = ['commercial', 'distributed', 'modified'] as const;
const claimsStates = new Set(['SUPPORT', 'RESTRICTION', 'UNKNOWN', 'COUNTER_EVIDENCE', 'NOT_COVERED']);
const quoteKinds = new Set(['license_identifier', 'copyright', 'permission', 'condition', 'warranty', 'notice']);
const noticeStates = new Set(['ABSENT_COMPLETE', 'PRESENT_UNREVIEWED', 'INCOMPLETE', 'INVALID']);
const permissive = new Set(['MIT', 'Apache-2.0', 'ISC', 'BSD-2-Clause', 'BSD-3-Clause']);
const copyleft = new Set(['MPL-2.0','GPL-2.0','GPL-3.0','LGPL-2.1','LGPL-3.0','AGPL-3.0']);
const usageNames = { commercial: '商业使用', distributed: '分发或交付', modified: '修改代码' };

type ClaimUse = typeof claimUses[number];
type V4Subject = Subject & { component_name: string; ecosystem: 'npm' | 'pypi' };
type V4Quote = {
  quote_id: string; material_id: string; clause_id: string; kind: string; quote: string;
  quote_sha256: string; byte_start: number; byte_end: number;
};
type ActionKind = keyof typeof actionTexts;
type ActionBinding = { action_kind: ActionKind; basis_ids: string[] };
type V4Action = ActionBinding & { text: string };
type V4Change = { index: number; explanation: string };
type V4Selection = {
  analysis_protocol: typeof v4AnalysisProtocol;
  prompt_version: typeof promptVersion;
  selected_quotes: { quote_id: string; category: string }[];
  selected_actions: ActionBinding[];
  selected_change_indices: number[];
};
type DependencyContext = {
  resource_id: string;
  version: string | null;
  gaps: string[];
  conflicts: { code: string; status: string; evidence_ids: string[] }[];
};
type V4PlanContext = {
  protocol: typeof v4PlanProtocol;
  material_claims_view_id: string;
  result_id: string;
  result_sha256: string;
  result_revision: number;
  previous_result_id: string | null;
  binding: Binding;
  subject: V4Subject;
  usage: Result['usage'];
  declared_spdx: string;
  claim_states: Record<ClaimUse, ClaimState>;
  advice_reasons: Record<ClaimUse, string[]>;
  counter_evidence_codes: string[];
  source_binding: 'PINNED_RELEASE_MATCH' | 'NOT_ESTABLISHED';
  notice_status: string | null;
  incremental_impact_summary: { mode: MaterialClaims['incremental_impact']['mode']; changed_claims: ClaimDelta[] };
  dependency_conflicts: DependencyContext | null;
  material_ids: string[];
  quote_catalog: V4Quote[];
  action_catalog: (ActionBinding & { required: boolean })[];
};
export type V4PlanEnvelope = {
  analysis_protocol: typeof v4AnalysisProtocol;
  display_origin: typeof displayOrigin;
  material_claims_view_id: string;
  context_sha256: string;
  plan_input_sha256: string;
  selection_sha256: string | null;
  context: V4PlanContext;
  plan: V4Selection | null;
  clauses: V4Quote[];
  actions: V4Action[];
  changes: V4Change[];
};

const actionTexts = {
  VERIFY_PERMISSIVE_OBLIGATIONS: (label: string) => '核对 ' + label + ' 的拟交付文件是否保留版权声明及许可文本。',
  RESOLVE_SPDX_TEXT_CONFLICT: (label: string) => '核对 ' + label + ' 的 SPDX 声明、绑定许可原文及各自来源，处理冲突后重新研判。',
  REVIEW_STRONG_COPYLEFT_DISCLOSURE: (label: string) => '人工核对 ' + label + ' 的源代码披露范围与拟采用的交付方式。',
  REVIEW_WEAK_COPYLEFT_FILE_SCOPE: (label: string) => '人工核对 ' + label + ' 的相关文件范围及适用条件。',
  REVIEW_APACHE_NOTICE_SECTION_4D: (label: string) => '人工核对 ' + label + ' 的 Apache-2.0 §4(d) NOTICE 归属和呈现要求。',
  SUPPLY_MISSING_LICENSE_MATERIAL: (label: string) => '补充 ' + label + ' 对应版本的许可证原文及来源记录。',
  VERIFY_UNESTABLISHED_RELEASE_SOURCE: (label: string) => '核对 ' + label + ' 的发行记录、材料原文与精确版本的对应关系。',
  RESOLVE_DEPENDENCY_VERSION_CONFLICT: (label: string) => '核对 ' + label + ' 的依赖声明和锁定版本，再处理记录中的冲突。',
  PIN_EXACT_DEPENDENCY_VERSION: (label: string) => '补充 ' + label + ' 的精确依赖版本及锁定来源。',
  CONFIRM_UNKNOWN_USAGE_FIELD: (label: string) => '确认 ' + label + ' 尚未声明的使用方式，补全用途记录。',
};

const obj = (value: unknown): value is Record<string, any> => !!value && typeof value === 'object' && !Array.isArray(value);
const keys = (value: unknown, fields: string) => obj(value) && Object.keys(value).sort().join(',') === fields.split(' ').sort().join(',');
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 65536;
const id = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(value);
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const ids = (value: unknown): value is string[] => Array.isArray(value) && value.every(id) && new Set(value).size === value.length;
const sameSubject = (left: Subject, right: Subject) => left.resource_id === right.resource_id && left.version === right.version;
const kindOf = (value: unknown): value is ActionKind => typeof value === 'string' && Object.hasOwn(actionTexts, value);
const invalid = (): never => { throw Error('v4 分析的证据、固定结果或行动依据不一致，已有规则结果保持不变。'); };

function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (obj(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}

const same = (left: unknown, right: unknown) => canonical(left) === canonical(right);

function v4Hash(bytes: Uint8Array<ArrayBuffer>) {
  if (!globalThis.crypto?.subtle) return invalid();
  return globalThis.crypto.subtle.digest('SHA-256', bytes).then(
    value => Array.from(new Uint8Array(value), item => item.toString(16).padStart(2, '0')).join(''),
  );
}

function safeCanonical(value: unknown): boolean {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return true;
  if (typeof value === 'number') return Number.isSafeInteger(value) && !Object.is(value, -0);
  if (Array.isArray(value)) return value.every(safeCanonical);
  return obj(value) && Object.entries(value).every(([key, item]) =>
    /^[A-Za-z0-9_.:-]+$/.test(key) && safeCanonical(item),
  );
}

function checkDependency(value: unknown, subject: V4Subject): boolean {
  if (value === null) return true;
  return obj(value) && keys(value, 'resource_id version gaps conflicts')
    && value.resource_id === subject.resource_id && value.version === subject.version
    && ids(value.gaps) && Array.isArray(value.conflicts)
    && value.conflicts.every((item: unknown) => obj(item) && keys(item, 'code status evidence_ids')
      && item.code === 'lock_version_conflict' && ['confirmed', 'ambiguous', 'incomplete'].includes(item.status)
      && ids(item.evidence_ids));
}

export function validateV4Plan(value: Record<string, any>, result: Result): V4PlanEnvelope {
  const ctx = value.context;
  const refs = value.source_refs;
  if (!obj(ctx) || !keys(ctx, 'protocol material_claims_view_id result_id result_sha256 result_revision previous_result_id binding subject usage declared_spdx claim_states advice_reasons counter_evidence_codes source_binding notice_status incremental_impact_summary dependency_conflicts material_ids quote_catalog action_catalog')
    || ctx.protocol !== v4PlanProtocol || !id(ctx.material_claims_view_id)
    || ctx.material_claims_view_id !== value.material_claims_view_id || !hash(value.context_sha256) || !hash(value.plan_input_sha256)
    || ctx.result_id !== result.result_id || ctx.result_sha256 !== result.result_sha256
    || ctx.result_revision !== result.revision || ctx.previous_result_id !== result.previous_result_id
    || !obj(ctx.binding) || !sameBinding(ctx.binding as Binding, result.binding) || !same(ctx.usage, result.usage)
    || value.analysis_protocol !== v4AnalysisProtocol || value.display_origin !== displayOrigin || value.formal_effect !== 'none'
    || value.previous_result_id !== result.previous_result_id || value.model.prompt_version !== promptVersion
    || !ids(ctx.material_ids) || ctx.material_ids.length > 4 || !text(ctx.declared_spdx)
    || !obj(ctx.subject) || !keys(ctx.subject, 'resource_id version component_name ecosystem')
    || !id(ctx.subject.resource_id) || !(ctx.subject.version === null || text(ctx.subject.version))
    || !text(ctx.subject.component_name) || !['npm', 'pypi'].includes(ctx.subject.ecosystem)
    || !obj(ctx.claim_states) || !keys(ctx.claim_states, 'commercial distributed modified')
    || !obj(ctx.advice_reasons) || !keys(ctx.advice_reasons, 'commercial distributed modified')
    || !claimUses.every(use => claimsStates.has(ctx.claim_states[use])
      && ids(ctx.advice_reasons[use]) && ctx.advice_reasons[use].length > 0)
    || !ids(ctx.counter_evidence_codes) || !['PINNED_RELEASE_MATCH', 'NOT_ESTABLISHED'].includes(ctx.source_binding)
    || !(ctx.notice_status === null || noticeStates.has(ctx.notice_status))
    || !obj(ctx.incremental_impact_summary) || !keys(ctx.incremental_impact_summary, 'mode changed_claims')
    || ctx.incremental_impact_summary.mode !== (result.revision === 1 ? 'INITIAL_RESULT' : 'INCREMENTAL_DERIVED')
    || !Array.isArray(ctx.incremental_impact_summary.changed_claims) || !checkDependency(ctx.dependency_conflicts, ctx.subject as V4Subject)
    || !Array.isArray(ctx.quote_catalog) || !Array.isArray(ctx.action_catalog)
    || ctx.quote_catalog.length > 24 || ctx.action_catalog.length > Object.keys(actionTexts).length || !safeCanonical(ctx)
    || new TextEncoder().encode(canonical(ctx)).length > 20000) return invalid();

  const context = ctx as V4PlanContext;
  const row = result.resources.find(item => sameSubject(item.subject, context.subject));
  if (!row || row.resource_kind !== 'component' || !context.material_ids.every(material => row.material_ids.includes(material))
    || !same([...context.material_ids].sort(), refs.map((ref: { material_id: string }) => ref.material_id).sort())
    || !refs.every((ref: { subject: Subject }) => sameSubject(ref.subject, context.subject))) return invalid();

  const quotes = new Map<string, V4Quote>();
  for (const quote of context.quote_catalog) {
    const ref = refs.find((item: { material_id: string }) => item.material_id === quote?.material_id);
    if (!keys(quote, 'quote_id material_id clause_id kind quote quote_sha256 byte_start byte_end') || !id(quote.quote_id)
      || !id(quote.clause_id) || quotes.has(quote.quote_id) || !ref || !quoteKinds.has(quote.kind) || !text(quote.quote)
      || !hash(quote.quote_sha256) || !Number.isSafeInteger(quote.byte_start) || !Number.isSafeInteger(quote.byte_end)
      || quote.byte_start < 0 || quote.byte_end <= quote.byte_start || quote.byte_end > ref.byte_count
      || new TextEncoder().encode(quote.quote).length !== quote.byte_end - quote.byte_start) return invalid();
    quotes.set(quote.quote_id, quote);
  }

  const catalog = new Map<ActionKind, ActionBinding & { required: boolean }>();
  const states = Object.values(context.claim_states);
  const permitsAction = permissive.has(context.declared_spdx) && states.includes('SUPPORT')
    && !states.some(state => state === 'UNKNOWN' || state === 'COUNTER_EVIDENCE')
    && !context.counter_evidence_codes.some(code => code !== 'NOTICE_REQUIRES_REVIEW');
  for (const action of context.action_catalog) {
    if (!keys(action, 'action_kind basis_ids required') || !kindOf(action.action_kind) || catalog.has(action.action_kind)
      || !ids(action.basis_ids) || !action.basis_ids.length || typeof action.required !== 'boolean'
      || (action.action_kind === 'VERIFY_PERMISSIVE_OBLIGATIONS' && !permitsAction)) return invalid();
    catalog.set(action.action_kind, action);
  }

  if (value.status === 'failed') {
    if (value.plan !== null || value.selection_sha256 !== null || value.actions.length || value.clauses.length || value.changes.length) return invalid();
    return value as V4PlanEnvelope;
  }

  const p = value.plan;
  if (!hash(value.selection_sha256) || !obj(p) || !keys(p,'analysis_protocol prompt_version selected_quotes selected_actions selected_change_indices')
    || p.analysis_protocol !== v4AnalysisProtocol || p.prompt_version !== promptVersion
    || !Array.isArray(p.selected_quotes) || !Array.isArray(p.selected_actions) || !Array.isArray(p.selected_change_indices)
    || p.selected_actions.length < 1 || p.selected_actions.length > 4
    || p.selected_quotes.length > 6 || p.selected_quotes.length > context.quote_catalog.length
    || p.selected_change_indices.length > context.incremental_impact_summary.changed_claims.length || !safeCanonical(p)) return invalid();

  const plan = p as V4Selection;
  const selectedQuoteIds = plan.selected_quotes.map(entry => entry?.quote_id);
  if (!ids(selectedQuoteIds)) return invalid();
  const expectedQuotes = plan.selected_quotes.map(entry => {
    const quote = quotes.get(entry.quote_id);
    if (!quote || !keys(entry, 'quote_id category') || entry.category !== quote.kind) return invalid();
    return quote;
  });

  const label = context.subject.component_name + '@' + (context.subject.version ?? '版本未确定');
  const selectedKinds = new Set<ActionKind>();
  const expectedActions = plan.selected_actions.map(action => {
    if (!keys(action, 'action_kind basis_ids') || !kindOf(action.action_kind) || !ids(action.basis_ids)
      || selectedKinds.has(action.action_kind) || !same(catalog.get(action.action_kind)?.basis_ids, action.basis_ids)) return invalid();
    selectedKinds.add(action.action_kind);
    return { action_kind: action.action_kind, basis_ids: action.basis_ids, text: actionTexts[action.action_kind](label) };
  });
  if (context.action_catalog.some(action => action.required && !selectedKinds.has(action.action_kind))) return invalid();

  const indices = new Set<number>();
  const expectedChanges = plan.selected_change_indices.map(index => {
    if (!Number.isSafeInteger(index) || index < 0 || indices.has(index)) return invalid();
    indices.add(index);
    const change = context.incremental_impact_summary.changed_claims[index];
    if (!change || !claimUses.includes(change.usage as ClaimUse) || !sameSubject(change.subject, context.subject)
      || !claimsStates.has(change.previous_state) || !claimsStates.has(change.current_state)) return invalid();
    const explanation = label + ' 的' + usageNames[change.usage as ClaimUse] + '研判由 ' + change.previous_state
      + ' 变为 ' + change.current_state + '。核对本次变动的材料与证据。';
    return { index, explanation };
  });
  if (!same(value.clauses, expectedQuotes) || !same(value.actions, expectedActions) || !same(value.changes, expectedChanges)) return invalid();
  return value as V4PlanEnvelope;
}

export async function verifyV4PlanHashes(value: V4PlanEnvelope) {
  const encoder = new TextEncoder();
  const digest = (payload: unknown) => v4Hash(encoder.encode(canonical(payload)));
  const contextInput = { analysis_protocol: v4AnalysisProtocol, context: value.context, context_sha256: value.context_sha256 };
  if (await digest(value.context) !== value.context_sha256 || await digest(contextInput) !== value.plan_input_sha256
    || (value.plan !== null && await digest(value.plan) !== value.selection_sha256)) return invalid();
  for (const quote of value.context.quote_catalog) {
    if (await v4Hash(encoder.encode(quote.quote)) !== quote.quote_sha256) return invalid();
  }
}

const sortedUnique = (entries: string[]) => [...new Set(entries)].sort();

async function selectedDependency(result: Result, subject: V4Subject, signal?: AbortSignal): Promise<DependencyContext | null> {
  let feed: DependencyEvidenceFeed | null = null;
  do {
    const cursor = feed?.next_cursor ?? null;
    const page = await readDependencyEvidencePage(result.binding.scan_id, { limit: 100, cursor, signal });
    if (page.scan_ref.registry_revision !== result.binding.registry_revision || page.scan_ref.facts_hash !== result.binding.facts_hash
      || page.scan_ref.revision !== result.binding.project_revision) return invalid();
    feed = appendDependencyEvidencePage(feed, page, cursor);
    const item = page.items.find(row => row.resource_id === subject.resource_id);
    if (item) {
      if (item.version !== subject.version || item.name !== subject.component_name || item.ecosystem !== subject.ecosystem) return invalid();
      return {
        resource_id: item.resource_id,
        version: item.version,
        gaps: [...item.gaps].sort(),
        conflicts: item.conflicts.map(conflict => ({
          code: conflict.code, status: conflict.status,
          evidence_ids: sortedUnique([conflict.declaration,conflict.lock].flatMap(side => side?.evidence.map(ref => ref.evidence_id) ?? [])),
        })),
      };
    }
  } while (feed.next_cursor !== null);
  return null;
}

function expectedCatalog(context: V4PlanContext, view: MaterialClaims, dependency: DependencyContext | null) {
  const subject = context.subject;
  const claims = view.claims.filter(row => sameSubject(row.subject, subject));
  const claimIds = claims.map(row => row.claim_id).sort();
  const supportIds = claims.filter(row => row.state === 'SUPPORT').map(row => row.claim_id).sort();
  const source = view.source_observations.find(row => sameSubject(row.subject, subject));
  const materials = view.materials.filter(row => sameSubject(row.subject, subject));
  const reasons = new Set(Object.values(context.advice_reasons).flat());
  const counters = new Set(context.counter_evidence_codes);
  const states = Object.values(context.claim_states);
  const strong = reasons.has('COPYLEFT_SOURCE_DISCLOSURE_REVIEW_REQUIRED');
  const weak = reasons.has('WEAK_COPYLEFT_FILE_SCOPE_REVIEW_REQUIRED');
  const entries: V4PlanContext['action_catalog'] = [];
  const add = (kind: ActionKind, allowed: boolean, required: boolean, basis = claimIds) => {
    if (allowed) entries.push({ action_kind: kind, basis_ids: basis, required });
  };
  add('VERIFY_PERMISSIVE_OBLIGATIONS',
    permissive.has(context.declared_spdx) && supportIds.length > 0 && !states.some(state => state === 'UNKNOWN' || state === 'COUNTER_EVIDENCE')
    && ![...counters].some(code => code !== 'NOTICE_REQUIRES_REVIEW') && !strong && !weak
    && !materials.some(item => copyleft.has(item.text_license)), false, supportIds);
  add('RESOLVE_SPDX_TEXT_CONFLICT', counters.has('SPDX_TEXT_CONFLICT'), true);
  add('REVIEW_STRONG_COPYLEFT_DISCLOSURE', strong, true);
  add('REVIEW_WEAK_COPYLEFT_FILE_SCOPE', weak, true);
  add('REVIEW_APACHE_NOTICE_SECTION_4D', context.declared_spdx === 'Apache-2.0' &&
    (reasons.has('NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW') || reasons.has('NOTICE_REQUIRES_REVIEW')
      || counters.has('NOTICE_REQUIRES_REVIEW')), true, source ? [source.source_observation_id] : claimIds);
  add('SUPPLY_MISSING_LICENSE_MATERIAL', context.incremental_impact_summary.mode === 'INITIAL_RESULT'
    || !materials.some(item => /^LICEN[CS]E(?:\.|$)/i.test(item.filename)) || reasons.has('MISSING_LICENSE_MATERIAL'), true);
  add('VERIFY_UNESTABLISHED_RELEASE_SOURCE', context.source_binding === 'NOT_ESTABLISHED', false);
  add('RESOLVE_DEPENDENCY_VERSION_CONFLICT', !!dependency?.conflicts.some(item => item.code === 'lock_version_conflict'), false, [subject.resource_id]);
  add('PIN_EXACT_DEPENDENCY_VERSION', !!dependency?.gaps.includes('version_unavailable'), false, [subject.resource_id]);
  const missing = Object.entries(context.usage).filter(([,value]) => value === null).map(([key]) => 'usage:' + key).sort();
  add('CONFIRM_UNKNOWN_USAGE_FIELD', missing.length > 0, false, missing);
  return entries;
}

function prefixBytes(bytes: Uint8Array<ArrayBuffer>): { bytes: Uint8Array<ArrayBuffer>; quote: string } {
  const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
  let end = Math.min(bytes.length, 300);
  for (; end > 0; end--) {
    const portion = bytes.subarray(0, end);
    try { return { bytes: portion, quote: decoder.decode(portion) }; }
    catch { /* A UTF-8 scalar may straddle the byte boundary. */ }
  }
  return invalid();
}

export async function verifyV4PlanAnchor(value: V4PlanEnvelope & { source_refs: {material_id:string;source_sha256:string;byte_count:number}[] },
                                         assessment: Assessment, result: Result,
                                         scan: Scan | undefined, signal?: AbortSignal) {
  const context = value.context;
  const subject = context.subject;
  const resource = scan?.resources.find(row => row.id === subject.resource_id && row.version === subject.version);
  if (!scan || scan.id !== result.binding.scan_id || !resource || resource.name !== subject.component_name
    || resource.ecosystem !== subject.ecosystem) return invalid();
  const view = await readMaterialClaims(assessment, result, scan.declarationSnapshot, signal);
  const declaration = view.declaration_observations.find(row => sameSubject(row.subject, subject));
  const advice = view.advice.filter(row => sameSubject(row.subject, subject));
  const claims = view.claims.filter(row => sameSubject(row.subject, subject));
  const materials = view.materials.filter(row => sameSubject(row.subject, subject) && context.material_ids.includes(row.material_id));
  const source = view.source_observations.find(row => sameSubject(row.subject, subject));
  const changes = view.incremental_impact.changed_claims.filter(row => sameSubject(row.subject, subject));
  if (view.view_id !== value.material_claims_view_id || declaration?.expression !== context.declared_spdx
    || advice.length !== 3 || !advice.every(row => row.state === context.claim_states[row.usage as ClaimUse]
      && same(row.reasons, context.advice_reasons[row.usage as ClaimUse]))
    || !same([...new Set(claims.flatMap(row => row.counter_evidence.map(item => item.code)))].sort(), context.counter_evidence_codes)
    || (source?.notice_status ?? null) !== context.notice_status
    || context.incremental_impact_summary.mode !== view.incremental_impact.mode
    || !same(context.incremental_impact_summary.changed_claims, changes)) return invalid();

  const targetMaterials = view.materials.filter(row => sameSubject(row.subject, subject));
  const binding = targetMaterials.some(row => row.source_binding === 'PINNED_RELEASE_MATCH') ? 'PINNED_RELEASE_MATCH' : 'NOT_ESTABLISHED';
  if (context.source_binding !== binding || value.source_refs.length !== materials.length || !value.source_refs.every(ref =>
    materials.some(row => row.material_id === ref.material_id && row.source_sha256 === ref.source_sha256 && row.byte_count === ref.byte_count))) return invalid();

  const encoder = new TextEncoder();
  const expectedQuotes: V4Quote[] = [];
  for (const clause of [...materials].sort((a,b) => a.material_id < b.material_id ? -1 : a.material_id > b.material_id ? 1 : 0)
    .flatMap(row => row.clauses).slice(0,24)) {
    const prefix = prefixBytes(encoder.encode(clause.quote));
    const byte_end = clause.byte_start + prefix.bytes.length;
    const identity = [clause.material_id, clause.clause_id, clause.kind, clause.byte_start, byte_end];
    expectedQuotes.push({
      quote_id: 'p2quote_' + await v4Hash(encoder.encode(canonical(identity))), material_id: clause.material_id,
      clause_id: clause.clause_id, kind: clause.kind, quote: prefix.quote, quote_sha256: await v4Hash(prefix.bytes),
      byte_start: clause.byte_start, byte_end,
    });
  }
  if (!same(context.quote_catalog, expectedQuotes)) return invalid();
  const dependency = await selectedDependency(result, subject, signal);
  if (!same(context.dependency_conflicts, dependency) || !same(context.action_catalog, expectedCatalog(context, view, dependency))) return invalid();
}
