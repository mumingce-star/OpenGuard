import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

// SYNTHETIC_TEST_ONLY: real Service with a closed bottom transport. No Git/npm/model request.
function setup(){
 const rt=runtime(),storage=new Map();
 rt.shared.TextEncoder=TextEncoder;rt.shared.structuredClone=structuredClone;
 rt.shared.sessionStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 const service=rt.load('services/officialSources.ts'),{makeFixture}=rt.load('../tests/bound-advice-maincard-corrected-fixture/fixture.ts'),f=makeFixture();
 const status={schema_version:'openguard-official-sources/1',binding:{...f.result.binding},result_id:f.result.result_id,result_sha256:f.result.result_sha256,
  fetch:{state:'failed',job_id:'job_SYNTHETIC',error_code:'http_budget_exhausted',http_intents:0,http_dispatched:0,http_responses:0},candidate:null,
  analysis:{state:'failed',mode:null,error_code:'official_source_retrieval_unavailable',preview:null,analysis_id:null},adopted_material_ids:[],runtime_jobs_enabled:true,
  explicit_fetch:{allowed:true,reason:'OWNER_ADMITTED_PRE_DISPATCH_FAILURE',request:null}};
 const ledger=[],nonGet=[],unknown=[];
 const accepted=body=>({...status,fetch:{...status.fetch,state:'queued'},explicit_fetch:{allowed:false,reason:'REQUEST_ACCEPTED',request:{idempotency_key:body.idempotency_key,state:'accepted',requested_at:'2026-10-24T00:00:00Z',job_id:'job_SYNTHETIC_NEW',result_id:f.result.result_id,result_sha256:f.result.result_sha256}}});
 let responder=row=>Response.json(accepted(JSON.parse(row.body)),{status:202});
 rt.setFetch(async(url,options)=>{const row={url:String(url),method:options.method??'GET',body:options.body??null};ledger.push(row);if(row.method!=='GET')nonGet.push(row);
  const route=new URL(row.url,'http://SYNTHETIC.invalid').pathname;
  if(row.method==='GET'&&route.endsWith('/official-sources'))return Response.json(status);
  if(row.method==='POST'&&route.endsWith('/official-sources/fetch'))return responder(row);
  unknown.push(row);throw Error('Unknown request; no native transport');});
 return{rt,storage,service,f,status,ledger,nonGet,unknown,accepted,respond:value=>{responder=value;}};
}
function clean(x,posts){assert.equal(x.nonGet.length,posts);assert.equal(x.unknown.length,0);}

test('passive read and refresh use GET only, including budget refusal before dispatch',async()=>{
 const x=setup();for(let i=0;i<2;i++)await x.service.readOfficialSources(x.f.assessment,x.f.result);
 assert.equal(x.ledger.length,2);assert.equal(x.service.canRequestOfficialFetch(x.status),true);clean(x,0);
});
test('explicit request sends one 202 request with exact fixed Result and durable identity',async()=>{
 const x=setup(),out=await x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true);
 assert.equal(out.fetch.state,'queued');const body=JSON.parse(x.nonGet[0].body);
 assert.equal(body.result_id,x.f.result.result_id);assert.equal(body.result_sha256,x.f.result.result_sha256);assert.equal(body.binding.usage_hash,x.f.binding.usage_hash);
 assert.equal(x.service.pendingOfficialFetch(x.f.result).serialized,x.nonGet[0].body);assert.equal(x.service.pendingOfficialFetch(x.f.result).state,'accepted');
 await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));clean(x,1);
});
test('double click while POST is pending cannot dispatch twice',async()=>{
 const x=setup();let release;x.respond(row=>new Promise(done=>{release=()=>done(Response.json(x.accepted(JSON.parse(row.body)),{status:202}));}));
 const first=x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true);
 await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));release();await first;clean(x,1);
});
test('unknown response persists across GET readback and cannot silently replay a fresh key',async()=>{
 const x=setup();x.respond(()=>{throw TypeError('SYNTHETIC_LOST_RECEIPT');});await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));
 const prior=x.service.pendingOfficialFetch(x.f.result);assert.equal(prior.state,'unknown');await x.service.readOfficialSources(x.f.assessment,x.f.result);
 await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));assert.equal(x.service.pendingOfficialFetch(x.f.result).serialized,prior.serialized);clean(x,1);
});
test('matching saved GET receipt resolves unknown without another POST',async()=>{
 const x=setup();x.respond(()=>{throw TypeError('SYNTHETIC_LOST_RECEIPT');});await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));
 const old=x.service.pendingOfficialFetch(x.f.result);Object.assign(x.status,x.accepted(old.body));await x.service.readOfficialSources(x.f.assessment,x.f.result);
 assert.equal(x.service.pendingOfficialFetch(x.f.result).state,'accepted');assert.equal(x.service.pendingOfficialFetch(x.f.result).serialized,old.serialized);clean(x,1);
});
test('readOnly and permission revoked immediately before dispatch send no POST',async()=>{
 const x=setup();await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>false));clean(x,0);
 let permits=0;await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>++permits<2));assert.equal(x.service.pendingOfficialFetch(x.f.result),null);clean(x,0);
});
test('wrong Result, no allow, dispatched request, active job and existing receipt fail before POST',async()=>{
 for(const mutate of [s=>s.result_id='p2res_FOREIGN',s=>s.explicit_fetch.allowed=false,s=>s.fetch.http_dispatched=1,s=>s.fetch.state='running',s=>s.explicit_fetch.request={idempotency_key:'saved'},s=>s.runtime_jobs_enabled=false]){
  const x=setup(),value=structuredClone(x.status);mutate(value);await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,value,()=>true));clean(x,0);
 }
});
test('HTTP409 remains rejected and malformed or foreign 202 remains unknown; no auto replay',async()=>{
 for(const [response,state] of [[()=>Response.json({error:{code:'explicit_fetch_once_only'}},{status:409}),'rejected'],[()=>Response.json({unbound:true},{status:202}),'unknown'],[(row,x)=>Response.json(x.accepted({idempotency_key:'FOREIGN_KEY'}),{status:202}),'unknown']]){
  const x=setup();x.respond(row=>response(row,x));await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));assert.equal(x.service.pendingOfficialFetch(x.f.result).state,state);
  await assert.rejects(x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true));clean(x,1);
 }
});
test('journal stays with account owner and contains no credentials or license body',async()=>{
 const x=setup();x.rt.shared.sessionStorage.setItem('openguard:account-cache-owner:v1','SYNTHETIC_OWNER_A');await x.service.requestOfficialFetch(x.f.assessment,x.f.result,x.status,()=>true);
 const old=x.service.pendingOfficialFetch(x.f.result);x.rt.shared.sessionStorage.setItem('openguard:account-cache-owner:v1','SYNTHETIC_OWNER_B');assert.equal(x.service.pendingOfficialFetch(x.f.result),null);
 x.rt.shared.sessionStorage.setItem('openguard:account-cache-owner:v1','SYNTHETIC_OWNER_A');assert.equal(x.service.pendingOfficialFetch(x.f.result).serialized,old.serialized);
 for(const [key,value]of x.storage)if(key.startsWith('openguard:official-source-fetch:1:'))assert.ok(!/password|token|cookie|csrf|license_text/i.test(value));clean(x,1);
});
test('new fixed Result can read scan-level earlier request as trace, without authenticating or replaying it',async()=>{
 const x=setup();x.status.explicit_fetch={allowed:false,reason:'already_requested',request:{idempotency_key:'OLD_REQUEST',state:'accepted',requested_at:'2026-10-24T00:00:00Z',job_id:'job_OLD',result_id:'p2res_OLD',result_sha256:'7'.repeat(64)}};
 const value=await x.service.readOfficialSources(x.f.assessment,x.f.result);assert.equal(value.explicit_fetch.request.result_id,'p2res_OLD');assert.equal(x.service.canRequestOfficialFetch(value),false);assert.equal(x.service.pendingOfficialFetch(x.f.result),null);clean(x,0);
});
test('rejected model output and unavailable source have distinct plain-language failures, not replacement advice',()=>{
 const x=setup(),rejected=x.service.officialAnalysisFailureMessage('p2_ai_output_rejected'),unavailable=x.service.officialAnalysisFailureMessage('official_source_retrieval_unavailable');
 assert.ok(rejected.includes('未通过原文引用或表述校验')&&rejected.includes('未展示建议')&&rejected.includes('原文仍可预览')&&rejected.includes('由你确认'));
 assert.equal(unavailable,'资料未就绪，本次未生成分析。');assert.ok(!rejected.includes('p2_ai_output_rejected')&&!unavailable.includes('official_source_retrieval_unavailable'));
 assert.equal(x.service.officialAnalysisFailureMessage(null),null);clean(x,0);
});
