import { useEffect, useState } from "react";
import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
import { restartDemo, skipDemo } from "../services/scans";
import { Header, Panel, StatusBadge, useNotice } from "../components/ui";
import { useReducedMotion } from "../hooks/useReducedMotion";
const stamp = (value?: string | null) => value ? Date.parse(value) : NaN;
function seconds(scan: Scan, now: number) { const start = stamp(scan.startedAt) || stamp(scan.createdAt); const end = stamp(scan.finishedAt); return Number.isFinite(start) ? Math.max(0, Math.floor(((Number.isFinite(end) ? end : now) - start) / 1000)) : null; }
function duration(value: number | null) { if (value === null) return "后端未提供开始时间"; const whole = Math.max(0, Math.floor(value)); const m = Math.floor(whole / 60), s = whole % 60; return m ? `${m}分${s}秒` : `${s}秒`; }
export function Progress({ scan, reload, onResults, pollingError }: { scan: Scan; reload: () => void; onResults: () => void; pollingError?: string | null }) {
 const notify = useNotice(), reduced = useReducedMotion(), active = ["queued", "running"].includes(scan.status), partial = scan.status === "partial";
 const [shown, setShown] = useState(scan.mode === "api" ? scan.progress ?? 0 : scan.stageIndex), [now, setNow] = useState(Date.now());
 const target = scan.mode === "api" ? scan.progress ?? 0 : scan.stageIndex;
 useEffect(() => setShown(target), [scan.id]);
 useEffect(() => { if (reduced || !active) { setShown(target); return; } if (pollingError || Math.abs(target - shown) < .1) { if (Math.abs(target - shown) < .1 && shown !== target) setShown(target); return; } const id = window.setTimeout(() => setShown(shown + (target - shown) * .28), 16); return () => clearTimeout(id); }, [target, shown, reduced, pollingError, active]);
 useEffect(() => { if (!active) return; const id = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, [active]);
 const endedStages = partial && (scan.reportFormats?.length ?? 0) > 0 && scan.stageIndex === scan.stages.length - 1 ? scan.stages.length : scan.stageIndex;
 const elapsed = seconds(scan, now);
 const ai = scan.aiProgress;
 function action(fn: () => void) { try { fn(); reload(); } catch (e) { notify((e as Error).message, "error"); } }
 return <><Header eyebrow={'TASK / ' + scan.id} title={scan.status === "completed" ? "扫描已完成" : partial ? "扫描已结束 · 部分结果" : scan.status === "failed" ? "扫描失败" : scan.status === "cancelled" ? "扫描已取消" : scan.status === "queued" ? "任务等待中" : "扫描执行中"} description={scan.input} action={<StatusBadge status={scan.status}/>}/><Panel title="阶段进度" caption={scan.mode === "api" ? `后端进度：${target}%` : "演示阶段进度"}>{pollingError && <p className="og-warning" role="alert">状态查询失败，已冻结在最后确认的后端进度：{pollingError}</p>}<div className="og-progress-summary"><strong>{endedStages}<small> / {scan.stages.length} 个阶段</small></strong><span>{statusLabels[scan.status]}</span></div><progress className={active && !reduced && !pollingError ? "og-progress-active" : ""} aria-label="扫描阶段进度" max={scan.mode === "api" ? 100 : scan.stages.length} value={shown}/><p className="og-muted" role="status">已用时：{duration(elapsed)}。{ai ? <>AI 阶段已用时：{duration(ai.elapsedSeconds)}；情境组 {ai.groupsDone} / {ai.groupsTotal}，实际请求 {ai.requests}，缓存命中 {ai.cacheHits}。{ai.etaSeconds ? `当前 AI 阶段预计剩余 ${Math.ceil(ai.etaSeconds[0])}–${Math.ceil(ai.etaSeconds[1])} 秒（估算）；报告等后续阶段未计入。` : "当前 AI 阶段正在估算；没有可靠的总体 ETA。"}</> : active ? "正在估算；后端未提供可靠 ETA 时不会虚构倒计时。" : partial ? "本次扫描已结束，保留部分结果与未覆盖原因。" : "进度来自后端实际状态。"}</p><ol className="og-stages">{scan.stages.map((stage, i) => <li key={i} className={i < endedStages ? "done" : i === scan.stageIndex && active ? "running" : ""}><span>{i < endedStages ? "✓" : i + 1}</span><div><strong>{stage}</strong><small>{i < endedStages ? partial ? "已结束（详见诊断）" : "已完成" : i === scan.stageIndex && active ? "等待/执行中" : "未执行"}</small></div></li>)}</ol><div className="og-actions"><button onClick={reload}>重新查询任务</button>{scan.mode === "mock" && <><button onClick={() => action(() => restartDemo(scan.id))}>重新开始演示</button>{active && <button onClick={() => action(() => skipDemo(scan.id))}>跳过等待</button>}</>}{!active && <button className="og-primary" onClick={onResults}>{scan.status === "completed" ? "查看扫描结果" : "查看已有结果与错误"}</button>}</div></Panel></>;
}
