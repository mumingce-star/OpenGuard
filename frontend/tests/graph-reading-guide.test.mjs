import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const source=fs.readFileSync(new URL('../src/pages/Graph.tsx',import.meta.url),'utf8');
function loadGuide(){const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:m,exports:m.exports,require:name=>name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:{}});return m.exports.GraphReadingGuide;}
const nodes=value=>!value||typeof value!=='object'?[]:Array.isArray(value)?value.flatMap(nodes):[value,...nodes(value.props?.children)];
const text=value=>value==null||typeof value==='boolean'?'':Array.isArray(value)?value.map(text).join(''):typeof value==='object'?text(value.props?.children):String(value);
const props={project:'true-project',resourceLabel:'actual-component 2.1.0',sourceLabel:'package-lock.json / dependency entry',onReadSource:()=>{}};
test('guide explains reading direction in ordinary language',()=>{const guide=loadGuide()(props);const t=text(guide);assert.match(t,/从左到右/);assert.match(t,/项目/);assert.match(t,/组件/);assert.match(t,/观测/);assert.match(t,/来源/);assert.equal(guide.props['aria-label'],'图谱阅读说明');});
test('guide uses the selected real resource and source rather than a canned example',()=>{const t=text(loadGuide()(props));assert.ok(t.includes(props.project));assert.ok(t.includes(props.resourceLabel));assert.ok(t.includes(props.sourceLabel));assert.ok(!t.includes('chalk'));});
test('guide distinguishes edge meaning from permission or confidence',()=>{const t=text(loadGuide()(props));for(const term of ['实线','虚线','点线','授权','置信度'])assert.ok(t.includes(term));});
test('source action preserves exact parent callback',()=>{let called=0;const v=loadGuide()({...props,onReadSource:()=>called++});const button=nodes(v).find(n=>n.type==='button');assert.match(text(button),/查看这条来源/);button.props.onClick();assert.equal(called,1);});
test('missing source is stated and no evidence action is invented',()=>{const v=loadGuide()({...props,sourceLabel:null,onReadSource:undefined});assert.match(text(v),/当前资源没有已关联的来源节点/);assert.equal(nodes(v).filter(n=>n.type==='button').length,0);});
test('guide updates both resource and source when selection changes',()=>{const render=loadGuide();const a=text(render(props));const b=text(render({...props,resourceLabel:'other-component 8.0',sourceLabel:'LICENSE'}));assert.ok(a.includes('actual-component 2.1.0'));assert.ok(!b.includes('actual-component'));assert.ok(b.includes('other-component 8.0'));assert.ok(b.includes('LICENSE'));});
