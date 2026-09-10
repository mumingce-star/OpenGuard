import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Scan } from '../types/domain';
import { ApiError } from '../services/scans';
import { listAssessments, createAssessment, getJob, getChat, sendChat, clearChat, assessmentReportUrl, presets, emptyUsage, type Assessment as AssessmentData, type Chat, type Job, type Usage } from '../services/assessments';
import { Header, Panel } from '../components/ui';
import { UsageForm } from '../components/UsageForm';
const labels = { conditional: '可按条件使用', restricted: '当前用途存在限制', unknown: '证据不足，暂无法判断', not_applicable: '不适用' };
const errorText = (e: unknown) => e instanceof ApiError && e.status === 404 ? '当前后端不支持此评估／问答功能，或所选版本不存在。原扫描、风险和历史报告仍可访问。' : e instanceof Error ? e.message : '读取失败，请重试。';
function CompactRows<T>({ rows, label, render }: { rows: T[]; label: string; render: (row: T, index: number) => ReactNode }) {
 const [open, setOpen] = useState(false);
 return <div>{rows.slice(0, 2).map(render)}{rows.length > 2 && <details open={open} onToggle={e => setOpen(e.currentTarget.open)}><summary>{open ? '收起' : '展开全部'}{label}（共 {rows.length} 项）</summary>{open && rows.slice(2).map((row, i) => render(row, i + 2))}</details>}</div>;
}
const aiLabels: Record<string, string> = { succeeded: 'AI 解释已生成，内容仍需核对', fallback: 'AI 未成功，使用确定性回退说明', not_requested: '尚未请求 AI 解释', failed: 'AI 解释生成失败' };
export function Assessment({ scan, query, selectVersion, compact = false }: { scan: Scan; query: URLSearchParams; selectVersion: (id: string) => void; compact?: boolean }) {
 const [items, setItems] = useState<AssessmentData[]>([]), [usage, setUsage] = useState<Usage>(emptyUsage), [chat, setChat] = useState<Chat | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [job, setJob] = useState<Job | null>(null), [revision, setRevision] = useState(0), [message, setMessage] = useState(''), [confirmUsage, setConfirmUsage] = useState(false), [confirmClear, setConfirmClear] = useState(false), [evidenceId, setEvidenceId] = useState(''), [chatOpen, setChatOpen] = useState(true), [copyNotice, setCopyNotice] = useState('');
 const [showAllHistory, setShowAllHistory] = useState(false);
 const evidencePanel = useRef<HTMLDivElement>(null);
 useEffect(() => { if (evidenceId) evidencePanel.current?.scrollIntoView({ block: "center", behavior: "auto" }); }, [evidenceId]);
 const readEpoch = useRef(0);
 const life = useRef(0), lock = useRef(false), requestKey = useRef(crypto.randomUUID()), chatKey = useRef(crypto.randomUUID());
 const requested = query.get('assessment_id');
 const selected = requested ? items.find(a => a.id === requested) : items[0];
 const pending = job?.status === 'pending' || chat?.items.some(t => t.status === 'pending');
 useEffect(() => { life.current++; return () => { life.current++; }; }, []);
 useEffect(() => { if (selected) setUsage(selected.usage); requestKey.current = crypto.randomUUID(); setMessage(''); setShowAllHistory(false); setEvidenceId(''); setConfirmUsage(false); setConfirmClear(false); chatKey.current = crypto.randomUUID(); }, [selected?.id]);
 useEffect(() => {
  if (scan.mode !== 'api') { setLoading(false); return; }
  const epoch = ++readEpoch.current;
  const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
  async function read() {
   try {
    const result = await listAssessments(scan.id, controller.signal);
    if (controller.signal.aborted || readEpoch.current !== epoch) return;
    setItems(result.items);
    let history: Chat | null = null;
    if (!compact) history = await getChat(scan.id, controller.signal);
    let nextJob = result.pending_job ?? job;
    if (nextJob?.status === 'pending') nextJob = await getJob(scan.id, nextJob.request_id, controller.signal);
    if (controller.signal.aborted || readEpoch.current !== epoch) return;
    setItems(result.items); setChat(history); setError('');
    // Reading a saved version never creates an assessment or changes its declared use.
    if (!items.length && result.usage) setUsage(result.usage);
    if (nextJob && (nextJob.status !== job?.status || nextJob.request_id !== job?.request_id)) { setJob(nextJob); if (nextJob.status === 'succeeded') { requestKey.current = crypto.randomUUID(); if (nextJob.assessment_id) selectVersion(nextJob.assessment_id); setRevision(n => n + 1); } }
    if (nextJob?.status === 'pending' || history?.items.some(t => t.status === 'pending')) timer = setTimeout(read, 2500);
   } catch (e) { if (!controller.signal.aborted && readEpoch.current === epoch) setError(errorText(e)); }
   finally { if (!controller.signal.aborted && readEpoch.current === epoch) setLoading(false); }
  }
  void read(); return () => { controller.abort(); clearTimeout(timer); };
 // A response belongs to this mounted scan only; App keys this component by scan and mode.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [scan.id, scan.mode, compact, revision, job?.request_id]);
 async function generate() {
  if (lock.current) return; lock.current = true; setBusy(true); setError(''); const token = life.current;
  try { const result = await createAssessment(scan.id, usage, requestKey.current); if (life.current !== token) return; setJob(result); setConfirmUsage(false); if (result.assessment_id) selectVersion(result.assessment_id); setRevision(n => n + 1); }
  catch (e) { if (life.current === token) setError(errorText(e)); }
  finally { if (life.current === token) { lock.current = false; setBusy(false); } }
 }
 async function ask(e: React.FormEvent) {
  e.preventDefault(); if (!selected || !chat || lock.current || !message.trim()) return;
  lock.current = true; setBusy(true); setError(''); const token = life.current;
  try { await sendChat(scan.id, { assessment_id: selected.id, request_id: chatKey.current, message: message.trim(), generation: chat.generation }); if (life.current !== token) return; setMessage(''); chatKey.current = crypto.randomUUID(); setRevision(n => n + 1); }
  catch (e) { if (life.current === token) setError(errorText(e)); }
  finally { if (life.current === token) { lock.current = false; setBusy(false); } }
 }
 async function clear() {
  if (!chat || lock.current) return; lock.current = true; setBusy(true); const token = life.current;
  try { ++readEpoch.current; await clearChat(scan.id, chat.generation); if (life.current !== token) return; setChat(null); setConfirmClear(false); chatKey.current = crypto.randomUUID(); setRevision(n => n + 1); }
  catch (e) { if (life.current === token) setError(errorText(e)); }
  finally { if (life.current === token) { lock.current = false; setBusy(false); setRevision(n => n + 1); } }
 }
 async function copyAnswer(answer: string) { try { await navigator.clipboard.writeText(answer); setCopyNotice('已复制答复'); } catch { setCopyNotice('复制未成功，请选中文字手动复制。'); } }
 const references = (ids: string[]) => <CompactRows rows={ids} label="证据引用" render={(id, index) => <button className="og-evidence-ref" key={id} type="button" title={id} aria-label={"查看本任务证据 " + id} onClick={() => setEvidenceId(id)}>{scan.evidence.some(e => e.id === id) ? '查看证据' : '证据待核对'} {index + 1}</button>} />;
 if (scan.mode !== 'api') return <Panel title="项目整体评估"><p>演示快照不生成真实评估或本地模型答疑。请通过真实接口完成扫描。</p></Panel>;
 const evidence = scan.evidence.find(e => e.id === evidenceId);
 return <section className="og-assessment">
  <Header title={compact ? '项目评估摘要' : '项目整体评估'} description="基于当前扫描事实、用途和规则；证据不足不代表许可通过。" />
  {loading && <p role="status">正在读取已保存评估…</p>}
  {error && <p className="og-error" role="alert">{error}</p>}
  <div className="og-actions"><button disabled={busy} onClick={() => setRevision(n => n + 1)}>重新读取评估</button>{items.length > 0 && <label>评估版本 <select aria-label="评估版本" value={requested ?? selected?.id ?? ''} disabled={busy} onChange={e => selectVersion(e.target.value)}>{requested && !selected && <option value={requested}>所选版本不存在</option>}{items.map(a => <option key={a.id} value={a.id}>第 {a.version} 版 · {new Date(a.generated_at).toLocaleString()}</option>)}</select></label>}</div>
  {requested && !selected && !loading && <p className="og-error">当前扫描中未找到所选评估版本，不会替换为其他任务的结论。</p>}
  <div className={compact ? "" : "og-assessment-layout" + (chatOpen ? "" : " chat-collapsed")}><div className="og-assessment-main">
  {selected ? <>
   <p>第 {selected.version} 版 · {presets[selected.usage.preset]} · {new Date(selected.generated_at).toLocaleString()}</p>
   <p className="og-assessment-summary">{selected.summary}</p><details className="og-assessment-technical"><summary>版本与技术信息</summary><p>规则版本：{selected.rule_version}</p><p>模型：{selected.model_version}</p><p>提示版本：{selected.prompt_version}</p><p>扫描终态：{scan.status === 'partial' ? '部分完成（覆盖不完整）' : scan.status === 'completed' ? '已完成' : scan.status}</p></details>
   {selected.coverage_issues.length > 0 && <div className="og-error"><strong>扫描存在 {selected.coverage_issues.length} 项覆盖限制，结论仍需核验。</strong><details><summary>展开全部覆盖限制原文</summary>{selected.coverage_issues.map((x, i) => <p key={i}>{x}</p>)}</details></div>}
   <div className="og-assessment-grid">{selected.dimensions.map(d => <Panel key={d.id} title={d.title}><strong className={'og-conclusion ' + d.status}>{labels[d.status]}</strong><p>{d.unknowns.length ? `尚有 ${d.unknowns.length} 项许可／范围／用途待核验。` : d.restrictions.length ? `存在 ${d.restrictions.length} 项用途限制。` : d.conditions.length ? `需要满足 ${d.conditions.length} 项条件。` : d.status === 'not_applicable' ? '此维度不适用于本次用途。' : '请结合本次用途和证据核对结论。'}</p>{!compact && <><details><summary>展开全部判断与原文（{d.conditions.length + d.restrictions.length + d.unknowns.length} 项）</summary><p>{d.conclusion}</p><CompactRows rows={d.conditions} label="条件" render={(x,i) => <p key={'c'+i}>需要满足：{x}</p>}/><CompactRows rows={d.restrictions} label="限制" render={(x,i) => <p key={'r'+i}>限制：{x}</p>}/><CompactRows rows={d.unknowns} label="待核验项" render={(x,i) => <p key={'u'+i}>待核验：{x}</p>}/>{references(d.evidence_ids)}</details><button disabled={busy || !!pending || !chat} onClick={() => { setChatOpen(true); setMessage(`请根据当前评估说明“${d.title}”的判断依据和下一步需要核对的证据。`); chatKey.current = crypto.randomUUID(); }}>就此提问</button></>}</Panel>)}</div>
   <Panel title="AI 辅助解释"><p role="status">{aiLabels[selected.ai_status] ?? 'AI 状态待核对'}</p>{selected.ai_summary && <p>{selected.ai_summary}</p>}{references(selected.ai_evidence_ids ?? [])}</Panel>
   {<Panel title="需要履行的义务"><p>识别出义务不代表已经履行。</p>{selected.obligations.length ? <CompactRows rows={selected.obligations} label="义务" render={o => <details key={o.id}><summary>{o.action} · {o.fulfillment === 'satisfied' ? '记录为已满足，请复核依据' : '待履行／待确认'}</summary><p>{o.requirement}</p><p>触发条件：{o.trigger}</p><p>规则：{o.rule_id} · {o.rule_version}</p>{references(o.evidence_ids)}</details>} /> : <p>本版本没有列出确定的义务；未知许可仍需复核。</p>}</Panel>}
   <div className="og-actions"><a download href={assessmentReportUrl(scan.id, selected.id, 'html')}>下载本版评估 HTML</a><a download href={assessmentReportUrl(scan.id, selected.id, 'json')}>下载本版评估 JSON</a></div>
  </> : !loading && <p>尚无已保存评估。旧扫描需要你明确生成，不会重新扫描项目。</p>}
  {!compact && <Panel title={selected ? '确认用途并生成新评估版本' : '生成项目评估'}><UsageForm value={usage} disabled={busy || !!pending} onChange={v => { setUsage(v); setConfirmUsage(false); requestKey.current = crypto.randomUUID(); }} /><p>用途变更只影响新评估版本，保留旧评估与原报告。</p>{confirmUsage ? <div className="og-actions"><span>确认按以上用途生成评估？未选的细节仍为未知。</span><button disabled={busy || !!pending} onClick={generate}>确认并生成</button><button disabled={busy} onClick={() => setConfirmUsage(false)}>返回检查</button></div> : <button disabled={busy || !!pending || !!error} onClick={() => setConfirmUsage(true)}>生成评估／更新用途</button>}{job?.status === 'failed' && <button disabled={busy} onClick={() => { requestKey.current = crypto.randomUUID(); setConfirmUsage(true); }}>重新确认并重试评估</button>}{job && <p role="status">{job.status === 'pending' ? '评估正在生成，稍后自动读取…' : job.status === 'failed' ? '评估生成失败：' + (job.error ?? '请重试') : '评估已保存'}</p>}</Panel>}
  </div>{!compact && <aside className="og-assessment-chat"><button aria-expanded={chatOpen} onClick={() => setChatOpen(v => !v)}>{chatOpen ? "收起项目答疑" : "展开项目答疑"}</button>{chatOpen && <Panel title="本地 Qwen3 项目答疑"><p>只解释当前扫描和所选评估；聊天不会修改正式用途、结论或重新扫描。</p>{chat && <p>已保存 {chat.items.length} / {chat.limits.max_turns} 轮；每条最多 {chat.limits.max_message_chars} 字符。历史跨刷新保留，切版本仍显示各条所属版本。</p>}<label><input type="checkbox" checked={showAllHistory} onChange={e => setShowAllHistory(e.target.checked)} />查看其他评估版本的历史问答（旧答复不代表本版结论）</label><div className="og-chat-history">{chat?.items.filter(t => showAllHistory || t.assessment_id === selected?.id).map(t => <article key={t.request_id} className="og-chat-turn"><small>评估 {items.find(a => a.id === t.assessment_id)?.version ?? t.assessment_id} · {new Date(t.created_at).toLocaleString()}</small><p><strong>你：</strong>{t.question}</p><p><strong>Qwen3 辅助答复：</strong>{t.status === 'pending' ? '正在生成…' : t.status === 'failed' ? '未能生成回答：' + (t.error ?? '请稍后重试') : t.answer ?? '未返回有效回答'}</p>{references(t.evidence_ids)}{t.status === 'succeeded' && t.answer && <button onClick={() => copyAnswer(t.answer!)}>复制答复</button>}{t.status === 'failed' && <button disabled={busy || !!pending || t.assessment_id !== selected?.id} onClick={() => { chatKey.current = crypto.randomUUID(); setMessage(t.question); }}>重新填写此问题</button>}</article>)}</div><p role="status">{copyNotice}</p><div className="og-actions" aria-label="建议问题">{['当前用途最需要核对哪些证据？', '哪些条件尚未满足？', '我应该先完成哪三项核验？'].map(question => <button key={question} disabled={busy || !!pending || !selected} onClick={() => { setMessage(question); chatKey.current = crypto.randomUUID(); }}>{question}</button>)}</div><form onSubmit={ask}><label className="og-field">向当前评估提问<textarea value={message} maxLength={chat?.limits.max_message_chars ?? 2000} disabled={busy || !!pending || !selected || !chat} onChange={e => { setMessage(e.target.value); chatKey.current = crypto.randomUUID(); }} placeholder="例如：这个项目用于对外在线服务，还需要核对哪些证据？" /></label><button type="submit" disabled={busy || !!pending || !selected || !chat || !message.trim() || chat.items.length >= chat.limits.max_turns}>发送给本地 Qwen3</button></form>{confirmClear ? <div className="og-actions"><span>确认清空本任务全部问答？所有评估版本与报告会保留。</span><button disabled={busy} onClick={clear}>确认清空问答</button><button onClick={() => setConfirmClear(false)}>取消</button></div> : <button disabled={busy || !chat || !chat.items.length} onClick={() => setConfirmClear(true)}>清空本任务问答</button>}</Panel>}</aside>}</div>
  {evidenceId && <div ref={evidencePanel} tabIndex={-1}><Panel title="本任务证据原文"><button onClick={() => setEvidenceId('')}>关闭证据</button><p>{evidenceId}</p>{evidence ? <><p>{evidence.path ?? evidence.url ?? evidence.label}</p><pre>{evidence.text ?? '未提供原文，请核对扫描证据。'}</pre></> : <p>本扫描未提供对应证据，不能据此确认授权。</p>}</Panel></div>}
 </section>;
}
