import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { runtime } from './runtime.mjs';

const hash = 'a'.repeat(64);
const binding = () => ({ scan_id: 'scn_1', assessment_id: 'asm_1', assessment_version: 2, registry_revision: 3,
  project_revision: null, facts_hash: hash, usage_hash: hash, rule_version: 'assessment-v1', assessment_sha256: hash });
const result = (revision = 1) => ({ schema_version: 'openguard-p2-result/1', algorithm_version: 'p2-bound-candidate/1',
  result_id: 'p2res_' + revision, revision, previous_result_id: revision === 1 ? null : 'p2res_' + (revision - 1), result_sha256: hash,
  binding: binding(), data_scope: 'TEST_ONLY', computation: 'DETERMINISTIC_P2B', publication_status: 'succeeded', formal_effect: 'none',
  model_calls: 0, state: 'pending', created_at: '2026-10-10T00:00:00Z', usage: { commercial: null },
  resources: [{ subject: { resource_id: 'cmp_1', version: '1.0.0' }, resource_kind: 'component', state: 'pending',
    verification_state: 'candidate_only', scope: 'resource', evidence_ids: ['ev_1'], evidence_source_hashes: {},
    material_ids: [], answer_ids: revision === 2 ? ['p2ans_1'] : [], gaps: ['notice_missing'], advice: [], user_assertions: {},
    inherited_local_support: false, inherited_support_source: 'PARENT_ASSESSMENT_NOT_NEW_VALUE' }],
  questions: [{ question_id: 'p2q_1', question_code: 'DELIVERY_SCOPE_FOR_RESOURCES', origin: 'DETERMINISTIC_P2_NOT_R6_AGGREGATE',
    subjects: [{ resource_id: 'cmp_1', version: '1.0.0' }], options: ['YES_INCLUDE','NO_EXCLUDE','NOT_DECIDED'], scope_rule: 'EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN' }],
  material_ids: [], answer_ids: revision === 2 ? ['p2ans_1'] : [], recomputed_resource_ids: ['cmp_1'], reused_resource_ids: [],
  companion_summary_id: 'p2sum_' + revision });
const index = (rev = 1) => ({ head_result_id: 'p2res_' + rev, head_revision: rev, result_ids: ['p2res_' + rev], has_more: false });
const envelope = (status, code, reason = '') => Response.json({ error: { code, message: code, request_id: 'req_1', details: { reason } } }, { status });

test('fixed URL, exact Result and same-revision Summary reject mismatches', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  assert.deepEqual(JSON.parse(JSON.stringify(p.p2Selection(new URLSearchParams('assessment_version=2&p2_result_id=p2res_1&p2_revision=1'), 2))), { id: 'p2res_1', revision: 1 });
  assert.throws(() => p.p2Selection(new URLSearchParams('assessment_version=3&p2_result_id=p2res_1&p2_revision=1'), 2), /URL/);
  assert.throws(() => p.p2Selection(new URLSearchParams('p2_result_id=p2res_1'), 2), /URL/);
  const calls = [];
  r.setFetch(async url => { calls.push(url); return Response.json(url.includes('/summary?') ? {
    summary_id: 'p2sum_1', result_id: 'p2res_1', result_revision: 1, result_sha256: hash,
    binding: binding(), material_ids: [], answer_ids: [], state: 'pending', resource_states: { cmp_1: 'pending' },
    formal_effect: 'none', report_kind: 'P2_COMPANION_NOT_FORMAL_REPORT',
  } : result()); });
  const api = r.load('services/p2Advice.ts');
  await assert.rejects(api.readP2Result(binding(), 'p2res_missing', 1), /契约|版本/);
  const good = await api.readP2Result(binding(), 'p2res_1', 1);
  assert.equal((await p.readP2Summary(good)).result_revision, 1);
  assert.match(calls.at(-1), /p2res_1\/summary\?assessment_version=2$/);
  assert.throws(() => p.validateSummary({ summary_id: 'p2sum_1', result_id: 'p2res_1', result_revision: 2 }, good), /回执/);
});

test('write keeps original key/body through uncertain result and explicit read before replay', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  const attempt = new p.P2WriteAttempt('results', { binding: binding(), expected_revision: 0, parent_result_id: null, idempotency_key: 'fixedkey_1' });
  let posts = 0; const bodies = [];
  r.setFetch(async (url, options) => {
    if ((options.method ?? 'GET') === 'POST') { posts++; bodies.push(options.body); if (posts === 1) throw new TypeError('connection lost'); return Response.json({ result: result(), answer: null, material: null }, { status: 201 }); }
    if (url.endsWith('/binding')) return Response.json(binding());
    if (url.includes('/results?')) return Response.json(index());
    return Response.json(result());
  });
  await assert.rejects(attempt.send(), /connection lost/);
  assert.equal(attempt.state, 'unknown'); assert.equal(posts, 1);
  await assert.rejects(attempt.send(), /核对/);
  assert.equal((await attempt.recover()).result_id, 'p2res_1');
  assert.equal(posts, 1);
  assert.equal((await attempt.send()).result.result_id, 'p2res_1');
  assert.equal(attempt.state, 'saved'); assert.equal(posts, 2); assert.equal(bodies[0], bodies[1]);
});

test('CAS and input errors never turn into saved state or an automatic POST', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  const codes = [[409, 'p2_revision_conflict', 'conflict'], [422, 'p2_request_invalid', 'rejected'], [503, 'p2_read_only', 'unknown']];
  for (const [status, code, expected] of codes) {
    const attempt = new p.P2WriteAttempt('results', { binding: binding(), expected_revision: 0, parent_result_id: null, idempotency_key: 'fixedkey_2' });
    let calls = 0; r.setFetch(async () => { calls++; return envelope(status, code); });
    await assert.rejects(attempt.send()); assert.equal(attempt.state, expected); assert.equal(calls, 1);
    await assert.rejects(attempt.send()); assert.equal(calls, 1);
  }
});

test('question comes from server, subset cannot be expanded or converted into Formal input', () => {
  const p = runtime().load('services/p2Workflow.ts');
  const req = p.prepareAnswer(result(), 'p2q_1', 'NOT_DECIDED', ['cmp_1']);
  assert.equal(req.subjects.length, 1); assert.equal(req.question_code, 'DELIVERY_SCOPE_FOR_RESOURCES');
  assert.throws(() => p.prepareAnswer(result(), 'made_up', 'YES_INCLUDE', ['cmp_1']), /服务端/);
  assert.throws(() => p.prepareAnswer(result(), 'p2q_1', 'FULFILLED', ['cmp_1']), /服务端/);
  assert.throws(() => p.prepareAnswer(result(), 'p2q_1', 'YES_INCLUDE', ['cmp_other']), /服务端/);
});

test('small source material is hashed as raw bytes; invalid name/version/encoding rejected', async () => {
  const p = runtime().load('services/p2Workflow.ts');
  const raw = new TextEncoder().encode('MIT License\n');
  const prepared = await p.prepareMaterial(result(), 'cmp_1', ['ev_1'], 'LICENSE', raw, '来自本地提供者', 'EXCERPT');
  assert.equal(prepared.source_sha256, '267f7a2e19dfa9df99af774520985a0e521925293ea5b7e767ab06969d06bf91');
  assert.equal(prepared.content_base64, Buffer.from(raw).toString('base64'));
  await assert.rejects(p.prepareMaterial(result(), 'cmp_1', ['ev_1'], 'license.bin', raw, '来源', 'EXCERPT'), /只允许/);
  await assert.rejects(p.prepareMaterial(result(), 'cmp_1', ['ev_1'], 'NOTICE', new Uint8Array([255]), '来源', 'EXCERPT'), /UTF-8/);
  await assert.rejects(p.prepareMaterial({ ...result(), resources: [{ ...result().resources[0], subject: { resource_id: 'cmp_1', version: null } }] }, 'cmp_1', ['ev_1'], 'LICENSE', raw, '来源', 'EXCERPT'), /版本/);
});

test('receipt and rendered labels preserve unverified source and Formal boundary', () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  const components = r.load('components/P2Workbench.tsx');
  const saved = result(2);
  const answer = { answer_id: 'p2ans_1', revision: 2, binding: binding(), question_id: 'p2q_1', question_code: 'DELIVERY_SCOPE_FOR_RESOURCES',
    answer_code: 'NOT_DECIDED', subjects: [{ resource_id: 'cmp_1', version: '1.0.0' }], evidence_ids: [], provenance: 'USER_ASSERTED', formal_effect: 'none', data_scope: 'TEST_ONLY' };
  assert.equal(p.validateAnswer(answer, saved, 'p2ans_1').provenance, 'USER_ASSERTED');
  const summary = { summary_id: 'p2sum_2', result_id: 'p2res_2', result_revision: 2, result_sha256: hash, binding: binding(),
    material_ids: [], answer_ids: ['p2ans_1'], state: 'pending', resource_states: { cmp_1: 'pending' }, formal_effect: 'none', report_kind: 'P2_COMPANION_NOT_FORMAL_REPORT' };
  const markup = renderToStaticMarkup(createElement(components.P2SummaryView, { summary }));
  assert.match(markup, /非正式报告/); assert.match(markup, /不能替代或改写 Formal/);
  const ref = renderToStaticMarkup(createElement(components.P2ReferenceView, { value: answer, onEvidence: () => {} }));
  assert.match(ref, /USER_ASSERTED/); assert.match(ref, /不等于正式义务已履行/);
});
