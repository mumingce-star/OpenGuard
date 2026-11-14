import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import {runtime} from './runtime.mjs';
const sourceRoot=process.env.TARGET_FRONTEND;
function harness(reduced=false){
 const rt=runtime(),hooks=[],pending=[],timers=new Map(),cache=new Map();let cursor=0,next=1,now=0,dirty=false;
 const clock=class extends Date{static now(){return now;}};
 const react={useState(initial){const i=cursor++;hooks[i]??={value:typeof initial==='function'?initial():initial};return[hooks[i].value,value=>{const v=typeof value==='function'?value(hooks[i].value):value;if(!Object.is(v,hooks[i].value)){hooks[i].value=v;dirty=true;}}];},useRef(initial){const i=cursor++;hooks[i]??={current:initial};return hooks[i];},useEffect(fn,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j]))){pending.push(()=>{old?.cleanup?.();hooks[i]={deps,cleanup:fn()};});}}};
 const timer=(fn,delay=0,interval=false)=>{const id=next++;timers.set(id,{fn,at:now+delay,interval:interval?delay:0});return id;};
 function load(relative){
  if(cache.has(relative))return cache.get(relative);
  const module={exports:{}},file=sourceRoot?path.join(sourceRoot,'src',relative):new URL('../src/'+relative,import.meta.url);
  const source=fs.readFileSync(file,'utf8');cache.set(relative,module.exports);
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,Date:clock,Math,Set,console,clearTimeout:id=>timers.delete(id),clearInterval:id=>timers.delete(id),window:{setTimeout:(fn,d)=>timer(fn,d),clearTimeout:id=>timers.delete(id),setInterval:(fn,d)=>timer(fn,d,true),clearInterval:id=>timers.delete(id)},require:name=>{
   if(name==='react')return react;if(name==='react/jsx-runtime')return{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
   if(name.endsWith('.css'))return{};if(name==='../components/ui')return{StatusBadge:()=>null,useNotice:()=>()=>{}};
   if(name==='../hooks/useReducedMotion')return{useReducedMotion:()=>reduced};
   if(name.startsWith('./'))return load('pages/'+name.slice(2)+'.ts');
   return rt.load(name.replace('../','')+'.ts');
  }});return module.exports;
 }
 const Component=load('pages/Progress.tsx').Progress;
 function render(scan,error=null){let tree;for(let i=0;i<20;i++){dirty=false;cursor=0;tree=Component({scan,reload:()=>{},onResults:()=>{},pollingError:error});while(pending.length)pending.shift()();if(!dirty)return tree;}throw Error('render did not settle');}
 return{render,tick(ms,scan,error=null){const end=now+ms;let tree=render(scan,error);for(let i=0;i<20000;i++){const due=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;const[id,t]=due;now=t.at;timers.delete(id);if(t.interval)timers.set(id,{...t,at:now+t.interval});t.fn();tree=render(scan,error);}now=end;return render(scan,error);},unmount(){for(const h of hooks)h?.cleanup?.();},get timers(){return timers.size;}};
}
const nodes=v=>!v||typeof v!=='object'?[]:Array.isArray(v)?v.flatMap(nodes):[v,...nodes(v.props?.children)];
const text=v=>v==null||typeof v==='boolean'?'':Array.isArray(v)?v.map(text).join(''):typeof v==='object'?text(v.props?.children):String(v);
const current=v=>nodes(v).filter(n=>n.type==='li'&&n.props.className?.includes('og-progress-stage')).findIndex(n=>n.props.className.includes(' running'))+1;
const gauge=v=>nodes(v).find(n=>n.props.role==='progressbar').props['aria-valuenow'];
function fixture(done=false){const keys=['ingestion','inventory','scan','normalize','rules','report'];return{id:'TEST_ONLY_COMPONENT',mode:'api',input:'合成离线测试',status:done?'completed':'running',stageIndex:done?6:0,progress:done?100:40,stages:['input','inventory','scan','normalize','rules','AI未启用','report'],resources:[],evidence:[],diagnostics:[],progressEvents:{events:keys.slice(0,done?6:3).flatMap((phase,i)=>[{sequence:2*i+1,phase,state:'start',percent:i*15,observed_at:'2026-10-15T00:00:00Z'},...(done||i<2?[{sequence:2*i+2,phase,state:'end',percent:(i+1)*15,observed_at:'2026-10-15T00:00:00Z'}]:[])])}};}
test('real component presents first and second phases even when the first response is already scanning resources',()=>{
 const h=harness(),s=fixture();let v=h.render(s);assert.equal(current(v),1);assert.equal(current(h.tick(799,s)),1);assert.equal(current(h.tick(1,s)),2);assert.equal(current(h.tick(800,s)),3);h.unmount();assert.equal(h.timers,0);
});
test('real component must visibly present phases four, five and six after a terminal polling batch',()=>{
 const h=harness(),s=fixture();h.render(s);h.tick(1600,s);const done=fixture(true);let v=h.render(done);assert.equal(current(v),3);assert.match(text(v),/扫描已完成，正在展示处理过程/);
 const seen=[3];for(let i=0;i<3;i++){v=h.tick(800,done);seen.push(current(v));assert.ok(gauge(v)<100);}
 assert.deepEqual(seen,[3,4,5,6]);v=h.tick(3800,done);assert.equal(current(v),0);assert.equal(gauge(v),100);h.unmount();assert.equal(h.timers,0);
});
test('opening a historical complete scan shows the saved result without replay',()=>{const h=harness(),v=h.render(fixture(true));assert.equal(current(v),0);assert.equal(gauge(v),100);assert.doesNotMatch(text(v),/正在展示处理过程/);h.unmount();assert.equal(h.timers,0);});
test('disconnect pauses the real queue and reconnect does not skip unseen phases',()=>{const h=harness(),s=fixture();h.render(s);let v=h.tick(400,s,'offline');assert.equal(current(v),1);v=h.tick(3000,s,'offline');assert.equal(current(v),1);v=h.render(s);assert.equal(current(v),2);h.unmount();assert.equal(h.timers,0);});
test('failure cancels presentation immediately and preserves actual stopped state',()=>{const h=harness(),s=fixture();h.render(s);const failed={...s,status:'failed'};const v=h.render(failed);assert.equal(current(v),0);assert.match(text(v),/扫描失败/);assert.doesNotMatch(text(v),/正在展示处理过程/);h.unmount();assert.equal(h.timers,0);});
test('reduced motion reads actual stages immediately without a presentation timer',()=>{const h=harness(true),s=fixture(),v=h.render(s);assert.equal(current(v),3);assert.equal(gauge(v),40);h.unmount();assert.equal(h.timers,0);});
test('changing scan identity does not show another scan’s completed phases',()=>{const h=harness(),s=fixture();h.render(s);h.tick(1600,s);const other={...fixture(),id:'OTHER_TASK'};assert.equal(current(h.render(other)),1);h.unmount();assert.equal(h.timers,0);});
