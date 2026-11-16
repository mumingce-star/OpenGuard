import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
test('obligation display translates only the exact frozen rule text and preserves originals',()=>{
 const s=runtime().load('services/resolution.ts');
 const source={rule_id:'LIC-MIT-NOTICE',rule_version:'1.0.0',action:'retain_license_notice',requirement:'Preserve the copyright and permission notice with the distributed material.',trigger:'Verified MIT-licensed material is included in a distribution',fulfillment:'pending'};
 const shown=s.presentObligation(source);
 assert.equal(shown.requirement,'随交付材料保留版权声明与许可声明');
 assert.equal(shown.trigger,'分发已核验的 MIT 许可材料时');
 assert.equal(source.requirement,'Preserve the copyright and permission notice with the distributed material.');
 for(const patch of [{rule_id:'OTHER'},{rule_version:'next'},{requirement:'Extra condition'}, {trigger:'Different trigger'}]) {
  const other={...source,...patch};assert.equal(s.presentObligation(other).requirement,other.requirement);assert.equal(s.presentObligation(other).trigger,other.trigger);
 }
});
test('model conflict clues remain pending and reject authority or single-source claims',()=>{
 const s=runtime().load('services/resolution.ts');
 const conflict={resource_id:'r',left_material_id:'m1',right_material_id:'m2',left_quote:'left',right_quote:'right',kind:'TEXT_DIFFERENCE',review_status:'pending',authorization_verified:false,producer_type:'model'};
 const model={status:'completed',calls:1,output:{formal:false,candidates:[],conflict_clues:[conflict]}};
 assert.equal(s.validateBrief({...brief(),resolution_model:model},'s','a',1).resolution_model.output.conflict_clues.length,1);
 for(const patch of [{authorization_verified:true},{review_status:'approved'},{right_material_id:'m1'}])
  assert.throws(()=>s.validateBrief({...brief(),resolution_model:{...model,output:{...model.output,conflict_clues:[{...conflict,...patch}]}}},'s','a',1));
});
test('case invalidations require fixed reasons and retain a read-only result',()=>{
 const s=runtime().load('services/resolution.ts');
 const cases=[{resource_id:'r',matches:[],invalidations:[{case_id:'c',reason:'WITHDRAWN'}],corpus_status:'NO_MATCH'}];
 assert.equal(s.validateBrief({...brief(),resolution_cases:cases},'s','a',1).formal,false);
 assert.throws(()=>s.validateBrief({...brief(),resolution_cases:[{...cases[0],invalidations:[{case_id:'c',reason:42}]}]},'s','a',1));
});
const brief = () => ({formal:false,display_version:'decision-brief/1',scan_id:'s',assessment_id:'a',assessment_version:1,facts_hash:'a'.repeat(64),title:'尚不能确认',permission_state:'unknown',notice:'不是授权',gaps:[],dimensions:[],obligations:[],local_results:[],resolution_observations:[]});
test('progressive use questions max two; preset never assigns facts',()=>{
 const r=runtime(),res=r.load('services/resolution.ts'),a=r.load('services/assessments.ts');
 for(const preset of Object.keys(a.presets)) {const u={...a.emptyUsage(),preset};assert.ok(res.relevantUsage(preset).length<=2);for(const k of Object.keys(a.usageFields))assert.equal(u[k],null);}
});
test('brief rejects another assessment, allowed badge and verified material',()=>{
 const s=runtime().load('services/resolution.ts');assert.equal(s.validateBrief(brief(),'s','a',1).formal,false);
 for(const patch of [{assessment_id:'other'},{assessment_version:2},{formal:true},{permission_state:'allowed'}, {resolution_observations:[{name:'acme',version:'1',authorization_verified:true,review_status:'verified',atomic_facts:{}}]}])assert.throws(()=>s.validateBrief({...brief(),...patch},'s','a',1));
});
test('read summary and job history are GET only; no storage or fallback',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts'),calls=[];
 r.setFetch(async(url,init)=>{calls.push(init.method??'GET');return Response.json(url.includes('decision-brief')?brief():{items:[]});});
 await s.readBrief('s','a',1);await s.readJobs('s','a',1);assert.deepEqual(calls,['GET','GET']);assert.equal(r.storage.size,0);
});
test('explicit local work binds exact version, hash, request and network false',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts');let sent;
 r.setFetch(async(url,init)=>{sent=JSON.parse(init.body);return Response.json({job_id:'j',request_key:'key',version:1,status:'queued',snapshot_id:null,binding:{scan_id:'s',assessment_id:'a',assessment_version:1}});});
 await s.resolveLocal('s','a',1,'b'.repeat(64),'key',true);assert.equal(sent.allow_network,false);assert.equal(sent.expected_facts_hash,'b'.repeat(64));assert.equal(sent.use_model,true);
});
test('old scan callers do not implicitly opt into material retention',async()=>{
 const r=runtime(),s=r.load('services/scans.ts');let sent;
 r.setFetch(async(url,init)=>{sent=JSON.parse(init.body);return Response.json({scan_id:'s',status:'queued',status_url:'/api/v1/scans/s'});});
 await s.createApiScan({kind:'github',url:'https://github.com/test/project'},'r');assert.equal(sent.resolve_local_materials,undefined);
 await assert.rejects(s.createApiScan({kind:'github',url:'https://github.com/test/project',resolveLocalMaterials:true},'r'),/未接入/);assert.equal(sent.resolve_local_materials,undefined);
});
test('old backend absence and malformed snapshot fall back without inventing data',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts');let calls=0;
 r.setFetch(async()=>{calls++;return Response.json({error:{message:'Not configured'}},{status:404});});
 await assert.rejects(()=>s.readBrief('s','a',1));assert.equal(calls,1);assert.equal(r.storage.size,0);
 assert.throws(()=>s.validateBrief({...brief(),resolution_snapshot_id:'snap',resolution_snapshot_hash:'wrong'},'s','a',1));
});
