import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { runtime } from './runtime.mjs';
const real=JSON.parse(fs.readFileSync(new URL('./saved-hints.fixture.json',import.meta.url)));
const plain=x=>JSON.parse(JSON.stringify(x));
const usage={...real.usage};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const gap=real.gaps[0];
const projection=()=>runtime().load('services/usageExperience.ts');
const jsx=(type,props)=>({type,props});
function nodes(n){if(!n||typeof n!=='object')return [];if(Array.isArray(n))return n.flatMap(nodes);return [n,...nodes(n.props?.children)];}
function text(n){if(n==null||typeof n==='boolean')return '';if(Array.isArray(n))return n.map(text).join('');if(typeof n!=='object')return String(n);return text(n.props?.children);}
const record=(id,version,u=usage)=>({id,version,scan_id:'s',usage:{...u},generated_at:'2026-10-05T04:01:30Z',ai_status:'not_requested',ai_summary:null,summary:'待确认',dimensions:[],coverage_issues:[],resource_ids:[],finding_ids:[],evidence_ids:[],obligations:[],facts_hash:'a'.repeat(64)});
export function harness(readOnly=false){
 const r=runtime({VITE_OPENGUARD_READ_ONLY_PREVIEW:readOnly?'true':'false'}),state=[],refs=[],effects=[],timers=new Map(),calls=[],selections=[];let si=0,ri=0,ei=0,dirty=true,tree,sequence=0,queued=[],items=[record('v2',2),record('v1',1,{preset:'unknown'})],post=deferred(),pendingJob=null,readFailure=null;
 const props={scan:{id:'s',mode:'api',evidence:[]},query:new URLSearchParams('assessment_id=v2'),selectVersion(id){selections.push(id);props.query=new URLSearchParams('assessment_id='+id);dirty=true;}};
 const hooks={useState(initial){const i=si++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return [state[i],v=>{const next=typeof v==='function'?v(state[i]):v;if(!Object.is(next,state[i])){state[i]=next;dirty=true;}}];},useRef(initial){const i=ri++;return refs[i]??(refs[i]={current:initial});},useEffect(fn,deps){const i=ei++,old=effects[i];if(!old||!deps||deps.some((v,j)=>!Object.is(v,old.deps?.[j]))){effects[i]={deps,cleanup:old?.cleanup};queued.push(()=>{old?.cleanup?.();effects[i].cleanup=fn();});}}};
 r.setFetch(async(url,init={})=>{calls.push({url,method:init.method??'GET',body:init.body&&JSON.parse(init.body)});if(init.method==='POST'){const value=await post.promise;return value instanceof Response?value:Response.json(value);}if(readFailure&&(readFailure==='all'||url.endsWith('/'+readFailure)))return new Response('unavailable',{status:503});if(url.includes('/jobs/'))return Response.json(pendingJob);if(url.endsWith('/chat'))return Response.json({items:[],generation:0,limits:{max_message_chars:2000,max_turns:50}});return Response.json({items,usage:null,pending_job:null});});
 const m={exports:{}};const output=ts.transpileModule(fs.readFileSync(new URL('../src/pages/Assessment.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(output,{...r.shared,module:m,exports:m.exports,setTimeout:fn=>{timers.set(++sequence,fn);return sequence;},clearTimeout:id=>timers.delete(id),document:{getElementById:()=>null},require:name=>name==='react'?hooks:name==='react/jsx-runtime'?{jsx,jsxs:jsx,Fragment:'fragment'}:name.includes('/components/')?{Header:'Header',Panel:'Panel',UsageForm:'UsageForm',DecisionBrief:'DecisionBrief'}:r.load(name.replace(/^\.\.\//,'')+'.ts')});
 async function settle(){for(let i=0;i<30;i++){if(dirty){dirty=false;si=ri=ei=0;queued=[];tree=m.exports.Assessment(props);for(const f of queued)f();}await new Promise(done=>setImmediate(done));if(!dirty)return;}throw Error('scheduler did not settle');}
 const button=name=>nodes(tree).find(n=>n.type==='button'&&text(n)===name);
 const form=()=>nodes(tree).find(n=>n.type==='UsageForm');
 return {settle,calls,selections,form,button,reply(value){post.resolve(value);},failRead(kind){readFailure=kind;},reload(){button('重新读取评估').props.onClick();},get text(){return text(tree);},get tree(){return tree;},edit(u){form().props.onChange(u);},choose(id){props.query=new URLSearchParams('assessment_id='+id);dirty=true;},scan(id){props.scan={...props.scan,id};dirty=true;},async submit(){button('生成评估／更新用途').props.onClick();await settle();const promise=button('确认并生成').props.onClick();await settle();return {promise};},resolve(status='succeeded',id='v3',u=usage){if(status==='succeeded')items=[record(id,3,u),...items];const response={request_id:calls.findLast(c=>c.method==='POST').body.request_id,status,assessment_id:id};if(status==='pending')pendingJob=response;post.resolve(response);},reject(error=new TypeError('offline')){post.reject(error);},async tick(){for(const [id,fn] of [...timers]){timers.delete(id);await fn();}await settle();},setPending(status='succeeded'){pendingJob={request_id:calls.findLast(c=>c.method==='POST').body.request_id,status,assessment_id:'v3'};items=[record('v3',3),...items];},dispose(){effects.forEach(e=>e.cleanup?.());}};
}

export {nodes,text,usage,record};
