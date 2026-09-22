import { ApiError, request } from './scans';
import type { NoticeRef } from './noticeDrafts';

type Row = Record<string, unknown>;
const row = (value: unknown): value is Row => !!value && typeof value === 'object' && !Array.isArray(value);
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const rows = (value: unknown): value is Row[] => Array.isArray(value) && value.every(row);

export type ReportSection = {
  authority: 'scan_facts' | 'formal_assessment' | 'workflow' | 'observation' | 'ai_explanation';
  schema_version: string;
  source_ids: string[];
  content_hash: string;
  content: unknown;
};
export type ReportDocument = {
  schema_version: '1.0';
  snapshot_id: string;
  binding: { scan_ref: { scan_id: string; status: string; revision: string | null }; assessment_ref: { assessment_id: string; version: number }; notice_refs: NoticeRef[] };
  created_at: string;
  generator_version: string;
  sections: ReportSection[];
  provenance: Row;
};

export type ReportSnapshot = {
  schema_version: '1.0';
  snapshot_id: string;
  binding: {
    scan_ref: { scan_id: string };
    assessment_ref: { assessment_id: string; version: number };
    task_refs: { task_id: string; version: number }[];
    notice_refs: NoticeRef[];
    algorithm_refs: unknown[];
  };
  artifacts: { format: 'json' | 'html'; content_hash: string; size_bytes: number; href: string }[];
  content_hash: string;
};

export function validateReportSnapshot(value: unknown, scanId: string, assessmentId: string): ReportSnapshot {
  const invalid = () => { throw new Error('Report V2 创建响应不符合接口契约，未作为正式快照打开。'); };
  if (!row(value) || value.schema_version !== '1.0' || !nonempty(value.snapshot_id) ||
      !row(value.binding) || !row(value.binding.scan_ref) || !row(value.binding.assessment_ref) ||
      value.binding.scan_ref.scan_id !== scanId || value.binding.assessment_ref.assessment_id !== assessmentId ||
      !Number.isInteger(value.binding.assessment_ref.version) || !Array.isArray(value.binding.task_refs) ||
      !Array.isArray(value.binding.notice_refs) || !Array.isArray(value.binding.algorithm_refs) ||
      !Array.isArray(value.artifacts) || !nonempty(value.content_hash) || !/^[a-f0-9]{64}$/.test(value.content_hash)) return invalid();
  if (!value.binding.task_refs.every(ref => row(ref) && nonempty(ref.task_id) && Number.isInteger(ref.version) && Number(ref.version) >= 1)) return invalid();
  if (!value.binding.notice_refs.every(ref => row(ref) && nonempty(ref.draft_id) && nonempty(ref.content_hash) && /^[a-f0-9]{64}$/.test(ref.content_hash))) return invalid();
  const artifacts = value.artifacts;
  if (artifacts.length !== 2 || new Set(artifacts.map(item => row(item) ? item.format : '')).size !== 2 ||
      !artifacts.every(item => row(item) && ['json', 'html'].includes(String(item.format)) &&
        nonempty(item.content_hash) && /^[a-f0-9]{64}$/.test(item.content_hash) &&
        Number.isInteger(item.size_bytes) && Number(item.size_bytes) > 0 && nonempty(item.href) &&
        item.href.startsWith(`/api/v1/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/report-v2/`))) return invalid();
  return value as ReportSnapshot;
}

export async function createReportV2(
  scanId: string,
  assessmentId: string,
  idempotencyKey: string,
  taskRefs: { task_id: string; version: number }[],
  noticeRefs: NoticeRef[] = [],
): Promise<ReportSnapshot> {
  if (!idempotencyKey.trim() || new Set(taskRefs.map(ref => ref.task_id)).size !== taskRefs.length ||
      taskRefs.some(ref => !ref.task_id || !Number.isInteger(ref.version) || ref.version < 1) ||
      new Set(noticeRefs.map(ref => ref.draft_id)).size !== noticeRefs.length ||
      noticeRefs.some(ref => !ref.draft_id || !/^[a-f0-9]{64}$/.test(ref.content_hash)))
    throw new Error('Report V2 创建参数无效。');
  const raw = await request(
    `/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/report-v2`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idempotency_key: idempotencyKey, task_refs: taskRefs, notice_refs: noticeRefs, algorithm_refs: [] }),
    },
  );
  return validateReportSnapshot(raw, scanId, assessmentId);
}

export function reportV2Url(scanId: string, assessmentId: string, snapshotId: string, format: 'json' | 'html') {
  const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
  return `${base}/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/report-v2/${encodeURIComponent(snapshotId)}?format=${format}`;
}

export function validateReportDocument(value: unknown, scanId: string, assessmentId: string, snapshotId: string): ReportDocument {
  const invalid = () => { throw new Error('Report V2 快照不符合接口契约，未展示为正式报告。'); };
  if (!row(value) || value.schema_version !== '1.0' || value.snapshot_id !== snapshotId ||
      !row(value.binding) || !row(value.binding.scan_ref) || !row(value.binding.assessment_ref) ||
      value.binding.scan_ref.scan_id !== scanId || value.binding.assessment_ref.assessment_id !== assessmentId ||
      !nonempty(value.binding.scan_ref.status) || !(value.binding.scan_ref.revision === null || nonempty(value.binding.scan_ref.revision)) ||
      !Number.isInteger(value.binding.assessment_ref.version) ||
      !Array.isArray(value.binding.notice_refs) || !nonempty(value.created_at) || !Number.isFinite(Date.parse(value.created_at)) ||
      !nonempty(value.generator_version) || !rows(value.sections) || !row(value.provenance)) return invalid();
  const allowed = new Set(['scan_facts', 'formal_assessment', 'workflow', 'observation', 'ai_explanation']);
  if (!value.binding.notice_refs.every(ref => row(ref) && nonempty(ref.draft_id) && nonempty(ref.content_hash) && /^[a-f0-9]{64}$/.test(ref.content_hash))) return invalid();
  const sections = value.sections;
  if (!sections.every(section => allowed.has(String(section.authority)) && nonempty(section.schema_version) &&
      Array.isArray(section.source_ids) && section.source_ids.every(nonempty) &&
      typeof section.content_hash === 'string' && /^[a-f0-9]{64}$/.test(section.content_hash) && 'content' in section)) return invalid();
  for (const authority of ['scan_facts', 'formal_assessment', 'workflow', 'ai_explanation']) {
    if (sections.filter(section => section.authority === authority).length !== 1) return invalid();
  }
  const formal = sections.find(section => section.authority === 'formal_assessment')?.content;
  if (!row(formal) || formal.formal !== true || formal.id !== assessmentId || formal.scan_id !== scanId) return invalid();
  return value as ReportDocument;
}

async function artifact(url: string, format: 'json' | 'html', signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try { response = await fetch(url, { method: 'GET', signal, headers: { Accept: format === 'json' ? 'application/json' : 'text/html' } }); }
  catch (error) { if (signal?.aborted) throw error; throw new Error('无法读取后端固定报告，请检查连接后重试。'); }
  if (!response.ok) {
    const details = await response.json().catch(() => null);
    const reason = details?.error?.details?.reason;
    throw new ApiError(response.status, response.status === 404 ? '固定报告不存在，或当前后端尚未发布该快照。' : `固定报告下载失败（HTTP ${response.status}）。`, details?.error?.code, reason);
  }
  const contentType = response.headers.get('Content-Type') || '';
  if (!contentType.toLowerCase().includes(format === 'json' ? 'application/json' : 'text/html')) throw new Error('后端返回的报告格式不符合请求，已停止展示。');
  return response;
}

export async function loadReportV2(scanId: string, assessmentId: string, snapshotId: string, signal?: AbortSignal) {
  const json = await artifact(reportV2Url(scanId, assessmentId, snapshotId, 'json'), 'json', signal);
  const document = validateReportDocument(await json.json(), scanId, assessmentId, snapshotId);
  const html = await artifact(reportV2Url(scanId, assessmentId, snapshotId, 'html'), 'html', signal);
  const htmlText = await html.text();
  if (!/^\s*<!doctype html>/i.test(htmlText) || !htmlText.includes('openguard-html-renderer')) throw new Error('后端 HTML 报告内容无效，已停止展示。');
  return { document, html: htmlText };
}

export async function downloadReportV2(scanId: string, assessmentId: string, snapshotId: string, format: 'json' | 'html') {
  const response = await artifact(reportV2Url(scanId, assessmentId, snapshotId, format), format);
  const blob = await response.blob();
  if (!blob.size) throw new Error('下载附件为空，未保存。');
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `openguard-${snapshotId}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally { setTimeout(() => URL.revokeObjectURL(objectUrl), 1000); }
}
