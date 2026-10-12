// P2 v1 is an independent, non-Formal result. These fields follow schemas/p2/contract-v1.schema.json.
export type P2Usage = 'commercial' | 'modified' | 'distributed' | 'network_service' | 'training' | 'redistributed_assets' | 'source_disclosure';
export type P2State = 'candidate' | 'unknown' | 'pending' | 'partial';

export interface P2Binding {
  scan_id: string;
  assessment_id: string;
  assessment_version: number;
  registry_revision: number;
  project_revision: string | null;
  facts_hash: string;
  usage_hash: string;
  rule_version: string;
  assessment_sha256: string;
}

export interface P2Advice {
  usage: P2Usage;
  saved_value: boolean | null;
  selection: 'SELECTED' | 'NOT_SELECTED' | 'UNKNOWN';
  state: 'conditional_candidate' | 'unknown' | 'not_selected';
  scope: 'RESOURCE';
  conditions: string[];
  gaps: string[];
  basis_evidence_ids: string[];
  rule_ids: string[];
}

export interface P2ResourceResult {
  subject: { resource_id: string; version: string | null };
  resource_kind: 'component' | 'ai_asset';
  state: P2State;
  verification_state: 'candidate_only';
  scope: string;
  evidence_ids: string[];
  evidence_source_hashes: Record<string, string>;
  material_ids: string[];
  answer_ids: string[];
  gaps: string[];
  advice: P2Advice[];
  user_assertions: Record<string, string>;
  inherited_local_support: boolean;
  inherited_support_source: 'PARENT_ASSESSMENT_NOT_NEW_VALUE';
}

export interface P2Result {
  schema_version: 'openguard-p2-result/1';
  algorithm_version: 'p2-bound-candidate/1';
  result_id: string;
  revision: number;
  previous_result_id: string | null;
  result_sha256: string;
  binding: P2Binding;
  data_scope: 'OWNER' | 'TEST_ONLY';
  computation: 'DETERMINISTIC_P2B';
  publication_status: 'succeeded';
  formal_effect: 'none';
  model_calls: 0;
  state: P2State;
  created_at: string;
  usage: Partial<Record<P2Usage, boolean | null>>;
  resources: P2ResourceResult[];
  questions: P2Question[];
  material_ids: string[];
  answer_ids: string[];
  recomputed_resource_ids: string[];
  reused_resource_ids: string[];
  companion_summary_id: string;
}

export interface P2ResultIndex {
  head_result_id: string | null;
  head_revision: number;
  result_ids: string[];
  has_more: boolean;
}

export type P2Subject = P2ResourceResult['subject'];
export type P2QuestionCode = 'DELIVERY_SCOPE_FOR_RESOURCES' | 'OBLIGATION_FULFILLMENT_IN_DELIVERY';
export type P2AnswerCode = 'YES_INCLUDE' | 'NO_EXCLUDE' | 'NOT_DECIDED' | 'FULFILLED' | 'NOT_FULFILLED' | 'NOT_DELIVERED_YET' | 'UNKNOWN';
export interface P2Question {
  question_id: string; question_code: P2QuestionCode;
  origin: 'DETERMINISTIC_P2_NOT_R6_AGGREGATE'; subjects: P2Subject[]; options: P2AnswerCode[];
  scope_rule: 'EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN';
}
export interface P2CreateRequest {
  binding: P2Binding; expected_revision: number; parent_result_id: string | null; idempotency_key: string;
}
export interface P2AnswerRequest extends P2CreateRequest {
  question_id: string; question_code: P2QuestionCode; answer_code: P2AnswerCode;
  subjects: P2Subject[]; evidence_ids: string[];
}
export interface P2MaterialRequest extends P2CreateRequest {
  subject: P2Subject; evidence_ids: string[]; filename: string; content_base64: string;
  source_sha256: string; source_description: string; completeness: 'FULL_TEXT_CLAIMED' | 'EXCERPT';
}
export interface P2Answer extends Omit<P2AnswerRequest, 'expected_revision' | 'parent_result_id' | 'idempotency_key'> {
  answer_id: string; revision: number; provenance: 'USER_ASSERTED'; formal_effect: 'none'; data_scope: 'OWNER' | 'TEST_ONLY';
}
export interface P2Material extends Omit<P2MaterialRequest, 'expected_revision' | 'parent_result_id' | 'idempotency_key' | 'content_base64' | 'source_description'> {
  material_id: string; revision: 1; byte_count: number; parse_status: 'text_observed';
  adoption_status: 'adopted_as_unverified_observation'; verification_state: 'pending';
  source_level: 'user_supplied_unverified'; formal_effect: 'none'; data_scope: 'OWNER' | 'TEST_ONLY';
}
export interface P2Summary {
  summary_id: string; result_id: string; result_revision: number; result_sha256: string;
  binding: P2Binding; material_ids: string[]; answer_ids: string[]; state: P2State;
  resource_states: Record<string, P2State>; formal_effect: 'none'; report_kind: 'P2_COMPANION_NOT_FORMAL_REPORT';
}
export interface P2Receipt { result: P2Result; answer: P2Answer | null; material: P2Material | null }
