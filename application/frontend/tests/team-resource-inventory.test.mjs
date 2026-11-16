// TEAM-CODE-REVIEW-01: authored, NOT_RUN. All transport/body/UI data below is
// TEST_ONLY; no captured business response, browser, network or database is used.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { runtime } from './runtime.mjs';

const csv = 'resource_id,name,version\nTEST_ONLY,is-number,7.0.0\n';
function headers(bytes = Buffer.from(csv)) {
  const h = createHash('sha256').update(bytes);
  const hex = h.digest('hex');
  return { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Length': String(bytes.length),
    'ETag': `"sha256:${hex}"`, 'Content-Digest': `sha-256=:${Buffer.from(hex, 'hex').toString('base64')}:` };
}
function setup(env = {}) {
  const rt = runtime(env), saved = [], blobs = [], revoked = [], timers = [], redirects = [];
  class LocalURL extends URL {
    static createObjectURL(blob) { blobs.push(blob); return 'blob:TEST_ONLY-' + blobs.length; }
    static revokeObjectURL(url) { revoked.push(url); }
  }
  Object.assign(rt.shared, { Blob, Headers, TextDecoder, TextEncoder, Uint8Array, btoa,
    crypto: webcrypto, URL: LocalURL,
    document: { body: { append() {} }, createElement() { return {
      href: '', download: '', click() { saved.push({ href: this.href, filename: this.download }); }, remove() {},
    }; } },
    window: { setTimeout(fn) { timers.push(fn); return 1; }, location: {
      pathname: '/app/scans/scn_test/resources', search: '?mode=api', replace: url => redirects.push(url),
    } },
  });
  const service = rt.load('services/resourceInventory.ts');
  return { rt, service, saved, blobs, revoked, timers, redirects,
    run: signal => service.downloadResourceInventory('scn_test', signal ?? new AbortController().signal) };
}

test('fixed current-scan URL, authenticated GET and exact bytes saved only after digest validation', async () => {
  const h = setup({ VITE_ACCOUNT_AUTH: '1' });
  let calls = 0;
  h.rt.setFetch(async (url, options) => {
    calls++;
    assert.equal(url, '/api/v1/scans/scn_test/report?format=resource_inventory&download=true');
    assert.equal(options.method, 'GET'); assert.equal(options.redirect, 'error');
    assert.equal(options.cache, 'no-store'); assert.equal(options.credentials, 'same-origin');
    assert.equal(new Headers(options.headers).get('Accept'), 'text/csv');
    assert.ok(options.signal instanceof AbortSignal);
    return new Response(csv, { headers: headers() });
  });
  await h.run();
  assert.equal(calls, 1); assert.equal(h.saved.length, 1);
  assert.equal(h.saved[0].filename, 'scn_test-resources.csv');
  assert.equal(await h.blobs[0].text(), csv);
  h.timers.forEach(fn => fn()); assert.deepEqual(h.revoked, ['blob:TEST_ONLY-1']);
});
for (const status of [401, 409, 500, 503]) test(`HTTP ${status}: safe failure, no save or automatic retry`, async () => {
  const h = setup({ VITE_ACCOUNT_AUTH: '1' }); let calls = 0;
  h.rt.setFetch(async () => { calls++; return new Response('PRIVATE_SERVER_DETAIL', { status }); });
  await assert.rejects(h.run(), e => e.message.includes(String(status)) && !e.message.includes('PRIVATE'));
  assert.equal(calls, 1); assert.equal(h.saved.length, 0); assert.equal(h.blobs.length, 0);
  assert.equal(h.redirects.length, status === 401 ? 1 : 0);
});
for (const [label, change] of [
  ['wrong MIME', x => x['Content-Type'] = 'application/json'],
  ['MIME substring spoof', x => x['Content-Type'] = 'text/csv-malicious'],
  ['missing digest', x => delete x['Content-Digest']],
  ['missing ETag', x => delete x.ETag],
  ['wrong digest', x => x['Content-Digest'] = `sha-256=:${Buffer.alloc(32).toString('base64')}:`],
  ['wrong ETag', x => x.ETag = '"sha256:' + '0'.repeat(64) + '"'],
  ['length mismatch', x => x['Content-Length'] = '1'],
  ['length zero', x => x['Content-Length'] = '0'],
  ['length malformed', x => x['Content-Length'] = '1e2'],
  ['length over budget', x => x['Content-Length'] = String(32 * 1024 * 1024 + 1)],
]) test(label + ': no saved attachment', async () => {
  const h = setup(), hs = headers(); change(hs);
  h.rt.setFetch(async () => new Response(csv, { headers: hs }));
  await assert.rejects(h.run()); assert.equal(h.saved.length, 0);
});
test('actual stream budget enforced even without Content-Length', async () => {
  const h = setup(), hs = headers(); delete hs['Content-Length']; let i = 0, cancelled = false;
  h.rt.setFetch(async () => new Response(new ReadableStream({
    pull(c) { if (i++ < 33) c.enqueue(new Uint8Array(1024 * 1024)); else c.close(); },
    cancel() { cancelled = true; },
  }, { highWaterMark: 0 }), { headers: hs }));
  await assert.rejects(h.run(), /32MiB/); assert.equal(h.saved.length, 0); assert.equal(cancelled, true);
});
test('empty stream and invalid UTF-8 fail despite internally matching hashes', async () => {
  for (const data of [Buffer.alloc(0), Buffer.from([0xff])]) {
    const h = setup(), hs = headers(data); delete hs['Content-Length'];
    h.rt.setFetch(async () => new Response(data, { headers: hs }));
    await assert.rejects(h.run()); assert.equal(h.saved.length, 0);
  }
});
test('redirected response, rejected redirect/network, stream failure and absent Web Crypto never save', async () => {
  for (const kind of ['redirected', 'network', 'stream', 'crypto']) {
    const h = setup();
    if (kind === 'crypto') h.rt.shared.crypto = undefined;
    // runtime contexts capture shared globals at load time; reload a fresh module
    // for the missing-crypto case rather than changing an already loaded context.
    const rt = kind === 'crypto' ? runtime() : h.rt;
    if (kind === 'crypto') {
      const { fetch: _transport, ...globals } = h.rt.shared;
      Object.assign(rt.shared, globals, { crypto: undefined });
    }
    rt.setFetch(async () => {
      if (kind === 'network') throw new Error('PRIVATE_NETWORK_DETAIL');
      if (kind === 'stream') return new Response(new ReadableStream({ start(c) { c.error(new Error('资源清单PRIVATE_STREAM_DETAIL')); } }), { headers: headers() });
      const response = new Response(csv, { headers: headers() });
      if (kind === 'redirected') Object.defineProperty(response, 'redirected', { value: true });
      return response;
    });
    const run = () => rt.load('services/resourceInventory.ts').downloadResourceInventory('scn_test', new AbortController().signal);
    await assert.rejects(run(), e => !e.message.includes('PRIVATE'));
    assert.equal(h.saved.length, 0);
  }
});
test('cancel during Web Crypto prevents a late result from saving for the old scan', async () => {
  const h = setup(), rt = runtime(), controller = new AbortController();
  let finish, started;
  const reached = new Promise(resolve => started = resolve);
  const { fetch: _transport, ...globals } = h.rt.shared;
  Object.assign(rt.shared, globals, { crypto: { subtle: { digest(...args) {
    started(); return new Promise(resolve => finish = async () => resolve(await webcrypto.subtle.digest(...args)));
  } } } });
  rt.setFetch(async () => new Response(csv, { headers: headers() }));
  const promise = rt.load('services/resourceInventory.ts').downloadResourceInventory('scn_old', controller.signal);
  const rejected = assert.rejects(promise, e => e.name === 'AbortError');
  await reached; controller.abort(); await finish(); await rejected;
  assert.equal(h.saved.length, 0);
});
test('pre-cancel and cancel while awaiting transport do not save or retry', async () => {
  const h = setup(), controller = new AbortController(); let calls = 0, finish;
  h.rt.setFetch(() => { calls++; return new Promise(resolve => finish = resolve); });
  const promise = h.run(controller.signal), rejected = assert.rejects(promise, e => e.name === 'AbortError');
  controller.abort(); finish(new Response(csv, { headers: headers() })); await rejected;
  await assert.rejects(h.run(controller.signal), e => e.name === 'AbortError');
  assert.equal(calls, 1); assert.equal(h.saved.length, 0);
});

// Isolated component behavior harness: calls the real component functions with
// deterministic React hooks; it is not browser or React scheduling acceptance.
function componentHarness() {
  const states = [], refs = [], effects = []; let s = 0, r = 0;
  const react = {
    createContext: value => ({ value }), useContext: x => x.value, useId: () => 'TEST_ONLY',
    useState: initial => { const i = s++; if (!(i in states)) states[i] = initial; return [states[i], value => states[i] = value]; },
    useRef: initial => { const i = r++; return refs[i] ??= { current: initial }; },
    useLayoutEffect: callback => effects.push(callback), useEffect() {},
  };
  const jsx = (type, props, key) => ({ type, props, key });
  function load(name, extra = {}) {
    const source = fs.readFileSync(new URL('../src/' + name, import.meta.url), 'utf8');
    const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    const m = { exports: {} };
    vm.runInNewContext(js, { module: m, exports: m.exports, AbortController, Error, require: path => {
      if (path === 'react') return react;
      if (path === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
      return extra[path] ?? {};
    } });
    return m.exports;
  }
  return { load, effects, reset() { s = 0; r = 0; } };
}
const flatten = node => Array.isArray(node) ? node.flatMap(flatten) : node && typeof node === 'object'
  ? [node, ...flatten(node.props?.children)] : [];
test('real shared control locks repeated clicks and offers explicit retry after failure', async () => {
  const h = componentHarness(), { DownloadControl } = h.load('components/ui.tsx');
  let calls = 0, reject, resolve;
  const props = { children: 'TEST_ONLY download', onDownload: () => { calls++; return new Promise((yes, no) => { resolve = yes; reject = no; }); } };
  const render = () => { h.reset(); return flatten(DownloadControl(props)); };
  let tree = render(); tree.find(n => n.type === 'button').props.onClick();
  tree.find(n => n.type === 'button').props.onClick();
  assert.equal(calls, 1); assert.equal(render().find(n => n.type === 'button').props.disabled, true);
  reject(new Error('TEST_ONLY failure'));
  await new Promise(resolve => setImmediate(resolve));
  tree = render(); assert.ok(tree.find(n => n.props?.role === 'alert'));
  tree.find(n => n.type === 'button' && n.props.children === '重试下载').props.onClick();
  assert.equal(calls, 2); resolve();
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(render().find(n => n.props?.role === 'status'));
});
test('resource download component aborts on lifecycle cleanup; Resources keys it by scan identity', async () => {
  const h = componentHarness(); let seen;
  const { ResourceInventoryDownload } = h.load('components/ResourceInventoryDownload.tsx', {
    './ui': { DownloadControl: 'DownloadControl' },
    '../services/resourceInventory': { downloadResourceInventory: async (id, signal) => {
      seen = { id, signal }; await new Promise((_, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
    } },
  });
  const node = ResourceInventoryDownload({ scanId: 'scn_old' });
  const cleanup = h.effects[0]();
  const p = node.props.onDownload(), rejected = assert.rejects(p, e => e.name === 'AbortError');
  assert.equal(seen.id, 'scn_old'); cleanup(); await rejected; assert.equal(seen.signal.aborted, true);
  const source = fs.readFileSync(new URL('../src/pages/Resources.tsx', import.meta.url), 'utf8');
  assert.match(source, /<ResourceInventoryDownload key=\{scan\.id\} scanId=\{scan\.id\}/);
  assert.match(source, /scan\.reportFormats\?\.includes\("resource_inventory"\)/);
  assert.match(source, /resourceCsv\(scan, rows\)/);
});
