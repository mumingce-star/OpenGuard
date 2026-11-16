import {request} from './scans';
import type {Evidence} from '../types/domain';
import type {Assessment} from './assessments';
export const reviewLabels={AI_HIGH_CONFIDENCE:'AI高置信研判',AI_ASSISTED:'AI辅助研判',NEEDS_USER_FACT:'仍需你确认',NEEDS_EXPERT_REVIEW:'冲突／专家复核',INSUFFICIENT_BASIS:'依据不足'} as const;
export type ReviewStatus=keyof typeof reviewLabels;
export type ReviewItem={judgment_code?:string;uncertainty_codes?:string[];item_id:string;resource_ids:string[];name:string;version:string|null;ai_status:ReviewStatus;confidence_band:'HIGH'|'MEDIUM'|'LOW';reason_summary:string;remaining_uncertainty:string;recommended_action:string;evidence_ids:string[];source_locators:string[];dimension:string;blocker_id:string;source_gap:string;formal_effect:'none'};
type Binding={scan_id:string;assessment_id:string;assessment_version:number;facts_hash:string;usage_hash:string;rule_version:string;namespace:string;input_digest:string};
type ReviewJob={job_id:string;status:string;error?:string;binding:Binding;snapshot_id?:string};
export type ReviewState={binding:Binding;job:ReviewJob|null;snapshot:{snapshot_id:string;binding:Binding;result:{formal_effect:'none';formal_changes:false;items:ReviewItem[];summary:{scope_unique_resources:number;ai_scope_unique_resources:number;total_items:number;unique_resource_count:number;item_counts:Record<ReviewStatus,number>;questions:{question_key:string;text:string;why_needed_zh?:string;item_ids:string[];resource_ids:string[]}[]};deterministic_context:{supported_resource_ids:string[];note:string}}}|null};
const obj=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const strs=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(x=>typeof x==='string');
const fail=():never=>{throw new Error('AI研判身份或内容不匹配；原评估保留。');};
function match(b:unknown,a:Assessment,namespace='ai-autonomous-review/1'){return obj(b)&&b.namespace===namespace&&b.scan_id===a.scan_id&&b.assessment_id===a.id&&b.assessment_version===a.version&&b.facts_hash===a.facts_hash&&b.usage_hash===(a as Assessment&{usage_hash:string}).usage_hash&&b.rule_version===a.rule_version&&typeof b.input_digest==='string';}
export function validateReview(x:unknown,a:Assessment,namespace='ai-autonomous-review/1'):ReviewState {
 if(!obj(x)||!match(x.binding,a,namespace))return fail();
 if(x.job!==null&&(!obj(x.job)||!match(x.job.binding,a,namespace)||typeof x.job.job_id!=='string'||!['queued','running','completed','failed','cancelled','interrupted'].includes(String(x.job.status))))return fail();
 if(obj(x.job)&&obj(x.job.binding)&&obj(x.binding)&&x.job.binding.input_digest!==x.binding.input_digest)return fail();
 if(x.snapshot!==null){
  const s=x.snapshot;if(!obj(s)||!match(s.binding,a,namespace)||typeof s.snapshot_id!=='string'||!obj(s.result))return fail();
  if(!obj(x.job)||x.job.status!=='completed'||x.job.snapshot_id!==s.snapshot_id||!obj(s.binding)||!obj(x.binding)||s.binding.input_digest!==x.binding.input_digest)return fail();
  const r=s.result;if(!obj(r.binding)||r.binding.input_digest!==s.binding.input_digest||!match(r.binding,a,namespace))return fail();
  if(r.formal_effect!=='none'||r.formal_changes!==false||!Array.isArray(r.items)||!obj(r.summary)||!obj(r.summary.item_counts)||!Array.isArray(r.summary.questions)||!obj(r.deterministic_context)||!strs(r.deterministic_context.supported_resource_ids))return fail();
  if(!r.items.every(i=>obj(i)&&typeof i.item_id==='string'&&typeof i.name==='string'&&strs(i.resource_ids)&&String(i.ai_status) in reviewLabels&&['HIGH','MEDIUM','LOW'].includes(String(i.confidence_band))&&i.formal_effect==='none'&&(i.judgment_code===undefined||typeof i.judgment_code==='string')&&(i.uncertainty_codes===undefined||strs(i.uncertainty_codes))&&strs(i.evidence_ids)&&strs(i.source_locators)&&i.evidence_ids.length===i.source_locators.length&&['reason_summary','remaining_uncertainty','recommended_action','blocker_id','dimension'].every(k=>typeof i[k]==='string')))return fail();
  const items=r.items as ReviewItem[];
  if(new Set(items.map(i=>i.item_id)).size!==items.length||r.summary.total_items!==items.length||r.summary.unique_resource_count!==new Set(items.flatMap(i=>i.resource_ids)).size)return fail();
  for(const status of Object.keys(reviewLabels))if(r.summary.item_counts[status]!==items.filter(i=>i.ai_status===status).length)return fail();
  if(!r.summary.questions.every(q=>obj(q)&&typeof q.question_key==='string'&&typeof q.text==='string'&&strs(q.item_ids)&&strs(q.resource_ids)&&(q.why_needed_zh===undefined||typeof q.why_needed_zh==='string')&&q.item_ids.every(id=>items.some(i=>i.item_id===id&&i.ai_status==='NEEDS_USER_FACT'))&&q.resource_ids.every(id=>items.some(i=>(q.item_ids as string[]).includes(i.item_id)&&i.resource_ids.includes(id)))))return fail();
 }
 return x as ReviewState;
}
const base=(a:Assessment)=>'/scans/'+encodeURIComponent(a.scan_id)+'/assessments/'+encodeURIComponent(a.id)+'/ai-review';
export async function readReview(a:Assessment){return validateReview(await request(base(a)+'?assessment_version='+a.version),a);}
// Kept after failure: render retries must not become implicit model retries.
const starts=new Map<string,Promise<ReviewState>>();
export async function loadReview(a:Assessment,readOnly:boolean):Promise<ReviewState>{
 if(readOnly)return readReview(a);
 const key=[a.scan_id,a.id,a.version,a.facts_hash,(a as Assessment&{usage_hash:string}).usage_hash,a.rule_version].join('|');
 let existing=starts.get(key);
 if(!existing){existing=(async()=>{const current=await readReview(a);if(current.job)return current;
  const value=await request(base(a),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assessment_version:a.version,facts_hash:a.facts_hash,usage_hash:(a as Assessment&{usage_hash:string}).usage_hash,rule_version:a.rule_version})});
  return validateReview({...current,job:value},a);
 })();starts.set(key,existing);}
 return existing;
}

// Presentation only. Source judgments, statuses and evidence remain immutable.
const judgmentTitles:Record<string,string>={likely_dev_test_only:'较可能仅用于开发／测试',likely_runtime_dependency:'较可能属于运行时依赖',likely_docs_example:'较可能属于文档／示例',license_unverified:'许可关联仍需核对',version_unresolved:'版本仍未精确定位',system_limit_explained:'当前系统覆盖有限',insufficient_basis:'现有依据不足以安全判断',needs_user_fact:'实际使用事实尚需补充',obligation_unconfirmed:'义务履行尚未确认'};
export const uncertaintyLabels:Record<string,string>={ACTUAL_DELIVERY_UNKNOWN:'实际交付范围尚未确定',INSUFFICIENT_EVIDENCE:'支撑判断的依据不足',MATERIAL_MISSING:'仍缺少相关材料',PATH_ONLY:'部分依据仅来自文件位置',SYSTEM_LIMIT:'存在当前系统覆盖限制',VERSION_UNRESOLVED:'版本尚未精确定位',LICENSE_RELATION_UNVERIFIED:'材料与许可的关联尚未核验',FUTURE_FACT:'实际履行事实需要交付方补充',CONFLICTING_EVIDENCE:'已有依据之间存在冲突',USER_ASSERTED_NOT_VERIFIED:'用户声明尚未独立核验'};
export function reviewGroups(items:ReviewItem[],status:ReviewStatus){
 const groups=new Map<string,ReviewItem[]>();
 for(const item of items.filter(i=>i.ai_status===status)){const code=item.judgment_code??'unknown';groups.set(code,[...(groups.get(code)??[]),item]);}
 return [...groups].map(([code,rows])=>({code,title:judgmentTitles[code]??'辅助研判记录',items:rows,resourceCount:new Set(rows.flatMap(i=>i.resource_ids)).size,bands:{HIGH:rows.filter(i=>i.confidence_band==='HIGH').length,MEDIUM:rows.filter(i=>i.confidence_band==='MEDIUM').length,LOW:rows.filter(i=>i.confidence_band==='LOW').length},uncertainties:[...new Set(rows.flatMap(i=>i.uncertainty_codes??[]))],explanation:rows[0].reason_summary})).sort((a,b)=>b.items.length-a.items.length||a.code.localeCompare(b.code));
}
export function reviewEvidence(item:ReviewItem,evidence:Evidence[]){
 const kinds:Record<string,string>={file:'文件证据',manifest_field:'依赖声明字段',license_text:'许可正文',url:'来源链接',rule:'规则依据'};
 return item.evidence_ids.map((id,index)=>{const e=evidence.find(e=>e.id===id);return {id,locator:item.source_locators[index],kind:e?.sourceKind?kinds[e.sourceKind]??'其他已保存证据':'证据类型未提供'};});
}

export type UserFact={user_fact_id:string;question_id:string;question_code:string;answer_code:string;covered_resource_ids:string[];covered_item_ids:string[];optional_note:string;revision:number;provenance:'USER_ASSERTED';formal_effect:'none'};
export type LoopQuestion={question_id:string;question_key:string;question_code:string;text:string;item_ids:string[];resource_ids:string[];resources:{id:string;name:string}[];options:{code:string;label:string}[];latest:UserFact|null;history:UserFact[]};
export type LoopView={version:string;binding:Record<string,unknown>;ai_aggregate_id:string;questions:LoopQuestion[];routes:{item_id:string;name:string;resource_ids:string[];resolution_routes:string[];why:string;public_source_candidate:{provider:string;source_url:string}|null}[];derived:{job:ReviewJob;snapshot:NonNullable<ReviewState['snapshot']>}|null;latest_job:ReviewJob|null};
function loopBinding(b:unknown,a:Assessment){return obj(b)&&b.scan_id===a.scan_id&&b.assessment_id===a.id&&b.assessment_version===a.version&&b.facts_hash===a.facts_hash&&b.usage_hash===(a as Assessment&{usage_hash:string}).usage_hash&&b.rule_version===a.rule_version;}
export function validateLoop(x:unknown,a:Assessment):LoopView{
 if(!obj(x)||x.version!=='openguard-ai-resolution-loop/1'||!loopBinding(x.binding,a)||typeof x.ai_aggregate_id!=='string'||!/^[a-f0-9]{64}$/.test(x.ai_aggregate_id)||!Array.isArray(x.questions)||!Array.isArray(x.routes))return fail();
 for(const q of x.questions){if(!obj(q)||!['question_id','question_key','question_code','text'].every(k=>typeof q[k]==='string')||!strs(q.item_ids)||!strs(q.resource_ids)||!Array.isArray(q.options)||!Array.isArray(q.resources)||!Array.isArray(q.history)||!q.options.every(o=>obj(o)&&typeof o.code==='string'&&typeof o.label==='string')||!q.resources.every(r=>obj(r)&&typeof r.id==='string'&&(q.resource_ids as string[]).includes(r.id)&&typeof r.name==='string'))return fail();
  for(const fact of q.history){if(!obj(fact)||fact.question_id!==q.question_id||fact.question_code!==q.question_code||fact.provenance!=='USER_ASSERTED'||fact.formal_effect!=='none'||!strs(fact.covered_item_ids)||!strs(fact.covered_resource_ids)||!fact.covered_item_ids.every(i=>(q.item_ids as string[]).includes(i))||!fact.covered_resource_ids.every(i=>(q.resource_ids as string[]).includes(i)))return fail();}}
 for(const row of x.routes)if(!obj(row)||typeof row.item_id!=='string'||typeof row.name!=='string'||typeof row.why!=='string'||!strs(row.resolution_routes))return fail();
 if(x.derived!==null){if(!obj(x.derived)||!obj(x.derived.snapshot)||!obj(x.derived.snapshot.binding)||x.derived.snapshot.binding.ai_aggregate_id!==x.ai_aggregate_id)return fail();validateReview({binding:x.derived.snapshot.binding,...x.derived},a,'openguard-derived-ai-review/1');}
 return x as LoopView;
}
export async function readLoop(a:Assessment){return validateLoop(await request(base(a)+'/questions?assessment_version='+a.version),a);}
const assertionBody=(a:Assessment,v:LoopView)=>({assessment_version:a.version,facts_hash:a.facts_hash,usage_hash:(a as Assessment&{usage_hash:string}).usage_hash,rule_version:a.rule_version,ai_aggregate_id:v.ai_aggregate_id});
export async function saveUserFact(a:Assessment,v:LoopView,q:LoopQuestion,answer:string,resources:string[],note:string,key:string,readOnly:boolean):Promise<UserFact>{
 if(readOnly)throw new Error('只读预览不能保存回答。');
 const f=await request(base(a)+'/user-facts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...assertionBody(a,v),question_id:q.question_id,question_code:q.question_code,answer_code:answer,covered_resource_ids:resources,optional_note:note,idempotency_key:key,expected_revision:q.latest?.revision??0})});
 if(!obj(f)||f.question_id!==q.question_id||f.answer_code!==answer||f.provenance!=='USER_ASSERTED'||f.formal_effect!=='none'||!loopBinding(f.binding,a)||typeof f.user_fact_id!=='string')return fail();return f as UserFact;
}
export async function startDerived(a:Assessment,v:LoopView,acquisitions:string[],readOnly:boolean){
 if(readOnly)throw new Error('只读预览不能重新研判。');
 return request(base(a)+'/reassess',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...assertionBody(a,v),user_fact_ids:v.questions.flatMap(q=>q.latest?[q.latest.user_fact_id]:[]),acquisition_snapshot_ids:acquisitions,previous_snapshot_id:v.derived?.snapshot.snapshot_id??null})});
}
export async function startAcquisition(a:Assessment,v:LoopView,itemIds:string[],readOnly:boolean){
 if(readOnly)throw new Error('只读预览不能联网补证。');
 return request(base(a)+'/evidence-acquisition',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...assertionBody(a,v),item_ids:itemIds})});
}
export async function readLoopJob(a:Assessment,v:LoopView,id:string){
 const data=await request(base(a)+'/resolution-jobs/'+encodeURIComponent(id)+'?assessment_version='+a.version+'&ai_aggregate_id='+encodeURIComponent(v.ai_aggregate_id));
 if(!obj(data)||!obj(data.job)||data.job.job_id!==id||!loopBinding(data.job.binding,a)||!obj(data.job.binding)||data.job.binding.ai_aggregate_id!==v.ai_aggregate_id)return fail();return data as {job:ReviewJob;snapshot:{snapshot_id:string;result:Record<string,unknown>}|null};
}

// Closed, user-facing error mapping. Raw transport/model errors remain internal.
export function loopJobMessage(job:{status:string;error?:string}){
 if(job.status==='cancelled')return '本次处理已取消；已保存回答与原研判保留。';
 const messages:Record<string,string>={dns_failed:'官方来源的安全解析未完成，本次未取得新材料；原研判保留。请稍后检查网络条件。',timeout:'官方材料读取超时，本次未取得新材料；原研判保留。',not_found:'官方来源此次未返回材料；不能据此判断资源不存在，原研判保留。',ai_provider_unavailable:'本地模型暂不可用；已保存回答与原研判保留。'};
 return messages[job.error??'']??'本次处理未完成，已保存回答与原研判保留；可查看历史记录。';
}
