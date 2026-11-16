import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { OfficialSources } from '../../src/components/OfficialSources';
import { fixture } from '../official-sources/fixture';
import { fixedCommit, fixedLicenseHash, type LocalActions } from '../../src/services/officialSources';

const report={classification:'SYNTHETIC_TEST_ONLY_REAL_REACT_AND_SERVICE_NO_EXTERNAL_OR_MODEL',status:'NOT_RUN',cases:[] as any[]};
declare global{interface Window{__LOCAL_ACTIONS__:typeof report;}}
window.__LOCAL_ACTIONS__=report;
const tick=()=>new Promise<void>(done=>{const c=new MessageChannel();c.port1.onmessage=()=>{c.port1.close();c.port2.close();done();};c.port2.postMessage(null);});
async function idle(){await act(async()=>{for(let i=0;i<6;i++)await tick();});}
async function until(fn:()=>boolean){const start=performance.now();while(!fn()){if(performance.now()-start>5000)throw Error('TEST_ONLY component did not settle');await idle();}}
function check(value:unknown,text:string):asserts value{if(!value)throw Error(text);}
function canonical(value:any):string{if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';return JSON.stringify(value);}
async function freeze(value:any){const bytes=new TextEncoder().encode(canonical(value)),sha=await crypto.subtle.digest('SHA-256',bytes);return{...value,content_sha256:[...new Uint8Array(sha)].map(x=>x.toString(16).padStart(2,'0')).join('')} as LocalActions;}
async function local(f:ReturnType<typeof fixture>,newer:boolean){
 const r=newer?f.newer:f.result,c=f.status(newer).candidate!,text=c.license_text,quote='The above copyright notice and this permission notice shall be\nincluded in all copies or substantial portions of the Software.',start=text.indexOf(quote),end=start+quote.length;
 check(start>=0,'Real fixed text condition missing');
 return freeze({schema_version:'openguard-p2-local-actions/1',result_id:r.result_id,result_revision:r.revision,result_sha256:r.result_sha256,binding:{...r.binding},subject:{...r.resources[0].subject},usage:{...r.usage},usage_assumption:'DEMO_USAGE_ASSUMPTION',state:newer?'supported_verification_actions':'awaiting_material',source_refs:newer?[{material_id:r.material_ids[0],subject:{...r.resources[0].subject},source_sha256:fixedLicenseHash,source_level:'user_supplied_unverified',verification_state:'pending',evidence_ids:[...r.resources[0].evidence_ids],candidate_id:c.candidate_id,git_commit:fixedCommit,source_url:`https://raw.githubusercontent.com/http-party/http-server/${fixedCommit}/LICENSE`}]:[],clauses:newer?[{material_id:r.material_ids[0],quote,start,end,line_start:text.slice(0,start).split('\n').length,line_end:text.slice(0,end).split('\n').length,category:'quoted_condition_not_applicability_decision'}]:[],actions:newer?[{code:'CHECK_EXACT_SOURCE_SCOPE',text:'核对http-server@14.1.2的实际文件范围并保留清单；TEST_ONLY不表示已经授权。',usage_fields:[],source_material_ids:[r.material_ids[0]],clause_indices:[0],claim_level:'verification_action_only'}]:[],gaps:['TEST_ONLY_scope_unverified'],limitations:['TEST_ONLY pending不表示许可通过'],quote_index_unit:'unicode_code_point',formal_effect:'none',model_calls:0,source_admission:'NOT_SIGNED',applicability:'NOT_SIGNED',obligations:'NOT_ESTABLISHED'});
}
async function scenario(name:string,defect?:string){
 const f=fixture('LOCAL_'+report.cases.length),ledger:any[]=[],unknown:any[]=[],nonGet:any[]=[],host=document.createElement('div');document.querySelector('#mounts')!.append(host);const root=createRoot(host);let error:any;
 const newer=defect!=='old-r1',status=f.status(newer);status.runtime_jobs_enabled=false;status.local_actions=await local(f,newer);
 if(defect==='wrong-result')status.local_actions.result_id=f.result.result_id;
 if(defect==='wrong-usage')status.local_actions.usage.commercial=!status.local_actions.usage.commercial;
 if(defect==='wrong-resource')status.local_actions.subject.resource_id='cmp_other';
 if(defect==='wrong-evidence')status.local_actions.source_refs[0].evidence_ids=['evd_other'];
 if(defect==='wrong-quote')status.local_actions.clauses[0].start++;
 if(defect==='wrong-hash')status.local_actions.content_sha256='0'.repeat(64);
 window.fetch=async(input,init)=>{const url=new URL(String(input),location.origin),method=init?.method??'GET',row={method,path:url.pathname+url.search};ledger.push(row);if(method!=='GET')nonGet.push(row);const base=`/api/v1/scans/${f.assessment.scan_id}/assessments/${f.assessment.id}/p2/official-sources`;if(method!=='GET'||url.origin!==location.origin||url.pathname!==base){unknown.push(row);throw Error('Unknown TEST_ONLY transport');}return Response.json(status);};
 try{
  flushSync(()=>root.render(<OfficialSources assessment={f.assessment} result={newer?f.newer:f.result} readOnly onAdopt={()=>{throw Error('Unexpected adopt callback');}} onAnalysisSaved={()=>{}}/>));
  await until(()=>!host.textContent?.includes('正在只读获取本版资料'));
  if(defect&&defect!=='old-r1'){check(!!host.querySelector('[role="alert"]'),'Invalid bound actions were accepted');check(!host.querySelector('[data-local-actions]'),'Invalid action remained visible');}
  else if(defect==='old-r1'){check(!host.querySelector('[data-local-actions]'),'r1 borrowed newer material');check(host.textContent?.includes('此固定Result尚未关联这份LICENSE材料'),'Missing exact material gap');}
  else{check(host.querySelector('[data-local-action-result]')?.getAttribute('data-local-action-result')===f.newer.result_id,'Wrong fixed Result action');check(host.textContent?.includes('基于已保存材料的核验行动'),'Action identity missing');check(host.textContent?.includes('未授权新增联网或模型调用'),'Budget boundary missing');const detail=host.querySelector('[data-local-action] details')!;flushSync(()=>detail.querySelector('summary')!.dispatchEvent(new MouseEvent('click',{bubbles:true})));await idle();check(detail.textContent?.includes('LICENSE 第'),'No exact line location');check(detail.textContent?.includes('user_supplied_unverified / pending'),'Source promoted');}
  check(nonGet.length===0,'Passive read dispatched a write');check(unknown.length===0,'Unknown request swallowed');check(ledger.length===1,'Unexpected polling when runtime jobs disabled');
 }catch(e){error=e;}finally{flushSync(()=>root.unmount());host.remove();await idle();if(nonGet.length&&!error)error=Error('Late write');if(unknown.length&&!error)error=Error('Late unknown');report.cases.push({name,status:error?'failed':'passed',error:error?String(error):null,ledger,nonGet,unknown});}
}
async function run(){report.status='running';await scenario('saved r2 material yields bound pending action and inspectable source without POST');await scenario('old r1 does not borrow r2 material','old-r1');for(const defect of['wrong-result','wrong-usage','wrong-resource','wrong-evidence','wrong-quote','wrong-hash'])await scenario('fails closed for '+defect,defect);report.status=report.cases.every(c=>c.status==='passed')?'passed':'failed';document.querySelector('#results')!.textContent=JSON.stringify(report,null,2);}
document.querySelector<HTMLButtonElement>('#run')!.onclick=()=>void run().catch(e=>{report.status='failed';document.querySelector('#results')!.textContent=String(e);});
