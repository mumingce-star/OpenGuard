import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import {runtime} from './runtime.mjs';
const rt=runtime(), motion=rt.load('pages/progressMotion.ts');
const fixture=()=>({id:'TEST_ONLY_MOTION',mode:'api',project:'离线测试',input:'合成状态',status:'running',stages:['安全读取','文件清单','依赖扫描','标准化','规则','AI（本次未启用）','报告'],stageIndex:3,progress:43,createdAt:'2026-10-14T04:00:00Z',startedAt:'2026-10-14T04:00:01Z',finishedAt:null,resources:[],risks:[],evidence:[],diagnostics:[],reportFormats:[]});
for(const [status,expected] of [['queued','still'],['running','running'],['completed','complete'],['partial','still'],['failed','still'],['cancelled','still']])test('motion follows actual '+status+' state',()=>assert.equal(motion.progressMotionState(status,false,false),expected));
for(const status of ['running','completed']){
 test('disconnection stops all task motion for '+status,()=>assert.equal(motion.progressMotionState(status,true,false),'still'));
 test('reduced motion stops all task motion for '+status,()=>assert.equal(motion.progressMotionState(status,false,true),'still'));
}
function harness({reduced=false}={}){
 const hooks=[],pending=[],timers=new Map();let cursor=0,next=1,reloads=0,results=0;
 const react={useState(initial){const i=cursor++;hooks[i]??={value:typeof initial==='function'?initial():initial};return[hooks[i].value,value=>hooks[i].value=typeof value==='function'?value(hooks[i].value):value];},useRef(initial){const i=cursor++;hooks[i]??={current:initial};return hooks[i];},useEffect(fn,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j]))){pending.push(()=>{old?.cleanup?.();hooks[i]={deps,cleanup:fn()};});}}};
 const module={exports:{}},source=fs.readFileSync(new URL('../src/pages/Progress.tsx',import.meta.url),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText,{module,exports:module.exports,Date,Math,console,clearTimeout:id=>timers.delete(id),clearInterval:id=>timers.delete(id),window:{setTimeout(fn){const id=next++;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),setInterval(fn){const id=next++;timers.set(id,fn);return id;},clearInterval:id=>timers.delete(id)},require:name=>{
  if(name==='react')return react;
  if(name==='react/jsx-runtime')return{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
  if(name.endsWith('.css'))return{};
  if(name==='../components/ui')return{StatusBadge:()=>null,useNotice:()=>()=>{}};
  if(name==='../hooks/useReducedMotion')return{useReducedMotion:()=>reduced};
  return rt.load(name.replace('../','').replace('./','pages/')+'.ts');
 }});
 return{render(scan,error=null){cursor=0;const v=module.exports.Progress({scan,reload:()=>reloads++,onResults:()=>results++,pollingError:error});while(pending.length)pending.shift()();return v;},flush(){for(const [id,fn]of[...timers]){timers.delete(id);fn();}},unmount(){for(const h of hooks)h?.cleanup?.();},get timers(){return timers.size;},get reloads(){return reloads;},get results(){return results;}};
}
const nodes=v=>!v||typeof v!=='object'?[]:Array.isArray(v)?v.flatMap(nodes):[v,...nodes(v.props?.children)];
const text=v=>v==null||typeof v==='boolean'?'':Array.isArray(v)?v.map(text).join(''):typeof v==='object'?text(v.props?.children):String(v);
for(const status of ['running','completed','partial','failed','cancelled'])test('actual component keeps six stages and exact progress during '+status,()=>{
 const h=harness(),s={...fixture(),status,progress:status==='completed'?100:43,stageIndex:status==='completed'?7:3};const before=JSON.stringify(s),v=h.render(s),all=nodes(v);assert.equal(v.props['data-motion'],motion.progressMotionState(status,false,false));assert.equal(all.filter(n=>n.type==='li'&&n.props.className?.includes('og-progress-stage')).length,6);assert.equal(all.find(n=>n.props?.role==='progressbar').props['data-confirmed-progress'],s.progress);assert.ok(all.find(n=>n.props?.role==='progressbar').props['aria-valuenow']<=s.progress);assert.equal(JSON.stringify(s),before);assert.ok(!text(v).includes('AI 辅助解释'));h.unmount();assert.equal(h.timers,0);
});
test('query feedback requests one reload and returns to still without changing completed data',()=>{
 const h=harness(),s={...fixture(),status:'completed',stageIndex:7,progress:100},before=JSON.stringify(s);let v=h.render(s);const button=nodes(v).find(n=>n.type==='button'&&text(n)==='重新查询任务');button.props.onClick();assert.equal(h.reloads,1);v=h.render(s);assert.match(nodes(v).find(n=>n.type==='button'&&text(n)==='重新查询任务').props.className,/is-querying/);h.flush();v=h.render(s);assert.doesNotMatch(nodes(v).find(n=>n.type==='button'&&text(n)==='重新查询任务').props.className,/is-querying/);assert.equal(h.reloads,1);assert.equal(JSON.stringify(s),before);h.unmount();
});
test('repeated manual queries do not leave multiple feedback timers',()=>{const h=harness(),s={...fixture(),status:'completed'};const v=h.render(s),button=nodes(v).find(n=>n.type==='button'&&text(n)==='重新查询任务');button.props.onClick();button.props.onClick();assert.equal(h.reloads,2);assert.equal(h.timers,1);h.unmount();assert.equal(h.timers,0);});
test('reduced motion still permits query and creates no feedback timer',()=>{const h=harness({reduced:true}),s={...fixture(),status:'completed'};const v=h.render(s);assert.equal(v.props['data-motion'],'still');nodes(v).find(n=>n.type==='button'&&text(n)==='重新查询任务').props.onClick();assert.equal(h.reloads,1);assert.equal(h.timers,0);h.unmount();});
test('disconnection freezes ongoing task animation and keeps error notice',()=>{const h=harness(),s=fixture(),v=h.render(s,'离线测试错误');assert.equal(v.props['data-motion'],'still');assert.match(text(v),/状态查询失败，进度已暂停更新/);assert.equal(nodes(v).find(n=>n.props?.role==='progressbar').props['data-confirmed-progress'],43);h.unmount();});
test('new live view starts at zero while restored completed task starts at 100',()=>{const a=harness(),live=a.render({...fixture(),progress:40});assert.equal(nodes(live).find(n=>n.props?.role==='progressbar').props['aria-valuenow'],0);assert.equal(nodes(live).find(n=>n.props?.role==='progressbar').props['data-confirmed-progress'],40);a.unmount();const b=harness(),old=b.render({...fixture(),status:'completed',progress:100,stageIndex:7});assert.equal(nodes(old).find(n=>n.props?.role==='progressbar').props['aria-valuenow'],100);b.unmount();});
test('same live task completes through every remaining integer rather than snapping',()=>{const h=harness(),s={...fixture(),progress:40};let v=h.render(s);for(let i=0;i<40;i++){h.flush();v=h.render(s);}assert.equal(nodes(v).find(n=>n.props?.role==='progressbar').props['aria-valuenow'],40);const done={...s,status:'completed',progress:100,stageIndex:7},values=[];v=h.render(done);values.push(nodes(v).find(n=>n.props?.role==='progressbar').props['aria-valuenow']);for(let i=0;i<60;i++){h.flush();v=h.render(done);values.push(nodes(v).find(n=>n.props?.role==='progressbar').props['aria-valuenow']);}assert.deepEqual(values,Array.from({length:61},(_,i)=>40+i));h.unmount();});
test('transport failure freezes the last rendered integer even when target changes',()=>{const h=harness(),s={...fixture(),progress:40};let v=h.render(s);for(let i=0;i<5;i++){h.flush();v=h.render(s);}v=h.render({...s,progress:80},'offline');assert.equal(nodes(v).find(n=>n.props?.role==='progressbar').props['aria-valuenow'],5);h.flush();v=h.render({...s,progress:80},'offline');assert.equal(nodes(v).find(n=>n.props?.role==='progressbar').props['aria-valuenow'],5);h.unmount();});
