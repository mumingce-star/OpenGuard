import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
export type StageState = "done" | "running" | "waiting" | "skipped" | "partial" | "failed" | "cancelled";
const keys = ["ingestion", "inventory", "scan", "normalize", "rules", "ai_assist", "report"];
const titles = ["安全获取项目", "建立文件清单", "识别第三方资源", "许可证标准化", "规则检查", "AI 辅助解释", "生成报告"];
const descriptions = ["校验输入并安全读取", "记录文件与内容摘要", "盘点依赖和资源引用", "整理已发现的许可声明", "按证据检查许可条件", "按任务配置提供辅助解释", "保存可追溯的结果"];
export function endedStageCount(scan: Scan): number {
  if (scan.status === "completed") return scan.stages.length;
  if (scan.status === "queued") return 0;
  if (scan.status === "partial" && (scan.reportFormats?.length ?? 0) > 0 && scan.stageIndex === scan.stages.length - 1) return scan.stages.length;
  return Math.max(0, Math.min(scan.stages.length, scan.stageIndex));
}
export function progressStages(scan: Scan) {
  const ended = endedStageCount(scan);
  return scan.stages.map((label, i) => {
    const disabled = i === 5 && label.includes("未启用");
    const diagnostic = scan.diagnostics?.find(d => d.stage === keys[i] || (i === 4 && d.code === "rules_stage_not_connected"));
    let state: StageState = i < ended ? "done" : "waiting";
    if (disabled) state = i < ended ? "skipped" : "waiting";
    else if (scan.status === "partial" && diagnostic) state = "partial";
    else if (i === scan.stageIndex && scan.status === "running") state = "running";
    else if (i === scan.stageIndex && scan.status === "failed") state = "failed";
    else if (i === scan.stageIndex && scan.status === "cancelled") state = "cancelled";
    else if (i === scan.stageIndex && scan.status === "partial" && ended < scan.stages.length) state = "partial";
    const stateText = state === "done" ? (scan.status === "completed" ? "已完成" : "已结束") : state === "running" ? "正在执行" : state === "skipped" ? "已跳过 · 未调用模型" : state === "partial" ? "部分结果 · 查看诊断" : state === "failed" ? "执行失败" : state === "cancelled" ? "已取消" : "等待调度";
    const badges = ["输入校验", "SHA-256", scan.resources.length ? `${scan.resources.length} 个资源` : "依赖与引用", "许可归一", "确定性规则", disabled ? "本次未启用" : scan.aiProgress ? `${scan.aiProgress.requests} 次请求` : "按配置执行", scan.reportFormats?.length ? `${scan.reportFormats.length} 种格式` : "结果归档"];
    return { key: keys[i] ?? String(i), sourceIndex: i, title: titles[i] ?? label, description: descriptions[i] ?? label, state, stateText, badge: badges[i] ?? "任务阶段", diagnostic };
  });
}
export function scanProgressView(scan: Scan) {
  let stages = progressStages(scan).filter(stage => stage.key !== "ai_assist");
  const recorded = scan.progressEvents?.events ?? [];
  if (recorded.length) {
    stages = stages.map(stage => {
      const events = recorded.filter(event => event.phase === stage.key);
      const last = events.at(-1);
      const ended = events.some(event => event.state === "end");
      const state: StageState = last?.state === "failed" ? "failed" : last?.state === "partial" ? "partial" : last?.state === "cancelled" ? "cancelled" : ended ? "done" : last?.state === "start" ? (scan.status === "failed" ? "failed" : scan.status === "cancelled" ? "cancelled" : scan.status === "partial" ? "partial" : "running") : "waiting";
      return { ...stage, state, stateText: state === "done" ? "已完成" : state === "running" ? "正在执行" : state === "failed" ? "执行失败" : state === "partial" ? "部分结果 · 查看诊断" : state === "cancelled" ? "已取消" : "等待调度" };
    });
    const index = stages.findIndex(stage => stage.state === "running");
    return { stages, ended: stages.filter(stage => stage.state === "done").length, currentNumber: index<0 ? null : index+1 };
  }
  const boundary = endedStageCount(scan);
  const index = stages.findIndex(stage => stage.sourceIndex === scan.stageIndex);
  return { stages, ended: stages.filter(stage => stage.sourceIndex < boundary).length, currentNumber: index < 0 || scan.status === "queued" ? null : index + 1 };
}
export interface StagePlayback {
  scanId: string; enabled: boolean; cursor: number; enteredAt: number; started: boolean;
}
export const stageDisplayMilliseconds = 800;
export function createStagePlayback(scan: Scan, now: number, newlySubmitted = false): StagePlayback {
  return { scanId: scan.id, enabled: newlySubmitted || ["queued", "running"].includes(scan.status), cursor: 0, enteredAt: now, started: false };
}
// Only present recorded starts/endings. This clock never advances backend work.
export function advanceStagePlayback(p: StagePlayback, scan: Scan, now: number, paused: boolean, newlySubmitted = false): StagePlayback {
  if (p.scanId !== scan.id) return createStagePlayback(scan, now, newlySubmitted);
  if (!p.enabled || paused) return p;
  if (!["queued", "running", "completed"].includes(scan.status)) return { ...p, enabled: false };
  const { stages } = scanProgressView(scan);
  const events = scan.progressEvents?.events ?? [];
  const started = (index: number) => events.some(e => e.phase === stages[index]?.key && e.state === "start");
  if (!started(p.cursor)) return p;
  if (!p.started) return { ...p, started: true, enteredAt: now };
  if (stages[p.cursor]?.state !== "done" || now - p.enteredAt < stageDisplayMilliseconds) return p;
  if (p.cursor === stages.length - 1) return { ...p, enabled: false };
  if (!started(p.cursor + 1)) return p;
  return { ...p, cursor: p.cursor + 1, enteredAt: now };
}
export function stagePlaybackView(scan: Scan, p: StagePlayback) {
  const actual = scanProgressView(scan);
  const events = scan.progressEvents?.events ?? [];
  if (!p.enabled || p.scanId !== scan.id || !events.length || !["queued", "running", "completed"].includes(scan.status)) {
    return { ...actual, replaying: false, presenting: false, ceiling: 100 };
  }
  const current = actual.stages[p.cursor];
  const started = events.some(e => e.phase === current?.key && e.state === "start");
  const replaying = started && (current.state === "done" || actual.stages.slice(p.cursor + 1).some(s => s.state !== "waiting"));
  const stages = actual.stages.map((stage, i) => i < p.cursor ? stage : i === p.cursor && started ? {
    ...stage, state: "running" as StageState, stateText: stage.state === "done" ? "已完成 · 过程展示" : stage.stateText,
  } : { ...stage, state: "waiting" as StageState, stateText: stage.state === "waiting" ? "等待调度" : "等待展示" });
  const displayedPhases = new Set(actual.stages.slice(0, p.cursor + 1).map(s => s.key));
  const ceiling = replaying ? Math.min(99, Math.max(0, ...events.filter(e => displayedPhases.has(e.phase)).map(e => e.percent))) : 100;
  return { stages, ended: p.cursor, currentNumber: started ? p.cursor + 1 : null, replaying, presenting: started, ceiling };
}
export function nextIntegerProgress(current: number, target: number) {
  const bounded = Math.max(0, Math.min(100, Math.floor(target)));
  return current < bounded ? Math.min(bounded, Math.floor(current)+1) : bounded;
}
export function scanElapsedSeconds(scan: Scan, now: number): number | null {
  const parse = (v?: string | null) => v ? Date.parse(v) : NaN;
  const started = parse(scan.startedAt), created = parse(scan.createdAt), end = parse(scan.finishedAt);
  const start = Number.isFinite(started) ? started : created;
  return Number.isFinite(start) ? Math.max(0, Math.floor(((Number.isFinite(end) ? end : now) - start) / 1000)) : null;
}
export function progressDuration(value: number | null) {
  if (value === null) return "暂不可用";
  const s = Math.max(0, Math.floor(value));
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`;
}
export interface ProgressRecord { key: string; time: string | null; tag: string; text: string; tone: "info" | "success" | "warning" | "error"; }
export function snapshotRecords(scan: Scan): ProgressRecord[] {
  const rows: ProgressRecord[] = [];
  if (scan.createdAt) rows.push({ key: "created", time: scan.createdAt, tag: "任务", text: "已创建扫描任务，保留固定任务身份。", tone: "info" });
  if (scan.startedAt) rows.push({ key: "started", time: scan.startedAt, tag: "开始", text: "任务开始执行，按实际步骤更新进度。", tone: "info" });
  if (scan.finishedAt) rows.push({ key: "finished", time: scan.finishedAt, tag: "结束", text: `${statusLabels[scan.status]}${scan.resources.length ? `，已保存 ${scan.resources.length} 个资源、${scan.evidence.length} 条证据` : ""}。`, tone: scan.status === "completed" ? "success" : scan.status === "failed" ? "error" : "warning" });
  scan.diagnostics?.forEach((d, i) => rows.push({ key: `diagnostic-${i}`, time: null, tag: "诊断", text: `${d.code}：${d.message}`, tone: "warning" }));
  return rows;
}
export function observationKey(scan: Scan) {
  return JSON.stringify([scan.id, scan.status, scan.stageIndex, scan.progress, scan.workProgress, scan.aiProgress]);
}
export function appendObservation(rows: ProgressRecord[], scan: Scan, at: string): ProgressRecord[] {
  const key = observationKey(scan);
  if (rows.at(-1)?.key === key) return rows;
  const operation = scan.workProgress?.operation ?? scan.stages[scan.stageIndex];
  const percent = Math.max(scan.progress ?? 0, scan.workProgress?.percent ?? 0);
  const text = `${statusLabels[scan.status]}${scan.status === "running" && operation ? ` · ${operation}` : ""}${typeof scan.progress === "number" ? ` · 接口进度 ${percent}%` : ""}`;
  return [...rows.slice(-39), { key, time: at, tag: "本页观察", text, tone: "info" as const }];
}
export function orderedRecords(scan: Scan, observations: ProgressRecord[]) {
  const at = (v: string | null) => v && Number.isFinite(Date.parse(v)) ? Date.parse(v) : Infinity;
  const phases = scan.progressEvents?.events.filter(e=>e.phase!=="ai_assist").map(e=>({ key:`stage-${e.sequence}`, time:e.observed_at, tag:"阶段记录", text:`${titles[keys.indexOf(e.phase)]} · ${e.state === "start" ? "开始" : e.state === "end" ? "结束" : statusLabels[e.state as keyof typeof statusLabels]} · 接口进度 ${e.percent}%`, tone:e.state === "failed" ? "error" as const : e.state === "end" || e.state === "completed" ? "success" as const : "info" as const })) ?? [];
  return [...snapshotRecords(scan), ...phases, ...observations].sort((a, b) => at(a.time) - at(b.time));
}
