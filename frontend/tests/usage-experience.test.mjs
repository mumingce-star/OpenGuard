import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
const binding = { scan_id:'s', assessment_id:'a', assessment_version:1, facts_hash:'a'.repeat(64) };
const job = (patch={}) => ({job_id:'j',request_key:'key',version:2,status:'running',snapshot_id:null,binding,...patch});
const brief = (patch={}) => ({permission_state:'unknown',local_results:[],resolution_observations:[],gaps:[],...patch});

test('new usage is a draft until a new fixed assessment is saved; nullable answers stay unknown',()=>{
 const p=runtime().load('services/usageExperience.ts');
 const fixed={preset:'personal',commercial:null,declared_at:'old'};
 assert.equal(p.sameUsage(fixed,{preset:'personal',declared_at:'new'}),true);
 assert.equal(p.sameUsage(fixed,{preset:'internal',commercial:null}),false);
 assert.equal(p.sameUsage(fixed,{...fixed,commercial:false}),false);
 assert.equal(p.usageDescription({preset:'service',network_service:null}).includes('对外在线服务'),true);
 assert.equal(p.usageDescription({preset:'service',network_service:null}).includes('对外提供在线服务：是'),false);
});
test('refresh uses the selected saved assessment usage, not stale scan-level usage arriving after chat',()=>{
 const p=runtime().load('services/usageExperience.ts');
 const old={id:'old',usage:{preset:'unknown',commercial:null}};
 const current={id:'current',usage:{preset:'closed_source',commercial:true,distributed:true}};
 assert.equal(p.initialUsage([current,old],'current',old.usage),current.usage);
 assert.equal(p.initialUsage([current,old],'old',current.usage),old.usage);
 assert.equal(p.initialUsage([current,old],'missing',old.usage),null);
 assert.equal(p.initialUsage([current,old],null,old.usage),current.usage);
 assert.equal(p.initialUsage([],null,old.usage),old.usage);
});
test('unknown and local partial results never become overall permission or a compliance percentage',()=>{
 const p=runtime().load('services/usageExperience.ts');
 assert.match(p.conclusionText(brief()),/不能确认/);
 assert.match(p.conclusionText(brief({permission_state:'partial'})),/部分组件/);
 const count=p.localResultText(brief({local_results:[{supported_permission:true},...Array.from({length:44},()=>({supported_permission:false}))]}));
 assert.match(count,/1.*45/);assert.match(count,/不是.*比例/);assert.doesNotMatch(count,/%/);
});
test('material progress reports what was found and keeps applicability and formal assessment pending',()=>{
 const p=runtime().load('services/usageExperience.ts');
 const result=p.materialProgress(brief({resolution_observations:[{atomic_facts:{version_located:true,document_acquired:true}}],gaps:[{code:'APPLICABILITY_UNVERIFIED',owner:'reviewer'}]}));
 assert.equal(result.documents,1);assert.equal(result.versions,1);assert.equal(result.remaining,1);
 assert.match(result.formal,/未改变/);assert.match(result.next,/审核/);
 assert.match(p.materialProgress(brief()).summary,/未附加/);
});
test('refresh restores active jobs while the displayed snapshot remains the exact initial result',()=>{
 const p=runtime().load('services/usageExperience.ts');
 const initial=job({job_id:'initial',request_key:'initial-a',status:'completed',snapshot_id:'s0'});
 const latest=job({job_id:'latest',status:'completed',snapshot_id:'s1'});
 assert.equal(p.initialSnapshot([latest,initial],'a'),'s0');
 assert.equal(p.initialSnapshot([latest],'a'),undefined);
 assert.equal(p.activeResolution([latest,initial,job()]).job_id,'j');
 for(const status of ['failed','cancelled','interrupted']) {
  assert.equal(p.resolutionStatus(job({status})).active,false);
  assert.equal(p.resolutionStatus(job({status})).completed,false);
  assert.match(p.resolutionStatus(job({status})).text,/保留/);
 }
 assert.match(p.resolutionStatus(job({status:'completed',snapshot_id:'s1'})).text,/不代表授权/);
});
test('a restored completed task is not presented as the currently displayed snapshot',()=>{
 const p=runtime().load('services/usageExperience.ts');
 const completed=job({status:'completed',snapshot_id:'saved'});
 assert.equal(p.needsResultSelection(completed,'initial'),true);
 assert.equal(p.needsResultSelection(completed,'saved'),false);
 assert.equal(p.needsResultSelection(job({status:'cancelled'}),'initial'),false);
 assert.equal(p.needsResultSelection(null,'initial'),false);
});
test('scan completion is labelled separately from a permission judgement',()=>{
 const d=runtime().load('types/domain.ts');assert.equal(d.statusLabels.completed,'扫描完成');
 assert.equal(d.handlingLabels.resolved,'已处理');
});
test('cancel reuses the existing CAS contract and checks task identity',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts');const calls=[];
 r.setFetch(async(url,init)=>{calls.push({url,body:JSON.parse(init.body)});return Response.json(job({status:'cancelled',version:3}));});
 const result=await s.cancelResolution('s','a',1,'j',2);assert.equal(result.status,'cancelled');
 assert.match(calls[0].url,/\/jobs\/j\/cancel$/);assert.deepEqual(calls[0].body,{expected_version:2});
 for(const v of [0,-1,1.5,NaN]) await assert.rejects(()=>s.cancelResolution('s','a',1,'j',v));
 assert.equal(calls.length,1);
 r.setFetch(async()=>Response.json(job({job_id:'other',status:'cancelled'})));
 await assert.rejects(()=>s.cancelResolution('s','a',1,'j',2));
});
test('cancel conflict is reported without silently retrying or changing CAS version',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts');let calls=0;
 r.setFetch(async()=>{calls++;return Response.json({error:{message:'Job changed'}},{status:409});});
 await assert.rejects(()=>s.cancelResolution('s','a',1,'j',2));assert.equal(calls,1);
});
test('cancel response must confirm the same task at the next CAS version and cancelled state',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts');
 for(const patch of [{status:'running',version:3},{status:'completed',version:3,snapshot_id:'saved'},{status:'cancelled',version:2}]) {
  r.setFetch(async()=>Response.json(job(patch)));
  await assert.rejects(()=>s.cancelResolution('s','a',1,'j',2));
 }
});

// Reduced fields from the saved http-positive-after-local.json and
// nonempty-initial-brief.json. IDs/paths are synthetic; no new business records.
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
 const r=runtime(),calls=[];
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

test('T01 reviewer identity action uses same-resource saved material facts, not just the gap code',()=>{
 const p=runtime().load('services/usageExperience.ts'),b=saved();const g=b.gaps[0];
 assert.match(p.presentGap(g,b).action,/版本材料已定位/);
 assert.match(p.presentGap(g,b).action,/审核|接纳/);assert.doesNotMatch(p.presentGap(g,b).action,/先查找/);
 assert.match(textOf(componentView(b).render()),/已找到.*版本材料与许可正文/);
});
test('T02 version-only and document-only evidence never invent the other atomic fact',()=>{
 const p=runtime().load('services/usageExperience.ts');
 const version=saved({resolution_observations:[observed('component-a',{document_acquired:false,content_matched:false})]});
 assert.match(p.presentGap(version.gaps[0],version).action,/版本材料已定位/);
 assert.doesNotMatch(textOf(componentView(version).render()),/已找到.*版本材料与许可正文/);
 const document=saved({resolution_observations:[observed('component-a',{version_located:false,content_matched:false})]});
 assert.match(p.presentGap(document.gaps[0],document).action,/版本.*仍|版本.*待/);
 assert.doesNotMatch(p.presentGap(document.gaps[0],document).action,/版本材料已定位/);
 assert.doesNotMatch(textOf(componentView(document).render()),/已取得正文并核对/);
});
test('T03 unrelated and partially matched resource IDs cannot complete a multi-resource gap',()=>{
 const p=runtime().load('services/usageExperience.ts');const g=versionReview({resource_ids:['component-a','component-b']});
 assert.match(p.presentGap(g,saved()).action,/部分/);
 const unmatched=p.presentGap(versionReview({resource_ids:['component-b']}),saved()).action;
 assert.doesNotMatch(unmatched,/已定位|已找到|无需重复/);
 assert.match(unmatched,/待|核对/);
});
test('T04 a genuine supported system material gap keeps the existing explicit POST handler in mixed states',async()=>{
 const b=saved({gaps:[versionReview(),versionReview({owner:'system',action:'RESOLVE_LOCAL',safe_automation:true,resource_ids:['component-b']})]});
 const view=componentView(b),tree=view.render(),find=button(tree,'继续检查本地材料');assert.ok(find);
 assert.match(textOf(tree),/已.*材料/);assert.match(textOf(tree),/现有检查范围/);
 find.props.onClick();await flush();
 assert.equal(view.calls.filter(c=>c.method==='POST').length,1);
 assert.equal(JSON.parse(view.calls.find(c=>c.method==='POST').body).assessment_id,'a');
});
test('T05 identity mismatch, conflicts, and unsupported rules keep their blockers alongside acquired material',()=>{
 const p=runtime().load('services/usageExperience.ts');
 for(const code of ['IDENTITY_MISMATCH','EVIDENCE_CONFLICT','RULE_NOT_COVERED']) {
  const g={...versionReview(),code,title:undefined,action:code==='RULE_NOT_COVERED'?'REVIEW_RULE_COVERAGE':'INSPECT_RESOLUTION'};
  const shown=p.presentGap(g,saved({gaps:[g]}));
  assert.doesNotMatch(shown.action,/已解决|授权已核验|无需审核/);
  assert.match(textOf(componentView(saved({gaps:[g]})).render()),/不一致|冲突|未覆盖/);
 }
 const system=versionReview({owner:'system',action:'RESOLVE_LOCAL',safe_automation:true});
 for(const code of ['PROVIDER_NOT_SUPPORTED','LOCAL_SOURCE_NOT_RETAINED','IDENTITY_MISMATCH','EVIDENCE_CONFLICT']) {
  const tree=componentView(saved({resolution_observations:[],gaps:[system,{code,owner:'system',action:'INSPECT_RESOLUTION',resource_ids:['component-a']}]})).render();
  assert.ok(button(tree,'查看材料与待审核事项'));assert.ok(!button(tree,'继续检查本地材料'));
 }
});
test('T06 actual view-materials button only opens and focuses loaded content, without any network or identity change',async()=>{
 const b=saved(),before=JSON.stringify(b),view=componentView(b),tree=view.render();
 const show=button(tree,'查看材料与待审核事项');assert.ok(show);
 const region=nodesOf(tree).find(n=>n.props?.['aria-label']==='材料与待审核事项');assert.ok(region?.props.ref);
 let scrolls=0,focus=0;const details=[{open:false}];
 region.props.ref.current={querySelectorAll:()=>details,scrollIntoView(){scrolls++;},focus(){focus++;}};
 show.props.onClick();await flush();assert.equal(scrolls,1);assert.equal(focus,1);assert.equal(details[0].open,false);
 assert.equal(view.calls.length,0);assert.equal(JSON.stringify(b),before);assert.equal(view.states[3],false);
});
test('T07 active and busy states retain progress/cancel controls and block duplicate material writes',()=>{
 for(const options of [{busy:true},{jobs:[job()],currentJob:job()}]) {
  const view=componentView(saved(),options),tree=view.render();
  const searches=nodesOf(tree).filter(n=>n.type==='button'&&/查找|检查本地材料/.test(textOf(n))&&!/取消/.test(textOf(n)));
  assert.ok(searches.every(n=>n.props.disabled));assert.equal(view.calls.length,0);
  if(options.jobs)assert.ok(button(tree,'取消本次查找'));
 }
});
test('T08 an unselected saved snapshot needs the existing explicit GET and is never borrowed for current copy',async()=>{
 const current=job({status:'completed',snapshot_id:'saved-v2'});
 const old=saved({resolution_snapshot_id:'initial',resolution_observations:[],gaps:[versionReview({owner:'system',action:'RESOLVE_LOCAL',safe_automation:true})]});
 const view=componentView(old,{currentJob:current,jobs:[current]}),tree=view.render();
 assert.doesNotMatch(textOf(tree),/已找到.*版本材料与许可正文/);assert.equal(view.states[0].resolution_snapshot_id,'initial');
 const select=button(tree,'查看已保存的查找结果');assert.ok(select);
 select.props.onClick();await flush();assert.equal(view.calls.length,1);assert.equal(view.calls[0].method,'GET');
 assert.match(view.calls[0].url,/snapshot_id=saved-v2/);assert.equal(view.states[0].resolution_snapshot_id,'saved-v2');
});
test('T09 a dirty usage draft leaves fixed usage/snapshot in place and keeps all material writes disabled',()=>{
 const b=saved(),view=componentView(b,{draftUsage:{preset:'internal',commercial:null}}),tree=view.render();
 assert.match(textOf(tree),/新选择.*尚未生成新评估.*下面仍是原用途/);
 const searches=nodesOf(tree).filter(n=>n.type==='button'&&/查找|检查本地材料/.test(textOf(n)));
 assert.ok(searches.length>0);assert.ok(searches.every(n=>n.props.disabled));assert.equal(view.calls.length,0);
 assert.equal(b.resolution_snapshot_id,'saved-v2');assert.equal(fixedAssessment.usage.preset,'closed_source');
});
test('T10 unknown fixed usage makes select-usage primary without requiring answers or losing material access',()=>{
 const view=componentView(saved(),{assessment:{...fixedAssessment,usage:{preset:'unknown',commercial:null}}}),tree=view.render();
 const main=nodesOf(tree).find(n=>n.type==='button'&&n.props.className==='og-primary');assert.equal(textOf(main),'选择用途');
 main.props.onClick();assert.equal(view.edits,1);assert.equal(view.calls.length,0);
 assert.ok(nodesOf(tree).some(n=>n.type==='button'&&/查找|检查本地材料/.test(textOf(n))&&!n.props.disabled));
});
test('T11 empty and all-false local records do not imply existing permission support even with found material',()=>{
 for(const rows of [[],saved().local_results]) {
  const tree=componentView(saved({local_results:rows})).render();
  const boundary=nodesOf(tree).find(n=>n.props?.className==='og-resolution-boundary');
  assert.doesNotMatch(textOf(boundary),/局部组件有判断|已有.*局部许可支持/);
  assert.match(textOf(boundary),/仍.*待核对/);
 }
});
test('T12 nonzero and all-supported records keep exact row counts, conditions, and overall permission state',()=>{
 for(const rows of [[{...saved().local_results[0],supported_permission:true},saved().local_results[0]],
  [{...saved().local_results[0],supported_permission:true}]]) {
  const b=saved({local_results:rows,dimensions:[{title:'条件',conditions:['保留声明'],restrictions:[]}]}),tree=componentView(b).render();
  const boundary=nodesOf(tree).find(n=>n.props?.className==='og-resolution-boundary');
  assert.match(textOf(boundary),/1.*条资源记录.*局部许可支持/);assert.match(textOf(boundary),/条件.*不代表项目整体/);
  assert.match(textOf(tree),/保留声明/);assert.equal(b.permission_state,'unknown');assert.equal(b.formal,false);
 }
});
test('T13 legacy/unknown codes, absent action or IDs remain conservative and preserve raw facts',()=>{
 const p=runtime().load('services/usageExperience.ts');
 for(const g of [versionReview({code:'FUTURE_CODE'}),versionReview({action:undefined}),versionReview({resource_ids:undefined}),versionReview({resource_ids:[]})]) {
  const before=JSON.stringify(g),shown=p.presentGap(g,saved());
  assert.doesNotMatch(shown.action,/无需重复|已完成|授权已核验/);assert.equal(JSON.stringify(g),before);
  assert.doesNotMatch(textOf(componentView(saved({gaps:[g]})).render()),/版本范围不能证明/);
  assert.equal(JSON.stringify(g),before);
 }
});
test('T14 obligation labels join only exact IDs in the same Brief, with multiple/unknown/missing-version cases',()=>{
 const base={id:'obligation',requirement:'原文',fulfillment:'pending',resource_ids:['component-a']};
 const rows=[{resource_id:'component-a',name:'pydantic',version:'2.13.4',supported_permission:true,conditions:[],next_steps:[]},
 {resource_id:'component-b',name:'other',version:null,supported_permission:false,conditions:[],next_steps:[]}];
 for(const [ids,match] of [[['component-a'],/关联对象：pydantic 2\.13\.4/],[['component-a','component-b'],/pydantic 2\.13\.4.*other.*版本未确认/],
  [['missing'],/关联对象尚未定位/]]) {
  const tree=componentView(saved({local_results:rows,obligations:[{...base,resource_ids:ids}]})).render();
  assert.match(textOf(tree),match);if(ids[0]==='missing')assert.doesNotMatch(textOf(tree),/关联对象：pydantic/);
 }
});
test('T15 condition/restriction hints and obligation originals are counted separately without altering fulfillment',()=>{
 const b=saved({dimensions:[{title:'条件',conditions:['保留声明'],restrictions:['保留声明']}],
 obligations:[{id:'o',requirement:'Preserve notice.',trigger:'Distribution',fulfillment:'pending',resource_ids:['component-a']}]});
 const before=JSON.stringify(b),tree=componentView(b).render();
 assert.match(textOf(tree),/条件\/限制提示 1 条 · 义务原文 1 条/);
 assert.match(textOf(tree),/Preserve notice\./);assert.match(textOf(tree),/Distribution/);assert.match(textOf(tree),/待履行／待确认/);
 assert.equal(JSON.stringify(b),before);
});
test('T16 compact without edit callback retains exact scan/assessment links and introduces no write action',()=>{
 const view=componentView(saved(),{compact:true,onEditUsage:undefined,assessment:{...fixedAssessment,id:'a exact',scan_id:'s exact',usage:{preset:'unknown'}}});
 const tree=view.render(),links=nodesOf(tree).filter(n=>n.type==='a'&&/用途/.test(textOf(n)));
 assert.ok(links.length);for(const link of links){assert.match(link.props.href,/scans\/s%20exact\/assessment\?mode=api&assessment_id=a%20exact/);}
 assert.ok(!nodesOf(tree).some(n=>n.type==='button'&&/重新查找|检查本地材料/.test(textOf(n))));assert.equal(view.calls.length,0);
});

// Desktop refinement: saved-response fields remain unchanged; presentation is not authority.
test('D01 ordinary result rendering excludes internal diagnostics and identifiers while preserving source',()=>{
 const b=saved({gaps:[versionReview({title:'PRIVATE_DIAGNOSTIC',raw:[{text:'RAW_INTERNAL /private/root'}]})]});
 const before=JSON.stringify(b),tree=componentView(b).render();
 const visible=nodesOf(tree).map(n=>[textOf(n),n.props?.title,n.props?.['aria-label']].join(' ')).join(' ');
 for(const secret of ['PRIVATE_DIAGNOSTIC','RAW_INTERNAL','VERSION_UNRESOLVED','REVIEW_IDENTITY_FACT','material-component-a','vendor/acme','b'.repeat(64),'saved-v2'])assert.ok(!visible.includes(secret),secret);
 assert.equal(JSON.stringify(b),before);
});
test('D02 empty supplemental observations do not deny existing formal evidence',()=>{
 const p=runtime().load('services/usageExperience.ts');
 assert.match(p.materialProgress(saved({resolution_observations:[]})).summary,/未附加/);
 assert.doesNotMatch(p.materialProgress(saved({resolution_observations:[]})).summary,/没有.*材料|未找到/);
});
test('D03 material original is opt-in, bound to loaded observation, plain text and read-only',()=>{
 const original='<script>doNotExecute()</script> MIT original';
 const b=saved({resolution_observations:[{...observed(),text:original}]});
 const v=componentView(b);assert.ok(!textOf(v.render()).includes(original));
 const read=button(v.render(),'查看许可原文');assert.ok(read);read.props.onClick();
 const tree=v.render();assert.ok(textOf(tree).includes(original));
 assert.ok(!nodesOf(tree).some(n=>n.props?.dangerouslySetInnerHTML));assert.equal(v.calls.length,0);
 assert.equal(b.resolution_snapshot_id,'saved-v2');
});
test('D04 missing and malformed original text has a truthful no-fetch fallback',()=>{
 for(const text of [undefined,null,'',{},42]) {
  const v=componentView(saved({resolution_observations:[{...observed(),text}]}));
  const read=button(v.render(),'查看许可原文');assert.ok(read);read.props.onClick();
  assert.match(textOf(v.render()),/未保存可显示的许可原文/);assert.equal(v.calls.length,0);
 }
});
test('D05 every necessary condition and obligation remains visible before expanding original text',()=>{
 const b=saved({dimensions:[{conditions:['条件一','条件二','条件三'],restrictions:['限制四']}],
 obligations:Array.from({length:4},(_,i)=>({id:'obligation-private-'+i,resource_ids:['component-a'],requirement:'必须履行'+i,trigger:'交付时'+i,fulfillment:'pending'}))});
 const tree=componentView(b).render(),text=textOf(tree);
 for(const value of ['条件三','限制四','必须履行3','交付时3'])assert.ok(text.includes(value));
 assert.ok(!text.includes('obligation-private-'));assert.ok(!nodesOf(tree).some(n=>n.type==='details'&&textOf(n).includes('必须履行3')));
});

test('D06 business-only expansion retains every source gap and never exposes raw diagnostic text',()=>{
 const gaps=Array.from({length:6},(_,i)=>versionReview({code:'FUTURE_'+i,raw:[{text:'RAW_'+i}]}));
 const b=saved({gaps}),before=JSON.stringify(b),v=componentView(b);
 button(v.render(),'查看全部待确认事项').props.onClick();
 assert.equal((textOf(v.render()).match(/仍有事项需要核对/g)||[]).length,6);
 assert.doesNotMatch(textOf(v.render()),/RAW_|FUTURE_/);assert.equal(JSON.stringify(b),before);
});
test('D07 selected snapshot switches close an old original without fetching a replacement body',()=>{
 const v=componentView(saved({resolution_observations:[{...observed(),text:'old body'}]}));
 button(v.render(),'查看许可原文').props.onClick();assert.match(textOf(v.render()),/old body/);
 v.states[0]=saved({resolution_snapshot_id:'another',resolution_observations:[{...observed(),text:'new body'}]});
 assert.doesNotMatch(textOf(v.render()),/old body|new body/);assert.equal(v.calls.length,0);
});
test('D08 view-material focus is repeatable without opening hidden content or changing fixed identity',()=>{
 const b=saved(),v=componentView(b);let focus=0,scroll=0;
 const tree=v.render(),region=nodesOf(tree).find(n=>n.props?.['aria-label']==='材料与待审核事项');
 region.props.ref.current={focus(o){assert.equal(o.preventScroll,true);focus++;},scrollIntoView(o){assert.equal(o.behavior,'instant');scroll++;}};
 button(tree,'查看材料与待审核事项').props.onClick();button(tree,'查看材料与待审核事项').props.onClick();
 assert.equal(focus,2);assert.equal(scroll,2);assert.equal(v.calls.length,0);assert.equal(v.states[0],b);
});
test('D09 unknown errors do not expose backend diagnostics in result alert',async()=>{
 const v=componentView(saved(),{currentJob:job({status:'failed'})});
 v.setFetch(async()=>Response.json({error:{message:'PRIVATE_STACK /root/secret'}},{status:500}));
 button(v.render(),'读取进度').props.onClick();await flush();
 assert.doesNotMatch(textOf(v.render()),/PRIVATE_STACK|secret/);assert.match(textOf(v.render()),/未完成|保留/);
});
test('D10 a new search retains the same idempotency key after an uncertain response',async()=>{
 const b=saved({resolution_observations:[],gaps:[versionReview({owner:'system',action:'RESOLVE_LOCAL',safe_automation:true})]});
 const v=componentView(b),keys=[];
 v.setFetch(async(url,init={})=>{if(init.method==='POST'){keys.push(JSON.parse(init.body).request_key);throw new TypeError('offline');}return Response.json({items:[]});});
 button(v.render(),'继续检查本地材料').props.onClick();await flush();await flush();
 button(v.render(),'继续检查本地材料').props.onClick();await flush();await flush();
 assert.equal(keys.length,2);assert.ok(keys[0]);assert.equal(keys[0],keys[1]);assert.equal(v.states[0],b);
});
test('D11 rapid duplicate search clicks reserve at most one request and preserve local source object',async()=>{
 const b=saved({resolution_observations:[],gaps:[versionReview({owner:'system',action:'RESOLVE_LOCAL',safe_automation:true})]});
 const v=componentView(b);let release,posts=0;
 v.setFetch(async(url,init={})=>{if(init.method==='POST'){posts++;return Response.json(job({status:'running'}));}return new Promise(r=>release=()=>r(Response.json({items:[]})));});
 const target=button(v.render(),'继续检查本地材料');target.props.onClick();target.props.onClick();assert.equal(posts,0);release();await flush();await flush();assert.equal(posts,1);assert.equal(v.states[0],b);
});
test('D12 late explicit snapshot response cannot replace the more recent user selection',async()=>{
 const jobs=[job({status:'completed',snapshot_id:'one'}),job({job_id:'two',status:'completed',snapshot_id:'two'})];
 const v=componentView(saved(),{jobs});const pending={};
 v.setFetch((url)=>new Promise(r=>pending[new URL(url,'http://local').searchParams.get('snapshot_id')]=r));
 const select=nodesOf(v.render()).find(n=>n.type==='select');select.props.onChange({target:{value:'one'}});select.props.onChange({target:{value:'two'}});
 pending.two(Response.json(saved({resolution_snapshot_id:'two'})));await flush();
 pending.one(Response.json(saved({resolution_snapshot_id:'one'})));await flush();assert.equal(v.states[0].resolution_snapshot_id,'two');
});
test('D13 result fallback preserves necessary obligations without dumping legacy unknown diagnostics',()=>{
 const a={...fixedAssessment,dimensions:[{conditions:['必要条件'],restrictions:[],unknowns:['PRIVATE_UNKNOWN']}],obligations:[{id:'internal-o',requirement:'保留声明',trigger:'分发时',fulfillment:'pending'}]};
 const v=componentView(null,{assessment:a});const text=textOf(v.render());
 assert.match(text,/必要条件/);assert.match(text,/保留声明/);assert.match(text,/分发时/);assert.doesNotMatch(text,/PRIVATE_UNKNOWN|internal-o/);
});

test('D14 unavailable model/case and material conflicts remain conservative without exposing identifiers',()=>{
 const v=componentView(saved({resolution_model:{status:'failed',reason:'PRIVATE_MODEL',calls:1,output:{conflict_clues:[{kind:'PRIVATE_KIND'}]}},resolution_cases:[{corpus_status:'PRIVATE_STATUS',matches:[],invalidations:[{case_id:'PRIVATE_CASE',reason:'PRIVATE_REASON'}]}]}));
 const text=textOf(v.render());assert.match(text,/模型超时|未通过核对/);assert.match(text,/没有可复用的审核参考/);assert.match(text,/冲突线索/);assert.match(text,/历史参考已失效/);assert.doesNotMatch(text,/PRIVATE_/);
});
test('D15 a long license stays opt-in and preserves all original bytes as plain text',()=>{
 const long='MIT <img src="https://invalid.example/never-fetch">\n'.repeat(2000),v=componentView(saved({resolution_observations:[{...observed(),text:long}]}));
 assert.ok(!textOf(v.render()).includes(long));button(v.render(),'查看许可原文').props.onClick();
 const pre=nodesOf(v.render()).find(n=>n.type==='pre');assert.equal(textOf(pre),long);assert.equal(v.calls.length,0);assert.ok(!nodesOf(pre).some(n=>n.type==='img'));
});
test('D16 duplicate resource IDs cannot choose one name or version for an obligation',()=>{
 const p=runtime().load('services/usageExperience.ts'),row=saved().local_results[0];
 const text=p.obligationResources({resource_ids:['component-a']},saved({local_results:[{...row,name:'A'},{...row,name:'B',version:'secret-version'}]}));
 assert.equal(text,'关联对象：关联对象尚未定位');assert.doesNotMatch(text,/secret-version/);
});
test('D17 cancel-unconfirmed handler retains uncertainty and does not turn task completion into cancellation',async()=>{
 const active=job(),v=componentView(saved(),{jobs:[active],currentJob:active});let posts=0;
 v.setFetch(async(url,init={})=>{if(init.method==='POST'){posts++;return Response.json({error:{message:'PRIVATE_CAS'}},{status:409});}return Response.json({items:[job({status:'completed',snapshot_id:'saved-v2'})]});});
 button(v.render(),'取消本次查找').props.onClick();await flush();await flush();
 assert.equal(posts,1);assert.match(textOf(v.render()),/取消未确认/);assert.doesNotMatch(textOf(v.render()),/PRIVATE_CAS/);assert.equal(v.states[5].status,'completed');
});
test('D18 existing optional observation text shapes never reject an otherwise valid saved Brief',async()=>{
 const r=runtime(),s=r.load('services/resolution.ts');
 for(const text of [undefined,null,'',{},42,'MIT text']) {
  r.setFetch(async()=>Response.json(saved({resolution_observations:[{...observed(),text}]})));
  const actual=await s.readBrief('s','a',1,'saved-v2');assert.equal(actual.resolution_snapshot_id,'saved-v2');
 }
});
