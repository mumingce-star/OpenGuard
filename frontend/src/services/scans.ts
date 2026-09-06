import type { Scan, Mode, Handling, ScanInput, ReportFormat, ResourceType } from "../types/domain";
import { createSnapshot, type Scenario } from "../mocks/data";
import { validateGithub, validateZip } from "./model";
export const defaultMode: Mode =
  import.meta.env.VITE_DATA_MODE === "mock" ? "mock" : "api";
const base = (
  import.meta.env.VITE_API_BASE_URL || "/api/v1"
).replace(/\/$/, "");
const mb = Number(import.meta.env.VITE_MAX_ZIP_MB);
export const zipLimit = Number.isFinite(mb) && mb > 0 ? mb * 1024 * 1024 : null;
const key = (id: string) => "openguard:scan:v2:" + id;
function record(x: unknown): x is Record<string, unknown> {
  return !!x && typeof x === "object" && !Array.isArray(x);
}
function text(x: unknown): x is string {
  return typeof x === "string";
}
function nullable(x: unknown) {
  return x === null || text(x);
}
function strings(x: unknown): x is string[] {
  return Array.isArray(x) && x.every(text);
}
function one(x: unknown, options: string[]) {
  return text(x) && options.includes(x);
}
function unique(items: Record<string, unknown>[]) {
  return (
    items.every((x) => text(x.id) && x.id.length > 0) &&
    new Set(items.map((x) => x.id)).size === items.length
  );
}
export function validateSnapshot(raw: unknown, mode: Mode, id?: string): Scan {
  const fail = () => {
    throw new Error(
      "任务数据结构不符合前端契约，请检查编号、状态、关联数据及全量快照标记。",
    );
  };
  if (!record(raw)) return fail();
  if (
    !text(raw.id) ||
    !raw.id ||
    (id && raw.id !== id) ||
    raw.mode !== mode ||
    raw.completeness !== "full" ||
    !text(raw.snapshotVersion) ||
    !text(raw.project) ||
    !text(raw.input) ||
    !text(raw.createdAt) ||
    !Number.isFinite(Date.parse(raw.createdAt)) ||
    !nullable(raw.finishedAt) ||
    (text(raw.finishedAt) && !Number.isFinite(Date.parse(raw.finishedAt))) ||
    !nullable(raw.error) ||
    !one(raw.status, ["queued", "running", "completed", "failed", "partial"]) ||
    !strings(raw.stages) ||
    !raw.stages.length ||
    !Number.isInteger(raw.stageIndex) ||
    Number(raw.stageIndex) < 0 ||
    Number(raw.stageIndex) > raw.stages.length ||
    !Array.isArray(raw.resources) ||
    !Array.isArray(raw.risks) ||
    !Array.isArray(raw.evidence)
  )
    return fail();
  if (raw.status === "completed" && raw.stageIndex !== raw.stages.length)
    return fail();
  if (
    !raw.resources.every(record) ||
    !raw.risks.every(record) ||
    !raw.evidence.every(record)
  )
    return fail();
  const resources = raw.resources as Record<string, unknown>[],
    risks = raw.risks as Record<string, unknown>[],
    evidence = raw.evidence as Record<string, unknown>[];
  if (!unique(resources) || !unique(risks) || !unique(evidence)) return fail();
  for (const r of resources)
    if (
      !text(r.name) ||
      !one(r.type, [
        "Package",
        "Model",
        "Dataset",
        "API",
        "Service",
        "Asset",
      ]) ||
      !nullable(r.version) ||
      !nullable(r.origin) ||
      !nullable(r.license) ||
      !one(r.licenseStatus, ["confirmed", "review_required", "unknown"]) ||
      !strings(r.evidenceIds)
    )
      return fail();
  for (const r of risks)
    if (
      !text(r.title) ||
      !text(r.resourceId) ||
      !resources.some((x) => x.id === r.resourceId) ||
      !one(r.severity, ["critical", "high", "medium", "low"]) ||
      !one(r.handling, ["open", "reviewing", "resolved"]) ||
      !one(r.verification, ["unverified", "passed", "failed"]) ||
      !nullable(r.fact) ||
      !nullable(r.conclusion) ||
      !nullable(r.remediation) ||
      !strings(r.evidenceIds) ||
      !record(r.ai) ||
      !one(r.ai.status, ["ready", "failed", "unavailable"]) ||
      !nullable(r.ai.text)
    )
      return fail();
  for (const e of evidence)
    if (
      !one(e.kind, ["code", "license", "rule"]) ||
      !text(e.label) ||
      !text(e.source) ||
      !nullable(e.text) ||
      (e.path !== undefined && !text(e.path)) ||
      (e.url !== undefined && !text(e.url)) ||
      (e.startLine !== undefined &&
        (!Number.isInteger(e.startLine) || Number(e.startLine) < 1)) ||
      (e.highlightLines !== undefined &&
        (!Array.isArray(e.highlightLines) ||
          !e.highlightLines.every((n) => Number.isInteger(n) && n > 0)))
    )
      return fail();
  // Missing evidence references intentionally remain visible as "待补充".
  return raw as unknown as Scan;
}
class ApiError extends Error { constructor(public status: number, message: string, public code?: string, public reason?: string) { super(message); } }
async function request(
  path: string,
  options: RequestInit = {},
  signal?: AbortSignal,
): Promise<unknown> {
  const timeout = new AbortController();
  const timer = window.setTimeout(() => timeout.abort(), 15000);
  const stop = () => timeout.abort();
  signal?.addEventListener("abort", stop, { once: true });
  try {
    if (signal?.aborted) timeout.abort();
    const response = await fetch(base + path, {
      ...options,
      signal: timeout.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.error;
      throw new ApiError(response.status, `接口请求失败（HTTP ${response.status}）` + (detail?.message ? `：${detail.message} (${detail.code})` : "，请检查后端或任务编号。"), detail?.code, detail?.details?.reason);
    }
    return response.status === 204 ? null : await response.json();
  } catch (e) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (e instanceof Error && e.name === "AbortError")
      throw new Error("请求超时，请检查后端服务后重试。");
    if (e instanceof TypeError)
      throw new Error(
        "无法连接后端，请检查网络、API 地址与 CORS。不会自动切换演示。",
      );
    throw e;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", stop);
  }
}
type Stored = { scan: Scan; scenario: Scenario; start: number; skip: boolean };
function readStored(id: string): Stored {
  let raw: unknown;
  try {
    raw = JSON.parse(localStorage.getItem(key(id)) ?? "null");
  } catch {
    throw new Error("演示快照无法读取，请主动重新载入演示。");
  }
  if (
    !record(raw) ||
    !record(raw.scan) ||
    !text(raw.scenario) ||
    !["standard", "clean", "empty", "missing", "partial", "failed"].includes(
      raw.scenario,
    ) ||
    typeof raw.start !== "number" ||
    !Number.isFinite(raw.start) ||
    typeof raw.skip !== "boolean"
  )
    throw new Error("未找到该演示任务，可能已清除本地数据。请重新载入演示。");
  return { ...raw, scan: validateSnapshot(raw.scan, "mock", id) } as Stored;
}
function save(s: Stored) {
  try {
    localStorage.setItem(key(s.scan.id), JSON.stringify(s));
  } catch {
    throw new Error("浏览器无法保存演示快照，请允许本地存储或释放空间后重试。");
  }
}
export function createDemo(scenario: Scenario = "standard"): Scan {
  const id = "DEMO-" + crypto.randomUUID().slice(0, 8);
  const scan = createSnapshot(id, scenario);
  save({ scan, scenario, start: Date.now(), skip: false });
  return { ...scan, resources: [], risks: [], evidence: [] };
}
function demoSnapshot(id: string): Scan {
  const stored = readStored(id),
    { scan, scenario } = stored;
  const steps = stored.skip
    ? scan.stages.length
    : Math.max(0, Math.floor((Date.now() - stored.start) / 1200));
  const terminal = steps >= scan.stages.length;
  const failed = scenario === "failed" && steps >= 2;
  return {
    ...scan,
    status: failed
      ? "failed"
      : terminal
        ? scenario === "partial"
          ? "partial"
          : "completed"
        : steps === 0
          ? "queued"
          : "running",
    stageIndex: failed
      ? 2
      : terminal && scenario === "partial"
        ? 5
        : Math.min(steps, scan.stages.length),
    finishedAt:
      terminal || failed
        ? new Date(stored.start + (failed ? 2400 : 8400)).toISOString()
        : null,
    resources: terminal && !failed ? scan.resources : [],
    risks: terminal && !failed ? scan.risks : [],
    evidence: terminal && !failed ? scan.evidence : [],
    error: failed || (terminal && scenario === "partial") ? scan.error : null,
  };
}
const stages = ["安全读取", "文件清单", "依赖扫描", "标准化", "规则判断", "AI 辅助", "报告"];
const stageKeys = ["ingestion", "inventory", "scan", "normalize", "rules", "ai_assist", "report"];
const formats: ReportFormat[] = ["html", "json", "csv", "resource_inventory"];
function object(value: unknown): Record<string, any> {
  if (!record(value)) throw new Error("后端数据不符合冻结 API 契约。");
  return value;
}
function list(value: unknown): Record<string, any>[] {
  if (!Array.isArray(value) || !value.every(record)) throw new Error("后端列表不符合冻结 API 契约。");
  return value;
}
function collection(value: unknown) {
  const dto = object(value), items = list(dto.items);
  if (dto.total !== items.length) throw new Error("后端列表不完整，不能展示为完整结果。");
  return items;
}
function scanRoute(id: string) { return "/scans/" + encodeURIComponent(id); }
export function reportDownloadUrl(id: string, format: ReportFormat) {
  if (!formats.includes(format)) throw new Error("未知报告格式。");
  return base + scanRoute(id) + "/report?format=" + format + "&download=true";
}
export function adaptApiScan(id: string, statusRaw: unknown, resourceRaw: unknown, riskRaw: unknown, evidenceRaw: unknown[], runRaw: unknown = null, available: ReportFormat[] = []): Scan {
  const state = object(statusRaw);
  if (state.scan_id !== id || !one(state.status, ["queued", "running", "completed", "partial", "failed", "cancelled"]) || !Number.isInteger(state.progress) || state.progress < 0 || state.progress > 100 || !["queued", "completed", ...stageKeys].includes(state.stage)) throw new Error("后端状态不符合冻结 API 契约。");
  const run = runRaw === null ? null : object(runRaw);
  if (run && (run.id !== id || run.status !== state.status)) throw new Error("报告与当前任务不一致。");
  const licenses = run ? list(run.licenses) : [];
  const remediations = run ? list(run.remediations) : [];
  const resources: Scan["resources"] = collection(resourceRaw).map(w => {
    const r = object(w.resource), lic = licenses.find(l => l.id === r.license_expression_id);
    if (!text(r.id) || !text(r.name) || !strings(r.evidence_ids) || !["component", "ai_asset"].includes(w.kind)) throw new Error("后端资源不符合冻结 API 契约。");
    const types: Record<string, ResourceType> = { model: "Model", dataset: "Dataset", api: "API", service: "Service", asset: "Asset" };
    const type = w.kind === "component" ? "Package" : types[r.asset_type];
    if (!type) throw new Error("未知资源类型。");
    return { id: r.id, name: r.name, type, version: r.version ?? null, origin: r.source_url ?? r.purl ?? null,
      license: lic?.expression ?? null, licenseStatus: lic?.verification_status === "verified" ? "confirmed" : lic ? "review_required" : "unknown", evidenceIds: r.evidence_ids };
  });
  const risks: Scan["risks"] = collection(riskRaw).map(r => {
    if (!text(r.id) || !text(r.title) || !resources.some(x => x.id === r.resource_id) || !one(r.severity, ["info", "low", "medium", "high"]) || !one(r.outcome, ["pass", "warning", "review_required", "unknown"]) || !strings(r.evidence_ids)) throw new Error("后端风险不符合冻结 API 契约。");
    const rem = remediations.find(x => x.id === r.remediation_id && x.finding_id === r.id);
    const advice = rem ? [rem.summary, ...rem.steps].join("\n") : null;
    const ai = rem?.generated_by?.type === "ai";
    return { id: r.id, resourceId: r.resource_id, title: r.title, severity: r.severity, outcome: r.outcome,
      handling: "open", verification: "unverified", fact: r.trigger, conclusion: r.description,
      remediation: advice, ai: { status: ai ? "ready" : "unavailable", text: ai ? advice : null }, evidenceIds: r.evidence_ids };
  });
  const evidence: Scan["evidence"] = evidenceRaw.map(raw => {
    const e = object(raw);
    if (!text(e.id) || !text(e.locator) || !text(e.detected_by)) throw new Error("后端证据不符合冻结 API 契约。");
    return { id: e.id, kind: e.kind === "license_text" ? "license" : "code", label: e.locator, source: e.detected_by,
      ...(e.kind === "url" ? { url: e.locator } : { path: e.locator }),
      ...(e.start_line ? { startLine: e.start_line } : {}), text: e.excerpt ?? null };
  });
  const errors = list(state.errors);
  return { id, mode: "api", project: run?.project?.name ?? "扫描任务", input: run?.project?.source ?? "未提供",
    createdAt: run?.created_at ?? null, finishedAt: run?.finished_at ?? null,
    status: state.status, stages, stageIndex: state.stage === "completed" ? stages.length : Math.max(0, stageKeys.indexOf(state.stage)), progress: state.progress,
    error: errors.length ? errors.map(e => `${e.code}: ${e.message}`).join("；") : null,
    resources, risks, evidence, resultsReady: ["completed", "partial"].includes(state.status), completeness: "full", snapshotVersion: run?.contract_version ?? "P0 API", reportFormats: available };
}
export async function getScan(id: string, mode: Mode, signal?: AbortSignal): Promise<Scan> {
  if (mode === "mock") return demoSnapshot(id);
  const path = scanRoute(id), status = object(await request(path, {}, signal));
  if (!["completed", "partial"].includes(status.status)) {
    return adaptApiScan(id, status, { items: [], total: 0 }, { items: [], total: 0 }, []);
  }
  const [resources, risks] = await Promise.all([request(path + "/resources", {}, signal), request(path + "/risks", {}, signal)]);
  const resourceItems = collection(resources), riskItems = collection(risks);
  let run: unknown = null;
  const available: ReportFormat[] = [];
  if (["completed", "partial"].includes(status.status)) {
    for (const format of formats) {
      try { const meta = object(await request(path + "/report?format=" + format, {}, signal));
        if (meta.format !== format) throw new Error("报告格式不一致。");
        available.push(format);
      } catch (error) { if (!(error instanceof ApiError && error.status === 409 && error.code === "report_not_ready" && error.reason === "not_generated")) throw error; }
    }
    if (available.includes("json")) run = object(await request(path + "/report?format=json&download=true", {}, signal)).scan_run;
  }
  const ids = [...new Set<string>([
    ...resourceItems.flatMap(w => object(w.resource).evidence_ids ?? []), ...riskItems.flatMap(r => r.evidence_ids ?? []),
    ...(run ? list(object(run).evidence).map(e => e.id) : [])
  ])];
  const evidence = [];
  // Bound concurrency and use the frozen evidence endpoint for actual excerpts.
  for (let i = 0; i < ids.length; i += 8) evidence.push(...await Promise.all(ids.slice(i, i + 8).map(e => request(path + "/evidence/" + encodeURIComponent(e), {}, signal))));
  return adaptApiScan(id, status, resources, risks, evidence, run, available);
}
export function skipDemo(id: string) {
  const s = readStored(id);
  s.skip = true;
  save(s);
}
export function restartDemo(id: string) {
  const s = readStored(id);
  save({
    scan: createSnapshot(id, s.scenario),
    scenario: s.scenario,
    start: Date.now(),
    skip: false,
  });
}
export async function updateHandling(
  id: string,
  riskId: string,
  handling: Handling,
  mode: Mode,
): Promise<void> {
  if (mode === "mock") {
    const s = readStored(id);
    const r = s.scan.risks.find((r) => r.id === riskId);
    if (!r) throw new Error("风险编号不存在。");
    r.handling = handling;
    save(s);
  } else throw new Error("当前真实扫描结果只读，未提供处理状态修改接口。");
}
export async function createApiScan(input: ScanInput, requestId: string): Promise<Pick<Scan, "id" | "mode">> {
  const error = input.kind === "github" ? validateGithub(input.url ?? "") : validateZip(input.file ?? null, zipLimit);
  if (error) throw new Error(error);
  let body: BodyInit;
  const headers: Record<string, string> = {};
  if (input.kind === "zip") {
    const form = new FormData();
    form.append("source_type", "zip");
    form.append("idempotency_key", requestId);
    form.append("file", input.file!);
    body = form;
  } else {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({ source_type: "git", source: input.url?.trim(), idempotency_key: requestId });
  }
  const accepted = object(await request("/scans", { method: "POST", headers, body }));
  if (!text(accepted.scan_id) || !accepted.scan_id || !one(accepted.status, ["queued", "running", "completed", "partial", "failed", "cancelled"]) || accepted.status_url !== "/api/v1/scans/" + accepted.scan_id) throw new Error("创建响应不符合冻结 API 契约。");
  return { id: accepted.scan_id, mode: "api" };
}
