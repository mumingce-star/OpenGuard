import { request } from './scans';
import type { P2Advice, P2Binding, P2ResourceResult, P2Result, P2ResultIndex, P2State, P2Usage } from '../types/p2Advice';

const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string');
const id = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(value);
const hash = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const integer = (value: unknown, minimum: number): value is number => Number.isInteger(value) && Number(value) >= minimum;
const oneOf = <T extends string>(value: unknown, values: readonly T[]): value is T => typeof value === 'string' && values.includes(value as T);
const fail = (): never => { throw new Error('P2 独立结果与当前接口契约或评估版本不一致，未展示该建议。'); };
const usages = ['commercial', 'modified', 'distributed', 'network_service', 'training', 'redistributed_assets', 'source_disclosure'] as const;
const states = ['candidate', 'unknown', 'pending', 'partial'] as const;
const unique = (values: string[]) => new Set(values).size === values.length;

function binding(value: unknown, scanId: string, assessmentId: string, version: number): P2Binding {
  if (!object(value) || value.scan_id !== scanId || value.assessment_id !== assessmentId || value.assessment_version !== version ||
    !integer(value.registry_revision, 1) || !(value.project_revision === null || typeof value.project_revision === 'string') ||
    !hash(value.facts_hash) || !hash(value.usage_hash) || !hash(value.assessment_sha256) ||
    typeof value.rule_version !== 'string' || !value.rule_version) return fail();
  return value as unknown as P2Binding;
}

export function sameBinding(a: P2Binding, b: P2Binding): boolean {
  return a.scan_id === b.scan_id && a.assessment_id === b.assessment_id && a.assessment_version === b.assessment_version &&
    a.registry_revision === b.registry_revision && a.project_revision === b.project_revision &&
    a.facts_hash === b.facts_hash && a.usage_hash === b.usage_hash && a.rule_version === b.rule_version &&
    a.assessment_sha256 === b.assessment_sha256;
}

export function validateP2Index(value: unknown): P2ResultIndex {
  if (!object(value) || !(value.head_result_id === null || id(value.head_result_id)) ||
    !integer(value.head_revision, 0) || !strings(value.result_ids) || !value.result_ids.every(id) || typeof value.has_more !== 'boolean' ||
    (value.head_result_id === null) !== (value.head_revision === 0) ||
    (value.head_result_id === null && value.result_ids.length !== 0)) return fail();
  return value as unknown as P2ResultIndex;
}

function validateAdvice(value: unknown): value is P2Advice {
  return object(value) && oneOf(value.usage, usages) &&
    (value.saved_value === null || typeof value.saved_value === 'boolean') &&
    oneOf(value.selection, ['SELECTED', 'NOT_SELECTED', 'UNKNOWN']) &&
    oneOf(value.state, ['conditional_candidate', 'unknown', 'not_selected']) &&
    value.scope === 'RESOURCE' && strings(value.conditions) && strings(value.gaps) &&
    strings(value.basis_evidence_ids) && value.basis_evidence_ids.every(id) && strings(value.rule_ids);
}

function validateResource(value: unknown): value is P2ResourceResult {
  if (!object(value) || !object(value.subject) || !id(value.subject.resource_id) ||
    !(value.subject.version === null || typeof value.subject.version === 'string') ||
    !oneOf(value.resource_kind, ['component', 'ai_asset']) || !oneOf(value.state, states) ||
    value.verification_state !== 'candidate_only' || typeof value.scope !== 'string' ||
    !strings(value.evidence_ids) || !value.evidence_ids.every(id) || !object(value.evidence_source_hashes) ||
    !Object.values(value.evidence_source_hashes).every(hash) ||
    !strings(value.material_ids) || !value.material_ids.every(id) ||
    !strings(value.answer_ids) || !value.answer_ids.every(id) || !strings(value.gaps) ||
    !Array.isArray(value.advice) || !value.advice.every(validateAdvice) || !object(value.user_assertions) ||
    typeof value.inherited_local_support !== 'boolean' || value.inherited_support_source !== 'PARENT_ASSESSMENT_NOT_NEW_VALUE') return false;
  return true;
}

export function validateP2Result(value: unknown, expected: P2Binding): P2Result {
  if (!object(value) || value.schema_version !== 'openguard-p2-result/1' || value.algorithm_version !== 'p2-bound-candidate/1' ||
    !id(value.result_id) || !integer(value.revision, 1) || !(value.previous_result_id === null || id(value.previous_result_id)) ||
    !hash(value.result_sha256) || !sameBinding(binding(value.binding, expected.scan_id, expected.assessment_id, expected.assessment_version), expected) ||
    !oneOf(value.data_scope, ['OWNER', 'TEST_ONLY']) || value.computation !== 'DETERMINISTIC_P2B' ||
    value.publication_status !== 'succeeded' || value.formal_effect !== 'none' || value.model_calls !== 0 ||
    !oneOf(value.state, states) || typeof value.created_at !== 'string' || !Number.isFinite(Date.parse(value.created_at)) ||
    !object(value.usage) || !Object.entries(value.usage).every(([key, saved]) => usages.includes(key as P2Usage) && (saved === null || typeof saved === 'boolean')) ||
    !Array.isArray(value.resources) || !value.resources.every(validateResource) ||
    !Array.isArray(value.questions) || !value.questions.every(question => object(question) && id(question.question_id) &&
      oneOf(question.question_code, ['DELIVERY_SCOPE_FOR_RESOURCES', 'OBLIGATION_FULFILLMENT_IN_DELIVERY']) &&
      question.origin === 'DETERMINISTIC_P2_NOT_R6_AGGREGATE' && question.scope_rule === 'EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN' &&
      Array.isArray(question.subjects) && question.subjects.every(subject => object(subject) && id(subject.resource_id) &&
        (subject.version === null || typeof subject.version === 'string') && (value.resources as unknown[]).some(resource =>
          object(resource) && object(resource.subject) && resource.subject.resource_id === subject.resource_id && resource.subject.version === subject.version)) &&
      strings(question.options) && question.options.length > 0 && question.options.every(option =>
        (question.question_code === 'DELIVERY_SCOPE_FOR_RESOURCES' ? ['YES_INCLUDE','NO_EXCLUDE','NOT_DECIDED'] : ['FULFILLED','NOT_FULFILLED','NOT_DELIVERED_YET','UNKNOWN']).includes(option))) ||
    !strings(value.material_ids) || !strings(value.answer_ids) || !strings(value.recomputed_resource_ids) ||
    !strings(value.reused_resource_ids) || !id(value.companion_summary_id)) return fail();
  const result = value as unknown as P2Result;
  const resourceIds = result.resources.map(resource => resource.subject.resource_id);
  const resourceSet = new Set(resourceIds);
  const materialSet = new Set(result.material_ids);
  const answerSet = new Set(result.answer_ids);
  const linkedMaterials = new Set(result.resources.flatMap(resource => resource.material_ids));
  const linkedAnswers = new Set(result.resources.flatMap(resource => resource.answer_ids));
  const recomputed = new Set(result.recomputed_resource_ids);
  const reused = new Set(result.reused_resource_ids);
  // These are references to saved backend objects, not new frontend evidence or conclusions.
  if (!unique(resourceIds) || !unique(result.material_ids) || !unique(result.answer_ids) ||
    !unique(result.recomputed_resource_ids) || !unique(result.reused_resource_ids) ||
    linkedMaterials.size !== materialSet.size || linkedAnswers.size !== answerSet.size ||
    result.recomputed_resource_ids.some(id => !resourceSet.has(id) || reused.has(id)) ||
    result.reused_resource_ids.some(id => !resourceSet.has(id)) ||
    recomputed.size + reused.size !== resourceSet.size ||
    result.resources.some(resource => {
      const evidence = new Set(resource.evidence_ids);
      return !unique(resource.evidence_ids) || !unique(resource.material_ids) || !unique(resource.answer_ids) ||
        Object.keys(resource.evidence_source_hashes).some(id => !evidence.has(id)) ||
        resource.material_ids.some(id => !materialSet.has(id)) ||
        resource.answer_ids.some(id => !answerSet.has(id)) ||
        resource.advice.some(advice => !unique(advice.basis_evidence_ids) || advice.basis_evidence_ids.some(id => !evidence.has(id)));
    })) return fail();
  return result;
}

const prefix = (scanId: string, assessmentId: string) => '/scans/' + encodeURIComponent(scanId) + '/assessments/' + encodeURIComponent(assessmentId) + '/p2';

export async function readP2Binding(scanId: string, assessmentId: string, version: number, signal?: AbortSignal) {
  if (!id(scanId) || !id(assessmentId) || !integer(version, 1)) return fail();
  return binding(await request(prefix(scanId, assessmentId) + '/binding', {}, signal), scanId, assessmentId, version);
}
export async function readP2Index(expected: P2Binding, offset = 0, signal?: AbortSignal) {
  if (!integer(offset, 0) || offset > 10000) return fail();
  return validateP2Index(await request(prefix(expected.scan_id, expected.assessment_id) + '/results?assessment_version=' + expected.assessment_version + '&offset=' + offset, {}, signal));
}
export async function readP2Result(expected: P2Binding, resultId: string, revision?: number, signal?: AbortSignal) {
  if (!id(resultId) || (revision !== undefined && !integer(revision, 1))) return fail();
  const result = validateP2Result(await request(prefix(expected.scan_id, expected.assessment_id) + '/results/' + encodeURIComponent(resultId) + '?assessment_version=' + expected.assessment_version, {}, signal), expected);
  if (result.result_id !== resultId || (revision !== undefined && result.revision !== revision)) return fail();
  return result;
}

export async function readP2Advice(scanId: string, assessmentId: string, assessmentVersion: number, signal?: AbortSignal): Promise<P2Result | null> {
  if (!id(scanId) || !id(assessmentId) || !integer(assessmentVersion, 1)) return fail();
  const path = prefix(scanId, assessmentId);
  const expected = binding(await request(path + '/binding', {}, signal), scanId, assessmentId, assessmentVersion);
  const index = validateP2Index(await request(path + '/results?assessment_version=' + assessmentVersion, {}, signal));
  if (!index.head_result_id) return null;
  const result = validateP2Result(await request(path + '/results/' + encodeURIComponent(index.head_result_id) + '?assessment_version=' + assessmentVersion, {}, signal), expected);
  if (result.result_id !== index.head_result_id || result.revision !== index.head_revision) return fail();
  return result;
}

export const p2StateLabels: Record<P2State, string> = {
  candidate: '条件候选，待核验', unknown: '未知，证据不足', pending: '待核验', partial: '部分候选与缺口并存',
};
