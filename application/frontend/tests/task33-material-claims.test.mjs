// TASK33 authored contract tests; NOT_RUN. Fixture is TEST_ONLY, not captured API output.
import test from 'node:test';
import assert from 'node:assert/strict';
import {runtime} from './runtime.mjs';
import {createHash,webcrypto} from 'node:crypto';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const sha=text=>createHash('sha256').update(text,'utf8').digest('hex');
const h='a'.repeat(64), b='b'.repeat(64);
const subject={resource_id:'cmp_1',version:'7.0.0'};
const binding={scan_id:'scn_1',assessment_id:'asm_1',assessment_version:1,registry_revision:3,project_revision:'fixed',facts_hash:h,usage_hash:b,rule_version:'r1',assessment_sha256:h};
const result=()=>({result_id:'p2res_1',result_sha256:h,revision:2,previous_result_id:'p2res_old',binding,data_scope:'TEST_ONLY',material_ids:['p2mat_1'],answer_ids:[],recomputed_resource_ids:[subject.resource_id],reused_resource_ids:[],usage:{commercial:true,distributed:true,modified:false},resources:[{subject,resource_kind:'component',material_ids:['p2mat_1'],answer_ids:[],evidence_ids:['evd_1'],evidence_source_hashes:{evd_1:h}}]});
const evidence=[{evidence_id:'evd_1',source_sha256:h}];
function legacyV3Fixture(){
 const clauses=['license_identifier','copyright','permission','condition','warranty'].map((kind,i)=>({clause_id:'p4clause_'+i,material_id:'p2mat_1',material_sha256:h,kind,byte_start:i,byte_end:i+1,line_start:1,line_end:1,quote:'x',quote_sha256:sha('x')}));
 const materials=[{material_id:'p2mat_1',subject,source_sha256:h,byte_count:5,filename:'LICENSE',parse_state:'MATCHED_MIT',parse_reason:'COMPLETE_EXISTING_MIT_PROFILE',binding_state:'BOUND_TO_SAVED_RESULT',adoption_state:'CONDITIONAL_TEXT_BASIS',declared_spdx:'MIT',text_license:'MIT',license_version:null,version_scope:'RESOURCE_VERSION_NOT_LICENSE_VERSION',role:'unknown',role_state:'unknown',role_basis_evidence_ids:[],source_binding:'PINNED_RELEASE_MATCH',source_profile_sha256:b,evidence,clauses}];
 const claims=['commercial','distributed','modified'].map((usage,i)=>({claim_id:'p4claim_'+i,usage,subject,material_ids:['p2mat_1'],evidence,clause_ids:clauses.map(c=>c.clause_id),conditions:i===2?[]:['preserve notice'],counter_evidence:[],state:i===2?'NOT_COVERED':'SUPPORT',formal_effect:'none'}));
 return {schema_version:'openguard-material-claims/3',rule_version:'mit-bound-claim/3',view_id:'p4view_1',result_id:'p2res_1',result_sha256:h,revision:2,previous_result_id:'p2res_old',binding,data_scope:'TEST_ONLY',source_status:'CHECKED',source_profile_sha256:b,materials,declaration_observations:[{subject,expression:'MIT',normalized_ids:['MIT'],declaration_evidence_ids:['evd_1'],evidence,evidence_status:'COMPLETE'}],source_observations:[{source_observation_id:'p4source_1',subject,source_profile_sha256:b,archive_sha256:h,notice_status:'ABSENT_COMPLETE',reason:'COMPLETE_SUPPORTED_ARCHIVE_NO_NOTICE',member_count:4,enumeration_complete:true,notices:[]}],claims,advice:claims.map(c=>({usage:c.usage,subject,saved_value:c.usage!=='modified',state:c.state,reasons:['TEXT_BASIS'],claim_ids:[c.claim_id],conditions:c.conditions,limitations:['not a legal determination']})),formal_effect:'none',applicability_review:'NOT_SIGNED',model_calls:0};
}
function fixture(){return v4Fixture(legacyV3Fixture(),result());}
function anchor(){return {scan_id:binding.scan_id,project_revision:binding.project_revision,resources:[{
 resource_id:subject.resource_id,version:subject.version,resource_evidence_ids:['evd_1'],license_expression_id:'lic_1',
 expression:'MIT',normalized_ids:['MIT'],declaration_evidence_ids:['evd_1'],evidence:structuredClone(evidence)}]};}
// Old test bodies retain their assertions; only the new independent input is supplied.
const withAnchor=s=>({...s,validateMaterialClaims:(v,r,a=anchor())=>s.validateMaterialClaims(v,r,a),
 readMaterialClaims:(a,r,signal)=>s.readMaterialClaims(a,r,anchor(),signal)});
function setup(){const rt=runtime();Object.assign(rt.shared,{TextEncoder,TextDecoder,structuredClone,crypto:webcrypto});return {rt,s:withAnchor(rt.load('services/materialClaims.ts'))};}
test('accepts exact saved-result scoped DTO without deriving license truth',async()=>{const {s}=setup();assert.equal((await s.validateMaterialClaims(fixture(),result())).materials[0].license_version,null);});
for(const [label,change] of [
 ['wrong result',v=>v.result_id='p2res_other'],['future revision',v=>v.revision++],['changed result hash',v=>v.result_sha256=b],
 ['foreign version',v=>v.materials[0].subject={...subject,version:'8.0.0'}],['foreign evidence',v=>v.claims[0].evidence=[{evidence_id:'evd_other',source_sha256:h}]],
 ['wrong evidence hash',v=>v.materials[0].evidence=[{evidence_id:'evd_1',source_sha256:b}]],['missing material',v=>v.materials=[]],
 ['missing condition',v=>v.claims[0].conditions=[]],['missing clause link',v=>v.claims[0].clause_ids.pop()],
 ['unbound source',v=>v.materials[0].source_binding='NOT_ESTABLISHED'],['range overflow',v=>v.materials[0].clauses[0].byte_end=999],
 ['UTF8 range mismatch',v=>v.materials[0].clauses[0].quote='许可'],['unknown field',v=>v.grant=true],
 ['false use upgraded',v=>{v.advice[2].state='SUPPORT';v.claims[2].state='SUPPORT';}],
 ['missing advice',v=>v.advice.pop()],['duplicate pair reordered subject keys',v=>{v.claims[1]={...v.claims[0],claim_id:'p4claim_dup',subject:{version:'7.0.0',resource_id:'cmp_1'}};}],
 ['formal escalation',v=>v.formal_effect='verified'],['model provenance',v=>v.model_calls=1]
])test('rejects '+label,async()=>{const {s}=setup(),v=structuredClone(fixture());change(v);await assert.rejects(s.validateMaterialClaims(v,result()));});
test('GET targets exact result and assessment version; transport error does not make a success',async()=>{const {rt,s}=setup(),calls=[];rt.setFetch(async(url,init)=>{calls.push({url,method:init.method??'GET'});return Response.json(fixture());});await s.readMaterialClaims({id:'asm_1',scan_id:'scn_1',version:1},result());assert.equal(calls.length,1);assert.equal(calls[0].method,'GET');assert.equal(calls[0].url,'/api/v1/scans/scn_1/assessments/asm_1/p2/results/p2res_1/material-claims?assessment_version=1');rt.setFetch(async()=>Response.json({error:{code:'p2_not_found',message:'missing'}},{status:404}));await assert.rejects(s.readMaterialClaims({id:'asm_1',scan_id:'scn_1',version:1},result()));assert.equal(rt.storage.size,0);});


// TASK34: real SHA256 inside test code, never a captured product response.
for(const [label,change] of [
 ['same byte length quote replacement',v=>v.materials[0].clauses[0].quote='y'],
 ['changed quote length',v=>v.materials[0].clauses[0].quote='longer'],
 ['changed quote hash',v=>v.materials[0].clauses[0].quote_sha256=b],
 ['v1 contract',v=>v.schema_version='openguard-material-claims/1'],
 ['source NOTICE omitted from upload',v=>{const o=v.source_observations[0];o.notice_status='PRESENT_UNREVIEWED';o.notices=[{path:'package/NOTICE',bytes:1,sha256:h,inspection_state:'EXTRACTED_UNREVIEWED'}];}],
 ['incomplete source with SUPPORT',v=>{v.source_observations[0].notice_status='INCOMPLETE';v.source_observations[0].enumeration_complete=false;}],
 ['invented role without source',v=>{v.materials[0].role='root_package';v.materials[0].role_state='inferred';}],
])test('v2 rejects '+label,async()=>{const {s}=setup(),v=structuredClone(fixture());change(v);await assert.rejects(s.validateMaterialClaims(v,result()));});
for(const quote of ['许可原文','line one\r\nline two','多字节\r\n第二行'])test('UTF8 and CRLF quote hash: '+JSON.stringify(quote),async()=>{
 const {s}=setup(),v=fixture();let offset=0,line=1;
 for(const [i,c] of v.materials[0].clauses.entries()){
  c.quote=i===0?quote:'x';c.quote_sha256=sha(c.quote);c.byte_start=offset;offset+=Buffer.byteLength(c.quote);c.byte_end=offset;
  c.line_start=line;c.line_end=line+c.quote.slice(0,-1).split('\n').length-1;line+=c.quote.split('\n').length-1;
 }
 v.materials[0].byte_count=offset;
 assert.equal((await s.validateMaterialClaims(v,result())).materials[0].clauses[0].quote,quote);
});
test('Web Crypto unavailable rejects without format-only fallback',async()=>{const {rt,s}=setup();rt.shared.crypto=undefined;const fresh=runtime();Object.assign(fresh.shared,{TextEncoder,TextDecoder,structuredClone,crypto:undefined});await assert.rejects(fresh.load('services/materialClaims.ts').validateMaterialClaims(fixture(),result(),anchor()));});
test('same-length quote mutated during await cannot replace checked snapshot',async()=>{
 const rt=runtime();let release,started;const entered=new Promise(r=>started=r),gate=new Promise(r=>release=r);let first=true;
 Object.assign(rt.shared,{TextEncoder,TextDecoder,structuredClone,crypto:{subtle:{digest:async(...args)=>{if(first){first=false;started();await gate;}return webcrypto.subtle.digest(...args);}}}});
 const s=withAnchor(rt.load('services/materialClaims.ts')),v=fixture();const pending=s.validateMaterialClaims(v,result());await entered;v.materials[0].clauses[0].quote='y';release();const checked=await pending;assert.equal(checked.materials[0].clauses[0].quote,'x');
});
test('abort while quote hashing rejects late response',async()=>{
 const rt=runtime();let release,started;const entered=new Promise(r=>started=r),gate=new Promise(r=>release=r);let first=true;
 Object.assign(rt.shared,{TextEncoder,TextDecoder,structuredClone,crypto:{subtle:{digest:async(...args)=>{if(first){first=false;started();await gate;}return webcrypto.subtle.digest(...args);}}}});
 rt.setFetch(async()=>Response.json(fixture()));const s=withAnchor(rt.load('services/materialClaims.ts')),controller=new AbortController();
 const pending=s.readMaterialClaims({id:'asm_1',scan_id:'scn_1',version:1},result(),controller.signal);await entered;controller.abort();release();await assert.rejects(pending,e=>e.name==='AbortError');
});

// Controlled hook harness executes the actual component only after future test approval.
// Transport fixtures below exercise UI isolation, not real backend success.
const nodes=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(nodes):[x,...nodes(x.props?.children)];
const renderedText=x=>x==null||typeof x==='boolean'?'':Array.isArray(x)?x.map(renderedText).join(''):typeof x==='object'?renderedText(x.props?.children):String(x);
async function panelHarness(previousOutcome='failure',empty=false){
 const states=[],effects=[];let si=0,ei=0,dirty=true,pending=[],tree;const calls=[];
 const props={assessment:{id:'asm_1',scan_id:'scn_1',version:1},result:result(),resourceName:()=> 'is-number',declarationSnapshot:anchor()};
 const hooks={useState(initial){const i=si++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return[states[i],value=>{const next=typeof value==='function'?value(states[i]):value;if(!Object.is(next,states[i])){states[i]=next;dirty=true;}}];},useEffect(fn,deps){const i=ei++,old=effects[i];if(!old||deps.some((x,j)=>!Object.is(x,old.deps[j]))){effects[i]={deps,cleanup:old?.cleanup};pending.push(()=>{old?.cleanup?.();effects[i].cleanup=fn();});}}};
 const display=fixture();
 if(empty){props.result.material_ids=[];props.result.resources[0].material_ids=[];display.materials=[];for(const c of display.claims){c.material_ids=[];c.evidence=[];c.clause_ids=[];c.conditions=[];if(c.state==='SUPPORT')c.state='UNKNOWN';}for(const a of display.advice){a.conditions=[];if(a.state==='SUPPORT')a.state='UNKNOWN';a.reasons=['MISSING_LICENSE_MATERIAL'];}}
 const services={readMaterialClaims:async(_a,r)=>{calls.push(r.result_id);if(r.result_id==='p2res_old')throw Error('previous DTO binding conflict');return display;}};
 const source=fs.readFileSync(new URL('../src/components/MaterialClaimsPanel.tsx',import.meta.url),'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const m={exports:{}};
 vm.runInNewContext(output,{module:m,exports:m.exports,AbortController,Error,require:name=>name==='react'?hooks:name==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'Fragment'}:name.endsWith('/services/materialClaims')?services:name.endsWith('/services/assessments')?{usageFields:{commercial:'商业',distributed:'分发',modified:'修改'}}:name.endsWith('/services/p2')?{readPreviousResult:async(_a,_b,r)=>{calls.push('previous:'+r.previous_result_id);if(previousOutcome==='failure')throw Error('previous missing');if(previousOutcome==='absent')return null;return{...r,result_id:r.previous_result_id};}}:(()=>{throw Error('unexpected import '+name);})()});
 async function settle(){for(let i=0;i<30;i++){if(dirty){dirty=false;si=ei=0;pending=[];tree=m.exports.MaterialClaimsPanel(props);for(const f of pending)f();}await new Promise(r=>setImmediate(r));if(!dirty)return;}throw Error('did not settle');}
 await settle();return{calls,settle,get tree(){return tree;},get text(){return renderedText(tree);},compare(){const button=nodes(tree).find(n=>n.type==='button'&&renderedText(n)==='读取指定前版的材料建议进行对照');assert.ok(button);button.props.onClick();},dispose(){effects.forEach(e=>e.cleanup?.());}};
}
for(const outcome of ['failure','absent','binding-conflict'])test('prior '+outcome+' preserves current verified view',async()=>{const ui=await panelHarness(outcome);try{assert.match(ui.text,/上传与绑定：本版保存 1 份材料/);assert.doesNotMatch(ui.text,/每条建议都有明确/);ui.compare();await ui.settle();assert.match(ui.text,/前版比较未完成/);assert.match(ui.text,/上传与绑定：本版保存 1 份材料/);assert.match(ui.text,/有条件文本支持/);assert.equal(ui.calls.filter(x=>x==='p2res_1').length,1);assert.equal(ui.calls.some(x=>String(x).includes('latest')),false);}finally{ui.dispose();}});

test('empty material panel states gap instead of claiming every advice has original text',async()=>{const ui=await panelHarness('failure',true);try{assert.match(ui.text,/本版保存 0 份材料/);assert.match(ui.text,/缺少完整许可证材料/);assert.doesNotMatch(ui.text,/每条建议都有明确的资源和原文依据/);}finally{ui.dispose();}});
test('role provenance is separate from material binding and requires hashed row references',async()=>{const {s}=setup(),v=fixture(),r=result();r.resources[0].evidence_ids.push('evd_name','evd_version');r.resources[0].evidence_source_hashes.evd_name=b;r.resources[0].evidence_source_hashes.evd_version=b;v.materials[0].role='root_package';v.materials[0].role_state='inferred';v.materials[0].role_basis_evidence_ids=['evd_name','evd_version'];const checked=await s.validateMaterialClaims(v,r);assert.deepEqual(checked.materials[0].evidence.map(e=>e.evidence_id),['evd_1']);assert.deepEqual(checked.materials[0].role_basis_evidence_ids,['evd_name','evd_version']);});
test('NOTICE source reference never needs fabricated uploaded material or scan evidence',async()=>{const {s}=setup(),v=fixture();v.source_observations[0].notice_status='PRESENT_UNREVIEWED';v.source_observations[0].notices=[{path:'package/NOTICE',bytes:1,sha256:h,inspection_state:'EXTRACTED_UNREVIEWED'}];v.materials[0].adoption_state='OBSERVATION_ONLY';v.materials[0].source_binding='NOT_ESTABLISHED';for(const c of v.claims){if(c.state==='SUPPORT')c.state='UNKNOWN';c.conditions=[];c.counter_evidence=[{code:'NOTICE_REQUIRES_REVIEW',material_ids:[],evidence_ids:[],source_observation_ids:['p4source_1'],declaration_evidence_ids:[],evidence_status:'COMPLETE'}];}for(const a of v.advice){if(a.state==='SUPPORT')a.state='UNKNOWN';a.conditions=[];}const checked=await s.validateMaterialClaims(v,result());assert.deepEqual(checked.claims[0].counter_evidence[0].material_ids,[]);const bad=structuredClone(v);bad.claims[0].counter_evidence[0].evidence_ids=['evd_1'];await assert.rejects(s.validateMaterialClaims(bad,result()));});


// TASK35: independent report provenance, deliberately not derived from the DTO under test.
function distinctSources(){
 const r=result(),v=fixture(),a=anchor();
 r.resources[0].evidence_ids=['evd_license','evd_decl','evd_readme'];
 r.resources[0].evidence_source_hashes={evd_license:h,evd_decl:b,evd_readme:'c'.repeat(64)};
 const material=[{evidence_id:'evd_license',source_sha256:h}],declaration=[{evidence_id:'evd_decl',source_sha256:b}];
 v.materials[0].evidence=material;
 Object.assign(v.declaration_observations[0],{declaration_evidence_ids:['evd_decl'],evidence:declaration});
 for(const c of v.claims)c.evidence=[...material,...declaration];
 Object.assign(a.resources[0],{resource_evidence_ids:[...r.resources[0].evidence_ids],declaration_evidence_ids:['evd_decl'],evidence:structuredClone(declaration)});
 return {r,v,a};
}
function makeConflict(x,normalization=false){
 const {r,v,a}=x,d=v.declaration_observations[0];
 const expression=normalization?'MIT':'GPL-3.0-only',normalized=normalization?['Apache-2.0']:['GPL-3.0-only'];
 Object.assign(a.resources[0],{expression,normalized_ids:normalized});Object.assign(d,{expression,normalized_ids:normalized});
 Object.assign(v.materials[0],{declared_spdx:expression,adoption_state:'OBSERVATION_ONLY',source_binding:'NOT_ESTABLISHED'});
 for(const c of v.claims){
   c.conditions=[];if(c.state==='SUPPORT')c.state='COUNTER_EVIDENCE';
   c.counter_evidence=[{code:normalization?'SPDX_NORMALIZATION_CONFLICT':'SPDX_TEXT_CONFLICT',material_ids:normalization?[]:['p2mat_1'],
     declaration_evidence_ids:['evd_decl'],evidence_ids:normalization?['evd_decl']:['evd_license','evd_decl'],source_observation_ids:[],evidence_status:'COMPLETE'}];
 }
 for(const d of v.advice){d.conditions=[];if(d.state==='SUPPORT')d.state='COUNTER_EVIDENCE';}
 return x;
}
test('v3 accepts separate material and declaration identities',async()=>{const {s}=setup(),{v,r,a}=distinctSources();const checked=await s.validateMaterialClaims(v,r,a);assert.deepEqual(checked.declaration_observations[0].declaration_evidence_ids,['evd_decl']);});
for(const normalization of [false,true])test('v3 exact SPDX counter set '+normalization,async()=>{const {s}=setup(),{v,r,a}=makeConflict(distinctSources(),normalization);await s.validateMaterialClaims(v,r,a);});
for(const [label,change] of [
 ['README added to declaration',({v})=>{const d=v.declaration_observations[0];d.declaration_evidence_ids.push('evd_readme');d.evidence.push({evidence_id:'evd_readme',source_sha256:'c'.repeat(64)});} ],
 ['README replaces declaration coherently',({v})=>{const d=v.declaration_observations[0];d.declaration_evidence_ids=['evd_readme'];d.evidence=[{evidence_id:'evd_readme',source_sha256:'c'.repeat(64)}];for(const c of v.claims){c.counter_evidence[0].declaration_evidence_ids=['evd_readme'];c.counter_evidence[0].evidence_ids=['evd_license','evd_readme'];c.evidence=[{evidence_id:'evd_license',source_sha256:h},...d.evidence];}}],
 ['cross resource',({v})=>v.declaration_observations[0].subject={resource_id:'cmp_foreign',version:'7.0.0'}],
 ['wrong declaration version',({v})=>v.declaration_observations[0].subject={...subject,version:'8.0.0'}],
 ['duplicate declaration',({v})=>v.declaration_observations.push(structuredClone(v.declaration_observations[0]))],
 ['declaration hash changed',({v})=>v.declaration_observations[0].evidence[0].source_sha256=h],
 ['counter unrelated README',({v})=>v.claims[0].counter_evidence[0].evidence_ids.push('evd_readme')],
 ['material and declaration exchanged',({v})=>{v.claims[0].counter_evidence[0].declaration_evidence_ids=['evd_license'];v.declaration_observations[0].declaration_evidence_ids=['evd_license'];v.declaration_observations[0].evidence=[{evidence_id:'evd_license',source_sha256:h}];}],
 ['SourceObservation as declaration',({v})=>{v.declaration_observations[0].declaration_evidence_ids=['p4source_1'];v.declaration_observations[0].evidence=[{evidence_id:'p4source_1',source_sha256:h}];}],
 ['claimed SPDX text mismatch absent in actual declaration',({v,a})=>{v.declaration_observations[0].expression='MIT';v.declaration_observations[0].normalized_ids=['MIT'];v.materials[0].declared_spdx='MIT';a.resources[0].expression='MIT';a.resources[0].normalized_ids=['MIT'];}],
])test('v3 rejects '+label,async()=>{const {s}=setup(),x=makeConflict(distinctSources());change(x);await assert.rejects(s.validateMaterialClaims(x.v,x.r,x.a));});
test('normalization counter cannot claim conflict for actual normalized MIT',async()=>{const {s}=setup(),x=makeConflict(distinctSources(),true);x.v.declaration_observations[0].normalized_ids=['MIT'];x.a.resources[0].normalized_ids=['MIT'];await assert.rejects(s.validateMaterialClaims(x.v,x.r,x.a));});
for(const missing of ['absent','foreign','hashless'])test('unknown declaration '+missing+' cannot support',async()=>{
 const {s}=setup(),{v,r,a}=distinctSources();const d=v.declaration_observations[0];
 if(missing==='absent'){a.resources[0].declaration_evidence_ids=[];a.resources[0].evidence=[];}
 if(missing==='foreign')a.resources[0].resource_evidence_ids=['evd_license','evd_readme'];
 if(missing==='hashless'){a.resources[0].evidence[0].source_sha256=null;delete r.resources[0].evidence_source_hashes.evd_decl;}
 d.declaration_evidence_ids=[];d.evidence=[];d.evidence_status='UNKNOWN';
 for(const c of v.claims)c.evidence=[{evidence_id:'evd_license',source_sha256:h}];
 await assert.rejects(s.validateMaterialClaims(v,r,a));
 v.materials[0].adoption_state='OBSERVATION_ONLY';v.materials[0].source_binding='NOT_ESTABLISHED';
 for(const c of v.claims){if(c.state==='SUPPORT')c.state='UNKNOWN';c.conditions=[];}
 for(const d of v.advice){if(d.state==='SUPPORT')d.state='UNKNOWN';d.conditions=[];}
 assert.equal((await s.validateMaterialClaims(v,r,a)).declaration_observations[0].evidence_status,'UNKNOWN');
});
test('missing independent report fails closed even when DTO internally agrees',async()=>{const {rt}=setup(),raw=rt.load('services/materialClaims.ts');await assert.rejects(raw.validateMaterialClaims(fixture(),result(),null));});
for(const [key,value] of [['scan_id','scn_other'],['project_revision','changed']])test('independent anchor '+key+' bound to result',async()=>{const {s}=setup(),a=anchor();a[key]=value;await assert.rejects(s.validateMaterialClaims(fixture(),result(),a));});
function frozenDecoder(version){
 const directory=version===3?'task39':'task35';
 const source=fs.readFileSync(new URL('./fixtures/'+directory+'/materialClaims.v'+version+'.ts.txt',import.meta.url),'utf8');
 const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const m={exports:{}};vm.runInNewContext(js,{module:m,exports:m.exports,TextEncoder,TextDecoder,structuredClone,crypto:webcrypto,
 require:name=>name==='./scans'?{request:()=>{throw Error('unexpected transport');}}:name==='./p2'?{sameBinding:(a,b)=>JSON.stringify(a)===JSON.stringify(b)}:(()=>{throw Error('unexpected import');})()});
 return m.exports.validateMaterialClaims;
}
for(const version of [1,2])test('frozen decoder v'+version+' rejects v3 and v4 responses',async()=>{
 const frozen=frozenDecoder(version);
 await assert.rejects(async()=>frozen(legacyV3Fixture(),result(),anchor()));
 await assert.rejects(async()=>frozen(fixture(),result(),anchor()));
});
for(const version of [1,2])test('v4 decoder rejects old response version '+version,async()=>{
 const {s}=setup(),v=fixture(),legacy=legacyV3Fixture();
 v.schema_version=legacy.schema_version='openguard-material-claims/'+version;
 v.rule_version=legacy.rule_version='mit-bound-claim/'+version;
 await assert.rejects(frozenDecoder(3)(legacy,result(),anchor()));
 await assert.rejects(s.validateMaterialClaims(v,result()));
});

function v4Fixture(legacy,r){
 const v=structuredClone(legacy),initial=r.revision===1;
 v.schema_version='openguard-material-claims/4';
 v.rule_version='mit-apache2-bound-claim/4';
 for(const m of v.materials)m.role_conflicts=[];
 v.incremental_impact={mode:initial?'INITIAL_RESULT':'INCREMENTAL_DERIVED',
  previous_result_id:r.previous_result_id,previous_revision:initial?null:r.revision-1,previous_view_id:initial?null:'p4view_old',
  affected_resource_ids:[...r.recomputed_resource_ids],unchanged_resource_ids:[...r.reused_resource_ids],
  recomputed_claim_ids:v.claims.filter(c=>r.recomputed_resource_ids.includes(c.subject.resource_id)).map(c=>c.claim_id),
  reused_claim_ids:v.claims.filter(c=>r.reused_resource_ids.includes(c.subject.resource_id)).map(c=>c.claim_id),
  added_material_ids:initial?[]:[...r.material_ids],added_answer_ids:initial?[]:[...r.answer_ids],changed_claims:[],unchanged_claims_verified:true};
 return v;
}
test('TASK39 active client accepts v4 while frozen v3 still rejects v4',async()=>{
 const {s}=setup(),r=result();
 const legacy=legacyV3Fixture(),modern=v4Fixture(legacy,r),frozen=frozenDecoder(3);
 assert.equal((await frozen(legacy,r,anchor())).schema_version,'openguard-material-claims/3');
 await assert.rejects(frozen(modern,r,anchor()));
 assert.equal((await s.validateMaterialClaims(modern,r)).schema_version,'openguard-material-claims/4');
 await assert.rejects(s.validateMaterialClaims(legacy,r));
});

// Synthetic decoder DTOs. The backend ASGI gate separately proves full Apache source binding.
function apacheFixture(noticeScenario='absent'){
 const r=result(),v=fixture(),a=anchor(),material=v.materials[0];
 r.usage.modified=true;
 for(const d of [v.declaration_observations[0],a.resources[0]])Object.assign(d,{expression:'Apache-2.0',normalized_ids:['Apache-2.0']});
 const quotes=[
  ['license_identifier','Apache License\r\nVersion 2.0, January 2004'],
  ['permission','   2. Grant of Copyright License.'],
  ['permission','   3. Grant of Patent License.'],
  ['condition','      (a) Synthetic license copy condition.'],
  ['condition','      (b) Synthetic modification notice condition.'],
  ['condition','      (c) Synthetic source notice condition.'],
  ['condition','      (d) Synthetic NOTICE condition.'],
  ['warranty','   7. Disclaimer of Warranty.'],
 ];
 const raw=quotes.map(([,quote])=>quote).join('\r\n');
 const sourceSha=sha(raw);
 let byte=0,line=1;
 const clauses=quotes.map(([kind,quote],i)=>{
  const bytes=Buffer.byteLength(quote),lines=quote.split('\n').length;
  const clause={clause_id:'p4apache_'+i,material_id:material.material_id,material_sha256:sourceSha,kind,
   byte_start:byte,byte_end:byte+bytes,line_start:line,line_end:line+lines-1,quote,quote_sha256:sha(quote)};
  byte+=bytes+2;line+=lines;return clause;
 });
 Object.assign(material,{source_sha256:sourceSha,byte_count:Buffer.byteLength(raw),parse_state:'MATCHED_APACHE_2_0',
  parse_reason:'COMPLETE_APACHE_2_0_PROFILE',declared_spdx:'Apache-2.0',text_license:'Apache-2.0',
  license_version:'2.0',version_scope:'LICENSE_VERSION_AND_RESOURCE_VERSION',clauses});
 const archiveNotice='\uFEFFSynthetic NOTICE\r\n许可声明';
 const source=v.source_observations[0];
 const counters=[];
 const counter=(code,material_ids=[],source_observation_ids=[])=>({
  code,material_ids,source_observation_ids,evidence_ids:material_ids.length?['evd_1']:[],
  declaration_evidence_ids:[],evidence_status:'COMPLETE',
 });
 if(['unuploaded','mismatch','matched'].includes(noticeScenario)){
  source.notice_status='PRESENT_UNREVIEWED';source.reason='NOTICE_NOT_INTERPRETED';
  source.notices=[{path:'package/NOTICE',bytes:Buffer.byteLength(archiveNotice),sha256:sha(archiveNotice),inspection_state:'EXTRACTED_UNREVIEWED'}];
  counters.push(counter('NOTICE_REQUIRES_REVIEW',[],[source.source_observation_id]));
 }
 if(['mismatch','matched','extra'].includes(noticeScenario)){
  const notice=noticeScenario==='matched'?archiveNotice:'Synthetic unbound upload';
  const id='p2mat_notice',hash=sha(notice),bytes=Buffer.byteLength(notice);
  r.material_ids.push(id);r.resources[0].material_ids.push(id);
  v.materials.push({...material,material_id:id,filename:'NOTICE',source_sha256:hash,byte_count:bytes,
   license_version:null,version_scope:'RESOURCE_VERSION_NOT_LICENSE_VERSION',
   text_license:'UNKNOWN',parse_state:'NOTICE_OBSERVED',parse_reason:'NOTICE_NOT_A_GRANT',
   adoption_state:'OBSERVATION_ONLY',source_binding:'NOT_ESTABLISHED',
   clauses:[{clause_id:'p4notice',material_id:id,material_sha256:hash,kind:'notice',byte_start:0,byte_end:bytes,
    quote:notice,quote_sha256:hash,line_start:1,line_end:notice.split('\n').length}]});
  counters.push(counter('NOTICE_REQUIRES_REVIEW',[id]));
  if(noticeScenario==='mismatch')counters.push(counter('BOUND_NOTICE_BYTES_CONFLICT',[id],[source.source_observation_id]));
 }
 const state=noticeScenario==='absent'?'SUPPORT':noticeScenario==='mismatch'?'COUNTER_EVIDENCE':'UNKNOWN';
 const reason={absent:'PINNED_RELEASE_AND_COMPLETE_APACHE_2_0_CONDITIONAL_TEXT',
  mismatch:'BOUND_NOTICE_BYTES_CONFLICT',matched:'NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW'}[noticeScenario]??'NOTICE_REQUIRES_REVIEW';
 const conditions=state==='SUPPORT'?['§4(a) 附许可证','§4(b) 说明改动','§4(c) 保留声明']
  :noticeScenario==='matched'?['§4(d) 人工核对 NOTICE']: [];
 if(state!=='SUPPORT')Object.assign(material,{adoption_state:'OBSERVATION_ONLY',source_binding:'NOT_ESTABLISHED'});
 for(const c of v.claims)Object.assign(c,{material_ids:[...r.material_ids],
  clause_ids:v.materials.flatMap(m=>m.clauses.map(clause=>clause.clause_id)),conditions,counter_evidence:counters,state});
 for(const d of v.advice)Object.assign(d,{saved_value:true,state,reasons:[reason],conditions});
 v.incremental_impact.added_material_ids=[...r.material_ids];
 return {v,r,a};
}
for(const [scenario,state] of [['absent','SUPPORT'],['unuploaded','UNKNOWN'],['mismatch','COUNTER_EVIDENCE'],['matched','UNKNOWN'],['extra','UNKNOWN']]){
 test('TASK39 validates Apache NOTICE scenario '+scenario,async()=>{
  const {s}=setup(),{v,r,a}=apacheFixture(scenario);
  const checked=await s.validateMaterialClaims(v,r,a);
  assert.equal(checked.materials[0].license_version,'2.0');
  assert.equal(checked.materials[0].clauses.length,8);
  assert.ok(checked.advice.every(x=>x.state===state));
  if(scenario==='matched'){
   assert.equal(checked.materials[1].source_sha256,checked.source_observations[0].notices[0].sha256);
   assert.ok(checked.advice[0].reasons.includes('NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW'));
  }
 });
}
for(const [label,scenario,mutate] of [
 ['Apache version','absent',v=>v.materials[0].license_version=null],
 ['Apache clause order','absent',v=>v.materials[0].clauses.reverse()],
 ['Apache quote bytes','absent',v=>v.materials[0].clauses[1].quote=v.materials[0].clauses[1].quote.replace('Copyright','CopyriGht')],
 ['Apache modification condition','absent',v=>{for(const item of [...v.claims,...v.advice])item.conditions=item.conditions.filter(c=>!c.includes('§4(b)'));}],
 ['matched NOTICE promotion','matched',v=>{v.claims[0].state=v.advice[0].state='SUPPORT';}],
 ['matched NOTICE reason','matched',v=>{v.advice[0].reasons=['NOTICE_REQUIRES_REVIEW'];}],
 ['archive NOTICE hash changed','matched',v=>v.source_observations[0].notices[0].sha256=b],
 ['missing NOTICE mismatch counter','mismatch',v=>v.claims[0].counter_evidence=v.claims[0].counter_evidence.filter(c=>c.code!=='BOUND_NOTICE_BYTES_CONFLICT')],
])test('TASK39 rejects '+label,async()=>{
 const {s}=setup(),{v,r,a}=apacheFixture(scenario);mutate(v);
 await assert.rejects(s.validateMaterialClaims(v,r,a));
});

test('TASK39 dependency roles require validated evidence and conflicts stay unknown',async()=>{
 const {s}=setup(),{v,r,a}=apacheFixture();
 const m=v.materials[0];
 Object.assign(m,{role:'dependency',role_state:'inferred',role_basis_evidence_ids:['evd_1']});
 assert.equal((await s.validateMaterialClaims(v,r,a)).materials[0].role,'dependency');
 m.role_conflicts=['lock_version_conflict'];
 await assert.rejects(s.validateMaterialClaims(v,r,a));
 Object.assign(m,{role:'unknown',role_state:'unknown',role_basis_evidence_ids:[]});
 assert.deepEqual((await s.validateMaterialClaims(v,r,a)).materials[0].role_conflicts,['lock_version_conflict']);
});

test('TASK39 verifies impact partitions, current claim and resource-scoped triggers',async()=>{
 const {s}=setup(),{v,r,a}=apacheFixture();
 r.answer_ids=['p2ans_1'];r.resources[0].answer_ids=['p2ans_1'];
 const impact=v.incremental_impact;
 impact.added_answer_ids=['p2ans_1'];
 impact.changed_claims=[{subject,usage:'commercial',previous_claim_id:'p4claim_prior',current_claim_id:v.claims[0].claim_id,
  previous_state:'UNKNOWN',current_state:'SUPPORT',previous_reasons:['MISSING_LICENSE_MATERIAL'],current_reasons:[...v.advice[0].reasons],
  trigger_material_ids:['p2mat_1'],trigger_answer_ids:['p2ans_1']}];
 const checked=await s.validateMaterialClaims(v,r,a);
 assert.deepEqual(checked.incremental_impact.changed_claims[0].trigger_answer_ids,['p2ans_1']);
 for(const mutate of [
  i=>i.affected_resource_ids.push('cmp_foreign'),i=>i.reused_claim_ids.push(v.claims[0].claim_id),
  i=>i.previous_revision=99,i=>i.previous_result_id='p2res_foreign',i=>i.unchanged_claims_verified=false,
  i=>i.changed_claims[0].current_state='UNKNOWN',i=>i.changed_claims[0].trigger_material_ids=[],
  i=>i.changed_claims[0].trigger_answer_ids=['p2ans_foreign'],i=>i.changed_claims[0].current_reasons=['FOREIGN_REASON'],
  i=>{i.added_material_ids=[];i.added_answer_ids=[];i.changed_claims=[];},
 ]){
  const bad=structuredClone(v);mutate(bad.incremental_impact);
  await assert.rejects(s.validateMaterialClaims(bad,r,a));
 }
});

test('scan report adapter preserves declaration mapping and ignores unrelated README',()=>{
 const {rt}=setup(),s=rt.load('services/scans.ts');
 const resource={id:'cmp_1',version:'7.0.0',license_expression_id:'lic_1',evidence_ids:['evd_decl','evd_readme']};
 const run={id:'scn_1',project:{revision:'fixed'},components:[resource],ai_assets:[],licenses:[{id:'lic_1',expression:'MIT',normalized_ids:['MIT'],evidence_ids:['evd_decl']}],
 evidence:[{id:'evd_decl',kind:'manifest_field',locator:'package.json:/license',content_hash:{algorithm:'sha256',value:b}},
 {id:'evd_readme',kind:'file_excerpt',locator:'README.md',content_hash:{algorithm:'sha256',value:h}}]};
 const a=s.declarationSnapshotFromReport('scn_1',run,[{kind:'component',resource}]);
 assert.deepEqual(Array.from(a.resources[0].declaration_evidence_ids),['evd_decl']);
 assert.equal(a.resources[0].evidence[0].source_sha256,b);
 assert.equal(s.declarationSnapshotFromReport('scn_other',run,[{resource}]),null);
 assert.equal(s.declarationSnapshotFromReport('scn_1',null,[{resource}]),null);
 const altered=structuredClone(resource);altered.version='8';assert.equal(s.declarationSnapshotFromReport('scn_1',run,[{resource:altered}]),null);
 const duplicate=structuredClone(run);duplicate.licenses.push(duplicate.licenses[0]);assert.equal(s.declarationSnapshotFromReport('scn_1',duplicate,[{resource}]),null);
});

// Controlled component render only: no browser, service or database is used by this harness.
// These test functions have NOT been run in TASK35.
function legacyWorkbenchTree(){
 const r={...result(),questions:[],recomputed_resource_ids:['cmp_1'],reused_resource_ids:[],resources:result().resources.map(x=>({...x,state:'pending',gaps:[],answer_ids:[],user_assertions:{},advice:[],inherited_local_support:false}))};
 const old={supported_resource_ids:['cmp_1'],uncovered_resource_ids:[],advice:['commercial','distributed'].map(usage=>({usage,resources:[{subject}],state:'CONDITIONAL_TEXT_BASIS'}))};
 let slot=0;
 const hooks={useState(initial){const index=slot++;const pinned={0:binding,1:{head_result_id:r.result_id,head_revision:r.revision,result_ids:[r.result_id],has_more:false},2:r,3:false,19:old};return[Object.hasOwn(pinned,index)?pinned[index]:typeof initial==='function'?initial():initial,()=>{}];},useRef:value=>({current:value}),useEffect(){},useLayoutEffect(){}};
 const js=ts.transpileModule(fs.readFileSync(new URL('../src/components/P2Workbench.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const m={exports:{}};
 vm.runInNewContext(js,{module:m,exports:m.exports,Error,require:name=>{
   if(name==='react')return hooks;
   if(name==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'Fragment'};
   if(name.endsWith('/services/p2'))return {pendingWriteFor:()=>null,sameBinding:()=>true,stateLabels:{pending:'待核验'},gapLabel:x=>x,resultPageUrl:(_a,id)=>'/exact/'+id};
   if(name.endsWith('/services/assessments'))return {usageFields:{commercial:'商业使用',distributed:'分发',modified:'修改'},assessmentReportUrl:()=>'/formal'};
   if(name.endsWith('/services/projectUsage'))return {readPendingUsageUpdate:()=>null};
   if(name.endsWith('/services/officialSources'))return {officialSourcesEnabled:false};
   if(name.endsWith('/services/p2Ai'))return {p2AiEnabled:false};
   if(name.endsWith('.css'))return {};
   return new Proxy({}, {get:(_o,k)=>String(k)});
 }});
 return m.exports.P2Workbench({assessment:{id:'asm_1',scan_id:'scn_1',version:1},scan:{id:'scn_1',status:'completed',resources:[{id:'cmp_1',name:'is-number'}],evidence:[],declarationSnapshot:anchor()},readOnly:true});
}
test('legacy support cannot stand in for new UNKNOWN or COUNTER_EVIDENCE and history stays visible',()=>{
 const tree=legacyWorkbenchTree(),all=nodes(tree),text=renderedText(tree);
 const panel=all.find(n=>n.type==='MaterialClaimsPanel'),legacy=all.find(n=>n.type==='details'&&n.props.className?.includes('p2-prior-evidence'));
 assert.ok(panel&&legacy);assert.ok(all.indexOf(panel)<all.indexOf(legacy));
 assert.equal(panel.props.result.result_id,'p2res_1');assert.deepEqual(panel.props.declarationSnapshot,anchor());
 assert.equal('preliminary' in panel.props,false);assert.equal('supported_resource_ids' in panel.props,false);
 assert.match(renderedText(legacy),/1 个资源具有旧规则条件初评/);
 const boundary=all.find(n=>Object.hasOwn(n.props??{},'data-legacy-advice-boundary'));
 assert.match(renderedText(boundary),/未上传的NOTICE/);assert.match(renderedText(boundary),/不是新版材料来源闭包的替代品/);
 assert.match(renderedText(boundary),/UNKNOWN、COUNTER_EVIDENCE或NOTICE阻塞/);
 for(const card of all.filter(n=>n.type==='article'&&n.props.className==='has-basis'))assert.match(renderedText(card),/不能替代上方新版证据链/);
 assert.match(text,/已保存版本与下载/);assert.ok(all.some(n=>n.type==='a'&&n.props.href==='/exact/p2res_1'));
});

test('SPDX conflict with genuinely missing declaration evidence stays UNKNOWN provenance',async()=>{
 const {s}=setup(),x=makeConflict(distinctSources());
 Object.assign(x.a.resources[0],{declaration_evidence_ids:[],evidence:[]});
 Object.assign(x.v.declaration_observations[0],{declaration_evidence_ids:[],evidence:[],evidence_status:'UNKNOWN'});
 for(const c of x.v.claims){c.evidence=[{evidence_id:'evd_license',source_sha256:h}];Object.assign(c.counter_evidence[0],{declaration_evidence_ids:[],evidence_ids:['evd_license'],evidence_status:'UNKNOWN'});}
 const actual=await s.validateMaterialClaims(x.v,x.r,x.a);
 assert.equal(actual.claims[0].counter_evidence[0].evidence_status,'UNKNOWN');assert.equal(actual.advice[0].state,'COUNTER_EVIDENCE');
});
test('NOTICE source counter cannot smuggle declaration evidence or source ID into scan evidence',async()=>{
 const {s}=setup(),x=distinctSources();const o=x.v.source_observations[0];o.notice_status='PRESENT_UNREVIEWED';o.notices=[{path:'package/NOTICE',bytes:1,sha256:h,inspection_state:'EXTRACTED_UNREVIEWED'}];
 x.v.materials[0].adoption_state='OBSERVATION_ONLY';x.v.materials[0].source_binding='NOT_ESTABLISHED';
 for(const c of x.v.claims){if(c.state==='SUPPORT')c.state='UNKNOWN';c.conditions=[];c.counter_evidence=[{code:'NOTICE_REQUIRES_REVIEW',material_ids:[],evidence_ids:[],declaration_evidence_ids:[],source_observation_ids:['p4source_1'],evidence_status:'COMPLETE'}];}
 for(const a of x.v.advice){if(a.state==='SUPPORT')a.state='UNKNOWN';a.conditions=[];}
 await s.validateMaterialClaims(x.v,x.r,x.a);
 for(const mutation of [e=>e.declaration_evidence_ids=['evd_decl'],e=>e.evidence_ids=['p4source_1'],e=>e.evidence_ids=['evd_decl']]){const v=structuredClone(x.v);mutation(v.claims[0].counter_evidence[0]);await assert.rejects(s.validateMaterialClaims(v,x.r,x.a));}
});

test('bound LICENSE conflict has only material evidence and cannot borrow declaration evidence',async()=>{
 const {s}=setup(),x=distinctSources(),m=structuredClone(x.v.materials[0]);
 m.material_id='p2mat_2';m.filename='LICENCE';m.source_sha256=b;m.adoption_state='OBSERVATION_ONLY';m.source_binding='NOT_ESTABLISHED';
 m.evidence=[{evidence_id:'evd_license2',source_sha256:'d'.repeat(64)}];
 for(const c of m.clauses){c.clause_id+='second';c.material_id=m.material_id;c.material_sha256=b;}
 x.r.material_ids.push(m.material_id);x.r.resources[0].material_ids.push(m.material_id);x.r.resources[0].evidence_ids.push('evd_license2');x.r.resources[0].evidence_source_hashes.evd_license2='d'.repeat(64);
 x.v.materials.push(m);x.v.materials[0].adoption_state='OBSERVATION_ONLY';x.v.materials[0].source_binding='NOT_ESTABLISHED';
 for(const c of x.v.claims){c.material_ids.push(m.material_id);c.clause_ids.push(...m.clauses.map(c=>c.clause_id));c.evidence.push(...m.evidence);c.conditions=[];if(c.state==='SUPPORT')c.state='COUNTER_EVIDENCE';
 c.counter_evidence=[{code:'BOUND_LICENSE_BYTES_CONFLICT',material_ids:['p2mat_1','p2mat_2'],evidence_ids:['evd_license','evd_license2'],declaration_evidence_ids:[],source_observation_ids:[],evidence_status:'COMPLETE'}];}
 for(const a of x.v.advice){a.conditions=[];if(a.state==='SUPPORT')a.state='COUNTER_EVIDENCE';}
 await s.validateMaterialClaims(x.v,x.r,x.a);
 x.v.claims[0].counter_evidence[0].declaration_evidence_ids=['evd_decl'];x.v.claims[0].counter_evidence[0].evidence_ids.push('evd_decl');
 await assert.rejects(s.validateMaterialClaims(x.v,x.r,x.a));
});

// TASK36: render the actual inner components, with a nonempty historical Result.
// SYNTHETIC_TEST_ONLY. Future local test only; no real backend success is claimed.
function task36NamedComponent(source, name, dependencies){
 const file=ts.createSourceFile('P2Workbench.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const fn=file.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name);
 assert.ok(fn,'actual production component is present');
 const js=ts.transpileModule(fn.getText(file)+'\nexports.render='+name+';',{
   compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const m={exports:{}};
 vm.runInNewContext(js,{...dependencies,module:m,exports:m.exports,require:n=>{
   assert.equal(n,'react/jsx-runtime');return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'Fragment'};
 }});
 return m.exports.render;
}
test('TASK36 nonempty saved compatibility candidate and old preliminary support coexist with actual v4 UNKNOWN panel',async()=>{
 const {rt,s}=setup(),p2=rt.load('services/p2.ts');
 const f=rt.load('../tests/bound-advice-maincard-corrected-fixture/fixture.ts').makeFixture();
 const original=JSON.stringify(f.result),names={commercial:'商业使用',distributed:'分发',modified:'修改'};
 const selected=p2.selectBoundSavedAdvice(f.assessment,f.binding,f.result,f.scan);
 assert.ok(selected.rows.length>0,'must not pass with empty historical advice');
 assert.ok(f.result.resources[0].advice.some(d=>d.state==='conditional_candidate'&&d.conditions.length>0));
 const source=fs.readFileSync(new URL('../src/components/P2Workbench.tsx',import.meta.url),'utf8');
 const savedRender=task36NamedComponent(source,'SavedAdviceMainCard',{selectBoundSavedAdvice:p2.selectBoundSavedAdvice,usageFields:names,gapLabel:p2.gapLabel});
 const savedTree=savedRender(f),savedText=renderedText(savedTree);
 assert.match(savedText,/已保存的兼容性条件候选/);
 assert.match(savedText,/不是新版 v3 材料来源闭包结论/);
 assert.match(savedText,/不能覆盖新版 UNKNOWN、COUNTER_EVIDENCE 或 NOTICE 阻塞/);
 assert.match(savedText,/不表示已获许可/);
 for(const row of selected.rows){
   for(const condition of row.conditions)assert.ok(savedText.includes(condition),'original conditions remain visible');
   const card=nodes(savedTree).find(n=>n.props?.['data-bound-advice-resource']===row.subject.resource_id);
   assert.ok(card);assert.match(renderedText(card),/仅来自历史 Result 的此资源版本与用途/);
 }
 const declarationSnapshot={scan_id:f.binding.scan_id,project_revision:f.binding.project_revision,
   resources:f.result.resources.map((r,i)=>({resource_id:r.subject.resource_id,version:r.subject.version,
     resource_evidence_ids:[...r.evidence_ids],license_expression_id:i===0?'lic_test_saved':null,
     expression:i===0?'MIT':'UNOBSERVED',normalized_ids:i===0?['MIT']:[],declaration_evidence_ids:[],evidence:[]}))};
 const decl=declarationSnapshot.resources.map(r=>({subject:{resource_id:r.resource_id,version:r.version},expression:r.expression,normalized_ids:r.normalized_ids,
   declaration_evidence_ids:[],evidence:[],evidence_status:'UNKNOWN'}));
 const claims=f.result.resources.flatMap((r,i)=>['commercial','distributed','modified'].map(usage=>({
   claim_id:'p4claim_saved_'+i+'_'+usage,usage,subject:r.subject,material_ids:[],evidence:[],clause_ids:[],conditions:[],counter_evidence:[],
   state:f.result.usage[usage]===false?'NOT_COVERED':'UNKNOWN',formal_effect:'none'})));
 const dto={schema_version:'openguard-material-claims/3',rule_version:'mit-bound-claim/3',view_id:'p4view_saved_unknown',
   result_id:f.result.result_id,result_sha256:f.result.result_sha256,revision:f.result.revision,previous_result_id:f.result.previous_result_id,
   binding:f.binding,data_scope:'TEST_ONLY',source_status:'NOT_CONFIGURED',source_profile_sha256:null,materials:[],source_observations:[],declaration_observations:decl,claims,
   advice:claims.map(c=>({usage:c.usage,subject:c.subject,saved_value:f.result.usage[c.usage],state:c.state,reasons:['MISSING_LICENSE_MATERIAL'],claim_ids:[c.claim_id],conditions:[],limitations:['SYNTHETIC_TEST_ONLY: material source closure is unavailable']})),
   formal_effect:'none',applicability_review:'NOT_SIGNED',model_calls:0};
 const checked=await s.validateMaterialClaims(v4Fixture(dto,f.result),f.result,declarationSnapshot);
 assert.equal(checked.advice.find(a=>a.subject.resource_id===selected.rows[0].subject.resource_id&&a.usage==='commercial').state,'UNKNOWN');
 // Ready state represents the validated DTO above; effects/transport cannot execute.
 const key=JSON.stringify([f.assessment.scan_id,f.assessment.id,f.assessment.version,f.result.result_id,f.result.result_sha256,f.result.binding,declarationSnapshot]);
 let stateSlot=0;
 const hooks={useState(initial){const slot=stateSlot++;return [slot===2?{key,current:checked}:typeof initial==='function'?initial():initial,()=>{}];},useEffect(){}};
 const panelSource=fs.readFileSync(new URL('../src/components/MaterialClaimsPanel.tsx',import.meta.url),'utf8');
 const js=ts.transpileModule(panelSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const m={exports:{}};
 vm.runInNewContext(js,{module:m,exports:m.exports,require:n=>{
   if(n==='react')return hooks;
   if(n==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'Fragment'};
   if(n.endsWith('/services/assessments'))return {usageFields:names};
   if(n.endsWith('/services/materialClaims'))return {readMaterialClaims:()=>{throw Error('transport forbidden in ready-state render');}};
   if(n.endsWith('/services/p2'))return {readPreviousResult:()=>{throw Error('transport forbidden');}};
   throw Error('unexpected import '+n);
 }});
 const newTree=m.exports.MaterialClaimsPanel({assessment:f.assessment,result:f.result,declarationSnapshot,resourceName:()=> 'synthetic-alpha'});
 assert.match(renderedText(newTree),/材料与用途证据链/);assert.match(renderedText(newTree),/依据不足，保持未知/);
 assert.doesNotMatch(renderedText(newTree),/有条件文本支持/);
 // CONDITIONAL_TEXT_BASIS is a separate old API object, never a Result state.
 const oldRender=task36NamedComponent(source,'UseAdviceCard',{});
 const oldTree=oldRender({advice:{state:'CONDITIONAL_TEXT_BASIS',summary:'SYNTHETIC_TEST_ONLY legacy preliminary',resources:[]}});
 assert.match(renderedText(oldTree),/有条件适用/);
 assert.ok(source.indexOf('<MaterialClaimsPanel')<source.indexOf('<SavedAdviceMainCard'));
 assert.match(source,/兼容性初评 · 不替代新版证据链/);
 const combined=renderedText([newTree,savedTree,oldTree]);
 assert.match(combined,/依据不足，保持未知/);assert.match(combined,/已保存的兼容性条件候选/);
 assert.equal(JSON.stringify(f.result),original,'render and selection must not rewrite historical Result');
});
