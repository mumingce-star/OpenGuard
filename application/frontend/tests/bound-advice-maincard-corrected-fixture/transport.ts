import type { Bundle } from './fixture';
export type RequestRecord={sequence:number;time:string;method:string;url:string;classification:'approved_get'|'unknown_route'|'non_get';status:number|null;requestBody:string|null;responseBody:string|null};
export type TransportOptions={automaticStatus?:number;automaticBody?:unknown;resultBody?:unknown};

/** Closed SYNTHETIC_TEST_ONLY transport. It never delegates to native fetch. */
export function createClosedTransport(f:Bundle,options:TransportOptions={}){
 const ledger:RequestRecord[]=[],unknown:RequestRecord[]=[],nonGet:RequestRecord[]=[];
 const prefix=`/api/v1/scans/${encodeURIComponent(f.assessment.scan_id)}/assessments/${encodeURIComponent(f.assessment.id)}/p2`;
 const suffix=`?assessment_version=${f.assessment.version}`;
 const routes=new Map<string,{status:number;body:unknown}>([
  [`/api/v1/scans/${encodeURIComponent(f.assessment.scan_id)}/assessments/${encodeURIComponent(f.assessment.id)}`,{status:200,body:f.assessment}],
  [prefix+'/binding',{status:200,body:f.binding}],
  [prefix+'/results'+suffix+'&offset=0',{status:200,body:{head_result_id:f.newer.result_id,head_revision:f.newer.revision,result_ids:[...new Set([f.newer.result_id,f.result.result_id])],has_more:false}}],
  [prefix+'/results/'+encodeURIComponent(f.result.result_id)+suffix,{status:200,body:options.resultBody??f.result}],
  [prefix+'/results/'+encodeURIComponent(f.result.result_id)+'/automatic-review'+suffix,{status:options.automaticStatus??200,body:options.automaticBody??f.review}],
  [prefix+'/results/'+encodeURIComponent(f.result.result_id)+'/preliminary-advice'+suffix,{status:503,body:{error:{code:'synthetic_preliminary_not_configured',message:'SYNTHETIC_TEST_ONLY: source profile intentionally unavailable'}}}],
 ]);
 // Avoid overriding the fixed response/negative override when r2 is also Index head.
 if(f.newer.result_id!==f.result.result_id)routes.set(prefix+'/results/'+encodeURIComponent(f.newer.result_id)+suffix,{status:200,body:f.newer});
 const fetcher:typeof fetch=async(input,init)=>{
  const req=input instanceof Request?input:null;
  const url=new URL(req?.url??String(input),window.location.origin);
  const method=String(init?.method??req?.method??'GET').toUpperCase();
  const requestBody=typeof init?.body==='string'?init.body:null;
  const item:RequestRecord={sequence:ledger.length+1,time:new Date().toISOString(),method,url:url.href,classification:'approved_get',status:null,requestBody,responseBody:null};
  ledger.push(item);
  // A request is ledgered before any rejection. HTTP errors are explicit fixture
  // responses; unknown destinations and write methods cannot reach any server.
  if(method!=='GET'){item.classification='non_get';nonGet.push(item);throw new Error('SYNTHETIC_TEST_ONLY closed transport rejected non-GET');}
  const route=url.origin===window.location.origin?routes.get(url.pathname+url.search):undefined;
  if(!route){item.classification='unknown_route';unknown.push(item);throw new Error('SYNTHETIC_TEST_ONLY closed transport rejected unknown route');}
  const signal=init?.signal??req?.signal;
  if(signal?.aborted)throw new DOMException('Fixture request aborted','AbortError');
  item.status=route.status;item.responseBody=JSON.stringify(route.body);
  return new Response(item.responseBody,{status:route.status,headers:{'Content-Type':'application/json'}});
 };
 return{fetch:fetcher,ledger,unknown,nonGet,prefix,suffix};
}

export async function closedTransportSelfcheck(f:Bundle){
 const transport=createClosedTransport(f);
 let unknownRejected=false,writeRejected=false,externalRejected=false;
 try{await transport.fetch('/api/v1/not-an-approved-route');}catch{unknownRejected=true;}
 try{await transport.fetch(transport.prefix+'/results',{method:'POST',body:'{}'});}catch{writeRejected=true;}
 try{await transport.fetch('https://not-an-approved-destination.invalid/x');}catch{externalRejected=true;}
 if(!unknownRejected||!writeRejected||!externalRejected||transport.unknown.length!==2||transport.nonGet.length!==1||transport.ledger.length!==3)throw Error('Closed transport rejection ledger selfcheck failed');
 return{classification:'TRANSPORT_SELFCHECK_NOT_APP_REQUESTS',ledger:transport.ledger};
}
