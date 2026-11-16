import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';
test('缓存评估不能用于错误扫描、错误版本或不存在的固定链接', () => {
  const { selectedAssessment } = runtime().load('services/versionContext.ts');
  const rows = [{ id: 'a', scan_id: 's', version: 2 }];
  const query = new URLSearchParams('assessment_id=a&assessment_version=2');
  assert.equal(selectedAssessment(rows, 's', query), rows[0]);
  assert.equal(selectedAssessment(rows, 'another', query), undefined);
  for (const version of ['1', '02', 'invalid', '']) {
    query.set('assessment_version', version);
    assert.equal(selectedAssessment(rows, 's', query), undefined);
  }
  assert.equal(selectedAssessment(rows, 's', new URLSearchParams('assessment_id=missing')), undefined);
});
test('跨页只带固定身份，刷新解析仍保持同一结果与报告', () => {
  const { versionContext } = runtime().load('services/versionContext.ts');
  const q = new URLSearchParams('assessment_id=a&assessment_version=2&p2_result_id=r&p2_revision=3&snapshot_id=s&task_status=done');
  const restored = new URLSearchParams(versionContext(q).toString());
  assert.equal(restored.get('snapshot_id'), 's'); assert.equal(restored.get('p2_revision'), '3');
  assert.equal(restored.get('assessment_version'), '2'); assert.equal(restored.has('task_status'), false);
});
test('同一评估补版本保留引用，切换评估清除下游身份，错误版本拒绝', () => {
  const { selectAssessment, checkAssessmentVersion } = runtime().load('services/versionContext.ts');
  const q = new URLSearchParams('assessment_id=a&p2_result_id=r&p2_revision=3&snapshot_id=s');
  assert.equal(selectAssessment(q, 'a', 2).get('snapshot_id'), 's');
  const next = selectAssessment(q, 'b', 4);
  assert.equal(next.get('assessment_version'), '4'); assert.equal(next.has('p2_result_id'), false); assert.equal(next.has('snapshot_id'), false);
  assert.throws(() => checkAssessmentVersion(next, 2), /不一致/);
});

test('资源筛选入口仍保留固定上下文，明确切换评估不继承旧报告', () => {
  const { navigationContext } = runtime().load('services/versionContext.ts');
  const current = new URLSearchParams('assessment_id=old&snapshot_id=report&p2_result_id=r&p2_revision=2');
  const filtered = navigationContext(current,new URLSearchParams('unknown=1'));
  assert.equal(filtered.get('snapshot_id'),'report'); assert.equal(filtered.get('unknown'),'1');
  const switched = navigationContext(current,new URLSearchParams('assessment_id=new'));
  assert.equal(switched.has('snapshot_id'),false);
});
