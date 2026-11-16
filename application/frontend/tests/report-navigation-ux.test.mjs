import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value) ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
const serial = value => JSON.parse(JSON.stringify(value));
function render({ reduced = false, hash = '', missing = false } = {}) {
  const m = { exports: {} }, effects = [], actions = [];
  const href = '/app/scans/scn_fixed/report?assessment_id=asm_fixed&assessment_version=1&mode=api&p2_result=p2res_fixed';
  const location = { pathname: href.split('?')[0], search: '?' + href.split('?')[1], hash };
  const targets = Object.fromEntries(Array.from({ length: 6 }, (_, i) => ['report-' + i, {
    focus(options) { actions.push(['focus', i, serial(options)]); },
    scrollIntoView(options) { actions.push(['scroll', i, serial(options)]); },
  }]));
  const win = {
    location,
    history: { state: { scroll: 1, ownerState: 'preserved' }, replaceState(state, title, url) { actions.push(['replace', serial(state), title, url]); } },
    matchMedia(query) { assert.equal(query, '(prefers-reduced-motion: reduce)'); return { matches: reduced }; },
  };
  const source = fs.readFileSync(new URL('../src/pages/Report.tsx', import.meta.url), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, {
    module: m, exports: m.exports, window: win,
    document: { getElementById(id) { return missing ? null : targets[id] ?? null; } },
    addEventListener() {}, removeEventListener() {},
    require: name => name === 'react/jsx-runtime' ? { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }
      : name === 'react' ? { useEffect: fn => effects.push(fn), useState: initial => [initial, () => {}] }
      : name === 'react-dom' ? { flushSync: fn => fn() }
      : name.endsWith('/components/ui') ? { Header: 'Header', useNotice: () => () => {}, download() {} }
      : name.endsWith('/services/scans') ? { reportDownloadUrl: () => '/download' }
      : name.endsWith('/services/assessmentPresentation') ? { presentDiagnostic: d => ({ title: d.code, detail: d.message }) }
      : name.endsWith('/services/model') ? { summarize: () => ({ resources: 0, risks: 0 }), groupRisks: () => [], riskCounts: () => ({ resources: 0, counts: {} }), reportPayload: () => ({}) }
      : name.endsWith('/types/domain') ? { statusLabels: { completed: '扫描完成' }, severityLabels: {} }
      : (() => { throw new Error('unexpected module ' + name); })(),
  });
  const tree = m.exports.Report({ scan: { id: 'scn_fixed', project: 'fixed', mode: 'api', status: 'completed', risks: [], resources: [], evidence: [], reportFormats: [] } });
  const nav = nodes(tree).find(node => node.type === 'nav' && node.props['aria-label'] === '报告目录');
  const links = nodes(nav).filter(node => node.type === 'a');
  const sections = nodes(tree).filter(node => node.type === 'section' && /^report-[0-5]$/.test(node.props.id));
  return { actions, links, sections, effects, href, location, win };
}
function click(link, override = {}) {
  let prevented = false;
  assert.equal(typeof link.props.onClick, 'function', 'report links need explicit same-document navigation');
  link.props.onClick({ button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, defaultPrevented: false, preventDefault() { prevented = true; }, ...override });
  return prevented;
}
for (let i = 0; i < 6; i++) test(`report chapter ${i + 1} scrolls and focuses without dropping immutable URL binding`, () => {
  const h = render();
  assert.equal(h.links.length, 6);
  assert.equal(h.links[i].props.href, '#report-' + i);
  assert.equal(click(h.links[i]), true);
  assert.deepEqual(h.actions, [
    ['replace', { scroll: 1, ownerState: 'preserved' }, '', h.href + '#report-' + i],
    ['focus', i, { preventScroll: true }],
    ['scroll', i, { behavior: 'smooth', block: 'start' }],
  ]);
  assert.equal(h.sections[i].props.tabIndex, -1);
  assert.equal(h.sections[i].props.style.scrollMarginTop, '100px');
});
test('report navigation honors reduced motion', () => { const h = render({ reduced: true }); click(h.links[5]); assert.equal(h.actions.at(-1)[2].behavior, 'auto'); });
for (const override of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }, { defaultPrevented: true }]) test('report navigation preserves modified browser action ' + JSON.stringify(override), () => {
  const h = render(); assert.equal(click(h.links[0], override), false); assert.deepEqual(h.actions, []);
});
test('report missing target does not change URL or steal focus', () => { const h = render({ missing: true }); assert.equal(click(h.links[0]), false); assert.deepEqual(h.actions, []); });
test('report exact fragment restores its section after async content mounts', () => {
  const h = render({ hash: '#report-4' }); h.effects.forEach(effect => effect());
  assert.deepEqual(h.actions, [['focus', 4, { preventScroll: true }], ['scroll', 4, { behavior: 'auto', block: 'start' }]]);
});
for (const hash of ['', '#report-99', '#other']) test('report ignores nonchapter fragment ' + JSON.stringify(hash), () => {
  const h = render({ hash }); h.effects.forEach(effect => effect()); assert.deepEqual(h.actions, []);
});
