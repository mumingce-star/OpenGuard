/** Read-only project assistance. Chat history is separate from business results. */
import { ApiError, request } from './scans';
import { accountRequestOptions, handleAccountResponse } from './auth';
import { sameBinding, type Binding, type Result } from './p2';
import { usageFields, type Assessment } from './assessments';

export type ChatBasis = {basis_id:string;kind:'scan_evidence'|'material'|'result_fact';label:string;resource_ids:string[];quote:string;verification_state:string};
export type ProjectChatTurn = {request_id:string;question:string;status:'pending'|'succeeded'|'failed';answer:string|null;citations:{basis_id:string;quote:string}[];created_at:string;error_code:string|null};
export type ProjectChat = {schema_version:'openguard-p2-project-chat/1';scope:{binding:Binding;result_id:string;result_revision:number;result_sha256:string};context:{project_name:string;usage:Result['usage'];resource_count:number;material_count:number;evidence:ChatBasis[]};items:ProjectChatTurn[];limits:{max_question_chars:number;max_turns:number;max_model_calls:number;used_model_calls:number;remaining_model_calls:number};formal_effect:'none'};
export type ChatQuestion = {binding:Binding;result_id:string;result_sha256:string;question:string;request_id:string};
const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown):v is string=>typeof v==='string';
const ident=(v:unknown):v is string=>text(v)&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const natural=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>=0;
const fail=():never=>{throw new Error('问答与当前项目版本或引用不一致，已停止显示这份回答。请重新读取准确版本。');};
// Derived citation of this immutable Result's saved usage, not a new Evidence or Material.
export function savedUsageFactQuote(r:Result):string {
 return Object.entries(usageFields).map(([key,label])=>`${label}：${r.usage[key as keyof typeof usageFields]===true?'是':r.usage[key as keyof typeof usageFields]===false?'否':'未知'}`).join('\n')+'\n以上为本版保存的演示用途声明，不证明实际行为已经发生或完成。';
}
export function validateProjectChat(v:unknown,a:Assessment,r:Result):ProjectChat {
 if(!obj(v)||v.schema_version!=='openguard-p2-project-chat/1'||v.formal_effect!=='none'||!obj(v.scope)||!obj(v.scope.binding)||!sameBinding(v.scope.binding as Binding,r.binding)||v.scope.binding.assessment_id!==a.id||v.scope.binding.scan_id!==a.scan_id||v.scope.binding.assessment_version!==a.version||v.scope.result_id!==r.result_id||v.scope.result_revision!==r.revision||v.scope.result_sha256!==r.result_sha256||!obj(v.context)||!text(v.context.project_name)||!obj(v.context.usage)||!Object.keys(usageFields).every(k=>v.context.usage[k]===r.usage[k as keyof typeof usageFields])||v.context.resource_count!==r.resources.length||v.context.material_count!==r.material_ids.length||!Array.isArray(v.context.evidence)||!Array.isArray(v.items)||!obj(v.limits))return fail();
 const basis=new Map<string,ChatBasis>();
 for(const e of v.context.evidence){
  if(!obj(e)||!ident(e.basis_id)||basis.has(e.basis_id)||!['scan_evidence','material','result_fact'].includes(e.kind)||!text(e.label)||!text(e.quote)||!text(e.verification_state)||!Array.isArray(e.resource_ids)||!e.resource_ids.every((id:unknown)=>ident(id)&&r.resources.some(x=>x.subject.resource_id===id)))return fail();
  if(e.kind==='result_fact'&&(e.basis_id!==`result:${r.result_sha256}:usage`||e.resource_ids.length!==0||e.verification_state!=='saved_declaration'||e.quote!==savedUsageFactQuote(r)))return fail();
  basis.set(e.basis_id,e as ChatBasis);
 }
 const seen=new Set<string>();
 for(const t of v.items){if(!obj(t)||!ident(t.request_id)||seen.has(t.request_id)||!text(t.question)||!['pending','succeeded','failed'].includes(t.status)||!(t.answer===null||text(t.answer))||!(t.error_code===null||text(t.error_code))||!text(t.created_at)||!Number.isFinite(Date.parse(t.created_at))||!Array.isArray(t.citations))return fail();
  if(t.status==='succeeded'&&(!t.answer?.trim()||t.error_code!==null||t.citations.length===0))return fail();
  if(t.status!=='succeeded'&&(t.answer!==null||t.citations.length!==0))return fail();
  for(const c of t.citations)if(!obj(c)||!ident(c.basis_id)||!text(c.quote)||!c.quote.trim()||!basis.get(c.basis_id)?.quote.includes(c.quote))return fail();
  seen.add(t.request_id);
 }
 const l=v.limits;if(!['max_question_chars','max_turns','max_model_calls','used_model_calls','remaining_model_calls'].every(k=>natural(l[k]))||l.max_question_chars<1||l.max_turns<1||l.used_model_calls>l.max_model_calls||l.remaining_model_calls!==l.max_model_calls-l.used_model_calls)return fail();
 return v as ProjectChat;
}
const prefix=(a:Assessment)=>`/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/project-chat`;
export async function readProjectChat(a:Assessment,r:Result,signal?:AbortSignal){return validateProjectChat(await request(prefix(a)+`?assessment_version=${a.version}&result_id=${encodeURIComponent(r.result_id)}`,{},signal),a,r);}
export function prepareChatQuestion(a:Assessment,r:Result,question:string,requestId:string):ChatQuestion {
 const q=question.trim();if(!q||q.length>2000||!ident(requestId)||r.binding.assessment_id!==a.id||r.binding.assessment_version!==a.version||r.binding.scan_id!==a.scan_id)return fail();
 return {binding:r.binding,result_id:r.result_id,result_sha256:r.result_sha256,question:q,request_id:requestId};
}
export async function sendProjectQuestion(a:Assessment,r:Result,body:ChatQuestion):Promise<ProjectChat> {
 // Generation is synchronous (<=120s). Keep a dedicated timeout without changing
 // normal 15s read requests. Abort/transport uncertainty never triggers a retry.
 const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),150000);
 try {
  const base=(import.meta.env.VITE_API_BASE_URL||'/api/v1').replace(/\/$/,'');
  const response=await fetch(base+prefix(a),accountRequestOptions({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal}));
  handleAccountResponse(response.status);
  const data=await response.json();
  if(!response.ok)throw new ApiError(response.status,data?.error?.message||'本次问答没有完成。',data?.error?.code,data?.error?.details?.reason);
  if(response.status!==201)throw new Error('问答回执状态异常；请读取已保存记录确认，勿重复发送。');
  const chat=validateProjectChat(data,a,r),turn=chat.items.find(x=>x.request_id===body.request_id);
  if(!turn||turn.question!==body.question)return fail();
  return chat;
 } catch(error) {
  if(error instanceof Error&&error.name==='AbortError')throw new Error('等待回答超时，结果尚未确认。请读取已保存问答；不会自动重新生成。');
  throw error;
 } finally {window.clearTimeout(timer);}
}
export function chatFailureMessage(code:string|null):string {
 if(code==='p2_chat_output_rejected')return '回答未通过用途或依据校验，已保留原始记录；没有更改项目结果，也未自动重试。';
 if(code?.includes('budget'))return '本轮问答额度已用完。已有对话仍可查看，不会自动重试。';
 if(code?.includes('validation')||code?.includes('semantic')||code?.includes('invalid'))return '回答未通过用途或依据校验，未作为有效建议展示；原始记录已保留。';
 if(code?.includes('timeout'))return '本次模型回答超时，未自动重试。';
 if(code?.includes('busy'))return '本地模型正在处理另一条问答，请等待后读取状态。';
 return '这条回答未完成；已有结果未被更改，可读取记录确认原因。';
}
