import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const usageFields = { commercial: '商业使用', distributed: '分发', modified: '修改' };
const binding = { scan_id: 'scn_test', assessment_id: 'asm_test', assessment_version: 1 };
const assessment = { id: binding.assessment_id, scan_id: binding.scan_id, version: binding.assessment_version };
const subject = { resource_id: 'cmp_example', version: '1.2.3' };
const scan = { id: binding.scan_id, resources: [{ id: subject.resource_id, name: 'fixture-example', version: subject.version }], evidence: [] };
const result = {
  result_id: 'p2res_current', result_sha256: '1'.repeat(64), revision: 2, previous_result_id: 'p2res_previous',
  data_scope: 'TEST_ONLY', binding, usage: { commercial: true, distributed: true, modified: false },
  resources: [{ subject, state: 'pending', gaps: [], material_ids: ['p2mat_license', 'p2mat_notice'], evidence_ids: [], advice: [] }],
  material_ids: ['p2mat_license', 'p2mat_notice'], recomputed_resource_ids: [subject.resource_id], reused_resource_ids: [],
  questions: [{ question_id: 'question_1', question_code: 'DELIVERY_SCOPE_FOR_RESOURCES', options: [], subjects: [subject] }],
};
const declarationSnapshot = { sources: [] };
const view = {
  revision: result.revision, data_scope: 'TEST_ONLY',
  materials: [
    { material_id: 'p2mat_license', filename: 'LICENSE', subject, parse_state: 'MATCHED_APACHE_2_0',
      adoption_state: 'CONDITIONAL_TEXT_BASIS', declared_spdx: 'Apache-2.0', text_license: 'Apache-2.0',
      license_version: '2.0', role: 'root_package', role_state: 'inferred', role_conflicts: [],
      evidence: [], role_basis_evidence_ids: [], byte_count: 1, source_sha256: '2'.repeat(64), clauses: [] },
    { material_id: 'p2mat_notice', filename: 'NOTICE', subject, parse_state: 'NOTICE_OBSERVED',
      adoption_state: 'OBSERVATION_ONLY', declared_spdx: 'Apache-2.0', text_license: 'UNKNOWN',
      license_version: null, role: 'root_package', role_state: 'inferred', role_conflicts: [],
      evidence: [], role_basis_evidence_ids: [], byte_count: 1, source_sha256: '3'.repeat(64), clauses: [] },
  ],
  advice: [
    { usage: 'commercial', subject, state: 'UNKNOWN', claim_ids: ['claim_1'],
      reasons: ['NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW'], conditions: [], limitations: [] },
    { usage: 'distributed', subject, state: 'UNKNOWN', claim_ids: ['claim_2'],
      reasons: ['NOTICE_REQUIRES_REVIEW'], conditions: [], limitations: [] },
    { usage: 'modified', subject, state: 'NOT_COVERED', claim_ids: ['claim_3'],
      reasons: ['USE_NOT_SELECTED'], conditions: [], limitations: [] },
  ],
  claims: [],
  declaration_observations: [{ subject, expression: 'Apache-2.0', normalized_ids: ['Apache-2.0'], evidence_status: 'COMPLETE', evidence: [] }],
  source_observations: [],
  incremental_impact: {
    mode: 'INCREMENTAL_DERIVED', previous_revision: 1, affected_resource_ids: [subject.resource_id], unchanged_resource_ids: [],
    recomputed_claim_ids: ['claim_1', 'claim_2', 'claim_3'], reused_claim_ids: [], added_material_ids: ['p2mat_notice'], added_answer_ids: [],
    changed_claims: [{ current_claim_id: 'claim_1', subject, usage: 'commercial', previous_state: 'SUPPORT', current_state: 'UNKNOWN',
      current_reasons: ['NOTICE_MATCHED_REQUIRES_HUMAN_OBLIGATION_REVIEW'], trigger_material_ids: ['p2mat_notice'], trigger_answer_ids: [] }],
  },
};
const jsx = (type, props) => ({ type, props });
const treeNodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(treeNodes)
  : [value, ...treeNodes(value.props?.children)];
const rendered = value => value == null || typeof value === 'boolean' ? '' : Array.isArray(value) ? value.map(rendered).join('')
  : typeof value === 'object' ? rendered(value.props?.children) : String(value);
const byData = (root, key) => treeNodes(root).filter(node => Object.hasOwn(node.props ?? {}, key));

function loadComponent(name, hooks, dependencies = {}) {
  const source = fs.readFileSync(new URL('../src/components/' + name + '.tsx', import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } });
  const module = { exports: {} };
  vm.runInNewContext(outputText, { module, exports: module.exports, AbortController, Error,
    require(specifier) {
      if (specifier === 'react') return hooks;
      if (specifier === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
      if (specifier in dependencies) return dependencies[specifier];
      return new Proxy({}, { get: (_obj, key) => key });
    },
  });
  return module.exports[name];
}

function renderClaims(record = result, dto = view) {
  const key = JSON.stringify([assessment.scan_id, assessment.id, assessment.version, record.result_id,
    record.result_sha256, record.binding, declarationSnapshot]);
  let slot = 0;
  const panel = loadComponent('MaterialClaimsPanel', {
    useState(initial) { return [slot++ === 2 ? { key, current: dto } : initial, () => {}]; },
    useEffect() {},
  }, { '../services/assessments': { usageFields } });
  return panel({ assessment, result: record, declarationSnapshot, resourceName: () => 'fixture-example' });
}

test('P5 overview reports exact object, selected uses, all five states and separate review boundaries', () => {
  const [overview] = byData(renderClaims(), 'data-p5-assessment-overview');
  assert.ok(overview);
  const body = rendered(overview);
  for (const text of ['本次研判概览', 'fixture-example', '1.2.3', 'r2', 'TEST_ONLY', '商业使用', '分发',
    '证据充分程度', '条款适用性未人工签认', '下一步', 'NOTICE']) assert.ok(body.includes(text), text);
  assert.doesNotMatch(body, /所选用途[^。]*修改/);
  const counts = Object.fromEntries(byData(overview, 'data-claim-state').map(node => [node.props['data-claim-state'], Number(rendered(node).match(/\d+/)?.[0])]));
  assert.deepEqual(counts, { SUPPORT: 0, RESTRICTION: 0, UNKNOWN: 2, COUNTER_EVIDENCE: 0, NOT_COVERED: 1 });
});

test('P5 places five stages on each material and distinguishes added from carried material', () => {
  const cards = byData(renderClaims(), 'data-p5-material-card');
  assert.equal(cards.length, 2);
  assert.equal(cards[0].props['data-parse-state'], 'MATCHED_APACHE_2_0');
  assert.equal(cards[1].props['data-parse-state'], 'NOTICE_OBSERVED');
  for (const card of cards) {
    const [chain] = byData(card, 'data-p5-material-chain');
    assert.deepEqual(byData(chain, 'data-stage').map(n => n.props['data-stage']),
      ['uploaded', 'parsed', 'bound', 'adoption', 'incremental']);
    assert.match(rendered(chain), /已上传.*已解析.*已绑定本版.*采用状态.*增量触发/);
  }
  assert.equal(cards[0].props['data-incremental-trigger'], 'false');
  assert.equal(cards[1].props['data-incremental-trigger'], 'true');
});

test('P5 derived impact defaults open with native summary and exact triggers; initial hides impact', () => {
  const [impact] = byData(renderClaims(), 'data-p5-incremental-impact');
  assert.ok(impact);
  assert.equal(impact.type, 'details');
  assert.equal(impact.props.open, true);
  assert.ok(treeNodes(impact).some(n => n.type === 'summary' && !Object.hasOwn(n.props, 'tabIndex')));
  assert.match(rendered(impact), /r1 → r2/);
  assert.match(rendered(impact), /重算 1 个资源、3 条主张/);
  assert.match(rendered(impact), /保留 0 个资源、0 条主张/);
  assert.match(rendered(impact), /触发材料：p2mat_notice/);
  assert.equal(byData(renderClaims({ ...result, revision: 1, previous_result_id: null },
    { ...view, revision: 1, incremental_impact: { ...view.incremental_impact, mode: 'INITIAL_RESULT' } }), 'data-p5-incremental-impact').length, 0);
});

function renderWorkbench({ readOnly = false, historical = false } = {}) {
  const effects = [], state = [], calls = [];
  let slot = 0;
  const hooks = {
    useState(initial) {
      const index = slot++;
      if (!Object.hasOwn(state, index)) {
        const pinned = { 0: binding, 1: { head_result_id: historical ? 'p2res_other' : result.result_id, result_ids: [result.result_id] }, 2: result, 3: false };
        state[index] = Object.hasOwn(pinned, index) ? pinned[index] : typeof initial === 'function' ? initial() : initial;
      }
      return [state[index], value => { state[index] = typeof value === 'function' ? value(state[index]) : value; }];
    },
    useEffect(effect) { effects.push(effect); },
    useLayoutEffect() {},
    useRef(value) { return { current: value }; },
  };
  const Workbench = loadComponent('P2Workbench', hooks, {
    '../services/assessments': { usageFields, assessmentReportUrl: () => '/report' },
    '../services/p2': { pendingWriteFor: () => null, sameBinding: () => true, stateLabels: { pending: '待核验' }, gapLabel: value => value,
      resultPageUrl: (_a, id) => '/exact/' + id,
      prepareWrite: () => { calls.push('write'); throw Error('unexpected write'); } },
    '../services/officialSources': { officialSourcesEnabled: false },
    '../services/p2Ai': { p2AiEnabled: false },
    '../services/projectUsage': { readPendingUsageUpdate: () => null },
    '../services/preliminaryAdvice': { readPreliminaryAdvice: async (_a, r) => {
      calls.push(r.result_id); throw Error('legacy profile incompatible');
    } },
  });
  return {
    calls,
    render() {
      slot = 0;
      effects.length = 0;
      const tree = Workbench({ assessment, scan, readOnly });
      return { tree, compatibility: effects.find(effect => effect.toString().includes('readPreliminaryAdvice')) };
    },
  };
}

test('P5 legacy MIT compatibility fetch requires explicit expansion and keeps explicit failures visible', async () => {
  const h = renderWorkbench();
  const initial = h.render();
  initial.compatibility();
  assert.equal(h.calls.length, 0);
  const details = treeNodes(initial.tree).find(n => n.type === 'details' && n.props.className?.includes('p2-prior-evidence'));
  assert.ok(details);
  details.props.onToggle({ currentTarget: { open: true } });
  h.render().compatibility();
  assert.deepEqual(h.calls, [result.result_id]);
  await new Promise(resolve => setImmediate(resolve));
  const alert = treeNodes(h.render().tree).find(n => n.props.role === 'alert' && rendered(n).includes('legacy profile incompatible'));
  assert.ok(alert);
});

test('P5 readonly or historical guards remain disabled at the UI and handler, while writable TEST_ONLY stays eligible', () => {
  for (const options of [{ readOnly: true }, { historical: true }, {}]) {
    const h = renderWorkbench(options);
    const { tree } = h.render();
    const nodes = treeNodes(tree);
    const materials = nodes.find(n => typeof n.type === 'function' && n.type.name === 'MaterialForm');
    const answers = nodes.find(n => typeof n.type === 'function' && n.type.name === 'AnswerForm');
    const disabled = !!(options.readOnly || options.historical);
    assert.equal(materials.props.disabled, disabled);
    assert.equal(answers.props.disabled, disabled);
    if (disabled) answers.props.onSubmit({ answer_code: 'YES_INCLUDE' });
    assert.equal(h.calls.length, 0);
    assert.ok(nodes.some(n => n.type === 'a' && n.props.href === '/exact/' + result.previous_result_id));
    assert.match(rendered(tree), /MIT 与 Apache-2\.0/);
    assert.match(rendered(tree), /NOTICE 需人工核对/);
  }
});
