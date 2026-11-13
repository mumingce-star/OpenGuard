import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { runtime } from './runtime.mjs';

function setup(env = {}) {
  const rt = runtime(env), clicks = [], revoked = [];
  rt.shared.Blob = Blob;
  rt.shared.structuredClone = structuredClone;
  rt.shared.document = {
    createElement: () => ({ click() { clicks.push({ href: this.href, download: this.download }); }, remove() {} }),
    body: { appendChild() {} },
  };
  rt.shared.URL = class TestURL extends URL {
    static createObjectURL() { return 'blob:SYNTHETIC_TEST_ONLY'; }
    static revokeObjectURL(url) { revoked.push(url); }
  };
  rt.shared.setTimeout = callback => { callback(); return 0; };
  const service = rt.load('services/evaluationExport.ts');
  const { fixture } = rt.load('../tests/p2-ai-analysis/fixture.ts');
  const f = fixture();
  return { rt, service, clicks, revoked, ...f };
}

const bytes = new Uint8Array([0x50, 0x4b, 3, 4, 0, 0]); // transport fixture; server ZIP validity tested by actual ASGI suite.
const sha = createHash('sha256').update(bytes).digest('hex');
function reply(result, changes = {}, body = bytes) {
  return new Response(body, { headers: {
    'Content-Type': 'application/zip', 'X-Content-SHA256': sha,
    'X-OpenGuard-Result-ID': result.result_id, 'X-OpenGuard-Result-SHA256': result.result_sha256,
    'X-OpenGuard-Result-Revision': String(result.revision),
    'X-OpenGuard-Assessment-Version': String(result.binding.assessment_version), ...changes,
  } });
}

test('SYNTHETIC_TEST_ONLY: selected fixed IDs and archive are explicit; no latest', () => {
  const { service, assessment, result } = setup();
  const url = service.evaluationPackageUrl(assessment, result, { analysisId: 'p2ai_fixed', reportSnapshotId: 'rptv2_fixed' });
  assert.ok(url.includes('/results/' + result.result_id + '/evaluation-package?'));
  assert.ok(url.includes('assessment_version=' + assessment.version));
  assert.ok(url.includes('analysis_id=p2ai_fixed') && url.includes('report_snapshot_id=rptv2_fixed'));
  assert.ok(!url.includes('latest'));
  assert.throws(() => service.evaluationPackageUrl(assessment, result, { analysisId: 'one', previewId: 'two' }));
  assert.throws(() => service.evaluationPackageUrl(assessment, result, { reportSnapshotId: '../private' }));
});

test('wrong Assessment cannot issue any download GET', async () => {
  const { rt, service, assessment, result, clicks } = setup(); let calls = 0;
  rt.setFetch(async () => { calls++; return reply(result); });
  await assert.rejects(service.downloadEvaluationPackage({ ...assessment, version: 99 }, result, {}, new AbortController().signal, () => true));
  assert.equal(calls, 0); assert.equal(clicks.length, 0);
});

test('byte hash and exact header checks precede one browser download; GET-only ledger', async () => {
  const { rt, service, assessment, result, clicks, revoked } = setup();
  const ledger = [], nonGet = [], unknown = [];
  rt.setFetch(async (url, options) => {
    ledger.push({ url, method: options.method });
    if (options.method !== 'GET') nonGet.push({ url, method: options.method });
    if (!url.includes('/evaluation-package?')) unknown.push(url);
    return reply(result);
  });
  await service.downloadEvaluationPackage(assessment, result, {}, new AbortController().signal, () => true);
  assert.equal(ledger.length, 1); assert.equal(nonGet.length, 0); assert.equal(unknown.length, 0);
  assert.equal(clicks.length, 1); assert.ok(clicks[0].download.includes(sha.slice(0, 16)));
  assert.deepEqual(revoked, ['blob:SYNTHETIC_TEST_ONLY']);
});

for (const [name, headers, body] of [
  ['wrong ZIP hash', { 'X-Content-SHA256': '0'.repeat(64) }, bytes],
  ['foreign Result', { 'X-OpenGuard-Result-ID': 'p2res_other' }, bytes],
  ['wrong assessment version', { 'X-OpenGuard-Assessment-Version': '99' }, bytes],
  ['wrong content type', { 'Content-Type': 'text/html' }, bytes],
  ['not ZIP', {}, new Uint8Array([1, 2, 3, 4])],
]) test(name + ' is not saved', async () => {
  const { rt, service, assessment, result, clicks } = setup();
  rt.setFetch(async () => reply(result, headers, body));
  await assert.rejects(service.downloadEvaluationPackage(assessment, result, {}, new AbortController().signal, () => true));
  assert.equal(clicks.length, 0);
});

test('scope changed while GET body was pending cannot trigger a stale download', async () => {
  const { rt, service, assessment, result, clicks } = setup();
  let release, entered; const waiting = new Promise(resolve => { entered = resolve; }); let current = true;
  rt.setFetch(async () => {
    const response = reply(result);
    response.arrayBuffer = () => { entered(); return new Promise(resolve => { release = resolve; }); };
    return response;
  });
  const operation = service.downloadEvaluationPackage(assessment, result, {}, new AbortController().signal, () => current);
  await waiting; current = false; release(bytes.buffer);
  await assert.rejects(operation, error => error.name === 'AbortError');
  assert.equal(clicks.length, 0);
});

test('saved AI is selected by exact Result GET and never regenerated', async () => {
  const { rt, service, assessment, result } = setup({ VITE_P2_AI_ANALYSIS: '1' });
  const all = [], nonGet = [], unknown = [];
  rt.setFetch(async (url, options) => {
    all.push({ url, method: options.method });
    if (options.method !== 'GET') nonGet.push(url);
    if (!url.includes('/ai-analyses?')) { unknown.push(url); throw Error('unknown request'); }
    assert.ok(url.includes('result_id=' + result.result_id));
    return Response.json({ result_id: result.result_id, analysis_ids: ['p2ai_exact'] });
  });
  assert.equal((await service.selectEvaluationAnalysis(assessment, result)).analysisId, 'p2ai_exact');
  assert.equal(all.length, 1); assert.equal(nonGet.length, 0); assert.equal(unknown.length, 0);
  rt.setFetch(async () => Response.json({ result_id: result.result_id, analysis_ids: ['one', 'two'] }));
  await assert.rejects(service.selectEvaluationAnalysis(assessment, result));
});

test('sensitive server rejection is preserved and does not show download success', async () => {
  const { rt, service, assessment, result, clicks } = setup();
  rt.setFetch(async () => Response.json({ error: { code: 'evaluation_package_sensitive_content_blocked', details: { reason: 'evaluation_package_sensitive_content_blocked' } } }, { status: 409 }));
  await assert.rejects(service.downloadEvaluationPackage(assessment, result, {}, new AbortController().signal, () => true), error => error.status === 409 && error.message.includes('敏感'));
  assert.equal(clicks.length, 0);
});
