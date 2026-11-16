import { makeFixture, TARGET, EVIDENCE } from '../bound-advice-maincard-corrected-fixture/fixture';
import type { Material, Result } from '../../src/services/p2';
export const classification='SYNTHETIC_TEST_ONLY';
export {TARGET,EVIDENCE};
export function fixture(){
 const f=makeFixture();
 f.result.material_ids=['mat_team_1'];f.result.resources[0].material_ids=['mat_team_1'];f.result.resources[0].state='pending';f.result.state='pending';
 f.newer.material_ids=['mat_team_1','mat_team_2'];f.newer.resources[0].material_ids=['mat_team_1','mat_team_2'];f.newer.resources[0].state='pending';f.newer.state='pending';f.newer.recomputed_resource_ids=[TARGET];f.newer.reused_resource_ids=[f.newer.resources[1].subject.resource_id];
 function material(id:string,name:string):Material{return {material_id:id,revision:1,binding:{...f.binding},subject:{...f.result.resources[0].subject},evidence_ids:[EVIDENCE],filename:name,source_sha256:'1'.repeat(64),byte_count:32,completeness:'FULL_TEXT_CLAIMED',parse_status:'text_observed',adoption_status:'adopted_as_unverified_observation',verification_state:'pending',source_level:'user_supplied_unverified',formal_effect:'none',data_scope:'TEST_ONLY'};}
 const materials:Record<string,Material>={mat_team_1:material('mat_team_1','LICENSE'),mat_team_2:material('mat_team_2','NOTICE')};
 const other=structuredClone(f);other.assessment.id+='B';other.assessment.version=2;other.binding.assessment_id=other.assessment.id;other.binding.assessment_version=2;
 for(const r of [other.result,other.newer]){r.result_id+='B';r.binding={...other.binding};r.material_ids=[];r.resources.forEach(row=>row.material_ids=[]);}
 other.result.previous_result_id=null;other.newer.previous_result_id=other.result.result_id;
 return {base:f,other,materials};
}
export type Fixture=ReturnType<typeof fixture>;
export type View='A'|'B';
export type ResponseOptions={previous?:'binding'|'revision'|'scope'|'missing';holdPrevious?:boolean;holdMaterial?:boolean;holdPost?:boolean;initial?:'r1'|'r2'};
export function summary(r:Result){return {summary_id:r.companion_summary_id,result_id:r.result_id,result_revision:r.revision,result_sha256:r.result_sha256,binding:r.binding,material_ids:r.material_ids,answer_ids:r.answer_ids,state:r.state,resource_states:Object.fromEntries(r.resources.map(row=>[row.subject.resource_id,row.state])),formal_effect:'none',report_kind:'P2_COMPANION_NOT_FORMAL_REPORT'};}
