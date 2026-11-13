import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {renderToStaticMarkup} from 'react-dom/server';
import {createElement} from 'react';
import ts from 'typescript';
import {runtime} from './runtime.mjs';

// SYNTHETIC_TEST_ONLY: an isolated saved Result, not an owner or production DTO.
const h='a'.repeat(64);
const usage={commercial:true,modified:false,distributed:true,network_service:null,training:null,redistributed_assets:false,source_disclosure:true};
const binding={scan_id:'s-demo',assessment_id:'a-demo',assessment_version:2,registry_revision:3,project_revision:'fixed',facts_hash:h,usage_hash:h,rule_version:'rules/1',assessment_sha256:h};
const assessment={id:'a-demo',scan_id:'s-demo',version:2};
const scan={id:'s-demo',project:'SYNTHETIC_TEST_ONLY',revision:'fixed',resources:[{id:'c-root',name:'demo-root',version:'1.2.3'},{id:'c-peer',name:'demo-peer',version:'4.5.6'}],evidence:[{id:'e1'},{id:'e2'},{id:'e3'}]};
const result={result_id:'r-demo',result_sha256:h,revision:3,binding,data_scope:'TEST_ONLY',usage,material_ids:['m-demo'],resources:[{subject:{resource_id:'c-root',version:'1.2.3'},state:'pending',material_ids:['m-demo']},{subject:{resource_id:'c-peer',version:'4.5.6'},state:'unknown',material_ids:[]}]};
const source=fs.readFileSync(new URL('../src/components/AutomaticProjectAssessment.tsx',import.meta.url),'utf8');
const require=createRequire(import.meta.url);
function load(hooks){const rt=runtime(),m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:m,exports:m.exports,AbortController,Error,require:n=>n==='react'?(hooks??require('react')):n.endsWith('.css')?{}:n.startsWith('../')?rt.load(n.slice(3)+'.ts'):require(n)});return{...m.exports,rt};}
const copy=(props={})=>renderToStaticMarkup(createElement(load().SavedResultAssessmentArticle,{scan,assessment,result,sourceStatus:'NOT_CONFIGURED',...props}));
const nodes=v=>!v||typeof v!=='object'?[]:Array.isArray(v)?v.flatMap(nodes):[v,...nodes(v.props?.children)];

// The inherited parent already renders this deterministic checklist. Its old
// Qwen-preview prose assertions predate that implementation and must not make
// the UI claim a model run or reinstate an obsolete generated narrative.
test('fixed saved result drives a deterministic preparation checklist with exact provenance and counts',()=>{
 const before=JSON.stringify({scan,assessment,result}),html=copy();
 assert.match(html,/使用准备清单/);assert.match(html,/data-saved-result="r-demo"/);
 assert.match(html,/由本版已保存用途与材料引用整理，不是模型输出/);
 assert.match(html,/评估 v2 · 保存结果 r3/);assert.match(html,/2 个资源/);assert.match(html,/3 条扫描证据/);assert.match(html,/演示假设/);
 assert.match(html,/<strong>当前能明确的是准备步骤。<\/strong>/);assert.match(html,/上述清单不新增许可判定/);assert.match(html,/扫描完成表示处理流程结束，不代表全项目已获许可/);
 assert.doesNotMatch(html,/Qwen3辅助判断|预生成示例|本次未实时调用Qwen3|57 个|106 条|<strong>(?:允许商业使用|已获得许可|所有组件已经取得许可认可)<\/strong>/);
 assert.doesNotMatch(html,/<button|<form|<input/);assert.equal(JSON.stringify({scan,assessment,result}),before);
});
test('saved true usage alone gets preparation actions while unknown and false remain distinct',()=>{
 const before=JSON.stringify(result.usage),html=copy();
 const actionFields=[...html.matchAll(/data-usage-preparation="([^"]+)"/g)].map(match=>match[1]);
 assert.deepEqual(actionFields,['commercial','distributed','source_disclosure']);assert.equal(new Set(actionFields).size,3);
 assert.match(html,/2 项用途待确认：对外提供在线服务、用于模型训练/);
 assert.match(html,/本次未选择：修改项目代码、再分发模型／数据等资源/);assert.match(html,/这些值保留为“否”；不代表许可证禁止，也不会代替未知项/);
 assert.match(html,/列出实际发给他人的代码、安装包和依赖/);assert.match(html,/对应版本的 LICENSE／NOTICE/);
 assert.equal(result.usage.network_service,null);assert.equal(result.usage.training,null);assert.equal(result.usage.modified,false);assert.equal(result.usage.redistributed_assets,false);assert.equal(JSON.stringify(result.usage),before);
});
test('saved pending references do not assert approved applicability, official npm appraisal or maintenance success',()=>{
 const html=copy();assert.match(html,/已保存 1 份材料/);assert.match(html,/1 个资源有材料引用，仍待核验/);assert.match(html,/demo-root@1.2.3/);
 assert.match(html,/材料已保存不等于使用已批准；材料真实性、适用范围和义务履行仍分别待核验/);
 assert.match(html,/独立 npm 发行材料初评来源尚未配置/);assert.match(html,/联网取得的资料以下方“联网查找官方依据”的实际记录为准。两者不是同一项核验/);
 assert.doesNotMatch(html,/<(?:strong|p)>已核对官方发行包|已核对 \d+ 个官方|维护状态已确认|没有弃用问题/);
 const empty=copy({result:{...result,material_ids:[],resources:result.resources.map(row=>({...row,material_ids:[]}))}});
 assert.match(empty,/本版尚未绑定材料/);assert.match(empty,/当前版本没有补充材料引用/);assert.match(empty,/联网找到但尚未采用的原文，不计入本版已保存材料/);assert.match(empty,/其他用途版本的材料也不会自动沿用/);
 assert.doesNotMatch(empty,/demo-root@1.2.3|已保存 1 份材料|1 个资源有材料引用/);
});
test('a missing or mismatched resource version cannot supply a narrative material name',()=>{const html=copy({scan:{...scan,resources:[{id:'c-root',name:'FORGED_OTHER_VERSION',version:'9.9.9'}]}});assert.doesNotMatch(html,/FORGED_OTHER_VERSION/);assert.match(html,/关联 1 个资源/);});
test('saved narrative survives actual derived service 503; no write or retry is dispatched',async()=>{
 const state=[],effects=[];let cursor=0,effectCursor=0,dirty=true,tree;const ledger=[];
 const hooks={useState(initial){const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],next=>{state[i]=next;dirty=true;}];},useEffect(fn,deps){const i=effectCursor++;if(!effects[i]||JSON.stringify(effects[i].deps)!==JSON.stringify(deps)){effects[i]?.cleanup?.();effects[i]={deps,cleanup:fn()};}}};
 const module=load(hooks);module.rt.setFetch(async(url,init)=>{ledger.push({url,method:init.method??'GET'});return Response.json({error:{code:'p2_automatic_source_invalid',message:'unavailable'}},{status:503});});
 for(let i=0;i<8;i++){if(dirty){dirty=false;cursor=0;effectCursor=0;tree=module.AutomaticProjectAssessment({scan,assessment,result});}await new Promise(resolve=>setImmediate(resolve));}
 assert.equal(nodes(tree).filter(n=>n.type===module.SavedResultAssessmentArticle).length,1);
 assert.equal(nodes(tree).filter(n=>n.props?.role==='alert').length,1);
 assert.deepEqual(ledger.map(r=>r.method),['GET']);assert.match(ledger[0].url,/r-demo\/automatic-review\?assessment_version=2$/);
 effects.forEach(e=>e.cleanup?.());
});
test('another assessment cannot show stale saved narrative or start its derived GET',()=>{const html=renderToStaticMarkup(createElement(load().AutomaticProjectAssessment,{scan,assessment:{...assessment,id:'a-other'},result}));assert.match(html,/不混用上一版建议/);assert.doesNotMatch(html,/Qwen3|demo-root/);});
test('workbench first-screen narrative is outside disclosures and its action links only reveal existing editors',()=>{const s=fs.readFileSync(new URL('../src/components/P2Workbench.tsx',import.meta.url),'utf8'),file=ts.createSourceFile('P2Workbench.tsx',s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);let found;const visit=n=>{if(ts.isJsxSelfClosingElement(n)&&n.tagName.getText(file)==='AutomaticProjectAssessment')found=n;ts.forEachChild(n,visit);};visit(file);assert.ok(found);for(let p=found.parent;p;p=p.parent){if(ts.isJsxElement(p))assert.notEqual(p.openingElement.tagName.getText(file),'details');}assert.ok(s.indexOf('<nav className="p2-primary-next"')<s.indexOf('<AutomaticProjectAssessment'));assert.ok(s.indexOf('<AutomaticProjectAssessment')<s.indexOf('<SavedAdviceMainCard'));assert.match(s,/href="#p2-optional-supplement" onClick=\{\(\)=>\{setSupplementOpen\(true\);setTab\('answer'\);\}\}/);assert.match(s,/id="p2-optional-supplement"/);assert.match(fs.readFileSync(new URL('../src/pages/Landing.tsx',import.meta.url),'utf8'),/六阶段证据扫描/);});
