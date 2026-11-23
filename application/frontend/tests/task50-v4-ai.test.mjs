import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { runtime } from './runtime.mjs';

function setup() {
  const rt = runtime({ VITE_P2_AI_ANALYSIS: '1' });
  Object.assign(rt.shared, { structuredClone, TextEncoder, TextDecoder });
  const api = rt.load('services/p2Ai.ts');
  const { fixture, record } = rt.load('../tests/p2-ai-analysis/fixture.ts');
  return { rt, api, f: fixture('v4'), record };
}

test('TASK50 explicit v3 subject can request r1 with no uploaded materials', () => {
  const { api, f } = setup();
  f.result.material_ids = [];
  f.result.resources[0].material_ids = [];
  const subject = { ...f.result.resources[0].subject };
  const body = api.prepareAiAnalysis(f.assessment, f.result, [], false, subject);
  assert.deepEqual(structuredClone(body.subject), subject);
  assert.deepEqual(structuredClone(body.material_ids), []);
  assert.throws(() => api.prepareAiAnalysis(f.assessment, f.result, [], false));
});

test('TASK50 v3 request cannot cite a material owned by another saved subject', () => {
  const { api, f } = setup();
  const subject = { ...f.result.resources[0].subject, resource_id: 'cmp_other_saved' };
  f.result.resources.push({ ...f.result.resources[0], subject, material_ids: [] });
  assert.throws(() => api.prepareAiAnalysis(f.assessment, f.result, f.result.material_ids, false, subject));
});

test('TASK50 opt-in capability is read from exact result index, legacy index shape still works', async () => {
  const { rt, api, f } = setup();
  let enabled;
  const read = (index) => {
    rt.setFetch(async () => Response.json({ result_id: f.result.result_id, analysis_ids: [], ...index }));
    return api.readAiIndex(f.assessment, f.result, undefined, (value) => { enabled = value; });
  };
  assert.deepEqual(structuredClone(await read({ v4_plan_enabled: true })), []);
  assert.equal(enabled, true);
  assert.deepEqual(structuredClone(await read({})), []);
  assert.equal(enabled, false);
});

test('TASK50 incomplete v3 output cannot fall back to a legacy free text envelope', () => {
  const { api, f, record } = setup();
  const forged = { ...record(f.result), analysis_protocol: 'openguard-qwen-v4-plan/3' };
  assert.throws(() => api.validateAiAnalysis(forged, f.assessment, f.result));
});

const protocol = 'openguard-qwen-v4-plan/3';
const prompt = 'p2-v4-structured-plan/1';
const sha = (text) => createHash('sha256').update(text).digest('hex');
const canonical = (value) => Array.isArray(value) ? '[' + value.map(canonical).join(',') + ']'
  : value && typeof value === 'object' ? '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}'
  : JSON.stringify(value);
const sorted = (values) => [...values].sort();
const viewId = 'v4_view_current';
const scanId = 'scn_11111111-1111-4111-8111-111111111111';
const origins = 'PROGRAM_RENDERED_FROM_QWEN_STRUCTURED_SELECTION';
const uses = ['commercial', 'distributed', 'modified'];
const requiredReason = (usage) => usage === 'modified' ? ['USE_NOT_SELECTED'] : usage === 'distributed'
  ? ['USAGE_UNDECLARED'] : ['MISSING_LICENSE_MATERIAL'];
const stateOf = (usage) => usage === 'modified' ? 'NOT_COVERED' : 'UNKNOWN';

function stamps(record) {
  record.context_sha256 = sha(canonical(record.context));
  record.plan_input_sha256 = sha(canonical({ analysis_protocol: protocol, context: record.context,
    context_sha256: record.context_sha256 }));
  record.selection_sha256 = record.plan === null ? null : sha(canonical(record.plan));
}

function scenario({ incremental = false, failed = false } = {}) {
  const { rt, api, f, record } = setup();
  const saved = f.result;
  const subject = structuredClone(saved.resources[0].subject);
  const install = 'SYNTHETIC_TEST_ONLY_Python';
  const label = install + '@' + subject.version;
  const sourceSha = '4'.repeat(64), evidenceId = 'evd_task50_observed';
  const materialId = 'mat_task50_bytes';
  const rawPart = '核验原文'.repeat(31) + '边界';
  const parts = ['版权所有', rawPart, '保留条件', '免责'];
  const rawMaterial = parts.join('\n');
  const evidence = [{ evidence_id:evidenceId, source_sha256:sourceSha }];
  const quotePrefix = '核验原文'.repeat(25);

  f.assessment.scan_id = scanId;
  saved.binding = { ...saved.binding, scan_id: scanId };
  const binding = saved.binding;
  saved.usage = { ...saved.usage, commercial: true, distributed: null, modified: false,
    network_service:false, training:false, redistributed_assets:false, source_disclosure:false };
  saved.revision = incremental ? 2 : 1;
  saved.previous_result_id = incremental ? 'p2res_v4_old' : null;
  saved.material_ids = incremental ? [materialId] : [];
  saved.answer_ids = [];
  saved.recomputed_resource_ids = [subject.resource_id];
  saved.reused_resource_ids = [];
  saved.resources = [{ ...saved.resources[0], subject, resource_kind:'component',
    material_ids:[...saved.material_ids], answer_ids:[], evidence_ids:[evidenceId], evidence_source_hashes:{ [evidenceId]:sourceSha } }];
  f.scan.id = scanId;
  f.scan.resources = [{ id:subject.resource_id, name:install, version:subject.version, ecosystem:'pypi', type:'Package' }];
  f.scan.declarationSnapshot = { scan_id:scanId, project_revision:binding.project_revision,
    resources:[{ ...subject, expression:'MIT', normalized_ids:['MIT'], resource_evidence_ids:[evidenceId],
      declaration_evidence_ids:[evidenceId], evidence, license_expression_id:'lic_synthetic' }] };
  const adviceReason = (usage) => incremental && usage==='commercial' ? ['SOURCE_OR_EVIDENCE_BINDING_NOT_ESTABLISHED'] : requiredReason(usage);
  const materialSha = sha(rawMaterial);
  const clauses = parts.map((quote, i)=>{
    const byte_start = Buffer.byteLength(parts.slice(0,i).map(part => part+'\n').join(''));
    return { clause_id:'clause_'+i, material_id:materialId, material_sha256:materialSha,
      kind:['copyright','permission','condition','warranty'][i], byte_start,
      byte_end:byte_start+Buffer.byteLength(quote), line_start:i+1, line_end:i+1, quote, quote_sha256:sha(quote) };
  });
  const claims = uses.map(usage=>({ claim_id:'claim_'+usage, usage, subject, material_ids:[...saved.material_ids], evidence,
    clause_ids:incremental?clauses.map(clause=>clause.clause_id):[], conditions:[], counter_evidence:[], state:stateOf(usage), formal_effect:'none' }));
  const advice = claims.map(claim=>({ usage:claim.usage, subject, saved_value:saved.usage[claim.usage], state:claim.state,
    reasons:adviceReason(claim.usage), claim_ids:[claim.claim_id], conditions:[], limitations:['仅核验'] }));
  const delta = { usage:'commercial', subject, previous_claim_id:'claim_old', current_claim_id:'claim_commercial',
    previous_state:'UNKNOWN', current_state:'UNKNOWN', previous_reasons:requiredReason('commercial'),
    current_reasons:adviceReason('commercial'), trigger_material_ids:[materialId], trigger_answer_ids:[] };
  const view = {
    schema_version:'openguard-material-claims/4', rule_version:'mit-apache2-bound-claim/4', view_id:viewId,
    result_id:saved.result_id, result_sha256:saved.result_sha256, revision:saved.revision, previous_result_id:saved.previous_result_id,
    binding, data_scope:'TEST_ONLY', source_status:'NOT_CONFIGURED', source_profile_sha256:null,
    materials:incremental?[{ material_id:materialId, subject, source_sha256:materialSha, byte_count:Buffer.byteLength(rawMaterial),
      filename:'LICENSE', parse_state:'MATCHED_MIT', parse_reason:'COMPLETE_EXISTING_MIT_PROFILE', binding_state:'BOUND_TO_SAVED_RESULT',
      adoption_state:'OBSERVATION_ONLY', declared_spdx:'MIT', text_license:'MIT', license_version:null,
      version_scope:'RESOURCE_VERSION_NOT_LICENSE_VERSION', role:'unknown', role_state:'unknown', role_basis_evidence_ids:[],
      role_conflicts:[], source_binding:'NOT_ESTABLISHED', source_profile_sha256:null, evidence, clauses }]:[],
    declaration_observations:[{ subject, expression:'MIT', normalized_ids:['MIT'], declaration_evidence_ids:[evidenceId],
      evidence, evidence_status:'COMPLETE' }],
    source_observations:[], claims, advice,
    incremental_impact:{ mode:incremental?'INCREMENTAL_DERIVED':'INITIAL_RESULT',
      previous_result_id:saved.previous_result_id, previous_revision:incremental?1:null,
      previous_view_id:incremental?'view_v4_old':null, affected_resource_ids:[subject.resource_id], unchanged_resource_ids:[],
      recomputed_claim_ids:claims.map(claim=>claim.claim_id), reused_claim_ids:[], added_material_ids:[...saved.material_ids],
      added_answer_ids:[], changed_claims:incremental?[delta]:[], unchanged_claims_verified:true },
    formal_effect:'none', applicability_review:'NOT_SIGNED', model_calls:0,
  };
  const context = {
    protocol:'openguard-action-plan/3', material_claims_view_id:viewId, result_id:saved.result_id,
    result_sha256:saved.result_sha256, result_revision:saved.revision, previous_result_id:saved.previous_result_id,
    binding, subject:{ ...subject, component_name:install, ecosystem:'pypi' }, usage:saved.usage, declared_spdx:'MIT',
    claim_states:Object.fromEntries(uses.map(usage=>[usage,stateOf(usage)])),
    advice_reasons:Object.fromEntries(uses.map(usage=>[usage,adviceReason(usage)])),
    counter_evidence_codes:[], source_binding:'NOT_ESTABLISHED', notice_status:null,
    incremental_impact_summary:{mode:view.incremental_impact.mode,changed_claims:view.incremental_impact.changed_claims},
    dependency_conflicts:null, material_ids:[...saved.material_ids],
    quote_catalog:incremental?clauses.map((clause,i)=>{
      const quote=i===1?quotePrefix:clause.quote;
      const byte_end=clause.byte_start+Buffer.byteLength(quote);
      return {quote_id:'p2quote_'+sha(canonical([materialId,clause.clause_id,clause.kind,clause.byte_start,byte_end])),
        material_id:materialId,clause_id:clause.clause_id,kind:clause.kind,quote,quote_sha256:sha(quote),byte_start:clause.byte_start,byte_end};
    }):[],
    action_catalog:[
      ...(!incremental?[{action_kind:'SUPPLY_MISSING_LICENSE_MATERIAL', basis_ids:sorted(claims.map(claim=>claim.claim_id)),required:true}]:[]),
      {action_kind:'VERIFY_UNESTABLISHED_RELEASE_SOURCE',basis_ids:sorted(claims.map(claim=>claim.claim_id)),required:false},
      {action_kind:'CONFIRM_UNKNOWN_USAGE_FIELD',basis_ids:['usage:distributed'],required:false},
    ],
  };
  const { action_kind, basis_ids } = context.action_catalog[0];
  const actions = [{
    action_kind,basis_ids,text:incremental?'核对 '+label+' 的发行记录、材料原文与精确版本的对应关系。':'补充 '+label+' 对应版本的许可证原文及来源记录。',
  }];
  const selectedQuotes=incremental?[context.quote_catalog[1]]:[];
  const plan = { analysis_protocol:protocol, prompt_version:prompt,
    selected_quotes:selectedQuotes.map(q=>({quote_id:q.quote_id,category:q.kind})),
    selected_actions:[{action_kind,basis_ids}],selected_change_indices:incremental?[0]:[] };
  const data = { ...record(saved), analysis_protocol:protocol, quote_index_unit:'utf8_byte', context,
    material_claims_view_id:viewId, display_origin:origins, model_calls:1,
    status:failed?'failed':'succeeded', error_code:failed?'p2_ai_output_rejected':null,
    source_refs:incremental?[{material_id:materialId,subject,source_sha256:materialSha,byte_count:Buffer.byteLength(rawMaterial),
      source_level:'user_supplied_unverified',verification_state:'pending'}]:[],
    plan:failed?null:plan, actions:failed?[]:actions, clauses:failed?[]:selectedQuotes,
    changes:incremental&&!failed?[{index:0,explanation:label+' 的商业使用研判由 UNKNOWN 变为 UNKNOWN。核对本次变动的材料与证据。'}]:[],
  };
  data.model.prompt_version = prompt;
  stamps(data);
  const dependencyPage = { schema_version:'openguard-dependency-evidence/1',
    scan_ref:{scan_id:scanId,revision:binding.project_revision,facts_hash:binding.facts_hash,input_hash:'7'.repeat(64),
      inventory_hash:null,status:'completed',registry_revision:binding.registry_revision},
    source:null,limit:100,total:0,returned:0,next_cursor:null,coverage:'unknown',incomplete:false,items:[] };
  const ledger=[];
  const read = (value = data, scan = f.scan) => {
    rt.setFetch(async (url, options) => {
      assert.equal(options.method??'GET','GET');
      ledger.push(url);
      if(url.includes('/material-claims?')) return Response.json(view);
      if(url.includes('/dependency-evidence?')) return Response.json(dependencyPage);
      if(url.includes('/ai-analyses/')) return Response.json(value);
      throw Error('unexpected test request: '+url);
    });
    return api.readAiAnalysis(f.assessment,saved,value.analysis_id,undefined,scan);
  };
  return { api, f, saved, data, read, ledger, view, dependencyPage, rawPart };
}

test('TASK50 uses independently fetched v4 and dependency views for empty-material r1', async () => {
  const { data, read, ledger } = scenario();
  const response = await read();
  assert.equal(response.plan_input_sha256,data.plan_input_sha256);
  assert.equal(response.clauses.length,0);
  assert.equal(response.actions[0].action_kind,'SUPPLY_MISSING_LICENSE_MATERIAL');
  assert.equal(ledger.length,3);
});

test('TASK50 verifies a bounded UTF-8 quote and a fixed r1 to r2 delta from actual v4 shapes', async () => {
  const { read, rawPart } = scenario({incremental:true});
  const response = await read();
  const [excerpt] = response.clauses;
  assert.equal(Buffer.byteLength(excerpt.quote),300);
  assert.ok(rawPart.startsWith(excerpt.quote));
  assert.equal(response.changes[0].index,0);
});

test('TASK50 failed v3 receipt reads exact prior evidence with no replacement text', async () => {
  const response = await scenario({failed:true}).read();
  assert.equal(response.status,'failed');
  assert.equal(response.error_code,'p2_ai_output_rejected');
  assert.equal(response.actions.length,0);
  assert.equal(response.plan,null);
});

for(const [label,tamper] of [
  ['changed context digest',value=>{ value.context_sha256='9'.repeat(64); }],
  ['changed selection digest',value=>{ value.selection_sha256='9'.repeat(64); }],
  ['changed model input digest',value=>{ value.plan_input_sha256='9'.repeat(64); }],
  ['non-deterministic action text',value=>{ value.actions[0].text='已经取得许可。'; }],
  ['fabricated fresh view with recomputed hashes',value=>{
    value.material_claims_view_id=value.context.material_claims_view_id='p4view_forged'; stamps(value);
  }],
  ['fabricated source scope with recomputed hashes',value=>{
    value.context.source_binding='PINNED_RELEASE_MATCH'; stamps(value);
  }],
  ['forged dependency conflicts with recomputed hashes',value=>{
    value.context.dependency_conflicts={resource_id:value.context.subject.resource_id,version:value.context.subject.version,
      gaps:['version_unavailable'],conflicts:[]}; stamps(value);
  }],
  ['removed required action',value=>{
    value.context.action_catalog[0].required=false;
    const {action_kind,basis_ids}=value.context.action_catalog[1];
    value.plan.selected_actions=[{action_kind,basis_ids}];
    value.actions=[{action_kind,basis_ids,text:'核对 '+value.context.subject.component_name+'@'+value.context.subject.version+' 的发行记录、材料原文与精确版本的对应关系。'}];
    stamps(value);
  }],
  ['forged permissive action on UNKNOWN',value=>{
    const action_kind='VERIFY_PERMISSIVE_OBLIGATIONS',basis_ids=['claim_commercial'];
    value.context.action_catalog.push({action_kind,basis_ids,required:false});
    value.plan.selected_actions.push({action_kind,basis_ids});
    value.actions.push({action_kind,basis_ids,text:'核对 '+value.context.subject.component_name+'@'+value.context.subject.version+' 的拟交付文件是否保留版权声明及许可文本。'});
    stamps(value);
  }],
])test('TASK50 rejects '+label,async()=>{
  const { read,data }=scenario();
  await read();
  tamper(data);
  await assert.rejects(read(data));
});

test('TASK50 rejects recomputed quote offsets or selected change indices outside exact source',async()=>{
  const { read,data }=scenario({incremental:true});
  await read();
  const shifted=structuredClone(data);
  shifted.clauses[0].byte_start-=1;
  shifted.clauses[0].byte_end-=1;
  const item=shifted.context.quote_catalog.find(q=>q.quote_id===shifted.clauses[0].quote_id);
  Object.assign(item,shifted.clauses[0]);
  stamps(shifted);
  await assert.rejects(read(shifted));
  data.plan.selected_change_indices=[99];
  stamps(data);
  await assert.rejects(read(data));
});
