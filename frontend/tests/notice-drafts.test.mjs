import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const hash = 'b'.repeat(64);
const draft = () => ({
  schema_version: '1.0', draft_id: 'ntc_1',
  binding: { scan_ref: { scan_id: 'scn_1' }, assessment_ref: { assessment_id: 'asm_1', version: 1 } },
  created_at: '2026-09-23T00:00:00Z', generator_version: 'notice-bound/1.0',
  entries: [{ entry_id: 'entry_1', resource_ids: ['ast_1'], license_expression_ids: [], obligation_refs: [], evidence_refs: [], text: null, missing: ['license_not_observed'] }],
  coverage_gaps: ['license_not_observed'], content_hash: hash, provenance: {},
});

test('NOTICE creation is explicit, idempotent-keyed, and accepts only the bound backend draft', async () => {
  const r = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = r.load('services/noticeDrafts.ts');
  let call;
  r.setFetch(async (url, init) => { call = [url, init]; return Response.json(draft()); });
  const result = await service.createNoticeDraft('scn_1', 'asm_1', 'notice-key');
  assert.equal(result.draft_id, 'ntc_1');
  assert.equal(call[0], '/api/v1/scans/scn_1/assessments/asm_1/notice-drafts');
  assert.equal(call[1].method, 'POST');
  assert.deepEqual(JSON.parse(call[1].body), { idempotency_key: 'notice-key' });
  assert.equal(r.storage.size, 0);
  assert.throws(() => service.parseNoticeDraft({ ...draft(), binding: { ...draft().binding, scan_ref: { scan_id: 'other' } } }, 'scn_1', 'asm_1'), /冻结契约/);
});

test('NOTICE unavailable and not-ready states are not replaced with browser content', async () => {
  const r = runtime(), service = r.load('services/noticeDrafts.ts');
  r.setFetch(async () => Response.json({ error: { code: 'feature_disabled', details: { reason: 'notice_not_configured' } } }, { status: 503 }));
  await assert.rejects(service.createNoticeDraft('scn_1', 'asm_1', 'key'), /NOTICE 草稿服务未配置/);
  r.setFetch(async () => Response.json({ error: { code: 'not_ready', details: { reason: 'facts_unavailable' } } }, { status: 409 }));
  await assert.rejects(service.createNoticeDraft('scn_1', 'asm_1', 'key'), error =>
    error.status === 409 && error.reason === 'facts_unavailable');
  assert.equal(r.storage.size, 0);
});

// TEST_ONLY response fixtures: these are not runtime BOUND packages or database records.
for (const [status, code, reason, message] of [
  [409, 'not_ready', 'notice_source_not_bound', '当前正式评估尚无精确绑定的 NOTICE source'],
  [409, 'not_ready', 'notice_source_binding_mismatch', 'NOTICE source 与当前 ScanRun / Assessment 固定绑定不一致'],
  [503, 'upstream_unavailable', 'notice_source_unavailable', 'NOTICE source 暂不可读取'],
  [503, 'upstream_unavailable', 'notice_source_invalid', 'NOTICE source 完整性校验失败'],
  [503, 'feature_disabled', 'notice_not_configured', 'NOTICE 草稿服务未配置'],
]) {
  test(`A3 NOTICE maps exactly ${status}/${reason} without retry or fabricated draft`, async () => {
    const r = runtime(), service = r.load('services/noticeDrafts.ts');
    let calls = 0;
    r.setFetch(async () => {
      calls++;
      return Response.json({ error: { code, message: 'backend message', details: { reason } } }, { status });
    });
    await assert.rejects(service.createNoticeDraft('scn_1', 'asm_1', 'fixed-key'), error =>
      error.status === status && error.code === code && error.reason === reason && error.message === message);
    assert.equal(calls, 1);
    assert.equal(r.storage.size, 0);
  });
}

test('unknown NOTICE errors and mismatched status preserve backend diagnostics', async () => {
  const r = runtime(), service = r.load('services/noticeDrafts.ts');
  for (const [status, reason] of [[503, 'storage_unavailable'], [409, 'notice_source_invalid'], [404, 'notice_draft_not_found']]) {
    r.setFetch(async () => Response.json({
      error: { code: 'actual_backend_code', message: 'actual backend detail', details: { reason } },
    }, { status }));
    await assert.rejects(service.createNoticeDraft('scn_1', 'asm_1', 'key'), error =>
      error.status === status && error.code === 'actual_backend_code' &&
      error.reason === reason && error.message === `接口请求失败（HTTP ${status}）：actual backend detail (actual_backend_code)`);
  }
});

test('BOUND projection preserves text, gaps, provenance and unknown formal references without inference', () => {
  const service = runtime().load('services/noticeDrafts.ts');
  const value = draft();
  value.entries[0].text = '<script>not executable</script>bounded excerpt';
  value.entries[0].missing = ['notice_source_excerpt_truncated', 'resource_relation_unresolved'];
  value.coverage_gaps = ['notice_source_partial', 'capacity_limit'];
  value.provenance = { source_refs: [{ scan_id: 'scn_1', status: 'partial' }], parameters_hash: hash };
  const before = JSON.stringify(value);
  const result = service.parseNoticeDraft(value, 'scn_1', 'asm_1');
  assert.equal(JSON.stringify(result), before);
  assert.equal(result.generator_version, 'notice-bound/1.0');
  assert.deepEqual(result.entries[0].license_expression_ids, []);
  assert.deepEqual(result.entries[0].obligation_refs, []);
  assert.equal('authorization_verified' in result, false);
  assert.equal('fulfillment' in result.entries[0], false);
});

test('legacy notice/1.0 snapshots and null text remain readable without source fallback', async () => {
  const r = runtime(), service = r.load('services/noticeDrafts.ts'), calls = [];
  r.setFetch(async (_url, init) => {
    calls.push(init.method ?? 'GET');
    return Response.json({ ...draft(), generator_version: 'notice/1.0' });
  });
  const result = await service.getNoticeDraft('scn_1', 'asm_1', 'ntc_1');
  assert.equal(result.generator_version, 'notice/1.0');
  assert.equal(result.entries[0].text, null);
  assert.deepEqual(calls, ['GET']);
});

test('NOTICE GET validates scope and never triggers creation', async () => {
  const r = runtime(), service = r.load('services/noticeDrafts.ts'), calls = [];
  r.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return Response.json(draft()); });
  const result = await service.getNoticeDraft('scn_1', 'asm_1', 'ntc_1');
  assert.equal(result.content_hash, hash);
  assert.deepEqual(calls, [['/api/v1/scans/scn_1/assessments/asm_1/notice-drafts/ntc_1', 'GET']]);
});

test('NOTICE GET integrity error remains a read failure, never a POST or source fallback', async () => {
  const r = runtime(), service = r.load('services/noticeDrafts.ts'), calls = [];
  r.setFetch(async (_url, init) => {
    calls.push(init.method ?? 'GET');
    return Response.json({ error: { code: 'upstream_unavailable', details: { reason: 'notice_source_invalid' } } }, { status: 503 });
  });
  await assert.rejects(service.getNoticeDraft('scn_1', 'asm_1', 'ntc_1'), error =>
    error.status === 503 && error.reason === 'notice_source_invalid' && error.message === 'NOTICE source 完整性校验失败');
  assert.deepEqual(calls, ['GET']);
});
