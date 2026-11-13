import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {runtime} from './runtime.mjs';
import {nodes,text,scanHarness} from './new-scan-harness.mjs';
function load(path, extra='') {
 const r=runtime(),m={exports:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../src/'+path,import.meta.url),'utf8')+extra,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:m,exports:m.exports,Intl,require:n=>n==='react'?{}:n==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'Fragment'}:n.endsWith('/ui')?{StatusBadge:'StatusBadge'}:r.load(n.replace('../','')+'.ts')});return m.exports;
}
const usage={preset:'closed_source',commercial:true,modified:null,distributed:false,network_service:null,training:null,redistributed_assets:null,source_disclosure:null};
test('compact usage keeps seven independent tristate fields inside optional disclosure',()=>{
 const t=load('components/UsageForm.tsx').UsageForm({value:usage,onChange(){},compact:true});
 const details=nodes(t).filter(n=>n.type==='details');assert.equal(details.length,1);
 const fields=nodes(details[0]).filter(n=>n.type==='select');assert.equal(fields.length,7);
 for(const f of fields)assert.deepEqual(nodes(f).filter(n=>n.type==='option').map(n=>n.props.value),['unknown','true','false']);
 assert.equal(fields.filter(f=>f.props.value==='true').length,1);assert.equal(fields.filter(f=>f.props.value==='false').length,1);
});
test('compact field edits preserve every other value and scenario edits do not fill facts',()=>{
 let next;const t=load('components/UsageForm.tsx').UsageForm({value:usage,onChange:v=>next=v,compact:true});
 const selects=nodes(t).filter(n=>n.type==='select');selects[0].props.onChange({target:{value:'internal'}});
 assert.equal(next.commercial,true);assert.equal(next.modified,null);assert.equal(next.distributed,false);
 selects[1].props.onChange({target:{value:'unknown'}});assert.equal(Object.values(next).filter(v=>v===true).length,0);assert.equal(next.distributed,false);
});
test('noncompact usage retains the existing priority and secondary groups',()=>{
 const t=load('components/UsageForm.tsx').UsageForm({value:usage,onChange(){}});
 assert.equal(nodes(t).filter(n=>n.type==='select').length,8);assert.match(text(t),/其余用途事实/);
});
test('new composer still freezes confirmation and only second submit sends request',async()=>{
 const h=scanHarness();await h.settle();await h.git();h.edit(usage);await h.settle();await h.submit();assert.ok(h.confirm);assert.equal(h.calls.length,0);
 await h.submit();assert.equal(h.calls.length,1);assert.equal(h.calls[0].input.usage.distributed,false);assert.equal(h.calls[0].input.usage.modified,null);h.resolve();await h.settle();
});
const base={source_type:'git',source:'https://github.com/example/repo',project_identity:{method:'canonical_github_repo_v1',key:'github.com/example/repo'},revision:'abcdef123456789',status:'completed',stage:'completed',created_at:'2026-10-15T00:00:00Z',finished_at:'2026-10-15T00:00:20Z',component_count:11,ai_asset_count:2,finding_count:3,summary:{evidence_count:19},latest_assessment:{version:2,assessment_id:'asm_exact'}};
const Row=load('pages/History.tsx','\nexport {HistoryRow};').HistoryRow;
test('history preserves old facts and adds actual evidence count',()=>{
 const t=Row({item:base,open(){},report(){},assessment(){}});for(const v of ['11','19','AI 资源','asm_exact','abcdef123456','查看报告','查看评估','打开任务'])assert.ok(text(t).includes(v),v);
});
test('failed history keeps diagnostic entry without report or invented assessment',()=>{
 const t=Row({item:{...base,status:'failed',latest_assessment:null},open(){},report(){},assessment(){}});assert.match(text(t),/打开任务/);assert.doesNotMatch(text(t),/查看报告|查看评估/);
});
test('partial history keeps partial warning and available report',()=>{
 const t=Row({item:{...base,status:'partial'},open(){},report(){},assessment(){}});assert.match(text(t),/覆盖范围不完整/);assert.match(text(t),/查看报告/);
});
test('row keyboard and nested button activation do not double navigate',()=>{
 let opened=0,reports=0;const t=Row({item:base,open(){opened++},report(){reports++},assessment(){}});const row={};
 t.props.onKeyDown({key:'Enter',target:row,currentTarget:row,preventDefault(){}});assert.equal(opened,1);
 t.props.onKeyDown({key:'Enter',target:{},currentTarget:row,preventDefault(){}});assert.equal(opened,1);
 nodes(t).find(n=>n.type==='button'&&text(n)==='查看报告').props.onClick({stopPropagation(){}});assert.equal(reports,1);assert.equal(opened,1);
});
