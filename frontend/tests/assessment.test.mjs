import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
const fixture = () => ({ id: 'a1', scan_id: 's1', version: 1, usage: {preset: 'unknown'}, generated_at: '2026-09-10T12:00:00Z', ai_status: 'not_requested', ai_summary: null, summary: '证据不足', dimensions: [{id:'commercial',title:'商业使用',status:'unknown',conclusion:'待核验',conditions:[],restrictions:[],unknowns:['未核验'],resource_ids:[],finding_ids:[],evidence_ids:[]}],coverage_issues:[],resource_ids:[],finding_ids:[],evidence_ids:[],obligations:[] });
test('assessment validates scan ownership, strict conclusions and evidence arrays', () => {
 const s=runtime().load('services/assessments.ts');
 assert.equal(s.validateAssessment(fixture(),'s1').id,'a1');
 assert.throws(()=>s.validateAssessment(fixture(),'s2'),/契约/);
 for(const mutate of [x=>x.dimensions[0].status='allowed',x=>x.evidence_ids=null,x=>x.generated_at='invalid',x=>x.version=0,x=>x.usage.preset='commercial']) { const x=fixture(); mutate(x); assert.throws(()=>s.validateAssessment(x,'s1'),/契约/); }
});
test('usage defaults remain unknown without inferred commercial or disclosure choice', () => {
 const s=runtime().load('services/assessments.ts');
 const u=s.emptyUsage(); assert.equal(u.preset,'unknown');
 for(const k of Object.keys(s.usageFields)) assert.equal(u[k],null);
 const changed={...u,preset:'closed_source'}; assert.equal(changed.source_disclosure,null); assert.equal(changed.commercial,null);
});
test('reading saved assessment and chat performs GET only and stores no mock history', async () => {
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push([url,init.method??'GET']);return Response.json(url.endsWith('/chat')?{items:[],generation:0,limits:{max_message_chars:2000,max_turns:50}}:{items:[fixture()],usage:null});});
 await s.listAssessments('s1'); await s.getChat('s1');
 assert.deepEqual(calls.map(x=>x[1]),['GET','GET']); assert.equal(r.storage.size,0);
});
test('404 is unsupported error rather than empty or demo assessment', async()=>{
 const r=runtime(),s=r.load('services/assessments.ts');r.setFetch(async()=>new Response('{}',{status:404}));
 await assert.rejects(s.listAssessments('s1'),e=>e.status===404); assert.equal(r.storage.size,0);
});
test('explicit generation retains the same caller request key and exact nullable usage',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push(JSON.parse(init.body));return Response.json({request_id:'same',status:'pending'});});
 await s.createAssessment('s1',s.emptyUsage(),'same');await s.createAssessment('s1',s.emptyUsage(),'same');
 assert.equal(calls[0].request_id,calls[1].request_id); assert.equal(calls[0].usage.commercial,null);
 assert.throws(()=>s.validateJob({request_id:'other',status:'pending'},'same'),/契约/);
});
test('chat submission binds version and generation; clear sends explicit confirmation',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];r.setFetch(async(url,init)=>{calls.push({url,...init});return Response.json({generation:4,items:[]});});
 await s.sendChat('s1',{assessment_id:'a1',request_id:'q1',message:'问题',generation:3});await s.clearChat('s1',3);
 assert.equal(JSON.parse(calls[0].body).assessment_id,'a1'); assert.equal(JSON.parse(calls[0].body).generation,3);
 assert.equal(calls[1].method,'DELETE'); assert.match(calls[1].url,/confirmed=true&generation=3$/);
});
test('invalid chat generation and states are rejected',()=>{
 const s=runtime().load('services/assessments.ts');
 assert.throws(()=>s.validateChat({items:[],generation:-1,limits:{max_message_chars:2000,max_turns:50}}),/契约/);
});
test('versioned report links encode identifiers and do not replace old report paths',()=>{
 const s=runtime().load('services/assessments.ts');
 assert.equal(s.assessmentReportUrl('a/b','x/y','html'),'/api/v1/scans/a%2Fb/assessments/x%2Fy/report?format=html');
});

test('new scan carries explicit usage in Git and ZIP without changing source contract', async () => {
 const r=runtime(),s=r.load('services/scans.ts'),bodies=[];
 r.setFetch(async(url,init)=>{bodies.push(init.body);return Response.json({scan_id:'s1',status:'queued',status_url:'/api/v1/scans/s1'});});
 const usage={preset:'service',commercial:null,network_service:true};
 await s.createApiScan({kind:'github',url:'https://github.com/pallets/flask',usage},'g1');
 const git=JSON.parse(bodies[0]);assert.equal(git.source_type,'git');assert.deepEqual(git.usage,usage);
 const file=new Blob(['PK'],{type:'application/zip'});Object.defineProperty(file,'name',{value:'fixed.zip'});
 await s.createApiScan({kind:'zip',file,usage},'z1');
 assert.deepEqual(JSON.parse(bodies[1].get('usage')),usage);assert.equal(bodies[1].get('source_type'),'zip');
});
test('assessment and chat task routes coexist with old risk and report paths',()=>{
 const r=runtime(),route=r.load('hooks/useRoute.ts');
 for(const page of ['assessment','chat','risks','resources','report','progress']) {r.shared.window.location={pathname:'/app/scans/s1/'+page,search:'?mode=api&assessment_id=a1'};const parsed=route.readRoute();assert.equal(parsed.page,page);assert.equal(parsed.scanId,'s1');assert.equal(parsed.query.get('assessment_id'),'a1');}
});
test('saved pending assessment job restores after refresh with GET only',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push(init.method??'GET');return Response.json(url.includes('/jobs/')?{request_id:'j1',status:'pending'}:{items:[],usage:null,pending_job:{request_id:'j1',status:'pending'}});});
 const saved=await s.listAssessments('s1');assert.equal(saved.pending_job.request_id,'j1');
 const job=await s.getJob('s1',saved.pending_job.request_id);assert.equal(job.status,'pending');assert.deepEqual(calls,['GET','GET']);
});
test('a failed assessment can be retried with a new explicit request key',async()=>{
 const r=runtime(),s=r.load('services/assessments.ts'),keys=[];
 r.setFetch(async(url,init)=>{const body=JSON.parse(init.body);keys.push(body.request_id);return Response.json({request_id:body.request_id,status:keys.length===1?'failed':'pending',error:keys.length===1?'model unavailable':null});});
 assert.equal((await s.createAssessment('s1',s.emptyUsage(),'first')).status,'failed');
 assert.equal((await s.createAssessment('s1',s.emptyUsage(),'explicit-retry')).status,'pending');assert.notEqual(keys[0],keys[1]);
});

test('AI summary evidence ids are retained, optional for old versions, and validated',()=>{
 const s=runtime().load('services/assessments.ts'),x=fixture();x.ai_evidence_ids=['e1','e2'];
 assert.equal(s.validateAssessment(x,'s1').ai_evidence_ids.join(','),'e1,e2');
 x.ai_evidence_ids='invalid';assert.throws(()=>s.validateAssessment(x,'s1'));
 assert.equal(s.validateAssessment(fixture(),'s1').ai_evidence_ids,undefined);
});
