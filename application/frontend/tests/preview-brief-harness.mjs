import {runtime} from './runtime.mjs';
const binding = { scan_id:'s', assessment_id:'a', assessment_version:1, facts_hash:'a'.repeat(64) };
const job = (patch={}) => ({job_id:'j',request_key:'key',version:2,status:'running',snapshot_id:null,binding,...patch});
const brief = (patch={}) => ({permission_state:'unknown',local_results:[],resolution_observations:[],gaps:[],...patch});

import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const observed = (id='component-a', facts={}) => ({resource_id:id,name:'acme',version:'1.2.3',
 source_locator:'vendor/acme/LICENSE.txt',material_id:'material-'+id,content_hash:'b'.repeat(64),
 authorization_verified:false,review_status:'pending',atomic_facts:{version_located:true,document_acquired:true,
 content_matched:true,applicable_relation_checked:false,formal_policy_covered:false,...facts}});
const versionReview = (patch={}) => ({code:'VERSION_UNRESOLVED',owner:'reviewer',action:'REVIEW_IDENTITY_FACT',
 safe_automation:false,title:'系统已定位版本材料；正式输入尚待接纳',resource_ids:['component-a'],
 raw:[{text:'版本范围不能证明实际使用版本'}],...patch});
const saved = (patch={}) => ({formal:false,display_version:'decision-brief/1',...binding,title:'尚不能确认',notice:'材料不等于授权',
 permission_state:'unknown',local_results:[{resource_id:'component-a',name:'acme',version:null,supported_permission:false,
 conditions:[],next_steps:[],license_expression:null}],dimensions:[],obligations:[],
 gaps:[versionReview(),{code:'HUMAN_REVIEW_REQUIRED',owner:'reviewer',action:'REVIEW_RELATION',safe_automation:false,resource_ids:['component-a']},
 {code:'SCOPE_UNRESOLVED',owner:'user',action:'CONFIRM_SCOPE',resource_ids:['component-a']}],
 resolution_snapshot_id:'saved-v2',resolution_snapshot_hash:'c'.repeat(64),resolution_observations:[observed()],...patch});
const fixedAssessment={id:'a',scan_id:'s',version:1,facts_hash:binding.facts_hash,usage:{preset:'closed_source',commercial:true,distributed:true}};
function textOf(node) {
 if(node==null||typeof node==='boolean')return '';
 if(Array.isArray(node))return node.map(textOf).join('');
 if(typeof node!=='object')return String(node);
 if(typeof node.type==='function')return textOf(node.type(node.props));
 return textOf(node.props?.children);
}
function nodesOf(node) {
 if(node==null||typeof node!=='object')return [];
 if(Array.isArray(node))return node.flatMap(nodesOf);
 const value=typeof node.type==='function'?node.type(node.props):node;
 if(value==null)return [];
 return [value,...nodesOf(value.props?.children)];
}
// Execute the product's actual handlers with deterministic hook state and Fake
// transport. Effects are not run: this is not browser/lifecycle acceptance.
function componentView(value, options={}) {
 const r=runtime({VITE_OPENGUARD_READ_ONLY_PREVIEW:options.readOnly?'true':'false'}),calls=[];
 const states=[value,'',options.busy??false,false,options.jobs??[],options.currentJob??null,''];
 const refs=[];let stateIndex=0,refIndex=0,edits=0;
 const hooks={useEffect(){},useState(initial){const i=stateIndex++;if(i>=states.length)states[i]=initial;
  return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];},
  useRef(initial){const i=refIndex++;return refs[i]??(refs[i]={current:initial});}};
 const module={exports:{}};
 const source=fs.readFileSync(new URL('../src/components/DecisionBrief.tsx',import.meta.url),'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 vm.runInNewContext(output,{...r.shared,module,exports:module.exports,require:name=>name==='react'?hooks:
  name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'fragment'}:
  name.endsWith('.css')?{}:r.load(name.replace(/^\.\.\//,'')+'.ts')});
 r.setFetch(async(url,init={})=>{calls.push({url,method:init.method??'GET',body:init.body});
  if(url.includes('/decision-brief'))return Response.json(saved({resolution_snapshot_id:new URL(url,'http://local').searchParams.get('snapshot_id')??'initial'}));
  if(url.includes('/jobs'))return Response.json({items:[]});
  return Response.json(job({status:'completed',snapshot_id:'written'}));});
 const props={assessment:fixedAssessment,onEditUsage:()=>{edits++;},...options};
 function render(){stateIndex=0;refIndex=0;return module.exports.DecisionBrief(props);}
 return {render,calls,states,refs,get edits(){return edits;},setFetch:r.setFetch};
}
const button=(tree,name)=>nodesOf(tree).find(n=>n.type==='button'&&textOf(n)===name);
const flush=()=>new Promise(resolve=>setImmediate(resolve));


export {componentView,button,nodesOf,textOf,saved,versionReview,job,flush};
