import { useEffect, useRef, useState } from 'react';
import type { Scan } from '../types/domain';
import { reportDownloadUrl } from '../services/scans';
import { type Assessment } from '../services/assessments';
import { listAllTasks, type RemediationTask } from '../services/remediationTasks';
import { classifyReportObservations, createReportV2, downloadReportV2, loadReportV2, loadReportAssessmentChoices, reportCreateControl, reportP2ContextUrl, readReportReferences, rememberReportReference, type ReportReference, type ReportDocument, type ReportSection } from '../services/reportV2';
import { createNoticeDraft, type NoticeDraft } from '../services/noticeDrafts';
import { ActionButton, DownloadControl, DownloadGlyph, Header, HelpTip, LoadingDots, Panel, useNotice } from '../components/ui';

type State = { kind: 'idle' | 'loading' | 'ready' | 'error'; document?: ReportDocument; html?: string; message?: string };
const names: Record<string, string> = {
  scan_facts: '扫描事实', formal_assessment: 'Formal Assessment · 正式评估',
  workflow: 'Action Plan · 整改进度快照', observation: '其他观测',
  ai_explanation: 'AI 建议 · 非正式结论',
};

function sectionName(section: ReportSection, graph: Set<ReportSection>, notice: Set<ReportSection>) {
  if (graph.has(section)) return '图谱观察摘要';
  if (notice.has(section)) return 'NOTICE 草稿观察';
  return names[section.authority] ?? section.authority;
}

export function ReportV2({ scan, query, open }: {
  scan: Scan;
  query: URLSearchParams;
  open: (assessmentId: string, snapshotId: string) => void;
}) {
  const notify = useNotice();
  const assessmentId = query.get('assessment_id')?.trim() ?? '';
  const snapshotId = query.get('snapshot_id')?.trim() ?? '';
  const [entryAssessment, setEntryAssessment] = useState(assessmentId);
  const [entrySnapshot, setEntrySnapshot] = useState(snapshotId);
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [loadedPreview, setLoadedPreview] = useState('');
  const [downloading, setDownloading] = useState<'json' | 'html' | null>(null);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [createAssessmentId, setCreateAssessmentId] = useState('');
  const [reportTasks, setReportTasks] = useState<RemediationTask[]>([]);
  const [assessmentLoading, setAssessmentLoading] = useState(scan.mode === 'api');
  const [taskLoading, setTaskLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [noticeCreating, setNoticeCreating] = useState(false);
  const [noticeDraft, setNoticeDraft] = useState<NoticeDraft | null>(null);
  const [noticeError, setNoticeError] = useState('');
  const [assessmentError, setAssessmentError] = useState('');
  const [taskError, setTaskError] = useState('');
  const createLoading = assessmentLoading || taskLoading;
  const loadError = assessmentError || taskError;
  const [createError, setCreateError] = useState('');
  const createKey = useRef(crypto.randomUUID());
  const noticeKey = useRef(crypto.randomUUID());
  const [reload, setReload] = useState(0);
  const [recent, setRecent] = useState<ReportReference[]>([]);
  const [remembered, setRemembered] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const saveSection = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!showCreate || !saveSection.current) return;
    saveSection.current.focus({ preventScroll: true });
    saveSection.current.scrollIntoView({
      block: 'start',
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
  }, [showCreate]);
  useEffect(() => {
    const refs = scan.mode === 'api' ? readReportReferences(scan.id, assessmentId) : [];
    setRecent(refs);
    if (!snapshotId && refs.length) open(assessmentId, refs[0].snapshotId);
  }, [scan.id, scan.mode, assessmentId, snapshotId]);
  useEffect(() => { setEntryAssessment(assessmentId); setEntrySnapshot(snapshotId); }, [assessmentId, snapshotId]);
  useEffect(() => {
    if (scan.mode !== 'api') { setAssessments([]); setCreateAssessmentId(''); setAssessmentLoading(false); return; }
    const controller = new AbortController();
    setAssessmentLoading(true); setAssessmentError(''); setCreateAssessmentId(''); setAssessments([]);
    loadReportAssessmentChoices(scan.id, assessmentId, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setAssessments(value.items);
      setTaskLoading(!!value.selectedId); setCreateAssessmentId(value.selectedId);
    }).catch(error => { if (!controller.signal.aborted) setAssessmentError(error instanceof Error ? error.message : 'Formal Assessment 读取失败。'); })
      .finally(() => { if (!controller.signal.aborted) setAssessmentLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, assessmentId]);
  useEffect(() => {
    if (scan.mode !== 'api' || !createAssessmentId) { setReportTasks([]); setTaskLoading(false); setTaskError(''); return; }
    const controller = new AbortController();
    setTaskLoading(true); setTaskError(''); setReportTasks([]);
    listAllTasks(scan.id, createAssessmentId, controller.signal).then(value => {
      if (!controller.signal.aborted) setReportTasks(value.filter(task => !task.superseded));
    }).catch(error => {
      if (!controller.signal.aborted) { setReportTasks([]); setTaskError(error instanceof Error ? error.message : '整改任务版本读取失败。'); }
    }).finally(() => { if (!controller.signal.aborted) setTaskLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, createAssessmentId]);
  useEffect(() => {
    createKey.current = crypto.randomUUID();
    noticeKey.current = crypto.randomUUID();
    setNoticeDraft(null); setNoticeError(''); setCreateError('');
  }, [createAssessmentId, reportTasks.map(task => `${task.task_id}:${task.version}`).join('|')]);
  useEffect(() => {
    if (scan.mode !== 'api' || !assessmentId || !snapshotId) { setState({ kind: 'idle' }); return; }
    const controller = new AbortController();
    setLoadedPreview('');
    setState({ kind: 'loading' });
    loadReportV2(scan.id, assessmentId, snapshotId, controller.signal)
      .then(result => { if (!controller.signal.aborted) {
        setRemembered(rememberReportReference(result.document));
        setRecent(readReportReferences(scan.id, assessmentId));
        setState({ kind: 'ready', ...result });
      } })
      .catch(error => { if (!controller.signal.aborted) setState({ kind: 'error', message: error instanceof Error ? error.message : '固定报告读取失败。' }); });
    return () => controller.abort();
  }, [scan.id, scan.mode, assessmentId, snapshotId, reload]);
  async function save(format: 'json' | 'html') {
    setDownloading(format);
    try { await downloadReportV2(scan.id, assessmentId, snapshotId, format); return true; }
    catch (error) { notify(error instanceof Error ? error.message : '下载失败，请重试。', 'error'); return false; }
    finally { setDownloading(null); }
  }
  async function create() {
    if (!createAssessmentId || createLoading || creating || loadError) return;
    setCreating(true); setCreateError('');
    try {
      const snapshot = await createReportV2(
        scan.id,
        createAssessmentId,
        createKey.current,
        reportTasks.map(task => ({ task_id: task.task_id, version: task.version })),
        noticeDraft ? [{ draft_id: noticeDraft.draft_id, content_hash: noticeDraft.content_hash }] : [],
      );
      open(createAssessmentId, snapshot.snapshot_id);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Report V2 创建失败。');
    } finally { setCreating(false); }
  }
  async function createNotice() {
    if (!createAssessmentId || createLoading || noticeCreating) return;
    setNoticeCreating(true); setNoticeError('');
    try {
      const draft = await createNoticeDraft(scan.id, createAssessmentId, noticeKey.current);
      setNoticeDraft(draft); createKey.current = crypto.randomUUID(); noticeKey.current = crypto.randomUUID();
    } catch (error) { setNoticeError(error instanceof Error ? error.message : 'NOTICE 草稿创建失败。'); }
    finally { setNoticeCreating(false); }
  }
  const p0 = scan.mode === 'api' ? scan.reportFormats ?? [] : [];
  const document = state.document?.snapshot_id === snapshotId &&
    state.document.binding.scan_ref.scan_id === scan.id &&
    state.document.binding.assessment_ref.assessment_id === assessmentId ? state.document : undefined;
  const sections = document?.sections ?? [];
  const has = (authority: string) => sections.some(section => section.authority === authority);
  const observations = document ? classifyReportObservations(document) : { graph: [], notice: [] };
  const graphSections = new Set(observations.graph);
  const noticeSections = new Set(observations.notice);
  const createControl = reportCreateControl({ assessmentId: createAssessmentId, createLoading, creating, loadError, createError });
  const p2ContextUrl = scan.mode === 'api' ? reportP2ContextUrl(scan.id, query) : null;
  const previewKey = `${scan.id}:${assessmentId}:${snapshotId}`;
  function printPreview() {
    if (!document || loadedPreview !== previewKey) return;
    try {
      const preview = frame.current?.contentWindow;
      if (!preview) throw new Error('preview_not_ready');
      preview.focus();
      preview.print();
    } catch {
      notify('浏览器暂时无法打印嵌入预览，请先下载 HTML 报告，再从浏览器打开打印；尚未生成 PDF。', 'error');
    }
  }
  return <div className="og-v2-page og-archive-page">
    <Header title="报告归档与导出" description="保存这一刻的评估，之后补充材料也不会改动旧报告。适合项目交付、留档和复查。" eyebrow="OPENGUARD / REPORT ARCHIVE" />
    <div className="og-archive-context" role="note">
      <p>归档保留所选评估的用途和判断；补充材料后的结果与摘要独立保存。</p>
      {p2ContextUrl && <a href={p2ContextUrl}>回看当前固定 P2 结果与同版摘要</a>}
    </div>
    <Panel title="本机最近打开" caption="仅列出这台浏览器在当前扫描与评估下成功读取过的报告，不是服务器全部归档。点击后会重新核对并读取原件。">
      <div className="og-archive-toolbar"><p>{recent.length ? `保留 ${recent.length} 份最近打开记录` : '尚无本机打开记录。可通过报告链接打开已有归档，或保存当前评估。'}</p><button type="button" className="og-primary" disabled={scan.mode !== 'api'} onClick={() => setShowCreate(value => !value)}>{showCreate ? '收起保存选项' : '保存当前评估的新归档'}</button></div>
      {recent.length > 0 && <ul className="og-archive-list">{recent.map(ref => <li key={ref.snapshotId} className={snapshotId === ref.snapshotId ? 'selected' : ''}>
        <div><strong>评估第 {ref.assessmentVersion} 版</strong><span>保存于 {new Date(ref.createdAt).toLocaleString('zh-CN')}</span></div>
        <button type="button" onClick={() => snapshotId === ref.snapshotId ? setReload(value => value + 1) : open(ref.assessmentId, ref.snapshotId)}>{snapshotId === ref.snapshotId ? '重新核对并预览' : '预览此归档'}</button>
      </li>)}</ul>}
      {!remembered && <p role="status">此浏览器未能保存最近打开记录；报告仍可正常阅读，请保留地址栏中的固定链接。</p>}
    </Panel>
    {state.kind === 'idle' && <div className="og-archive-empty"><h2>从已有报告开始</h2><p>有归档链接时直接打开即可；第一次使用可点击「保存当前评估的新归档」。打开页面本身不会创建报告。</p></div>}
    {state.kind === 'loading' && <Panel title="正在读取报告原件"><LoadingDots label="正在读取固定版本报告" detail="按固定版本读取，旧报告内容保持不变。" /></Panel>}
    {state.kind === 'error' && <Panel title="这份归档暂时无法读取"><p role="alert">{state.message}</p><button onClick={() => setReload(value => value + 1)}>重试读取</button><p>请确认当前服务和报告链接；不会用其他版本代替。</p></Panel>}
    {state.kind === 'ready' && document && state.html && <Panel title={`已保存报告 · Assessment 评估第 ${document.binding.assessment_ref.version} 版`} caption={`保存于 ${new Date(document.created_at).toLocaleString('zh-CN')}。下方是后端保存的原始报告，后续补充信息不会改变这份内容。`}>
      <div className="og-archive-downloads"><DownloadControl key={`${previewKey}:html`} disabled={!!downloading} onDownload={() => save('html')}>下载 HTML 报告</DownloadControl><button className="og-download-button" disabled={loadedPreview !== previewKey} onClick={printPreview}><DownloadGlyph /><span>打印 / 保存 PDF</span></button><DownloadControl key={`${previewKey}:json`} disabled={!!downloading} onDownload={() => save('json')}>下载 JSON 数据</DownloadControl></div>
      <iframe className="og-archive-preview" ref={frame} title="Report V2 后端原始 HTML 正文" srcDoc={state.html} sandbox="allow-same-origin allow-modals" onLoad={() => setLoadedPreview(previewKey)} />
      <details className="og-archive-advanced"><summary>高级信息：来源、版本与报告内容范围</summary><p>固定来源 <HelpTip label="来源 Hash 说明">Hash 来自后端固定快照；前端不会猜测或重新生成正式来源 Hash。</HelpTip></p>
        <dl className="og-v2-meta"><dt>归档编号</dt><dd>{document.snapshot_id}</dd><dt>扫描编号</dt><dd>{document.binding.scan_ref.scan_id}</dd><dt>项目修订</dt><dd>{document.binding.scan_ref.revision ?? '未获取'}</dd><dt>扫描覆盖</dt><dd>{document.binding.scan_ref.status === 'partial' ? '部分完成' : document.binding.scan_ref.status}</dd><dt>正式评估</dt><dd>{document.binding.assessment_ref.assessment_id} · v{document.binding.assessment_ref.version}</dd><dt>生成版本</dt><dd>{document.generator_version}</dd></dl>
        <p>{has('formal_assessment') ? '正式评估来自归档绑定的同一对象与版本。' : '正式评估章节缺失。'} {has('ai_explanation') ? 'AI 章节仅保留历史状态与说明，不改变正式结论。' : '此归档没有 AI 说明。'}</p>
        <p>处理记录仅表示当时的完成进度；不能单凭已完成状态判断项目合规。</p>
        <p>{observations.graph.length ? '包含已绑定的图谱观察。' : '未包含已绑定的图谱观察。'} {document.binding.notice_refs.length ? '包含后端固定的 NOTICE 草稿引用；草稿不等于授权证明。' : '未附 NOTICE 草稿；不表示没有相关声明义务。'}</p>
        <ul>{sections.map((section, index) => <li key={index}><strong>{sectionName(section, graphSections, noticeSections)}</strong> · {section.schema_version} · 来源 {section.source_ids.join('、') || '未获取'} · hash {section.content_hash}</li>)}</ul>
        <details><summary>查看原始来源字段</summary><pre>{JSON.stringify(document.provenance, null, 2)}</pre></details>
      </details>
    </Panel>}
    <details className="og-archive-help" open><summary>归档如何使用 · 查看保存范围</summary>
      <div className="og-archive-guide">
        <div><strong>查看当前结论</strong><p>到「合规报告」阅读本次扫描的完整内容。</p></div>
        <div><strong>保留历史版本</strong><p>在这里保存报告；每份归档有自己的固定链接。</p></div>
        <div><strong>分享与交付</strong><p>下载 HTML 离线阅读，或打印为 PDF；JSON 供技术核对。</p></div>
      </div>
      <div className="og-report-version-boundary" role="note"><strong>评估版次与材料结果分别保留</strong><p>这里归档所选评估的用途、判断与处理进度。P2 补充材料生成的 Result 修订及同版摘要独立保存，不会自动写入这份归档；评估第 2 版也不等于 Result r2。</p></div>
    </details>
    <details ref={saveSection} tabIndex={-1} className="og-archive-save" open={showCreate} onToggle={event => setShowCreate(event.currentTarget.open)}><summary>保存新归档</summary>
    <Panel title="创建固定版本报告" caption="保存一份当前评估和处理进度的副本，便于交付、复查或对比。只在你点击保存按钮后创建。">
      {scan.mode !== 'api' ? <p role="status">演示模式不创建正式报告。</p> : <div className="og-v2-create">
        <label>选择要保存的评估版本<select value={createAssessmentId} disabled={createLoading || creating} onChange={event => { const next = event.target.value; if (next === createAssessmentId) return; setTaskLoading(!!next); setCreateAssessmentId(next); }}><option value="">请选择</option>{assessments.map(item => <option key={item.id} value={item.id}>评估第 {item.version} 版</option>)}</select></label>
        <p>一并保存 {reportTasks.length} 项当前处理记录。保存报告不会重新扫描或改变评估，也不会合并独立的 P2 Result 与材料摘要。</p>
        <details className="og-v2-notice-create"><summary>高级选项：附加 NOTICE 声明草稿</summary>
          <p>NOTICE 只有后端返回不可变草稿和 content hash 后才会加入；前端不生成正文、许可证、授权或 Obligation。</p>
          <button type="button" onClick={createNotice} disabled={!createAssessmentId || createLoading || creating || noticeCreating}>{noticeCreating ? '正在由后端创建草稿…' : '创建并固定 NOTICE 草稿'}</button>
          {noticeDraft && <div role="status">
            <strong>已固定 {noticeDraft.draft_id}</strong>
            <p>hash {noticeDraft.content_hash} · {noticeDraft.generator_version} · {noticeDraft.entries.length} 项</p>
            <p>草稿不是授权证明，不代表义务已履行。缺少正式引用仍为未知；保留文本可能为摘录，以后端缺口为准。</p>
            <details><summary>查看后端保留文本与缺口（{noticeDraft.coverage_gaps.length}）</summary>
              <ul>{noticeDraft.coverage_gaps.map(gap => <li key={gap}>{gap}</li>)}</ul>
              {noticeDraft.entries.map(entry => <section key={entry.entry_id}>
                <h3>{entry.entry_id}</h3>
                <p>资源引用：{entry.resource_ids.join('、') || '未映射 / 未知'}</p>
                <p>正式许可证引用：{entry.license_expression_ids.join('、') || '未提供 / 未知'}</p>
                <p>正式义务引用：{entry.obligation_refs.map(ref => `${ref.namespace}:${ref.source_id}:${ref.obligation_id}`).join('、') || '未提供 / 未知（不等于无义务）'}</p>
                <p>missing：{entry.missing.join('、') || '后端未列出；不代表完整覆盖或合规'}</p>
                {entry.text === null ? <p>未保留正文；不代表 NOTICE 不存在。</p> : <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{entry.text}</pre>}
              </section>)}
            </details>
          </div>}
          {noticeError && <p role="alert" className="og-error">{noticeError}</p>}
        </details>
        <ActionButton type="button" onClick={create} disabled={createControl.disabled} aria-busy={creating}>{createControl.label}</ActionButton>
        {createLoading && <LoadingDots label="正在读取评估与处理记录…" />}
        {loadError && <p role="alert" className="og-error">{loadError}</p>}
        {createError && <div role="alert" className="og-error"><p>{createError}</p><p>不会自动再次提交；手动重试会沿用同一请求标识、Assessment、Task 与 NOTICE 引用，避免产生第二份报告。</p></div>}
      </div>}
    </Panel>
    </details>
    <details className="og-archive-advanced"><summary>高级选项：按编号打开已有报告</summary>
      <p>有既有报告编号时使用；当前后端没有全量报告列表接口。</p>
      <form className="og-v2-picker" onSubmit={event => { event.preventDefault(); open(entryAssessment.trim(), entrySnapshot.trim()); }}>
        <label>评估编号<input value={entryAssessment} onChange={event => setEntryAssessment(event.target.value)} placeholder="asm_…" required /></label>
        <label>报告编号<input value={entrySnapshot} onChange={event => setEntrySnapshot(event.target.value)} placeholder="rptv2_…" required /></label>
        <button type="submit" disabled={scan.mode !== 'api'}>读取报告</button>
      </form>
    </details>
    <details className="og-archive-advanced"><summary>历史扫描附件</summary><p>这些附件属于扫描报告（附件由后端 GET 返回），与上方保存的评估归档分别保留。</p>
      {p0.length ? <div className="og-actions">{p0.map(format => <a key={format} className="og-download-button" href={reportDownloadUrl(scan.id, format)} download><DownloadGlyph /><span>下载扫描附件 {format.toUpperCase()}</span></a>)}</div> : <p>当前扫描没有已发布的历史附件。</p>}
    </details>
  </div>;
}
