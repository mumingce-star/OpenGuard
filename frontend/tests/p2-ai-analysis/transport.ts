import { fixture, record } from './fixture';
import type { P2AiAnalysis } from '../../src/services/p2Ai';
export const check=(v:unknown,text:string):asserts v=>{if(!v)throw Error(text);};
export type Row={method:string;url:string;body:string|null;route:string;status:number|null;response:string|null;aborted:boolean};
export type Options={saved?:boolean;savedNewest?:boolean;failed?:boolean;holdPost?:boolean;holdRead?:boolean;reject?:number;drift?:'result'|'material'|'previous'|'quote'};
export function transport(groups:ReturnType<typeof fixture>[],options:Options={}){
 const ledger:Row[]=[],nonGet:Row[]=[],unknown:Row[]=[],values=new Map<string,P2AiAnalysis>();
 for(const f of groups)for(const r of [f.result,f.newer])if(options.saved){const v=record(r);values.set(v.analysis_id,v);}
 for(const f of groups)for(const r of [f.result,f.newer])if(options.savedNewest){const failed=record(r,'01_failure',true),success=record(r,'02_success');values.set(failed.analysis_id,failed);values.set(success.analysis_id,success);}
 let releasePost:()=>void=()=>{},releaseRead:()=>void=()=>{};
 const postGate=new Promise<void>(resolve=>releasePost=resolve),readGate=new Promise<void>(resolve=>releaseRead=resolve);
 let heldRead=false;
 const fetcher:typeof fetch=async(input,init)=>{
  const url=new URL(String(input),location.origin),method=init?.method??'GET',row:Row={method,url:url.pathname+url.search,body:typeof init?.body==='string'?init.body:null,route:'unmatched',status:null,response:null,aborted:false};
  ledger.push(row);if(method!=='GET')nonGet.push(row);init?.signal?.addEventListener('abort',()=>{row.aborted=true;},{once:true});
  const reply=(status:number,value:unknown)=>{row.status=status;row.response=JSON.stringify(value);return Response.json(value,{status});};
  if(url.origin===location.origin)for(const f of groups){
   const prefix=`/api/v1/scans/${f.assessment.scan_id}/assessments/${f.assessment.id}/p2`;
   if(method==='GET'&&url.pathname===prefix+'/binding'){row.route='binding';return reply(200,f.binding);}
   if(method==='GET'&&url.pathname===prefix+'/results'&&url.searchParams.get('assessment_version')===String(f.assessment.version)&&url.searchParams.get('offset')==='0'){row.route='result-index';return reply(200,{head_result_id:f.newer.result_id,head_revision:2,result_ids:[f.newer.result_id,f.result.result_id],has_more:false});}
   for(const r of [f.result,f.newer]){
    if(method==='GET'&&url.pathname===prefix+'/results/'+r.result_id&&url.searchParams.get('assessment_version')===String(f.assessment.version)){row.route='fixed-result';return reply(200,r);}
    if(method==='GET'&&['/automatic-review','/preliminary-advice'].some(s=>url.pathname===prefix+'/results/'+r.result_id+s)){row.route='derived-503';return reply(503,{error:{code:'synthetic_derived_unavailable',message:'SYNTHETIC_TEST_ONLY'}});}
   }
   if(url.pathname===prefix+'/ai-analyses'&&method==='POST'){
    row.route='ai-post';if(options.holdPost)await postGate;
    if(options.reject)return reply(options.reject,{error:{code:'synthetic_rejected',message:'SYNTHETIC_TEST_ONLY explicit rejection'}});
    const body=JSON.parse(row.body??'{}'),r=[f.result,f.newer].find(x=>x.result_id===body.result_id);check(r,'Request target missing');
    const v=record(r,body.idempotency_key,options.failed);v.previous_result_id=body.previous_result_id;v.previous_result_sha256=body.previous_result_id?'e'.repeat(64):null;if(!body.previous_result_id)v.changes=[];
    if(options.drift==='result')v.result_sha256='9'.repeat(64);
    if(options.drift==='material')v.actions[0].source_material_ids=['mat_foreign'];
    if(options.drift==='previous')v.previous_result_id='foreign_result';
    if(options.drift==='quote')v.clauses[0].end++;
    values.set(v.analysis_id,v);return reply(201,v);
   }
   if(method==='GET'&&url.pathname===prefix+'/ai-analyses'&&url.searchParams.get('assessment_version')===String(f.assessment.version)){
    row.route='ai-index';const rid=url.searchParams.get('result_id');check([f.result.result_id,f.newer.result_id].includes(rid??''),'Wrong indexed Result');
    // Backend contract is saved rowid ascending, not newest-first.
    return reply(200,{result_id:rid,analysis_ids:[...values.values()].filter(v=>v.result_id===rid).map(v=>v.analysis_id)});
   }
   if(method==='GET'&&url.pathname.startsWith(prefix+'/ai-analyses/')){
    row.route='ai-fixed';const id=url.pathname.split('/').at(-1)!,v=values.get(id);check(v&&v.result_id===url.searchParams.get('result_id'),'Wrong fixed AI lookup');
    if(options.holdRead&&!heldRead){heldRead=true;await readGate;}return reply(200,v);
   }
  }
  unknown.push(row);throw Error('SYNTHETIC_TEST_ONLY unknown route; no native transport fallback');
 };
 return{fetch:fetcher,ledger,nonGet,unknown,releasePost,releaseRead,values};
}
