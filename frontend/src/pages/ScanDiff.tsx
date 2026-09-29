import { useEffect, useState } from 'react';
import type { Mode } from '../types/domain';
import { scanPath } from '../hooks/useRoute';
import { Dialog, Empty, Header, Panel } from '../components/ui';
import { comparisonGate, getDiffEvidence, getScanDiff, listAllHistory, resourceSlice, type EvidenceDetail, type EvidenceRef, type FactChange, type HistoryItem, type ResourceChange, type ScanDiff } from '../services/scanDiff';

const shown = (value: string | null | undefined) => value === null || value === undefined || value === '' ? '未获取' : value;
const statusText: Record<string, string> = { queued: '排队中', running: '扫描中', completed: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消' };
const kindText: Record<ResourceChange['kind'], string> = { added: '新增', not_observed_in_target: '目标扫描未观测到', changed: '变化', ambiguous: '匹配不确定', unmatched: '未匹配' };
const evidenceStatus: Record<string, string> = { unknown: '未知', pending: '待核验', verified: '已核验' };
const verificationShown = (value: string | null) => value && evidenceStatus[value] ? evidenceStatus[value] : shown(value);

export function ScanDiff({ targetId, mode, query, go }: { targetId: string; mode: Mode; query: URLSearchParams; go: (url: string) => void }) {
  const baseId = query.get('base') ?? '';
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyState, setHistoryState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [historyError, setHistoryError] = useState('');
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const [diff, setDiff] = useState<ScanDiff | null>(null);
  const [diffState, setDiffState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [diffError, setDiffError] = useState('');
  const [diffAttempt, setDiffAttempt] = useState(0);
  const [page, setPage] = useState(0);
  const [evidenceRef, setEvidenceRef] = useState<EvidenceRef | null>(null);
  const [evidence, setEvidence] = useState<EvidenceDetail | null>(null);
  const [evidenceError, setEvidenceError] = useState('');
  const [evidenceAttempt, setEvidenceAttempt] = useState(0);
  useEffect(() => {
    if (mode !== 'api') return;
    const controller = new AbortController();
    setHistoryState('loading');
    listAllHistory(controller.signal).then(items => { setHistory(items); setHistoryState('ready'); }, error => { if (!controller.signal.aborted) { setHistoryError(String(error.message ?? error)); setHistoryState('error'); } });
    return () => controller.abort();
  }, [mode, historyAttempt]);
  const base = history.find(item => item.scan_id === baseId);
  const target = history.find(item => item.scan_id === targetId);
  const gate = comparisonGate(base, target);
  useEffect(() => {
    setPage(0);
    setDiff(null);
    if (mode !== 'api' || historyState !== 'ready' || gate) { setDiffState('idle'); return; }
    const controller = new AbortController();
    setDiffState('loading');
    getScanDiff(baseId, targetId, controller.signal).then(value => { setDiff(value); setDiffState('ready'); }, error => { if (!controller.signal.aborted) { setDiffError(String(error.message ?? error)); setDiffState('error'); } });
    return () => controller.abort();
  }, [mode, historyState, gate, baseId, targetId, diffAttempt]);
  useEffect(() => {
    if (!evidenceRef) return;
    const controller = new AbortController();
    setEvidence(null); setEvidenceError('');
    getDiffEvidence(evidenceRef, controller.signal).then(setEvidence, error => { if (!controller.signal.aborted) setEvidenceError(String(error.message ?? error)); });
    return () => controller.abort();
  }, [evidenceRef, evidenceAttempt]);
  const navigate = (id: string, section: 'progress' | 'resources' | 'risks' | 'assessment', extra?: string) => {
    const q = new URLSearchParams();
    if (section === 'resources' && extra) q.set('resource_id', extra);
    if (section === 'assessment' && extra) q.set('assessment_id', extra);
    go(scanPath(id, section, 'api', q, section === 'risks' ? extra : undefined));
  };
  const choose = (nextBase: string, nextTarget: string) => {
    const q = new URLSearchParams();
    if (nextBase) q.set('base', nextBase);
    go(scanPath(nextTarget, 'diff', 'api', q));
  };
  const evidenceButtons = (refs: EvidenceRef[]) => refs.length ? <div className="og-diff-evidence">证据：{refs.map((ref, index) => <button type="button" key={`${ref.scan_id}:${ref.evidence_id}:${index}`} onClick={() => setEvidenceRef(ref)}>{ref.evidence_id} ↗</button>)}</div> : <p>证据：未获取</p>;
  const facts = (title: string, rows: FactChange[], caption: string) => <Panel title={`${title} · ${rows.length}`} caption={caption}>{rows.length ? <div className="og-diff-list">{rows.map((row, index) => <article className="og-diff-row" key={`${row.path}:${index}`}><strong className="og-wrap">{row.path}</strong><p>基准：{title === '核验状态变化' ? verificationShown(row.before) : shown(row.before)} → 目标：{title === '核验状态变化' ? verificationShown(row.after) : shown(row.after)}</p><p>来源 ID：{row.source_ids_before.length ? row.source_ids_before.join('、') : '未获取'} → {row.source_ids_after.length ? row.source_ids_after.join('、') : '未获取'}</p>{evidenceButtons(row.evidence_refs)}{title === 'Finding 变化' && <div className="og-actions">{row.source_ids_before.map(id => <button key={`base:${id}`} onClick={() => navigate(baseId, 'risks', id)}>基准 Finding {id} ↗</button>)}{row.source_ids_after.map(id => <button key={`target:${id}`} onClick={() => navigate(targetId, 'risks', id)}>目标 Finding {id} ↗</button>)}</div>}</article>)}</div> : <Empty title="接口未返回此维度的变化" detail="仅表示本次 Diff 未列出变化，不等于合规。" />}</Panel>;
  return <div className="og-diff">
    <Header title="扫描差异" eyebrow="SCAN DIFF / READ ONLY" description="差异仅来自真实 Diff API；未观测到不等于已删除，整改状态也不改变正式 Assessment。" />
    {mode !== 'api' ? <Empty title="差异页面仅支持真实接口模式" detail="演示数据不用于正式扫描对比。" /> : historyState === 'loading' ? <Empty title="正在读取真实扫描历史…" /> : historyState === 'error' ? <Empty title="历史读取失败" detail={historyError}><button onClick={() => setHistoryAttempt(v => v + 1)}>重试</button></Empty> : <>
      <Panel title="选择两次扫描" caption="base 与 target 保存在 URL；只读取后端数据，不触发扫描或评估。"><div className="og-diff-selectors"><label>基准扫描<select aria-label="基准扫描" value={baseId} onChange={event => choose(event.target.value, targetId)}><option value="">请选择</option>{history.map(item => <option value={item.scan_id} key={item.scan_id}>{item.scan_id} · {shown(item.revision)} · {statusText[item.status]}</option>)}</select></label><label>目标扫描<select aria-label="目标扫描" value={target ? targetId : ''} onChange={event => choose(baseId, event.target.value)}><option value="">请选择</option>{history.map(item => <option value={item.scan_id} key={item.scan_id}>{item.scan_id} · {shown(item.revision)} · {statusText[item.status]}</option>)}</select></label></div><div className="og-diff-scanrefs">{[base, target].map((item, index) => <div key={index}><strong>{index ? '目标' : '基准'}</strong><p className="og-wrap">{item?.scan_id ?? '未选择'}</p><p>revision：{shown(item?.revision)}</p><p>状态：{item ? statusText[item.status] : '未获取'}；资源 {item ? item.component_count + item.ai_asset_count : '未获取'}；Finding {item?.finding_count ?? '未获取'}</p>{item && <button onClick={() => navigate(item.scan_id, 'progress')}>查看扫描 ↗</button>}</div>)}</div></Panel>
      {gate ? <Empty title="暂不能请求差异" detail={gate} /> : diffState === 'loading' ? <Empty title="正在读取真实 Diff…" /> : diffState === 'error' ? <Empty title="Diff 读取失败" detail={diffError}><button onClick={() => setDiffAttempt(v => v + 1)}>重试</button></Empty> : diff && <>
        <Panel title="覆盖范围与结论边界" caption={`后端 view_id：${diff.view_id}`}><p>基准覆盖：{diff.coverage.base_complete ? '完整' : '不完整'}；目标覆盖：{diff.coverage.target_complete ? '完整' : '不完整'}。</p><p>扫描状态：{statusText[diff.base.status]} → {statusText[diff.target.status]}；revision：{shown(diff.base.revision)} → {shown(diff.target.revision)}</p>{diff.coverage.gaps.length ? <ul>{diff.coverage.gaps.map((gap, index) => <li key={index} className="og-wrap">{gap}</li>)}</ul> : <p>后端未报告覆盖缺口。</p>}{(!diff.coverage.base_complete || !diff.coverage.target_complete) && <p className="og-diff-warning">存在部分扫描或覆盖缺口：未出现的资源不能视为已删除。</p>}</Panel>
        <Panel title={`资源变化 · ${diff.resources.length}`} caption="分类、字段变化及删除确认均来自后端；每页展示 50 项。">{diff.resources.length ? <><div className="og-diff-list">{resourceSlice(diff.resources, page).map((row, index) => <article className="og-diff-row" key={`${page}:${index}`}><strong>{kindText[row.kind]}</strong><p className="og-wrap">{row.before ? row.before.resource_id : '基准无此资源'} → {row.after ? row.after.resource_id : '目标未观测到'}</p><p>类型：{shown(row.before?.resource_kind)} → {shown(row.after?.resource_kind)}</p>{row.kind === 'not_observed_in_target' && <p className="og-diff-warning">{row.removal_confirmed === true ? '后端确认移除' : '仅目标扫描未观测到；不能断言删除'}</p>}{row.field_changes.map((field, i) => <p className="og-wrap" key={i}>{field.path}：{field.path.endsWith('/verification_status') ? verificationShown(field.before) : shown(field.before)} → {field.path.endsWith('/verification_status') ? verificationShown(field.after) : shown(field.after)}</p>)}{evidenceButtons(row.evidence_refs)}<div className="og-actions">{row.before && <button onClick={() => navigate(row.before!.scan_id, 'resources', row.before!.resource_id)}>基准资源 ↗</button>}{row.after && <button onClick={() => navigate(row.after!.scan_id, 'resources', row.after!.resource_id)}>目标资源 ↗</button>}</div></article>)}</div><div className="og-actions"><button disabled={page === 0} onClick={() => setPage(v => v - 1)}>上一页</button><span>第 {page + 1} / {Math.ceil(diff.resources.length / 50)} 页</span><button disabled={(page + 1) * 50 >= diff.resources.length} onClick={() => setPage(v => v + 1)}>下一页</button></div></> : <Empty title="无资源差异记录" detail="仅表示后端未返回资源差异；不等于两次扫描覆盖完全。" />}</Panel>
        {facts('观测许可变化', diff.license_observation_changes, '仅展示后端记录，不推断许可证或授权。')}
        {facts('核验状态变化', diff.verification_changes, '未知、待核验、已核验以证据为准。')}
        {facts('Finding 变化', diff.finding_changes, 'Finding 是待核查线索，不代表已经违法。')}
        <Panel title="Formal Assessment 变化" caption="正式评估以各自 Assessment 为准；本页不生成第二套结论。"><p>比较状态：{diff.assessment_diff.status === 'compared' ? '已比较' : diff.assessment_diff.status === 'not_comparable' ? '不可比较' : '不可用'}</p>{diff.assessment_diff.reason && <p>{diff.assessment_diff.reason}</p>}<div className="og-actions">{diff.assessment_diff.base && <button onClick={() => navigate(baseId, 'assessment', diff.assessment_diff.base!.assessment_id)}>基准 Assessment ↗</button>}{diff.assessment_diff.target && <button onClick={() => navigate(targetId, 'assessment', diff.assessment_diff.target!.assessment_id)}>目标 Assessment ↗</button>}</div>{diff.assessment_diff.status === 'compared' ? diff.assessment_diff.changes.length ? <div className="og-diff-list">{diff.assessment_diff.changes.map((row, index) => <article key={index} className="og-diff-row"><strong className="og-wrap">{row.path}</strong><p>{shown(row.before)} → {shown(row.after)}</p>{evidenceButtons(row.evidence_refs)}</article>)}</div> : <p>后端未返回正式评估变化。</p> : <p>不可据此声称 Assessment 没有变化。</p>}</Panel>
      </>}
    </>}
    {evidenceRef && <Dialog title="真实 Evidence" onClose={() => setEvidenceRef(null)}>{evidenceError ? <Empty title="Evidence 读取失败" detail={evidenceError}><button onClick={() => setEvidenceAttempt(v => v + 1)}>重试</button></Empty> : evidence ? <div className="og-diff-evidence-detail"><p>ID：{evidence.id}</p><p>核验状态：{evidenceStatus[evidence.verification_status]}</p><p>类型：{evidence.kind}</p><p className="og-wrap">来源：{evidence.locator}</p><pre className="og-wrap">{shown(evidence.excerpt)}</pre></div> : <p>读取 Evidence 中…</p>}</Dialog>}
  </div>;
}
