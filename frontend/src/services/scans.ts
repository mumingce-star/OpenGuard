import type { Scan, Mode, Handling, ScanInput } from "../types/domain";
import { createSnapshot, type Scenario } from "../mocks/data";
import { validateGithub, validateZip } from "./model";
export const defaultMode: Mode =
  import.meta.env.VITE_DATA_MODE === "api" ? "api" : "mock";
const base = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
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
    if (!response.ok)
      throw new Error(
        response.status === 404
          ? "任务或接口不存在（404）。请确认任务编号和后端契约。"
          : `接口请求失败（HTTP ${response.status}），请稍后重试。`,
      );
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
export async function getScan(
  id: string,
  mode: Mode,
  signal?: AbortSignal,
): Promise<Scan> {
  return mode === "mock"
    ? demoSnapshot(id)
    : validateSnapshot(
        await request("/scans/" + encodeURIComponent(id), {}, signal),
        "api",
        id,
      );
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
  } else
    await request(
      "/scans/" +
        encodeURIComponent(id) +
        "/risks/" +
        encodeURIComponent(riskId),
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ handling }),
      },
    );
}
export async function validateRepository(
  url: string,
  signal?: AbortSignal,
): Promise<void> {
  const error = validateGithub(url);
  if (error) throw new Error(error);
  const result = await request(
    "/repositories/validate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim() }),
    },
    signal,
  );
  if (!record(result) || result.accessible !== true)
    throw new Error("后端未确认仓库可访问，请检查地址与权限。");
}
export async function createApiScan(
  input: ScanInput,
  requestId: string,
): Promise<Scan> {
  const error =
    input.kind === "github"
      ? validateGithub(input.url ?? "")
      : validateZip(input.file ?? null, zipLimit);
  if (error) throw new Error(error);
  if (input.kind === "zip" && zipLimit === null)
    throw new Error(
      "ZIP 大小上限尚未配置，请与后端确认 VITE_MAX_ZIP_MB 后再上传。",
    );
  let body: BodyInit;
  const headers: Record<string, string> = { "Idempotency-Key": requestId };
  if (input.kind === "zip") {
    const form = new FormData();
    form.append("file", input.file!);
    form.append("scopes", JSON.stringify(input.scopes));
    body = form;
  } else {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({
      kind: input.kind,
      url: input.url?.trim(),
      scopes: input.scopes,
    });
  }
  return validateSnapshot(
    await request("/scans", { method: "POST", headers, body }),
    "api",
  );
}
