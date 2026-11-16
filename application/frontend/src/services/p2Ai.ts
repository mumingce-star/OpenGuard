import type { Assessment } from './assessments';
import { accountRequestOptions, handleAccountResponse } from './auth';
import { ApiError } from './scans';
import { sameBinding, validateBinding, type Binding, type Result, type Subject } from './p2';

export const p2AiEnabled=import.meta.env.VITE_P2_AI_ANALYSIS==='1';

export type BoundAction = {text:string;claim_level:'verification_action_only';action_kind:string;target_id:string;basis_kind:'license_condition'|'usage_gap';basis_ids:string[];usage_fields:(keyof Result['usage'])[];plan_protocol:'openguard-action-plan/2';display_origin:'PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION'};
export type BoundPlanDetails = {protocol:'openguard-action-plan/2';status:'validated';display_origin:'PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION';context_sha256:string;selection_sha256:string;context:Record<string,any>;action_bindings:Record<string,any>[];human_review_required:false;corrective_attempt_used?:boolean;attempt_count?:number;issues?:{code:string;path:string}[]};
export type BoundPlanEnvelope = {analysis_protocol?:'openguard-qwen-action-plan/2';validation_details?:BoundPlanDetails;plan?:Record<string,unknown>;attempts?:Record<string,unknown>[]};

/** Independent, immutable model explanation. Never a P2 Result or permission decision. */
export type AiSourceRef = { material_id:string; subject:Subject; source_sha256:string; byte_count:number; source_level:'user_supplied_unverified'; verification_state:'pending' };
export type P2AiAnalysis = BoundPlanEnvelope & {
 schema_version:'openguard-p2-ai-analysis/1'; analysis_id:string; analysis_sha256:string;
 status:'succeeded'|'failed'; error_code:string|null; result_id:string; result_revision:number; result_sha256:string; binding:Binding;
 previous_result_id:string|null; previous_result_sha256:string|null; idempotency_key:string;
 model:{name:string;digest:string;runtime:string;prompt_version:string}; input_sha256:string; created_at:string; model_calls:number;
 metrics:{elapsed_ms:number;prompt_eval_count:number|null;eval_count:number|null;total_duration:number|null};
 source_refs:AiSourceRef[]; clauses:{material_id:string;quote:string;start:number;end:number;category:'permission'|'condition'|'disclaimer'|'other';quote_id?:string}[];
 actions:({text:string;source_material_ids:string[];claim_level:'verification_action_only'} & Partial<BoundAction>)[];
 changes:{field:string;before:unknown;after:unknown;explanation:string}[]; limitations:string[];
 formal_effect:'none';usage_assumption:'DEMO_USAGE_ASSUMPTION';data_scope:'TEST_ONLY';quote_index_unit:'unicode_code_point';
};
export type AiRequest = {binding:Binding;result_id:string;result_sha256:string;material_ids:string[];idempotency_key:string;previous_result_id:string|null};
export type AiPending = {body:AiRequest;serialized:string;state:'sent'|'unknown'};
const pending = new Map<string,AiPending>();
const scope=(r:Result)=>JSON.stringify([r.binding,r.result_id,r.revision,r.result_sha256]);
const prefix=(a:Assessment)=>`/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/ai-analyses`;
const base=(import.meta.env.VITE_API_BASE_URL||'/api/v1').replace(/\/$/,'');
const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const sha=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const texts=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(x=>typeof x==='string');
const ids=(v:unknown):v is string[]=>texts(v)&&v.every(id)&&new Set(v).size===v.length;
const number=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)&&v>=0;
const fail=():never=>{throw Error('AI分析的固定结果、材料引用或数据契约不一致；已有规则结果保持不变。');};
function current(a:Assessment,r:Result){if(!sameBinding(validateBinding(r.binding,a),r.binding)||r.data_scope!=='TEST_ONLY')fail();}

const planProtocol='openguard-action-plan/2';
const planOrigin='PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION';
const usageKeys=['commercial','modified','distributed','network_service','training','redistributed_assets','source_disclosure'];
const canonical=(value:unknown):string=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':obj(value)?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);
const sameUsage=(value:unknown,r:Result):boolean=>obj(value)&&Object.keys(value).sort().join(',')===[...usageKeys].sort().join(',')&&usageKeys.every(k=>value[k]===r.usage[k as keyof Result['usage']]);
const sameSubject=(left:unknown,right:unknown):boolean=>obj(left)&&obj(right)&&left.resource_id===right.resource_id&&left.version===right.version;
const planUsageNames:Record<string,string>={commercial:'商业使用',modified:'修改代码',distributed:'向他人分发或交付',network_service:'在线服务',training:'模型训练',redistributed_assets:'资源再分发',source_disclosure:'公开源代码'};
/** Mirror the fixed-sample server renderer, so a valid protocol tag cannot bless substituted prose. */
export function boundActionText(kind:string,subject:Subject):string|null{
 const component='http-server@'+subject.version;
 const rows:Record<string,string>={
  CHECK_COMPONENT_SOURCE:`核对实际使用的${component}文件与记录的Git提交是否一致，保留文件清单及Hash；当前原文不证明npm发行包或其他依赖的范围。`,
  CHECK_MODIFIED_COPY:`核对修改后的${component}文件中哪些属于该源码的副本或实质部分，记录版权和许可声明保留位置及待补项；不代表义务已经履行。`,
  CHECK_PLANNED_COMPONENT_DELIVERY:`核对拟交付的${component}文件清单，再对照所引条件记录声明保留位置；这是计划范围核验，不表示交付已经发生。`,
  CHECK_PUBLIC_SOURCE_SCOPE:`核对计划公开的${component}源码文件集合，对照所引条件记录声明保留位置；不表示源码已经公开。`,
  CHECK_COMMERCIAL_SCOPE:'补充商业使用方式、涉及文件及实际范围的记录；商业用途声明不等于已取得许可认可。',
  CHECK_SERVICE_SCOPE:'核对在线服务是否另外向用户提供源码或文件，记录实际边界；仅运行服务不等于已经分发。',
  CHECK_TRAINING_SCOPE:'补充训练输入、所用代码及各自来源清单，分别核对适用范围；本组件Git LICENSE不能覆盖训练数据、模型或其他资源。',
  CHECK_ASSET_SCOPE:'补充拟再分发资源的实际对象、准确版本及各自许可来源清单；不能用本组件Git LICENSE替代其他资源的依据。',
 };
 if(kind.startsWith('CONFIRM_')){const name=planUsageNames[kind.slice(8).toLowerCase()];return name?'确认'+name+'的实际计划，并记录是、否或仍未知；当前未知值不会自动改成否。':null;}
 return rows[kind]??null;
}
function actionUsageRule(kind:string):{basis:'license_condition'|'usage_gap';field:string|null;expected:true|null}|null{
 const licence:Record<string,string|null>={CHECK_COMPONENT_SOURCE:null,CHECK_MODIFIED_COPY:'modified',CHECK_PLANNED_COMPONENT_DELIVERY:'distributed',CHECK_PUBLIC_SOURCE_SCOPE:'source_disclosure'};
 if(Object.prototype.hasOwnProperty.call(licence,kind))return{basis:'license_condition',field:licence[kind],expected:true};
 const gap:Record<string,string>={CHECK_COMMERCIAL_SCOPE:'commercial',CHECK_SERVICE_SCOPE:'network_service',CHECK_TRAINING_SCOPE:'training',CHECK_ASSET_SCOPE:'redistributed_assets'};
 if(gap[kind])return{basis:'usage_gap',field:gap[kind],expected:true};
 const field=kind.startsWith('CONFIRM_')?kind.slice(8).toLowerCase():'';
 return usageKeys.includes(field)?{basis:'usage_gap',field,expected:null}:null;
}

/** A separate discriminated protocol; legacy free text can never gain its guarantee by adding a label. */
export function validateBoundPlan(value:unknown,a:Assessment,r:Result,sources:{id:string;subject:Subject;sha256:string;text?:string}[],clauses:Record<string,any>[],actions:Record<string,any>[]):void{
 if(!obj(value)||value.analysis_protocol!=='openguard-qwen-action-plan/2'||!obj(value.plan)||!obj(value.validation_details))return fail();
 const d=value.validation_details,c=d.context;
 if(d.protocol!==planProtocol||d.status!=='validated'||d.display_origin!==planOrigin||d.human_review_required!==false||!sha(d.context_sha256)||!sha(d.selection_sha256)
  ||!obj(c)||c.protocol!==planProtocol||c.result_id!==r.result_id||c.result_sha256!==r.result_sha256||c.context_sha256!==d.context_sha256
  ||!sameBinding(validateBinding(c.binding,a),r.binding)||!sameUsage(c.usage,r)||!r.resources.some(row=>sameSubject(c.subject,row.subject))||!sources.length||!sources.every(source=>sameSubject(c.subject,source.subject))
  ||!Array.isArray(c.targets)||!Array.isArray(c.quote_catalog)||!Array.isArray(c.action_catalog)||!Array.isArray(c.gaps)||!Array.isArray(d.action_bindings)
  ||d.action_bindings.length!==actions.length||!actions.length||actions.length>4||!Array.isArray(value.plan.actions)||!Array.isArray(value.plan.clauses)
  ||value.plan.actions.length!==actions.length||value.plan.clauses.length!==clauses.length||!Array.isArray(value.plan.change_explanations)
  ||Object.keys(value.plan).sort().join(',')!=='actions,change_explanations,clauses')return fail();
 const targets=new Map<string,Record<string,any>>(),quotes=new Map<string,Record<string,any>>(),gaps=new Map<string,Record<string,any>>();
 for(const target of c.targets){
  if(!obj(target)||!id(target.target_id)||targets.has(target.target_id)||target.assessment_id!==a.id||!['component_source','assessment_usage_gap'].includes(target.scope_kind))return fail();
  if(target.scope_kind==='component_source'&&(!sameSubject(target.subject,c.subject)||target.usage_field!==null))return fail();
  if(target.scope_kind==='assessment_usage_gap'&&(target.subject!==null||!usageKeys.includes(target.usage_field)))return fail();
  targets.set(target.target_id,target);
 }
 for(const quote of c.quote_catalog){
  const source=sources.find(s=>s.id===quote?.material_id);
  if(!obj(quote)||!id(quote.quote_id)||quotes.has(quote.quote_id)||!source||!sameSubject(quote.subject,source.subject)||quote.source_sha256!==source.sha256
   ||quote.verification_state!=='pending'||!['retrieved_unadopted_candidate','user_supplied_unverified'].includes(quote.source_level)||typeof quote.quote!=='string'||!quote.quote
   ||!Number.isInteger(quote.start)||quote.start<0||!Number.isInteger(quote.end)||quote.end<=quote.start||quote.end-quote.start!==[...quote.quote].length
   ||source.text!==undefined&&[...source.text].slice(quote.start,quote.end).join('')!==quote.quote)return fail();
  quotes.set(quote.quote_id,quote);
 }
 for(let index=0;index<clauses.length;index++){const clause=clauses[index],quote=quotes.get(clause?.quote_id),selected=value.plan.clauses[index];
  const role=quote?.quote==='The above copyright notice and this permission notice shall be\nincluded in all copies or substantial portions of the Software.'?'condition':quote?.quote.startsWith('Permission is hereby granted, free of charge,')?'permission':quote?.quote.startsWith('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY')?'disclaimer':'other';
  if(!quote||clause.quote!==quote.quote||clause.start!==quote.start||clause.end!==quote.end||(clause.material_id??clause.source_candidate_id)!==quote.material_id
   ||!obj(selected)||Object.keys(selected).sort().join(',')!=='category,quote_id'||selected.quote_id!==clause.quote_id||selected.category!==clause.category||clause.category!==role)return fail();
 }
 for(const gap of c.gaps){const target=targets.get(gap?.target_id);
  if(!obj(gap)||!id(gap.gap_id)||gaps.has(gap.gap_id)||!target||target.scope_kind!=='assessment_usage_gap'||gap.usage_field!==target.usage_field
   ||gap.observed_value!==r.usage[gap.usage_field as keyof Result['usage']]||![true,null].includes(gap.observed_value)||gap.state!=='NOT_OBSERVED'||typeof gap.description!=='string'||!gap.description)return fail();
  gaps.set(gap.gap_id,gap);
 }
 const seen=new Set<string>();
 for(let index=0;index<actions.length;index++){
  const action=actions[index],binding=d.action_bindings[index],target=targets.get(action?.target_id),refs=action?.source_material_ids??action?.source_candidate_ids,selected=value.plan.actions[index],rule=actionUsageRule(action?.action_kind??'');
  if(!obj(action)||!obj(binding)||!target||typeof action.text!=='string'||!action.text||action.text.length>600||action.claim_level!=='verification_action_only'
   ||action.plan_protocol!==planProtocol||action.display_origin!==planOrigin||!id(action.action_kind)||!['license_condition','usage_gap'].includes(action.basis_kind)
   ||!ids(action.basis_ids)||!action.basis_ids.length||!ids(action.usage_fields)||!action.usage_fields.every(k=>usageKeys.includes(k))||!ids(refs)
   ||!c.action_catalog.some(item=>canonical(item)===canonical(binding))||binding.kind!==action.action_kind||binding.target_id!==action.target_id||binding.basis_kind!==action.basis_kind
   ||!ids(binding.eligible_basis_ids)||!action.basis_ids.every(x=>binding.eligible_basis_ids.includes(x))||canonical(action.usage_fields)!==canonical(binding.usage_fields)
   ||!obj(binding.required_usage)||!Object.keys(binding.required_usage).every(k=>usageKeys.includes(k)&&r.usage[k as keyof Result['usage']]===binding.required_usage[k])
   ||!rule||rule.basis!==action.basis_kind||(rule.field!==null&&r.usage[rule.field as keyof Result['usage']]!==rule.expected)
   ||canonical(action.usage_fields)!==canonical(rule.field===null?[]:[rule.field])||action.text!==boundActionText(action.action_kind,c.subject)
   ||!obj(selected)||Object.keys(selected).sort().join(',')!=='basis_ids,basis_kind,kind,target_id'||selected.kind!==action.action_kind||selected.target_id!==action.target_id||selected.basis_kind!==action.basis_kind||canonical(selected.basis_ids)!==canonical(action.basis_ids))return fail();
  const key=action.action_kind+':'+action.target_id;if(seen.has(key))return fail();seen.add(key);
  if(action.basis_kind==='usage_gap'){
   if(target.scope_kind!=='assessment_usage_gap'||target.usage_field!==rule.field||refs.length||!action.basis_ids.every(gid=>gaps.get(gid)?.target_id===action.target_id))return fail();
  }else{
   if(target.scope_kind!=='component_source'||!refs.length||!action.basis_ids.every(qid=>clauses.some(clause=>clause.quote_id===qid&&clause.category==='condition'))
    ||!refs.every(mid=>sources.some(s=>s.id===mid))||!action.basis_ids.every(qid=>refs.includes(quotes.get(qid)!.material_id))
    ||canonical([...refs].sort())!==canonical([...new Set(action.basis_ids.map(qid=>quotes.get(qid)!.material_id))].sort()))return fail();
  }
 }
 const changes=value.changes;
 if(!Array.isArray(changes)||value.plan.change_explanations.length!==changes.length)return fail();
 const indexes=new Set<number>();
 for(const selected of value.plan.change_explanations){if(!obj(selected)||Object.keys(selected).sort().join(',')!=='index,kind'||!Number.isInteger(selected.index)||selected.index<0||selected.index>=changes.length||indexes.has(selected.index))return fail();indexes.add(selected.index);const row=changes[selected.index];if(!obj(row)||selected.kind!==(row.field?.startsWith('usage.')?'usage_change':'resource_change'))return fail();}
 for(const change of changes){
  if(!obj(change)||typeof change.field!=='string'||change.display_origin!==planOrigin)return fail();
  let text:string;
  if(change.field.startsWith('usage.')){const key=change.field.slice(6),label=(v:unknown)=>v===true?'是':v===false?'否':'暂不确定';
   if(!usageKeys.includes(key)||![true,false,null].includes(change.before)||change.after!==r.usage[key as keyof Result['usage']]||change.before===change.after)return fail();
   text=`${planUsageNames[key]}用途声明由${label(change.before)}变为${label(change.after)}；这不是实际使用、交付或义务履行的证明。`;
  }else{const label:Record<string,string>={state:'资源状态',material_ids:'材料引用',answer_ids:'回答引用',gaps:'待核验缺口'};if(!label[change.field])return fail();text=label[change.field]+'已按固定新旧结果发生变化；新增材料不等于许可通过。';}
  if(change.explanation!==text)return fail();
 }
}

export async function verifyBoundPlanHashes(value:BoundPlanEnvelope){
 if(value.analysis_protocol!=='openguard-qwen-action-plan/2'||value.validation_details?.status!=='validated')return;
 const details=value.validation_details,{context_sha256,...context}=details.context;
 const hash=async(v:unknown)=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(v))))].map(b=>b.toString(16).padStart(2,'0')).join('');
 if(await hash(context)!==context_sha256||await hash(value.plan)!==details.selection_sha256)return fail();
}

export function validateAiAnalysis(v:unknown,a:Assessment,r:Result,expectedId?:string):P2AiAnalysis{
 current(a,r);
 const structured=obj(v)&&v.analysis_protocol==='openguard-qwen-action-plan/2';
 if(!obj(v)||v.schema_version!=='openguard-p2-ai-analysis/1'||!id(v.analysis_id)||(expectedId!==undefined&&v.analysis_id!==expectedId)||!sha(v.analysis_sha256)
  ||!['succeeded','failed'].includes(v.status)||v.result_id!==r.result_id||v.result_revision!==r.revision||v.result_sha256!==r.result_sha256
  ||!sameBinding(validateBinding(v.binding,a),r.binding)||!id(v.idempotency_key)||!sha(v.input_sha256)
  ||typeof v.created_at!=='string'||!Number.isFinite(Date.parse(v.created_at))||!(structured?[0,1,2]:[0,1]).includes(v.model_calls)
  ||!obj(v.model)||!['name','runtime','prompt_version'].every(k=>typeof v.model[k]==='string'&&v.model[k].length>0)||!sha(v.model.digest)
  ||!obj(v.metrics)||!number(v.metrics.elapsed_ms)||!['prompt_eval_count','eval_count','total_duration'].every(k=>v.metrics[k]===null||number(v.metrics[k]))
  ||!Array.isArray(v.source_refs)||v.source_refs.length<1||v.source_refs.length>4||!Array.isArray(v.clauses)||!Array.isArray(v.actions)||!Array.isArray(v.changes)||!texts(v.limitations)
  ||v.formal_effect!=='none'||v.data_scope!=='TEST_ONLY'||v.usage_assumption!=='DEMO_USAGE_ASSUMPTION'||v.quote_index_unit!=='unicode_code_point')return fail();
 if(v.previous_result_id!==null&&(v.previous_result_id!==r.previous_result_id||!sha(v.previous_result_sha256)))return fail();
 if(v.previous_result_id===null&&(v.previous_result_sha256!==null||v.changes.length>0))return fail();
 const materials=new Map<string,AiSourceRef>();
 for(const s of v.source_refs){
  if(!obj(s)||!id(s.material_id)||materials.has(s.material_id)||!r.material_ids.includes(s.material_id)||!obj(s.subject)
   ||!sha(s.source_sha256)||!Number.isInteger(s.byte_count)||s.byte_count<1||s.byte_count>65536
   ||s.source_level!=='user_supplied_unverified'||s.verification_state!=='pending')return fail();
  const rows=r.resources.filter(x=>x.material_ids.includes(s.material_id));
  if(rows.length!==1||rows[0].subject.resource_id!==s.subject.resource_id||rows[0].subject.version!==s.subject.version)return fail();
  materials.set(s.material_id,s as AiSourceRef);
 }
 if(v.status==='succeeded'){
  if(v.error_code!==null||!(structured?[1,2]:[1]).includes(v.model_calls)||!v.actions.length||!v.clauses.length)return fail();
 }else if(typeof v.error_code!=='string'||!v.error_code||v.clauses.length||v.actions.length||v.changes.length)return fail();
 for(const c of v.clauses){if(!obj(c)||!materials.has(c.material_id)||typeof c.quote!=='string'||!c.quote
  ||!Number.isInteger(c.start)||c.start<0||!Number.isInteger(c.end)||c.end<=c.start||c.end-c.start!==[...c.quote].length
  ||!['permission','condition','disclaimer','other'].includes(c.category))return fail();}
 if(structured&&v.status==='succeeded')validateBoundPlan(v,a,r,[...materials.values()].map(s=>({id:s.material_id,subject:s.subject,sha256:s.source_sha256})),v.clauses,v.actions);
 else for(const action of v.actions){if(!obj(action)||typeof action.text!=='string'||!action.text||action.claim_level!=='verification_action_only'
  ||!ids(action.source_material_ids)||!action.source_material_ids.length||!action.source_material_ids.every(x=>materials.has(x)))return fail();}
 for(const c of v.changes){if(!obj(c)||typeof c.field!=='string'||!c.field||!('before'in c)||!('after'in c)||typeof c.explanation!=='string'||!c.explanation)return fail();}
 return v as P2AiAnalysis;
}

/** AI POST can take 120s. Other business request timeouts are intentionally unchanged. */
async function transport(path:string,method:'GET'|'POST',body?:string,signal?:AbortSignal,permit?:()=>boolean,onDispatch?:()=>void):Promise<unknown>{
 const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),method==='POST'?150000:15000);
 const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});
 try{
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  const options=accountRequestOptions({method,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},body,cache:'no-store',signal:controller.signal});
  // No await between the committed permission check and actual dispatch.
  if(method==='POST'&&!permit?.())throw Error('当前对象或写入许可已变化，未发送模型请求。');
  onDispatch?.();
  const response=await fetch(base+path,options);handleAccountResponse(response.status);
  const value=await response.json().catch(()=>null);
  if(!response.ok)throw new ApiError(response.status,`AI请求未完成（HTTP ${response.status}）。`+(value?.error?.message??''),value?.error?.code);
  if(method==='POST'&&response.status!==200&&response.status!==201)throw Error('AI保存回执状态异常，请先只读核对已保存记录。');
  if(method==='GET'&&response.status!==200)throw Error('AI读取回执状态异常。');
  return value;
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export async function readAiIndex(a:Assessment,r:Result,signal?:AbortSignal):Promise<string[]>{
 current(a,r);const q=new URLSearchParams({assessment_version:String(a.version),result_id:r.result_id});
 const v=await transport(prefix(a)+'?'+q,'GET',undefined,signal);
 if(!obj(v)||v.result_id!==r.result_id||!ids(v.analysis_ids))return fail();return v.analysis_ids;
}
export function aiAnalysisUrl(a:Assessment,r:Result,analysisId:string){
 if(!id(analysisId))return fail();const q=new URLSearchParams({assessment_version:String(a.version),result_id:r.result_id});
 return base+prefix(a)+'/'+encodeURIComponent(analysisId)+'?'+q;
}
export async function readAiAnalysis(a:Assessment,r:Result,analysisId:string,signal?:AbortSignal){
 const url=aiAnalysisUrl(a,r,analysisId);const value=validateAiAnalysis(await transport(url.slice(base.length),'GET',undefined,signal),a,r,analysisId);
 await verifyBoundPlanHashes(value);
 const old=pending.get(scope(r));if(old&&old.body.idempotency_key===value.idempotency_key)pending.delete(scope(r));return value;
}
export function pendingAiAnalysis(r:Result){return pending.get(scope(r))??null;}
export function prepareAiAnalysis(a:Assessment,r:Result,materialIds:string[],comparePrevious:boolean):AiRequest{
 current(a,r);if(!ids(materialIds)||!materialIds.length||materialIds.length>4||!materialIds.every(x=>r.material_ids.includes(x)))return fail();
 return {binding:{...r.binding},result_id:r.result_id,result_sha256:r.result_sha256,material_ids:[...materialIds],idempotency_key:crypto.randomUUID(),previous_result_id:comparePrevious?r.previous_result_id:null};
}
export async function submitAiAnalysis(a:Assessment,r:Result,body:AiRequest,permit:()=>boolean):Promise<P2AiAnalysis>{
 current(a,r);if(pending.has(scope(r)))throw Error('此版本已有结果待确认的模型请求，请先读取保存记录，不自动重复调用。');
 if(!permit())throw Error('当前对象或写入许可已变化，未发送模型请求。');
 if(!sameBinding(body.binding,r.binding)||body.result_id!==r.result_id||body.result_sha256!==r.result_sha256||!id(body.idempotency_key)
  ||!ids(body.material_ids)||!body.material_ids.length||body.material_ids.length>4||!body.material_ids.every(x=>r.material_ids.includes(x))
  ||body.previous_result_id!==null&&body.previous_result_id!==r.previous_result_id)return fail();
 const row:AiPending={body,serialized:JSON.stringify(body),state:'sent'};pending.set(scope(r),row);let dispatched=false;
 try{
  const value=validateAiAnalysis(await transport(prefix(a),'POST',row.serialized,undefined,permit,()=>{dispatched=true;}),a,r);
  await verifyBoundPlanHashes(value);
  if(value.idempotency_key!==body.idempotency_key||value.previous_result_id!==body.previous_result_id
   ||value.source_refs.length!==body.material_ids.length||!value.source_refs.every(x=>body.material_ids.includes(x.material_id)))return fail();
  pending.delete(scope(r));return value;
 }catch(e){
  // A sent unknown outcome is never replayed or silently assigned a new key.
  if(!dispatched||e instanceof ApiError&&[400,401,403,404,422].includes(e.status))pending.delete(scope(r));else row.state='unknown';
  throw e;
 }
}
