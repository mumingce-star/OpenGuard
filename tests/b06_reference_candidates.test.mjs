import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const catalog = JSON.parse(readFileSync(join(root, 'benchmarks/candidates/b06-reference-only-v1.json'), 'utf8'));
const verification = JSON.parse(readFileSync(join(root, 'benchmarks/annotations/real-resource-20260911-ai-assisted/source-reverification.json'), 'utf8'));

test('B06 reference-only candidates are fixed to independently recorded commit/path/hash observations', () => {
  assert.equal(catalog.status, 'not_gold_not_admitted');
  const records = new Map();
  for (const file of verification.files) records.set(`${file.repository}:${file.path}:${file.sha256}`, file);
  const commits = new Map(verification.repositories.map((item) => [item.repository, item.commit]));
  for (const candidate of catalog.candidates) {
    const repository = candidate.repository_url.replace('https://github.com/', '');
    assert.equal(candidate.commit, commits.get(repository), candidate.candidate_id);
    assert.ok(records.has(`${repository}:${candidate.path}:${candidate.source_sha256}`), candidate.candidate_id);
    assert.equal(candidate.citation_status, 'public_reference_only_pending_human_rights_review');
    assert.match(candidate.source_sha256, /^[a-f0-9]{64}$/);
  }
});

test('B06 catalog cannot imply Gold, split admission, or source redistribution', () => {
  assert.equal(catalog.redistribution_policy, 'reference_only_no_third_party_source_content');
  assert.deepEqual(catalog.admission_requirements, [
    'human_rights_review', 'split_assignment_after_family_deduplication', 'blind_packet_hash',
    'two_human_reviews', 'third_human_adjudication', 'gold_freeze_sha256',
  ]);
  assert.ok(catalog.candidates.every((candidate) => !Object.hasOwn(candidate, 'gold_label') && !Object.hasOwn(candidate, 'split')));
});
