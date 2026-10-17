import { useEffect, useState } from 'react';
import type { P2Advice, P2ResourceResult, P2Result } from '../types/p2Advice';
import { readP2Advice, p2StateLabels } from '../services/p2Advice';
import { usageFields } from '../services/assessments';
import { ApiError } from '../services/scans';
import { Panel } from './ui';

type View = { kind: 'loading' } | { kind: 'empty' } | { kind: 'error'; message: string } | { kind: 'ready'; result: P2Result };
const resourceScope = (value: string) => value === 'resource' ? '资源级' : value === 'unknown' ? '未知，待核验' : value || '未获取';

function EvidenceRefs({ ids, available, open }: { ids: string[]; available: Set<string>; open: (id: string) => void }) {
  if (!ids.length) return <p>没有返回 Evidence 引用；证据不足。</p>;
  return <div className="og-p2-evidence">{ids.map(id => available.has(id)
    ? <button type="button" key={id} className="og-evidence-ref" onClick={() => open(id)}>查看 Evidence：{id}</button>
    : <span key={id}>Evidence {id} 未在本次扫描中定位，待核对。</span>)}</div>;
}

function AdviceDetail({ advice, available, open }: { advice: P2Advice; available: Set<string>; open: (id: string) => void }) {
  const selection = advice.selection === 'SELECTED' ? '本次已选择' : advice.selection === 'NOT_SELECTED' ? '本次未选择' : '选择情况未知';
  const saved = advice.saved_value === true ? '用途已声明为是' : advice.saved_value === false ? '用途已声明为否' : '用途尚未声明';
  const state = advice.state === 'conditional_candidate' ? '条件候选，仍待核验' : advice.state === 'not_selected' ? '未选择，不代表不适用' : '尚无候选结论';
  return <article className="og-p2-advice">
    <strong>{usageFields[advice.usage]}：{state}</strong>
    <p>{selection} · {saved} · 范围：资源级</p>
    {advice.conditions.length ? <div><span>后端列出的必要条件：</span><ul>{advice.conditions.map((item, i) => <li key={i}>{item}</li>)}</ul></div>
      : <p>未列出条件；不能据此认定没有义务。</p>}
    {advice.gaps.length ? <div><span>证据缺口：</span><ul>{advice.gaps.map((item, i) => <li key={i}>{item}</li>)}</ul></div> : null}
    {advice.rule_ids.length ? <p>规则引用：{advice.rule_ids.join('、')}</p> : <p>规则引用未获取。</p>}
    <EvidenceRefs ids={advice.basis_evidence_ids} available={available} open={open} />
  </article>;
}

function ResourceDetail({ resource, available, open, openResources }: { resource: P2ResourceResult; available: Set<string>; open: (id: string) => void; openResources?: () => void }) {
  return <details className="og-p2-resource">
    <summary>
      <strong>{resource.subject.resource_id}</strong>
      <span>{resource.resource_kind === 'component' ? '软件组件' : '模型或数据资源'} · {p2StateLabels[resource.state]}</span>
    </summary>
    <p>资源版本：{resource.subject.version || '未获取'} · 适用范围：{resourceScope(resource.scope)}</p>
    <p>核验状态：仅为候选，尚未核验。继承的父评估支持不构成本次新增许可结论。</p>
    {openResources && <button type="button" onClick={openResources}>查看扫描资源卡片</button>}
    {resource.gaps.length ? <div><strong>尚缺信息</strong><ul>{resource.gaps.map((gap, i) => <li key={i}>{gap}</li>)}</ul></div> : null}
    <div><strong>本资源 Evidence</strong><EvidenceRefs ids={resource.evidence_ids} available={available} open={open} /></div>
    {Object.keys(resource.evidence_source_hashes).length
      ? <details><summary>查看证据源文件 Hash</summary><p>这是后端记录的源文件摘要，不证明官方来源、许可证适用性或义务履行。</p><ul>{Object.entries(resource.evidence_source_hashes).map(([id, hash]) => <li key={id}>{id}：{hash}</li>)}</ul></details>
      : <p>证据源文件 Hash 未获取；Evidence ID 本身不能替代源文件 Hash。</p>}
    {resource.material_ids.length ? <p>材料引用：{resource.material_ids.join('、')}（材料观察仍需核验）</p> : null}
    {resource.advice.length ? resource.advice.map(advice => <AdviceDetail key={advice.usage} advice={advice} available={available} open={open} />)
      : <p>后端尚未为此资源返回用途建议，不能推断允许或禁止。</p>}
  </details>;
}

export function P2ResultView({ result, evidenceIds, onEvidence, openResources }: { result: P2Result; evidenceIds: string[]; onEvidence: (id: string) => void; openResources?: () => void }) {
  const [selectedResourceId, setSelectedResourceId] = useState('');
  const [selectedUsage, setSelectedUsage] = useState('');
  const available = new Set(evidenceIds);
  const first = result.resources.slice(0, 3);
  const remaining = result.resources.slice(3);
  const focusedResource = result.resources.find(item => item.subject.resource_id === selectedResourceId) ?? result.resources[0];
  const focusedAdvice = focusedResource?.advice.find(item => item.usage === selectedUsage) ?? focusedResource?.advice[0];
  return <div className="og-p2-result">
    {result.data_scope === 'TEST_ONLY' && <p className="og-p2-test-only">受控验收数据，仅用于功能验证；不是生产历史或许可证明。</p>}
    <div className="og-p2-main">
      <strong>{p2StateLabels[result.state]}</strong>
      <p>独立用途建议 · 资源级 · 第 {result.revision} 版。结果已保存，但不改变正式评估、许可核验或项目合规状态。</p>
      <small>绑定评估 {result.binding.assessment_id} 第 {result.binding.assessment_version} 版 · 结果 {result.result_id}</small>
      {result.state === 'partial' && <p>本结果仅覆盖后端返回的部分信息；未出现的资源不能据此视为已删除。</p>}
      {focusedResource && <section className="og-p2-focus" aria-label="L1资源级用途建议">
        {result.resources.length > 1 && <label>聚焦资源
          <select aria-label="聚焦资源" value={focusedResource.subject.resource_id} onChange={event => {
            setSelectedResourceId(event.target.value); setSelectedUsage('');
          }}>
            {result.resources.map(item => <option key={item.subject.resource_id} value={item.subject.resource_id}>{item.subject.resource_id}</option>)}
          </select>
        </label>}
        <p><strong>适用对象：</strong>{focusedResource.subject.resource_id} @ {focusedResource.subject.version ?? '版本未获取'}</p>
        <p><strong>适用范围：</strong>{resourceScope(focusedResource.scope)} · <strong>资源状态：</strong>{p2StateLabels[focusedResource.state]}</p>
        {focusedResource.advice.length > 1 && <label>聚焦用途
          <select aria-label="聚焦用途" value={focusedAdvice?.usage ?? ''} onChange={event => setSelectedUsage(event.target.value)}>
            {focusedResource.advice.map(item => <option key={item.usage} value={item.usage}>{usageFields[item.usage]}</option>)}
          </select>
        </label>}
        {focusedAdvice
          ? <AdviceDetail advice={focusedAdvice} available={available} open={onEvidence} />
          : <p>后端未返回该资源的用途判断；不能从资源名称或其他用途推断允许或禁止。</p>}
        {focusedResource.gaps.length > 0 && <div><strong>资源信息缺口</strong><ul>{focusedResource.gaps.map((gap, i) => <li key={i}>{gap}</li>)}</ul></div>}
        <p>本卡仅转述后端保存的资源级判断与必要条件；未选择、未知或证据不足均不等于已获授权。</p>
        <div><strong>原扫描 Evidence</strong><EvidenceRefs ids={focusedResource.evidence_ids} available={available} open={onEvidence} /></div>
        <p>材料观察引用：{focusedResource.material_ids.join('、') || '未获取'}；引用本身不证明材料来源或适用性。</p>
        {Object.keys(focusedResource.evidence_source_hashes).length
          ? <details><summary>查看本资源源文件 Hash</summary><p>Hash 仅供核对后端记录，不是官方来源证明。</p><ul>{Object.entries(focusedResource.evidence_source_hashes).map(([id, hash]) => <li key={id}>{id}：{hash}</li>)}</ul></details>
          : <p>本资源源文件 Hash 未获取；不能以 Evidence ID 代替。</p>}
      </section>}
    </div>
    {result.resources.length ? <>
      <p>后端返回 {result.resources.length} 个资源的独立计算结果。未知、待核验和部分结果均保留原状态。</p>
      {first.map(resource => <ResourceDetail key={resource.subject.resource_id} resource={resource} available={available} open={onEvidence} openResources={openResources} />)}
      {remaining.length > 0 && <details className="og-p2-rest"><summary>展开其余 {remaining.length} 个资源</summary>
        {remaining.map(resource => <ResourceDetail key={resource.subject.resource_id} resource={resource} available={available} open={onEvidence} openResources={openResources} />)}
      </details>}
    </> : <p>独立结果没有列出资源；不能由此推断扫描范围完整或不存在资源。</p>}
    <details className="og-assessment-technical"><summary>查看 P2 结果身份与边界</summary>
      <p>结果 SHA-256：{result.result_sha256}</p>
      <p>算法：{result.algorithm_version} · 正式评估影响：无 · 模型调用：0</p>
      <p>本结果仅记录后端返回的资源和证据；companion 摘要不是 Formal Report。</p>
    </details>
  </div>;
}

export function P2AdvicePanel({ scanId, assessmentId, assessmentVersion, evidenceIds, onEvidence, openResources }: {
  scanId: string; assessmentId: string; assessmentVersion: number; evidenceIds: string[]; onEvidence: (id: string) => void; openResources?: () => void;
}) {
  const [view, setView] = useState<View>({ kind: 'loading' });
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setView({ kind: 'loading' });
    void readP2Advice(scanId, assessmentId, assessmentVersion, controller.signal)
      .then(result => { if (!controller.signal.aborted) setView(result ? { kind: 'ready', result } : { kind: 'empty' }); })
      .catch(error => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError && error.status === 503 && error.code === 'p2_service_disabled'
          ? '当前后端没有启用 P2 独立结果。正式评估仍可阅读。'
          : error instanceof Error ? error.message : '独立结果读取失败。';
        setView({ kind: 'error', message });
      });
    return () => controller.abort();
  }, [scanId, assessmentId, assessmentVersion, reload]);

  return <Panel title="P2 用途建议 · 独立结果">
    <div className="og-p2-panel">
      <p>此区只展示后端保存的确定性候选和缺口；Formal Assessment 以上方正式评估为准。</p>
      {view.kind === 'loading' && <p role="status">正在按当前评估版本读取独立结果…</p>}
      {view.kind === 'empty' && <p role="status">当前评估尚未生成 P2 独立结果。浏览页面不会自动生成。</p>}
      {view.kind === 'error' && <p className="og-error" role="alert">{view.message}</p>}
      {view.kind === 'ready' && <P2ResultView result={view.result} evidenceIds={evidenceIds} onEvidence={onEvidence} openResources={openResources} />}
      <button type="button" onClick={() => setReload(value => value + 1)}>重新读取独立结果</button>
    </div>
  </Panel>;
}
