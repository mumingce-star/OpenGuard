import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const fixture = join(root, 'tests', 'fixtures', 'notice-license-facts-v3');
const facts = JSON.parse(readFileSync(join(fixture, 'facts.json'), 'utf8'));
const hash = (value) => createHash('sha256').update(value).digest('hex');

test('v3 facts are reproducible from real project inputs', () => {
  execFileSync('node', [join(fixture, 'generate.mjs'), '--check'], { cwd: root, stdio: 'pipe' });
  assert.equal(facts.schema_version, 'openguard.notice-license-facts/3');
  assert.equal(facts.package_status, 'draft_facts_only');
  assert.equal(facts.facts.length, 31);
  assert.equal(facts.evidence.length, 31);
});

test('every fact is source-bound and all conclusions fail closed', () => {
  const evidenceById = new Map(facts.evidence.map((item) => [item.evidence_id, item]));
  for (const fact of facts.facts) {
    assert.equal(fact.authorization_status, 'pending');
    assert.equal(fact.license_expression_id, null);
    assert.ok(fact.fact_provenance_evidence_ids.length > 0);
    for (const id of fact.fact_provenance_evidence_ids) assert.ok(evidenceById.has(id), `${fact.fact_id} references ${id}`);
    for (const relation of Object.values(fact.relationships)) {
      assert.ok(['text_observed', 'provider_declared_unverified', 'gap'].includes(relation.state));
      if (relation.state === 'gap') assert.deepEqual(relation.evidence_ids, []);
    }
  }
  for (const item of facts.evidence) {
    assert.match(item.source_file_sha256, /^[a-f0-9]{64}$/);
    assert.match(item.selected_content_sha256, /^[a-f0-9]{64}$/);
    assert.equal(item.producer.version, '3.0.0');
    assert.match(item.captured_at, /^2026-09-22T09:30:00Z$/);
  }
});

test('hash scopes and locators preserve observation granularity', () => {
  const rootLicense = facts.evidence.find((item) => item.evidence_id === 'evidence.root.license');
  assert.equal(rootLicense.source_file_sha256, hash(readFileSync(join(root, 'LICENSE'))));
  assert.equal(rootLicense.selected_content_sha256, rootLicense.source_file_sha256);
  const npmReact = facts.evidence.find((item) => item.evidence_id === 'evidence.dependency.npm.react');
  assert.equal(npmReact.selected_json_pointer, '/dependencies/react');
  assert.equal(npmReact.locator, 'frontend/package.json#/dependencies/react');
  const pythonFastapi = facts.evidence.find((item) => item.evidence_id === 'evidence.dependency.python.fastapi');
  assert.equal(pythonFastapi.selected_json_pointer, null);
  assert.match(pythonFastapi.locator, /pyproject\.toml#project\.dependencies/);
  const ai = facts.evidence.find((item) => item.evidence_id === 'evidence.ai.hf-model-gpt2.declared-license');
  assert.equal(ai.selected_json_pointer, '/payload/cardData/license');
  assert.match(ai.source_url, /^https:\/\/huggingface\.co\/api\//);
});

test('tampering an observed source hash is detectable without inventing a conclusion', () => {
  const rootLicense = facts.evidence.find((item) => item.evidence_id === 'evidence.root.license');
  const tampered = `${readFileSync(join(root, 'LICENSE'), 'utf8')}\nmutation`;
  assert.notEqual(rootLicense.source_file_sha256, hash(tampered));
  assert.equal(facts.facts.find((item) => item.fact_id === 'fact.root.openguard').authorization_status, 'pending');
});
