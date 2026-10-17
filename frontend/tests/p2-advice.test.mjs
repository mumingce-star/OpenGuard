import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { runtime } from './runtime.mjs';

const sha = 'a'.repeat(64);
const binding = () => ({
  scan_id: 'scn_1', assessment_id: 'asm_1', assessment_version: 6, registry_revision: 13,
  project_revision: null, facts_hash: sha, usage_hash: sha, rule_version: 'assessment-1', assessment_sha256: sha,
});
const result = () => ({
  schema_version: 'openguard-p2-result/1', algorithm_version: 'p2-bound-candidate/1',
  result_id: 'p2res_1', revision: 2, previous_result_id: 'p2res_0', result_sha256: sha,
  binding: binding(), data_scope: 'TEST_ONLY', computation: 'DETERMINISTIC_P2B',
  publication_status: 'succeeded', formal_effect: 'none', model_calls: 0,
  state: 'pending', created_at: '2026-10-10T00:00:00Z', usage: { commercial: null },
  resources: [{
    subject: { resource_id: 'cmp_1', version: '7.0.0' }, resource_kind: 'component',
    state: 'pending', verification_state: 'candidate_only', scope: 'resource',
    evidence_ids: ['ev_1', 'ev_missing'], evidence_source_hashes: {}, material_ids: ['p2mat_1'], answer_ids: [],
    gaps: ['upstream_source_attestation_missing'], user_assertions: {}, inherited_local_support: false,
    inherited_support_source: 'PARENT_ASSESSMENT_NOT_NEW_VALUE',
    advice: [{
      usage: 'commercial', saved_value: false, selection: 'NOT_SELECTED', state: 'not_selected', scope: 'RESOURCE',
      conditions: [], gaps: ['applicability_human_verified_missing'], basis_evidence_ids: ['ev_1'], rule_ids: [],
    }],
  }], questions: [], material_ids: ['p2mat_1'], answer_ids: [],
  recomputed_resource_ids: ['cmp_1'], reused_resource_ids: [], companion_summary_id: 'p2sum_1',
});

test('P2 L1 read uses only exact binding, index and immutable result GETs', async () => {
  const r = runtime(), api = r.load('services/p2Advice.ts'), calls = [];
  r.setFetch(async (url, options) => {
    calls.push([url, options.method ?? 'GET']);
    if (url.endsWith('/binding')) return Response.json(binding());
    if (url.includes('/results?')) return Response.json({ head_result_id: 'p2res_1', head_revision: 2, result_ids: ['p2res_1'], has_more: false });
    return Response.json(result());
  });
  const loaded = await api.readP2Advice('scn_1', 'asm_1', 6);
  assert.equal(loaded.result_id, 'p2res_1');
  assert.deepEqual(calls.map(([, method]) => method), ['GET', 'GET', 'GET']);
  assert.match(calls[1][0], /\/scans\/scn_1\/assessments\/asm_1\/p2\/results\?assessment_version=6$/);
  assert.match(calls[2][0], /\/results\/p2res_1\?assessment_version=6$/);
  assert.equal(r.storage.size, 0);
});

test('empty saved P2 result remains empty and never creates a result', async () => {
  const r = runtime(), api = r.load('services/p2Advice.ts'), calls = [];
  r.setFetch(async (url, options) => {
    calls.push(options.method ?? 'GET');
    return Response.json(url.endsWith('/binding') ? binding() : { head_result_id: null, head_revision: 0, result_ids: [], has_more: false });
  });
  assert.equal(await api.readP2Advice('scn_1', 'asm_1', 6), null);
  assert.deepEqual(calls, ['GET', 'GET']);
});

test('wrong assessment, stale version and changed parent binding reject before display', async () => {
  const cases = [
    { binding: { ...binding(), assessment_id: 'asm_other' }, index: null, result: null },
    { binding: { ...binding(), assessment_version: 5 }, index: null, result: null },
    { binding: binding(), index: { head_result_id: 'p2res_1', head_revision: 2, result_ids: ['p2res_1'], has_more: false }, result: { ...result(), binding: { ...binding(), facts_hash: 'b'.repeat(64) } } },
    { binding: binding(), index: { head_result_id: 'p2res_1', head_revision: 3, result_ids: ['p2res_1'], has_more: false }, result: result() },
  ];
  for (const item of cases) {
    const r = runtime(), api = r.load('services/p2Advice.ts');
    r.setFetch(async url => Response.json(url.endsWith('/binding') ? item.binding : url.includes('/results?') ? item.index : item.result));
    await assert.rejects(api.readP2Advice('scn_1', 'asm_1', 6), /契约|版本/);
  }
});

test('P2 presentation keeps TEST_ONLY, pending, missing evidence and not selected semantics', () => {
  const r = runtime(), api = r.load('services/p2Advice.ts');
  const component = r.load('components/P2AdvicePanel.tsx');
  const parsed = api.validateP2Result(result(), binding());
  const html = renderToStaticMarkup(createElement(component.P2ResultView, {
    result: parsed, evidenceIds: ['ev_1'], onEvidence: () => {},
  }));
  assert.match(html, /受控验收数据/);
  assert.match(html, /待核验/);
  assert.match(html, /未选择，不代表不适用/);
  assert.match(html, /ev_missing 未在本次扫描中定位/);
  assert.match(html, /不能据此认定没有义务/);
  assert.doesNotMatch(html, /已核验|已授权|项目已合规/);
});

test('L1 main card shows the returned resource, usage judgment, conditions, gaps and Evidence before details', () => {
  const r = runtime(), component = r.load('components/P2AdvicePanel.tsx');
  const positive = result();
  positive.state = 'candidate'; positive.resources[0].state = 'candidate';
  positive.resources[0].evidence_source_hashes = { ev_1: sha };
  positive.resources[0].advice[0] = {
    usage: 'commercial', saved_value: true, selection: 'SELECTED', state: 'conditional_candidate', scope: 'RESOURCE',
    conditions: ['保留后端列出的许可证文本'], gaps: ['上游适用性尚未核验'], basis_evidence_ids: ['ev_1'], rule_ids: ['RULE-1'],
  };
  const html = renderToStaticMarkup(createElement(component.P2ResultView, {
    result: positive, evidenceIds: ['ev_1'], onEvidence: () => {},
  }));
  const main = html.slice(html.indexOf('og-p2-main'), html.indexOf('og-p2-resource'));
  for (const expected of ['L1资源级用途建议', 'cmp_1', '7.0.0', '商业', '条件候选', '保留后端列出的许可证文本',
    '上游适用性尚未核验', '查看 Evidence：ev_1', '材料观察引用：p2mat_1', '查看本资源源文件 Hash', sha]) assert.match(main, new RegExp(expected));
  assert.match(main, /不等于已获授权/);
  assert.match(main, /不是官方来源证明/);
  assert.doesNotMatch(main, /项目已合规/);
});

test('L1 partial and no-advice cases do not invent a permitted usage or a deleted resource', () => {
  const component = runtime().load('components/P2AdvicePanel.tsx');
  const partial = result(); partial.state = 'partial'; partial.resources[0].advice = [];
  partial.resources[0].scope = 'unknown';
  const html = renderToStaticMarkup(createElement(component.P2ResultView, {
    result: partial, evidenceIds: [], onEvidence: () => {},
  }));
  assert.match(html, /未出现的资源不能据此视为已删除/);
  assert.match(html, /后端未返回该资源的用途判断/);
  assert.match(html, /适用范围：<\/strong>未知，待核验/);
  assert.match(html, /ev_1 未在本次扫描中定位/);
  assert.match(html, /本资源源文件 Hash 未获取/);
  const empty = { ...result(), resources: [] };
  assert.match(renderToStaticMarkup(createElement(component.P2ResultView, { result: empty, evidenceIds: [], onEvidence: () => {} })), /不能由此推断扫描范围完整/);
});

test('contract failure never promotes unknown to a candidate', () => {
  const api = runtime().load('services/p2Advice.ts');
  const invalid = result();
  invalid.resources[0].verification_state = 'verified';
  assert.throws(() => api.validateP2Result(invalid, binding()), /契约/);
  invalid.resources[0].verification_state = 'candidate_only';
  invalid.formal_effect = 'updated';
  assert.throws(() => api.validateP2Result(invalid, binding()), /契约/);
  assert.equal(api.p2StateLabels.unknown, '未知，证据不足');
});

test('L1 read errors distinguish fixed-object absence, service outage and binding conflict', () => {
  const r = runtime(), { ApiError } = r.load('services/scans.ts');
  const { p2ReadErrorText } = r.load('components/P2Workbench.tsx');
  assert.match(p2ReadErrorText(new ApiError(404, 'missing')), /不会改选最新版本/);
  assert.match(p2ReadErrorText(new ApiError(503, 'disabled')), /Formal Assessment 仍可单独查看/);
  assert.match(p2ReadErrorText(new ApiError(409, 'conflict')), /不会展示不匹配的建议/);
  assert.match(p2ReadErrorText(new Error('network')), /network/);
});

test('P2B source hashes and suggestion basis stay inside the returned resource Evidence closure', () => {
  const { validateP2Result } = runtime().load('services/p2Advice.ts');
  const valid = result();
  valid.resources[0].evidence_source_hashes = { ev_1: sha };
  assert.equal(validateP2Result(valid, binding()).result_id, 'p2res_1');
  const wrongSource = structuredClone(valid);
  wrongSource.resources[0].evidence_source_hashes = { ev_other: sha };
  assert.throws(() => validateP2Result(wrongSource, binding()), /契约/);
  const wrongBasis = structuredClone(valid);
  wrongBasis.resources[0].advice[0].basis_evidence_ids = ['ev_other'];
  assert.throws(() => validateP2Result(wrongBasis, binding()), /契约/);
});

test('P2B material, answer and recomputation references cannot escape the fixed Result', () => {
  const { validateP2Result } = runtime().load('services/p2Advice.ts');
  const cases = [
    value => { value.resources[0].material_ids = ['p2mat_other']; },
    value => { value.resources[0].answer_ids = ['p2ans_other']; },
    value => { value.material_ids.push('p2mat_orphan'); },
    value => { value.answer_ids.push('p2ans_orphan'); },
    value => { value.reused_resource_ids = ['cmp_1']; },
    value => { value.recomputed_resource_ids = ['cmp_other']; },
    value => { value.resources.push(structuredClone(value.resources[0])); },
  ];
  for (const mutate of cases) {
    const invalid = result(); mutate(invalid);
    assert.throws(() => validateP2Result(invalid, binding()), /契约/);
  }
});
