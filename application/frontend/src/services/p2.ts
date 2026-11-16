import { ApiError, request } from './scans';
import { usageFields, type Assessment } from './assessments';
import type { Scan } from '../types/domain';

export const p2WorkbenchEnabled = import.meta.env.VITE_P2_WORKBENCH === '1';
export type Use = keyof typeof usageFields;
export type Binding = {scan_id:string;assessment_id:string;assessment_version:number;registry_revision:number;project_revision:string|null;facts_hash:string;usage_hash:string;rule_version:string;assessment_sha256:string};
export type Subject = {resource_id:string;version:string|null};
export type State = 'candidate'|'unknown'|'pending'|'partial';
export type Advice = {usage:Use;saved_value:boolean|null;selection:'SELECTED'|'NOT_SELECTED'|'UNKNOWN';state:'conditional_candidate'|'unknown'|'not_selected';scope:'RESOURCE';conditions:string[];gaps:string[];basis_evidence_ids:string[];rule_ids:string[]};
export type ResourceResult = {subject:Subject;resource_kind:'component'|'ai_asset';state:State;verification_state:'candidate_only';scope:string;evidence_ids:string[];evidence_source_hashes:Record<string,string>;material_ids:string[];answer_ids:string[];gaps:string[];advice:Advice[];user_assertions:Record<string,string>;inherited_local_support:boolean;inherited_support_source:'PARENT_ASSESSMENT_NOT_NEW_VALUE'};
export type QuestionCode = 'DELIVERY_SCOPE_FOR_RESOURCES'|'OBLIGATION_FULFILLMENT_IN_DELIVERY';
export type AnswerCode = 'YES_INCLUDE'|'NO_EXCLUDE'|'NOT_DECIDED'|'FULFILLED'|'NOT_FULFILLED'|'NOT_DELIVERED_YET'|'UNKNOWN';
export type Question = {question_id:string;question_code:QuestionCode;origin:'DETERMINISTIC_P2_NOT_R6_AGGREGATE';subjects:Subject[];options:AnswerCode[];scope_rule:'EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN'};
export type Result = {schema_version:'openguard-p2-result/1';algorithm_version:'p2-bound-candidate/1';result_id:string;revision:number;previous_result_id:string|null;result_sha256:string;binding:Binding;data_scope:'OWNER'|'TEST_ONLY';computation:'DETERMINISTIC_P2B';publication_status:'succeeded';formal_effect:'none';model_calls:0;state:State;created_at:string;usage:Record<Use,boolean|null>;resources:ResourceResult[];questions:Question[];material_ids:string[];answer_ids:string[];recomputed_resource_ids:string[];reused_resource_ids:string[];companion_summary_id:string};
export type ResultIndex = {head_result_id:string|null;head_revision:number;result_ids:string[];has_more:boolean};
export type Material = {material_id:string;revision:1;binding:Binding;subject:Subject;evidence_ids:string[];filename:string;source_sha256:string;byte_count:number;completeness:'FULL_TEXT_CLAIMED'|'EXCERPT';parse_status:'text_observed';adoption_status:'adopted_as_unverified_observation';verification_state:'pending';source_level:'user_supplied_unverified';formal_effect:'none';data_scope:'OWNER'|'TEST_ONLY'};
export type Answer = {answer_id:string;revision:number;binding:Binding;question_id:string;question_code:QuestionCode;answer_code:AnswerCode;subjects:Subject[];evidence_ids:string[];provenance:'USER_ASSERTED';formal_effect:'none';data_scope:'OWNER'|'TEST_ONLY'};
export type Receipt = {result:Result;answer:Answer|null;material:Material|null};
export type WriteBody = {binding:Binding;expected_revision:number;parent_result_id:string|null;idempotency_key:string}&Record<string,unknown>;
export type PendingWrite = {operation:'results'|'answers'|'materials';body:WriteBody;serialized:string};
export type Summary = {summary_id:string;result_id:string;result_revision:number;result_sha256:string;binding:Binding;material_ids:string[];answer_ids:string[];state:State;resource_states:Record<string,State>;formal_effect:'none';report_kind:'P2_COMPANION_NOT_FORMAL_REPORT'};
const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const sha=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const strs=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(x=>typeof x==='string');
const ids=(v:unknown):v is string[]=>strs(v)&&v.every(id)&&new Set(v).size===v.length;
const positive=(v:unknown)=>Number.isInteger(v)&&Number(v)>0;
const states=['candidate','unknown','pending','partial'];
const uses=Object.keys(usageFields) as Use[];
const fail=():never=>{throw new Error('P2身份或数据契约不一致；保留原结果，请重新读取准确版本。');};
const subject=(v:unknown):v is Subject=>obj(v)&&id(v.resource_id)&&(v.version===null||typeof v.version==='string');
const equalSubject=(a:Subject,b:Subject)=>a.resource_id===b.resource_id&&a.version===b.version;
export const options:Record<QuestionCode,AnswerCode[]>={DELIVERY_SCOPE_FOR_RESOURCES:['YES_INCLUDE','NO_EXCLUDE','NOT_DECIDED'],OBLIGATION_FULFILLMENT_IN_DELIVERY:['FULFILLED','NOT_FULFILLED','NOT_DELIVERED_YET','UNKNOWN']};
export const stateLabels:Record<State,string>={candidate:'有条件候选',unknown:'依据待补齐',pending:'材料待核验',partial:'部分有依据'};
export const answerLabels:Record<AnswerCode,string>={YES_INCLUDE:'会交付所选资源',NO_EXCLUDE:'不交付所选资源',NOT_DECIDED:'尚未决定',FULFILLED:'已保留要求的声明',NOT_FULFILLED:'尚未保留',NOT_DELIVERED_YET:'尚未交付',UNKNOWN:'暂不清楚'};
export const questionLabels:Record<QuestionCode,string>={DELIVERY_SCOPE_FOR_RESOURCES:'哪些资源会随产品一起交付？',OBLIGATION_FULFILLMENT_IN_DELIVERY:'实际交付物中，是否已保留要求的版权和许可声明？'};
export function validateBinding(v:unknown,a:Assessment):Binding {
 if(!obj(v)||v.scan_id!==a.scan_id||v.assessment_id!==a.id||v.assessment_version!==a.version||!positive(v.registry_revision)||!(v.project_revision===null||typeof v.project_revision==='string')||!sha(v.facts_hash)||v.facts_hash!==a.facts_hash||!sha(v.usage_hash)||!sha(v.assessment_sha256)||v.rule_version!==a.rule_version)return fail();
 const storedUsage=(a as Assessment&{usage_hash?:string}).usage_hash;
 if(storedUsage!==undefined&&v.usage_hash!==storedUsage)return fail();
 return v as Binding;
}
export function sameBinding(a:Binding,b:Binding):boolean {return (Object.keys(a) as (keyof Binding)[]).length===9&&(['scan_id','assessment_id','assessment_version','registry_revision','project_revision','facts_hash','usage_hash','rule_version','assessment_sha256'] as const).every(k=>a[k]===b[k]);}
export function validateResult(v:unknown,a:Assessment,b:Binding,expectedId?:string):Result {
 if(!obj(v)||v.schema_version!=='openguard-p2-result/1'||v.algorithm_version!=='p2-bound-candidate/1'||!id(v.result_id)||(expectedId!==undefined&&v.result_id!==expectedId)||!positive(v.revision)||!(v.previous_result_id===null||id(v.previous_result_id))||!sha(v.result_sha256)||!sameBinding(validateBinding(v.binding,a),b)||!['OWNER','TEST_ONLY'].includes(v.data_scope)||v.computation!=='DETERMINISTIC_P2B'||v.publication_status!=='succeeded'||v.formal_effect!=='none'||v.model_calls!==0||!states.includes(v.state)||typeof v.created_at!=='string'||!Number.isFinite(Date.parse(v.created_at))||!obj(v.usage)||!uses.every(k=>[true,false,null].includes(v.usage[k]))||!uses.every(k=>v.usage[k]===(a.usage?.[k]??null))||Object.keys(v.usage).length!==uses.length||!Array.isArray(v.resources)||!Array.isArray(v.questions)||!['material_ids','answer_ids','recomputed_resource_ids','reused_resource_ids'].every(k=>ids(v[k]))||!id(v.companion_summary_id))return fail();
 const resources=new Map<string,ResourceResult>();
 for(const r of v.resources){
  if(!obj(r)||!subject(r.subject)||resources.has(r.subject.resource_id)||!a.resource_ids.includes(r.subject.resource_id)||!['component','ai_asset'].includes(r.resource_kind)||!states.includes(r.state)||r.verification_state!=='candidate_only'||typeof r.scope!=='string'||!['evidence_ids','material_ids','answer_ids'].every(k=>ids(r[k]))||!strs(r.gaps)||!obj(r.evidence_source_hashes)||!Object.entries(r.evidence_source_hashes).every(([k,h])=>r.evidence_ids.includes(k)&&sha(h))||!r.evidence_ids.every((e:string)=>a.evidence_ids.includes(e))||!r.material_ids.every((e:string)=>v.material_ids.includes(e))||!r.answer_ids.every((e:string)=>v.answer_ids.includes(e))||!Array.isArray(r.advice)||r.advice.length!==uses.length||new Set(r.advice.map((x:any)=>x.usage)).size!==uses.length||!obj(r.user_assertions)||typeof r.inherited_local_support!=='boolean'||r.inherited_support_source!=='PARENT_ASSESSMENT_NOT_NEW_VALUE')return fail();
  for(const d of r.advice){if(!obj(d)||!uses.includes(d.usage)||d.saved_value!==v.usage[d.usage]||d.selection!==(d.saved_value===null?'UNKNOWN':d.saved_value?'SELECTED':'NOT_SELECTED')||!['conditional_candidate','unknown','not_selected'].includes(d.state)||(d.saved_value===false&&d.state!=='not_selected')||d.scope!=='RESOURCE'||!strs(d.conditions)||!strs(d.gaps)||!ids(d.basis_evidence_ids)||!d.basis_evidence_ids.every((e:string)=>r.evidence_ids.includes(e))||!strs(d.rule_ids))return fail();}
  resources.set(r.subject.resource_id,r as ResourceResult);
 }
 if(resources.size!==a.resource_ids.length)return fail();
 const qids=new Set<string>();
 for(const q of v.questions){if(!obj(q)||!id(q.question_id)||qids.has(q.question_id)||!(q.question_code in options)||q.origin!=='DETERMINISTIC_P2_NOT_R6_AGGREGATE'||q.scope_rule!=='EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN'||!Array.isArray(q.subjects)||!q.subjects.length||new Set(q.subjects.map((s:any)=>s.resource_id)).size!==q.subjects.length||!q.subjects.every((s:unknown)=>subject(s)&&resources.has(s.resource_id)&&equalSubject(s,resources.get(s.resource_id)!.subject))||!ids(q.options)||!q.options.every((x:string)=>options[q.question_code as QuestionCode].includes(x as AnswerCode)))return fail();qids.add(q.question_id);}
 // Saved global object references must equal the union of resource references.
 // Recompute/reuse is a complete disjoint partition, never a partial display count.
 const linkedMaterials=new Set(v.resources.flatMap((r:ResourceResult)=>r.material_ids));
 const linkedAnswers=new Set(v.resources.flatMap((r:ResourceResult)=>r.answer_ids));
 if(linkedMaterials.size!==v.material_ids.length||!v.material_ids.every((x:string)=>linkedMaterials.has(x))
  ||linkedAnswers.size!==v.answer_ids.length||!v.answer_ids.every((x:string)=>linkedAnswers.has(x)))return fail();
 if(!v.recomputed_resource_ids.every((s:string)=>resources.has(s))||!v.reused_resource_ids.every((s:string)=>resources.has(s))||v.recomputed_resource_ids.some((s:string)=>v.reused_resource_ids.includes(s))
  ||v.recomputed_resource_ids.length+v.reused_resource_ids.length!==resources.size)return fail();
 return v as Result;
}
export function validateIndex(v:unknown):ResultIndex {if(!obj(v)||!(v.head_result_id===null||id(v.head_result_id))||!Number.isInteger(v.head_revision)||v.head_revision<0||!ids(v.result_ids)||typeof v.has_more!=='boolean'||(v.head_result_id===null)!==(v.head_revision===0))return fail();return v as ResultIndex;}
export function validateMaterial(v:unknown,a:Assessment,b:Binding,result:Result):Material {
 if(!obj(v)||!id(v.material_id)||!result.material_ids.includes(v.material_id)||v.revision!==1||!sameBinding(validateBinding(v.binding,a),b)||!subject(v.subject)||!result.resources.some(r=>equalSubject(r.subject,v.subject))||!ids(v.evidence_ids)||!v.evidence_ids.length||!v.evidence_ids.every((e:string)=>result.resources.find(r=>equalSubject(r.subject,v.subject))!.evidence_ids.includes(e))||!sha(v.source_sha256)||!positive(v.byte_count)||v.byte_count>65536||!['FULL_TEXT_CLAIMED','EXCERPT'].includes(v.completeness)||!/^((LICENSE|LICENCE|NOTICE)(\.(txt|md|rst))?)$/i.test(v.filename)||v.parse_status!=='text_observed'||v.adoption_status!=='adopted_as_unverified_observation'||v.verification_state!=='pending'||v.source_level!=='user_supplied_unverified'||v.formal_effect!=='none'||v.data_scope!==result.data_scope)return fail();
 // Only the exact subject resource may reference the current Material ID.
 const references=result.resources.filter(r=>r.material_ids.includes(v.material_id));
 if(references.length!==1||!equalSubject(references[0].subject,v.subject))return fail();
 return v as Material;
}
function validateAnswer(v:unknown,a:Assessment,b:Binding,result:Result):Answer {
 // Adapt xzb 7dd84b5 p2Workflow.validateAnswer to the existing Assessment-aware validator.
 if(!obj(v)||!id(v.answer_id)||!result.answer_ids.includes(v.answer_id)||!sameBinding(validateBinding(v.binding,a),b)||v.provenance!=='USER_ASSERTED'||v.formal_effect!=='none'||v.data_scope!==result.data_scope||!positive(v.revision)||v.revision>result.revision||!id(v.question_id)||!(v.question_code in options)||!options[v.question_code as QuestionCode].includes(v.answer_code)||!Array.isArray(v.subjects)||!v.subjects.length||!v.subjects.every((s:unknown)=>subject(s)&&result.resources.some(r=>equalSubject(r.subject,s)))||!ids(v.evidence_ids))return fail();
 const subjects=v.subjects as Subject[];
 if(new Set(subjects.map(s=>s.resource_id)).size!==subjects.length)return fail();
 const resources=result.resources.filter(r=>subjects.some(s=>equalSubject(r.subject,s)));
 if(result.resources.some(r=>r.answer_ids.includes(v.answer_id)!==subjects.some(s=>equalSubject(r.subject,s)))||!v.evidence_ids.every((e:string)=>resources.some(r=>r.evidence_ids.includes(e))))return fail();
 return v as Answer;
}
export function validateReceipt(v:unknown,a:Assessment,b:Binding):Receipt {if(!obj(v))return fail();const result=validateResult(v.result,a,b);if(v.material!==null)validateMaterial(v.material,a,b,result);if(v.answer!==null)validateAnswer(v.answer,a,b,result);return {...v,result} as Receipt;}
export function validateSummary(v:unknown,result:Result):Summary {if(!obj(v)||v.summary_id!==result.companion_summary_id||v.result_id!==result.result_id||v.result_revision!==result.revision||v.result_sha256!==result.result_sha256||!obj(v.binding)||!sameBinding(v.binding as Binding,result.binding)||JSON.stringify(v.material_ids)!==JSON.stringify(result.material_ids)||JSON.stringify(v.answer_ids)!==JSON.stringify(result.answer_ids)||v.state!==result.state||v.formal_effect!=='none'||v.report_kind!=='P2_COMPANION_NOT_FORMAL_REPORT'||!obj(v.resource_states)||Object.keys(v.resource_states).length!==result.resources.length||!result.resources.every(r=>v.resource_states[r.subject.resource_id]===r.state))return fail();return v as Summary;}

// A display-only projection of saved Advice, never a new API DTO or license decision.
export type BoundSavedAdviceRow = {
 subject:Subject;name:string;usage:Use;conditions:string[];advice_gaps:string[];resource_gaps:string[];
 basis_evidence_ids:string[];rule_ids:string[];
};
// Local display diagnostics, not new public API fields or a source/permission verdict.
export type BoundAdviceNoticeCode = 'BINDING_OR_USAGE_MISMATCH'|'SOURCE_REVISION_UNESTABLISHED'|'SOURCE_REVISION_MISMATCH'|'RESOURCE_BINDING_MISMATCH'|'BASIS_INCOMPLETE'|'BASIS_INDIRECT_UNCONFIRMED'|'NO_SAVED_CONDITIONAL';
export type BoundAdviceNotice = {code:BoundAdviceNoticeCode;subject?:Subject;usage?:Use};
export type BoundSavedAdviceSelection = {rows:BoundSavedAdviceRow[];notices:BoundAdviceNotice[];usage_hash_assurance:'PARENT_FIELD_MATCH'|'BINDING_AND_USAGE_VALUES_ONLY'|null};
export function selectBoundSavedAdvice(a:Assessment,b:Binding|null,result:Result,scan:Scan):BoundSavedAdviceSelection {
 const blocked=(code:BoundAdviceNoticeCode):BoundSavedAdviceSelection=>({rows:[],notices:[{code}],usage_hash_assurance:null});
 try {
  // b comes from the Workbench's existing binding GET, not from Summary or a derived view.
  if(!b||scan.mode!=='api'||scan.completeness!=='full'||scan.id!==a.scan_id||scan.id!==b.scan_id
   ||!obj(a.usage)||!uses.every(k=>a.usage[k]===true||a.usage[k]===false||a.usage[k]===null))return blocked('BINDING_OR_USAGE_MISMATCH');
  validateBinding(b,a);
  if(!sameBinding(b,result.binding))return blocked('BINDING_OR_USAGE_MISMATCH');
  validateResult(result,a,b,result.result_id);
  const parentUsageHash=(a as Assessment&{usage_hash?:unknown}).usage_hash;
  if(parentUsageHash!==undefined&&(!sha(parentUsageHash)||parentUsageHash!==b.usage_hash))return blocked('BINDING_OR_USAGE_MISMATCH');
  const usage_hash_assurance=parentUsageHash===undefined?'BINDING_AND_USAGE_VALUES_ONLY' as const:'PARENT_FIELD_MATCH' as const;
  // Neither branch independently recomputes the parent's canonical usage hash.
  if(scan.revision===null&&b.project_revision===null)return {rows:[],notices:[{code:'SOURCE_REVISION_UNESTABLISHED'}],usage_hash_assurance};
  if(typeof scan.revision!=='string'||!scan.revision||typeof b.project_revision!=='string'||!b.project_revision)return blocked('SOURCE_REVISION_UNESTABLISHED');
  if(scan.revision!==b.project_revision)return blocked('SOURCE_REVISION_MISMATCH');
  if(!Array.isArray(scan.resources)||!Array.isArray(scan.evidence)
   ||new Set(scan.resources.map(r=>r.id)).size!==scan.resources.length
   ||new Set(scan.evidence.map(e=>e.id)).size!==scan.evidence.length)return blocked('RESOURCE_BINDING_MISMATCH');
  const evidence=new Set(scan.evidence.map(e=>e.id));
  const rows:BoundSavedAdviceRow[]=[],notices:BoundAdviceNotice[]=[];
  for(const row of result.resources){
   const saved=row.advice.filter(d=>result.usage[d.usage]===true&&a.usage[d.usage]===true&&d.saved_value===true
    &&d.selection==='SELECTED'&&d.state==='conditional_candidate');
   if(!saved.length)continue;
   const resource=scan.resources.find(r=>r.id===row.subject.resource_id);
   if(!resource||resource.type!=='Package'||row.resource_kind!=='component'
    ||typeof resource.version!=='string'||!resource.version||resource.version!==row.subject.version
    ||/[\s*^~<>=|,]/.test(resource.version)||!ids(resource.evidenceIds)
    ||(resource.ecosystem==='npm'&&!/^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?$/.test(resource.version))){notices.push({code:'RESOURCE_BINDING_MISMATCH',subject:{...row.subject}});continue;}
   for(const d of saved){
    if(!d.conditions.length||!d.conditions.every(c=>c.trim().length>0)||!d.rule_ids.length||!d.rule_ids.every(r=>r.trim().length>0)
     ||!d.basis_evidence_ids.length||!d.basis_evidence_ids.every(e=>row.evidence_ids.includes(e)&&a.evidence_ids.includes(e)
      &&evidence.has(e)&&Object.prototype.hasOwnProperty.call(row.evidence_source_hashes,e)&&sha(row.evidence_source_hashes[e]))){notices.push({code:'BASIS_INCOMPLETE',subject:{...row.subject},usage:d.usage});continue;}
    // A saved union reference is not an independently verified LicenseExpression edge.
    // Do not declare the Advice invalid or promote a same-ID/hash reference into direct support.
    if(!d.basis_evidence_ids.every(e=>resource.evidenceIds.includes(e))){notices.push({code:'BASIS_INDIRECT_UNCONFIRMED',subject:{...row.subject},usage:d.usage});continue;}
    rows.push({subject:{...row.subject},name:resource.name,usage:d.usage,conditions:[...d.conditions],
     advice_gaps:[...d.gaps],resource_gaps:[...row.gaps],basis_evidence_ids:[...d.basis_evidence_ids],rule_ids:[...d.rule_ids]});
   }
  }
  if(!rows.length&&!notices.length)notices.push({code:'NO_SAVED_CONDITIONAL'});
  return {rows,notices,usage_hash_assurance};
 } catch {return blocked('BINDING_OR_USAGE_MISMATCH');}
}
// Indirect LicenseExpression-only references are not independently linked by this Scan DTO.
// Keep them in existing details; this main-card guard requires every displayed basis to be direct.
// Stored hashes are registration checks here, not independent authentication of source bytes.
const prefix=(a:Assessment)=>`/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2`;
const version=(a:Assessment)=>`?assessment_version=${a.version}`;
export const resultPath=(a:Assessment,id:string)=>prefix(a)+'/results/'+encodeURIComponent(id)+version(a);
export const summaryUrl=(a:Assessment,id:string)=>(import.meta.env.VITE_API_BASE_URL||'/api/v1').replace(/\/$/,'')+prefix(a)+'/results/'+encodeURIComponent(id)+'/summary'+version(a);
export function resultPageUrl(a:Assessment,id:string){return `/app/scans/${encodeURIComponent(a.scan_id)}/assessment?mode=api&assessment_id=${encodeURIComponent(a.id)}&p2_result=${encodeURIComponent(id)}`;}
export async function readBinding(a:Assessment,signal?:AbortSignal){return validateBinding(await request(prefix(a)+'/binding',{},signal),a);}
export async function readIndex(a:Assessment,signal?:AbortSignal,offset=0){return validateIndex(await request(prefix(a)+'/results'+version(a)+'&offset='+offset,{},signal));}
export async function readResult(a:Assessment,b:Binding,id:string,signal?:AbortSignal){return validateResult(await request(resultPath(a,id),{},signal),a,b,id);}
// Read the explicit immutable parent only. Assessment changes are not Result revisions.
export async function readPreviousResult(a:Assessment,b:Binding,current:Result,signal?:AbortSignal):Promise<Result|null>{
 validateResult(current,a,b,current.result_id);
 if(current.previous_result_id===null)return null;
 if(current.revision<=1)return fail();
 const previous=await readResult(a,b,current.previous_result_id,signal);
 if(previous.revision!==current.revision-1||previous.data_scope!==current.data_scope||!sameBinding(previous.binding,current.binding))return fail();
 return previous;
}
export async function readMaterial(a:Assessment,b:Binding,result:Result,id:string,signal?:AbortSignal){const value=await request(prefix(a)+'/materials/'+encodeURIComponent(id)+version(a),{},signal);const m=validateMaterial(value,a,b,result);if(m.material_id!==id)return fail();return m;}
export async function readSummary(a:Assessment,result:Result,signal?:AbortSignal){return validateSummary(await request(prefix(a)+'/results/'+encodeURIComponent(result.result_id)+'/summary'+version(a),{},signal),result);}
export function prepareWrite(operation:PendingWrite['operation'],b:Binding,parent:Result|null,key:string,extra:Record<string,unknown>={}):PendingWrite {
 if(!/^[A-Za-z0-9_-]{8,100}$/.test(key)||Object.keys(extra).some(k=>['binding','parent_result_id','expected_revision','idempotency_key'].includes(k)))return fail();
 const body={...extra,binding:b,parent_result_id:parent?.result_id??null,expected_revision:parent?.revision??0,idempotency_key:key};
 return {operation,body,serialized:JSON.stringify(body)};
}
// Adapted from xzb 7dd84b5 p2Workflow: keep the recording validator, bind to the submitted request.
export function validateSubmittedReceipt(v:unknown,a:Assessment,b:Binding,p:PendingWrite):Receipt {
 const receipt=validateReceipt(v,a,b),r=receipt.result,sent=p.body;
 if(r.revision!==sent.expected_revision&&r.revision!==sent.expected_revision+1)return fail();
 if(r.revision===sent.expected_revision?r.result_id!==sent.parent_result_id:r.previous_result_id!==sent.parent_result_id)return fail();
 // The fixed backend sorts these valid unique sets and uppercases ASCII material names.
 // Compare only copies/values: never rewrite the frozen request, receipt or other arrays.
 const sameIds=(x:unknown,y:unknown)=>ids(x)&&ids(y)&&x.length===y.length&&x.every(v=>y.includes(v));
 const uniqueSubjects=(v:unknown):v is Subject[]=>Array.isArray(v)&&v.length>0&&v.every(subject)&&new Set(v.map(s=>s.resource_id)).size===v.length;
 const sameSubjects=(x:unknown,y:unknown)=>uniqueSubjects(x)&&uniqueSubjects(y)&&x.length===y.length&&x.every(s=>y.some(t=>equalSubject(s,t)));
 const materialName=(v:unknown)=>{
  if(typeof v!=='string'||/[^\x00-\x7f]/.test(v))return null;
  const match=/^(LICENSE|LICENCE|NOTICE)(\.(txt|md|rst))?$/i.exec(v);
  return match?.[0]===v?v.toUpperCase():null;
 };
 const sameMaterialName=(x:unknown,y:unknown)=>{const name=materialName(x);return name!==null&&name===materialName(y);};
 if(p.operation==='answers'){
  const x=receipt.answer;if(!x||receipt.material||x.question_id!==sent.question_id||x.question_code!==sent.question_code||x.answer_code!==sent.answer_code||!sameSubjects(sent.subjects,x.subjects)||!sameIds(sent.evidence_ids,x.evidence_ids))return fail();
 }else if(p.operation==='materials'){
  const x=receipt.material;if(!x||receipt.answer||!subject(sent.subject)||!equalSubject(x.subject,sent.subject)||!sameIds(sent.evidence_ids,x.evidence_ids)||x.source_sha256!==sent.source_sha256||!sameMaterialName(sent.filename,x.filename)||x.completeness!==sent.completeness)return fail();
 }else if(receipt.answer||receipt.material)return fail();
 return receipt;
}
type Attempt={pending:PendingWrite;state:'sending'|'unknown'|'conflict'|'rejected';recovered:boolean};
// Only this tab's memory; material content is never written to localStorage.
const attempts=new Map<string,Attempt>();
const attemptKey=(a:Assessment)=>JSON.stringify([a.scan_id,a.id,a.version]);
export const pendingWriteFor=(a:Assessment)=>attempts.get(attemptKey(a))?.pending??null;
export const canReplayWrite=(a:Assessment)=>{const x=attempts.get(attemptKey(a));return !!x&&x.state==='unknown'&&x.recovered;};
export const canClearWrite=(a:Assessment)=>{const x=attempts.get(attemptKey(a));return !!x&&x.state!=='sending'&&x.recovered;};
export function clearPendingWrite(a:Assessment){if(!canClearWrite(a))throw Error('请先只读核对服务器结果。');attempts.delete(attemptKey(a));}
export async function recoverWrite(a:Assessment,b:Binding,p:PendingWrite){
 const key=attemptKey(a),attempt=attempts.get(key);if(!attempt||attempt.pending!==p||attempt.state==='sending')return fail();
 attempt.recovered=false;
 const current=await readBinding(a);if(!sameBinding(current,b)||!sameBinding(current,p.body.binding))return fail();
 const index=await readIndex(a),result=index.head_result_id?await readResult(a,current,index.head_result_id):null;
 if(result&&result.revision!==index.head_revision)return fail();
 if(attempts.get(key)!==attempt)return fail();attempt.recovered=true;return {index,result};
}
export async function submitWrite(a:Assessment,b:Binding,pending:PendingWrite){
 if(!sameBinding(pending.body.binding,b)||JSON.stringify(pending.body)!==pending.serialized)return fail();
 const key=attemptKey(a),old=attempts.get(key);
 if(old&&(old.pending!==pending||!canReplayWrite(a)))throw Error('请先核对服务器状态；冲突或拒绝后不可重放。');
 const attempt:Attempt={pending,state:'sending',recovered:false};attempts.set(key,attempt);
 try{const receipt=validateSubmittedReceipt(await request(prefix(a)+'/'+pending.operation,{method:'POST',headers:{'Content-Type':'application/json'},body:pending.serialized},undefined,201),a,b,pending);attempts.delete(key);return receipt;}
 catch(e){attempt.state=e instanceof ApiError&&e.status===409?'conflict':e instanceof ApiError&&[403,404,413,422].includes(e.status)?'rejected':'unknown';throw e;}
}
// Accept both the established recording URL and xzb's versioned links, never silently latest.
export function selectP2Result(q:URLSearchParams,assessmentVersion:number):{id:string;revision:number|null}|null {
 for(const key of ['p2_result','p2_result_id','p2_revision','assessment_version'])if(q.getAll(key).length>1)return fail();
 const legacy=q.get('p2_result'),named=q.get('p2_result_id'),revision=q.get('p2_revision'),av=q.get('assessment_version');
 if(av!==null&&(!/^[1-9]\d*$/.test(av)||!Number.isSafeInteger(Number(av))||Number(av)!==assessmentVersion))return fail();
 if(named!==null&&(revision===null||!id(named)))return fail();
 if(legacy!==null&&!id(legacy))return fail();
 if(legacy!==null&&named!==null&&legacy!==named)return fail();
 if(revision!==null&&(!(legacy||named)||!/^[1-9]\d*$/.test(revision)||!Number.isSafeInteger(Number(revision))))return fail();
 const chosen=legacy??named;return chosen?{id:chosen,revision:revision===null?null:Number(revision)}:null;
}
export async function materialBytes(file:File){if(!/^((LICENSE|LICENCE|NOTICE)(\.(txt|md|rst))?)$/i.test(file.name))throw Error('仅接受 LICENSE、LICENCE 或 NOTICE 小文本（可带 .txt/.md/.rst）。');if(file.size<1||file.size>65536)throw Error('材料须为 1–65,536 字节的完整小文本；不会自动截断。');const buffer=await file.arrayBuffer();const bytes=new Uint8Array(buffer);if(bytes.byteLength!==file.size)throw Error('材料读取不完整。');let text:string;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw Error('材料必须使用有效的 UTF-8 编码。');}if(!text.trim()||text.includes('\0'))throw Error('材料内容为空或含非法二进制字符。');let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),x=>x.toString(16).padStart(2,'0')).join('');return {content_base64:btoa(binary),source_sha256:hash,filename:file.name,byte_count:bytes.length};}
const gapLabels:Record<string,string>={scan_coverage_incomplete:'扫描部分完成，覆盖范围有限',scan_error_rules_stage_not_connected:'扫描规则阶段尚未接通，相关覆盖不足',scan_error_git_scan_coverage_partial:'Git 扫描覆盖不完整',scan_error_unclassified:'扫描记录了未分类错误，覆盖仍待核查',upstream_source_attestation_missing:'发行来源及许可适用范围尚待审核',evidence_source_hash_missing:'部分证据缺少原材料摘要',exact_version_missing:'尚未确定精确资源版本',object_scope_unverified:'实际使用范围尚待确认',ai_asset_independent_license_required:'AI资产需要独立的许可依据',license_text_and_applicability_unverified:'许可正文与适用范围尚未核验',uploaded_material_applicability_pending:'已关联材料，适用性待核验',uploaded_material_incomplete:'当前材料为片段，仍缺完整正文',user_statement_not_independently_verified:'已记录用户声明，尚未独立核实',scope_unsupported_or_unknown:'资源使用范围尚待核实',scan_partial:'扫描部分完成，覆盖范围有限',rules_stage_not_connected:'当前扫描规则阶段未完成'};
export function gapLabel(code:string){if(gapLabels[code])return gapLabels[code];if(code.startsWith('usage_')&&code.endsWith('_unknown')){const field=code.slice(6,-8) as Use;return field in usageFields?`${usageFields[field]}：用途尚未确定`:'用途尚未确定';}if(code.includes('coverage')||code.includes('scan_'))return '扫描覆盖存在缺口，详见技术记录';return '此项依据仍待补齐（详见技术记录）';}
