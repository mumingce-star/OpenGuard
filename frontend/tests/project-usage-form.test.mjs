import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const nodes=v=>!v||typeof v!=='object'?[]:Array.isArray(v)?v.flatMap(nodes):[v,...nodes(v.props?.children)];
const text=v=>v==null||typeof v==='boolean'?'':Array.isArray(v)?v.map(text).join(''):typeof v==='object'?text(v.props?.children):String(v);
function render(props){const src=fs.readFileSync(new URL('../src/components/ProjectUsageEditor.tsx',import.meta.url),'utf8');const m={exports:{}};vm.runInNewContext(ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:m,exports:m.exports,require:n=>n==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:n.endsWith('assessments')?{presets:{unknown:'暂不确定',closed_source:'闭源交付'}}:{}});return m.exports.ProjectUsageQuestions(props);}
const usage={preset:'closed_source',commercial:true,modified:null,distributed:true,network_service:false,training:null,redistributed_assets:null,source_disclosure:false};
test('seven plain-language project questions each preserve yes/no/unknown',()=>{const v=render({value:usage,onChange:()=>{}});const groups=nodes(v).filter(n=>n.type==='fieldset'&&n.props['data-usage']);assert.equal(groups.length,7);for(const g of groups){const rs=nodes(g).filter(n=>n.type==='input');assert.equal(rs.length,3);assert.equal(rs.filter(n=>n.props.checked).length,1);}for(const term of ['商业','二次开发','发布','在线','训练','模型或数据','源代码','暂不确定'])assert.ok(text(v).includes(term));});
test('changing modification writes its boolean only without filling unknowns',()=>{let next;const v=render({value:usage,onChange:x=>next=x});const group=nodes(v).find(n=>n.props?.['data-usage']==='modified');nodes(group).find(n=>n.type==='input'&&n.props.value==='true').props.onChange();assert.equal(next.modified,true);assert.equal(next.training,null);assert.equal(next.network_service,false);assert.equal(usage.modified,null);});
test('unknown choice stores null rather than false',()=>{let next;const v=render({value:usage,onChange:x=>next=x});const group=nodes(v).find(n=>n.props?.['data-usage']==='commercial');nodes(group).find(n=>n.type==='input'&&n.props.value==='unknown').props.onChange();assert.equal(next.commercial,null);});
test('project questions do not demand selecting resource IDs',()=>{const v=render({value:usage,onChange:()=>{}});assert.equal(nodes(v).filter(n=>n.type==='input'&&n.props.type==='checkbox').length,0);assert.match(text(v),/项目整体/);assert.match(text(v),/不需要选择依赖/);});
test('disabled state protects all project controls',()=>{const v=render({value:usage,disabled:true,onChange:()=>{}});assert.equal(v.props.disabled,true);});
