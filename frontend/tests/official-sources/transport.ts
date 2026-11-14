import { fixture } from './fixture';
import { record } from '../p2-ai-analysis/fixture';
import type { OfficialSources } from '../../src/services/officialSources';
export function check(v:unknown,message:string):asserts v{if(!v)throw Error(message);}
export type Row={method:string;url:string;body:string|null;route:string;status:number|null;response:string|null};
export type Options={holdPost?:boolean;holdRead?:boolean;reject?:number;mutate?:(value:OfficialSources)=>void;pendingAnalysis?:boolean;failure?:'network_once'|'lost_response_once';holdRecovery?:boolean};
export function transport(groups:ReturnType<typeof fixture>[],options:Options={}){
 const ledger:Row[]=[],nonGet:Row[]=[],unknown:Row[]=[];let held=false,postRelease!:()=>void,readRelease!:()=>void;
 let postCount=0;
 const postGate=new Promise<void>(r=>postRelease=r),readGate=new Promise<void>(r=>readRelease=r),adopted=new Set<string>();
 const fetcher:typeof fetch=async(input,init)=>{
  const url=new URL(String(input),location.origin),method=init?.method??'GET',row:Row={method,url:url.pathname+url.search,body:typeof init?.body==='string'?init.body:null,route:'unknown',status:null,response:null};ledger.push(row);if(method!=='GET')nonGet.push(row);
  const reply=(status:number,value:unknown)=>{row.status=status;row.response=JSON.stringify(value);return Response.json(value,{status});};
  if(url.origin===location.origin)for(const f of groups){
   const p=`/api/v1/scans/${f.assessment.scan_id}/assessments/${f.assessment.id}/p2`;
   if(method==='GET'&&url.pathname===p+'/binding'){row.route='binding';if(options.holdRecovery)await readGate;return reply(200,f.binding);}
   if(method==='GET'&&url.pathname===p+'/results'){row.route='result-index';return reply(200,{head_result_id:adopted.has(f.assessment.id)?f.newer.result_id:f.result.result_id,head_revision:adopted.has(f.assessment.id)?2:1,result_ids:adopted.has(f.assessment.id)?[f.newer.result_id,f.result.result_id]:[f.result.result_id],has_more:false});}
   for(const r of[f.result,f.newer]){
    if(method==='GET'&&url.pathname===p+'/results/'+r.result_id){row.route='fixed-result';return reply(200,r);}
    if(method==='GET'&&['/automatic-review','/preliminary-advice'].some(s=>url.pathname===p+'/results/'+r.result_id+s)){row.route='derived-503';return reply(503,{error:{code:'SYNTHETIC_DERIVED_503'}});}
   }
   if(method==='GET'&&url.pathname===p+'/official-sources'){
    row.route='official-status';check(url.searchParams.get('assessment_version')===String(f.assessment.version),'Wrong Assessment');const rid=url.searchParams.get('result_id');check([f.result.result_id,f.newer.result_id].includes(rid??''),'Wrong fixed Result');
    if(options.holdRead&&!held){held=true;await readGate;}
    const value=f.status(rid===f.newer.result_id);if(options.pendingAnalysis){value.analysis.state='running';value.analysis.preview=null;value.analysis.analysis_id=null;}options.mutate?.(value);return reply(200,value);
   }
   if(method==='POST'&&url.pathname===p+'/official-sources/adopt'){
    row.route='official-adopt';const body=JSON.parse(row.body??'{}');check(body.candidate_id===f.status().candidate?.candidate_id&&body.result_id===f.result.result_id&&body.parent_result_id===f.result.result_id&&body.result_sha256===f.result.result_sha256&&body.expected_revision===1,'CAS/request parent mismatch');
    postCount++;if(options.holdPost)await postGate;if(options.failure==='network_once'&&postCount===1)throw Error('SYNTHETIC_NETWORK_UNKNOWN');if(options.reject)return reply(options.reject,{error:{code:'SYNTHETIC_CONFLICT'}});adopted.add(f.assessment.id);if(options.failure==='lost_response_once'&&postCount===1){row.status=201;row.response=JSON.stringify(f.receipt);throw Error('SYNTHETIC_SAVED_RESPONSE_LOST');}return reply(201,f.receipt);
   }
   if(method==='GET'&&url.pathname===p+'/ai-analyses'){row.route='ai-index';const rid=url.searchParams.get('result_id');return reply(200,{result_id:rid,analysis_ids:rid===f.newer.result_id?['p2ai_SYNTHETIC_'+f.assessment.id.split('_').at(-1)]:[]});}
   if(method==='GET'&&url.pathname.startsWith(p+'/ai-analyses/')){row.route='ai-fixed';const value=record(f.newer);value.analysis_id=url.pathname.split('/').at(-1)!;return reply(200,value);}
  }
  unknown.push(row);throw Error('Unknown TEST_ONLY request; native fetch is never used');
 };
 return{fetch:fetcher,ledger,nonGet,unknown,postRelease,readRelease};
}
