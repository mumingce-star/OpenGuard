import type { Assessment } from './assessments';
import { accountRequestOptions, handleAccountResponse } from './auth';
export interface TierRequirement {requirement_id:string;category:string;label:string;name:string;status:string;critical:boolean;resource_ids:string[];item_ids:string[];formal_effect:'none';}
export interface TierQuestion {question_id:string;question_code:string;text:string;item_ids:string[];resource_ids:string[];why_user_only:string;current_answer_status:string;input_available:boolean;}
export interface TierRoute {item_id:string;name:string;resource_ids:string[];why:string;resolution_routes:string[];primary_owner:string;}
export interface TierView {schema_version:string;scan_id:string;assessment_id:string;assessment_version:number;facts_hash:string;usage_hash:string;rule_version:string;ai_aggregate_id:string;current_level:string;data_scope:'OWNER'|'TEST_ONLY';formal_effect:'none';level_states:{L1:string;L2:string;L3:string};view_digest:string;
 evidence_summary:{accepted_human_items:number;remaining_human_items:number;automatic_public_status:string;local_material_capability:string};
 upgrade_plan:{upgrade_to_l2:{user_fact_questions:TierQuestion[];local_material_requirements:TierRoute[];automatic_public_actions:TierRoute[];parser_actions:TierRoute[];system_limit_actions:TierRoute[];unique_route_items:number;unique_route_resources:number;route_counts_are_overlapping:boolean};upgrade_to_l3:{open_critical_requirements:TierRequirement[];category_counts:Record<string,number>;open_requirement_count:number;unique_resource_count:number}};requirements:TierRequirement[];provenance:{derived_snapshot_id:string|null};}
export function validateTier(value:unknown,a:Assessment):TierView {
 const v=value as TierView;
 if(!v||v.schema_version!=='openguard-assessment-tier/1'||v.formal_effect!=='none'||!['OWNER','TEST_ONLY'].includes(v.data_scope)||!['L1','L2','L3','NOT_READY'].includes(v.current_level)||v.scan_id!==a.scan_id||v.assessment_id!==a.id||v.assessment_version!==a.version||v.facts_hash!==a.facts_hash||v.usage_hash!==(a as Assessment&{usage_hash:string}).usage_hash||v.rule_version!==a.rule_version||! /^[a-f0-9]{64}$/.test(v.view_digest)||! /^[a-f0-9]{64}$/.test(v.ai_aggregate_id))throw Error('TIER_FIXED_IDENTITY');
 if(!v.provenance||!(v.provenance.derived_snapshot_id===null||typeof v.provenance.derived_snapshot_id==='string'))throw Error('TIER_SOURCE_IDENTITY');
 if(!v.level_states||!Array.isArray(v.requirements)||!v.upgrade_plan?.upgrade_to_l2||!v.evidence_summary)throw Error('TIER_SCHEMA');
 const q=v.upgrade_plan.upgrade_to_l2,u=v.upgrade_plan.upgrade_to_l3;
 if(![q.user_fact_questions,q.local_material_requirements,q.automatic_public_actions,q.parser_actions,q.system_limit_actions,u?.open_critical_requirements].every(Array.isArray))throw Error('TIER_SCHEMA');
 if(q.route_counts_are_overlapping!==true||v.requirements.some(r=>r.formal_effect!=='none')||new Set(v.requirements.map(r=>r.requirement_id)).size!==v.requirements.length)throw Error('TIER_REQUIREMENTS');
 const open=v.requirements.filter(r=>r.critical&&!['SATISFIED','NOT_APPLICABLE'].includes(r.status));
 if(u.open_requirement_count!==open.length||u.unique_resource_count!==new Set(open.flatMap(r=>r.resource_ids)).size||JSON.stringify(open.map(r=>r.requirement_id).sort())!==JSON.stringify(u.open_critical_requirements.map(r=>r.requirement_id).sort()))throw Error('TIER_COUNTS');
 if(v.current_level==='L3'&&(open.length||v.level_states.L3!=='COMPLETE'))throw Error('TIER_CLOSURE');
 if(v.current_level==='L2'&&(!v.evidence_summary.accepted_human_items||!['IN_PROGRESS','COMPLETE'].includes(v.level_states.L2)))throw Error('TIER_CONSUMPTION');
 return v;
}
export async function readAssessmentTier(a:Assessment):Promise<TierView> {
 const response=await fetch(`/api/v1/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/assessment-tier?assessment_version=${a.version}`,accountRequestOptions({method:'GET',cache:'no-store'}));
 handleAccountResponse(response.status);
 if(!response.ok)throw Error('TIER_READ_FAILED');return validateTier(await response.json(),a);
}

export function tierAllowsDerived(tier:TierView|null,snapshotId:string):boolean {return !tier||tier.provenance.derived_snapshot_id===snapshotId;}
