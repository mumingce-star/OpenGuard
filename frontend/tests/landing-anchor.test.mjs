import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function route({pathname='/',hash='',scroll=0,target=true}={}){
 const events=new Map(),calls=[],cleanups=[],location={pathname,search:'',hash},history={state:{scroll}},module={exports:{}};
 const source=fs.readFileSync(new URL('../src/hooks/useRoute.ts',import.meta.url),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module,exports:module.exports,URLSearchParams,location,history,document:{getElementById(id){calls.push(['lookup',id]);return target?{scrollIntoView(options){calls.push(['anchor',id,options.block]);}}:null;}},requestAnimationFrame:fn=>fn(),window:{location,history,addEventListener:(name,fn)=>events.set(name,fn),removeEventListener:name=>events.delete(name),scrollTo:(x,y)=>calls.push(['scroll',x,y])},require:name=>name==='react'?{useState:fn=>[fn(),()=>{}],useEffect:fn=>cleanups.push(fn())}:{defaultMode:'api'}});
 module.exports.useRoute();return{calls,pop:()=>events.get('popstate')(),cleanup(){cleanups.forEach(fn=>fn?.());assert.equal(events.size,0);}};
}
for(const hash of ['#capability','#workflow'])test('home '+hash+' wins over saved zero scroll on native fragment navigation',()=>{const r=route({hash});r.pop();assert.deepEqual(r.calls,[['lookup',hash.slice(1)],['anchor',hash.slice(1),'start']]);r.cleanup();});
test('back/forward to a home anchor also keeps its target visible',()=>{const r=route({hash:'#workflow',scroll:420});r.pop();r.pop();assert.equal(r.calls.filter(c=>c[0]==='anchor').length,2);assert.equal(r.calls.some(c=>c[0]==='scroll'),false);r.cleanup();});
test('workspace navigation keeps its saved scroll even if a same-named fragment is present',()=>{const r=route({pathname:'/app/new-scan',hash:'#workflow',scroll:420});r.pop();assert.deepEqual(r.calls,[['scroll',0,420]]);r.cleanup();});
test('unknown home fragment does not scroll to an arbitrary element',()=>{const r=route({hash:'#other',scroll:55});r.pop();assert.deepEqual(r.calls,[['scroll',0,55]]);r.cleanup();});
test('missing home target falls back safely to saved scroll',()=>{const r=route({hash:'#workflow',scroll:55,target:false});r.pop();assert.deepEqual(r.calls,[['lookup','workflow'],['scroll',0,55]]);r.cleanup();});
