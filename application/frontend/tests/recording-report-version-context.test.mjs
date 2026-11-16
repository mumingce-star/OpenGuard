import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { runtime } from './runtime.mjs';

test('recording report navigation preserves exact Assessment version independently of Result ID', () => {
  const r = runtime(), service = r.load('services/reportV2.ts');
  r.setFetch(() => { throw Error('navigation must not dispatch a request'); });
  const current = new URLSearchParams('mode=api&assessment_id=asm_v2&assessment_version=2&p2_result=p2res_r1&snapshot_id=rpt_fixed');
  const selected = service.reportNavigationQuery('scn_1', 'scn_1', current);
  assert.equal(selected.get('assessment_version'), '2');
  assert.equal(selected.get('p2_result'), 'p2res_r1');
  assert.equal(selected.get('snapshot_id'), 'rpt_fixed');
  assert.equal(service.reportNavigationQuery('scn_1', 'scn_2', current).toString(), '');
});

test('P2 result return link keeps explicit identities and does not relabel the Assessment archive', () => {
  const service = runtime().load('services/reportV2.ts');
  const url = service.reportP2ContextUrl('scn_1', new URLSearchParams('assessment_id=asm_v2&assessment_version=2&p2_result=p2res_r1'));
  const parsed = new URL(url, 'http://localhost');
  assert.equal(parsed.pathname, '/app/scans/scn_1/assessment');
  assert.equal(parsed.searchParams.get('assessment_id'), 'asm_v2');
  assert.equal(parsed.searchParams.get('assessment_version'), '2');
  assert.equal(parsed.searchParams.get('p2_result'), 'p2res_r1');
  assert.equal(parsed.searchParams.has('snapshot_id'), false);
});

test('invalid or incomplete P2 context does not offer an apparently fixed result link', () => {
  const service = runtime().load('services/reportV2.ts');
  for (const query of [
    'assessment_id=asm_v2', 'p2_result=p2res_r1',
    'assessment_id=asm_v2&p2_result=p2res_r1&assessment_version=0',
    'assessment_id=asm_v2&p2_result=p2res_r1&assessment_version=null',
    'assessment_id=asm_v2&p2_result=p2res_r1&assessment_version=undefined',
    'assessment_id=asm_v2&p2_result=../../other',
  ]) assert.equal(service.reportP2ContextUrl('scn_1', new URLSearchParams(query)), null, query);
});

test('opening an archive for another Assessment drops previous Result, snapshot and version context', () => {
  const service = runtime().load('services/reportV2.ts');
  const current = new URLSearchParams('assessment_id=asm_v1&assessment_version=1&p2_result=p2res_r2&snapshot_id=old');
  const next = service.reportSnapshotQuery('scn_1', 'scn_1', current, 'asm_v2', 'new');
  assert.equal(next.get('assessment_id'), 'asm_v2');
  assert.equal(next.get('snapshot_id'), 'new');
  assert.equal(next.has('p2_result'), false);
  assert.equal(next.has('assessment_version'), false);
});

test('recording report UI names all three independent preservation scopes', () => {
  const report = fs.readFileSync(new URL('../src/pages/Report.tsx', import.meta.url), 'utf8');
  const archive = fs.readFileSync(new URL('../src/pages/ReportV2.tsx', import.meta.url), 'utf8');
  assert.match(report, /本页保留扫描事实/);
  assert.match(report, /后续评估覆盖/);
  assert.match(archive, /评估第 2 版也不等于 Result r2/);
  assert.match(archive, /P2 补充材料生成的 Result 修订及同版摘要独立保存/);
  assert.match(archive, /回看当前固定 P2 结果与同版摘要/);
});
