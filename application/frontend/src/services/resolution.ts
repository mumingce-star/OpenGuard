import { request } from './scans';
import type { Usage, usageFields } from './assessments';

type Field = keyof typeof usageFields;
export type BriefObligation = {id:string;requirement:string;trigger?:string;fulfillment:string;action?:string;rule_id?:string;rule_version?:string;resource_ids?:string[]};
export function presentObligation(o:BriefObligation) {
 // Display translation of one exact frozen rule, never inferred from prose or severity.
 if (o.rule_id==='LIC-MIT-NOTICE'&&o.rule_version==='1.0.0'&&o.action==='retain_license_notice'
  &&o.requirement==='Preserve the copyright and permission notice with the distributed material.'
  &&o.trigger==='Verified MIT-licensed material is included in a distribution')
  return {requirement:'随交付材料保留版权声明与许可声明',trigger:'分发已核验的 MIT 许可材料时'};
 return {requirement:o.requirement,trigger:o.trigger};
}
export function relevantUsage(preset: Usage['preset']): Field[] {
 const order: Record<Usage['preset'], Field[]> = {
  personal: ['commercial', 'training'], internal: ['commercial', 'modified'],
  open_source: ['distributed', 'source_disclosure'], closed_source: ['commercial', 'distributed'],
  service: ['network_service', 'commercial'], unknown: ['commercial', 'distributed'],
 };
 return order[preset];
}
export type Gap = { code: string; owner: 'system'|'user'|'reviewer'; title?: string; action: string; safe_automation?:boolean; resource_ids?: string[]; affected_dimensions?: string[]; raw?: {text:string}[] };
export type Observation = { resource_id: string; name: string; version: string; source_locator: string; content_hash: string|null; material_id: string; text?: unknown;
 authorization_verified: false; review_status: 'pending'; atomic_facts: { version_located: boolean; document_acquired: boolean; content_matched: boolean; applicable_relation_checked: false; formal_policy_covered: false } };
export type Brief = { formal: false; display_version: string; scan_id: string; assessment_id: string; assessment_version: number;
 facts_hash: string; title: string; permission_state: 'unknown'|'partial'|'conditional'|'restricted'; notice: string;
 local_results: {resource_id?:string; name:string; version?:string|null; supported_permission:boolean; conditions:string[]; next_steps:string[]; license_expression:string|null}[];
 dimensions: { title:string; conditions:string[]; restrictions:string[] }[]; obligations: BriefObligation[];
 gaps: Gap[]; resolution_observations: Observation[]; resolution_snapshot_id?:string; resolution_snapshot_hash?:string;
 resolution_model?: {status:string;calls:number;reason?:string;output?:{formal:false;candidates:{quote:string;action:string;review_status:'pending';authorization_verified:false}[];
 conflict_clues?:{resource_id:string;left_material_id:string;right_material_id:string;left_quote:string;right_quote:string;kind:string;review_status:'pending';producer_type:'model';authorization_verified:false}[]}}|null;
 resolution_cases?: {resource_id:string;matches:{case_id:string;explanation:string;formal:false;authorization_transfer:false}[];invalidations?:{case_id:string;reason:string}[];corpus_status:string}[];
 resolution_attempts?: {kind:string;status:string;requests?:number}[] };
export type ResolutionJob = { job_id:string; request_key:string; version:number; status:'queued'|'running'|'completed'|'failed'|'cancelled'|'interrupted';
 snapshot_id:string|null; created_at?:string; error?:string; binding:{scan_id:string;assessment_id:string;assessment_version:number;facts_hash:string} };
const obj = (x:unknown):x is Record<string,unknown> => !!x && typeof x==='object' && !Array.isArray(x);
const strings = (x:unknown):x is string[] => Array.isArray(x) && x.every(y=>typeof y==='string');
const fail = ():never => { throw new Error('补证数据与当前固定评估不匹配；不展示为成功。'); };
export function validateBrief(x:unknown, sid:string, aid:string, version:number):Brief {
 if (!obj(x) || x.formal!==false || x.display_version!=='decision-brief/1' || x.scan_id!==sid || x.assessment_id!==aid || x.assessment_version!==version
  || typeof x.facts_hash!=='string' || !/^[a-f0-9]{64}$/.test(x.facts_hash) || !['unknown','partial','conditional','restricted'].includes(String(x.permission_state))
  || typeof x.title!=='string' || typeof x.notice!=='string' || !Array.isArray(x.gaps) || !x.gaps.every(g=>obj(g) && typeof g.code==='string' && ['system','user','reviewer'].includes(String(g.owner)))
  || (x.resolution_snapshot_id!==undefined && (typeof x.resolution_snapshot_id!=='string' || typeof x.resolution_snapshot_hash!=='string' || !/^[a-f0-9]{64}$/.test(x.resolution_snapshot_hash)))
  || !Array.isArray(x.obligations) || !Array.isArray(x.dimensions) || !x.dimensions.every(d=>obj(d)&&typeof d.title==='string'&&strings(d.conditions)&&strings(d.restrictions))
  || !Array.isArray(x.local_results) || !x.local_results.every(r=>obj(r)&&typeof r.name==='string'&&typeof r.supported_permission==='boolean'&&strings(r.conditions)&&strings(r.next_steps))
  || !Array.isArray(x.resolution_observations) || !x.resolution_observations.every(o=>obj(o)&&typeof o.name==='string'&&typeof o.version==='string'&&o.authorization_verified===false&&o.review_status==='pending'&&obj(o.atomic_facts)&&o.atomic_facts.applicable_relation_checked===false&&o.atomic_facts.formal_policy_covered===false)) return fail();
 if (x.resolution_model!=null && (!obj(x.resolution_model)||typeof x.resolution_model.status!=='string'||!Number.isInteger(x.resolution_model.calls)
  || (x.resolution_model.output!==undefined&&(!obj(x.resolution_model.output)||x.resolution_model.output.formal!==false||!Array.isArray(x.resolution_model.output.candidates)
   || !x.resolution_model.output.candidates.every(c=>obj(c)&&typeof c.quote==='string'&&typeof c.action==='string'&&c.review_status==='pending'&&c.authorization_verified===false))))) return fail();
 if (obj(x.resolution_model)&&obj(x.resolution_model.output)&&x.resolution_model.output.conflict_clues!==undefined) {
  const clues=x.resolution_model.output.conflict_clues;
  if (!Array.isArray(clues)||clues.length>8||!clues.every(c=>obj(c)&&c.review_status==='pending'&&c.producer_type==='model'&&c.authorization_verified===false
   &&typeof c.resource_id==='string'&&typeof c.left_material_id==='string'&&typeof c.right_material_id==='string'&&c.left_material_id!==c.right_material_id
   &&typeof c.left_quote==='string'&&typeof c.right_quote==='string'&&['TEXT_DIFFERENCE','VERSION','SCOPE'].includes(String(c.kind)))) return fail();
 }
 if (x.resolution_cases!==undefined && (!Array.isArray(x.resolution_cases)||!x.resolution_cases.every(c=>obj(c)&&Array.isArray(c.matches)&&c.matches.every(m=>obj(m)&&m.formal===false&&m.authorization_transfer===false&&typeof m.explanation==='string')
  &&(c.invalidations===undefined||(Array.isArray(c.invalidations)&&c.invalidations.every(i=>obj(i)&&typeof i.case_id==='string'&&typeof i.reason==='string')))))) return fail();
 return x as Brief;
}
function job(x:unknown, sid:string, aid:string, version:number):ResolutionJob {
 if (!obj(x) || typeof x.job_id!=='string' || typeof x.request_key!=='string' || !Number.isInteger(x.version) || Number(x.version)<1 || !['queued','running','completed','failed','cancelled','interrupted'].includes(String(x.status))
  || !obj(x.binding) || x.binding.scan_id!==sid || x.binding.assessment_id!==aid || x.binding.assessment_version!==version || (x.status==='completed' && typeof x.snapshot_id!=='string')) return fail();
 return x as ResolutionJob;
}
const prefix=(sid:string)=>'/scans/'+encodeURIComponent(sid);
export async function readBrief(sid:string,aid:string,version:number,snapshot?:string,signal?:AbortSignal) {
 return validateBrief(await request(prefix(sid)+'/assessments/'+encodeURIComponent(aid)+'/decision-brief?assessment_version='+version+(snapshot?'&snapshot_id='+encodeURIComponent(snapshot):''),{},signal),sid,aid,version);
}
export async function readJobs(sid:string,aid:string,version:number,signal?:AbortSignal) {
 const value=await request(prefix(sid)+'/evidence-resolution/jobs?assessment_id='+encodeURIComponent(aid)+'&assessment_version='+version,{},signal);
 if (!obj(value)||!Array.isArray(value.items)) return fail();
 return value.items.map(x=>job(x,sid,aid,version));
}
export async function resolveLocal(sid:string,aid:string,version:number,factsHash:string,key:string,useModel:boolean) {
 return job(await request(prefix(sid)+'/evidence-resolution',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assessment_id:aid,assessment_version:version,expected_facts_hash:factsHash,request_key:key,use_model:useModel,allow_network:false})}),sid,aid,version);
}
export function snapshotUrl(sid:string,id:string) { return (import.meta.env.VITE_API_BASE_URL||'/api/v1').replace(/\/$/,'')+prefix(sid)+'/evidence-resolution/snapshots/'+encodeURIComponent(id); }
export async function cancelResolution(sid:string,aid:string,version:number,jobId:string,expectedVersion:number) {
 if (!Number.isInteger(expectedVersion)||expectedVersion<1) return fail();
 const value=job(await request(prefix(sid)+'/evidence-resolution/jobs/'+encodeURIComponent(jobId)+'/cancel',
  {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:expectedVersion})}),sid,aid,version);
 if (value.job_id!==jobId || value.status!=='cancelled' || value.version!==expectedVersion+1) return fail();
 return value;
}
