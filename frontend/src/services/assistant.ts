/** Independent account-scoped assistant. Event reads never start a generation. */
import { ApiError, request } from './scans';
import { accountRequestOptions, handleAccountResponse } from './auth';
import { readExactAssessment, type Assessment } from './assessments';
import { readBinding, readResult, type Result } from './p2';
import { validateProjectChat, type ChatBasis, type ProjectChat } from './projectChat';
export type ProjectRef={scan_id:string;assessment_id:string;assessment_version:number;result_id:string;result_sha256:string};
export type Conversation={id:string;title:string;created_at:string;updated_at:string;context:ProjectRef|null};
export type Citation={basis_id:string;quote:string;label:string;verification_state:string};
export type Message={id:string;request_id:string;role:'user'|'assistant';text:string;status:'pending'|'streaming'|'completed'|'stopped'|'failed';created_at:string;error_code:string|null;citations:Citation[]};
export type Limits={total_call_limit:null;max_requests_per_minute:number;concurrent:number;request_timeout_seconds:number;max_question_chars:number;project_max_question_chars:number};
export type ProjectContext={scope:ProjectChat['scope'];context:ProjectChat['context']};
export type Detail={schema_version:'openguard-assistant/1';conversation:Conversation;items:Message[];limits:Limits;has_more:boolean;cursor:string|null;context_policy:unknown;project_context:ProjectContext|null};
export type Event={seq:number;type:'start'|'delta'|'final'|'stopped'|'error';text?:string;message?:Message};
const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const date=(v:unknown):v is string=>typeof v==='string'&&Number.isFinite(Date.parse(v));
const natural=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>=0;
const fail=():never=>{throw new Error('会话响应与固定版本或依据不一致，已停止显示；请重新读取记录。');};
export function validateProjectRef(v:unknown):ProjectRef {if(!obj(v)||!id(v.scan_id)||!id(v.assessment_id)||!natural(v.assessment_version)||v.assessment_version<1||!id(v.result_id)||!hash(v.result_sha256))return fail();return v as ProjectRef;}
export function sameProject(a:ProjectRef|null,b:ProjectRef|null){return a===null?b===null:b!==null&&(['scan_id','assessment_id','assessment_version','result_id','result_sha256'] as const).every(k=>a[k]===b[k]);}
export function validateConversation(v:unknown):Conversation {if(!obj(v)||!id(v.id)||typeof v.title!=='string'||!date(v.created_at)||!date(v.updated_at))return fail();if(v.context!==null)validateProjectRef(v.context);return v as Conversation;}
function validateLimits(v:unknown):Limits {if(!obj(v)||v.total_call_limit!==null||!['max_requests_per_minute','concurrent','request_timeout_seconds','max_question_chars','project_max_question_chars'].every(k=>natural(v[k])&&v[k]>0))return fail();return v as Limits;}
export function validateMessage(v:unknown,context:ProjectRef|null,basis:ChatBasis[]=[]):Message {
 if(!obj(v)||!id(v.id)||!id(v.request_id)||!['user','assistant'].includes(v.role)||typeof v.text!=='string'||v.text.length>300000||!['pending','streaming','completed','stopped','failed'].includes(v.status)||!date(v.created_at)||!(v.error_code===null||typeof v.error_code==='string')||!Array.isArray(v.citations))return fail();
 if(v.status==='completed'&&v.role==='assistant'&&(!v.text.trim()||v.error_code!==null))return fail();
 for(const c of v.citations){if(!obj(c)||!id(c.basis_id)||typeof c.quote!=='string'||!c.quote.trim()||typeof c.label!=='string'||typeof c.verification_state!=='string')return fail();if(context){const e=basis.find(e=>e.basis_id===c.basis_id);if(!e||!e.quote.includes(c.quote)||e.label!==c.label||e.verification_state!==c.verification_state)return fail();}}
 if(context&&v.role==='assistant'){
  if(v.status==='completed'&&v.citations.length===0)return fail();
  if(v.status!=='completed'&&(v.text!==''||v.citations.length))return fail();
 }
 return v as Message;
}
export async function listConversations(signal?:AbortSignal,cursor?:string){const v=await request('/assistant/conversations'+(cursor?'?cursor='+encodeURIComponent(cursor):''),{},signal);if(!obj(v)||v.schema_version!=='openguard-assistant/1'||!Array.isArray(v.items))return fail();return{items:v.items.map(validateConversation),limits:validateLimits(v.limits),has_more:v.has_more===true,cursor:typeof v.cursor==='string'?v.cursor:null};}
export async function createConversation(context:ProjectRef|null,requestId=crypto.randomUUID()){if(context)validateProjectRef(context);const v=await request('/assistant/conversations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,context})},undefined,201);const c=validateConversation(v);if(!sameProject(c.context,context))return fail();return c;}
export function projectReference(a:Assessment,r:Result):ProjectRef{return validateProjectRef({scan_id:a.scan_id,assessment_id:a.id,assessment_version:a.version,result_id:r.result_id,result_sha256:r.result_sha256});}
export async function readConversation(cid:string,signal?:AbortSignal,cursor?:string):Promise<Detail>{
 const v=await request('/assistant/conversations/'+encodeURIComponent(cid)+(cursor?'?cursor='+encodeURIComponent(cursor):''),{},signal);
 if(!obj(v)||v.schema_version!=='openguard-assistant/1'||!Array.isArray(v.items))return fail();
 const c=validateConversation(v.conversation);if(c.id!==cid)return fail();let project:ProjectContext|null=null;
 if(c.context){
  const ref=c.context,a=await readExactAssessment(ref.scan_id,ref.assessment_id,signal),binding=await readBinding(a,signal),r=await readResult(a,binding,ref.result_id,signal);
  if(!sameProject(ref,projectReference(a,r))||!obj(v.project_context))return fail();
  const checked=validateProjectChat({schema_version:'openguard-p2-project-chat/1',formal_effect:'none',...v.project_context,items:[],limits:{max_question_chars:2000,max_turns:50,max_model_calls:8,used_model_calls:0,remaining_model_calls:8}},a,r);
  project={scope:checked.scope,context:checked.context};
 }else if(v.project_context!=null)return fail();
 const items=v.items.map((m:unknown)=>validateMessage(m,c.context,project?.context.evidence));if(new Set(items.map((m:Message)=>m.id)).size!==items.length)return fail();
 return{schema_version:'openguard-assistant/1',conversation:c,items,limits:validateLimits(v.limits),has_more:v.has_more===true,cursor:typeof v.cursor==='string'?v.cursor:null,context_policy:v.context_policy,project_context:project};
}
export async function sendMessage(c:Conversation,text:string,requestId:string,basis:ChatBasis[]=[]):Promise<Message>{
 const question=text.trim();if(!question||question.length>(c.context?2000:8000)||!id(requestId))throw new Error('请输入符合长度限制的问题。');
 const v=await request('/assistant/conversations/'+encodeURIComponent(c.id)+'/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,message:question})},undefined,202);
 if(!obj(v)||v.conversation_id!==c.id||v.request_id!==requestId)return fail();const m=validateMessage(v.message,c.context,basis);if(m.role!=='assistant'||m.request_id!==requestId)return fail();return m;
}
export async function stopMessage(c:Conversation,requestId:string,basis:ChatBasis[]=[]){const v=await request('/assistant/conversations/'+encodeURIComponent(c.id)+'/messages/'+encodeURIComponent(requestId)+'/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'},undefined,200);if(!obj(v))return fail();const m=validateMessage(v.message,c.context,basis);if(m.request_id!==requestId||m.role!=='assistant')return fail();return m;}
/** UTF8 streaming decoder. A fresh replay buffer is used when after=0. */
export async function consumeNDJSON(body:ReadableStream<Uint8Array>,onLine:(value:unknown)=>void,signal?:AbortSignal){
 const reader=body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});let buffer='',total=0;
 const abort=()=>{void reader.cancel();};signal?.addEventListener('abort',abort,{once:true});
 try{while(true){if(signal?.aborted)throw new DOMException('Aborted','AbortError');const{done,value}=await reader.read();if(done)break;total+=value.length;if(total>2000000)throw Error('会话进度超过读取上限。');buffer+=decoder.decode(value,{stream:true});if(buffer.length>600000)throw Error('会话进度行过长。');let i;while((i=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,i).trim();buffer=buffer.slice(i+1);if(line)onLine(JSON.parse(line));}}
 buffer+=decoder.decode();if(buffer.trim())onLine(JSON.parse(buffer));if(signal?.aborted)throw new DOMException('Aborted','AbortError');
 }finally{signal?.removeEventListener('abort',abort);await reader.cancel().catch(()=>{});reader.releaseLock();}
}
export async function readEvents(c:Conversation,requestId:string,after:number,onEvent:(event:Event)=>void,signal:AbortSignal,basis:ChatBasis[]=[]){
 const base=(import.meta.env.VITE_API_BASE_URL||'/api/v1').replace(/\/$/,'');
 const response=await fetch(base+'/assistant/conversations/'+encodeURIComponent(c.id)+'/messages/'+encodeURIComponent(requestId)+'/events?after='+after,accountRequestOptions({method:'GET',cache:'no-store',headers:{Accept:'application/x-ndjson'},signal}));handleAccountResponse(response.status);
 if(!response.ok){const v=await response.json().catch(()=>null);throw new ApiError(response.status,v?.error?.message??'进度连接未完成。',v?.error?.code);}
 if(!response.body||!response.headers.get('Content-Type')?.includes('application/x-ndjson'))throw Error('进度流格式不符合契约。');
 let seq=after,terminalSeen=false;
 await consumeNDJSON(response.body,v=>{if(!obj(v)||!natural(v.seq)||!['start','delta','final','stopped','error'].includes(v.type))return fail();if(v.seq<=seq)return;if(v.seq!==seq+1)throw Error('会话进度不连续，请读取保存状态。');if(terminalSeen)return fail();seq=v.seq;
  if(v.type==='delta'){if(c.context||typeof v.text!=='string')return fail();}
  else if(['final','stopped','error'].includes(v.type)){const m=validateMessage(v.message,c.context,basis);if(m.role!=='assistant'||m.request_id!==requestId||(v.type==='final'&&m.status!=='completed')||(v.type==='stopped'&&m.status!=='stopped')||(v.type==='error'&&m.status!=='failed'))return fail();terminalSeen=true;}
  onEvent(v as Event);
 },signal);
}
export function assistantError(error:unknown){if(error instanceof ApiError){if(error.status===429)return'操作较快，请稍候再发送（每分钟最多10次）。';if(error.status===409)return'本机已有回答正在生成，或请求身份冲突。请先读取记录。';}return error instanceof Error?error.message:'会话操作没有完成，请读取记录确认。';}
