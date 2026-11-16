import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { runtime } from './runtime.mjs';

// SYNTHETIC_TEST_ONLY. These objects are independently authored contract fixtures,
// not backend executions, trusted source attestations, M1 objects or approvals.
// Basis: backend/app/p2/service.py resource_result (173-202), write (364-449),
// contract.py AnswerRequest/MaterialRequest/Result/Answer/Material; p2b/materials.py.
const GRADE = 'SYNTHETIC_TEST_ONLY';
const useNames = ['commercial', 'modified', 'distributed', 'network_service', 'training', 'redistributed_assets', 'source_disclosure'];
const usage = Object.fromEntries(useNames.map((key, i) => [key, i === 0 ? true : i === 1 ? false : null]));
const baseGaps = ['license_text_and_applicability_unverified', 'object_scope_unverified', 'upstream_source_attestation_missing'];
const questionCode = 'DELIVERY_SCOPE_FOR_RESOURCES';
const materialText = 'SYNTHETIC_TEST_ONLY unreviewed material\n';
const materialHash = createHash('sha256').update(materialText).digest('hex');
const copy = value => JSON.parse(JSON.stringify(value));
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const digest = value => createHash('sha256').update(JSON.stringify(stable(value))).digest('hex');
const sorted = values => [...values].sort();
const uniqueSorted = values => sorted([...new Set(values)]);
const snapshot = value => JSON.stringify(value);
const rowId = i => 'cmp_' + i;
const subject = i => ({ resource_id: rowId(i), version: '7.0.0' });
const evidenceFor = i => ['evd_' + i + '_a', 'evd_' + i + '_b', ...(i < 3 ? ['evd_shared'] : [])];
const postPath = (ctx, operation) => '/api/v1/scans/' + ctx.assessment.scan_id + '/assessments/' + ctx.assessment.id + '/p2/' + operation;
const resultPath = (ctx, result) => postPath(ctx, 'results/' + result.result_id) + '?assessment_version=2';

function deepFreeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const item of Object.values(value)) deepFreeze(item);
    Object.freeze(value);
  }
  return value;
}
function context() {
  const resources = [1, 2, 3];
  const factsHash = digest({ grade: GRADE, resources: resources.map(i => ({ ...subject(i), evidence_ids: evidenceFor(i) })) });
  // P2Service.context hashes UsageDeclaration except declared_at: preset is included.
  const usageHash = digest({ preset: 'unknown', ...usage });
  const assessment = { id: 'asm_synthetic_closure', scan_id: 'scn_synthetic_closure', version: 2, formal: false,
    project_name: GRADE, generated_at: '2026-10-15T00:00:00Z', usage: { preset: 'unknown', ...usage },
    summary: GRADE, ai_status: 'not_requested', ai_summary: null, ai_evidence_ids: [], dimensions: [], coverage_issues: [],
    resource_ids: resources.map(rowId), finding_ids: [], evidence_ids: uniqueSorted(resources.flatMap(evidenceFor)),
    rule_version: 'synthetic-rules/1', model_version: 'not_requested', prompt_version: 'not_requested', facts_hash: factsHash,
    usage_hash: usageHash, resource_evaluations: resources.map(i => ({ resource_id: rowId(i), name: GRADE + '_' + i,
      finding_ids: [], evidence_ids: evidenceFor(i), supported_permission: false })), obligations: [] };
  const binding = { scan_id: assessment.scan_id, assessment_id: assessment.id, assessment_version: 2,
    registry_revision: 3, project_revision: 'synthetic_fixed_revision', facts_hash: factsHash, usage_hash: usageHash,
    rule_version: assessment.rule_version, assessment_sha256: digest(assessment) };
  return { grade: GRADE, assessment, binding };
}
function resource(i, { answer = null, materials = [] } = {}) {
  const gaps = uniqueSorted([...baseGaps, ...(answer ? ['user_statement_not_independently_verified'] : []),
    ...(materials.length ? ['uploaded_material_applicability_pending', 'uploaded_material_incomplete'] : [])]);
  return { subject: subject(i), resource_kind: 'component', state: materials.length ? 'pending' : 'unknown',
    verification_state: 'candidate_only', scope: 'unknown', evidence_ids: evidenceFor(i),
    evidence_source_hashes: Object.fromEntries(evidenceFor(i).map(id => [id, digest({ grade: GRADE, id })])),
    material_ids: [...materials], answer_ids: answer ? [answer.answer_id] : [], gaps,
    advice: useNames.map(key => ({ usage: key, saved_value: usage[key],
      selection: usage[key] === null ? 'UNKNOWN' : usage[key] ? 'SELECTED' : 'NOT_SELECTED',
      state: usage[key] === false ? 'not_selected' : 'unknown', scope: 'RESOURCE', conditions: [],
      gaps: uniqueSorted([...gaps, ...(usage[key] === null ? ['usage_' + key + '_unknown'] : [])]),
      basis_evidence_ids: [], rule_ids: [] })),
    user_assertions: answer ? { [answer.question_code]: answer.answer_code } : {},
    inherited_local_support: false, inherited_support_source: 'PARENT_ASSESSMENT_NOT_NEW_VALUE' };
}
function seal(result) {
  result.result_sha256 = digest(Object.fromEntries(Object.entries(result).filter(([key]) => key !== 'result_sha256')));
  return result;
}
function initial(ctx) {
  return seal({ schema_version: 'openguard-p2-result/1', algorithm_version: 'p2-bound-candidate/1', result_id: 'p2res_synthetic_r1',
    revision: 1, previous_result_id: null, result_sha256: '', binding: copy(ctx.binding), data_scope: 'TEST_ONLY',
    computation: 'DETERMINISTIC_P2B', publication_status: 'succeeded', formal_effect: 'none', model_calls: 0,
    state: 'unknown', created_at: '2026-10-15T00:00:00Z', usage: copy(usage), resources: [1, 2, 3].map(i => resource(i)),
    questions: [
      { question_id: 'p2q_synthetic_scope', question_code: questionCode, origin: 'DETERMINISTIC_P2_NOT_R6_AGGREGATE',
        subjects: [1, 2, 3].map(subject), options: ['YES_INCLUDE', 'NO_EXCLUDE', 'NOT_DECIDED'], scope_rule: 'EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN' },
      { question_id: 'p2q_synthetic_obligation', question_code: 'OBLIGATION_FULFILLMENT_IN_DELIVERY', origin: 'DETERMINISTIC_P2_NOT_R6_AGGREGATE',
        subjects: [1, 2, 3].map(subject), options: ['FULFILLED', 'NOT_FULFILLED', 'NOT_DELIVERED_YET', 'UNKNOWN'], scope_rule: 'EXPLICIT_SUBSET_ONLY_UNMENTIONED_UNKNOWN' },
    ], material_ids: [], answer_ids: [], recomputed_resource_ids: [1, 2, 3].map(rowId), reused_resource_ids: [], companion_summary_id: 'p2sum_synthetic_r1' });
}
function setup() {
  // Each test owns a separate VM/module cache, including the in-memory attempts map.
  const ctx = context(), rt = runtime({ VITE_P2_WORKBENCH: '1' });
  return { ctx, rt, api: rt.load('services/p2.ts') };
}
function answerTransaction(ctx, { selected = [1], evidence = selected.map(i => 'evd_' + i + '_a'), answerCode = 'NOT_DECIDED' } = {}) {
  const before = initial(ctx), question = before.questions[0];
  const request = { question_id: question.question_id, question_code: question.question_code, answer_code: answerCode,
    subjects: selected.map(subject), evidence_ids: [...evidence] };
  // Fixed service writes subjects sorted by resource_id and Evidence sorted by ID.
  const answer = { answer_id: 'ans_synthetic_new', revision: 2, binding: copy(ctx.binding), question_id: request.question_id,
    question_code: request.question_code, answer_code: request.answer_code, subjects: sorted(selected).map(subject), evidence_ids: sorted(evidence),
    provenance: 'USER_ASSERTED', formal_effect: 'none', data_scope: 'TEST_ONLY' };
  const after = copy(before);
  Object.assign(after, { result_id: 'p2res_synthetic_answer_r2', revision: 2, previous_result_id: before.result_id,
    created_at: '2026-10-15T00:00:01Z', answer_ids: [answer.answer_id], recomputed_resource_ids: sorted(selected.map(rowId)),
    reused_resource_ids: [1, 2, 3].filter(i => !selected.includes(i)).map(rowId), companion_summary_id: 'p2sum_synthetic_answer_r2' });
  after.resources = [1, 2, 3].map(i => selected.includes(i) ? resource(i, { answer }) : copy(before.resources[i - 1]));
  seal(after);
  return { grade: GRADE, operation: 'answers', before, request, after, receipt: { result: after, answer, material: null }, selected: sorted(selected.map(rowId)), noop: false };
}
function materialTransaction(ctx, { filename = 'LICENSE', evidence = ['evd_1_a', 'evd_1_b'], priorMaterial = false } = {}) {
  const before = initial(ctx);
  if (priorMaterial) {
    before.result_id = 'p2res_synthetic_previous_material_r2'; before.revision = 2; before.previous_result_id = 'p2res_synthetic_r1';
    before.resources[0] = resource(1, { materials: ['mat_synthetic_existing'] }); before.material_ids = ['mat_synthetic_existing'];
    before.state = 'partial'; before.recomputed_resource_ids = ['cmp_1']; before.reused_resource_ids = ['cmp_2', 'cmp_3'];
    before.companion_summary_id = 'p2sum_synthetic_previous_material_r2'; seal(before);
  }
  const request = { subject: subject(1), evidence_ids: [...evidence], filename,
    content_base64: Buffer.from(materialText).toString('base64'), source_sha256: materialHash,
    source_description: GRADE + ' local unverified observation', completeness: 'EXCERPT' };
  const material = { material_id: 'mat_synthetic_new', revision: 1, binding: copy(ctx.binding), subject: subject(1), evidence_ids: sorted(evidence),
    filename: filename.toUpperCase(), source_sha256: materialHash, byte_count: Buffer.byteLength(materialText), completeness: 'EXCERPT',
    parse_status: 'text_observed', adoption_status: 'adopted_as_unverified_observation', verification_state: 'pending',
    source_level: 'user_supplied_unverified', formal_effect: 'none', data_scope: 'TEST_ONLY' };
  const after = copy(before), materialIds = [...before.material_ids, material.material_id];
  Object.assign(after, { result_id: 'p2res_synthetic_material_r' + (before.revision + 1), revision: before.revision + 1,
    previous_result_id: before.result_id, created_at: '2026-10-15T00:00:02Z', state: 'partial', material_ids: materialIds,
    recomputed_resource_ids: ['cmp_1'], reused_resource_ids: ['cmp_2', 'cmp_3'], companion_summary_id: 'p2sum_synthetic_material_new' });
  after.resources[0] = resource(1, { materials: materialIds }); seal(after);
  return { grade: GRADE, operation: 'materials', before, request, after, receipt: { result: after, answer: null, material }, selected: ['cmp_1'], noop: false };
}
function sameValueTransaction(ctx) {
  const earlier = answerTransaction(ctx, { selected: [1, 2], evidence: ['evd_1_a', 'evd_2_a'] });
  const before = copy(earlier.after), after = copy(before);
  return { ...earlier, before, after, receipt: { result: after, answer: copy(earlier.receipt.answer), material: null }, noop: true };
}

// Independent transaction assertions: these do not invoke any p2.ts validator or
// normalization helper, and distinguish recomputation from exact reused rows.
function assertTransaction(ctx, tx) {
  assert.equal(tx.grade, GRADE);
  assert.deepEqual(tx.before.binding, ctx.binding); assert.deepEqual(tx.after.binding, ctx.binding);
  // Independent fixture precondition from backend context/engine, not a p2.ts helper.
  const storedUsageWithoutDeclaredAt = Object.fromEntries(Object.entries(ctx.assessment.usage).filter(([key]) => key !== 'declared_at'));
  assert.deepEqual(sorted(Object.keys(storedUsageWithoutDeclaredAt)), sorted(['preset', ...useNames]));
  assert.equal(storedUsageWithoutDeclaredAt.preset, 'unknown');
  assert.equal(ctx.binding.usage_hash, digest(storedUsageWithoutDeclaredAt));
  assert.equal(ctx.assessment.usage_hash, ctx.binding.usage_hash);
  // A P2 Result exposes seven usage values; that view alone is not its parent's usage pin.
  assert.deepEqual(sorted(Object.keys(tx.after.usage)), sorted(useNames));
  assert.notEqual(ctx.binding.usage_hash, digest(tx.after.usage));
  assert.deepEqual(tx.after.usage, tx.before.usage); assert.equal(tx.after.formal_effect, 'none'); assert.equal(tx.after.model_calls, 0);
  assert.equal(tx.after.data_scope, 'TEST_ONLY'); assert.equal(tx.before.resources.length, 3); assert.equal(tx.after.resources.length, 3);
  assert.deepEqual(tx.after.resources.map(r => r.subject.resource_id), ctx.assessment.resource_ids);
  assert.equal(tx.after.result_sha256, digest(Object.fromEntries(Object.entries(tx.after).filter(([key]) => key !== 'result_sha256'))));
  if (tx.noop) {
    assert.deepEqual(tx.after, tx.before); assert.ok(tx.receipt.answer.revision <= tx.after.revision); return;
  }
  assert.equal(tx.after.revision, tx.before.revision + 1); assert.equal(tx.after.previous_result_id, tx.before.result_id);
  assert.deepEqual(tx.after.recomputed_resource_ids, tx.selected);
  assert.deepEqual(tx.after.reused_resource_ids, ctx.assessment.resource_ids.filter(id => !tx.selected.includes(id)));
  for (const row of tx.after.resources) {
    const previous = tx.before.resources.find(r => r.subject.resource_id === row.subject.resource_id);
    assert.deepEqual(row.subject, previous.subject); assert.deepEqual(row.evidence_ids, previous.evidence_ids);
    if (!tx.selected.includes(row.subject.resource_id)) { assert.deepEqual(row, previous); continue; }
    if (tx.operation === 'answers') {
      assert.deepEqual(row.answer_ids, [tx.receipt.answer.answer_id]);
      assert.deepEqual(row.user_assertions, { [questionCode]: tx.request.answer_code });
      assert.ok(row.gaps.includes('user_statement_not_independently_verified')); assert.equal(row.state, 'unknown');
    } else {
      assert.deepEqual(row.material_ids, [...previous.material_ids, tx.receipt.material.material_id]);
      assert.deepEqual(row.user_assertions, previous.user_assertions); assert.equal(row.state, 'pending');
      assert.ok(row.gaps.includes('uploaded_material_applicability_pending')); assert.ok(row.gaps.includes('uploaded_material_incomplete'));
    }
    for (const advice of row.advice) {
      assert.deepEqual(advice.gaps, uniqueSorted([...row.gaps, ...(usage[advice.usage] === null ? ['usage_' + advice.usage + '_unknown'] : [])]));
      assert.deepEqual(advice.conditions, []); assert.deepEqual(advice.basis_evidence_ids, []); assert.deepEqual(advice.rule_ids, []);
    }
  }
  const object = tx.receipt.answer ?? tx.receipt.material;
  assert.deepEqual(object.binding, ctx.binding); assert.equal(object.formal_effect, 'none'); assert.equal(object.data_scope, 'TEST_ONLY');
  if (tx.operation === 'answers') {
    assert.equal(object.revision, tx.after.revision); assert.equal(object.provenance, 'USER_ASSERTED');
    const allowed = tx.before.questions.find(q => q.question_id === tx.request.question_id);
    assert.ok(allowed.options.includes(tx.request.answer_code));
    for (const chosen of tx.request.subjects) assert.ok(allowed.subjects.some(s => snapshot(s) === snapshot(chosen)));
    const chosenIds = sorted(tx.request.subjects.map(s => s.resource_id));
    assert.equal(new Set(chosenIds).size, chosenIds.length); assert.deepEqual(chosenIds, tx.selected);
    assert.deepEqual(tx.after.answer_ids, [object.answer_id]);
    assert.deepEqual(tx.after.resources.filter(r => r.answer_ids.includes(object.answer_id)).map(r => r.subject.resource_id), tx.selected);
    const union = new Set(tx.before.resources.filter(r => chosenIds.includes(r.subject.resource_id)).flatMap(r => r.evidence_ids));
    assert.ok(tx.request.evidence_ids.every(e => union.has(e))); assert.equal(new Set(tx.request.evidence_ids).size, tx.request.evidence_ids.length);
  } else {
    assert.equal(object.verification_state, 'pending'); assert.equal(object.source_level, 'user_supplied_unverified');
    assert.deepEqual(tx.after.resources.filter(r => r.material_ids.includes(object.material_id)).map(r => r.subject.resource_id), tx.selected);
    assert.equal(object.byte_count, Buffer.from(tx.request.content_base64, 'base64').length); assert.equal(object.source_sha256, materialHash);
  }
}
function pendingFor(api, ctx, tx, key = 'synthetic_closure_key') {
  const pending = api.prepareWrite(tx.operation, ctx.binding, tx.before, key, copy(tx.request));
  assert.equal(pending.body.parent_result_id, tx.before.result_id); assert.equal(pending.body.expected_revision, tx.before.revision);
  assert.equal(pending.body.idempotency_key, key); assert.equal(pending.serialized, snapshot(pending.body));
  return deepFreeze(pending);
}
async function acceptPost(env, tx) {
  const { ctx, rt, api } = env; assertTransaction(ctx, tx);
  const pending = pendingFor(api, ctx, tx), original = snapshot(pending), receiptOriginal = snapshot(tx.receipt), calls = [];
  deepFreeze(tx.receipt);
  // Supplement the full submit chain with direct validation of the same frozen fixture.
  assert.equal(api.validateSubmittedReceipt(tx.receipt, ctx.assessment, ctx.binding, pending).result.result_id, tx.after.result_id);
  rt.setFetch(async (url, init) => { calls.push({ url, method: init.method ?? 'GET', body: init.body }); return Response.json(tx.receipt, { status: 201 }); });
  const saved = await api.submitWrite(ctx.assessment, ctx.binding, pending);
  assert.equal(saved.result.result_id, tx.after.result_id); assert.equal(saved.result.revision, tx.after.revision);
  assert.equal(api.pendingWriteFor(ctx.assessment), null);
  assert.deepEqual(calls, [{ url: postPath(ctx, tx.operation), method: 'POST', body: pending.serialized }]);
  assert.equal(snapshot(pending), original); assert.equal(snapshot(tx.receipt), receiptOriginal);
  return { saved, pending, calls };
}
async function rejectPost(env, tx, mutate, { mutateRequest = false } = {}) {
  const { ctx, rt, api } = env; assertTransaction(ctx, tx);
  if (mutateRequest) mutate(tx.request, tx); else mutate(tx.receipt, tx);
  const pending = pendingFor(api, ctx, tx), before = snapshot(pending), receiptBefore = snapshot(tx.receipt), calls = [];
  deepFreeze(tx.receipt);
  rt.setFetch(async (url, init) => { calls.push({ url, method: init.method ?? 'GET', body: init.body }); return Response.json(tx.receipt, { status: 201 }); });
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending));
  assert.equal(api.pendingWriteFor(ctx.assessment), pending); assert.equal(api.canReplayWrite(ctx.assessment), false);
  assert.equal(api.canClearWrite(ctx.assessment), false);
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending));
  assert.deepEqual(calls, [{ url: postPath(ctx, tx.operation), method: 'POST', body: pending.serialized }]);
  assert.equal(snapshot(pending), before); assert.equal(snapshot(tx.receipt), receiptBefore);
}

// R1's ten original intentions are retained, with complete transaction fixtures.
test('reference controls preserve valid USER_ASSERTED answer and pending material without Formal escalation', () => {
  const { ctx, api } = setup(), a = answerTransaction(ctx), m = materialTransaction(ctx);
  assertTransaction(ctx, a); assertTransaction(ctx, m);
  assert.equal(api.validateReceipt(a.receipt, ctx.assessment, ctx.binding).answer.provenance, 'USER_ASSERTED');
  assert.equal(api.validateReceipt(a.receipt, ctx.assessment, ctx.binding).answer.answer_code, 'NOT_DECIDED');
  assert.equal(api.validateReceipt(m.receipt, ctx.assessment, ctx.binding).material.verification_state, 'pending');
  assert.equal(a.after.formal_effect, 'none'); assert.equal(m.after.formal_effect, 'none');
  assert.equal(a.after.usage.training, null); assert.equal(a.after.usage.modified, false);
});
for (const [label, change] of [
  ['future answer revision', saved => { saved.answer.revision = saved.result.revision + 1; }],
  ['invalid question ID', saved => { saved.answer.question_id = '../another_question'; }],
  ['empty answer subject subset', saved => { saved.answer.subjects = []; saved.answer.evidence_ids = []; }],
  ['answer ID detached from selected resource', saved => { saved.result.resources[0].answer_ids = []; seal(saved.result); }],
  ['evidence outside selected resource subset', saved => { saved.answer.evidence_ids = ['evd_3_a']; }],
]) test('published reference closure rejects ' + label, () => {
  const { ctx, api } = setup(), tx = answerTransaction(ctx); assertTransaction(ctx, tx); change(tx.receipt);
  // The integrated global-reference closure now rejects a detached Answer at
  // Result validation, before receipt validation; retain both rejection checks.
  if (label === 'answer ID detached from selected resource') {
    assert.throws(() => api.validateResult(tx.receipt.result, ctx.assessment, ctx.binding), /P2/);
  } else assert.equal(api.validateResult(tx.receipt.result, ctx.assessment, ctx.binding).result_id, tx.after.result_id);
  assert.throws(() => api.validateReceipt(tx.receipt, ctx.assessment, ctx.binding), /P2/);
});
test('material global membership cannot substitute for membership on its exact resource', () => {
  const { ctx, api } = setup(), tx = materialTransaction(ctx); assertTransaction(ctx, tx);
  tx.after.resources[0].material_ids = []; tx.after.resources[1].material_ids = [tx.receipt.material.material_id]; seal(tx.after);
  assert.equal(api.validateResult(tx.after, ctx.assessment, ctx.binding).result_id, tx.after.result_id);
  assert.throws(() => api.validateReceipt(tx.receipt, ctx.assessment, ctx.binding), /P2/);
});
test('material exact GET uses the resource closure and never reads or invents content', async () => {
  const { ctx, rt, api } = setup(), tx = materialTransaction(ctx), calls = [];
  tx.after.resources[0].material_ids = []; seal(tx.after);
  rt.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return Response.json(tx.receipt.material); });
  await assert.rejects(api.readMaterial(ctx.assessment, ctx.binding, tx.after, tx.receipt.material.material_id), /P2/);
  assert.deepEqual(calls, [[postPath(ctx, 'materials/' + tx.receipt.material.material_id) + '?assessment_version=2', 'GET']]);
});
test('a mismatched 201 answer receipt remains unconfirmed and is never automatically retried', async () => {
  const env = setup(); await rejectPost(env, answerTransaction(env.ctx), saved => { saved.result.resources[0].answer_ids = []; seal(saved.result); });
});
test('multi-resource answer accepts only the union of its explicit subject Evidence', async () => {
  const env = setup(), tx = answerTransaction(env.ctx, { selected: [1, 2], evidence: ['evd_1_a', 'evd_2_a'] });
  assert.deepEqual(tx.after.recomputed_resource_ids, ['cmp_1', 'cmp_2']); assert.deepEqual(tx.after.reused_resource_ids, ['cmp_3']);
  assert.deepEqual(tx.after.resources[2], tx.before.resources[2]); await acceptPost(env, tx);
});

// F-02 positive controls use the complete prepare -> POST -> submitted receipt chain.
for (const [label, config] of [
  ['single selected Answer', { selected: [1] }],
  ['all resources Answer', { selected: [1, 2, 3] }],
  ['explicit two-resource subset with one-resource Evidence subset', { selected: [1, 2], evidence: ['evd_1_a'] }],
  ['shared Evidence belongs to explicit union', { selected: [1, 2], evidence: ['evd_shared'] }],
  ['empty optional Answer Evidence', { selected: [1, 2], evidence: [] }],
]) test('F02 complete transaction accepts ' + label, async () => { const env = setup(); await acceptPost(env, answerTransaction(env.ctx, config)); });
test('F02 single Material POST keeps two unrelated rows unchanged', async () => {
  const env = setup(), tx = materialTransaction(env.ctx); await acceptPost(env, tx);
  assert.deepEqual(tx.after.resources.slice(1), tx.before.resources.slice(1));
});
test('F01 one resource may own two different Materials without weakening current-ID closure', async () => {
  const env = setup(), tx = materialTransaction(env.ctx, { filename: 'NOTICE', priorMaterial: true });
  assert.deepEqual(tx.after.resources[0].material_ids, ['mat_synthetic_existing', 'mat_synthetic_new']); await acceptPost(env, tx);
});
test('F02 material exact GET accepts pending metadata and does not invent a body', async () => {
  const { ctx, rt, api } = setup(), tx = materialTransaction(ctx), calls = [];
  assertTransaction(ctx, tx);
  rt.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return Response.json(tx.receipt.material); });
  const saved = await api.readMaterial(ctx.assessment, ctx.binding, tx.after, tx.receipt.material.material_id);
  assert.equal(saved.verification_state, 'pending'); assert.equal(saved.source_level, 'user_supplied_unverified');
  for (const key of ['body', 'content', 'content_base64', 'text']) assert.equal(Object.hasOwn(saved, key), false);
  assert.deepEqual(calls, [[postPath(ctx, 'materials/' + saved.material_id) + '?assessment_version=2', 'GET']]);
});

for (const [label, mutate] of [
  ['Material correctly owned plus extra unrelated reverse reference', saved => { saved.result.resources[1].material_ids.push(saved.material.material_id); seal(saved.result); }],
  ['Material missing its owner reference', saved => { saved.result.resources[0].material_ids = []; seal(saved.result); }],
  ['Material wrong subject version', saved => { saved.material.subject.version = '7.0.1'; }],
  ['Material Evidence outside its exact resource', saved => { saved.material.evidence_ids = ['evd_3_a']; }],
]) test('F01 malformed 201 rejects ' + label + ' and keeps one pending POST', async () => {
  const env = setup(); await rejectPost(env, materialTransaction(env.ctx), mutate);
});
for (const [label, mutate] of [
  ['Answer correctly selected plus extra unselected reverse reference', saved => { saved.result.resources[2].answer_ids.push(saved.answer.answer_id); seal(saved.result); }],
  ['Answer missing a selected resource reference', saved => { saved.result.resources[1].answer_ids = []; seal(saved.result); }],
  ['Answer subject wrong version', saved => { saved.answer.subjects[0].version = '7.0.1'; }],
  ['Answer repeats a subject', saved => { saved.answer.subjects.push(copy(saved.answer.subjects[0])); }],
  ['Answer Evidence outside selected resource union', saved => { saved.answer.evidence_ids = ['evd_3_a']; }],
]) test('F01 malformed multi-resource 201 rejects ' + label + ' without automatic replay', async () => {
  const env = setup(); await rejectPost(env, answerTransaction(env.ctx, { selected: [1, 2] }), mutate);
});
for (const [label, mutate] of [
  ['additional reverse resource owner', tx => { tx.after.resources[1].material_ids.push(tx.receipt.material.material_id); seal(tx.after); }],
  ['missing exact owner', tx => { tx.after.resources[0].material_ids = []; seal(tx.after); }],
  ['wrong subject version', tx => { tx.receipt.material.subject.version = '7.0.1'; }],
  ['foreign Evidence', tx => { tx.receipt.material.evidence_ids = ['evd_3_a']; }],
]) test('F01 readMaterial rejects ' + label + ' with one exact GET', async () => {
  const { ctx, rt, api } = setup(), tx = materialTransaction(ctx), calls = []; assertTransaction(ctx, tx); mutate(tx);
  rt.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return Response.json(tx.receipt.material); });
  await assert.rejects(api.readMaterial(ctx.assessment, ctx.binding, tx.after, tx.receipt.material.material_id), /P2/);
  assert.deepEqual(calls, [[postPath(ctx, 'materials/' + tx.receipt.material.material_id) + '?assessment_version=2', 'GET']]);
});

// F-03 comparison normalization must not rewrite a request or silently repair duplicates.
for (const filename of ['LiCeNsE.TxT', 'licence.md', 'Notice.RsT', 'LICENSE']) test('F03 accepts supported ASCII filename normalization ' + filename, async () => {
  const env = setup(), tx = materialTransaction(env.ctx, { filename }); await acceptPost(env, tx);
  assert.equal(tx.request.filename, filename); assert.equal(tx.receipt.material.filename, filename.toUpperCase());
});
test('F03 Material Evidence order may differ without changing frozen body', async () => {
  const env = setup(); await acceptPost(env, materialTransaction(env.ctx, { evidence: ['evd_1_b', 'evd_1_a'] }));
});
test('F03 multi-subject and union Evidence order may differ without mutating arrays', async () => {
  const env = setup(), tx = answerTransaction(env.ctx, { selected: [2, 1], evidence: ['evd_2_b', 'evd_1_a'] });
  assert.deepEqual(tx.request.subjects.map(s => s.resource_id), ['cmp_2', 'cmp_1']);
  assert.deepEqual(tx.receipt.answer.subjects.map(s => s.resource_id), ['cmp_1', 'cmp_2']); await acceptPost(env, tx);
});
for (const [label, mutate] of [
  ['different legal filename', request => { request.filename = 'NOTICE'; }],
  ['different legal extension', request => { request.filename = 'LICENSE.md'; }],
  ['path instead of filename', request => { request.filename = '../LICENSE'; }],
  ['extra filename characters', request => { request.filename = 'LICENSE '; }],
  ['trailing filename LF', request => { request.filename = 'LICENSE\n'; }],
  ['trailing filename CRLF', request => { request.filename = 'LICENSE\r\n'; }],
  ['unsupported extension', request => { request.filename = 'LICENSE.pdf'; }],
  ['non-ASCII lookalike', request => { request.filename = 'LİCENSE'; }],
  ['missing Evidence member', request => { request.evidence_ids.pop(); }],
  ['extra in-resource Evidence member', request => { request.evidence_ids.push('evd_shared'); }],
  ['replaced Evidence member', request => { request.evidence_ids[0] = 'evd_shared'; }],
  ['duplicate request Evidence', request => { request.evidence_ids = ['evd_1_a', 'evd_1_a']; }],
  ['changed source hash', request => { request.source_sha256 = 'c'.repeat(64); }],
  ['changed completeness', request => { request.completeness = 'FULL_TEXT_CLAIMED'; }],
  ['changed subject version', request => { request.subject.version = '7.0.1'; }],
]) test('F03 Material comparison rejects ' + label + ' and preserves original request', async () => {
  const env = setup(); await rejectPost(env, materialTransaction(env.ctx), mutate, { mutateRequest: true });
});
for (const [label, mutate] of [
  ['missing subject', request => { request.subjects.pop(); }],
  ['extra allowed but unsubmitted subject', request => { request.subjects.push(subject(3)); }],
  ['replaced subject member', request => { request.subjects[1] = subject(3); }],
  ['duplicate request subject', request => { request.subjects[1] = copy(request.subjects[0]); }],
  ['changed subject version', request => { request.subjects[0].version = '7.0.1'; }],
  ['missing Evidence member', request => { request.evidence_ids.pop(); }],
  ['extra Evidence member', request => { request.evidence_ids.push('evd_shared'); }],
  ['duplicate request Evidence', request => { request.evidence_ids[1] = request.evidence_ids[0]; }],
  ['foreign replacement Evidence', request => { request.evidence_ids[0] = 'evd_3_a'; }],
  ['changed Answer code', request => { request.answer_code = 'YES_INCLUDE'; }],
  ['changed Question ID', request => { request.question_id = 'p2q_another'; }],
  ['changed Question code', request => { request.question_code = 'OBLIGATION_FULFILLMENT_IN_DELIVERY'; }],
]) test('F03 Answer comparison rejects ' + label + ' despite legal normalization support', async () => {
  const env = setup(); await rejectPost(env, answerTransaction(env.ctx, { selected: [1, 2] }), mutate, { mutateRequest: true });
});
for (const [label, filename] of [['trailing LF', 'LICENSE\n'], ['trailing CRLF', 'LICENSE\r\n']]) test('F03 full-string filename check rejects ' + label + ' on both request and receipt', async () => {
  const env = setup(), tx = materialTransaction(env.ctx);
  await rejectPost(env, tx, (saved, fixture) => { saved.material.filename = filename; fixture.request.filename = filename; });
});
for (const [label, filename] of [['different name', 'NOTICE'], ['different extension', 'LICENSE.MD'], ['path', '../LICENSE'], ['non-ASCII', 'LİCENSE']]) test('F03 returned Material filename rejects ' + label, async () => {
  const env = setup(); await rejectPost(env, materialTransaction(env.ctx), saved => { saved.material.filename = filename; });
});
test('F03 duplicate subjects on both request and receipt cannot be hidden by Set comparison', async () => {
  const env = setup(), tx = answerTransaction(env.ctx); assertTransaction(env.ctx, tx);
  await rejectPost(env, tx, (saved, fixture) => { saved.answer.subjects.push(copy(saved.answer.subjects[0])); fixture.request.subjects.push(copy(fixture.request.subjects[0])); });
});
test('F03 duplicate Evidence on both sides cannot be hidden by Set comparison', async () => {
  const env = setup(), tx = answerTransaction(env.ctx);
  await rejectPost(env, tx, (saved, fixture) => { saved.answer.evidence_ids.push(saved.answer.evidence_ids[0]); fixture.request.evidence_ids.push(fixture.request.evidence_ids[0]); });
});

for (const operation of ['answers', 'materials']) test('F01 ' + operation + ' invalid 201 requires explicit recover before exact original-key/body replay', async () => {
  const { ctx, rt, api } = setup(), tx = operation === 'answers' ? answerTransaction(ctx, { selected: [1, 2] }) : materialTransaction(ctx);
  assertTransaction(ctx, tx); const pending = pendingFor(api, ctx, tx, 'synthetic_recovery_key'), original = snapshot(pending), bad = copy(tx.receipt), calls = [];
  if (operation === 'answers') bad.result.resources[2].answer_ids.push(bad.answer.answer_id);
  else bad.result.resources[1].material_ids.push(bad.material.material_id);
  seal(bad.result); let valid = false;
  rt.setFetch(async (url, init) => {
    calls.push({ url, method: init.method ?? 'GET', body: init.body });
    if (init.method === 'POST') return Response.json(valid ? tx.receipt : bad, { status: 201 });
    if (url === postPath(ctx, 'binding')) return Response.json(ctx.binding);
    if (url === postPath(ctx, 'results') + '?assessment_version=2&offset=0') return Response.json({ head_result_id: tx.before.result_id, head_revision: tx.before.revision, result_ids: [tx.before.result_id], has_more: false });
    if (url === resultPath(ctx, tx.before)) return Response.json(tx.before);
    assert.fail('unexpected offline request ' + url);
  });
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending));
  assert.equal(api.pendingWriteFor(ctx.assessment), pending); assert.equal(api.canReplayWrite(ctx.assessment), false);
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending)); assert.equal(calls.length, 1);
  await api.recoverWrite(ctx.assessment, ctx.binding, pending);
  assert.equal(api.canReplayWrite(ctx.assessment), true); assert.equal(calls.length, 4); assert.equal(snapshot(pending), original);
  valid = true; const saved = await api.submitWrite(ctx.assessment, ctx.binding, pending);
  assert.equal(saved.result.result_id, tx.after.result_id); assert.equal(api.pendingWriteFor(ctx.assessment), null);
  const posts = calls.filter(c => c.method === 'POST'); assert.equal(posts.length, 2);
  assert.equal(posts[0].url, posts[1].url); assert.equal(posts[0].body, pending.serialized); assert.equal(posts[1].body, pending.serialized);
  assert.equal(JSON.parse(posts[1].body).idempotency_key, 'synthetic_recovery_key'); assert.equal(snapshot(pending), original);
});
test('F03 legitimate same-value Answer may return unchanged parent revision', async () => {
  const env = setup(), tx = sameValueTransaction(env.ctx); await acceptPost(env, tx);
  assert.equal(tx.after.result_id, tx.before.result_id); assert.equal(tx.after.revision, tx.before.revision);
});
test('F03 explicit idempotent replay retains the original request and saved revision', async () => {
  const { ctx, rt, api } = setup(), tx = answerTransaction(ctx); assertTransaction(ctx, tx);
  const pending = pendingFor(api, ctx, tx, 'synthetic_idempotent_key'), original = snapshot(pending), bodies = [];
  rt.setFetch(async (_url, init) => { assert.equal(init.method, 'POST'); bodies.push(init.body); return Response.json(tx.receipt, { status: 201 }); });
  const first = await api.submitWrite(ctx.assessment, ctx.binding, pending), replay = await api.submitWrite(ctx.assessment, ctx.binding, pending);
  assert.equal(first.result.result_id, replay.result.result_id); assert.equal(first.result.revision, replay.result.revision);
  assert.deepEqual(bodies, [pending.serialized, pending.serialized]); assert.equal(snapshot(pending), original);
});

for (const status of [403, 404, 409, 413, 422, 503]) test('existing HTTP ' + status + ' classification preserves pending and recovery boundary', async () => {
  const { ctx, rt, api } = setup(), tx = answerTransaction(ctx), pending = pendingFor(api, ctx, tx), original = snapshot(pending), calls = [];
  rt.setFetch(async (url, init) => {
    calls.push([url, init.method ?? 'GET', init.body]);
    if (init.method === 'POST') return Response.json({ error: { code: 'synthetic_rejection', message: GRADE, details: { reason: GRADE } } }, { status });
    if (url.endsWith('/binding')) return Response.json(ctx.binding);
    if (url.includes('/results?')) return Response.json({ head_result_id: tx.before.result_id, head_revision: tx.before.revision, result_ids: [tx.before.result_id], has_more: false });
    return Response.json(tx.before);
  });
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending));
  assert.equal(calls.length, 1); assert.equal(api.pendingWriteFor(ctx.assessment), pending); assert.equal(api.canReplayWrite(ctx.assessment), false);
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending)); assert.equal(calls.length, 1);
  await api.recoverWrite(ctx.assessment, ctx.binding, pending); assert.equal(api.canReplayWrite(ctx.assessment), status === 503);
  if (status !== 503) { await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending)); assert.equal(calls.filter(c => c[1] === 'POST').length, 1); }
  assert.equal(snapshot(pending), original);
});
test('network uncertainty never means unsaved and still requires explicit readback', async () => {
  const { ctx, rt, api } = setup(), tx = answerTransaction(ctx), pending = pendingFor(api, ctx, tx); let posts = 0;
  rt.setFetch(async (_url, init) => { assert.equal(init.method, 'POST'); posts++; throw new TypeError('SYNTHETIC_TEST_ONLY offline transport'); });
  await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending)); assert.equal(api.pendingWriteFor(ctx.assessment), pending);
  assert.equal(api.canReplayWrite(ctx.assessment), false); await assert.rejects(api.submitWrite(ctx.assessment, ctx.binding, pending)); assert.equal(posts, 1);
});
test('successful POST remains saved when auxiliary same-version Summary read fails', async () => {
  const { ctx, rt, api } = setup(), tx = answerTransaction(ctx), pending = pendingFor(api, ctx, tx), calls = [];
  rt.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return init.method === 'POST' ? Response.json(tx.receipt, { status: 201 }) : Response.json({ error: { code: 'synthetic_summary_unavailable' } }, { status: 503 }); });
  const saved = await api.submitWrite(ctx.assessment, ctx.binding, pending), savedSnapshot = snapshot(saved);
  assert.equal(api.pendingWriteFor(ctx.assessment), null); await assert.rejects(api.readSummary(ctx.assessment, saved.result));
  assert.equal(snapshot(saved), savedSnapshot); assert.equal(api.pendingWriteFor(ctx.assessment), null); assert.equal(saved.result.formal_effect, 'none');
  assert.deepEqual(calls, [[postPath(ctx, 'answers'), 'POST'], [postPath(ctx, 'results/' + tx.after.result_id + '/summary') + '?assessment_version=2', 'GET']]);
});
