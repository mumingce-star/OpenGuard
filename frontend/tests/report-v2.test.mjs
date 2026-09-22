import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const hash = 'a'.repeat(64);
function fixture(status = 'completed', extra = []) {
  const section = (authority, content) => ({ authority, schema_version: '1.0', source_ids: ['source'], content_hash: hash, content });
  return {
    schema_version: '1.0', snapshot_id: 'rptv2_1',
    binding: { scan_ref: { scan_id: 'scn_1', status, revision: null }, assessment_ref: { assessment_id: 'asm_1', version: 2 }, notice_refs: [] },
    created_at: '2026-09-18T00:00:00Z', generator_version: 'report-v2/1.1', provenance: { source_refs: [], assessment_refs: [] },
    sections: [section('scan_facts', { status }), section('formal_assessment', { id: 'asm_1', scan_id: 'scn_1', formal: true, summary: '正式结论' }), section('workflow', { tasks: [] }), section('ai_explanation', { ai_status: 'not_requested' }), ...extra],
  };
}

function snapshot() {
  return {
    schema_version: '1.0', snapshot_id: 'rptv2_1', content_hash: hash,
    binding: { scan_ref: { scan_id: 'scn_1' }, assessment_ref: { assessment_id: 'asm_1', version: 2 }, task_refs: [{ task_id: 'tsk_1', version: 3 }], notice_refs: [], algorithm_refs: [] },
    artifacts: [
      { format: 'json', content_hash: hash, size_bytes: 100, href: '/api/v1/scans/scn_1/assessments/asm_1/report-v2/rptv2_1?format=json' },
      { format: 'html', content_hash: hash, size_bytes: 200, href: '/api/v1/scans/scn_1/assessments/asm_1/report-v2/rptv2_1?format=html' },
    ],
  };
}

test('Report V2 URL binds scan, assessment, snapshot and format', () => {
  const service = runtime().load('services/reportV2.ts');
  assert.equal(service.reportV2Url('s/1', 'a/2', 'r/3', 'html'), '/api/v1/scans/s%2F1/assessments/a%2F2/report-v2/r%2F3?format=html');
});

test('explicit creation binds current task versions and never supplies invented Notice or graph refs', async () => {
  const r = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = r.load('services/reportV2.ts');
  let call;
  r.setFetch(async (url, init) => { call = [url, init]; return Response.json(snapshot()); });
  const created = await service.createReportV2('scn_1', 'asm_1', 'report-key', [{ task_id: 'tsk_1', version: 3 }]);
  assert.equal(created.snapshot_id, 'rptv2_1');
  assert.equal(call[0], '/api/v1/scans/scn_1/assessments/asm_1/report-v2');
  assert.equal(call[1].method, 'POST');
  assert.deepEqual(JSON.parse(call[1].body), { idempotency_key: 'report-key', task_refs: [{ task_id: 'tsk_1', version: 3 }], notice_refs: [], algorithm_refs: [] });
  assert.equal(r.storage.size, 0);
  assert.throws(() => service.validateReportSnapshot({ ...snapshot(), binding: { ...snapshot().binding, scan_ref: { scan_id: 'other' } } }, 'scn_1', 'asm_1'), /契约/);
});

test('Report V2 includes only an exact backend NoticeDraft id and content hash', async () => {
  const r = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = r.load('services/reportV2.ts');
  let body;
  r.setFetch(async (_url, init) => {
    body = JSON.parse(init.body);
    return Response.json({ ...snapshot(), binding: { ...snapshot().binding, notice_refs: [{ draft_id: 'ntc_1', content_hash: hash }] } });
  });
  const created = await service.createReportV2('scn_1', 'asm_1', 'report-with-notice', [{ task_id: 'tsk_1', version: 3 }], [{ draft_id: 'ntc_1', content_hash: hash }]);
  assert.deepEqual(body.notice_refs, [{ draft_id: 'ntc_1', content_hash: hash }]);
  assert.equal(created.binding.notice_refs[0].draft_id, 'ntc_1');
  await assert.rejects(async () => service.createReportV2('scn_1', 'asm_1', 'bad', [], [{ draft_id: 'ntc_1', content_hash: 'bad' }]), /参数无效/);
});

test('only a bound Formal Assessment snapshot is accepted', () => {
  const service = runtime().load('services/reportV2.ts');
  assert.equal(service.validateReportDocument(fixture('partial'), 'scn_1', 'asm_1', 'rptv2_1').binding.scan_ref.status, 'partial');
  for (const [value, scan, assessment, snapshot] of [
    [fixture(), 'wrong', 'asm_1', 'rptv2_1'], [fixture(), 'scn_1', 'wrong', 'rptv2_1'], [fixture(), 'scn_1', 'asm_1', 'wrong'],
    [{ ...fixture(), sections: fixture().sections.filter(section => section.authority !== 'formal_assessment') }, 'scn_1', 'asm_1', 'rptv2_1'],
    [{ ...fixture(), sections: fixture().sections.map(section => section.authority === 'formal_assessment' ? { ...section, content: { ...section.content, formal: false } } : section) }, 'scn_1', 'asm_1', 'rptv2_1'],
  ]) assert.throws(() => service.validateReportDocument(value, scan, assessment, snapshot), /契约/);
});

test('large saved body is displayed from GET only; no creation or model call', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts'), calls = [];
  const html = '<!doctype html><html><head><meta name="openguard-html-renderer" content="1.1"></head><body>' + '固定正文'.repeat(20000) + '</body></html>';
  r.setFetch(async (url, options) => {
    calls.push([url, options.method]);
    return url.endsWith('format=json') ? Response.json(fixture('partial')) : new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  });
  const result = await service.loadReportV2('scn_1', 'asm_1', 'rptv2_1');
  assert.equal(result.html, html);
  assert.equal(result.document.binding.scan_ref.status, 'partial');
  assert.deepEqual(calls.map(call => call[1]), ['GET', 'GET']);
  assert.equal(r.storage.size, 0);
});

test('missing report, wrong MIME, malformed JSON and failed download never fall back to mock', async () => {
  const r = runtime(), service = r.load('services/reportV2.ts');
  r.setFetch(async () => new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } }));
  await assert.rejects(service.loadReportV2('scn_1', 'asm_1', 'rptv2_1'), error => error.status === 404);
  await assert.rejects(service.downloadReportV2('scn_1', 'asm_1', 'rptv2_1', 'html'), error => error.status === 404);
  r.setFetch(async () => new Response('<html>SPA</html>', { headers: { 'Content-Type': 'text/html' } }));
  await assert.rejects(service.loadReportV2('scn_1', 'asm_1', 'rptv2_1'), /格式/);
  r.setFetch(async () => Response.json({ ...fixture(), sections: [] }));
  await assert.rejects(service.loadReportV2('scn_1', 'asm_1', 'rptv2_1'), /契约/);
  assert.equal(r.storage.size, 0);
});

test('report route preserves IDs on reload and share', () => {
  const r = runtime(), route = r.load('hooks/useRoute.ts');
  r.shared.window.location = { pathname: '/app/scans/scn_1/report-v2', search: '?mode=api&assessment_id=asm_1&snapshot_id=rptv2_1' };
  const parsed = route.readRoute();
  assert.equal(parsed.page, 'report-v2');
  assert.equal(parsed.scanId, 'scn_1');
  assert.equal(parsed.query.get('snapshot_id'), 'rptv2_1');
});
