import type { Assessment } from './assessments';
import { accountRequestOptions, handleAccountResponse } from './auth';
import { ApiError } from './scans';
import { sameBinding, validateBinding, type Result } from './p2';
import { officialSourcesEnabled, readOfficialSources } from './officialSources';
import { p2AiEnabled, readAiIndex } from './p2Ai';

export type EvaluationExportSelection = { reportSnapshotId?: string; analysisId?: string; previewId?: string };
const identifier = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(v);
const base = () => (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

function bound(a: Assessment, result: Result) {
  if (result.binding.scan_id !== a.scan_id || result.binding.assessment_id !== a.id ||
      result.binding.assessment_version !== a.version || !sameBinding(validateBinding(result.binding, a), result.binding))
    throw Error('评估包与当前固定结果不一致，未发起下载。');
}

/** Resolve saved model IDs once, then pin them in the package request. No POST. */
export async function selectEvaluationAnalysis(a: Assessment, result: Result, signal?: AbortSignal): Promise<EvaluationExportSelection> {
  bound(a, result);
  if (officialSourcesEnabled) {
    const status = await readOfficialSources(a, result, signal);
    if (['queued', 'running', 'waiting_source'].includes(status.analysis.state) || ['queued', 'running'].includes(status.fetch.state))
      throw Error('本版资料或辅助分析仍在处理，请等待状态确定后下载；不会重新生成。');
    if (status.analysis.analysis_id) return { analysisId: status.analysis.analysis_id };
    if (status.analysis.preview) return { previewId: status.analysis.preview.preview_id };
    return {}; // Accurate saved failure/not-scheduled status is included server-side.
  }
  if (p2AiEnabled) {
    const ids = await readAiIndex(a, result, signal);
    if (ids.length > 1) throw Error('本版存在多个独立AI分析，请先明确要导出的固定分析身份。');
    if (ids.length === 1) return { analysisId: ids[0] };
  }
  return {};
}

export function evaluationPackageUrl(a: Assessment, result: Result, selection: EvaluationExportSelection = {}) {
  bound(a, result);
  if ((selection.analysisId && selection.previewId) ||
      [selection.reportSnapshotId, selection.analysisId, selection.previewId].some(x => x !== undefined && !identifier(x)))
    throw Error('评估包的固定引用无效，未发起下载。');
  const query = new URLSearchParams({ assessment_version: String(a.version) });
  if (selection.reportSnapshotId) query.set('report_snapshot_id', selection.reportSnapshotId);
  if (selection.analysisId) query.set('analysis_id', selection.analysisId);
  if (selection.previewId) query.set('preview_id', selection.previewId);
  return `${base()}/scans/${encodeURIComponent(a.scan_id)}/assessments/${encodeURIComponent(a.id)}/p2/results/${encodeURIComponent(result.result_id)}/evaluation-package?${query}`;
}

/** Download only after both byte hash and exact response identity are checked. */
export async function downloadEvaluationPackage(a: Assessment, result: Result, selection: EvaluationExportSelection,
                                               signal: AbortSignal, stillCurrent: () => boolean) {
  const response = await fetch(evaluationPackageUrl(a, result, selection), accountRequestOptions({
    method: 'GET', headers: { Accept: 'application/zip' }, cache: 'no-store', signal,
  }));
  handleAccountResponse(response.status);
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    const reason = value?.error?.details?.reason ?? value?.error?.code;
    const descriptions: Record<string, string> = {
      evaluation_package_sensitive_content_blocked: '本版包含本机路径或疑似敏感内容，已阻止完整包导出；原数据保留。',
      evaluation_package_analysis_in_progress: '本版辅助分析尚未形成确定状态，请稍后只读下载。',
      evaluation_package_analysis_selection_required: '辅助分析身份发生变化，请重新核对固定版本后下载。',
    };
    throw new ApiError(response.status, descriptions[reason] ?? `完整评估包未导出（HTTP ${response.status}），已有结果保留。`, value?.error?.code, reason);
  }
  if (response.status !== 200 || !response.headers.get('Content-Type')?.toLowerCase().includes('application/zip') ||
      response.headers.get('X-OpenGuard-Result-ID') !== result.result_id ||
      response.headers.get('X-OpenGuard-Result-SHA256') !== result.result_sha256 ||
      response.headers.get('X-OpenGuard-Result-Revision') !== String(result.revision) ||
      response.headers.get('X-OpenGuard-Assessment-Version') !== String(a.version))
    throw Error('评估包的返回版本或格式不匹配，已停止保存。');
  const buffer = await response.arrayBuffer();
  if (!stillCurrent() || signal.aborted) throw new DOMException('Aborted', 'AbortError');
  const bytes = new Uint8Array(buffer);
  if (bytes.length < 4 || bytes.length > 32 * 1024 * 1024 ||
      bytes[0] !== 0x50 || bytes[1] !== 0x4b || bytes[2] !== 3 || bytes[3] !== 4)
    throw Error('评估包为空、过大或不是有效ZIP，未保存。');
  const sha = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buffer)), x => x.toString(16).padStart(2, '0')).join('');
  if (sha !== response.headers.get('X-Content-SHA256')) throw Error('评估包字节摘要不一致，未保存。');
  if (!stillCurrent() || signal.aborted) throw new DOMException('Aborted', 'AbortError');
  const url = URL.createObjectURL(new Blob([buffer], { type: 'application/zip' }));
  try {
    const link = document.createElement('a'); link.href = url;
    link.download = `OpenGuard-evaluation-v${a.version}-r${result.revision}-${sha.slice(0,16)}.zip`;
    document.body.appendChild(link); link.click(); link.remove();
  } finally { setTimeout(() => URL.revokeObjectURL(url), 10_000); }
}
