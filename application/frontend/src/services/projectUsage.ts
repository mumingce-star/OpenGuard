import { createAssessment, getJob, presets, readExactAssessment, usageFields, type Assessment, type Job, type Usage } from './assessments';
import { clearPendingWrite, prepareWrite, readBinding, readIndex, readResult, recoverWrite, submitWrite, validateResult, type Binding, type PendingWrite, type Result } from './p2';
import { ApiError } from './scans';

/** Project uses are Assessment inputs. Resource-level L2 answers retain their original meaning. */
export type UsageUpdateOperation = Readonly<{requestId:string;scanId:string;sourceAssessmentId:string;sourceVersion:number;usage:Readonly<Usage>}>;
export type UsageUpdateOutcome = {phase:'pending'|'saved'|'complete'|'blocked';assessment?:Assessment;result?:Result;errorCode?:string;message:string;canSubmitOriginal?:boolean};
/** Per-call UI capability; never serialized into requests, pending state or storage. */
export type UsageWritePermit = () => boolean;
export class ProjectUsageError extends Error { constructor(public code:string, message:string){super(message);this.name='ProjectUsageError';} }
type Anchor = {scanId:string;assessmentId:string;version:number;factsHash:string;ruleVersion:string;resourceIds:string[];usage:Usage};
type Stored = {schema:1;anchor:Anchor;requestId:string;usage:Usage;assessmentAttempted:boolean;p2Attempted:boolean;complete:boolean};
type State = {op:UsageUpdateOperation;stored:Stored;assessment?:Assessment;pending?:PendingWrite;binding?:Binding;outcome?:UsageUpdateOutcome;flight?:Promise<UsageUpdateOutcome>};
const fields=Object.keys(usageFields) as (keyof typeof usageFields)[];
const operations=new Map<string,State>();
const states=new WeakMap<UsageUpdateOperation,State>();
const keyFor=(scan:string,id:string)=>`openguard:project-usage:1:${scan}:${id}`;
const isObject=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const validId=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const fail=(code:string,message:string):never=>{throw new ProjectUsageError(code,message);};
function normalizedUsage(v:unknown,complete=true):Usage {
 if(!isObject(v)||typeof v.preset!=='string'||!Object.prototype.hasOwnProperty.call(presets,v.preset)||Object.keys(v).some(k=>!['preset','declared_at',...fields].includes(k))||fields.some(k=>!(v[k]===true||v[k]===false||v[k]===null||(!complete&&v[k]===undefined))))return fail('USAGE_INVALID','请为七项项目用途分别选择是、否或暂不确定。');
 return {preset:v.preset as Usage['preset'],...Object.fromEntries(fields.map(k=>[k,v[k]??null]))};
}
const sameUsage=(a:Usage,b:Usage)=>a.preset===b.preset&&fields.every(k=>(a[k]??null)===(b[k]??null));
function anchorFor(a:Assessment):Anchor {
 if(!validId(a.scan_id)||!validId(a.id)||!Number.isSafeInteger(a.version)||a.version<1||!/^([a-f0-9]{64})$/.test(a.facts_hash)||typeof a.rule_version!=='string'||!a.rule_version||!Array.isArray(a.resource_ids)||!a.resource_ids.every(validId)||new Set(a.resource_ids).size!==a.resource_ids.length)return fail('USAGE_SOURCE_INVALID','当前评估身份不完整，请重新读取准确版本。');
 return {scanId:a.scan_id,assessmentId:a.id,version:a.version,factsHash:a.facts_hash,ruleVersion:a.rule_version,resourceIds:[...a.resource_ids],usage:normalizedUsage(a.usage??{preset:'unknown'},false)};
}
function storageRead(key:string):string|null {try{return sessionStorage.getItem(key);}catch{return fail('USAGE_STORAGE_UNAVAILABLE','浏览器无法保存本次操作标识，请允许会话存储后再保存。');}}
function persist(s:State){try{sessionStorage.setItem(keyFor(s.op.scanId,s.op.sourceAssessmentId),JSON.stringify(s.stored));}catch{fail('USAGE_STORAGE_UNAVAILABLE','本次操作标识未能保存；不会发起新的写入，请保留当前页面。');}}
function register(stored:Stored):State {
 const op=Object.freeze({requestId:stored.requestId,scanId:stored.anchor.scanId,sourceAssessmentId:stored.anchor.assessmentId,sourceVersion:stored.anchor.version,usage:Object.freeze({...stored.usage})});
 const state:State={op,stored};states.set(op,state);operations.set(keyFor(op.scanId,op.sourceAssessmentId),state);return state;
}
/** Only minimal IDs, uses and call-intent flags persist; no evidence, material or model text. */
export function readPendingUsageUpdate(a:Assessment):UsageUpdateOperation|null {
 const anchor=anchorFor(a),key=keyFor(a.scan_id,a.id),active=operations.get(key);
 if(active){if(JSON.stringify(active.stored.anchor)!==JSON.stringify(anchor))return fail('USAGE_SOURCE_CHANGED','原评估身份发生变化，已停止恢复操作。');return active.stored.complete?null:active.op;}
 const raw=storageRead(key);if(raw===null)return null;
 let value:unknown;try{value=JSON.parse(raw);}catch{return fail('USAGE_STORAGE_INVALID','会话操作记录损坏；请按原请求编号核对后端结果，不要重复保存。');}
 if(!isObject(value)||value.schema!==1||JSON.stringify(value.anchor)!==JSON.stringify(anchor)||typeof value.requestId!=='string'||!/^[A-Za-z0-9_-]{8,90}$/.test(value.requestId)||typeof value.assessmentAttempted!=='boolean'||typeof value.p2Attempted!=='boolean'||typeof value.complete!=='boolean'||(value.p2Attempted&&!value.assessmentAttempted)||Object.keys(value).length!==7)return fail('USAGE_STORAGE_INVALID','会话记录与当前评估不一致，已停止恢复。');
 const usage=normalizedUsage(value.usage);if(sameUsage(usage,anchor.usage))return fail('USAGE_STORAGE_INVALID','会话记录未包含用途变更。');
 const state=register({...value,usage} as Stored);return state.stored.complete?null:state.op;
}
export function beginUsageUpdate(a:Assessment,usage:Usage,requestId:string):UsageUpdateOperation {
 const normalized=normalizedUsage(usage),anchor=anchorFor(a);
 if(sameUsage(anchor.usage,normalized))return fail('USAGE_UNCHANGED','项目用途没有变化，无需重复保存。');
 if(!/^[A-Za-z0-9_-]{8,90}$/.test(requestId))return fail('USAGE_REQUEST_INVALID','本次请求编号无效，尚未发送。');
 const pending=readPendingUsageUpdate(a);
 if(pending){if(pending.requestId===requestId&&sameUsage(pending.usage,normalized))return pending;return fail('USAGE_OPERATION_PENDING','上一份用途变更仍待确认，请先核对其保存结果。');}
 const state=register({schema:1,anchor,requestId,usage:normalized,assessmentAttempted:false,p2Attempted:false,complete:false});
 try{persist(state);}catch(e){operations.delete(keyFor(a.scan_id,a.id));states.delete(state.op);throw e;}return state.op;
}
function blocked(s:State,code:string,message:string):UsageUpdateOutcome {return {phase:s.assessment?'saved':'blocked',...(s.assessment?{assessment:s.assessment}:{}),...(!s.stored.assessmentAttempted?{canSubmitOriginal:true}:{}),errorCode:code,message};}
function requireWritePermit(canWrite?:UsageWritePermit) {
 if(canWrite===undefined)return;
 let allowed=false;try{allowed=canWrite()===true;}catch{/* A failed capability check cannot grant a write. */}
 if(!allowed)fail('USAGE_WRITE_PERMISSION_REVOKED','当前操作已暂停新写入；原请求身份已保留。恢复可写后，请明确继续原请求。');
}
function errorOutcome(s:State,e:unknown):UsageUpdateOutcome {
 const code=e instanceof ProjectUsageError?e.code:e instanceof ApiError&&e.status===404?'USAGE_REQUEST_UNCONFIRMED':'USAGE_READ_OR_SAVE_UNCONFIRMED';
 if(code==='USAGE_WRITE_PERMISSION_REVOKED')return blocked(s,code,e instanceof Error?e.message:'当前操作已暂停新写入，原请求身份已保留。');
 return blocked(s,code,s.assessment?'项目用途已保存。用途核对结果尚未确认，可先查看已保存评估；不会重复创建评估。':code==='USAGE_REQUEST_UNCONFIRMED'?'原请求暂未读到，保存状态尚未确认。保留同一请求编号，只读核对，不重复提交。':e instanceof ProjectUsageError?e.message:'保存状态尚未确认，请使用“核对保存结果”读取原请求，避免重复提交。');
}
function getState(op:UsageUpdateOperation):State {const s=states.get(op);if(!s)return fail('USAGE_OPERATION_INVALID','请恢复或重新准备当前页面的项目用途操作。');return s;}
function single(s:State,action:()=>Promise<UsageUpdateOutcome>):Promise<UsageUpdateOutcome> {
 if(s.flight)return s.flight;
 s.flight=Promise.resolve().then(action).catch(e=>errorOutcome(s,e)).then(outcome=>{s.outcome=outcome;return outcome;}).finally(()=>{s.flight=undefined;});return s.flight;
}
function verifySaved(s:State,a:Assessment,expectedId:string) {
 const b=s.stored.anchor,u=normalizedUsage(a.usage);
 anchorFor(a); // Validate safe version and unique resource closure before any P2 request.
 if(a.id!==expectedId||a.scan_id!==b.scanId||a.facts_hash!==b.factsHash||a.rule_version!==b.ruleVersion||!sameUsage(u,s.stored.usage)||a.resource_ids.length!==b.resourceIds.length||a.resource_ids.some(id=>!b.resourceIds.includes(id)))return fail('USAGE_RESULT_BINDING_MISMATCH','服务器返回的评估与本次用途、扫描事实或对象不一致，已停止后续写入。');
 // Cache reuse may return an earlier immutable Assessment. Never invent version + 1.
}
async function finishJob(s:State,job:Job,canWrite?:UsageWritePermit):Promise<UsageUpdateOutcome> {
 if(job.status==='pending')return {phase:'pending',message:'项目用途正在保存；可核对进度，原评估继续保留。'};
 if(job.status==='failed')return blocked(s,'USAGE_JOB_FAILED','后端未完成本次评估，请保留原请求编号和旧版本供核对。');
 const a=await readExactAssessment(s.op.scanId,job.assessment_id!);verifySaved(s,a,job.assessment_id!);s.assessment=a;
 requireWritePermit(canWrite);
 return ensureP2(s,a,canWrite);
}
async function ensureP2(s:State,a:Assessment,canWrite?:UsageWritePermit):Promise<UsageUpdateOutcome> {
 let b:Binding,index,result:Result|null;
 if(s.stored.p2Attempted&&s.pending&&s.binding){
  const recovered=await recoverWrite(a,s.binding,s.pending);b=s.binding;index=recovered.index;result=recovered.result;
  requireWritePermit(canWrite);
 }else{
  b=await readBinding(a);requireWritePermit(canWrite);
  index=await readIndex(a);requireWritePermit(canWrite);
  result=index.head_result_id?await readResult(a,b,index.head_result_id):null;requireWritePermit(canWrite);
 }
 if(result&&result.revision!==index.head_revision)return fail('USAGE_P2_BINDING_MISMATCH','用途核对结果与版本索引不一致，已停止。');
 if(!result){
  if(s.stored.p2Attempted)return blocked(s,'USAGE_P2_UNCONFIRMED','项目用途已保存，但用途核对结果尚未确认；不会自动重放写入。');
  // From this final check through intent registration and submitWrite/request/fetch
  // there is no await: a rejected permit cannot leave an unsent attempted latch.
  requireWritePermit(canWrite);
  s.binding=b;s.pending=prepareWrite('results',b,null,'usage_'+s.op.requestId);s.stored.p2Attempted=true;persist(s);
  result=(await submitWrite(a,b,s.pending)).result;
  // A POST already dispatched keeps its real receipt, even if permission changed while awaiting it.
 }
 if(s.pending&&s.stored.p2Attempted){
  // A read-only recovery confirmed an existing head; release this tab's P2 latch.
  // A successful submit already releases it in p2.ts.
  if(result&&index.head_result_id)clearPendingWrite(a);
  s.pending=undefined;
 }
 s.stored.complete=true;persist(s);
 return {phase:'complete',assessment:a,result,message:'项目用途与对应结果已保存，旧版本可继续查看。'};
}
/** Explicit click only. Even transport failure consumes this operation's single Assessment POST. */
export function submitUsageUpdate(op:UsageUpdateOperation,canWrite?:UsageWritePermit):Promise<UsageUpdateOutcome> {
 const s=getState(op);return single(s,async()=>{
  if(s.stored.complete&&s.outcome?.phase==='complete')return s.outcome;
  if(s.stored.assessmentAttempted)return continueRead(s,canWrite);
  requireWritePermit(canWrite);
  s.stored.assessmentAttempted=true;persist(s);
  const job=await createAssessment(op.scanId,s.stored.usage,op.requestId);
  // Consume the actual job/Assessment after a sent POST; gate only subsequent new writes.
  return finishJob(s,job,canWrite);
 });
}
async function continueRead(s:State,canWrite?:UsageWritePermit):Promise<UsageUpdateOutcome> {
 if(!s.stored.assessmentAttempted)return blocked(s,'USAGE_NOT_SUBMITTED','本次用途尚未提交，请先明确保存。');
 if(s.stored.complete&&s.outcome?.phase==='complete')return s.outcome;
 const job=await getJob(s.op.scanId,s.op.requestId);requireWritePermit(canWrite);
 return finishJob(s,job,canWrite);
}
/** No Assessment POST, including after refresh, unknown response, 404 or repeated clicks. */
export function continueUsageUpdate(op:UsageUpdateOperation,canWrite?:UsageWritePermit):Promise<UsageUpdateOutcome> {const s=getState(op);return single(s,()=>continueRead(s,canWrite));}
export function projectUsageUrl(a:Assessment,result?:Result,currentSearch=''):string {
 anchorFor(a);
 if(result)validateResult(result,a,result.binding,result.result_id);
 const q=new URLSearchParams(currentSearch);
 for(const key of ['assessment_id','assessment_version','snapshot_id','report_id','p2_result','p2_result_id','p2_revision'])q.delete(key);
 q.set('mode','api');q.set('assessment_id',a.id);q.set('assessment_version',String(a.version));
 if(result){q.set('p2_result',result.result_id);q.set('p2_revision',String(result.revision));}
 return `/app/scans/${encodeURIComponent(a.scan_id)}/assessment?${q.toString()}`;
}
