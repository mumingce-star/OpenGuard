import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
import {runtime} from './runtime.mjs';

// SYNTHETIC_TEST_ONLY. Closed bottom transport, real Services and React SSR.
// No real network, browser, model generation or business storage is involved.
const require=createRequire(import.meta.url),origin='PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION';
const clone=value=>JSON.parse(JSON.stringify(value));
const canonical=value=>Array.isArray(value)?'['+value.map(canonical).join(',')+']':value&&typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);
const digest=value=>crypto.createHash('sha256').update(canonical(value)).digest('hex');
const condition='The above copyright notice and this permission notice shall be\nincluded in all copies or substantial portions of the Software.';

function setup(){
 const rt=runtime(),ledger=[],nonGet=[],unknown=[];rt.shared.TextEncoder=TextEncoder;rt.shared.structuredClone=structuredClone;
 rt.shared.sessionStorage={getItem:()=>null,setItem:()=>{},removeItem:()=>{}};
 const service=rt.load('services/officialSources.ts'),ai=rt.load('services/p2Ai.ts'),f=rt.load('../tests/bound-advice-maincard-corrected-fixture/fixture.ts').makeFixture();
 const usage={commercial:true,modified:true,distributed:false,network_service:false,training:true,redistributed_assets:true,source_disclosure:false};
 f.result.usage={...usage};f.assessment.usage={preset:'closed_source',...usage};f.binding.project_revision=service.fixedCommit;f.result.resources[0].subject.version='14.1.2';
 const subject={...f.result.resources[0].subject},mid='p2src_SYNTHETIC_TEST_ONLY',license=fs.readFileSync(new URL('./official-sources/LICENSE.txt',import.meta.url),'utf8'),start=[...license.slice(0,license.indexOf(condition))].length;
 const quote={quote_id:'q0',material_id:mid,source_sha256:service.fixedLicenseHash,source_level:'retrieved_unadopted_candidate',verification_state:'pending',subject,quote:condition,start,end:start+[...condition].length};
 const targets=[{target_id:'component_source',scope_kind:'component_source',subject,assessment_id:f.assessment.id,usage_field:null},...['training','redistributed_assets'].map(field=>({target_id:'usage_'+field,scope_kind:'assessment_usage_gap',subject:null,assessment_id:f.assessment.id,usage_field:field}))];
 const gaps=['training','redistributed_assets'].map(field=>({gap_id:'gap_'+field+'_scope_unobserved',target_id:'usage_'+field,usage_field:field,observed_value:true,state:'NOT_OBSERVED',description:'SYNTHETIC_TEST_ONLY 未取得相应范围材料'}));
 const catalog=[{kind:'CHECK_MODIFIED_COPY',target_id:'component_source',basis_kind:'license_condition',eligible_basis_ids:['q0'],usage_fields:['modified'],required_usage:{modified:true},description:'SYNTHETIC_TEST_ONLY 修改副本核对'},...gaps.map((gap,i)=>({kind:i?'CHECK_ASSET_SCOPE':'CHECK_TRAINING_SCOPE',target_id:gap.target_id,basis_kind:'usage_gap',eligible_basis_ids:[gap.gap_id],usage_fields:[gap.usage_field],required_usage:{[gap.usage_field]:true},description:gap.description}))];
 const context={protocol:'openguard-action-plan/2',result_id:f.result.result_id,result_sha256:f.result.result_sha256,binding:{...f.binding},subject,usage:{...usage},targets,quote_catalog:[quote],action_catalog:catalog,gaps};context.context_sha256=digest(context);
 const plan={clauses:[{quote_id:'q0',category:'condition'}],actions:catalog.map(row=>({kind:row.kind,target_id:row.target_id,basis_kind:row.basis_kind,basis_ids:[...row.eligible_basis_ids]})),change_explanations:[]};
 const actions=catalog.map(row=>({text:ai.boundActionText(row.kind,subject),source_candidate_ids:row.basis_kind==='usage_gap'?[]:[mid],claim_level:'verification_action_only',action_kind:row.kind,target_id:row.target_id,basis_kind:row.basis_kind,basis_ids:[...row.eligible_basis_ids],usage_fields:[...row.usage_fields],plan_protocol:'openguard-action-plan/2',display_origin:origin}));
 const details={protocol:'openguard-action-plan/2',status:'validated',display_origin:origin,context_sha256:context.context_sha256,selection_sha256:digest(plan),context,action_bindings:clone(catalog),human_review_required:false,corrective_attempt_used:false,attempt_count:1};
 const coverage={coverage:'complete_fixed_sources',npm_metadata_status:'observed',source_failures:[]};
 const preview={...coverage,schema_version:'openguard-official-source-preview/1',preview_id:'p2prev_SYNTHETIC_TEST_ONLY',preview_sha256:'3'.repeat(64),result_id:f.result.result_id,result_sha256:f.result.result_sha256,binding:{...f.binding},status:'succeeded',created_at:'2026-10-24T00:00:00Z',model_calls:1,model:{name:'Qwen_SYNTHETIC_TEST_ONLY',digest:'2'.repeat(64),runtime:'SYNTHETIC_TEST_ONLY'},metrics:{elapsed_ms:1},clauses:[{source_candidate_id:mid,quote:condition,start,end:quote.end,category:'condition',quote_id:'q0'}],actions,changes:[],limitations:['SYNTHETIC_TEST_ONLY：不签发来源，不确认许可适用。'],analysis_protocol:'openguard-qwen-action-plan/2',validation_details:details,plan,attempts:[{number:1,state:'succeeded',raw_output:JSON.stringify(plan),model_calls:1}]};
 const candidate={...coverage,candidate_id:mid,scan_id:f.assessment.scan_id,subject,commit:service.fixedCommit,license_text:license,adoption_status:'not_adopted',limitations:[],sources:[{kind:'git_license',url:`https://raw.githubusercontent.com/http-party/http-server/${service.fixedCommit}/LICENSE`,sha256:service.fixedLicenseHash,byte_count:1124,source_level:'retrieved_unadopted_candidate',verification_state:'pending'},{kind:'npm_metadata',url:'https://registry.npmjs.org/http-server/14.1.2',sha256:'4'.repeat(64),byte_count:99,source_level:'provider_declared_unverified',verification_state:'pending'}]};
 const status={schema_version:'openguard-official-sources/1',binding:{...f.binding},result_id:f.result.result_id,result_sha256:f.result.result_sha256,fetch:{state:'ready',job_id:'job_SYNTHETIC_TEST_ONLY',error_code:null,http_intents:6,http_dispatched:6,http_responses:6},candidate,analysis:{state:'ready',mode:'unadopted_preview',error_code:null,preview,analysis_id:null},adopted_material_ids:[]};
 rt.setFetch(async(url,options={})=>{const row={url:String(url),method:options.method??'GET'};ledger.push(row);if(row.method!=='GET')nonGet.push(row);if(row.method==='GET'&&new URL(row.url,'http://SYNTHETIC.invalid').pathname.endsWith('/official-sources'))return Response.json(status);unknown.push(row);throw Error('Closed transport: unknown request');});
 const render=value=>{const module={exports:{}},source=fs.readFileSync(new URL('../src/components/OfficialSources.tsx',import.meta.url),'utf8'),code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;vm.runInNewContext(code,{module,exports:module.exports,require:name=>name==='react'||name==='react/jsx-runtime'?require(name):name.endsWith('.css')?{}:rt.load(name.replace(/^\.\.\//,'')+'.ts')});return renderToStaticMarkup(module.exports.OfficialAnalysisPreview({preview:value,usage:f.result.usage}));};
 return{rt,service,ai,f,status,preview,context,plan,render,ledger,nonGet,unknown};
}
const noWrites=x=>{assert.equal(x.nonGet.length,0);assert.equal(x.unknown.length,0);};

test('SYNTHETIC_TEST_ONLY structured actions bind current usage, exact Git source and separate scope gaps',async()=>{
 const x=setup(),before=JSON.stringify(x.f.result),value=await x.service.readOfficialSources(x.f.assessment,x.f.result);
 assert.equal(value.analysis.preview.validation_details.status,'validated');assert.equal(value.analysis.preview.actions[1].source_candidate_ids.length,0);assert.equal(JSON.stringify(x.f.result),before);assert.equal(x.ledger.length,1);noWrites(x);
 const html=x.render(value.analysis.preview);assert.match(html,/Qwen选取依据，系统核对后整理/);assert.match(html,/data-license-condition-basis/);assert.equal((html.match(/data-usage-gap-basis=/g)??[]).length,2);assert.doesNotMatch(html,/待人工复核预览|data-original-model-action|data-model-action-warning/);for(const row of html.match(/<li data-bound-action-kind="CHECK_(?:TRAINING|ASSET)_SCOPE"[\s\S]*?<\/li>/g)??[])assert.doesNotMatch(row,/<blockquote|data-license-condition-basis/);noWrites(x);
});
for(const[label,change]of[
 ['wrong current usage',p=>p.validation_details.context.usage.distributed=true],
 ['wrong current Result',p=>p.validation_details.context.result_id='p2res_FOREIGN'],
 ['wrong usage Binding',p=>p.validation_details.context.binding.usage_hash='9'.repeat(64)],
 ['wrong resource version',p=>p.validation_details.context.subject.version='99.0.0'],
 ['another existing resource cannot borrow the target source',p=>{p.validation_details.context.subject={resource_id:'cmp_10000000-0000-4000-8000-000000000002',version:'4.5.6'};p.validation_details.context.targets[0].subject={...p.validation_details.context.subject};}],
 ['wrong source hash',p=>p.validation_details.context.quote_catalog[0].source_sha256='9'.repeat(64)],
 ['cross-object target',p=>p.validation_details.context.targets[0].subject.resource_id='cmp_FOREIGN'],
 ['gap disguised as Git citation',p=>p.actions[1].source_candidate_ids=['p2src_SYNTHETIC_TEST_ONLY']],
 ['licence action without quote',p=>p.actions[0].basis_ids=['gap_training_scope_unobserved']],
 ['false delivery prose with valid tags',p=>p.actions[0].text='对照已交付文件清单保留声明。'],
 ['substituted generic prose',p=>p.actions[1].text='所有训练输入均获准使用。'],
 ['unchecked action selector',p=>p.plan.actions[0].kind='CHECK_PLANNED_COMPONENT_DELIVERY'],
 ['wrong quote role',p=>{p.plan.clauses[0].category='disclaimer';p.clauses[0].category='disclaimer';}],
 ['raw v1 relabelled v2',p=>{delete p.plan;}],
 ['more than one correction',p=>p.model_calls=3],
])test('structured protocol rejects '+label,()=>{const x=setup(),status=clone(x.status);change(status.analysis.preview);assert.throws(()=>x.service.validateOfficialSources(status,x.f.assessment,x.f.result));noWrites(x);});

test('context and exact model selection hashes are rechecked on GET, not accepted from protocol labels',async()=>{
 for(const field of ['context_sha256','selection_sha256']){const x=setup();x.preview.validation_details[field]='9'.repeat(64);if(field==='context_sha256')x.preview.validation_details.context.context_sha256='9'.repeat(64);await assert.rejects(x.service.readOfficialSources(x.f.assessment,x.f.result));noWrites(x);}
});
test('a single validated correction may report two model calls without weakening legacy limits',()=>{const x=setup();x.preview.model_calls=2;x.preview.validation_details.corrective_attempt_used=true;x.preview.validation_details.attempt_count=2;assert.equal(x.service.validateOfficialSources(x.status,x.f.assessment,x.f.result).analysis.preview.model_calls,2);noWrites(x);});
test('legacy free text stays historical review content and cannot be relabelled as validated plan',()=>{
 const x=setup(),legacy=clone(x.preview);delete legacy.analysis_protocol;delete legacy.validation_details;delete legacy.plan;delete legacy.attempts;
 legacy.actions=[{text:'SYNTHETIC_TEST_ONLY：对照已交付文件清单检查声明。',source_candidate_ids:[x.status.candidate.candidate_id],claim_level:'verification_action_only'}];
 const status=clone(x.status);status.analysis.preview=legacy;assert.equal(x.service.validateOfficialSources(status,x.f.assessment,x.f.result).analysis.preview.status,'succeeded');const html=x.render(legacy);assert.match(html,/待人工复核预览/);assert.match(html,/data-original-model-action/);assert.match(html,/当前用途未声明向他人交付/);assert.doesNotMatch(html,/data-bound-action-plan/);noWrites(x);
});
test('failed structured analysis renders no replacement success or action text',()=>{const x=setup(),failed=clone(x.preview);failed.status='failed';failed.actions=[];failed.clauses=[];assert.equal(x.render(failed),'');noWrites(x);});

test('saved Material analysis uses the same strict v2 plan but scope-gap actions cite no Material',async()=>{
 const x=setup(),mid='mat_SYNTHETIC_TEST_ONLY',p=clone(x.preview),subject={...x.f.result.resources[0].subject};
 x.f.result.material_ids=[mid];x.f.result.resources[0].material_ids=[mid];
 p.validation_details.context.quote_catalog[0].material_id=mid;p.validation_details.context.quote_catalog[0].source_level='user_supplied_unverified';
 const {context_sha256,...context}=p.validation_details.context;p.validation_details.context.context_sha256=digest(context);p.validation_details.context_sha256=digest(context);
 const value={...p,schema_version:'openguard-p2-ai-analysis/1',analysis_id:'p2ai_SYNTHETIC_TEST_ONLY',analysis_sha256:'1'.repeat(64),result_revision:x.f.result.revision,idempotency_key:'SYNTHETIC_TEST_ONLY_request',input_sha256:'7'.repeat(64),error_code:null,previous_result_id:null,previous_result_sha256:null,formal_effect:'none',usage_assumption:'DEMO_USAGE_ASSUMPTION',data_scope:'TEST_ONLY',quote_index_unit:'unicode_code_point',model:{...p.model,prompt_version:'p2-bound-action-plan/8'},metrics:{elapsed_ms:1,prompt_eval_count:1,eval_count:1,total_duration:1},source_refs:[{material_id:mid,subject,source_sha256:x.service.fixedLicenseHash,byte_count:1124,source_level:'user_supplied_unverified',verification_state:'pending'}],clauses:p.clauses.map(({source_candidate_id,...q})=>({...q,material_id:mid})),actions:p.actions.map(({source_candidate_ids,...a})=>({...a,source_material_ids:source_candidate_ids.length?[mid]:[]}))};
 assert.equal(x.ai.validateAiAnalysis(value,x.f.assessment,x.f.result).actions[1].source_material_ids.length,0);await x.ai.verifyBoundPlanHashes(value);
 const bad=clone(value);bad.actions[1].source_material_ids=[mid];assert.throws(()=>x.ai.validateAiAnalysis(bad,x.f.assessment,x.f.result));
 noWrites(x);
});

test('unknown route and non-GET are retained by independent ledgers even when a caller catches errors',async()=>{
 const x=setup();for(const options of [{method:'POST'},{method:'GET'}])await assert.rejects(x.rt.shared.fetch('/SYNTHETIC_UNKNOWN',options));assert.equal(x.ledger.length,2);assert.equal(x.nonGet.length,1);assert.equal(x.unknown.length,2);
});

test('exception text separates one rejected correction from uncertain runtime and routine scope gaps',()=>{
 const x=setup(),correction=x.service.officialAnalysisFailureMessage('p2_ai_output_rejected',true),timeout=x.service.officialAnalysisFailureMessage('p2_ai_model_unavailable'),budget=x.service.officialAnalysisFailureMessage('p2_ai_budget_exhausted');
 assert.match(correction,/一次定向纠错后/);assert.match(correction,/只需核对这次异常/);assert.match(timeout,/不会自动重新生成/);assert.match(budget,/不会自动追加额度/);assert.equal(x.service.officialAnalysisFailureMessage(null),null);noWrites(x);
 assert.match(x.service.officialAnalysisFailureMessage('p2_ai_output_rejected',true,[{code:'plan_change_kind'}]),/用途变更分类未通过校验；本次结果未展示，原记录保留/);
});

test('v2 keeps the legacy free-text limitation only in immutable trace, while real source boundaries remain visible',()=>{
 const x=setup(),old='结构与已知错误模式检查不保证行动完整或语义正确，内容仍需人工复核。';
 x.preview.limitations=[old,'SYNTHETIC_TEST_ONLY：固定Git LICENSE不能证明npm发行包、正式许可适用或履约。'];
 const before=JSON.stringify(x.preview),html=x.render(x.preview),visible=html.replace(/<pre>[\s\S]*?<\/pre>/g,'');
 assert.match(html,/stored_limitations/);assert.ok(html.includes(old));assert.ok(!visible.includes(old));assert.match(visible,/已核对结构化用途、准确对象和行动依据/);assert.match(visible,/固定Git LICENSE不能证明npm发行包、正式许可适用或履约/);assert.doesNotMatch(visible,/内容仍需人工复核/);assert.equal(JSON.stringify(x.preview),before);noWrites(x);
});

test('legacy free-text limitation stays unchanged on the legacy model presentation',()=>{
 const x=setup(),old='结构与已知错误模式检查不保证行动完整或语义正确，内容仍需人工复核。',legacy=clone(x.preview);
 delete legacy.analysis_protocol;delete legacy.validation_details;delete legacy.plan;legacy.limitations=[old];
 const html=x.render(legacy).replace(/<pre>[\s\S]*?<\/pre>/g,'');assert.ok(html.includes(old));assert.match(html,/待人工复核预览/);assert.doesNotMatch(html,/data-current-plan-assurance/);noWrites(x);
});
