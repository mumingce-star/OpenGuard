import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { ProjectChat } from '../../src/pages/ProjectChat';
import { makeFixture } from '../bound-advice-maincard-corrected-fixture/fixture';
import type { ProjectChat as ChatData } from '../../src/services/projectChat';
import type { Result } from '../../src/services/p2';

const classification='SYNTHETIC_TEST_ONLY_REAL_REACT_AND_SERVICE_CLOSED_TRANSPORT';
const check=(value:unknown,message:string)=>{if(!value)throw Error(message);};
function until(fn:()=>boolean,message:string){return new Promise<void>((resolve,reject)=>{const start=Date.now();const timer=setInterval(()=>{if(fn()){clearInterval(timer);resolve();}else if(Date.now()-start>7000){clearInterval(timer);reject(Error(message));}},10);});}
function setup(){
 const f=makeFixture(),ledger:{method:string;url:string;body:any}[]=[],unknown:string[]=[],nonGet:{method:string;url:string;body:any}[]=[];
 const saved=new Map<string,ChatData>();let hold=false,fail=false,release=()=>{};const gate=new Promise<void>(r=>release=r);
 const response=(r:Result):ChatData=>({schema_version:'openguard-p2-project-chat/1',scope:{binding:r.binding,result_id:r.result_id,result_revision:r.revision,result_sha256:r.result_sha256},context:{project_name:'SYNTHETIC_TEST_ONLY',usage:r.usage,resource_count:r.resources.length,material_count:r.material_ids.length,evidence:[{basis_id:'evidence:scope',kind:'scan_evidence',label:'SYNTHETIC_TEST_ONLY 范围记录',resource_ids:[r.resources[0].subject.resource_id],quote:'SYNTHETIC_TEST_ONLY saved source scope.',verification_state:'pending'}]},items:[],limits:{max_question_chars:2000,max_turns:50,max_model_calls:8,used_model_calls:0,remaining_model_calls:8},formal_effect:'none'});
 for(const r of[f.result,f.newer])saved.set(r.result_id,response(r));
 const fetcher:typeof fetch=async(input,init)=>{
  const u=new URL(String(input),location.origin),method=init?.method??'GET',row={method,url:u.pathname+u.search,body:init?.body?JSON.parse(String(init.body)):null};ledger.push(row);if(method!=='GET')nonGet.push(row);
  const prefix=`/api/v1/scans/${f.scan.id}/assessments/${f.assessment.id}/p2`;
  if(method==='GET'&&u.pathname===`/api/v1/scans/${f.scan.id}/assessments`)return Response.json({items:[f.assessment],usage:f.assessment.usage,pending_job:null});
  if(method==='GET'&&u.pathname===`/api/v1/scans/${f.scan.id}/assessments/${f.assessment.id}`)return Response.json(f.assessment);
  if(method==='GET'&&u.pathname===prefix+'/binding')return Response.json(f.binding);
  if(method==='GET'&&u.pathname===prefix+'/results')return Response.json({head_result_id:f.newer.result_id,head_revision:2,result_ids:[f.newer.result_id,f.result.result_id],has_more:false});
  for(const r of[f.result,f.newer])if(method==='GET'&&u.pathname===prefix+'/results/'+r.result_id)return Response.json(r);
  if(u.pathname===prefix+'/project-chat'){
   if(method==='GET'){const id=u.searchParams.get('result_id');check(id&&saved.has(id),'unknown history Result');return Response.json(saved.get(id!));}
   if(method==='POST'){
    const b=row.body,r=[f.result,f.newer].find(x=>x.result_id===b.result_id);check(r,'wrong result POST');
    const value=saved.get(r!.result_id)!;const turn={request_id:b.request_id,question:b.question,status:'pending' as 'pending'|'succeeded'|'failed',answer:null as string|null,citations:[] as {basis_id:string;quote:string}[],created_at:'2026-10-25T00:00:00Z',error_code:null};value.items.push(turn);value.limits.used_model_calls++;value.limits.remaining_model_calls--;
    if(hold)await gate;if(fail)throw TypeError('SYNTHETIC_TEST_ONLY response lost');turn.status='succeeded';turn.answer='这是 '+r!.result_id+' 的保存范围说明。';turn.citations=[{basis_id:'evidence:scope',quote:'saved source scope.'}];return Response.json(value,{status:201});
   }
  }
  unknown.push(row.url);throw Error('Unknown request, no native fallback');
 };
 const host=document.createElement('div');document.querySelector('#mounts')!.append(host);const root=createRoot(host);let rid=f.result.result_id;
 const query=()=>new URLSearchParams({assessment_id:f.assessment.id,p2_result:rid});
 const go=(url:string)=>{const u=new URL(url,location.origin);rid=u.searchParams.get('p2_result')??f.newer.result_id;render();};
 function render(){flushSync(()=>root.render(<ProjectChat scan={f.scan} query={query()} go={go}/>));}
 function button(text:string){return [...host.querySelectorAll<HTMLButtonElement>('button')].find(x=>x.textContent===text);}
 function send(){const el=host.querySelector<HTMLTextAreaElement>('textarea')!;check(el,'question input missing');const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!;flushSync(()=>{setter.call(el,'SYNTHETIC_TEST_ONLY 下一步做什么？');el.dispatchEvent(new Event('input',{bubbles:true}));});flushSync(()=>button('发送问题')!.click());}
 return{f,host,ledger,unknown,nonGet,saved,fetch:fetcher,render,send,button,release,setHold(){hold=true;},setFail(){fail=true;},switchResult(){rid=f.newer.result_id;render();},switchBack(){rid=f.result.result_id;render();},dispose(){flushSync(()=>root.unmount());host.remove();},ready:()=>until(()=>!!host.querySelector('textarea')&&!host.textContent?.includes('正在读取当前账号'),'chat ready')};
}
async function run(){
 const native=window.fetch,cases:any[]=[];
 async function one(name:string,body:(t:ReturnType<typeof setup>)=>Promise<void>){const t=setup();window.fetch=t.fetch;try{t.render();await t.ready();await body(t);check(t.unknown.length===0,'unknown requests');check(t.nonGet.every(x=>x.method==='POST'&&x.url.endsWith('/project-chat')),'business write dispatched');cases.push({name,status:'passed',requests:t.ledger,nonGet:t.nonGet,unknown:t.unknown});}catch(e){cases.push({name,status:'failed',error:String(e),requests:t.ledger,nonGet:t.nonGet,unknown:t.unknown});}finally{t.release();t.dispose();window.fetch=native;}}
 await one('passive rendering is GET-only with fixed r1',async t=>{check(t.nonGet.length===0,'passive POST');check(t.host.textContent?.includes('结果 r1'),'r1 not pinned');});
 await one('send real service request once, show exact answer and clickable source',async t=>{t.send();await until(()=>t.host.textContent?.includes('已检查用途与引用')??false,'answer complete');check(t.nonGet.length===1,'not one chat POST');flushSync(()=>t.host.querySelector<HTMLButtonElement>('.og-chat-citations button')!.click());check(t.host.querySelector('blockquote')?.textContent?.includes('saved source scope'),'source not visible');});
 await one('switch version while POST receipt pending cannot pollute r2',async t=>{t.setHold();t.send();await until(()=>t.nonGet.length===1,'POST not entered');t.switchResult();await t.ready();check(t.host.textContent?.includes('结果 r2'),'r2 not shown');t.release();await act(async()=>{await new Promise(r=>setTimeout(r,100));});check(!t.host.textContent?.includes('这是 '+t.f.result.result_id),'r1 answer polluted r2');check(t.nonGet.length===1,'automatic replay');});
 await one('A to B to A does not let old sent receipt replace returned view',async t=>{t.setHold();t.send();await until(()=>t.nonGet.length===1,'POST not entered');t.switchResult();await t.ready();t.switchBack();await t.ready();t.release();await act(async()=>{await new Promise(r=>setTimeout(r,100));});check(!t.host.textContent?.includes('已检查用途与引用'),'old receipt bypassed generation boundary');check(t.nonGet.length===1,'ABA replay');});
 await one('history reread does not generate or change fixed result',async t=>{t.send();await until(()=>t.host.textContent?.includes('已检查用途与引用')??false,'answer complete');flushSync(()=>t.button('读取已保存问答')!.click());await act(async()=>{await new Promise(r=>setTimeout(r,50));});check(t.nonGet.length===1,'history reload generated');check(t.host.textContent?.includes('结果 r1'),'history changed head');});
 await one('uncertain response blocks resend and only GET recovery occurs',async t=>{t.setFail();t.send();await until(()=>t.host.textContent?.includes('先读取记录确认状态')??false,'uncertain not surfaced');check(t.button('发送问题')?.disabled,'unknown state permits resend');flushSync(()=>t.button('读取已保存问答')!.click());await act(async()=>{await new Promise(r=>setTimeout(r,50));});check(t.nonGet.length===1,'uncertain auto retry');});
 (window as any).__PROJECT_CHAT__={status:cases.every(c=>c.status==='passed')?'passed':'failed',classification,cases};document.querySelector('#output')!.textContent=JSON.stringify((window as any).__PROJECT_CHAT__,null,2);
}
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
document.querySelector('#run')!.addEventListener('click',()=>void run());
