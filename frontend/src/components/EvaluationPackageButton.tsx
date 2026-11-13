import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { Assessment } from '../services/assessments';
import type { Result } from '../services/p2';
import { readReportReferences, type ReportReference } from '../services/reportV2';
import { downloadEvaluationPackage, selectEvaluationAnalysis } from '../services/evaluationExport';
import { DownloadGlyph } from './ui';

/** GET-only export; readOnly pages can download without generating a report. */
export function EvaluationPackageButton({ assessment, result }: { assessment: Assessment; result: Result }) {
  const scope = JSON.stringify([assessment.id, assessment.version, result.result_id, result.result_sha256, result.binding]);
  const committed = useRef({ scope, epoch: 0, mounted: false });
  const controller = useRef<AbortController | null>(null);
  const [state, setState] = useState<'idle'|'busy'|'done'|'error'>('idle');
  const [message, setMessage] = useState('');
  const [archives, setArchives] = useState<ReportReference[]>([]);
  const [archiveId, setArchiveId] = useState('');
  useLayoutEffect(() => {
    committed.current = { scope, epoch: committed.current.epoch + 1, mounted: true };
    return () => { committed.current = { ...committed.current, mounted: false, epoch: committed.current.epoch + 1 }; controller.current?.abort(); };
  }, [scope]);
  useEffect(() => {
    setState('idle'); setMessage(''); setArchiveId('');
    setArchives(readReportReferences(assessment.scan_id, assessment.id).filter(x => x.assessmentVersion === assessment.version));
  }, [scope]);
  async function download() {
    if (state === 'busy') return;
    const permit = { ...committed.current };
    const current = () => committed.current.mounted && committed.current.scope === permit.scope && committed.current.epoch === permit.epoch;
    const abort = new AbortController(); controller.current = abort;
    setState('busy'); setMessage('');
    try {
      const selection = await selectEvaluationAnalysis(assessment, result, abort.signal);
      if (!current()) return;
      await downloadEvaluationPackage(assessment, result, { ...selection, ...(archiveId ? { reportSnapshotId: archiveId } : {}) }, abort.signal, current);
      if (current()) { setState('done'); setMessage('已核对文件摘要并发起下载，请在浏览器中确认保存。'); }
    } catch (error) {
      if (!current() || abort.signal.aborted) return;
      setState('error'); setMessage(error instanceof Error ? error.message : '完整评估包未导出，已有版本保留。');
    } finally { if (current()) controller.current = null; }
  }
  return <div className="p2-evaluation-export">
    {archives.length > 0 && <label>附加已归档报告 <select aria-label="评估包附加固定归档" value={archiveId} disabled={state === 'busy'} onChange={event => setArchiveId(event.target.value)}>
      <option value="">仅本版原评估报告与P2结果</option>
      {archives.map(archive => <option key={archive.snapshotId} value={archive.snapshotId}>{new Date(archive.createdAt).toLocaleString()} · {archive.snapshotId.slice(0, 18)}…</option>)}
    </select></label>}
    <button type="button" className="og-download-button" disabled={state === 'busy'} aria-busy={state === 'busy'} onClick={() => void download()}><DownloadGlyph /><span>{state === 'busy' ? '正在核对固定版本…' : '一键导出完整评估包'}</span></button>
    <small>包含本版原评估报告、固定Result与摘要、已关联材料原文和已保存AI状态；下载不重算、不联网补证。</small>
    {message && <p role={state === 'error' ? 'alert' : 'status'}>{message}</p>}
  </div>;
}
