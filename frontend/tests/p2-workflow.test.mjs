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

test('a successful content-deduplicated write may reuse the current Result without inventing a revision', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  const attempt = new p.P2WriteAttempt('results', {
    binding: binding(), expected_revision: 1, parent_result_id: 'p2res_1', idempotency_key: 'fixedkey_content_reuse',
  });
  r.setFetch(async () => Response.json({ result: result(1), answer: null, material: null }, { status: 201 }));
  const receipt = await attempt.send();
  assert.equal(receipt.result.result_id, 'p2res_1');
  assert.equal(receipt.result.revision, 1);
  assert.equal(attempt.state, 'saved');
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

test('a reference GET aborts when its fixed Result context is left', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  const saved = result(2);
  saved.material_ids = ['p2mat_1']; saved.resources[0].material_ids = ['p2mat_1'];
  let started;
  const requested = new Promise(resolve => { started = resolve; });
  let aborted = false;
  r.setFetch((url, options) => new Promise((resolve, reject) => {
    assert.match(url, /\/p2\/materials\/p2mat_1\?assessment_version=2$/);
    options.signal.addEventListener('abort', () => { aborted = true; reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
    started();
  }));
  const controller = new AbortController();
  const pending = p.readP2Reference(saved, 'materials', 'p2mat_1', controller.signal);
  await requested;
  controller.abort();
  await assert.rejects(pending, error => error.name === 'AbortError');
  assert.equal(aborted, true);
});

test('previous snapshot GET pins parent id, revision and binding; missing first parent makes no request', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  const calls = [];
  let response = result(1);
  r.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return Response.json(response); });
  assert.equal(await p.readPreviousP2Result(result(1)), null);
  assert.equal(calls.length, 0);
  assert.equal((await p.readPreviousP2Result(result(2))).result_id, 'p2res_1');
  assert.deepEqual(calls[0], ['/api/v1/scans/scn_1/assessments/asm_1/p2/results/p2res_1?assessment_version=2', 'GET']);
  for (const bad of [
    { ...result(), result_id: 'other' }, { ...result(), revision: 5 },
    { ...result(), binding: { ...binding(), facts_hash: 'b'.repeat(64) } },
    { ...result(), data_scope: 'OWNER' },
  ]) { response = bad; await assert.rejects(p.readPreviousP2Result(result(2)), /契约|范围/); }
});

test('snapshot pair shows source values without treating recomputation or absent resource as a conclusion', () => {
  const r = runtime(), { P2VersionPair } = r.load('components/P2VersionComparison.tsx');
  const current = { ...result(2), resources: [], recomputed_resource_ids: [], state: 'partial' };
  const html = renderToStaticMarkup(createElement(P2VersionPair, { previous: result(), current }));
  for (const text of ['前版快照', '本版快照', 'p2res_1', 'p2res_2', '不是前端生成的差异结论', '重新计算不等于结论已改变', '不代表资源已删除', '缺口']) assert.ok(html.includes(text), text);
});

test('read-only deployment blocks initial and uncertain replay POSTs at transport boundary', async () => {
  const r = runtime({ VITE_P2_READ_ONLY: '1' }), p = r.load('services/p2Workflow.ts');
  let calls = 0; r.setFetch(async () => { calls++; throw new Error('must not fetch'); });
  const attempt = new p.P2WriteAttempt('results', p.createFields(binding(), null));
  await assert.rejects(attempt.send(), /只读/);
  attempt.state = 'unknown'; attempt.recovered = true;
  await assert.rejects(attempt.send(), /只读/);
  assert.equal(calls, 0); assert.equal(attempt.state, 'unknown');
  const { P2Workbench } = r.load('components/P2Workbench.tsx');
  const html = renderToStaticMarkup(createElement(P2Workbench, { scanId: 'scn_1', assessmentId: 'asm_1', assessmentVersion: 2,
    query: new URLSearchParams(), evidenceIds: [], onEvidence() {}, onSelect() {} }));
  assert.match(html, /P2写入已禁用/);
  assert.match(html, /<input(?=[^>]*type="checkbox")(?=[^>]*disabled="")[^>]*>/);
});

test('material boundary, capacity, evidence mismatch and source text validation never send requests', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  let calls = 0; r.setFetch(async () => { calls++; throw new Error('unexpected write'); });
  const args = [result(), 'cmp_1', ['ev_1'], 'NOTICE.txt', new TextEncoder().encode('source'), 'user source', 'EXCERPT'];
  for (const [position, value, pattern] of [[2, ['ev_other'], /Evidence/], [4, new Uint8Array(65537), /字节/],
    [4, new Uint8Array([0]), /NUL/], [5, '', /来源说明/],
    [0, { ...result(), material_ids: Array.from({ length: 20 }, (_, i) => 'mat_' + i) }, /20份/]]) {
    const input = [...args]; input[position] = value; await assert.rejects(p.prepareMaterial(...input), pattern);
  }
  const input = [...args]; input[4] = new Uint8Array(65536).fill(65);
  assert.equal((await p.prepareMaterial(...input)).content_base64.length, 87384);
  assert.equal(calls, 0);
});

test('mismatched successful receipt stays unknown and a repeated click cannot POST while sending', async () => {
  const r = runtime(), p = r.load('services/p2Workflow.ts');
  let release; let calls = 0;
  r.setFetch(() => { calls++; return new Promise(resolve => { release = resolve; }); });
  const attempt = new p.P2WriteAttempt('results', p.createFields(binding(), null));
  const pending = attempt.send();
  await assert.rejects(attempt.send(), /核对/); assert.equal(calls, 1);
  release(Response.json({ result: { ...result(), binding: { ...binding(), assessment_id: 'asm_other' } } }, { status: 201 }));
  await assert.rejects(pending, /契约/); assert.equal(attempt.state, 'unknown');
  await assert.rejects(attempt.send(), /核对/); assert.equal(calls, 1);
});
