import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
import { restartDemo, skipDemo, scanPercent } from "../services/scans";
import { StatusBadge, useNotice } from "../components/ui";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { progressMotionState } from "./progressMotion";
import { nextIntegerProgress, appendObservation, orderedRecords, progressDuration, scanProgressView, scanElapsedSeconds, createStagePlayback, advanceStagePlayback, stagePlaybackView, stageDisplayMilliseconds, type ProgressRecord } from "./progressModel";
import { isNewScanProgressEntry, consumeNewScanProgressEntry } from "../services/scanProgressEntry";
import "./Progress.css";
function RefreshIcon() { return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/></svg>; }
function timeLabel(value: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return "时间未提供";
  return new Date(value).toLocaleTimeString("zh-CN", { hour12: false });
}
export function Progress({ scan, reload, onResults, pollingError }: {
  scan: Scan; reload: () => void; onResults: () => void; pollingError?: string | null;
}) {
  const notify = useNotice(), reduced = useReducedMotion();
  const [entry, setEntry] = useState(() => ({ id: scan.id, mode: scan.mode, fresh: isNewScanProgressEntry(scan) }));
  const newlySubmitted = entry.id === scan.id && entry.mode === scan.mode ? entry.fresh : isNewScanProgressEntry(scan);
  useEffect(() => {
    if (entry.id !== scan.id || entry.mode !== scan.mode) setEntry({ id: scan.id, mode: scan.mode, fresh: newlySubmitted });
    consumeNewScanProgressEntry(scan);
  }, [scan.id, scan.mode, entry.id, entry.mode, newlySubmitted]);
  const [playback, setPlayback] = useState(() => createStagePlayback(scan, Date.now(), newlySubmitted));
  const presentation = stagePlaybackView(scan, reduced ? { ...playback, enabled: false } : playback);
  const { stages, ended, currentNumber, replaying } = presentation;
  const motion = progressMotionState(replaying ? "running" : scan.status, !!pollingError, reduced);
  useEffect(() => {
    if (reduced) {
      if (playback.enabled) setPlayback({ ...playback, enabled: false });
      return;
    }
    const next = advanceStagePlayback(playback, scan, Date.now(), !!pollingError, newlySubmitted);
    if (next !== playback) { setPlayback(next); return; }
    if (!playback.enabled || pollingError || !playback.started) return;
    const actual = scanProgressView(scan).stages;
    const nextStarted = scan.progressEvents?.events.some(e => e.phase === actual[playback.cursor + 1]?.key && e.state === "start");
    if (actual[playback.cursor]?.state !== "done" || (!nextStarted && playback.cursor < actual.length - 1)) return;
    const timer = window.setTimeout(() => setPlayback(p => advanceStagePlayback(p, scan, Date.now(), false, newlySubmitted)), Math.max(0, stageDisplayMilliseconds - (Date.now() - playback.enteredAt)));
    return () => window.clearTimeout(timer);
  }, [scan, playback, pollingError, reduced, newlySubmitted]);
  const [queryFeedback, setQueryFeedback] = useState(false);
  const queryTimer = useRef<number | null>(null);
  useEffect(() => () => {
    if (queryTimer.current !== null) window.clearTimeout(queryTimer.current);
  }, []);
  function queryTask() {
    if (queryTimer.current !== null) window.clearTimeout(queryTimer.current);
    if (!reduced) {
      setQueryFeedback(true);
      queryTimer.current = window.setTimeout(() => { setQueryFeedback(false); queryTimer.current = null; }, 600);
    }
    reload();
  }
  const active = ["queued", "running"].includes(scan.status), partial = scan.status === "partial";
  const target = scanPercent(scan);
  const displayTarget = Math.min(target, presentation.ceiling);
  const startAtZero = !reduced && (active || newlySubmitted);
  const [visual, setVisual] = useState({ id: scan.id, value: startAtZero ? 0 : target });
  const [now, setNow] = useState(Date.now());
  const [observations, setObservations] = useState<{ id: string; rows: ProgressRecord[] }>({ id: scan.id, rows: [] });
  const shown = visual.id === scan.id ? visual.value : startAtZero ? 0 : target;
  useEffect(() => {
    if (visual.id !== scan.id) { setVisual({ id: scan.id, value: startAtZero ? 0 : target }); return; }
    if (pollingError) return;
    if (reduced || (!active && scan.status !== "completed")) {
      if (shown !== target) setVisual({ id: scan.id, value: target });
      return;
    }
    if (shown >= displayTarget) return;
    const id = window.setTimeout(() => setVisual({ id: scan.id, value: nextIntegerProgress(shown, displayTarget) }), 30);
    return () => clearTimeout(id);
  }, [scan.id, visual.id, target, displayTarget, shown, reduced, pollingError, active, scan.status, startAtZero]);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active, scan.id]);
  useEffect(() => {
    if (pollingError || !active) return;
    setObservations(prev => ({ id: scan.id, rows: appendObservation(prev.id === scan.id ? prev.rows : [], scan, new Date().toISOString()) }));
  }, [scan.id, scan.status, scan.stageIndex, scan.progress, scan.workProgress?.percent, scan.workProgress?.operation, scan.aiProgress?.groupsDone, scan.aiProgress?.requests, pollingError, active]);
  const elapsed = scanElapsedSeconds(scan, now);
  const operation = scan.progressEvents?.events.length ? stages.find(stage => stage.state === "running")?.title ?? "正在保存并读取结果" : scan.stageIndex === 5 ? "后台任务处理中" : scan.workProgress?.operation ?? stages.find(stage => stage.sourceIndex === scan.stageIndex)?.title ?? "等待调度";
  const title = scan.status === "completed" ? "扫描已完成" : partial ? "扫描已结束 · 部分结果" : scan.status === "failed" ? "扫描失败" : scan.status === "cancelled" ? "扫描已取消" : scan.status === "queued" ? "任务等待中" : "扫描执行中";
  const rows = orderedRecords(scan, observations.id === scan.id ? observations.rows : []);
  function action(fn: () => void) {
    try { fn(); reload(); } catch (e) { notify((e as Error).message, "error"); }
  }
  return <div className={`og-progress-page status-${scan.status}${pollingError ? " is-disconnected" : ""}`} data-motion={motion} data-presentation={replaying ? "replay" : "live"}>
    <header className="og-progress-heading">
      <div><div className="og-progress-task"><span>任务 / {scan.id}</span><StatusBadge status={scan.status}/></div>
        <h1>{title}</h1><p className="og-progress-source">{scan.input}</p></div>
      <button className={`og-progress-refresh${queryFeedback && !reduced ? " is-querying" : ""}`} onClick={queryTask}><RefreshIcon/>重新查询任务</button>
    </header>
    {pollingError && <p className="og-progress-warning" role="alert">状态查询失败，进度已暂停更新：{pollingError}。可重新查询任务。</p>}
    {replaying && <p className="og-progress-replay" role="status">{scan.status === "completed" ? "扫描已完成，正在展示处理过程" : "按真实记录逐步展示，后台扫描继续执行"}。高亮表示正在展示的步骤，实际状态和时间以下方记录为准。</p>}
    <section className="og-progress-console" aria-label="扫描执行进度">
      <div className="og-progress-overview">
        <div className="og-progress-gauge" role="progressbar" aria-label="扫描流程进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(shown)} data-confirmed-progress={target} aria-valuetext={`${Math.round(shown)}%，后台已确认 ${target}%，${statusLabels[scan.status]}`}>
          <svg viewBox="0 0 112 112" aria-hidden="true"><circle className="og-gauge-track" cx="56" cy="56" r="47"/><circle className="og-gauge-value" cx="56" cy="56" r="47" pathLength="100" strokeDasharray={`${shown} 100`} transform="rotate(-90 56 56)"/></svg>
          <strong>{Math.round(shown)}<small>%</small></strong>
        </div>
        <div className="og-progress-main-label"><h2>扫描进度 <span>{ended} / {stages.length} 个阶段{replaying ? "已展示" : "已结束"}</span></h2><p>{replaying ? "正按记录顺序展示已完成的步骤，可随时查看结果。" : "按实际完成步骤计算流程进度，不代表许可核验通过率。"}</p></div>
        <div className="og-progress-current" role="status"><strong>{pollingError ? "连接中断 · 等待重新查询" : replaying ? `过程展示：${operation}` : scan.status === "queued" ? "等待调度：尚未开始扫描" : active ? `正在处理：${operation}` : partial ? "已保留部分结果与诊断" : scan.status === "completed" ? "结果已保存，可查看报告" : "任务已停止，查看下方原因"}</strong>
          <p>{scan.status === "queued" ? "已等待" : "已用时"}：{progressDuration(elapsed)}{active ? " · 预计剩余时间：正在估算" : " · " + statusLabels[scan.status]}</p></div>
      </div>
      <div className="og-progress-pipeline-header"><h3><span className="og-progress-dot"/>执行流水线全景 <small>{stages.length} 个阶段 · 从输入到报告</small></h3><span className={`og-progress-phase ${(active || replaying) && !pollingError ? "is-running" : ""}`}>{pollingError ? "连接已暂停" : replaying ? `阶段 ${currentNumber} · 过程展示` : scan.status === "running" ? currentNumber ? `阶段 ${currentNumber} 正在执行` : "后台任务处理中" : statusLabels[scan.status]}</span></div>
      <div className="og-progress-pipeline-scroll" tabIndex={0} aria-label="扫描阶段，可横向滚动"><ol className="og-progress-pipeline">{stages.map((stage, i) => <li key={stage.key} className={`og-progress-stage ${stage.state}`} style={{ "--stage-order": i } as CSSProperties} aria-current={stage.state === "running" ? "step" : undefined}>
        <span className="og-stage-marker" aria-hidden="true">{stage.state === "done" ? "✓" : stage.state === "skipped" ? "−" : stage.state === "running" ? <span className="og-stage-spinner"/> : stage.state === "partial" || stage.state === "failed" ? "!" : i + 1}</span>
        <h4>{stage.title}</h4><p className="og-stage-description">{stage.description}</p><strong className="og-stage-state">{pollingError && stage.state === "running" ? "状态更新已暂停" : stage.stateText}</strong><span className="og-stage-detail">{stage.badge}</span>
      </li>)}</ol></div>
      <section className="og-progress-records" aria-label="任务状态记录"><header><h3><span className="og-console-icon" aria-hidden="true">›_</span>任务状态记录</h3><span>{active && !pollingError ? "随接口状态更新" : "读取已保存的任务记录"}</span></header>
        <div className="og-progress-log"><ul>{rows.length ? rows.map((row, i) => <li key={`${row.key}-${i}`} className={`tone-${row.tone}`}><time dateTime={row.time ?? undefined}>[{timeLabel(row.time)}]</time><span className="og-log-tag">[{row.tag}]</span><span>{row.text}</span></li>) : <li className="og-progress-log-empty">等待任务状态；接口未提供的时间与日志不会补造。</li>}</ul></div>
        <p className="og-progress-log-source">来自任务接口的时间、状态、真实阶段记录和诊断；“本页观察”仅记录本页收到的变化，并非扫描工具的原始 stdout。</p>
      </section>
      <footer className="og-progress-footer"><p>{active ? "可以离开此页，稍后通过同一任务继续查看进度。" : partial ? "部分完成不等于完整扫描；结果与未覆盖原因会一并保留。" : scan.status === "completed" ? "扫描完成表示流程结束，许可证适用性仍以具体证据和评估为准。" : "已保存的记录保持可查，重新查询不会重新提交扫描。"}</p>
        <div className="og-progress-actions">{scan.mode === "mock" && <><button onClick={() => action(() => restartDemo(scan.id))}>重新开始演示</button>{active && <button onClick={() => action(() => skipDemo(scan.id))}>跳过等待</button>}</>}{!active && <button className="og-primary" onClick={onResults}>{scan.status === "completed" ? "查看扫描结果" : "查看已有结果与错误"}</button>}</div>
      </footer>
    </section>
  </div>;
}
