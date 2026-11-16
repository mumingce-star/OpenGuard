import { ApiError, request } from './scans';
import type { NoticeRef } from './noticeDrafts';
import { listAssessments, validateAssessment, type Assessment } from './assessments';
import { accountRequestOptions, handleAccountResponse } from './auth';

type Row = Record<string, unknown>;
const row = (value: unknown): value is Row => !!value && typeof value === 'object' && !Array.isArray(value);
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.length > 0;
const rows = (value: unknown): value is Row[] => Array.isArray(value) && value.every(row);

export async function loadReportAssessmentChoices(scanId: string, requestedId: string, signal?: AbortSignal) {
  const listed = await listAssessments(scanId, signal);
  const items = listed.items.filter(item => item.formal === true && !!item.facts_hash);
  if (!requestedId) return { items, selectedId: items[0]?.id ?? '' };
  // The list is paginated. A pinned older version must be read by its exact ID,
  // never silently replaced by the first (latest) item in that list.
  const exact: Assessment = validateAssessment(await request(
    `/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(requestedId)}`,
    { method: 'GET' }, signal,
  ), scanId);
  if (exact.id !== requestedId || exact.formal !== true || !exact.facts_hash)
    throw new Error('所选正式评估身份不一致，已停止创建报告；不会改用最新评估。');
  return { items: [exact, ...items.filter(item => item.id !== exact.id)], selectedId: exact.id };
}

export function reportNavigationQuery(currentScanId: string, targetScanId: string, current: URLSearchParams) {
  const next = new URLSearchParams();
  if (!currentScanId || currentScanId !== targetScanId) return next;
  const assessment = current.get('assessment_id');
  if (!assessment) return next;
  next.set('assessment_id', assessment);
  const assessmentVersion = current.get('assessment_version');
  if (assessmentVersion && /^[1-9]\d*$/.test(assessmentVersion)) next.set('assessment_version', assessmentVersion);
  const snapshot = current.get('snapshot_id');
  if (snapshot) next.set('snapshot_id', snapshot);
  const result = current.get('p2_result');
  if (result) next.set('p2_result', result);
  return next;
}

// Navigation context only. These query values do not prove that a P2 Result is
// part of an Assessment report: the Workbench re-reads its exact bound objects.
export function reportP2ContextUrl(scanId: string, current: URLSearchParams): string | null {
  const assessment = current.get('assessment_id'), result = current.get('p2_result');
  const safeId = (value: string | null) => !!value && /^[A-Za-z0-9_-]{1,160}$/.test(value);
  if (!safeId(scanId) || !safeId(assessment) || !safeId(result)) return null;
  const params = new URLSearchParams({ mode: 'api', assessment_id: assessment!, p2_result: result! });
  const version = current.get('assessment_version');
  if (version !== null) {
    if (!/^[1-9]\d*$/.test(version)) return null;
    params.set('assessment_version', version);
  }
  return `/app/scans/${encodeURIComponent(scanId)}/assessment?${params}`;
}

export function reportSnapshotQuery(currentScanId: string, targetScanId: string, current: URLSearchParams, assessmentId: string, snapshotId: string) {
  const next = current.get('assessment_id') === assessmentId
    ? reportNavigationQuery(currentScanId, targetScanId, current) : new URLSearchParams();
  if (assessmentId) next.set('assessment_id', assessmentId); else next.delete('assessment_id');
  if (snapshotId) next.set('snapshot_id', snapshotId); else next.delete('snapshot_id');
  return next;
}

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
  binding: {
    scan_ref: { scan_id: string; status: string; revision: string | null };
    assessment_ref: { assessment_id: string; version: number };
    notice_refs: NoticeRef[];
    algorithm_refs?: { kind: string; version: string; content_hash: string }[];
  };
  created_at: string;
  generator_version: string;
  sections: ReportSection[];
  provenance: Row;
};

export type ReportObservationGroups = {
  graph: ReportSection[];
  notice: ReportSection[];
};

export function classifyReportObservations(document: ReportDocument): ReportObservationGroups {
  const graphRefs = (document.binding.algorithm_refs ?? []).filter(ref => ref.kind === 'graph');
  const noticeRefs = new Map(document.binding.notice_refs.map(ref => [ref.draft_id, ref.content_hash]));
  const groups: ReportObservationGroups = { graph: [], notice: [] };
  for (const section of document.sections) {
    if (section.authority !== 'observation' || !row(section.content)) continue;
    const content = section.content;
    const provenance = row(content.provenance) ? content.provenance : null;
    if (nonempty(content.view_id) && section.source_ids.includes(content.view_id) && provenance &&
        nonempty(provenance.algorithm_version) && graphRefs.some(ref => ref.version === provenance.algorithm_version)) {
      groups.graph.push(section);
      continue;
    }
    if (nonempty(content.draft_id) && section.source_ids.includes(content.draft_id) &&
        nonempty(content.content_hash) && noticeRefs.get(content.draft_id) === content.content_hash) {
      groups.notice.push(section);
    }
  }
  return groups;
}

export function reportCreateControl(input: {
  assessmentId: string;
  createLoading: boolean;
  creating: boolean;
  loadError: string;
  createError: string;
}) {
  return {
    disabled: !input.assessmentId || input.createLoading || input.creating || !!input.loadError,
    label: input.creating ? '正在由后端保存…' : input.createError ? '重试创建（沿用同一请求标识）' : '创建并打开固定报告',
  };
}

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
  try {
    const raw = await request(
      `/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/report-v2`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idempotency_key: idempotencyKey, task_refs: taskRefs, notice_refs: noticeRefs, algorithm_refs: [] }),
      },
    );
    return validateReportSnapshot(raw, scanId, assessmentId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && error.reason === 'notice_draft_not_found')
      throw new ApiError(error.status, '引用的 NOTICE 草稿不存在；请核对固定的 draft_id 与当前扫描、评估，不会自动生成替代草稿。', error.code, error.reason);
    throw error;
  }
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
  if ('algorithm_refs' in value.binding && (!Array.isArray(value.binding.algorithm_refs) ||
      !value.binding.algorithm_refs.every(ref => row(ref) && nonempty(ref.kind) && nonempty(ref.version) &&
        nonempty(ref.content_hash) && /^[a-f0-9]{64}$/.test(ref.content_hash)))) return invalid();
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
  try { response = await fetch(url, accountRequestOptions({ method: 'GET', signal, headers: { Accept: format === 'json' ? 'application/json' : 'text/html' } })); }
  catch (error) { if (signal?.aborted) throw error; throw new Error('无法读取后端固定报告，请检查连接后重试。'); }
  handleAccountResponse(response.status);
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

// Validate the saved artifact before creating any browser download. These are
// transport integrity checks, not a new source or license acceptance decision.
const MAX_REPORT_DOWNLOAD_BYTES = 32 * 1024 * 1024;
async function verifiedDownloadBytes(response: Response): Promise<Uint8Array<ArrayBuffer>> {
  const invalid = () => new Error('报告附件完整性校验失败，未保存；原归档保持不变。');
  const digestHeader = response.headers.get('Content-Digest');
  const etag = response.headers.get('ETag');
  if (response.status !== 200 || !/^sha-256=:[A-Za-z0-9+/]{43}=:$/.test(digestHeader ?? '') ||
      !/^"sha256:[a-f0-9]{64}"$/.test(etag ?? '')) throw invalid();
  const declared = response.headers.get('Content-Length');
  if (declared !== null && (!/^[1-9]\d*$/.test(declared) || Number(declared) > MAX_REPORT_DOWNLOAD_BYTES))
    throw new Error('报告附件为空或超过下载大小上限，未保存。');
  if (!response.body) throw invalid();
  const reader = response.body.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_REPORT_DOWNLOAD_BYTES) throw new Error('报告附件超过下载大小上限，未保存。');
      chunks.push(value);
    }
    if (!size || (declared !== null && Number(declared) !== size)) throw invalid();
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hex = Array.from(hash, x => x.toString(16).padStart(2, '0')).join('');
  const base64 = btoa(Array.from(hash, x => String.fromCharCode(x)).join(''));
  if (etag !== `"sha256:${hex}"` || digestHeader !== `sha-256=:${base64}:`) throw invalid();
  return bytes;
}

export async function downloadReportV2(scanId: string, assessmentId: string, snapshotId: string, format: 'json' | 'html') {
  const response = await artifact(reportV2Url(scanId, assessmentId, snapshotId, format), format);
  const bytes = await verifiedDownloadBytes(response);
  let text: string;
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes); }
  catch { throw new Error('报告附件文字编码无效，未保存。'); }
  if (format === 'json') {
    let parsed: unknown;
    try { parsed = JSON.parse(text); }
    catch { throw new Error('报告 JSON 附件无法解析，未保存。'); }
    validateReportDocument(parsed, scanId, assessmentId, snapshotId);
  } else if (!/^\s*<!doctype html>/i.test(text) || !/<meta\s+name="openguard-html-renderer"\s+content="[^"]+"\s*\/?\s*>/i.test(text)) {
    throw new Error('后端 HTML 报告内容无效，未保存。');
  }
  const blob = new Blob([bytes], { type: format === 'json' ? 'application/json' : 'text/html;charset=utf-8' });
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


// Local navigation hints only: never a server report list or proof that a report
// still exists. Every selection is reopened through the exact bound GET above.
export type ReportReference = {
  scanId: string;
  assessmentId: string;
  assessmentVersion: number;
  snapshotId: string;
  createdAt: string;
};
function reportReferenceKey(scanId: string, assessmentId: string) {
  return `openguard.report-references.v1:${JSON.stringify([
    (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, ''), scanId, assessmentId,
  ])}`;
}
export function readReportReferences(scanId: string, assessmentId: string): ReportReference[] {
  if (!scanId || !assessmentId) return [];
  try {
    const raw = localStorage.getItem(reportReferenceKey(scanId, assessmentId));
    if (!raw || raw.length > 32_000) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length > 10) return [];
    const valid = parsed.every(ref => row(ref) && ref.scanId === scanId && ref.assessmentId === assessmentId &&
      typeof ref.snapshotId === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(ref.snapshotId) &&
      Number.isInteger(ref.assessmentVersion) && Number(ref.assessmentVersion) > 0 &&
      typeof ref.createdAt === 'string' && Number.isFinite(Date.parse(ref.createdAt)));
    if (!valid || new Set(parsed.map(ref => ref.snapshotId)).size !== parsed.length) return [];
    return parsed as ReportReference[];
  } catch { return []; }
}
export function rememberReportReference(document: ReportDocument): boolean {
  try {
    const { scan_id: scanId } = document.binding.scan_ref;
    const { assessment_id: assessmentId, version: assessmentVersion } = document.binding.assessment_ref;
    validateReportDocument(document, scanId, assessmentId, document.snapshot_id);
    if (!/^[A-Za-z0-9_-]{1,160}$/.test(document.snapshot_id) || assessmentVersion < 1) return false;
    const reference: ReportReference = { scanId, assessmentId, assessmentVersion,
      snapshotId: document.snapshot_id, createdAt: document.created_at };
    const previous = readReportReferences(scanId, assessmentId).filter(ref => ref.snapshotId !== reference.snapshotId);
    localStorage.setItem(reportReferenceKey(scanId, assessmentId), JSON.stringify([reference, ...previous].slice(0, 10)));
    return true;
  } catch { return false; }
}
