import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {runtime} from './runtime.mjs';
import {scanHarness} from './new-scan-harness.mjs';

// SYNTHETIC_TEST_ONLY. Execute the real Progress function and progress model;
// only React hooks, clock and presentation timers are controlled here.
const phases=['ingestion','inventory','scan','normalize','rules','report'];
const fixture=(status='completed',id='TEST_ONLY_FAST_RECORDING')=>({id,mode:'api',input:'SYNTHETIC_TEST_ONLY',status,stageIndex:status==='completed'?7:0,progress:status==='completed'?100:15,stages:['input','inventory','scan','normalize','rules','AI未启用','report'],resources:[],evidence:[],diagnostics:[],progressEvents:{events:phases.flatMap((phase,i)=>[{sequence:2*i+1,phase,state:'start',percent:i*15,observed_at:'2026-10-22T00:00:00Z'},{sequence:2*i+2,phase,state:'end',percent:(i+1)*15,observed_at:'2026-10-22T00:00:00Z'}])}});
const nodes=v=>!v||typeof v!=='object'?[]:Array.isArray(v)?v.flatMap(nodes):[v,...nodes(v.props?.children)];
const text=v=>v==null||typeof v==='boolean'?'':Array.isArray(v)?v.map(text).join(''):typeof v==='object'?text(v.props?.children):String(v);
const stages=v=>nodes(v).filter(n=>n.type==='li'&&n.props.className?.includes('og-progress-stage'));
const current=v=>stages(v).findIndex(n=>n.props.className.includes(' running'))+1;
const gauge=v=>nodes(v).find(n=>n.props.role==='progressbar').props['aria-valuenow'];
function harness({reduced=false,rt=runtime()}={}){
 const hooks=[],pending=[],timers=new Map();let cursor=0,next=1,now=0,dirty=false;
 const clock=class extends Date{static now(){return now;}};
 const react={useState(initial){const i=cursor++;hooks[i]??={value:typeof initial==='function'?initial():initial};return[hooks[i].value,value=>{const v=typeof value==='function'?value(hooks[i].value):value;if(!Object.is(v,hooks[i].value)){hooks[i].value=v;dirty=true;}}];},useRef(initial){const i=cursor++;hooks[i]??={current:initial};return hooks[i];},useEffect(fn,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j]))){pending.push(()=>{old?.cleanup?.();hooks[i]={deps,cleanup:fn()};});}}};
 const timer=(fn,delay=0,interval=false)=>{const id=next++;timers.set(id,{fn,at:now+delay,interval:interval?delay:0});return id;};
 const module={exports:{}},source=fs.readFileSync(new URL('../src/pages/Progress.tsx',import.meta.url),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,Date:clock,Math,Set,console,clearTimeout:id=>timers.delete(id),clearInterval:id=>timers.delete(id),window:{setTimeout:(fn,d)=>timer(fn,d),clearTimeout:id=>timers.delete(id),setInterval:(fn,d)=>timer(fn,d,true),clearInterval:id=>timers.delete(id)},require:name=>{
  if(name==='react')return react;
  if(name==='react/jsx-runtime')return{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
  if(name.endsWith('.css'))return{};
  if(name==='../components/ui')return{StatusBadge:()=>null,useNotice:()=>()=>{}};
  if(name==='../hooks/useReducedMotion')return{useReducedMotion:()=>reduced};
  return rt.load(name.replace('../','').replace('./','pages/')+'.ts');
 }});
 function render(scan,error=null){for(let i=0;i<30;i++){dirty=false;cursor=0;const tree=module.exports.Progress({scan,reload:()=>{},onResults:()=>{},pollingError:error});while(pending.length)pending.shift()();if(!dirty)return tree;}throw Error('render did not settle');}
 return{rt,mark:scan=>rt.load('services/scanProgressEntry.ts').markNewScanForProgress(scan),render,tick(ms,scan,error=null){const end=now+ms;let tree=render(scan,error);for(let i=0;i<20000;i++){const due=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;const[id,t]=due;now=t.at;timers.delete(id);if(t.interval)timers.set(id,{...t,at:now+t.interval});t.fn();tree=render(scan,error);}now=end;return render(scan,error);},unmount(){for(const h of hooks)h?.cleanup?.();},get timers(){return timers.size;}};
}

test('newly submitted scan completed before the first GET still starts at zero and presents all six real stages',()=>{
 const h=harness(),s=fixture(),before=JSON.stringify(s);h.mark(s);
 let v=h.render(s);assert.equal(gauge(v),0);assert.equal(current(v),1);assert.match(text(v),/扫描已完成，正在展示处理过程/);
 const seen=[];
 for(let i=1;i<=6;i++){
  assert.equal(current(v),i);seen.push(current(v));assert.equal(current(h.tick(799,s)),i);v=h.tick(1,s);
 }
 assert.deepEqual(seen,[1,2,3,4,5,6]);assert.equal(current(v),0);
 v=h.tick(3000,s);assert.equal(gauge(v),100);assert.doesNotMatch(text(v),/正在展示处理过程/);
 assert.equal(JSON.stringify(s),before);h.unmount();assert.equal(h.timers,0);
});
test('fresh completion advances only by integers and never exceeds confirmed or displayed-stage bounds',()=>{
 const h=harness(),s=fixture();h.mark(s);let v=h.render(s),prior=gauge(v);
 for(let i=0;i<270;i++){v=h.tick(30,s);const n=gauge(v);assert.ok(n>=prior&&n<=prior+1);assert.ok(n<=100);if(current(v))assert.ok(n<100);prior=n;}
 assert.equal(prior,100);h.unmount();
});
test('consuming new-entry navigation does not replay the same completed scan when opened from history',()=>{
 const rt=runtime(),s=fixture(),fresh=harness({rt});fresh.mark(s);assert.equal(gauge(fresh.render(s)),0);fresh.unmount();
 const history=harness({rt}),v=history.render(s);assert.equal(gauge(v),100);assert.equal(current(v),0);history.unmount();
});
test('missing real event feed never creates six successful stage records',()=>{
 const h=harness(),s=fixture('queued');s.progressEvents.events=[];h.mark(s);let v=h.render(s);v=h.tick(10000,s);
 assert.equal(current(v),0);assert.ok(stages(v).every(n=>n.props.className.endsWith('waiting')));assert.equal(gauge(v),15);h.unmount();
});
test('disconnection freezes both integer progress and queued stage display',()=>{
 const h=harness(),s=fixture();h.mark(s);let v=h.render(s);v=h.tick(300,s);const p=gauge(v),phase=current(v);
 v=h.tick(10000,s,'TEST_ONLY_DISCONNECTED');assert.equal(gauge(v),p);assert.equal(current(v),phase);assert.match(text(v),/进度已暂停更新/);h.unmount();
});
for(const status of ['failed','partial','cancelled'])test('fresh '+status+' never replays terminal stages as successful work',()=>{
 const h=harness(),s=fixture(status);s.progressEvents.events=[{sequence:1,phase:'ingestion',state:'start',percent:0,observed_at:'2026-10-22T00:00:00Z'},{sequence:2,phase:'ingestion',state:status,percent:15,observed_at:'2026-10-22T00:00:00Z'}];h.mark(s);const v=h.render(s);
 assert.equal(current(v),0);assert.equal(stages(v)[0].props.className.includes(status),true);assert.ok(stages(v).slice(1).every(n=>n.props.className.endsWith('waiting')));h.unmount();
});
test('reduced motion presents actual completed state without playback timers',()=>{
 const h=harness({reduced:true}),s=fixture();h.mark(s);const v=h.render(s);assert.equal(gauge(v),100);assert.equal(current(v),0);h.unmount();assert.equal(h.timers,0);
});
test('new-entry identity is mode- and scan-specific',()=>{
 const r=runtime(),m=r.load('services/scanProgressEntry.ts'),s=fixture();m.markNewScanForProgress(s);
 assert.equal(m.isNewScanProgressEntry(s),true);assert.equal(m.isNewScanProgressEntry({...s,mode:'mock'}),false);assert.equal(m.isNewScanProgressEntry({...s,id:'OTHER'}),false);
 m.consumeNewScanProgressEntry(s);assert.equal(m.isNewScanProgressEntry(s),false);
});
test('successful NewScan registers the fresh progress entry before its created callback',async()=>{
 const h=scanHarness();await h.settle();await h.git();await h.submit();await h.submit();h.resolve();await h.settle();
 assert.deepEqual(h.created,[{id:'scan-confirmed',mode:'api'}]);h.dispose();
 const source=fs.readFileSync(new URL('../src/pages/NewScan.tsx',import.meta.url),'utf8');assert.match(source,/markNewScanForProgress\(created\);onCreated\(created\)/);
});
test('recording product configuration explicitly enables the real progress-events GET',()=>{
 const source=fs.readFileSync(new URL('../../../helpers/frontend-config.mjs',import.meta.url),'utf8');assert.match(source,/'import\.meta\.env\.VITE_PROGRESS_EVENTS': JSON\.stringify\('1'\)/);
});
