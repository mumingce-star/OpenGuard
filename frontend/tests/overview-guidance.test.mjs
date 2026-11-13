import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {runtime} from './runtime.mjs';
const nodes=v=>!v||typeof v!=='object'?[]:Array.isArray(v)?v.flatMap(nodes):[v,...nodes(v.props?.children)];
const text=v=>v==null||typeof v==='boolean'?'':Array.isArray(v)?v.map(text).join(''):typeof v==='object'?text(v.props?.children):String(v);
function fixture(){return {resources:Array.from({length:57},(_,i)=>({subject:{resource_id:'resource-'+i,version:'1.0.'+i},name:'component-'+i,priority:i<29?'routine':i===29?'attention':'manual',maintenance_deprecated:[29,30,31].includes(i),reasons:['来源已绑定 '+i],conditions:['保留作者版权声明 '+i],state:i<30?'CONDITIONAL':'NONSTANDARD'})),summary:{priority_counts:{routine:29,attention:1,manual:27},maintenance_count:3,source_packages:55,license_materials:63,license_groups:[{license:'MIT',count:30},{license:'UNOBSERVED',count:27}]}};}
function harness(){const rt=runtime(),m={exports:{}},state=[];let cursor=0,tree;const source=fs.readFileSync(new URL('../src/components/AutomaticProjectAssessment.tsx',import.meta.url),'utf8');vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:m,exports:m.exports,require:n=>n==='react'?{useState(initial){const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useEffect(){}}:n==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})}:n.endsWith('.css')?{}:rt.load(n.replace(/^\.\.\//,'')+'.ts')});const go=[];return {render(review=fixture()){cursor=0;assert.equal(typeof m.exports.AutomaticOverviewContent,'function');tree=m.exports.AutomaticOverviewContent({review,go:(...args)=>go.push(args),query:'assessment_id=a&p2_result=r'});return tree;},click(p){nodes(tree).find(n=>n.type==='button'&&n.props['data-priority']===p).props.onClick();},toggleAll(){const button=nodes(tree).find(n=>n.type==='button'&&/^(?:显示全部|收起为前 5 个组件)/.test(text(n)));assert.ok(button);button.props.onClick();},go};}
test('overview explains every classification with a plain action and preserves 29/1/27',()=>{const h=harness(),tree=h.render(),cards=nodes(tree).filter(n=>n.type==='button'&&n.props['data-priority']);assert.equal(cards.length,3);for(const [i,p] of ['routine','attention','manual'].entries()){assert.equal(cards[i].props['data-priority'],p);assert.match(text(cards[i]),new RegExp(String([29,1,27][i])));assert.match(text(cards[i]),/为什么/);assert.match(text(cards[i]),/怎么做/);}assert.match(text(tree),/常规义务/);assert.match(text(tree),/维护关注/);assert.match(text(tree),/单独审查/);});
test('each category starts with at most five actual members and expands to every member without omissions or overlap',()=>{
 const h=harness(),review=fixture(),seen=new Set();h.render(review);
 const rowsOf=tree=>nodes(tree).filter(node=>node.type==='li'&&typeof node.props?.['data-resource-id']==='string');
 const idsOf=rows=>rows.map(row=>row.props['data-resource-id']);
 const toggleOf=tree=>nodes(tree).find(node=>node.type==='button'&&/^(?:显示全部|收起为前 5 个组件)/.test(text(node)));
 for(const [priority,count]of [['routine',29],['attention',1],['manual',27]]){
  const expected=review.resources.filter(resource=>resource.priority===priority),expectedIds=expected.map(resource=>resource.subject.resource_id);
  h.click(priority);let tree=h.render(review),rows=rowsOf(tree);
  assert.equal(rows.length,Math.min(5,count));assert.deepEqual(idsOf(rows),expectedIds.slice(0,5));
  if(count>5){
   const toggle=toggleOf(tree);assert.ok(toggle);assert.equal(text(toggle),`显示全部 ${count} 个组件`);assert.equal(toggle.props['aria-expanded'],false);
   h.toggleAll();tree=h.render(review);rows=rowsOf(tree);assert.equal(toggleOf(tree).props['aria-expanded'],true);
  }else assert.equal(toggleOf(tree),undefined);
  assert.equal(rows.length,count);assert.deepEqual(idsOf(rows),expectedIds);assert.equal(new Set(idsOf(rows)).size,count);
  for(const row of rows){
   const id=row.props['data-resource-id'],resource=review.resources.find(value=>value.subject.resource_id===id);
   assert.equal(resource.priority,priority);assert.equal(seen.has(id),false);seen.add(id);
   const disclosure=nodes(row).find(node=>node.type==='details'&&node.props?.className==='auto-overview-resource');assert.ok(disclosure);assert.notEqual(disclosure.props.open,true);
   assert.ok(nodes(disclosure).some(node=>node.type==='summary'&&text(node).includes(resource.name)&&text(node).includes(resource.subject.version)));
   assert.ok(resource.reasons.every(reason=>text(row).includes(reason)));
   assert.ok(priority==='manual'?text(row).includes('查看上述原因与原始材料，逐项核对条款或来源；必要时请维护者协助。'):resource.conditions.every(condition=>text(row).includes(condition)));
  }
  if(count>5){
   assert.equal(text(toggleOf(tree)),'收起为前 5 个组件');h.toggleAll();tree=h.render(review);assert.deepEqual(idsOf(rowsOf(tree)),expectedIds.slice(0,5));assert.equal(toggleOf(tree).props['aria-expanded'],false);
   // Leave this category expanded so the next category must reset the view.
   h.toggleAll();assert.equal(rowsOf(h.render(review)).length,count);
  }
 }
 assert.equal(seen.size,review.resources.length);assert.deepEqual([...seen].sort(),review.resources.map(resource=>resource.subject.resource_id).sort());
});
test('deprecated counts distinguish maintenance attention from manual review without reclassifying',()=>{const tree=harness().render();assert.match(text(tree),/3 个组件被官方标记为弃用/);assert.match(text(tree),/1 个归入“维护关注”/);assert.match(text(tree),/2 个归入“单独审查”/);assert.match(text(tree),/不是漏洞数量/);});
test('license distribution is secondary and collapsed, exact assessment navigation remains bound',()=>{const h=harness(),tree=h.render(),detail=nodes(tree).find(n=>n.type==='details'&&n.props.className==='auto-overview-license-details');assert.ok(detail);assert.notEqual(detail.props.open,true);assert.match(text(detail),/MIT/);const b=nodes(tree).find(n=>n.type==='button'&&text(n).includes('进入项目评估'));b.props.onClick();assert.deepEqual(h.go,[['assessment','assessment_id=a&p2_result=r']]);});
test('empty classifications show zero and no invented components',()=>{const h=harness(),v=fixture();v.resources=[];v.summary.priority_counts={routine:0,attention:0,manual:0};v.summary.maintenance_count=0;const tree=h.render(v);assert.equal(nodes(tree).filter(n=>n.props?.className==='auto-overview-resource').length,0);assert.match(text(tree),/没有归入此类/);assert.doesNotMatch(text(tree),/3 个组件被官方/);});
