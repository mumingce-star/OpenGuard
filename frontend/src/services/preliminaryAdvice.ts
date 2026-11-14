import { request } from './scans';
import { usageFields, type Assessment } from './assessments';
import { sameBinding, type Binding, type Result, type Subject, type Use } from './p2';

export type PreliminaryResource = {
 subject:Subject;name:string;state:'CONDITIONAL_TEXT_BASIS';recommendation:string;
 conditions:string[];limitations:string[];material_ids:string[];material_sha256:string[];
 evidence_ids:string[];source_urls:string[];rule_id:string;
};
export type PreliminaryUse = {
 usage:Use;saved_value:boolean|null;selection:'SELECTED'|'NOT_SELECTED'|'UNKNOWN';
 state:'CONDITIONAL_TEXT_BASIS'|'NO_SUPPORTED_BASIS'|'NOT_SELECTED'|'USAGE_UNDECLARED';
 summary:string;resources:PreliminaryResource[];uncovered_resource_ids:string[];
};
export type PreliminaryAdvice = {
 schema_version:'openguard-p2-preliminary-advice/1';rule_version:'mit-complete-text/1';
 recommendation_id:string;result_id:string;result_sha256:string;binding:Binding;data_scope:'OWNER'|'TEST_ONLY';
 source_profile_sha256:string|null;source_status:'CHECKED'|'NOT_CONFIGURED';scope:'RESOURCE_SUBSET';
 total_resources:number;supported_resource_ids:string[];uncovered_resource_ids:string[];
 advice:PreliminaryUse[];limitations:string[];formal_effect:'none';model_calls:0;applicability_review:'NOT_SIGNED';
};
const object=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown):v is string=>typeof v==='string'&&v.length>0;
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(text);
const unique=(v:unknown):v is string[]=>strings(v)&&new Set(v).size===v.length;
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const sameSet=(a:string[],b:string[])=>a.length===b.length&&a.every(x=>b.includes(x));
const fail=():never=>{throw Error('用途初评与当前结果的绑定不一致，未展示未经核对的建议。');};

export function validatePreliminaryAdvice(v:unknown,result:Result):PreliminaryAdvice {
 const all=result.resources.map(r=>r.subject.resource_id),uses=Object.keys(usageFields) as Use[];
 if(!object(v)||v.schema_version!=='openguard-p2-preliminary-advice/1'||v.rule_version!=='mit-complete-text/1'||!text(v.recommendation_id)||v.result_id!==result.result_id||v.result_sha256!==result.result_sha256||!object(v.binding)||!sameBinding(v.binding as Binding,result.binding)||v.data_scope!==result.data_scope||v.scope!=='RESOURCE_SUBSET'||v.formal_effect!=='none'||v.model_calls!==0||v.applicability_review!=='NOT_SIGNED'||v.total_resources!==all.length||!['CHECKED','NOT_CONFIGURED'].includes(v.source_status)||!(v.source_profile_sha256===null||hash(v.source_profile_sha256))||(v.source_status==='CHECKED')!==(v.source_profile_sha256!==null)||!unique(v.supported_resource_ids)||!unique(v.uncovered_resource_ids)||!sameSet([...v.supported_resource_ids,...v.uncovered_resource_ids],all)||v.supported_resource_ids.some((x:string)=>v.uncovered_resource_ids.includes(x))||!strings(v.limitations)||!Array.isArray(v.advice)||v.advice.length!==uses.length||new Set(v.advice.map((x:any)=>x.usage)).size!==uses.length)return fail();
 const supported=new Set<string>();
 for(const d of v.advice){
  if(!object(d)||!uses.includes(d.usage)||d.saved_value!==result.usage[d.usage as Use]||d.selection!==(d.saved_value===null?'UNKNOWN':d.saved_value?'SELECTED':'NOT_SELECTED')||!text(d.summary)||!Array.isArray(d.resources)||!unique(d.uncovered_resource_ids)||!['CONDITIONAL_TEXT_BASIS','NO_SUPPORTED_BASIS','NOT_SELECTED','USAGE_UNDECLARED'].includes(d.state))return fail();
  const expected=d.saved_value===null?'USAGE_UNDECLARED':d.saved_value===false?'NOT_SELECTED':d.resources.length?'CONDITIONAL_TEXT_BASIS':'NO_SUPPORTED_BASIS';
  if(d.state!==expected||(d.resources.length&&v.source_status!=='CHECKED'))return fail();
  const covered:string[]=[];
  for(const r of d.resources){
   if(!object(r)||!object(r.subject))return fail();
   const old=result.resources.find(x=>x.subject.resource_id===r.subject.resource_id);
   if(!old||r.subject.version!==old.subject.version||covered.includes(r.subject.resource_id)||r.state!=='CONDITIONAL_TEXT_BASIS'||!text(r.name)||!text(r.recommendation)||!strings(r.conditions)||!r.conditions.length||!strings(r.limitations)||!r.limitations.length||!unique(r.material_ids)||!r.material_ids.length||!r.material_ids.every((x:string)=>old.material_ids.includes(x))||!Array.isArray(r.material_sha256)||r.material_sha256.length!==r.material_ids.length||!r.material_sha256.every(hash)||!unique(r.evidence_ids)||!r.evidence_ids.length||!r.evidence_ids.every((x:string)=>old.evidence_ids.includes(x))||!strings(r.source_urls)||!r.source_urls.length||!r.source_urls.every((x:string)=>{try{const u=new URL(x);return u.protocol==='https:'&&u.hostname==='registry.npmjs.org'&&!u.username&&!u.password;}catch{return false;}})||r.rule_id!==v.rule_version)return fail();
   covered.push(r.subject.resource_id);supported.add(r.subject.resource_id);
  }
  if(!sameSet([...covered,...d.uncovered_resource_ids],all)||covered.some(x=>d.uncovered_resource_ids.includes(x)))return fail();
 }
 if(!sameSet([...supported],v.supported_resource_ids))return fail();
 return v as PreliminaryAdvice;
}
export async function readPreliminaryAdvice(a:Assessment,result:Result,signal?:AbortSignal){
 const path=`/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/results/${encodeURIComponent(result.result_id)}/preliminary-advice?assessment_version=${a.version}`;
 return validatePreliminaryAdvice(await request(path,{},signal),result);
}
