import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
// SYNTHETIC_TEST_ONLY: contract fixtures, not backend or source-authentication evidence.
const sha='a'.repeat(64), uses=['commercial','modified','distributed','network_service','training','redistributed_assets','source_disclosure'];
const usage=Object.fromEntries(uses.map(k=>[k,null]));
const a={id:'asm_team',scan_id:'scn_team',version:1,facts_hash:sha,usage_hash:sha,rule_version:'rules/team',usage:{preset:'unknown',...usage},resource_ids:['cmp_a','cmp_b'],evidence_ids:['evd_a','evd_b']};
const b={scan_id:a.scan_id,assessment_id:a.id,assessment_version:1,registry_revision:1,project_revision:'SYNTHETIC_TEST_ONLY',facts_hash:sha,usage_hash:sha,rule_version:a.rule_version,assessment_sha256:sha};
function fixture(){return {schema_version:'openguard-p2-result/1',algorithm_version:'p2-bound-candidate/1',result_id:'p2res_team',revision:2,previous_result_id:'p2res_old',result_sha256:sha,binding:{...b},data_scope:'TEST_ONLY',computation:'DETERMINISTIC_P2B',publication_status:'succeeded',formal_effect:'none',model_calls:0,state:'pending',created_at:'2026-10-22T00:00:00Z',usage:{...usage},resources:['a','b'].map(k=>({subject:{resource_id:'cmp_'+k,version:'1.0.0'},resource_kind:'component',state:'pending',verification_state:'candidate_only',scope:'unknown',evidence_ids:['evd_'+k],evidence_source_hashes:{['evd_'+k]:sha},material_ids:k==='a'?['mat_a']:[],answer_ids:k==='a'?['ans_a']:[],gaps:['SYNTHETIC_TEST_ONLY'],advice:uses.map(u=>({usage:u,saved_value:null,selection:'UNKNOWN',state:'unknown',scope:'RESOURCE',conditions:[],gaps:[],basis_evidence_ids:[],rule_ids:[]})),user_assertions:{},inherited_local_support:false,inherited_support_source:'PARENT_ASSESSMENT_NOT_NEW_VALUE'})),questions:[],material_ids:['mat_a'],answer_ids:['ans_a'],recomputed_resource_ids:['cmp_a'],reused_resource_ids:['cmp_b'],companion_summary_id:'sum_team'};}
const load=()=>runtime({VITE_P2_WORKBENCH:'1',VITE_ACCOUNT_AUTH:'0'}).load('services/p2.ts');
test('complete saved-reference and recomputed/reused partitions remain accepted',()=>assert.equal(load().validateResult(fixture(),a,b).result_id,'p2res_team'));
for(const [label,mutate] of [
 ['orphan global material',v=>v.material_ids.push('mat_orphan')],
 ['orphan global answer',v=>v.answer_ids.push('ans_orphan')],
 ['missing partition resource',v=>v.reused_resource_ids=[]],
 ['global material missing resource reference',v=>v.material_ids=[]],
 ['global answer missing resource reference',v=>v.answer_ids=[]],
 ['overlapping partition',v=>v.reused_resource_ids=['cmp_a','cmp_b']],
 ['unknown partition resource',v=>v.reused_resource_ids=['cmp_other']],
 ['duplicate resource reference',v=>v.resources[0].material_ids.push('mat_a')],
]) test('rejects '+label,()=>{const v=fixture();mutate(v);assert.throws(()=>load().validateResult(v,a,b),/P2/);});
test('references may cover multiple resources for one Answer without duplicate global IDs',()=>{const v=fixture();v.resources[1].answer_ids=['ans_a'];assert.equal(load().validateResult(v,a,b).answer_ids.length,1);});
