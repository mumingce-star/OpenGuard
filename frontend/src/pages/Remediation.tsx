import { useEffect, useMemo, useRef, useState } from 'react';
import type { Scan } from '../types/domain';
import { listAssessments, type Assessment } from '../services/assessments';
import { deriveTasks, isVersionConflict, listAllTasks, optimisticTask, patchTask, taskLinks, type RemediationTask, type TaskStatus } from '../services/remediationTasks';
import { Empty, Header, Panel } from '../components/ui';
import { EvidenceReader } from '../components/EvidenceReader';

const labels: Record<TaskStatus, string> = { todo: '待处理', in_progress: '处理中', done: '已完成任务', dismissed: '已驳回任务' };
const statuses: TaskStatus[] = ['todo', 'in_progress', 'done', 'dismissed'];
type Props = { scan: Scan; query: URLSearchParams; filter: (name: string, value: string) => void; openRisk: (id: string) => void };

export function Remediation({ scan, query, filter, openRisk }: Props) {
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [tasks, setTasks] = useState<RemediationTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selectedEvidence, setSelectedEvidence] = useState<{ taskId: string; id: string } | null>(null);
  const deriveKey = useRef(crypto.randomUUID());
  const requested = query.get('assessment_id');
  const selected = requested ? assessments.find(item => item.id === requested) : assessments[0];
  const selectedId = selected?.id ?? '';
  const selectedStatus = query.get('task_status') ?? 'all';
  const selectedResource = query.get('task_resource') ?? 'all';

  useEffect(() => {
    if (scan.mode !== 'api') { setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError('');
    listAssessments(scan.id, controller.signal).then(value => { if (!controller.signal.aborted) setAssessments(value.items.filter(item => item.scan_id === scan.id && item.formal === true && !!item.facts_hash)); }).catch(reason => { if (!controller.signal.aborted) setError((reason as Error).message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, attempt]);

  useEffect(() => {
    if (!selectedId || scan.mode !== 'api') { setTasks([]); return; }
    const controller = new AbortController();
    setLoading(true); setError('');
    listAllTasks(scan.id, selectedId, controller.signal).then(value => { if (!controller.signal.aborted) { setTasks(value); setDrafts(Object.fromEntries(value.map(task => [task.task_id, task.note]))); } }).catch(reason => { if (!controller.signal.aborted) { setTasks([]); setError((reason as Error).message); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, selectedId, attempt]);

  const resources = useMemo(() => [...new Set(tasks.flatMap(task => task.resource_ids))], [tasks]);
  const filtered = tasks.filter(task => (selectedStatus === 'all' || task.status === selectedStatus) && (selectedResource === 'all' || task.resource_ids.includes(selectedResource) || (selectedResource === 'none' && !task.resource_ids.length)));
  const grouped = useMemo(() => {
    const map = new Map<string, RemediationTask[]>();
    for (const task of filtered) {
      const resource = task.resource_ids.length === 1 ? task.resource_ids[0] : task.resource_ids.length ? 'multiple' : 'none';
      const key = task.status + '|' + resource;
      map.set(key, [...(map.get(key) ?? []), task]);
    }
    return [...map.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [filtered]);

  async function refresh() {
    if (!selectedId) return;
    const value = await listAllTasks(scan.id, selectedId);
    setTasks(value); setDrafts(Object.fromEntries(value.map(task => [task.task_id, task.note])));
  }
  async function update(task: RemediationTask, changes: { status?: TaskStatus; note?: string }) {
    if (busy) return;
    const nextStatus = changes.status ?? task.status;
    const nextNote = changes.note ?? drafts[task.task_id] ?? task.note;
    if (['done', 'dismissed'].includes(nextStatus) && !nextNote.trim()) { setError('已完成或已驳回任务必须填写非空备注；这不是项目合规或义务不适用结论。'); return; }
    const payload = { ...changes, ...(changes.status ? { note: nextNote } : {}) };
    const previous = tasks;
    setBusy(task.task_id); setError(''); setMessage('');
    setTasks(rows => rows.map(row => row.task_id === task.task_id ? optimisticTask(row, payload) : row));
    try {
      const saved = await patchTask(scan.id, selectedId, task, payload);
      setTasks(rows => rows.map(row => row.task_id === task.task_id ? saved : row));
      setDrafts(value => ({ ...value, [task.task_id]: saved.note }));
      setMessage('任务状态已由服务器确认；正式评估未改变。');
    } catch (reason) {
      setTasks(previous);
      if (isVersionConflict(reason)) {
        setError('版本冲突：其他操作已更新此任务，已回滚本地显示并重新读取服务器状态。');
        try { await refresh(); } catch (readError) { setError('版本冲突，重新读取服务器状态失败：' + (readError as Error).message); }
      } else setError('保存失败，已回滚本地显示：' + (reason as Error).message);
    } finally { setBusy(''); }
  }
  async function derive() {
    if (!selected || busy) return;
    setBusy('derive'); setError('');
    try { await deriveTasks(scan.id, selected, deriveKey.current); await refresh(); setMessage('已从当前固定版本 Formal Assessment 派生任务。'); }
    catch (reason) { setError('派生失败：' + (reason as Error).message); }
    finally { setBusy(''); }
  }

  if (scan.mode !== 'api') return <><Header title="整改任务" description="正式任务仅来自真实 Assessment 与 Task API；演示模式不生成任务。" /><Empty title="演示模式不可用" /></>;
  return <>
    <Header eyebrow="P1 / REMEDIATION" title="整改任务工作台" description="任务是独立工作流，不改变 Formal Assessment。done 不等于项目合规；dismissed 不等于义务不适用。" />
    <div className="og-scan-coverage-notice"><strong>优先级：后端未提供</strong><span>冻结 Task 1.0 没有优先级字段；全部任务归入“未提供”组，前端不根据 Finding 严重度或标题猜测。</span></div>
    <Panel title="固定评估版本" caption="刷新只读服务器状态；生成任务需要明确点击，不由 GET 触发。" action={<button type="button" onClick={() => setAttempt(value => value + 1)} disabled={!!busy}>重新读取</button>}>
      <label className="og-field">Formal Assessment<select value={selected?.id ?? ''} onChange={event => filter('assessment_id', event.target.value)}>{assessments.map(item => <option key={item.id} value={item.id}>v{item.version} · {item.id}</option>)}</select></label>
      {selected && <p>评估 ID：{selected.id} · 版本 {selected.version} · Formal Assessment 不因任务更新而改变。</p>}
      {!loading && selected && !tasks.length && !error && <div className="og-actions"><span>该评估尚无整改任务。</span><button type="button" disabled={!!busy} onClick={derive}>从该评估显式生成任务</button></div>}
    </Panel>
    {message && <p role="status" className="og-success">{message}</p>}
    {error && <div role="alert" className="og-error">{error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重试读取</button></div>}
    {loading ? <Empty title="正在读取真实任务…" /> : !selected ? <Empty title="没有可用 Formal Assessment" detail="请先在项目评估页完成正式评估。" /> : tasks.length === 0 ? <Empty title="暂无整改任务" detail="仅显式生成；此页面不会自动创建任务。" /> : <Panel title={`任务 · ${filtered.length} / ${tasks.length}`} caption="优先级未提供 → 状态 → 资源分组。">
      <div className="og-task-filters"><label>状态<select value={selectedStatus} onChange={event => filter('task_status', event.target.value === 'all' ? '' : event.target.value)}><option value="all">全部状态</option>{statuses.map(status => <option key={status} value={status}>{labels[status]}</option>)}</select></label><label>资源<select value={selectedResource} onChange={event => filter('task_resource', event.target.value === 'all' ? '' : event.target.value)}><option value="all">全部资源</option>{resources.map(id => <option key={id} value={id}>{scan.resources.find(item => item.id === id)?.name ?? id}</option>)}<option value="none">未绑定资源</option></select></label></div>
      {!filtered.length ? <Empty title="筛选后没有任务" /> : grouped.map(([key, rows]) => { const [status, resource] = key.split('|') as [TaskStatus, string]; return <section key={key} className="og-task-group"><h3>{labels[status]} · {resource === 'multiple' ? '跨资源任务' : resource === 'none' ? '未绑定资源' : scan.resources.find(item => item.id === resource)?.name ?? resource} <small>{rows.length} 项</small></h3>{rows.map(task => {
        const links = taskLinks(task, selected);
        const ids = task.evidence_refs.filter((ref): ref is Extract<typeof ref, { namespace: 'scan' }> => ref.namespace === 'scan' && ref.scan_id === scan.id).map(ref => ref.evidence_id);
        return <article key={task.task_id} className="og-task-card"><div className="og-task-heading"><div><small>{task.origin.kind} · {task.superseded ? '旧评估版本任务' : '当前评估版本'} · v{task.version}</small><h4>{task.title}</h4></div><span>{labels[task.status]}</span></div><p>来源：{task.origin.source_pointer}</p><p>关联 Finding：{links.findingIds.length ? links.findingIds.map(id => <button type="button" key={id} onClick={() => openRisk(id)}>{id}</button>) : '未提供直接关联'}</p><p>关联 Obligation：{links.obligation ? `${links.obligation.id} · ${links.obligation.action}` : '未提供直接关联'}</p><p>Evidence：{ids.length ? ids.map(id => <button type="button" key={id} onClick={() => setSelectedEvidence(current => current?.taskId === task.task_id && current.id === id ? null : { taskId: task.task_id, id })}>{id}</button>) : '未提供扫描证据'}</p>{task.evidence_refs.some(ref => ref.namespace === 'profile_observation') && <p>另含 Profile Observation 引用；当前扫描证据阅读器不冒充其原文。</p>}{selectedEvidence?.taskId === task.task_id && ids.includes(selectedEvidence.id) && <EvidenceReader key={selectedEvidence.id} scan={scan} ids={[selectedEvidence.id]} initialId={selectedEvidence.id} />}<div className="og-task-edit"><label>任务状态<select value={task.status} disabled={!!busy} onChange={event => update(task, { status: event.target.value as TaskStatus })}>{statuses.map(status => <option key={status} value={status}>{labels[status]}</option>)}</select></label><label>备注<textarea maxLength={2000} value={drafts[task.task_id] ?? task.note} onChange={event => setDrafts(value => ({ ...value, [task.task_id]: event.target.value }))} /></label><button type="button" disabled={!!busy || (drafts[task.task_id] ?? task.note) === task.note} onClick={() => update(task, { note: drafts[task.task_id] ?? task.note })}>保存备注</button></div><small>更新时间：{new Date(task.updated_at).toLocaleString()} · 服务端版本 {task.version}{busy === task.task_id ? ' · 保存中…' : ''}</small></article>;
      })}</section>; })}
    </Panel>}
  </>;
}
