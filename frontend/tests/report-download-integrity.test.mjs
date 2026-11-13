import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { runtime } from './runtime.mjs';

// SYNTHETIC_TEST_ONLY: actual report service, closed bottom-level transport.
const ids = ['scn_integrity', 'asm_integrity', 'rptv2_integrity'];
const h = 'a'.repeat(64);
const fixture = () => ({ schema_version: '1.0', snapshot_id: ids[2], created_at: '2026-10-24T00:00:00Z', generator_version: 'report-v2/1.1',
  binding: { scan_ref: { scan_id: ids[0], status: 'partial', revision: null }, assessment_ref: { assessment_id: ids[1], version: 2 }, notice_refs: [] },
  provenance: {}, sections: ['scan_facts','formal_assessment','workflow','ai_explanation'].map(authority => ({ authority, schema_version: '1.0', source_ids: ['source'], content_hash: h,
    content: authority === 'formal_assessment' ? { id: ids[1], scan_id: ids[0], formal: true } : {} })) });
const html = '<!doctype html><html><head><meta name="openguard-html-renderer" content="1.1"></head><body>固定归档</body></html>';
function response(body, format = 'json', overrides = {}) {
  const bytes = Buffer.from(body), digest = createHash('sha256').update(bytes).digest();
  return new Response(bytes, { headers: { 'Content-Type': format === 'json' ? 'application/json' : 'text/html',
    'Content-Length': String(bytes.length), 'Content-Digest': `sha-256=:${digest.toString('base64')}:`, 'ETag': `"sha256:${digest.toString('hex')}"`, ...overrides } });
}
function harness(reply) {
  const r = runtime(), downloads = [], ledger = [], unknown = [], nonGet = [];
  r.shared.crypto = webcrypto; r.shared.Blob = Blob; r.shared.TextDecoder = TextDecoder; r.shared.btoa = btoa;
  r.shared.URL = class extends URL { static createObjectURL(blob) { downloads.push({ blob }); return 'blob:integrity'; } static revokeObjectURL() {} };
  r.shared.setTimeout = fn => { fn(); return 0; };
  r.shared.document = { createElement(tag) { assert.equal(tag, 'a'); return { href: '', download: '', click() { downloads.at(-1).name = this.download; }, remove() {} }; }, body: { appendChild() {} } };
  r.setFetch(async (url, init) => {
    const entry = { url, method: init.method ?? 'GET' }; ledger.push(entry);
    if (entry.method !== 'GET') nonGet.push(entry);
    if (!url.startsWith(`/api/v1/scans/${ids[0]}/assessments/${ids[1]}/report-v2/${ids[2]}?format=`)) unknown.push(entry);
    return reply(url, init);
  });
  return { service: r.load('services/reportV2.ts'), downloads, ledger, unknown, nonGet, r };
}
async function refused(reply, format = 'json', expected = /摘要|完整性|附件|契约|格式|HTML|大小|超限|保存/) {
  const x = harness(reply);
  await assert.rejects(x.service.downloadReportV2(...ids, format), expected);
  assert.equal(x.downloads.length, 0, 'failure must never dispatch a browser download');
  assert.deepEqual(x.nonGet, []); assert.deepEqual(x.unknown, []); assert.equal(x.r.storage.size, 0);
}
for (const format of ['json','html']) test(`${format} exact saved bytes and digest download once, GET only`, async () => {
  const body = format === 'json' ? JSON.stringify(fixture()) : html;
  const x = harness(() => response(body, format)); await x.service.downloadReportV2(...ids, format);
  assert.equal(x.downloads.length, 1); assert.equal(await x.downloads[0].blob.text(), body);
  assert.equal(x.downloads[0].name, `openguard-${ids[2]}.${format}`);
  assert.equal(x.ledger.length, 1); assert.deepEqual(x.nonGet, []); assert.deepEqual(x.unknown, []);
});
for (const key of ['Content-Digest','ETag']) {
  test(`${key} missing fails closed`, () => refused(() => { const r=response(JSON.stringify(fixture()));r.headers.delete(key);return r; }));
  test(`${key} mismatch fails closed`, () => refused(() => response(JSON.stringify(fixture()), 'json', { [key]: key === 'ETag' ? `"sha256:${'0'.repeat(64)}"` : `sha-256=:${Buffer.alloc(32).toString('base64')}:` })));
}
test('changed raw JSON with stale digest fails even if parsed object is identical', () => {
  const body = JSON.stringify(fixture()); const stale = response(body).headers.get('Content-Digest');
  return refused(() => response(body + '\n', 'json', { 'Content-Digest': stale }));
});
for (const field of ['scan','assessment','snapshot']) test(`valid hash with wrong ${field} identity is refused`, () => refused(() => {
  const doc = fixture(); if (field === 'scan') doc.binding.scan_ref.scan_id = 'scn_other';
  if (field === 'assessment') doc.binding.assessment_ref.assessment_id = 'asm_other'; if (field === 'snapshot') doc.snapshot_id = 'rptv2_other';
  return response(JSON.stringify(doc));
}));
test('unrecognized HTML/SPA is refused even with a matching byte digest', () => refused(() => response('<!doctype html><html><body>login fallback</body></html>', 'html'), 'html'));
test('empty artifact is refused', () => refused(() => response('')));
test('declared oversized body is rejected before reading', () => refused(() => { const r=response('{}', 'json', {'Content-Length': String(32*1024*1024+1)});r.body.getReader=()=>{throw Error('must not read oversized response');};return r; }));
test('actual streaming body over limit without Content-Length is refused', () => refused(() => {
  const r = response(' '.repeat(32*1024*1024+1));r.headers.delete('Content-Length');return r;
}));
test('false Content-Length and malformed JSON are refused', async () => {
  await refused(() => response(JSON.stringify(fixture()), 'json', {'Content-Length':'1'}));
  await refused(() => response('{bad json'));
});
test('non-200 and wrong MIME preserve failure with no artifact', async () => {
  await refused(() => new Response('{}',{status:503,headers:{'Content-Type':'application/json'}}), 'json', /503/);
  await refused(() => response(html,'html'), 'json', /格式/);
});
