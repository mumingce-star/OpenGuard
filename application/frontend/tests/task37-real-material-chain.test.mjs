// Actual captured ASGI payloads replayed offline through production decoders.
// This is not a network request, React/browser E2E, or synthetic successful DTO.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {webcrypto, createHash} from 'node:crypto';
import {runtime} from './runtime.mjs';
const root=path.resolve('../../evidence/real-chain',process.env.TASK37_CAPTURE_TAG||'final');
const read=(dir,name)=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));
for(const [name,expected] of [['original','SUPPORT'],['spdx_conflict','COUNTER_EVIDENCE'],['missing_declaration','UNKNOWN'],['unuploaded_notice','UNKNOWN'],['incomplete_notice','UNKNOWN']]){
 test('captured real pipeline '+name+' strict v4 consumption',async()=>{
  const dir=path.join(root,name),report=read(dir,'SCAN_REPORT.json').scan_run,resourceRaw=read(dir,'RESOURCES.json');
  const result=read(dir,'RESULT_AFTER.json'),old=read(dir,'RESULT_BEFORE.json'),assessment=read(dir,'ASSESSMENT.json');
  const recorded=read(dir,'API_EXCHANGES.json'),rt=runtime();
  Object.assign(rt.shared,{TextEncoder,TextDecoder,structuredClone,crypto:webcrypto});
  const seen=[];
  rt.setFetch(async url=>{
   const u=new URL(String(url),'http://offline.invalid');const key=u.pathname+u.search;
   const hit=recorded.find(r=>r.method==='GET'&&r.path===key);assert.ok(hit,'unrecorded request '+key);
   const raw=fs.readFileSync(path.join(dir,hit.raw_response_file));
   assert.equal(createHash('sha256').update(raw).digest('hex'),hit.response_sha256);
   seen.push(key);return new Response(raw,{status:hit.status,headers:{'Content-Type':'application/json'}});
  });
  const scans=rt.load('services/scans.ts'),p2=rt.load('services/p2.ts'),claims=rt.load('services/materialClaims.ts');
  const anchor=scans.declarationSnapshotFromReport(report.id,report,resourceRaw.items);assert.ok(anchor);
  const checked=p2.validateResult(result,assessment,result.binding,result.result_id);
  const view=await claims.readMaterialClaims(assessment,checked,anchor);
  assert.deepEqual(JSON.parse(JSON.stringify(view)),read(dir,'MATERIAL_CLAIMS.json'));
  assert.equal(view.schema_version,'openguard-material-claims/4');
  assert.equal(view.rule_version,'mit-apache2-bound-claim/4');
  const impact=JSON.parse(JSON.stringify(view.incremental_impact));
  assert.equal(impact.mode,'INCREMENTAL_DERIVED');
  assert.equal(impact.unchanged_claims_verified,true);
  assert.deepEqual(impact.affected_resource_ids,result.recomputed_resource_ids);
  assert.deepEqual(impact.unchanged_resource_ids,result.reused_resource_ids);
  const component=report.components.find(c=>c.name==='is-number'&&c.version==='7.0.0');assert.ok(component);
  const exact=view.advice.filter(a=>a.subject.resource_id===component.id);
  assert.equal(exact.length,3);assert.ok(exact.every(a=>a.state===expected));
  const previous=await p2.readPreviousResult(assessment,result.binding,result);
  assert.equal(previous.result_id,old.result_id);
  const oldview=await claims.readMaterialClaims(assessment,previous,anchor);
  assert.equal(oldview.materials.length,0);
  assert.ok(oldview.advice.filter(a=>a.subject.resource_id===component.id).every(a=>a.state==='UNKNOWN'));
  assert.equal(oldview.incremental_impact.mode,'INITIAL_RESULT');
  assert.equal(impact.previous_result_id,oldview.result_id);
  assert.equal(impact.previous_revision,oldview.revision);
  assert.equal(impact.previous_view_id,oldview.view_id);
  for(const delta of impact.changed_claims){
   const oldClaim=oldview.advice.find(a=>a.claim_ids[0]===delta.previous_claim_id);
   assert.ok(oldClaim);assert.equal(delta.previous_state,oldClaim.state);
   assert.deepEqual(delta.previous_reasons,Array.from(oldClaim.reasons));
  }
  assert.ok(seen.every(p=>!p.includes('latest')));
  if(name==='original'){
   const conflicted=p2.validateResult(read(dir,'CONFLICT_RESULT.json'),assessment,result.binding);
   const conflict=await claims.validateMaterialClaims(read(dir,'CONFLICT_CLAIMS.json'),conflicted,anchor);
   assert.ok(conflict.advice.filter(a=>a.subject.resource_id===component.id).every(a=>a.state==='COUNTER_EVIDENCE'));
   assert.equal(conflict.incremental_impact.previous_view_id,view.view_id);
   assert.equal(conflict.incremental_impact.previous_revision,view.revision);
   // Mutate a real captured quote without changing its hash. Must fail closed.
   const bad=structuredClone(view);bad.materials[0].clauses[0].quote='X'+bad.materials[0].clauses[0].quote.slice(1);
   await assert.rejects(claims.validateMaterialClaims(bad,result,anchor));
  }
 });
}
