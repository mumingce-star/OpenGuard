import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { runtime } from './runtime.mjs';

// SYNTHETIC_TEST_ONLY. Render the real read-only summary, without fetching or generating.
const require=createRequire(import.meta.url),commit='0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b';
function component(){
 const service=runtime(),module={exports:{}},source=fs.readFileSync(new URL('../src/components/AutomaticProjectAssessment.tsx',import.meta.url),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,require:name=>name==='react'||name==='react/jsx-runtime'?require(name):name.endsWith('.css')?{}:service.load(name.replace(/^\.\.\//,'')+'.ts')});
 return module.exports;
}
function fixtures(){
 const usage={commercial:true,modified:true,distributed:false,network_service:null,training:true,redistributed_assets:true,source_disclosure:false};
 return {scan:{id:'scn_synthetic',input:'https://github.com/http-party/http-server',project:'http-server',revision:commit,resources:[{id:'cmp_synthetic',name:'http-server',version:'14.1.2'}],evidence:[{id:'ev_synthetic'}]},assessment:{id:'asm_synthetic',scan_id:'scn_synthetic',version:1},result:{result_id:'res_synthetic',revision:1,binding:{scan_id:'scn_synthetic',assessment_id:'asm_synthetic',assessment_version:1,project_revision:commit},data_scope:'TEST_ONLY',usage,material_ids:[],resources:[{subject:{resource_id:'cmp_synthetic',version:'14.1.2'},material_ids:[]}]},sourceStatus:'NOT_CONFIGURED'};
}
const render=props=>renderToStaticMarkup(component().SavedResultAssessmentArticle(props));
test('exact fixed http-server project is explained for a new user without a licensing approval',()=>{
 const props=fixtures(),before=JSON.stringify(props),html=render(props);
 assert.match(html,/静态文件服务器/);assert.match(html,/网页、图片/);assert.match(html,/本次准备怎么用/);
 assert.match(html,/使用前要做什么/);assert.match(html,/商业使用/);assert.match(html,/模型训练/);
 assert.doesNotMatch(html,/已确认允许商业使用|已获正式许可|全项目可直接使用/);assert.equal(JSON.stringify(props),before);
});
test('unknown and false usage stay distinct and no missing usage is filled',()=>{
 const props=fixtures(),html=render(props);
 assert.match(html,/待确认用途/);assert.match(html,/对外提供在线服务/);assert.match(html,/本次未选择/);
 assert.match(html,/向他人分发/);assert.match(html,/公开源代码/);assert.equal(props.result.usage.network_service,null);
 assert.equal(props.result.usage.distributed,false);assert.equal(props.result.usage.source_disclosure,false);
});
test('a saved pending material is an observed text, not approved applicability',()=>{
 const props=fixtures();props.result.material_ids=['mat_synthetic'];props.result.resources[0].material_ids=['mat_synthetic'];
 const html=render(props);assert.match(html,/已保存 1 份材料/);assert.match(html,/http-server@14\.1\.2/);
 assert.match(html,/待核验/);assert.match(html,/材料已保存不等于使用已批准/);
});
test('NOT_CONFIGURED identifies the independent npm appraisal rather than denying online fetching',()=>{
 const html=render(fixtures());assert.match(html,/独立 npm 发行材料初评/);assert.match(html,/联网取得的资料以/);
 assert.doesNotMatch(html,/未配置联网|联网功能未开启/);
});
test('lookalike project, wrong revision and a foreign result do not gain the fixed-project explanation',()=>{
 for(const alter of [p=>p.scan.input='https://github.com/another/http-server',p=>p.scan.revision='f'.repeat(40),p=>p.result.binding.scan_id='scn_foreign',p=>p.scan.resources[0].version='1.0.0']){
  const props=fixtures();alter(props);assert.doesNotMatch(render(props),/静态文件服务器/);
 }
});
test('all seven unknown values remain a concrete request for usage, with no positive action claims',()=>{
 const props=fixtures();for(const key of Object.keys(props.result.usage))props.result.usage[key]=null;
 const html=render(props);assert.match(html,/7 项用途待确认/);assert.match(html,/尚未确认使用方式/);
 assert.doesNotMatch(html,/已选择用途下的准备事项/);assert.equal(Object.values(props.result.usage).filter(x=>x===null).length,7);
});
test('read-only summary has no request or write affordance and relegates trace details to disclosure',()=>{
 const html=render(fixtures());assert.doesNotMatch(html,/<button|<form|<input/);
 assert.match(html,/<details[^>]*class="auto-guide-details"/);assert.match(html,/查看版本、来源与判断边界/);
});
