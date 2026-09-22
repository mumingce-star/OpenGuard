import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {execFileSync} from 'node:child_process';

const ROOT=process.cwd();
const DIR=path.join(ROOT,'tests/fixtures/notice-license-facts-v2');
const load=name=>JSON.parse(fs.readFileSync(path.join(DIR,name),'utf8'));
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');

test('v2 is deterministic and pinned to immutable v1 source',()=>{
  execFileSync('node',[path.join(DIR,'generate.mjs'),'--check'],{cwd:ROOT});
  const value=load('facts.json'), source=value.source_package;
  assert.equal(sha(fs.readFileSync(path.join(ROOT,source.path))),source.source_file_sha256);
  assert.equal(sha(execFileSync('git',['show',`${source.fixed_commit}:${source.path}`],{cwd:ROOT})),source.commit_blob_sha256);
  assert.equal(value.schema_version,'openguard.notice-license-facts/2');
  assert.deepEqual(value.policies,{license_expression_autofill:false,authorization_default:'pending',gap_is_noncompliance:false,notice_absence_is_violation:false});
});

test('machine facts remain conservative and rows cannot drift',()=>{
  const value=load('facts.json');
  assert.equal(value.facts.length,8); assert.equal(value.evidence.length,10); assert.equal(value.report_v2_rows.length,8);
  const evidence=new Set(value.evidence.map(item=>item.evidence_id));
  for (const fact of value.facts) {
    assert.equal(fact.authorization_status,'pending'); assert.equal(fact.review_status,'pending_human_review');
    assert.ok(fact.license_observations.every(item=>item.license_expression_id===null));
    assert.ok(Object.values(fact.relationships).every(item=>item.applicability==='pending_review'));
    assert.ok(Object.values(fact.relationships).flatMap(item=>item.evidence_ids).every(id=>evidence.has(id)));
    const row=value.report_v2_rows.find(item=>item.subject_fact_id===fact.fact_id);
    assert.equal(row.authorization_status,fact.authorization_status); assert.deepEqual(row.license_expression_ids,[]);
    assert.deepEqual(row.gap_codes,[...fact.gaps].sort());
  }
  assert.ok(value.facts.filter(item=>item.subject.category==='ai_resource').every(item=>item.relationships.license.state==='declared_unverified'));
  assert.ok(value.facts.filter(item=>item.subject.category!=='ai_resource').every(item=>item.relationships.license.state==='text_observed'));
  assert.ok(value.facts.flatMap(item=>item.gaps).includes('GAP_NOTICE_FILE_NOT_OBSERVED'));
  assert.ok(!value.facts.flatMap(item=>item.gaps).includes('GAP_NOTICE_NOT_PACKAGED'));
});

test('hash scopes distinguish files, archive entries and JSON pointer values',()=>{
  const value=load('facts.json');
  assert.deepEqual([...new Set(value.evidence.map(item=>item.content_scope))].sort(),['archive_entry','json_pointer_value','whole_file']);
  for (const item of value.evidence) {
    assert.match(item.source_file_sha256,/^[0-9a-f]{64}$/); assert.match(item.selected_content_sha256,/^[0-9a-f]{64}$/);
    if (item.content_scope==='archive_entry') assert.notEqual(item.source_file_sha256,item.selected_content_sha256);
    if (item.content_scope==='json_pointer_value') { assert.ok(item.selected_json_pointer.startsWith('/')); assert.notEqual(item.source_file_sha256,item.selected_content_sha256); }
  }
});
