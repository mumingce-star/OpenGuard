import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { runtime } from './runtime.mjs';

// SYNTHETIC_TEST_ONLY. Display projection tests, not backend or browser acceptance.
function componentModule() {
 const service=runtime(),module={exports:{}};
 const source=fs.readFileSync(new URL('../src/components/P2VersionComparison.tsx',import.meta.url),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
  module,exports:module.exports,require:name=>name==='react'?{}:name==='react/jsx-runtime'?{}:service.load(name.replace('../','')+'.ts'),
 });return module.exports;
}
const usage=(patch={})=>({preset:'unknown',commercial:false,modified:true,distributed:false,network_service:true,training:false,redistributed_assets:false,source_disclosure:true,...patch});
const binding=()=>({scan_id:'scn_synthetic',assessment_id:'asm_synthetic',assessment_version:1,registry_revision:13,project_revision:'c'.repeat(40),facts_hash:'a'.repeat(64),usage_hash:'b'.repeat(64),rule_version:'synthetic/1',assessment_sha256:'d'.repeat(64)});
function pair(){
 const row=id=>({subject:{resource_id:id,version:'1.0.0'},state:'unknown',scope:'unknown',material_ids:[],answer_ids:[],evidence_ids:['ev_'+id],gaps:['object_scope_unverified'],advice:[{usage:'modified',saved_value:true,state:'unknown',conditions:[],gaps:['object_scope_unverified'],basis_evidence_ids:[],rule_ids:[]}]});
 const previous={result_id:'res_old',result_sha256:'1'.repeat(64),revision:1,previous_result_id:null,binding:binding(),data_scope:'TEST_ONLY',material_ids:[],answer_ids:[],resources:[row('peer'),row('target')],recomputed_resource_ids:['peer','target'],reused_resource_ids:[]};
 const current=structuredClone(previous);Object.assign(current,{result_id:'res_new',revision:2,previous_result_id:'res_old',result_sha256:'2'.repeat(64),material_ids:['mat_new'],recomputed_resource_ids:['target'],reused_resource_ids:['peer']});
 current.resources[1].material_ids=['mat_new'];current.resources[1].state='pending';current.resources[1].gaps=['uploaded_material_applicability_pending'];
 return{previous,current};
}
test('unknown scene with seven explicit booleans displays custom usage without changing facts',()=>{
 const api=runtime().load('services/usageExperience.ts'),value=usage(),before=JSON.stringify(value);
 assert.equal(api.usageTitle(value),'自定义用途 · 七项已确认');
 assert.match(api.usageDescription(value),/^自定义用途 · 七项已确认/);assert.equal(JSON.stringify(value),before);
});
test('partial, entirely unknown and malformed facts do not imply seven confirmations',()=>{
 const api=runtime().load('services/usageExperience.ts');
 assert.equal(api.usageTitle({preset:'unknown',commercial:false,modified:true}),'自定义用途 · 已确认 2/7 项');
 assert.equal(api.usageTitle({preset:'unknown',commercial:null}),'暂不确定／跳过');
 assert.equal(api.usageTitle(usage({commercial:'false',training:null})),'自定义用途 · 已确认 5/7 项');
 assert.equal(api.usageTitle(usage({preset:'service'})),'对外在线服务');
});
test('Assessment main header and fixed history label share the exact display helper',()=>{
 const text=fs.readFileSync(new URL('../src/pages/Assessment.tsx',import.meta.url),'utf8');
 assert.match(text,/usageTitle\(selected\.usage\)/);assert.doesNotMatch(text,/presets\[selected\.usage\.preset\]/);
});
test('comparison defaults to actual changed resource rather than first or a mere recomputation',()=>{
 const {previous,current}=pair(),before=JSON.stringify([previous,current]),out=componentModule().versionDifference(previous,current);
 assert.equal(out.defaultResourceId,'target');assert.equal(out.addedMaterialCount,1);assert.equal(out.addedAnswerCount,0);
 assert.equal(out.stateChangedCount,1);assert.equal(out.adviceChangedCount,0);assert.equal(out.changedResourceCount,1);
 assert.equal(out.recomputedCount,1);assert.equal(out.reusedCount,1);assert.equal(JSON.stringify([previous,current]),before);
});
test('recomputation is not presented as a changed conclusion',()=>{
 const {previous,current}=pair();current.resources=structuredClone(previous.resources);current.material_ids=[];
 const out=componentModule().versionDifference(previous,current);
 assert.equal(out.recomputedCount,1);assert.equal(out.changedResourceCount,0);assert.equal(out.stateChangedCount,0);assert.equal(out.adviceChangedCount,0);assert.equal(out.defaultResourceId,'target');
});
test('advice changes and added material references are counted independently',()=>{
 const {previous,current}=pair();current.resources[1].advice[0].conditions=['SYNTHETIC_TEST_ONLY 条件'];current.resources[0].material_ids=['mat_new'];
 const out=componentModule().versionDifference(previous,current);assert.equal(out.adviceChangedCount,1);assert.equal(out.addedMaterialCount,1);
});
test('same row values with different JSON key order remain unchanged',()=>{
 const {previous,current}=pair();current.material_ids=[];current.resources=previous.resources.map(row=>Object.fromEntries(Object.entries(row).reverse()));
 const out=componentModule().versionDifference(previous,current);assert.equal(out.changedResourceCount,0);
});
for(const [label,mutate] of [['Assessment',r=>r.binding.assessment_id='other'],['version',r=>r.binding.assessment_version=2],['parent',r=>r.previous_result_id='not_old'],['revision',r=>r.revision=3],['data scope',r=>r.data_scope='OWNER']])test('comparison rejects cross '+label+' instead of manufacturing a delta',()=>{
 const {previous,current}=pair();mutate(current);assert.equal(componentModule().versionDifference(previous,current),null);
});
test('comparison preserves raw gaps in details and names pending state without licensing approval',()=>{
 const text=fs.readFileSync(new URL('../src/components/P2VersionComparison.tsx',import.meta.url),'utf8');
 assert.match(text,/gapLabel\(/);assert.match(text,/原始缺口代码/);assert.match(text,/重新计算不等于结论已经改变/);assert.match(text,/状态变化/);
 assert.doesNotMatch(text,/已确认允许商业使用|已获得正式许可/);
});
