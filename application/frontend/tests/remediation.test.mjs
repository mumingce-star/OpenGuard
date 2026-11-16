import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const h = 'a'.repeat(64);
function task(status = 'todo') { return { schema_version: '1.0', task_id: 'tsk_1', scan_id: 's1', assessment_ref: { assessment_id: 'a1', version: 1, scan_id: 's1', facts_hash: h, usage_hash: h, rule_version: 'r1', formal: true }, origin: { kind: 'next_step', source_pointer: '/resource_evaluations/0/next_steps/0', source_hash: h }, resource_ids: ['r1'], evidence_refs: [{ namespace: 'scan', scan_id: 's1', evidence_id: 'e1' }], title: '核查版本', status, note: status === 'done' ? '人工已处理' : '', version: 1, superseded: false, created_at: '2026-09-17T00:00:00Z', updated_at: '2026-09-17T00:00:00Z' }; }

test('GET-only pagination restores server state without local storage', async () => {
 const run = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = run.load('services/remediationTasks.ts'), calls = [];
 run.setFetch(async (url, init) => { calls.push([url, init.method]); return Response.json({ schema_version: '1.0', items: [task()], next_cursor: null }); });
 const items = await service.listAllTasks('s1', 'a1');
 assert.equal(items.length, 1); assert.equal(calls[0][1], 'GET'); assert.equal(run.storage.size, 0);
});

test('PATCH sends CAS version and validates server increment', async () => {
 const run = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = run.load('services/remediationTasks.ts');
 run.setFetch(async (_url, init) => { const body = JSON.parse(init.body); assert.equal(init.method, 'PATCH'); assert.equal(body.expected_version, 1); assert.equal(body.status, 'in_progress'); return Response.json({ ...task(), status: 'in_progress', version: 2 }); });
 assert.equal((await service.patchTask('s1', 'a1', task(), { status: 'in_progress' })).version, 2);
});

test('failed PATCH exposes rollback input and stale-version conflict', async () => {
 const run = runtime({ VITE_API_BASE_URL: '/api/v1' }), service = run.load('services/remediationTasks.ts');
 const previous = task(); let visible = service.optimisticTask(previous, { status: 'done', note: 'checked' });
 assert.equal(visible.status, 'done');
 run.setFetch(async () => Response.json({ error: { code: 'conflict', message: 'stale', details: { reason: 'stale_version' } } }, { status: 409 }));
 try { await service.patchTask('s1', 'a1', previous, { status: 'done', note: 'checked' }); assert.fail('must reject'); }
 catch (error) { visible = previous; assert.equal(service.isVersionConflict(error), true); }
 assert.equal(visible.status, 'todo'); assert.equal(visible.version, 1);
});

test('direct Assessment source pointers only expose recorded associations', () => {
 const service = runtime().load('services/remediationTasks.ts');
 const assessment = { obligations: [{ id: 'o1', action: 'notice' }], resource_evaluations: [{ resource_id: 'r1', finding_ids: ['f1'] }] };
 assert.deepEqual(Array.from(service.taskLinks(task(), assessment).findingIds), ['f1']);
 assert.equal(service.taskLinks({ ...task(), origin: { ...task().origin, source_pointer: '/unknown/0' } }, assessment).findingIds.length, 0);
 const obligation = { ...task(), origin: { ...task().origin, kind: 'obligation', source_pointer: '/obligations/0' } };
 assert.equal(service.taskLinks(obligation, assessment).obligation.id, 'o1');
});

test('rejects invalid task states and empty terminal notes', () => {
 const service = runtime().load('services/remediationTasks.ts');
 assert.throws(() => service.validateTask({ ...task(), status: 'verified' }, 's1', 'a1'));
 assert.throws(() => service.validateTask({ ...task(), status: 'done' }, 's1', 'a1'));
 assert.throws(() => service.validateTask(task(), 's2', 'a1'));
});
