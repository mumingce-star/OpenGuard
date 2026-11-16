import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
function harness(){
 const states=[],effects=[],calls=[];let cursor=0;
 const react={useState(v){const n=cursor++;if(!(n in states))states[n]=v;return [states[n],x=>{states[n]=x;}];},useEffect(fn){effects.push(fn);}};
 const service={reviewLabels:{AI_ASSISTED:'AI辅助研判'},loadReview(a,readOnly){return new Promise((resolve,reject)=>calls.push({a,readOnly,resolve,reject}));},readReview(){throw Error('unexpected poll');}};
 const source=fs.readFileSync(new URL('../src/components/AiReview.tsx',import.meta.url),'utf8');
 const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
 const mod={exports:{}};vm.runInNewContext(js,{module:mod,exports:mod.exports,require:n=>n==='react'?react:n.endsWith('/aiReview')?service:n.endsWith('/assessmentTier')?{tierAllowsDerived:()=>true,readAssessmentTier:async()=>{throw Error('not configured');}}:n==='./StageResult'?{StageResult:()=>null}:n==='./AssessmentTier'?{AssessmentTier:()=>null,TierUpgradePlans:()=>null}:n.endsWith('.css')?{}:require(n),setTimeout,clearTimeout});
 return {states,calls,render(a,readOnly=true){cursor=0;return mod.exports.AiReview({assessment:a,readOnly});},start(){const cleanups=effects.splice(0).map(fn=>fn());return ()=>cleanups.forEach(fn=>fn?.());}};
}
const a={id:'v6',version:6,facts_hash:'f'},b={id:'v7',version:7,facts_hash:'g'};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('R6 AI component late v6 response cannot replace selected v7 result',async()=>{
 const h=harness();h.render(a);const cleanup=h.start();cleanup();h.render(b);h.start();
 h.calls[0].resolve({binding:{assessment_id:'v6'},job:null,snapshot:null});await flush();assert.equal(h.states[0],null);
 const current={binding:{assessment_id:'v7'},job:null,snapshot:null};h.calls[1].resolve(current);await flush();assert.equal(h.states[0],current);
 assert.deepEqual(h.calls.map(c=>c.readOnly),[true,true]);
});
test('R6 AI component unavailable result displays fallback without hiding original assessment boundary',async()=>{
 const h=harness();h.render(a);h.start();h.calls[0].reject(new Error('controlled unavailable'));await flush();
 const rendered=h.render(a);assert.match(JSON.stringify(rendered),/AI研判暂不可用；原评估与义务保留/);assert.equal(h.calls.length,1);
});
test('R6 AI component disposed request failure does not overwrite a new selection',async()=>{
 const h=harness();h.render(a);h.start()();h.render(b);h.start();h.calls[0].reject(new Error('old failure'));await flush();assert.equal(h.states[1],false);
 h.calls[1].resolve({job:null,snapshot:null});await flush();assert.equal(h.states[1],false);
});
