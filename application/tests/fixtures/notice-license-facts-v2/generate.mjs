#!/usr/bin/env node
/** Deterministically migrate the immutable v1 evidence package into B03/B04 v2 facts. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../../..');
const V1_PATH = 'tests/fixtures/notice-license-facts-v1/facts.json';
const V1_COMMIT = 'e2d8c016ef5f4cfcddd23abb0205ec41c7cf3db1';
const PROFILE_COMMIT = '23fae26485db2fe3449ec8e7cccc3af64a487002';
const GENERATED_AT = '2026-09-21T15:25:00Z';
const PRODUCER = {name:'openguard-b03-b04-facts',version:'2.0.0'};

const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const bytes = value => Buffer.from(JSON.stringify(stable(value)));
const digest = value => crypto.createHash('sha256').update(Buffer.isBuffer(value) ? value : bytes(value)).digest('hex');
const fileDigest = name => digest(fs.readFileSync(name));
const readJson = name => JSON.parse(fs.readFileSync(name, 'utf8'));
const writeJson = (name,value) => fs.writeFileSync(name,JSON.stringify(value,null,2)+'\n','utf8');

function pointerValue(document, pointer) {
  if (pointer === '') return document;
  return pointer.slice(1).split('/').reduce((value,token)=>value[token.replaceAll('~1','/').replaceAll('~0','~')],document);
}

function evidenceV2(item, sourcePackage) {
  const hash = item.container_sha256 ?? item.content_sha256;
  const fragment = item.locator.includes('#') ? item.locator.slice(item.locator.indexOf('#')+1) : null;
  let selected = item.content_sha256;
  let sourceCommit = item.kind === 'repository_file' ? V1_COMMIT : null;
  let scope = item.kind === 'archive_entry' ? 'archive_entry' : item.kind === 'provider_snapshot' ? 'json_pointer_value' : 'whole_file';
  if (item.kind === 'provider_snapshot') {
    const relative = item.locator.slice(0,item.locator.indexOf('#'));
    selected = digest(pointerValue(readJson(path.join(ROOT,relative)),fragment));
    sourceCommit = PROFILE_COMMIT;
  }
  return {
    evidence_id:item.evidence_id,kind:item.kind,locator:item.locator,source_url:item.source_url,
    source_revision:sourceCommit,content_scope:scope,source_file_sha256:hash,
    container_sha256:item.container_sha256,selected_content_sha256:selected,selected_json_pointer:fragment,
    excerpt:item.excerpt,verification:item.verification,captured_at:new Date(sourcePackage.observed_at).toISOString(),producer:PRODUCER,
  };
}

const noticeGap = code => code === 'GAP_NOTICE_NOT_PACKAGED' ? 'GAP_NOTICE_FILE_NOT_OBSERVED' : code;

function factV2(item) {
  const isAi = item.subject.category === 'ai_resource';
  const isRoot = item.subject.category === 'root_project';
  const observations = item.license_observations.map(value=>({...value,
    observation_strength:isAi?'provider_declared_unverified':'text_observed'}));
  const relationships = {
    license:{state:isAi?'declared_unverified':'text_observed',evidence_ids:item.relationships.license.evidence_ids,
      gap_code:item.relationships.license.gap_code,applicability:'pending_review'},
    notice:{...item.relationships.notice,gap_code:noticeGap(item.relationships.notice.gap_code),applicability:'pending_review'},
    copyright:{...item.relationships.copyright,gap_code:noticeGap(item.relationships.copyright.gap_code),applicability:'pending_review'},
  };
  return {
    fact_id:item.fact_id,
    subject:{...item.subject,
      source_url:isRoot?`https://github.com/mumingce-star/OpenGuard/blob/${V1_COMMIT}/LICENSE`:item.subject.source_url,
      source_revision:isRoot?V1_COMMIT:item.subject.version},
    authorization_status:'pending',license_observations:observations,relationships,
    gaps:item.gaps.map(noticeGap),review_status:'pending_human_review',
  };
}

function rowFor(fact) {
  const subject=fact.subject;
  const raw=fact.license_observations.map(item=>Array.isArray(item.raw_value)?item.raw_value.join(', '):item.raw_value??'missing').join('; ');
  const observed=Object.entries(fact.relationships).filter(([,value])=>value.state!=='gap').map(([key])=>key);
  const gaps=fact.gaps;
  return {
    row_id:'row.v2.'+fact.fact_id.slice('fact.'.length),subject_fact_id:fact.fact_id,
    resource_name_and_type:`${subject.display_name} / ${subject.category}`,
    version_and_source:`${subject.version??'version unknown'} / ${subject.source_url??'repository commit '+subject.source_revision}`,
    license_or_authorization:`raw license observation: ${raw}; authorization=${fact.authorization_status}; formal expression absent`,
    usage_or_open_mode:`usage_scope=${subject.usage_scope}; applicability pending human review`,
    key_obligations_or_restrictions:`observed=${observed.join(',')||'none'}; gaps=${gaps.join(',')||'none'}; no legal conclusion`,
    team_modifications:'not evidenced by this facts package',compliance_status:'待核验',authorization_status:fact.authorization_status,
    license_expression_ids:[],observation_strengths:[...new Set(fact.license_observations.map(item=>item.observation_strength))].sort(),
    evidence_ids:[...new Set(Object.values(fact.relationships).flatMap(value=>value.evidence_ids))].sort(),gap_codes:[...gaps].sort(),
  };
}

function build() {
  const v1=readJson(path.join(ROOT,V1_PATH));
  const committed=execFileSync('git',['show',`${V1_COMMIT}:${V1_PATH}`],{cwd:ROOT});
  const source_package={path:V1_PATH,schema_version:v1.schema_version,fixed_commit:V1_COMMIT,
    source_file_sha256:fileDigest(path.join(ROOT,V1_PATH)),commit_blob_sha256:digest(committed)};
  const evidence=v1.evidence.map(item=>evidenceV2(item,v1));
  const facts=v1.facts.map(factV2);
  const report_v2_rows=facts.map(rowFor);
  return {schema_version:'openguard.notice-license-facts/2',package_status:'draft_facts_only',generated_at:GENERATED_AT,
    source_package,producer:PRODUCER,evidence,facts,report_v2_rows,
    policies:{license_expression_autofill:false,authorization_default:'pending',gap_is_noncompliance:false,notice_absence_is_violation:false}};
}

function validate(value) {
  const evidenceIds=new Set(value.evidence.map(item=>item.evidence_id));
  if (evidenceIds.size!==value.evidence.length) throw new Error('duplicate evidence_id');
  if (new Set(value.facts.map(item=>item.fact_id)).size!==value.facts.length) throw new Error('duplicate fact_id');
  if (value.report_v2_rows.length!==value.facts.length) throw new Error('row cardinality mismatch');
  for (const fact of value.facts) {
    if (fact.authorization_status!=='pending'||fact.review_status!=='pending_human_review') throw new Error(`unsafe status: ${fact.fact_id}`);
    if (fact.license_observations.some(item=>item.license_expression_id!==null)) throw new Error(`expression autofill: ${fact.fact_id}`);
    for (const relation of Object.values(fact.relationships)) {
      if (relation.evidence_ids.some(id=>!evidenceIds.has(id))) throw new Error(`unknown evidence: ${fact.fact_id}`);
      if ((relation.state==='gap') !== Boolean(relation.gap_code)) throw new Error(`gap invariant: ${fact.fact_id}`);
      if (relation.state==='gap' && relation.evidence_ids.length) throw new Error(`gap evidence invariant: ${fact.fact_id}`);
    }
    const row=value.report_v2_rows.find(item=>item.subject_fact_id===fact.fact_id);
    if (!row||row.authorization_status!==fact.authorization_status||JSON.stringify(row.gap_codes)!==JSON.stringify([...fact.gaps].sort())) throw new Error(`row drift: ${fact.fact_id}`);
  }
  for (const item of value.evidence) {
    if (!/^[0-9a-f]{64}$/.test(item.source_file_sha256)||!/^[0-9a-f]{64}$/.test(item.selected_content_sha256)) throw new Error(`hash invalid: ${item.evidence_id}`);
    if (item.content_scope==='json_pointer_value'&&!item.selected_json_pointer) throw new Error(`pointer missing: ${item.evidence_id}`);
  }
}

const value=build(); validate(value);
const output=path.join(HERE,'facts.json');
if (process.argv.includes('--check')) {
  if (fs.readFileSync(output,'utf8')!==JSON.stringify(value,null,2)+'\n') throw new Error('stale facts.json');
} else writeJson(output,value);
