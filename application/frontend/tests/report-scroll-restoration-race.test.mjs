import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Actual useRoute code, with only the browser scheduling and React hook host
// controlled. A delayed restoration must honor the chapter clicked meanwhile.
function router(url, present = true) {
 const module = { exports: {} }, listeners = {}, frames = [], actions = [], saved = new Map();
 const location = { pathname: '', search: '', hash: '' };
 function setUrl(value) { const parsed = new URL(value, 'http://127.0.0.1'); Object.assign(location, { pathname: parsed.pathname, search: parsed.search, hash: parsed.hash }); }
 setUrl(url);
 const history = { state: { scroll: 37 }, scrollRestoration: '',
  replaceState(state, title, value) { this.state = state; if (value !== undefined) setUrl(value); },
  pushState(state, title, value) { this.state = state; setUrl(value); } };
 const target = { scrollIntoView(options) { actions.push(['anchor', { ...options }]); } };
 const window = { location, history, scrollY: 37,
  addEventListener(name, listener) { listeners[name] = listener; }, removeEventListener() {},
  scrollTo(x, y) { actions.push(['window', x, y]); } };
 const source = fs.readFileSync(new URL('../src/hooks/useRoute.ts', import.meta.url), 'utf8');
 vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, {
  module, exports: module.exports, window, location, history, URLSearchParams,
  document: { getElementById(id) { return present && ['report-0', 'report-1', 'report-2', 'report-3', 'report-4', 'report-5', 'workflow', 'capability'].includes(id) ? target : null; } },
  requestAnimationFrame(fn) { frames.push(fn); },
  sessionStorage: { getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value) },
  require: name => name === 'react' ? { useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}], useEffect: effect => effect() }
   : name === '../services/scans' ? { defaultMode: 'api' } : (() => { throw Error('unexpected module ' + name); })(),
 });
 return { ...module.exports.useRoute(), setUrl, actions, listeners, history, flush() { while (frames.length) frames.shift()(); } };
}

for (let chapter = 0; chapter < 6; chapter++) test(`late popstate restoration honors report chapter ${chapter + 1}`, () => {
 const h = router(`/app/scans/scn_exact/report?assessment_id=asm_exact&p2_result=p2res_exact#report-${chapter}`);
 h.listeners.popstate(); h.flush();
 assert.deepEqual(h.actions, [['anchor', { block: 'start', behavior: 'instant' }]]);
});

test('a chapter clicked before pending go RAF is not overwritten by page-top restoration', () => {
 const h = router('/app/scans/scn_exact/overview?mode=api');
 h.go('/app/scans/scn_exact/report?assessment_id=asm_exact&p2_result=p2res_exact');
 h.setUrl('/app/scans/scn_exact/report?assessment_id=asm_exact&p2_result=p2res_exact#report-5');
 h.flush();
 assert.deepEqual(h.actions, [['anchor', { block: 'start', behavior: 'instant' }]]);
});

for (const [path, present] of [
 ['/app/scans/scn_exact/report?mode=api#report-99', true],
 ['/app/scans/scn_exact/report?mode=api#other', true],
 ['/app/scans/scn_exact/report?mode=api#report-5', false],
 ['/app/scans/scn_exact/report-v2?mode=api#report-5', true],
 ['/app/scans/scn_exact/overview?mode=api#report-5', true],
]) test('unknown, missing and other-page anchors retain saved-scroll fallback: ' + path + present, () => {
 const h = router(path, present); h.listeners.popstate(); h.flush();
 assert.deepEqual(h.actions, [['window', 0, 37]]);
});

test('homepage workflow anchor behavior remains unchanged', () => {
 const h = router('/#workflow'); h.listeners.popstate(); h.flush();
 assert.deepEqual(h.actions, [['anchor', { block: 'start', behavior: 'instant' }]]);
});
