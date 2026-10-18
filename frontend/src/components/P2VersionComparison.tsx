import { useEffect, useState } from 'react';
import type { P2Result, P2ResourceResult } from '../types/p2Advice';
import { readPreviousP2Result } from '../services/p2Workflow';
import { p2StateLabels } from '../services/p2Advice';
import { usageFields } from '../services/assessments';

function SavedResource({ value }: { value: P2ResourceResult | undefined }) {
  if (!value) return <p>此版未返回该资源，不代表资源已删除或不适用。</p>;
  return <>
    <p>资源：{value.subject.resource_id}</p>
    <p>版本：{value.subject.version ?? '未获取'} · {p2StateLabels[value.state]} · 仅为候选</p>
    <p>范围：{value.scope === 'unknown' ? '未知，待核验' : value.scope === 'resource' ? '资源级' : value.scope || '未获取'}</p>
    <p>缺口：{value.gaps.join('、') || '未返回缺口，不代表证据完整'}</p>
    <p>材料：{value.material_ids.join('、') || '未提供'}；回答：{value.answer_ids.join('、') || '未提供'}</p>
    {value.advice.length ? value.advice.map(a => <div key={a.usage}>
      <strong>{usageFields[a.usage]}</strong>
      <p>保存的用途：{a.saved_value === null ? '未知' : a.saved_value ? '是' : '否'}；判断：{a.state === 'conditional_candidate' ? '条件候选，待核验' : a.state === 'not_selected' ? '未选择，不代表不适用' : '未知'}</p>
      <p>必要条件：{a.conditions.join('、') || '未返回，不能推断没有义务'}</p>
      <p>用途缺口：{a.gaps.join('、') || '未返回'}</p>
      <p>Evidence：{a.basis_evidence_ids.join('、') || '证据不足'}</p>
    </div>) : <p>用途建议未返回。</p>}
  </>;
}

export function P2VersionPair({ previous, current }: { previous: P2Result; current: P2Result }) {
  const [selected, setSelected] = useState('');
  const resourceIds = [...new Set([...current.resources, ...previous.resources].map(r => r.subject.resource_id))];
  const id = resourceIds.includes(selected) ? selected : resourceIds[0];
  return <div className="og-p2-version-pair">
    <p>以下为两个后端不可变快照的原值并排核对，不是前端生成的差异结论，不改变 Formal Assessment。</p>
    <p>本版后端声明重新计算：{current.recomputed_resource_ids.join('、') || '未列出'}；复用：{current.reused_resource_ids.join('、') || '未列出'}。重新计算不等于结论已改变。</p>
    {id ? <label>核对资源<select value={id} onChange={e => setSelected(e.target.value)}>{resourceIds.map(value => <option key={value}>{value}</option>)}</select></label> : <p>两版均未列出资源，无法核对资源结论。</p>}
    <div className="og-p2-version-columns">{[{ label: '前版快照', value: previous }, { label: '本版快照', value: current }].map(({ label, value }) =>
      <section key={value.result_id} aria-label={label}>
        <h4>{label} · Result 第{value.revision}版</h4>
        <p>{value.result_id} · {p2StateLabels[value.state]}</p>
        <p>父 Assessment：{value.binding.assessment_id} 第{value.binding.assessment_version}版</p>
        <p>Result SHA-256：{value.result_sha256}</p>
        <SavedResource value={value.resources.find(r => r.subject.resource_id === id)} />
      </section>)}</div>
  </div>;
}

export function P2VersionComparison({ current }: { current: P2Result }) {
  const [previous, setPrevious] = useState<P2Result | null>(null);
  const [requested, setRequested] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!requested) return;
    const controller = new AbortController();
    setPrevious(null); setLoading(true); setError('');
    void readPreviousP2Result(current, controller.signal).then(value => {
      if (!controller.signal.aborted) setPrevious(value);
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '前版读取失败'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [current, requested]);
  return <section aria-label="新旧P2结果核对">
    <h3>新旧结果核对</h3>
    {!current.previous_result_id ? <p>此结果没有前版引用。</p> : <>
      <button disabled={loading} onClick={() => setRequested(n => n + 1)}>{error ? '重试读取指定前版' : '读取指定前版并排核对'}</button>
      {loading && <p role="status">正在读取前版固定快照…</p>}
      {error && <p role="alert">{error} 不会选用其他版本或重算。</p>}
      {previous && <P2VersionPair previous={previous} current={current} />}
    </>}
  </section>;
}
