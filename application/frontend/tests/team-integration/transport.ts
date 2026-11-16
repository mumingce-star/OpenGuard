import { summary, type Fixture, type ResponseOptions, type View } from './fixture';
export function check(value:unknown,message:string):asserts value{if(!value)throw Error(message);}
export function deferred(){let release!:()=>void;const promise=new Promise<void>(yes=>release=yes);return{promise,release};}
export type Row={sequence:number;method:string;url:string;body:string;route:string|null;status:number|null;aborted:boolean};
export function transport(f:Fixture,o:ResponseOptions){
 const ledger:Row[]=[],unknown:Row[]=[],nonGet:Row[]=[],signals=new Map<Row,AbortSignal|undefined>(),gates=new Set<ReturnType<typeof deferred>>();
 const previousGate=deferred(),materialGate=deferred(),postGate=deferred();for(const g of [previousGate,materialGate,postGate])gates.add(g);
 let view:View='A',head='r2',previousRequests=0,savedResult:typeof f.base.result|null=null;
 const inflight=new Set<Promise<Response>>();
 const markAbort=(row:Row,signal:AbortSignal|undefined)=>{signals.set(row,signal);if(signal)signal.addEventListener('abort',()=>{row.aborted=true;},{once:true});};
 const response=(row:Row,value:unknown,status=200)=>{row.status=status;return Response.json(value,{status});};
 async function dispatch(input:RequestInfo|URL,init:RequestInit={}){
  const url=new URL(String(input),location.origin),method=String(init.method??'GET').toUpperCase(),row:Row={sequence:ledger.length+1,method,url:url.href,body:typeof init.body==='string'?init.body:'',route:null,status:null,aborted:false};ledger.push(row);if(method!=='GET')nonGet.push(row);markAbort(row,init.signal??undefined);
  function bad(message:string):never{unknown.push(row);throw Error('Independent ledger: '+message);}
  if(url.origin!==location.origin||url.username||url.password||url.hash)bad('foreign target');
  for(const [label,bundle] of [['A',f.base],['B',f.other]] as const){
   const prefix=`/api/v1/scans/${bundle.assessment.scan_id}/assessments/${bundle.assessment.id}/p2`,version=`?assessment_version=${bundle.assessment.version}`,key=url.pathname+url.search;
   if(method==='GET'&&key===prefix+'/binding'){row.route='binding-'+label;return response(row,bundle.binding);}
   if(method==='GET'&&key===prefix+'/results'+version+'&offset=0'){row.route='index-'+label;const current=label==='A'&&savedResult?savedResult:head==='r1'?bundle.result:bundle.newer;return response(row,{head_result_id:current.result_id,head_revision:current.revision,result_ids:[bundle.newer.result_id,bundle.result.result_id],has_more:false});}
   if(method==='GET')for(const [kind,result] of [['r1',bundle.result],['r2',bundle.newer]] as const){
    const fixed=prefix+'/results/'+result.result_id;
    if(key===fixed+version){row.route='fixed-'+kind+'-'+label;
     if(label==='A'&&kind==='r1'&&o.initial!=='r1'&&++previousRequests>=1){if(o.holdPrevious)await previousGate.promise;if(o.previous==='missing')return response(row,{error:{code:'p2_missing'}},404);const value=structuredClone(result);if(o.previous==='binding')value.binding.registry_revision++;if(o.previous==='revision')value.revision=4;if(o.previous==='scope')value.data_scope='OWNER';return response(row,value);}
     return response(row,result);
    }
    if(key===fixed+'/automatic-review'+version||key===fixed+'/preliminary-advice'+version){row.route='derived-'+kind+'-'+label;return response(row,{error:{code:'synthetic_derived_unavailable',message:'SYNTHETIC_TEST_ONLY'}},503);}
    if(key===fixed+'/summary'+version){row.route='summary-'+kind+'-'+label;return response(row,summary(result));}
   }
   if(label==='A'&&method==='GET'&&savedResult){const fixed=prefix+'/results/'+savedResult.result_id;if(key===fixed+version){row.route='fixed-r3-A';return response(row,savedResult);}if(key===fixed+'/automatic-review'+version||key===fixed+'/preliminary-advice'+version){row.route='derived-r3-A';return response(row,{error:{code:'synthetic_derived_unavailable',message:'SYNTHETIC_TEST_ONLY'}},503);}if(key===fixed+'/summary'+version){row.route='summary-r3-A';return response(row,summary(savedResult));}}
   if(label==='A'&&method==='GET'&&key.startsWith(prefix+'/materials/')&&url.search===version){const id=url.pathname.split('/').pop()!;const value=f.materials[id];if(!value)bad('unlisted material');row.route='material-'+id;if(o.holdMaterial&&id==='mat_team_1')await materialGate.promise;return response(row,value);}
   if(label==='A'&&method==='POST'&&key===prefix+'/materials'){
    row.route='material-post';const body=JSON.parse(row.body);check(body.parent_result_id===f.base.newer.result_id&&body.expected_revision===2,'original CAS changed');if(o.holdPost)await postGate.promise;
    const result=structuredClone(f.base.newer);result.result_id='res_team_r3';result.revision=3;result.previous_result_id=f.base.newer.result_id;result.result_sha256='3'.repeat(64);result.companion_summary_id='sum_team_r3';result.material_ids.push('mat_team_3');result.resources[0].material_ids.push('mat_team_3');
    const material={...f.materials.mat_team_1,material_id:'mat_team_3',filename:body.filename.toUpperCase(),source_sha256:body.source_sha256,evidence_ids:body.evidence_ids,subject:body.subject,completeness:body.completeness,byte_count:atob(body.content_base64).length};savedResult=result;return response(row,{result,material,answer:null},201);
   }
  }
  return bad('unknown method/path/query');
 }
 const fetcher:typeof fetch=(input,init)=>{const p=dispatch(input,init);inflight.add(p);void p.then(()=>inflight.delete(p),()=>inflight.delete(p));return p;};
 return{fetch:fetcher,ledger,unknown,nonGet,signals,view(v:View){view=v;},setHead(v:'r1'|'r2'){head=v;},releasePrevious:previousGate.release,releaseMaterial:materialGate.release,releasePost:postGate.release,async drain(){for(const g of gates)g.release();await Promise.allSettled([...inflight]);}};
}
