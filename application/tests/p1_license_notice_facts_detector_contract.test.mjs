import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import test from 'node:test';

const load = name => JSON.parse(fs.readFileSync(name, 'utf8'));
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const digest = value => crypto.createHash('sha256').update(JSON.stringify(stable(value))).digest('hex');

test('B02 fixed expectation stays conservative and hash pinned', () => {
  const facts = load('tests/fixtures/notice-license-facts-v2/facts.json');
  const expected = load('tests/fixtures/p1-integration-b-v1/expected.json');
  const codes = new Map();
  const add = code => codes.set(code, (codes.get(code) ?? 0) + 1);

  for (const fact of facts.facts) {
    assert.equal(fact.authorization_status, 'pending');
    assert.ok(fact.license_observations.every(item => item.license_expression_id === null));
    fact.gaps.forEach(add);
    if (fact.relationships.license.state === 'declared_unverified') {
      add('LICENSE_DECLARATION_UNVERIFIED');
    }
  }

  assert.equal(digest(facts), expected.source_package_sha256);
  assert.equal([...codes.values()].reduce((left, right) => left + right, 0), expected.finding_count);
  assert.deepEqual(Object.fromEntries([...codes].sort()), expected.finding_codes);
  assert.equal(expected.obligation_count, 0);
  assert.deepEqual(expected.semantics, {
    authorization_status: 'pending', finding_status: 'review_required', gap_is_violation: false,
    license_expression_autofill: false, provider_declaration_is_verified_license: false,
  });
});

test('B02 candidate matrix exhaustively guards fixed-fact omissions and overstatement', () => {
  const facts = load('tests/fixtures/notice-license-facts-v2/facts.json');
  const matrix = load('tests/fixtures/p1-integration-b-v1/candidate-matrix.json');
  const expected = Object.fromEntries(facts.facts.map(fact => {
    const candidates = fact.gaps.map(code => ({ category: 'evidence_gap', code }));
    if (fact.relationships.license.state === 'declared_unverified') {
      candidates.push({ category: 'unverified_license_declaration', code: 'LICENSE_DECLARATION_UNVERIFIED' });
    }
    return [fact.fact_id, candidates];
  }));

  assert.equal(digest(facts), matrix.source_package_sha256);
  assert.deepEqual(matrix.expected_candidates_by_fact, expected);
  assert.deepEqual(Object.keys(matrix.expected_candidates_by_fact).sort(), facts.facts.map(fact => fact.fact_id).sort());
  assert.deepEqual(matrix.false_positive_guards.zero_candidate_facts, ['fact.dep.jackson-databind', 'fact.dep.springboot']);
  assert.equal(matrix.false_positive_guards.forbidden_confirmed_violation, true);
  assert.deepEqual(matrix.false_positive_guards.forbidden_candidate_categories, ['formal_risk', 'obligation']);
});
