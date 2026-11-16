#!/usr/bin/env node
// Generate the deterministic P1 integration fixture package (Node stdlib only).
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../../..');
const BASE = '23fae26485db2fe3449ec8e7cccc3af64a487002';
const TARGET = 'e2d8c016ef5f4cfcddd23abb0205ec41c7cf3db1';
const NOW = '2026-09-21T14:30:00Z';
const PROJECT = 'github.com/mumingce-star/OpenGuard';
const GENERATED = ['scans.json','assessment.json','remediation-input.json','remediation-task.json','graph-100.json','graph-300.json','graph-500.json','history.json','report-v2-input.json'];

const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const digest = value => crypto.createHash('sha256').update(JSON.stringify(stable(value))).digest('hex');
const fileDigest = name => crypto.createHash('sha256').update(fs.readFileSync(name)).digest('hex');
const dump = (name, value) => fs.writeFileSync(name, JSON.stringify(value, null, 2) + '\n', 'utf8');
const scanRef = scan => Object.fromEntries(['scan_id','revision','facts_hash','input_hash','inventory_hash','status','registry_revision'].map(key => [key, scan[key]]));
const assessmentRef = a => ({assessment_id:a.id,version:a.version,scan_id:a.scan_id,facts_hash:a.facts_hash,usage_hash:a.usage_hash,rule_version:a.rule_version,formal:a.formal});
const provenance = (scan, assessment, algorithm, parameters) => ({
  producer:{name:'openguard-p1-integration-fixture',version:'1.0.0'}, source_refs:[scanRef(scan)],
  assessment_refs:assessment?[assessmentRef(assessment)]:[], generated_at:NOW,
  algorithm_version:algorithm, parameters_hash:digest(parameters),
});

function makeScans() {
  return [{
    scan_id:'scn-p1-fixed-base-partial', revision:BASE,
    facts_hash:digest({commit:BASE,scope:'resource-profile',status:'partial'}),
    input_hash:digest({project:PROJECT,commit:BASE}), inventory_hash:digest({commit:BASE,inventory:'profile-only'}),
    status:'partial', registry_revision:1, coverage_gaps:['NOTICE facts were not present at this revision'],
  },{
    scan_id:'scn-p1-fixed-target-completed', revision:TARGET,
    facts_hash:digest({commit:TARGET,sources:['resource-profile-v1','notice-license-facts-v1']}),
    input_hash:digest({project:PROJECT,commit:TARGET}), inventory_hash:digest({commit:TARGET,inventory:'profile-and-notice'}),
    status:'completed', registry_revision:2, coverage_gaps:[],
    findings:[{id:'finding.root.notice-missing',status:'review_required',severity:'medium',code:'GAP_ROOT_NOTICE_MISSING',resource_id:'cmp-openguard-root',
      message:'根项目未观察到 NOTICE 文件；不得据此推定无需 NOTICE。',evidence_ids:['ev.root.license'],source_fact_pointer:'/facts/0/relationships/notice'}],
  }];
}

function makeAssessment(completed) {
  const obligation = {
    id:'obl-p1-apache-notice-review', action:'retain_license_and_notice',
    requirement:'Review retention of the license and applicable NOTICE content, and document material modifications where required.',
    trigger:'Verified Apache-2.0 material is redistributed or modified', fulfillment:'pending',
    resource_ids:['cmp-jackson-databind'], evidence_ids:['ev.jackson.license','ev.jackson.notice'],
    rule_id:'LIC-APACHE-2.0-NOTICE', rule_version:'1.0.0',
  };
  const usage = {preset:'unknown',commercial:null,modified:null,distributed:null,network_service:null,training:null,redistributed_assets:null,source_disclosure:null,declared_at:NOW};
  const usageHash = digest(Object.fromEntries(Object.entries(usage).filter(([key]) => key !== 'declared_at')));
  return {
    schema_version:'1.0', id:'asm-p1-fixed-notice-review', version:1, scan_id:completed.scan_id,
    project_name:'OpenGuard', revision:TARGET, input_hash:completed.input_hash, facts_hash:completed.facts_hash,
    usage_hash:usageHash, cache_key:digest([completed.scan_id,completed.facts_hash,usageHash,'assessment-1.0-facts2:2026.09.2']),
    generated_at:NOW, usage, rule_version:'assessment-1.0-facts2:2026.09.2', model_version:'none',
    prompt_version:'assessment-1.0', formal:true, scan_status:'completed', ai_status:'not_requested', ai_summary:null, ai_evidence_ids:[],
    summary:'观察到根项目 NOTICE 缺口；Apache NOTICE 规则仅形成待人工确认的候选义务，不构成许可证结论。',
    dimensions:[{id:'redistribution',title:'公开发布与再分发',status:'unknown',conclusion:'证据不足，暂无法判断',conditions:[],restrictions:[],
      unknowns:['根项目 NOTICE 与版权主体来源缺失','用途与分发形态未声明'],resource_ids:['cmp-openguard-root','cmp-jackson-databind'],
      finding_ids:['finding.root.notice-missing'],evidence_ids:['ev.root.license','ev.jackson.license','ev.jackson.notice'],strength:'insufficient'}],
    resource_evaluations:[
      {resource_id:'cmp-openguard-root',resource_kind:'component',name:'OpenGuard',version:TARGET,scope:'project_code',scope_evidence_ids:[],
       license_expression:null,license_verified:false,supported_permission:false,finding_ids:['finding.root.notice-missing'],evidence_ids:['ev.root.license'],
       locators:['LICENSE'],conditions:[],restrictions:{},gaps:['GAP_ROOT_NOTICE_MISSING','GAP_ROOT_COPYRIGHT_SOURCE_MISSING'],next_steps:['人工补齐根项目 NOTICE 与版权来源证据']},
      {resource_id:'cmp-jackson-databind',resource_kind:'component',name:'Jackson Databind',version:'2.21.5',scope:'runtime_dependency',scope_evidence_ids:[],
       license_expression:null,license_verified:false,supported_permission:false,finding_ids:[],evidence_ids:['ev.jackson.license','ev.jackson.notice'],
       locators:['com.fasterxml.jackson.core:jackson-databind:2.21.5!/META-INF/LICENSE','com.fasterxml.jackson.core:jackson-databind:2.21.5!/META-INF/NOTICE'],
       conditions:[],restrictions:{},gaps:['正式许可证表达式与适用性仍待人工复核'],next_steps:['人工核对分发形态与 NOTICE 处理']},
    ],
    obligations:[obligation], coverage_issues:['GAP_ROOT_NOTICE_MISSING','GAP_ROOT_COPYRIGHT_SOURCE_MISSING'],
    resource_ids:['cmp-openguard-root','cmp-jackson-databind'], finding_ids:['finding.root.notice-missing'],
    evidence_ids:['ev.root.license','ev.jackson.license','ev.jackson.notice'], license_ids:[], remediation_ids:[],
    rule_sources:['rules/license-obligations.yaml#/rules/1'],
  };
}

function makeTask(completed, assessment) {
  const obligation = assessment.obligations[0];
  return {schema_version:'1.0',task_id:'task-p1-review-notice',scan_id:completed.scan_id,assessment_ref:assessmentRef(assessment),
    origin:{kind:'obligation',source_pointer:'/obligations/0',source_hash:digest(obligation)},resource_ids:obligation.resource_ids,
    evidence_refs:obligation.evidence_ids.map(evidence_id => ({namespace:'scan',scan_id:completed.scan_id,evidence_id})),
    title:'人工复核 Apache 许可证与 NOTICE 分发材料',status:'todo',note:'',version:1,superseded:false,created_at:NOW,updated_at:NOW,
    provenance:provenance(completed,assessment,'remediation-derive/1',{source_pointer:'/obligations/0'})};
}

function makeRemediationInput(completed, assessment, task) {
  return {schema_version:'openguard.p1-remediation-upstream-input/1',status:'fixed_upstream_input',
    endpoint_template:'/api/v1/scans/{scan_id}/assessments/{assessment_id}/remediation-tasks/derive',
    binding:{scan_ref:scanRef(completed),assessment_ref:assessmentRef(assessment)},
    derive_request:{idempotency_key:'p1-fixed-notice-review-v1',expected_facts_hash:completed.facts_hash},
    eligible_origins:[{kind:'obligation',source_pointer:'/obligations/0',source_hash:task.origin.source_hash,
      obligation_id:assessment.obligations[0].id,rule_id:assessment.obligations[0].rule_id}],
    expected_task_ref:{task_id:task.task_id,version:task.version,status:task.status}};
}

function makeGraph(size, completed, assessment) {
  const special = [
    ['node-project','project','openguard','OpenGuard'],['node-root-license','license_observation','fact.root.openguard','根 LICENSE 标题观察'],
    ['node-root-evidence','evidence','ev.root.license','LICENSE 字节证据'],['node-root-finding','finding','finding.root.notice-missing','根 NOTICE 缺口'],
    ['node-obligation','obligation','obl-p1-apache-notice-review','Apache NOTICE 待复核义务'],['node-jackson','component','cmp-jackson-databind','Jackson Databind 2.21.5'],
    ['node-jackson-license','license_observation','fact.dep.jackson-databind','Jackson LICENSE 观察'],['node-jackson-notice','evidence','ev.jackson.notice','Jackson NOTICE 证据'],
    ['node-bert','ai_asset','huggingface:model:google-bert/bert-base-uncased','BERT 固定快照'],['node-bert-license','license_observation','fact.ai.bert','BERT provider 声明'],
    ['node-bert-evidence','evidence','ev.hf.bert.license','BERT provider snapshot'],
  ];
  const nodes = special.map(([id,kind,source_id,label]) => ({id,kind,source_id,label}));
  for (let i=0;i<size-special.length;i++) nodes.push({id:`node-component-${String(i).padStart(4,'0')}`,kind:'component',source_id:`cmp-fixed-${String(i).padStart(4,'0')}`,label:`固定组件 ${String(i).padStart(4,'0')}`});
  const links = [
    ['RESOURCE_HAS_LICENSE_OBSERVATION','node-project','node-root-license','/licenses/root'],['RESOURCE_SUPPORTED_BY_EVIDENCE','node-project','node-root-evidence','/evidence/ev.root.license'],
    ['RESOURCE_HAS_FINDING','node-project','node-root-finding','/findings/0'],['FINDING_SUPPORTED_BY_EVIDENCE','node-root-finding','node-root-evidence','/findings/0/evidence_ids/0'],
    ['FINDING_REFERENCES_OBLIGATION','node-root-finding','node-obligation','/obligations/0'],['LICENSE_HAS_RULE_OBLIGATION','node-root-license','node-obligation','/obligations/0/rule_id'],
    ['PROJECT_HAS_RESOURCE','node-project','node-jackson','/components/0'],['RESOURCE_HAS_LICENSE_OBSERVATION','node-jackson','node-jackson-license','/components/0/license_expression_id'],
    ['RESOURCE_SUPPORTED_BY_EVIDENCE','node-jackson','node-jackson-notice','/components/0/evidence_ids/0'],['PROJECT_HAS_RESOURCE','node-project','node-bert','/ai_assets/0'],
    ['RESOURCE_HAS_LICENSE_OBSERVATION','node-bert','node-bert-license','/ai_assets/0/license_expression_id'],['RESOURCE_SUPPORTED_BY_EVIDENCE','node-bert','node-bert-evidence','/ai_assets/0/evidence_ids/0'],
  ];
  const edges = links.map(([type,source,target,pointer],i) => ({id:`edge-${String(i).padStart(4,'0')}`,type,source,target,source_refs:[{scan_id:completed.scan_id,pointer}]}));
  for (const node of nodes.slice(special.length)) edges.push({id:`edge-${String(edges.length).padStart(4,'0')}`,type:'PROJECT_HAS_RESOURCE',source:'node-project',target:node.id,source_refs:[{scan_id:completed.scan_id,pointer:`/components/${node.source_id}`} ]});
  return {schema_version:'1.0',view_id:`graph-p1-fixed-${size}`,formal:false,scan_ref:scanRef(completed),filter:{resource_ids:[],resource_kinds:[]},nodes,edges,
    coverage:{view_complete:true,scope:'all',node_count:nodes.length,edge_count:edges.length,scan_gaps:[]},capacity:{max_nodes:20000,max_edges:60000},
    provenance:provenance(completed,assessment,'resource-graph/1',{tier:size})};
}

function historyItem(index, partial, completed, assessment) {
  let scan,status,stage,latest=null;
  if (index===0) [scan,status,stage]=[partial,'partial','report'];
  else if (index===1) { [scan,status,stage]=[completed,'completed','completed']; latest=assessmentRef(assessment); }
  else {
    status=index%17===0?'partial':index%31===0?'failed':'completed'; stage=status==='partial'?'report':status==='failed'?'scan':'completed';
    const revision=index%2===0?BASE:TARGET;
    scan={scan_id:`scn-p1-history-${String(index).padStart(3,'0')}`,revision,facts_hash:digest({history:index,commit:revision,status}),
      input_hash:digest({project:PROJECT,commit:revision,history:index}),inventory_hash:digest({history:index,inventory:'fixed'}),status,registry_revision:index+1};
  }
  const created=new Date(Date.parse('2026-09-21T12:00:00Z')-index*3600000); const finding=status==='completed'||status==='partial'?1:0;
  return {schema_version:'1.0',scan_id:scan.scan_id,project_identity:{method:'canonical_github_repo_v1',key:PROJECT,source_project_id:'OpenGuard'},
    source_type:'git',source:'https://github.com/mumingce-star/OpenGuard.git',revision:scan.revision,input_hash:scan.input_hash,inventory_hash:scan.inventory_hash,
    status,stage,created_at:created.toISOString(),finished_at:new Date(created.getTime()+300000).toISOString(),component_count:2,ai_asset_count:1,finding_count:finding,
    summary:{component_count:2,ai_asset_count:1,evidence_count:3,finding_counts:{pass:0,warning:0,review_required:finding,unknown:0}},latest_assessment:latest,
    provenance:provenance(scan,latest?assessment:null,'scan-history/1',{index})};
}

function makeReportInput(completed,assessment,task) {
  return {schema_version:'openguard.p1-report-v2-input/1',status:'draft_input_only',
    binding:{scan_ref:scanRef(completed),assessment_ref:assessmentRef(assessment),task_refs:[{task_id:task.task_id,version:task.version}]},
    resource_profile:{source:'tests/fixtures/huggingface/resource-profile-v1/manifest.json',record_pointer:'/records/1',case_id:'hf-model-bert-base-uncased',
      canonical_id:'google-bert/bert-base-uncased',revision:'86b5e0934494bd15c9632b12f734a8a67f723594',provider:'huggingface',visibility:'public',gated:'ungated',
      declared_license_raw:'apache-2.0',license_expression_id:null,authorization_status:'pending',evidence:{json_pointer:'/payload/cardData/license',source_file_sha256:'dc293e547c6cb125a94305654420a49aa3d930b39bd55309bd8e323b0ce865dc'}},
    notice_license_facts:{source:'tests/fixtures/notice-license-facts-v1/facts.json',selected_fact_pointers:['/facts/0','/facts/1','/facts/3','/facts/4','/facts/6'],
      selected_evidence_ids:['ev.root.license','ev.jackson.license','ev.jackson.notice','ev.hamcrest.license','ev.mockito.license','ev.hf.bert.license'],observed_entries:[
        {category:'root_project',canonical_id:'openguard',license_raw:'Apache License Version 2.0',notice_state:'gap',copyright_state:'gap',gaps:['GAP_ROOT_NOTICE_MISSING','GAP_ROOT_COPYRIGHT_SOURCE_MISSING']},
        {category:'dependency',canonical_id:'pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.21.5',license_raw:'Apache License Version 2.0',notice_state:'observed',copyright_state:'observed',gaps:[]},
        {category:'dependency',canonical_id:'pkg:maven/org.hamcrest/hamcrest@3.0',license_raw:'BSD 3-Clause License',notice_state:'gap',copyright_state:'observed',gaps:['GAP_NOTICE_NOT_PACKAGED']},
        {category:'dependency',canonical_id:'pkg:maven/org.mockito/mockito-core@5.23.0',license_raw:'The MIT License',notice_state:'gap',copyright_state:'observed',gaps:['GAP_NOTICE_NOT_PACKAGED']},
        {category:'ai_resource',canonical_id:'huggingface:model:google-bert/bert-base-uncased',license_raw:'apache-2.0',notice_state:'gap',copyright_state:'gap',gaps:['GAP_AI_NOTICE_NOT_OBSERVED','GAP_AI_COPYRIGHT_NOT_OBSERVED','GAP_AI_LICENSE_TEXT_NOT_VERIFIED']},
      ]},
    policy:{license_expression_autofill:false,unknown_items_are_gaps:true,requires_human_review:true},
    expected_consumer_result:{profile_count:1,notice_fact_count:5,gap_count:7,authorization_statuses:['pending'],report_snapshot_created:false}};
}

function build() {
  const [partial,completed]=makeScans(); const assessment=makeAssessment(completed); const task=makeTask(completed,assessment);
  return {'scans.json':{schema_version:'openguard.p1-fixed-scans/1',project_key:PROJECT,items:[partial,completed]},'assessment.json':assessment,
    'remediation-input.json':makeRemediationInput(completed,assessment,task),'remediation-task.json':task,'graph-100.json':makeGraph(100,completed,assessment),'graph-300.json':makeGraph(300,completed,assessment),
    'graph-500.json':makeGraph(500,completed,assessment),'history.json':{schema_version:'openguard.p1-fixed-history/1',count:205,items:Array.from({length:205},(_,i)=>historyItem(i,partial,completed,assessment))},
    'report-v2-input.json':makeReportInput(completed,assessment,task)};
}
const source = (name,commit,purpose) => {
  const committed=execFileSync('git',['show',`${commit}:${name}`],{cwd:ROOT});
  const commit_blob_sha256=crypto.createHash('sha256').update(committed).digest('hex');
  return {path:name,fixed_commit:commit,sha256:fileDigest(path.join(ROOT,name)),commit_blob_sha256,purpose};
};
function makeManifest() {
  return {schema_version:'openguard.p1-integration-fixture-manifest/1',package_status:'fixed_acceptance_draft_data',generated_at:NOW,
    project:{canonical_id:PROJECT,provider:'github'},revisions:[{role:'base_partial',commit:BASE,scan_id:'scn-p1-fixed-base-partial',expected_status:'partial'},
      {role:'target_completed',commit:TARGET,scan_id:'scn-p1-fixed-target-completed',expected_status:'completed'}],
    sources:[source('tests/fixtures/huggingface/resource-profile-v1/manifest.json',BASE,'Resource Profile facts'),source('tests/fixtures/notice-license-facts-v1/facts.json',TARGET,'NOTICE/license relationship facts'),source('rules/license-obligations.yaml',TARGET,'Finding/Obligation rule source')],
    artifacts:GENERATED.map(name=>({path:name,sha256:fileDigest(path.join(HERE,name)),source_commits:[BASE,TARGET]})),expected_results:{revision_count:2,scan_statuses:['partial','completed'],history_count:205,
      graph_node_counts:[100,300,500],assessment_finding_count:1,assessment_obligation_count:1,remediation_task_count:1,report_v2_profile_count:1,report_v2_notice_fact_count:5,
      report_v2_snapshot_included:false,download_api_included:false},limitations:['This package contains deterministic facts and draft inputs only; it is not a legal conclusion.',
      'No final Report V2 snapshot or download API response is included.','Provider license labels remain raw observations; license_expression_id stays null and authorization stays pending.']};
}
function verifyCommits() {
  for (const commit of [BASE,TARGET]) execFileSync('git',['cat-file','-e',`${commit}^{commit}`],{cwd:ROOT,stdio:'pipe'});
  execFileSync('git',['merge-base','--is-ancestor',BASE,TARGET],{cwd:ROOT,stdio:'pipe'});
}
function validateArtifacts(artifacts) {
  const scans=artifacts['scans.json'].items,assessment=artifacts['assessment.json'],task=artifacts['remediation-task.json'],history=artifacts['history.json'];
  if (scans.map(x=>x.status).join(',')!=='partial,completed') throw new Error('scan status contract failed');
  if (history.count!==205||history.items.length!==205||new Set(history.items.map(x=>x.scan_id)).size!==205) throw new Error('history contract failed');
  if (task.origin.source_hash!==digest(assessment.obligations[0])) throw new Error('task origin hash failed');
  for (const size of [100,300,500]) { const graph=artifacts[`graph-${size}.json`],ids=new Set(graph.nodes.map(x=>x.id));
    if (ids.size!==size||graph.coverage.node_count!==size||graph.edges.some(e=>!ids.has(e.source)||!ids.has(e.target))) throw new Error(`graph ${size} contract failed`); }
  const report=artifacts['report-v2-input.json'];
  if (report.resource_profile.authorization_status!=='pending'||report.resource_profile.license_expression_id!==null||report.policy.license_expression_autofill!==false) throw new Error('report input policy failed');
}

verifyCommits(); const artifacts=build(); validateArtifacts(artifacts);
if (process.argv.includes('--check')) {
  for (const [name,value] of Object.entries(artifacts)) if (fs.readFileSync(path.join(HERE,name),'utf8')!==JSON.stringify(value,null,2)+'\n') throw new Error(`stale generated artifact: ${name}`);
  if (JSON.stringify(JSON.parse(fs.readFileSync(path.join(HERE,'manifest.json'),'utf8')))!==JSON.stringify(makeManifest())) throw new Error('stale generated artifact: manifest.json');
} else {
  for (const [name,value] of Object.entries(artifacts)) dump(path.join(HERE,name),value);
  dump(path.join(HERE,'manifest.json'),makeManifest());
}
