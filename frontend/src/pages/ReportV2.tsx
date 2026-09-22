import { useEffect, useRef, useState } from 'react';
import type { Scan } from '../types/domain';
import { reportDownloadUrl } from '../services/scans';
import { listAssessments, type Assessment } from '../services/assessments';
import { listAllTasks, type RemediationTask } from '../services/remediationTasks';
import { createReportV2, downloadReportV2, loadReportV2, type ReportDocument } from '../services/reportV2';
import { createNoticeDraft, type NoticeDraft } from '../services/noticeDrafts';
import { Header, Panel, useNotice } from '../components/ui';

type State = { kind: 'idle' | 'loading' | 'ready' | 'error'; document?: ReportDocument; html?: string; message?: string };
const names: Record<string, string> = {
  scan_facts: '扫描事实', formal_assessment: 'Formal Assessment · 正式评估',
  workflow: 'Action Plan · 整改进度快照', observation: '图谱观察摘要',
  ai_explanation: 'AI 建议 · 非正式结论',
};

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
  const [downloading, setDownloading] = useState<'json' | 'html' | null>(null);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [createAssessmentId, setCreateAssessmentId] = useState(assessmentId);
  const [reportTasks, setReportTasks] = useState<RemediationTask[]>([]);
  const [createLoading, setCreateLoading] = useState(scan.mode === 'api');
  const [creating, setCreating] = useState(false);
  const [noticeCreating, setNoticeCreating] = useState(false);
  const [noticeDraft, setNoticeDraft] = useState<NoticeDraft | null>(null);
  const [noticeError, setNoticeError] = useState('');
  const [createError, setCreateError] = useState('');
  const createKey = useRef(crypto.randomUUID());
  const noticeKey = useRef(crypto.randomUUID());
  const [reload, setReload] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => { setEntryAssessment(assessmentId); setEntrySnapshot(snapshotId); }, [assessmentId, snapshotId]);
  useEffect(() => {
    if (scan.mode !== 'api') { setAssessments([]); setCreateLoading(false); return; }
    const controller = new AbortController();
    setCreateLoading(true); setCreateError('');
    listAssessments(scan.id, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      const formal = value.items.filter(item => item.scan_id === scan.id && item.formal === true && !!item.facts_hash);
      setAssessments(formal);
      setCreateAssessmentId(current => formal.some(item => item.id === current) ? current : formal[0]?.id ?? '');
    }).catch(error => { if (!controller.signal.aborted) setCreateError(error instanceof Error ? error.message : 'Formal Assessment 读取失败。'); })
      .finally(() => { if (!controller.signal.aborted) setCreateLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode]);
  useEffect(() => {
    if (scan.mode !== 'api' || !createAssessmentId) { setReportTasks([]); return; }
    const controller = new AbortController();
    setCreateLoading(true); setCreateError('');
    listAllTasks(scan.id, createAssessmentId, controller.signal).then(value => {
      if (!controller.signal.aborted) setReportTasks(value.filter(task => !task.superseded));
    }).catch(error => {
      if (!controller.signal.aborted) { setReportTasks([]); setCreateError(error instanceof Error ? error.message : '整改任务版本读取失败。'); }
    }).finally(() => { if (!controller.signal.aborted) setCreateLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, createAssessmentId]);
  useEffect(() => {
    createKey.current = crypto.randomUUID();
    noticeKey.current = crypto.randomUUID();
    setNoticeDraft(null); setNoticeError('');
  }, [createAssessmentId, reportTasks.map(task => `${task.task_id}:${task.version}`).join('|')]);
  useEffect(() => {
    if (scan.mode !== 'api' || !assessmentId || !snapshotId) { setState({ kind: 'idle' }); return; }
    const controller = new AbortController();
    setState({ kind: 'loading' });
    loadReportV2(scan.id, assessmentId, snapshotId, controller.signal)
      .then(result => { if (!controller.signal.aborted) setState({ kind: 'ready', ...result }); })
      .catch(error => { if (!controller.signal.aborted) setState({ kind: 'error', message: error instanceof Error ? error.message : '固定报告读取失败。' }); });
    return () => controller.abort();
  }, [scan.id, scan.mode, assessmentId, snapshotId, reload]);
  async function save(format: 'json' | 'html') {
    setDownloading(format);
    try { await downloadReportV2(scan.id, assessmentId, snapshotId, format); }
    catch (error) { notify(error instanceof Error ? error.message : '下载失败，请重试。', 'error'); }
    finally { setDownloading(null); }
  }
  async function create() {
    if (!createAssessmentId || createLoading || creating || createError) return;
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
  const document = state.document;
  const sections = document?.sections ?? [];
  const has = (authority: string) => sections.some(section => section.authority === authority);
  return <div className="og-v2-page">
    <Header title="Assessment Report V2" description="读取后端已保存的固定版本报告；浏览器不生成、修改或重新判断正式结论。" eyebrow="OPENGUARD / IMMUTABLE REPORT" />
    <Panel title="创建固定版本报告" caption="这是明确的写操作：后端固定当前 Formal Assessment 与所列 Task 版本并保存报告；不会触发扫描、重新评估或 Qwen。">
      {scan.mode !== 'api' ? <p role="status">演示模式不创建正式报告。</p> : <div className="og-v2-create">
        <label>Formal Assessment<select value={createAssessmentId} disabled={createLoading || creating} onChange={event => setCreateAssessmentId(event.target.value)}><option value="">请选择</option>{assessments.map(item => <option key={item.id} value={item.id}>v{item.version} · {item.id}</option>)}</select></label>
        <p>将固定 {reportTasks.length} 个当前整改任务版本。任务 done 不等于项目合规，dismissed 不等于义务不适用。</p>
        <div className="og-v2-notice-create">
          <p>NOTICE 只有后端返回不可变草稿和 content hash 后才会加入；前端不生成正文、许可证、授权或 Obligation。</p>
          <button type="button" onClick={createNotice} disabled={!createAssessmentId || createLoading || creating || noticeCreating}>{noticeCreating ? '正在由后端创建草稿…' : '创建并固定 NOTICE 草稿'}</button>
          {noticeDraft && <div role="status"><strong>已固定 {noticeDraft.draft_id}</strong><span>hash {noticeDraft.content_hash} · {noticeDraft.entries.length} 项 · {noticeDraft.coverage_gaps.length} 个缺口</span></div>}
          {noticeError && <p role="alert" className="og-error">{noticeError}</p>}
        </div>
        <button type="button" onClick={create} disabled={!createAssessmentId || createLoading || creating || !!createError}>{creating ? '正在由后端保存…' : '创建并打开固定报告'}</button>
        {createLoading && <span role="status">正在读取 Assessment 与 Task 版本…</span>}
        {createError && <p role="alert" className="og-error">{createError}</p>}
      </div>}
    </Panel>
    <Panel title="选择固定快照" caption="当前后端没有报告列表接口。请使用显式创建报告后返回的 assessment_id 和 snapshot_id；刷新、分享 URL 可恢复。">
      <form className="og-v2-picker" onSubmit={event => { event.preventDefault(); open(entryAssessment.trim(), entrySnapshot.trim()); }}>
        <label>Assessment ID<input value={entryAssessment} onChange={event => setEntryAssessment(event.target.value)} placeholder="asm_…" required /></label>
        <label>Snapshot ID<input value={entrySnapshot} onChange={event => setEntrySnapshot(event.target.value)} placeholder="rptv2_…" required /></label>
        <button type="submit" disabled={scan.mode !== 'api'}>读取报告</button>
      </form>
      {scan.mode !== 'api' && <p role="status">演示模式不提供正式报告。请切换真实接口和真实扫描。</p>}
    </Panel>
    {state.kind === 'idle' && <Panel title="尚未选择 Report V2"><p>未读取固定快照，不会用演示或旧报告冒充。旧版 P0 附件仍可在下方单独下载。</p></Panel>}
    {state.kind === 'loading' && <Panel title="正在读取固定快照"><p role="status">仅发起 JSON/HTML GET，不会创建扫描、Assessment、报告或调用 AI。</p></Panel>}
    {state.kind === 'error' && <Panel title="Report V2 暂不可用"><p role="alert">{state.message}</p><button onClick={() => setReload(value => value + 1)}>重试读取</button><p>旧版 P0 报告不会作为 Report V2 替代；可单独下载核查。</p></Panel>}
    {state.kind === 'ready' && document && state.html && <>
      <Panel title="来源与版本" caption="以下信息来自已保存的 Report V2 JSON；正式正文由后端 HTML 原样显示。">
        <dl className="og-v2-meta"><dt>快照</dt><dd>{document.snapshot_id}</dd><dt>扫描</dt><dd>{document.binding.scan_ref.scan_id}</dd><dt>revision</dt><dd>{document.binding.scan_ref.revision ?? '未获取'}</dd><dt>覆盖状态</dt><dd>{document.binding.scan_ref.status === 'partial' ? '部分扫描完成；缺失不代表资源已删除' : document.binding.scan_ref.status}</dd><dt>正式评估</dt><dd>{document.binding.assessment_ref.assessment_id} · v{document.binding.assessment_ref.version}</dd><dt>保存时间</dt><dd>{document.created_at}</dd><dt>生成版本</dt><dd>{document.generator_version}</dd></dl>
      </Panel>
      <div className="og-v2-layout">
        <nav aria-label="固定报告目录" className="og-v2-toc">
          <strong>目录与来源</strong>
          <a href="#v2-executive">Executive Summary</a>
          <a href="#v2-formal">Formal Assessment</a>
          <a href="#v2-ai">AI 建议</a>
          <a href="#v2-graph">图谱摘要</a>
          <a href="#v2-actions">Action Plan</a>
          <a href="#v2-notice">NOTICE 草稿</a>
          <a href="#v2-provenance">Provenance</a>
          <a href="#v2-download">下载</a>
        </nav>
        <div className="og-v2-content">
          <section id="v2-executive" className="og-v2-boundary"><h2>Executive Summary</h2><p>正文中的项目整体评价来自报告绑定的 Formal Assessment；不在此处重新摘要或推断风险数量。</p></section>
          <section id="v2-formal" className="og-v2-boundary formal"><h2>Formal Assessment · 正式评估</h2><p>{has('formal_assessment') ? '以下嵌入的是后端保存的原始 HTML 报告，不是前端重组的评估。' : '正式评估章节缺失；不能作为正式报告使用。'}</p></section>
          <section id="v2-ai" className="og-v2-boundary ai"><h2>AI 建议 · 辅助解释</h2><p>{has('ai_explanation') ? '后端报告保留历史 AI 状态与正文；AI 不进入 Formal Conclusion。' : '此快照没有 AI 说明。'}</p></section>
          <section id="v2-graph" className="og-v2-boundary"><h2>图谱摘要</h2><p>{has('observation') ? '后端快照包含已有图谱观察；不代表未知关系或授权已确认。' : '此快照没有图谱观察章节；不补造节点或关系。'}</p></section>
          <section id="v2-actions" className="og-v2-boundary"><h2>Action Plan</h2><p>{has('workflow') ? '后端报告中保存了任务版本与处理状态；done 不等于项目合规，dismissed 不等于不适用。' : '此快照没有任务章节。'}</p></section>
          <section id="v2-notice" className="og-v2-boundary draft"><h2>NOTICE 草稿 · 非正式结论</h2>{document.binding.notice_refs.length ? <><p>以下引用来自后端固定快照；完整草稿、缺失字段与来源保留在原始报告中。</p><ul>{document.binding.notice_refs.map(ref => <li key={ref.draft_id}><code>{ref.draft_id}</code> · hash {ref.content_hash}</li>)}</ul></> : <p>当前快照未包含 NOTICE 草稿；后端 reader 尚未提供时不会由前端生成。</p>}</section>
          <section id="v2-provenance" className="og-v2-boundary"><h2>Provenance · 来源</h2><p>以下章节元数据来自报告快照；详情及完整依据保留在后端 HTML 的附录中。</p><ul>{sections.map((section, index) => <li key={index}><strong>{names[section.authority] ?? section.authority}</strong> · {section.schema_version} · 来源 {section.source_ids.join('、') || '未获取'} · hash {section.content_hash}</li>)}</ul><details><summary>查看后端保存的 Provenance 原始字段</summary><pre>{JSON.stringify(document.provenance, null, 2)}</pre></details></section>
          <section className="og-v2-boundary formal" aria-label="后端固定 HTML 报告"><h2>后端固定报告正文</h2><iframe ref={frame} title="Report V2 后端原始 HTML 正文" srcDoc={state.html} sandbox="allow-same-origin" /></section>
          <section id="v2-download" className="og-v2-boundary"><h2>下载固定附件</h2><div className="og-actions"><button disabled={!!downloading} onClick={() => save('html')}>下载 P1 HTML</button><button disabled={!!downloading} onClick={() => save('json')}>下载 P1 JSON</button><button onClick={() => frame.current?.contentWindow?.print()}>打印后端报告</button></div><p>附件由后端 GET 返回；下载失败会提示，不用旧版报告静默代替。</p></section>
        </div>
      </div>
    </>}
    <Panel title="P0 历史附件" caption="旧版扫描报告独立保留，不等同于 Report V2 或新的 Formal Conclusion。">
      {p0.length ? <div className="og-actions">{p0.map(format => <a key={format} href={reportDownloadUrl(scan.id, format)} download>下载 P0 {format}</a>)}</div> : <p>当前扫描没有已发布的 P0 报告附件。</p>}
    </Panel>
  </div>;
}
