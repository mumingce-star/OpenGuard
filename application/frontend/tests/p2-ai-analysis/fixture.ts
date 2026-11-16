import { makeFixture } from '../bound-advice-maincard-corrected-fixture/fixture';
import type { P2AiAnalysis } from '../../src/services/p2Ai';
import type { Result } from '../../src/services/p2';
export const CLASSIFICATION='SYNTHETIC_TEST_ONLY_NOT_REAL_MODEL_OR_LICENSE';
export function fixture(suffix='A'){
 const f=makeFixture();f.assessment.id+='_'+suffix;f.assessment.scan_id+='_'+suffix;f.binding.assessment_id=f.assessment.id;f.binding.scan_id=f.assessment.scan_id;f.scan.id=f.assessment.scan_id;
 for(const r of [f.result,f.newer]){r.result_id+='_'+suffix;r.binding={...f.binding};r.material_ids=['mat_ai_'+suffix];r.resources[0].material_ids=[...r.material_ids];}
 f.newer.previous_result_id=f.result.result_id;
 return f;
}
export function record(r:Result,key='synthetic_saved_request',failed=false):P2AiAnalysis{
 return {schema_version:'openguard-p2-ai-analysis/1',analysis_id:'p2ai_'+r.result_id+'_'+key,analysis_sha256:'1'.repeat(64),status:failed?'failed':'succeeded',error_code:failed?'synthetic_provider_unavailable':null,
  result_id:r.result_id,result_revision:r.revision,result_sha256:r.result_sha256,binding:{...r.binding},previous_result_id:r.previous_result_id,previous_result_sha256:r.previous_result_id?'e'.repeat(64):null,idempotency_key:key,
  model:{name:'qwen3:SYNTHETIC_TEST_ONLY',digest:'2'.repeat(64),runtime:'SYNTHETIC_TEST_ONLY',prompt_version:'synthetic/1'},input_sha256:'3'.repeat(64),created_at:'2026-10-23T00:00:00Z',model_calls:1,
  metrics:{elapsed_ms:1,prompt_eval_count:10,eval_count:20,total_duration:1000000},source_refs:r.material_ids.map(material_id=>({material_id,subject:{...r.resources[0].subject},source_sha256:'4'.repeat(64),byte_count:64,source_level:'user_supplied_unverified',verification_state:'pending'})),
  clauses:failed?[]:[{material_id:r.material_ids[0],quote:'SYNTHETIC_TEST_ONLY 原文',start:0,end:[...'SYNTHETIC_TEST_ONLY 原文'].length,category:'condition'}],
  actions:failed?[]:[{text:'SYNTHETIC_TEST_ONLY：核对本版实际交付范围并保留准确原文。',source_material_ids:[r.material_ids[0]],claim_level:'verification_action_only'}],
  changes:failed||!r.previous_result_id?[]:[{field:'material_ids',before:[],after:[...r.material_ids],explanation:'SYNTHETIC_TEST_ONLY：本版新增材料，适用范围仍待核对。'}],
  limitations:['SYNTHETIC_TEST_ONLY：来源和适用范围尚未完成正式接纳。'],formal_effect:'none',usage_assumption:'DEMO_USAGE_ASSUMPTION',data_scope:'TEST_ONLY',quote_index_unit:'unicode_code_point'};
}
