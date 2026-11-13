import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { runtime } from './runtime.mjs';

const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
const text = value => value == null || typeof value === 'boolean' ? '' : Array.isArray(value) ? value.map(text).join('') : typeof value === 'object' ? text(value.props?.children) : String(value);
function render(scan) {
  const r = runtime(), m = { exports: {} }, calls = [];
  const source = fs.readFileSync(new URL('../src/pages/Overview.tsx', import.meta.url), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, {
    module:m, exports:m.exports, require:name => name === 'react/jsx-runtime' ? { jsx:(type,props)=>({type,props}), jsxs:(type,props)=>({type,props}) }
    : name.endsWith('/components/ui') ? {Panel:'Panel',SeverityBadge:'SeverityBadge',Empty:'Empty'}
    : name.endsWith('/components/AutomaticProjectAssessment') ? {AutomaticOverview:'AutomaticOverview'}
    : name.endsWith('/components/DecisionBrief') ? {OverviewDecision:'OverviewDecision'}
    : name.endsWith('/services/p2') ? {p2WorkbenchEnabled:true}
    : r.load(name.replace(/^\.\.\//,'')+'.ts'),
  });
  const tree = m.exports.Overview({scan,go:(...args)=>calls.push(args)});
  const cards = nodes(tree).filter(node => node.type === 'button' && String(node.props.className??'').includes('og-overview-metric'));
  return {tree,cards,calls,text:text(tree),count(card){return Number(text(nodes(card).find(node=>node.type==='strong')));}};
}
function scanWith(severities) {
  const r=runtime(), scan=r.load('mocks/data.ts').createSnapshot('overview-fixture','standard');
  scan.mode='api';
  scan.risks=severities.map((severity,index)=>({...scan.risks[0],id:`risk-${index}`,resourceId:scan.resources[index%scan.resources.length].id,severity,outcome:'review_required',ruleId:'license-evidence-gate',handling:index%2?'resolved':'open'}));
  return scan;
}

test('overview exposes five severity cards with dynamic counts independent of handling or license state',()=>{
  const scan=scanWith(['critical','high','high','medium','low','low','low','info','info']);
  const h=render(scan);
  assert.equal(h.cards.length,5);
  assert.deepEqual(h.cards.map(h.count),[1,2,1,3,2]);
  assert.deepEqual(h.cards.map(card=>card.props['data-severity']),['critical','high','medium','low','info']);
});

test('each severity card navigates using the real severity filter including zero buckets',()=>{
  const h=render(scanWith(['info','info']));
  h.cards.forEach(card=>card.props.onClick());
  assert.deepEqual(h.calls,[['risks','severity=critical'],['risks','severity=high'],['risks','severity=medium'],['risks','severity=low'],['risks','severity=info']]);
});

test('all informational license gates remain information instead of invented high risks',()=>{
  const h=render(scanWith(['info','info','info']));
  assert.deepEqual(h.cards.map(h.count),[0,0,0,0,3]);
  assert.match(h.text,/许可依据待核验提示/);
  assert.match(h.text,/零高风险不代表许可已确认/);
});

test('informational findings from another rule are not mislabeled license evidence gaps',()=>{
  const scan=scanWith(['info']);scan.risks[0].ruleId='different-info-rule';
  const h=render(scan);
  assert.doesNotMatch(h.text,/均为许可依据待核验提示/);
  assert.match(h.text,/信息级规则提示/);
});

test('zero findings preserve all five zero buckets without manufacturing a successful license conclusion',()=>{
  const h=render(scanWith([]));
  assert.deepEqual(h.cards.map(h.count),[0,0,0,0,0]);
  assert.doesNotMatch(h.text,/均为许可依据待核验提示/);
  assert.match(h.text,/不代表许可已确认/);
});

test('resource and evidence statistics are separate from severity counts and not fixed at demo totals',()=>{
  const scan=scanWith(['info']);scan.resources=scan.resources.slice(0,2);scan.evidence=scan.evidence.slice(0,3);
  const h=render(scan), summary=nodes(h.tree).find(node=>node.props?.className==='og-overview-inventory');
  assert.ok(summary);
  assert.match(text(summary),/2\s*个资源/);assert.match(text(summary),/3\s*条证据/);
  assert.deepEqual(h.cards.map(h.count),[0,0,0,0,1]);
});

test('API and mock retain their actual severity values without display-derived upgrades',()=>{
  const scan=scanWith(['low','info']);scan.mode='mock';const before=JSON.stringify(scan);
  assert.deepEqual(render(scan).cards.map(card=>card.props['data-severity']),['critical','high','medium','low','info']);
  assert.equal(JSON.stringify(scan),before);
});

test('primary sidebar order follows scan lifecycle and preserves all detail pages',()=>{
  const source=fs.readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  const ast=ts.createSourceFile('App.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let list;
  function walk(node){if(ts.isVariableDeclaration(node)&&node.name.getText(ast)==='items')list=node.initializer;ts.forEachChild(node,walk);}walk(ast);
  assert.ok(list && ts.isArrayLiteralExpression(list));
  const pages=list.elements.map(row=>row.elements[0].text);
  const details=['risks','resources','graph','remediation','diff'];
  assert.deepEqual(pages.filter(page=>!details.includes(page)&&page!=='chat'),['new-scan','progress','overview','assessment','report','report-v2','history']);
  for(const page of details)assert.equal(pages.filter(value=>value===page).length,1);
});


test('navigation icons remain bound to pages after menu reordering',()=>{
  const source=fs.readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  const ast=ts.createSourceFile('App.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const declarations=ast.statements.filter(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='Icon'||ts.isVariableStatement(node)&&node.declarationList.declarations.some(decl=>decl.name.getText(ast)==='navigationIcons'));
  assert.equal(declarations.length,2);
  const code=declarations.map(node=>node.getText(ast)).join('\n')+'\nmodule.exports={Icon};';
  const m={exports:{}};
  vm.runInNewContext(ts.transpileModule(code,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module:m,exports:m.exports,require:()=>({jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})})});
  const icon=page=>nodes(m.exports.Icon({page})).find(node=>node.type==='path').props.d;
  const pages=['report','progress','risks','assessment','history','report-v2'];
  const before=Object.fromEntries(pages.map(page=>[page,icon(page)]));
  for(const page of [...pages].reverse())assert.equal(icon(page),before[page]);
  assert.match(icon('risks'),/^M12 3 2 21h20/);
  assert.match(icon('report'),/^M5 3h10l4 4v14H5z/);
  assert.match(icon('progress'),/^M12 3a9 9/);
  assert.match(icon('assessment'),/^M3 3h7v7/);
  assert.equal(new Set(pages.map(icon)).size,pages.length);
  assert.match(source,/<Icon page=\{page\}/);
  assert.doesNotMatch(source,/<Icon index=/);
});
