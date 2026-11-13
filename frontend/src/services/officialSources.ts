import type { Assessment } from './assessments';
import { accountAuthEnabled, accountRequestOptions, handleAccountResponse } from './auth';
import { ApiError } from './scans';
import { sameBinding, validateBinding, validateReceipt, readBinding, readIndex, readResult, type Binding, type Receipt, type Result, type Subject } from './p2';
import { validateBoundPlan, verifyBoundPlanHashes, type BoundAction, type BoundPlanEnvelope } from './p2Ai';

export const officialSourcesEnabled = import.meta.env.VITE_OFFICIAL_SOURCE_AUTO === '1';
export const fixedCommit = '0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b';
export const fixedLicenseHash = 'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6';
const licenseUrl = `https://raw.githubusercontent.com/http-party/http-server/${fixedCommit}/LICENSE`;
const metadataUrl = 'https://registry.npmjs.org/http-server/14.1.2';
export type Source = {kind:string;url:string;sha256:string;byte_count:number;source_level:string;verification_state:string;retrieved_at?:string|null};
export type SourceFailure={kind:'npm_metadata';url:string;http_status:404;error_code:'upstream_404';request_number:6;retrieved_at:string};
export type Coverage={coverage:'complete_fixed_sources'|'partial_git_license_only';npm_metadata_status:'observed'|'missing_404';source_failures:SourceFailure[]};
export type OfficialCandidate = Coverage & {candidate_id:string;scan_id:string;subject:Subject;commit:string;sources:Source[];license_text:string;adoption_status:'not_adopted';limitations:string[]};
export type Preview = Coverage & BoundPlanEnvelope & {schema_version:'openguard-official-source-preview/1';preview_id:string;preview_sha256:string;result_id:string;result_sha256:string;binding:Binding;status:'succeeded'|'failed';created_at:string;model_calls:number;model:{name:string;digest:string;runtime:string};metrics:{elapsed_ms:number};clauses:{source_candidate_id:string;quote:string;start:number;end:number;category:string;quote_id?:string}[];actions:({text:string;source_candidate_ids:string[];claim_level:'verification_action_only'} & Partial<BoundAction>)[];changes:{field:string;before:unknown;after:unknown;explanation:string}[];previous_result?:null|{result_id:string;result_sha256:string;binding:Binding;selection:string};limitations:string[]};
export type LocalActions = {schema_version:'openguard-p2-local-actions/1';result_id:string;result_revision:number;result_sha256:string;binding:Binding;subject:Subject;usage:Result['usage'];usage_assumption:'DEMO_USAGE_ASSUMPTION';state:'supported_verification_actions'|'awaiting_material'|'source_unavailable';source_refs:{material_id:string;subject:Subject;source_sha256:string;source_level:'user_supplied_unverified';verification_state:'pending';evidence_ids:string[];candidate_id:string;git_commit:string;source_url:string}[];clauses:{material_id:string;quote:string;start:number;end:number;line_start:number;line_end:number;category:'quoted_condition_not_applicability_decision'}[];actions:{code:string;text:string;usage_fields:(keyof Result['usage'])[];source_material_ids:string[];clause_indices:number[];claim_level:'verification_action_only'}[];gaps:string[];limitations:string[];quote_index_unit:'unicode_code_point';formal_effect:'none';model_calls:0;source_admission:'NOT_SIGNED';applicability:'NOT_SIGNED';obligations:'NOT_ESTABLISHED';content_sha256:string};
export type OfficialSources = {schema_version:'openguard-official-sources/1';binding:Binding;result_id:string;result_sha256:string;
 fetch:{state:'not_scheduled'|'queued'|'running'|'ready'|'partial'|'failed'|'outcome_unknown'|'unsupported';retrieval_status?:string;job_id:string|null;error_code:string|null;http_intents:number;http_dispatched:number;http_responses:number};
 candidate:OfficialCandidate|null;analysis:{state:'not_scheduled'|'waiting_source'|'queued'|'running'|'ready'|'failed'|'outcome_unknown';mode:'unadopted_preview'|'saved_material'|null;error_code:string|null;preview:Preview|null;analysis_id:string|null};adopted_material_ids:string[];runtime_jobs_enabled?:boolean;local_actions?:LocalActions;explicit_fetch?:{allowed:boolean;reason:string;request?:Record<string,unknown>|null}};
export type AdoptionRequest = {binding:Binding;candidate_id:string;result_id:string;result_sha256:string;expected_revision:number;parent_result_id:string;idempotency_key:string};
export type PendingOfficialAdoption = {body:AdoptionRequest;serialized:string;subject:Subject;state:'sent'|'unknown'|'conflict'|'rejected';checked:boolean;checked_head_id:string|null;checked_head_revision:number|null};
const inFlight = new Set<string>();
export type PendingOfficialFetch={body:{binding:Binding;result_id:string;result_sha256:string;idempotency_key:string};serialized:string;state:'sent'|'accepted'|'unknown'|'rejected';error_code:string|null};
const fetchInFlight=new Set<string>();
const fetchStoragePrefix='openguard:official-source-fetch:1:';
const storagePrefix='openguard:official-source-adoption:1:';
// Existing account lifecycle sets this per-tab owner key before Workbench mount.
// The new journal is owner-namespaced and never includes auth headers, cookies,
// passwords, CSRF, fetched LICENSE text or arbitrary response bodies.
function accountOwner():string|null{try{const value=sessionStorage.getItem('openguard:account-cache-owner:v1');if(value&&/^[A-Za-z0-9_-]{1,160}$/.test(value))return value;return accountAuthEnabled?null:'AUTH_DISABLED_TEST_ONLY';}catch{return null;}}
function storageKey(r:Result,owner=accountOwner()){return owner===null?null:storagePrefix+encodeURIComponent(owner)+':'+encodeURIComponent(scope(r));}
function savePending(key:string,row:PendingOfficialAdoption){sessionStorage.setItem(key,JSON.stringify(row));if(sessionStorage.getItem(key)!==JSON.stringify(row))throw Error('无法可靠保留原采用请求，未发送新请求。');}
function removePending(key:string){sessionStorage.removeItem(key);}
function fetchStorageKey(r:Result,owner=accountOwner()){return owner===null?null:fetchStoragePrefix+encodeURIComponent(owner)+':'+encodeURIComponent(scope(r));}
function saveFetch(key:string,row:PendingOfficialFetch){const bytes=JSON.stringify(row);sessionStorage.setItem(key,bytes);if(sessionStorage.getItem(key)!==bytes)throw Error('无法保留本次联网请求身份，尚未发起请求。');}
export function pendingOfficialFetch(r:Result):PendingOfficialFetch|null{
 const key=fetchStorageKey(r);if(!key)return null;const raw=sessionStorage.getItem(key);if(raw===null)return null;
 let row:unknown;try{row=JSON.parse(raw);}catch{throw Error('本账号联网请求记录无法读取，请保留现场；不会重新发送。');}
 if(!obj(row)||!obj(row.body)||!sameBinding(row.body.binding,r.binding)||row.body.result_id!==r.result_id||row.body.result_sha256!==r.result_sha256||!id(row.body.idempotency_key)
  ||Object.keys(row.body).sort().join(',')!=='binding,idempotency_key,result_id,result_sha256'||typeof row.serialized!=='string'||JSON.stringify(row.body)!==row.serialized
  ||!['sent','accepted','unknown','rejected'].includes(row.state)||!(row.error_code===null||typeof row.error_code==='string'))throw Error('联网请求身份与当前固定结果不符；不会重新发送。');
 const value=row as PendingOfficialFetch;if(value.state==='sent'&&!fetchInFlight.has(key)){value.state='unknown';saveFetch(key,value);}return value;
}
/** This is a retry of a specifically admitted pre-dispatch failure, never a general search or automatic retry. */
export function canRequestOfficialFetch(value:OfficialSources){return value.runtime_jobs_enabled!==false&&value.explicit_fetch?.allowed===true&&!value.explicit_fetch.request
 &&value.fetch.state==='failed'&&value.fetch.http_intents===0&&value.fetch.http_dispatched===0&&value.fetch.http_responses===0&&value.candidate===null
 &&value.analysis.state==='failed'&&value.analysis.error_code==='official_source_retrieval_unavailable'&&value.analysis.preview===null&&value.analysis.analysis_id===null;}
export function officialAnalysisFailureMessage(code:string|null,correctiveAttemptUsed=false,issues?:unknown):string|null{
 if(!code)return null;
 if(code==='p2_ai_output_rejected'&&Array.isArray(issues)&&issues.some(row=>obj(row)&&row.code==='plan_change_kind'))return '用途变更分类未通过校验；本次结果未展示，原记录保留。'+(correctiveAttemptUsed?'一次定向纠错也未通过，已停止生成；仅需处理这次异常。':'未把错误的变更解释作为已确认事实。');
 if(code==='p2_ai_output_rejected'&&correctiveAttemptUsed)return '一次定向纠错后，行动选择仍未通过用途或依据校验；本次停止展示建议，保留两次原始输出。只需核对这次异常的具体依据，不必复核其他已通过的行动。';
 if(code==='p2_ai_output_rejected')return '辅助分析未通过原文引用或表述校验，未展示建议；已获取的原文仍可预览，材料是否采用由你确认。';
 if(code==='p2_ai_model_unavailable')return '本地模型调用未完成或运行结果不确定，已停止，不会自动重新生成；已有资料和结果保持不变。';
 if(code==='p2_ai_budget_exhausted')return '本轮模型调用额度已用尽，未继续生成；不会自动追加额度或重发。';
 if(code==='p2_ai_busy')return '本地模型正在处理其他任务，本次没有追加并发请求。';
 if(code==='p2_ai_input_too_large')return '本次材料超出受控分析输入范围，未发送给模型；请核对所选材料范围。';
 if(code==='p2_ai_protocol_disabled')return '当前入口未启用用途与依据结构协议，未生成替代建议。';
 if(code==='p2_ai_saved_output_rejected')return '保存记录的用途、引用或行动正文回读核对失败，已停止展示该记录；原始记录保留，需核对本次异常。';
 if(code==='official_source_analysis_repair_prompt_conflict')return '本次分析提示词身份与授权版本不符，已停止调用；不会改用其他模型或旧提示词。';
 if(code==='official_source_process_interrupted')return '上次分析进程中断，执行结果尚未确认；仅核对已有记录，不自动重发。';
 if(code==='official_source_retrieval_unavailable')return '资料未就绪，本次未生成分析。';
 return '本次辅助分析未完成，未展示替代建议；已保存的扫描与结果保持不变。';
}

const scope = (r:Result) => JSON.stringify([r.binding,r.result_id,r.result_sha256]);
const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/,'');
const prefix = (a:Assessment) => `/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/official-sources`;
const obj = (v:unknown):v is Record<string,any> => !!v&&typeof v==='object'&&!Array.isArray(v);
const id = (v:unknown):v is string => typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const sha = (v:unknown):v is string => typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const texts = (v:unknown):v is string[] => Array.isArray(v)&&v.every(x=>typeof x==='string');
const ids = (v:unknown):v is string[] => texts(v)&&v.every(id)&&new Set(v).size===v.length;
const count = (v:unknown):v is number => Number.isInteger(v)&&Number(v)>=0;
const date = (v:unknown) => typeof v==='string'&&Number.isFinite(Date.parse(v));
const fail = ():never => {throw Error('官方资料与当前固定结果的绑定或原文引用不一致，未采用材料，已有结果保持不变。');};
function current(a:Assessment,r:Result){if(!sameBinding(validateBinding(r.binding,a),r.binding)||r.data_scope!=='TEST_ONLY')fail();}

/** This validates a separate verification checklist, never converts it to P2 Advice. */
export function validateLocalActions(v:unknown,a:Assessment,r:Result,c:OfficialCandidate|null):LocalActions{
 if(!obj(v)||v.schema_version!=='openguard-p2-local-actions/1'||v.result_id!==r.result_id||v.result_revision!==r.revision||v.result_sha256!==r.result_sha256
  ||!sameBinding(validateBinding(v.binding,a),r.binding)||!obj(v.subject)||v.subject.version!=='14.1.2'||!obj(v.usage)
  ||Object.keys(v.usage).sort().join(',')!==Object.keys(r.usage).sort().join(',')||!Object.keys(r.usage).every(k=>v.usage[k]===r.usage[k as keyof Result['usage']])
  ||v.usage_assumption!=='DEMO_USAGE_ASSUMPTION'||!['supported_verification_actions','awaiting_material','source_unavailable'].includes(v.state)
  ||!Array.isArray(v.source_refs)||!Array.isArray(v.clauses)||!Array.isArray(v.actions)||!texts(v.gaps)||!texts(v.limitations)||!sha(v.content_sha256)
  ||v.quote_index_unit!=='unicode_code_point'||v.formal_effect!=='none'||v.model_calls!==0||v.source_admission!=='NOT_SIGNED'||v.applicability!=='NOT_SIGNED'||v.obligations!=='NOT_ESTABLISHED')return fail();
 const row=r.resources.find(x=>x.subject.resource_id===v.subject.resource_id&&x.subject.version===v.subject.version);
 if(!row)return fail();
 if(v.state!=='supported_verification_actions'){
  if(v.source_refs.length||v.clauses.length||v.actions.length||(v.state==='source_unavailable'?c!==null:!c))return fail();
  return v as LocalActions;
 }
 if(!c||c.subject.resource_id!==v.subject.resource_id||c.subject.version!==v.subject.version||!v.source_refs.length||v.source_refs.length>4||v.actions.length<1||v.actions.length>4||!v.clauses.length)return fail();
 const mids:string[]=[];
 for(const ref of v.source_refs){
  if(!obj(ref)||!id(ref.material_id)||mids.includes(ref.material_id)||!r.material_ids.includes(ref.material_id)||!row.material_ids.includes(ref.material_id)
   ||!obj(ref.subject)||ref.subject.resource_id!==v.subject.resource_id||ref.subject.version!==v.subject.version||ref.source_sha256!==fixedLicenseHash
   ||ref.source_level!=='user_supplied_unverified'||ref.verification_state!=='pending'||!ids(ref.evidence_ids)||!ref.evidence_ids.every((eid:string)=>row.evidence_ids.includes(eid))
   ||ref.candidate_id!==c.candidate_id||ref.git_commit!==fixedCommit||ref.source_url!==licenseUrl)return fail();
  mids.push(ref.material_id);
 }
 const points=[...c.license_text];
 for(const clause of v.clauses){
  if(!obj(clause)||!mids.includes(clause.material_id)||typeof clause.quote!=='string'||!clause.quote||!count(clause.start)||!count(clause.end)||clause.end<=clause.start
   ||points.slice(clause.start,clause.end).join('')!==clause.quote||!count(clause.line_start)||!count(clause.line_end)||clause.line_start!==points.slice(0,clause.start).join('').split('\n').length
   ||clause.line_end!==points.slice(0,clause.end).join('').split('\n').length||clause.category!=='quoted_condition_not_applicability_decision')return fail();
 }
 const codes=['CHECK_EXACT_SOURCE_SCOPE','CHECK_MODIFIED_FILES','CHECK_PLANNED_DELIVERY','CHECK_SERVICE_DELIVERY_BOUNDARY'];
 if(new Set(v.actions.map((action:any)=>action.code)).size!==v.actions.length)return fail();
 for(const action of v.actions)if(!obj(action)||!codes.includes(action.code)||typeof action.text!=='string'||!action.text.startsWith('核对')||action.text.length>300
  ||action.claim_level!=='verification_action_only'||!ids(action.source_material_ids)||!action.source_material_ids.length||!action.source_material_ids.every((mid:string)=>mids.includes(mid))
  ||!Array.isArray(action.clause_indices)||!action.clause_indices.length||!action.clause_indices.every((n:unknown)=>count(n)&&n<v.clauses.length&&action.source_material_ids.includes(v.clauses[n].material_id))
  ||!ids(action.usage_fields)||!action.usage_fields.every((key:string)=>Object.prototype.hasOwnProperty.call(r.usage,key)&&r.usage[key as keyof Result['usage']]===true))return fail();
 return v as LocalActions;
}

function stableJson(value:unknown):string{
 if(Array.isArray(value))return '['+value.map(stableJson).join(',')+']';
 if(obj(value))return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stableJson(value[k])).join(',')+'}';
 return JSON.stringify(value);
}
export async function verifyLocalActionsHash(value:LocalActions){
 const {content_sha256,...payload}=value,bytes=new TextEncoder().encode(stableJson(payload));
 const result=await crypto.subtle.digest('SHA-256',bytes);
 if([...new Uint8Array(result)].map(x=>x.toString(16).padStart(2,'0')).join('')!==content_sha256)return fail();
}

export function validateOfficialSources(v:unknown,a:Assessment,r:Result):OfficialSources {
 current(a,r);
 if(!obj(v)||v.schema_version!=='openguard-official-sources/1'||v.result_id!==r.result_id||v.result_sha256!==r.result_sha256||!sameBinding(validateBinding(v.binding,a),r.binding)
  ||!obj(v.fetch)||!['not_scheduled','queued','running','ready','partial','failed','outcome_unknown','unsupported'].includes(v.fetch.state)
  ||!(v.fetch.job_id===null||id(v.fetch.job_id))||!(v.fetch.error_code===null||typeof v.fetch.error_code==='string')
  ||!['http_intents','http_dispatched','http_responses'].every(k=>count(v.fetch[k]))||v.fetch.http_intents>6||v.fetch.http_dispatched>v.fetch.http_intents||v.fetch.http_responses>v.fetch.http_dispatched
  ||!obj(v.analysis)||!['not_scheduled','waiting_source','queued','running','ready','failed','outcome_unknown'].includes(v.analysis.state)
  ||![null,'unadopted_preview','saved_material'].includes(v.analysis.mode)||!(v.analysis.error_code===null||typeof v.analysis.error_code==='string')
  ||!(v.analysis.analysis_id===null||id(v.analysis.analysis_id))||!ids(v.adopted_material_ids)||!v.adopted_material_ids.every(x=>r.material_ids.includes(x)))return fail();
 if(v.candidate!==null){
  const c=v.candidate;
  if(!obj(c)||!id(c.candidate_id)||c.scan_id!==a.scan_id||!obj(c.subject)||c.subject.version!=='14.1.2'||!r.resources.some(x=>x.subject.resource_id===c.subject.resource_id&&x.subject.version===c.subject.version)
   ||c.commit!==fixedCommit||r.binding.project_revision!==fixedCommit||c.adoption_status!=='not_adopted'||typeof c.license_text!=='string'||new TextEncoder().encode(c.license_text).length!==1124
   ||!texts(c.limitations)||!Array.isArray(c.sources)||!Array.isArray(c.source_failures))return fail();
  const partial=c.coverage==='partial_git_license_only';
  if(partial){
   const f=c.source_failures[0];
   if(c.npm_metadata_status!=='missing_404'||c.sources.length!==1||c.sources[0]?.url!==licenseUrl||c.source_failures.length!==1
    ||!obj(f)||f.kind!=='npm_metadata'||f.url!==metadataUrl||f.http_status!==404||f.error_code!=='upstream_404'||f.request_number!==6||!date(f.retrieved_at)
    ||v.fetch.state!=='partial'||v.fetch.retrieval_status!=='failed'||v.fetch.error_code!=='upstream_404'||v.fetch.http_intents!==6||v.fetch.http_dispatched!==6||v.fetch.http_responses!==6)return fail();
  }else if(c.coverage!=='complete_fixed_sources'||c.npm_metadata_status!=='observed'||c.source_failures.length||c.sources.length!==2||new Set(c.sources.map((s:any)=>s.url)).size!==2)return fail();
  for(const s of c.sources){
   if(!obj(s)||typeof s.kind!=='string'||![licenseUrl,metadataUrl].includes(s.url)||!sha(s.sha256)||!count(s.byte_count)||s.byte_count<1||s.byte_count>32768
    ||s.kind!==(s.url===licenseUrl?'git_license':'npm_metadata')||typeof s.source_level!=='string'||!s.source_level||s.verification_state!=='pending'||(s.retrieved_at!==undefined&&s.retrieved_at!==null&&!date(s.retrieved_at)))return fail();
   if(s.url===licenseUrl&&(s.sha256!==fixedLicenseHash||s.byte_count!==1124))return fail();
  }
 }
 const p=v.analysis.preview;
 if(p!==null){
  const c=v.candidate;
  const structured=obj(p)&&p.analysis_protocol==='openguard-qwen-action-plan/2';
  if(!c||!obj(p)||p.schema_version!=='openguard-official-source-preview/1'||!id(p.preview_id)||!sha(p.preview_sha256)||p.result_id!==r.result_id||p.result_sha256!==r.result_sha256
   ||!sameBinding(validateBinding(p.binding,a),r.binding)||!['succeeded','failed'].includes(p.status)||!date(p.created_at)||!(structured?[0,1,2]:[0,1]).includes(p.model_calls)
   ||!obj(p.model)||!['name','runtime'].every(k=>typeof p.model[k]==='string'&&p.model[k])||!sha(p.model.digest)||!obj(p.metrics)||typeof p.metrics.elapsed_ms!=='number'||p.metrics.elapsed_ms<0
   ||!Array.isArray(p.clauses)||!Array.isArray(p.actions)||!Array.isArray(p.changes)||!texts(p.limitations)||v.analysis.mode!=='unadopted_preview')return fail();
  if(p.coverage!==c.coverage||p.npm_metadata_status!==c.npm_metadata_status||JSON.stringify(p.source_failures)!==JSON.stringify(c.source_failures))return fail();
  if(p.status==='succeeded'&&(!(structured?[1,2]:[1]).includes(p.model_calls)||!p.clauses.length||!p.actions.length))return fail();
  if(p.status==='failed'&&(p.clauses.length||p.actions.length||p.changes.length))return fail();
  for(const q of p.clauses)if(!obj(q)||q.source_candidate_id!==c.candidate_id||typeof q.quote!=='string'||!q.quote||!count(q.start)||!count(q.end)||q.end<=q.start
   ||[...c.license_text].slice(q.start,q.end).join('')!==q.quote||!['permission','condition','disclaimer','other'].includes(q.category))return fail();
  if(structured&&p.status==='succeeded')validateBoundPlan(p,a,r,[{id:c.candidate_id,subject:c.subject,sha256:fixedLicenseHash,text:c.license_text}],p.clauses,p.actions);
  else for(const action of p.actions)if(!obj(action)||typeof action.text!=='string'||!action.text||action.claim_level!=='verification_action_only'||!ids(action.source_candidate_ids)||action.source_candidate_ids.length!==1||action.source_candidate_ids[0]!==c.candidate_id)return fail();
  for(const change of p.changes)if(!obj(change)||typeof change.field!=='string'||!change.field||!('before'in change)||!('after'in change)||typeof change.explanation!=='string'||!change.explanation)return fail();
  if(p.previous_result!=null&&(!obj(p.previous_result)||!id(p.previous_result.result_id)||!sha(p.previous_result.result_sha256)||!obj(p.previous_result.binding)||p.previous_result.binding.scan_id!==a.scan_id||p.previous_result.binding.project_revision!==r.binding.project_revision||typeof p.previous_result.selection!=='string'))return fail();
 }
 if(v.analysis.mode==='saved_material'&&p!==null)return fail();
 if(v.analysis.state==='ready'&&!(v.analysis.mode==='saved_material'?id(v.analysis.analysis_id):p?.status==='succeeded'))return fail();
 if(v.runtime_jobs_enabled!==undefined&&typeof v.runtime_jobs_enabled!=='boolean')return fail();
 if(v.explicit_fetch!==undefined){
  const x=v.explicit_fetch,q=x?.request;
  if(!obj(x)||typeof x.allowed!=='boolean'||typeof x.reason!=='string'||!x.reason||!(q===undefined||q===null||obj(q)))return fail();
  // A scan-level request may belong to an earlier fixed Result. It is trace only;
  // it cannot authenticate the current Result or authorize another acquisition.
  if(q!=null&&(!obj(q)||!id(q.idempotency_key)||q.state!=='accepted'||!date(q.requested_at)||!id(q.job_id)||!id(q.result_id)||!sha(q.result_sha256)||x.allowed))return fail();
 }
 if(v.local_actions!==undefined)validateLocalActions(v.local_actions,a,r,v.candidate);
 return v as OfficialSources;
}

async function transport(path:string,method:'GET'|'POST',body?:string,signal?:AbortSignal,permit?:()=>boolean,onDispatch?:()=>void,expectedStatus=method==='POST'?201:200):Promise<unknown>{
 const c=new AbortController(),timer=window.setTimeout(()=>c.abort(),30000),abort=()=>c.abort();signal?.addEventListener('abort',abort,{once:true});
 try{
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  const options=accountRequestOptions({method,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},body,cache:'no-store',signal:c.signal});
  if(method==='POST'&&!permit?.())throw Error('当前对象或操作许可已变化，未发送资料操作请求。');
  onDispatch?.();const response=await fetch(base+path,options);handleAccountResponse(response.status);const value=await response.json().catch(()=>null);
  if(!response.ok)throw new ApiError(response.status,`资料请求未完成（HTTP ${response.status}）。`+(value?.error?.message??''),value?.error?.code);
  if(response.status!==expectedStatus)throw Error('资料回执状态异常，请先读取保存结果。');return value;
 }finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
export async function readOfficialSources(a:Assessment,r:Result,signal?:AbortSignal){
 current(a,r);
 const value=validateOfficialSources(await transport(prefix(a)+'?'+new URLSearchParams({assessment_version:String(a.version),result_id:r.result_id}),'GET',undefined,signal),a,r);
 if(value.candidate){const bytes=new TextEncoder().encode(value.candidate.license_text),digest=await crypto.subtle.digest('SHA-256',bytes);if([...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('')!==fixedLicenseHash)return fail();}
 if(value.local_actions)await verifyLocalActionsHash(value.local_actions);
 if(value.analysis.preview)await verifyBoundPlanHashes(value.analysis.preview);
 const request=value.explicit_fetch?.request,pending=pendingOfficialFetch(r),key=fetchStorageKey(r);
 if(request&&pending&&key&&request.idempotency_key===pending.body.idempotency_key&&request.result_id===r.result_id&&request.result_sha256===r.result_sha256&&pending.state!=='accepted')saveFetch(key,{...pending,state:'accepted',error_code:null});
 return value;
}
export async function requestOfficialFetch(a:Assessment,r:Result,value:OfficialSources,permit:()=>boolean):Promise<OfficialSources>{
 current(a,r);validateOfficialSources(value,a,r);
 if(!canRequestOfficialFetch(value))throw Error('当前任务不满足本轮明确联网范围；已有来源不重复获取。');
 const owner=accountOwner(),key=fetchStorageKey(r,owner);if(!owner||!key)throw Error('无法建立本账号的联网请求记录，未发送请求。');
 if(pendingOfficialFetch(r)||fetchInFlight.has(key))throw Error('本次联网请求已有记录；请仅刷新状态核对，不会重新发送。');
 const allowed=()=>accountOwner()===owner&&permit();if(!allowed())throw Error('当前对象或联网许可已变化，未发送请求。');
 const body={binding:{...r.binding},result_id:r.result_id,result_sha256:r.result_sha256,idempotency_key:crypto.randomUUID()};
 const row:PendingOfficialFetch={body,serialized:JSON.stringify(body),state:'sent',error_code:null};saveFetch(key,row);fetchInFlight.add(key);let sent=false;
 try{
  const response=await transport(prefix(a)+'/fetch','POST',row.serialized,undefined,allowed,()=>{sent=true;},202);
  const status=validateOfficialSources(response,a,r),request=status.explicit_fetch?.request;
  if(request?.idempotency_key!==body.idempotency_key||request.result_id!==r.result_id||request.result_sha256!==r.result_sha256)return fail();row.state='accepted';saveFetch(key,row);return status;
 }catch(error){
  if(!sent)sessionStorage.removeItem(key);
  else {row.state=error instanceof ApiError&&[400,401,403,404,409,413,415,422].includes(error.status)?'rejected':'unknown';row.error_code=error instanceof ApiError?error.code??null:null;saveFetch(key,row);}
  throw error;
 }finally{fetchInFlight.delete(key);}
}
export function pendingOfficialAdoption(r:Result):PendingOfficialAdoption|null{
 const key=storageKey(r);if(!key)return null;
 const raw=sessionStorage.getItem(key);if(raw===null)return null;
 let value:unknown;try{value=JSON.parse(raw);}catch{throw Error('本账号采用请求记录损坏；未发送请求，请保留现场核对。');}
 if(!obj(value)||!obj(value.body)||typeof value.serialized!=='string'||JSON.stringify(value.body)!==value.serialized
  ||!sameBinding(value.body.binding,r.binding)||value.body.result_id!==r.result_id||value.body.result_sha256!==r.result_sha256
  ||value.body.parent_result_id!==r.result_id||value.body.expected_revision!==r.revision||!id(value.body.candidate_id)||!id(value.body.idempotency_key)
  ||Object.keys(value.body).sort().join(',')!=='binding,candidate_id,expected_revision,idempotency_key,parent_result_id,result_id,result_sha256'
  ||!obj(value.subject)||!r.resources.some(row=>row.subject.resource_id===value.subject.resource_id&&row.subject.version===value.subject.version)
  ||!['sent','unknown','conflict','rejected'].includes(value.state)||typeof value.checked!=='boolean'
  ||!(value.checked_head_id===null||id(value.checked_head_id))||!(value.checked_head_revision===null||count(value.checked_head_revision)))return fail();
 const row=value as PendingOfficialAdoption;
 // A previous document's in-flight request has an unknown outcome after reload.
 // Never automatically resend it or treat it as an active connection.
 if(row.state==='sent'&&!inFlight.has(key)){row.state='unknown';row.checked=false;savePending(key,row);}
 return row;
}
export function canReplayOfficialAdoption(r:Result){const p=pendingOfficialAdoption(r);return !!p&&p.state==='unknown'&&p.checked;}
export function canEndOfficialAdoption(r:Result){const p=pendingOfficialAdoption(r);return !!p&&p.state!=='sent'&&p.checked;}
function validateCandidate(candidate:OfficialCandidate,a:Assessment,r:Result){
 if(!id(candidate.candidate_id)||candidate.scan_id!==a.scan_id||candidate.commit!==fixedCommit||candidate.adoption_status!=='not_adopted'||candidate.subject.version!=='14.1.2'||!r.resources.some(row=>row.subject.resource_id===candidate.subject.resource_id&&row.subject.version===candidate.subject.version))return fail();
}
function adoptionReceipt(value:unknown,a:Assessment,r:Result,subject:Subject){
 const receipt=validateReceipt(value,a,r.binding),next=receipt.result,m=receipt.material;
 if(!m||receipt.answer!==null||next.revision!==r.revision+1||next.previous_result_id!==r.result_id||m.source_sha256!==fixedLicenseHash||m.byte_count!==1124
  ||m.subject.resource_id!==subject.resource_id||m.subject.version!==subject.version||next.material_ids.length!==r.material_ids.length+1
  ||!r.material_ids.every(x=>next.material_ids.includes(x))||m.verification_state!=='pending'||m.source_level!=='user_supplied_unverified')return fail();
 return receipt;
}
async function sendAdoption(a:Assessment,r:Result,row:PendingOfficialAdoption,permit:()=>boolean):Promise<Receipt>{
 const owner=accountOwner(),key=storageKey(r,owner);if(!owner||!key)throw Error('尚未建立本账号的请求记录，未发送采用请求。');
 const allowed=()=>accountOwner()===owner&&permit();
 if(!allowed()||inFlight.has(key))throw Error('当前对象、账号或采用许可已变化，未发送请求。');
 row={...row,state:'sent',checked:false,checked_head_id:null,checked_head_revision:null};
 // Durable intent before dispatch. No permissive fallback when storage is unavailable.
 savePending(key,row);inFlight.add(key);let sent=false;
 try{
  const receipt=adoptionReceipt(await transport(prefix(a)+'/adopt','POST',row.serialized,undefined,allowed,()=>{sent=true;}),a,r,row.subject);
  removePending(key);if(accountOwner()!==owner)throw Error('原账号的采用回执已保存；当前账号视图不接纳此回执。');return receipt;
 }catch(e){
  if(!sent)removePending(key);
  else if(sessionStorage.getItem(key)!==null){row.state=e instanceof ApiError&&e.status===409?'conflict':e instanceof ApiError&&[400,401,403,404,413,415,422].includes(e.status)?'rejected':'unknown';savePending(key,row);}
  throw e;
 }finally{inFlight.delete(key);}
}
export async function adoptOfficialSources(a:Assessment,r:Result,candidate:OfficialCandidate,permit:()=>boolean):Promise<Receipt>{
 current(a,r);validateCandidate(candidate,a,r);if(pendingOfficialAdoption(r))throw Error('原采用请求仍待确认，请先核对保存结果；不会自动重发。');
 if(!permit())throw Error('当前对象或采用许可已变化，未发送材料采用请求。');
 const body:AdoptionRequest={binding:{...r.binding},candidate_id:candidate.candidate_id,result_id:r.result_id,result_sha256:r.result_sha256,expected_revision:r.revision,parent_result_id:r.result_id,idempotency_key:crypto.randomUUID()};
 return sendAdoption(a,r,{body,serialized:JSON.stringify(body),subject:{...candidate.subject},state:'unknown',checked:false,checked_head_id:null,checked_head_revision:null},permit);
}
/** Read-only recovery cannot prove a particular idempotency key from a head DTO.
 * It records the checked head, then enables explicit same-body recovery or local ending. */
export async function recoverOfficialAdoption(a:Assessment,r:Result){
 current(a,r);const owner=accountOwner(),key=storageKey(r,owner),old=pendingOfficialAdoption(r);
 if(!key||!old||old.state==='sent')throw Error('没有可核对的待确认请求。');
 savePending(key,{...old,checked:false});
 const binding=await readBinding(a);if(!sameBinding(binding,r.binding)||!sameBinding(binding,old.body.binding))return fail();
 const index=await readIndex(a),head=index.head_result_id?await readResult(a,binding,index.head_result_id):null;
 if(head&&head.revision!==index.head_revision)return fail();
 const latest=pendingOfficialAdoption(r);
 if(accountOwner()!==owner||!latest||latest.serialized!==old.serialized||latest.state==='sent')throw Error('账号或原请求状态已变化，核对结果未接入当前视图。');
 const row={...latest,checked:true,checked_head_id:head?.result_id??null,checked_head_revision:head?.revision??0};savePending(key,row);
 return{pending:row,index,result:head};
}
export async function replayOfficialAdoption(a:Assessment,r:Result,candidate:OfficialCandidate,permit:()=>boolean){
 current(a,r);validateCandidate(candidate,a,r);const row=pendingOfficialAdoption(r);
 if(!row||row.state!=='unknown'||!row.checked||row.body.candidate_id!==candidate.candidate_id||row.subject.resource_id!==candidate.subject.resource_id||row.subject.version!==candidate.subject.version)throw Error('请先核对原请求；明确拒绝或冲突不允许重放。');
 return sendAdoption(a,r,row,permit);
}
export function endOfficialAdoption(r:Result){
 const key=storageKey(r),row=pendingOfficialAdoption(r);if(!key||!row||row.state==='sent'||!row.checked)throw Error('请先只读核对服务器结果，再明确结束原请求。');
 removePending(key);
}
