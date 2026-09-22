import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const hash = 'b'.repeat(64);
const draft = () => ({
  schema_version: '1.0', draft_id: 'ntc_1',
  binding: { scan_ref: { scan_id: 'scn_1' }, assessment_ref: { assessment_id: 'asm_1', version: 1 } },
  created_at: '2026-09-23T00:00:00Z', generator_version: 'notice-draft/1',
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
  await assert.rejects(service.createNoticeDraft('scn_1', 'asm_1', 'key'), /生产服务尚未接线/);
  r.setFetch(async () => Response.json({ error: { code: 'not_ready', details: { reason: 'facts_unavailable' } } }, { status: 409 }));
  await assert.rejects(service.createNoticeDraft('scn_1', 'asm_1', 'key'), /来源尚未就绪/);
  assert.equal(r.storage.size, 0);
});

test('NOTICE GET validates scope and never triggers creation', async () => {
  const r = runtime(), service = r.load('services/noticeDrafts.ts'), calls = [];
  r.setFetch(async (url, init) => { calls.push([url, init.method ?? 'GET']); return Response.json(draft()); });
  const result = await service.getNoticeDraft('scn_1', 'asm_1', 'ntc_1');
  assert.equal(result.content_hash, hash);
  assert.deepEqual(calls, [['/api/v1/scans/scn_1/assessments/asm_1/notice-drafts/ntc_1', 'GET']]);
});
