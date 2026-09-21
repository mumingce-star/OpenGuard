import { useEffect, useState } from "react";
import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
import { restartDemo, skipDemo, scanPercent } from "../services/scans";
import { Header, Panel, StatusBadge, useNotice } from "../components/ui";
import { useReducedMotion } from "../hooks/useReducedMotion";

const stamp = (value?: string | null) => value ? Date.parse(value) : NaN;
function seconds(scan: Scan, now: number) {
  const started = stamp(scan.startedAt), created = stamp(scan.createdAt), end = stamp(scan.finishedAt);
  const start = Number.isFinite(started) ? started : created;
  return Number.isFinite(start) ? Math.max(0, Math.floor(((Number.isFinite(end) ? end : now) - start) / 1000)) : null;
}
function duration(value: number | null) {
  if (value === null) return "暂不可用";
  const whole = Math.max(0, Math.floor(value)), m = Math.floor(whole / 60), s = whole % 60;
  return m ? `${m}分${s}秒` : `${s}秒`;
}
export function Progress({ scan, reload, onResults, pollingError }: {
  scan: Scan; reload: () => void; onResults: () => void; pollingError?: string | null;
}) {
  const notify = useNotice(), reduced = useReducedMotion();
  const active = ["queued", "running"].includes(scan.status), partial = scan.status === "partial";
  const target = scanPercent(scan);
  const [visual, setVisual] = useState({ id: scan.id, value: target });
  const [now, setNow] = useState(Date.now());
  // A restored or different task starts at its confirmed value, never replays from zero.
  const shown = visual.id === scan.id ? visual.value : target;
  useEffect(() => {
    if (visual.id !== scan.id || reduced || !active) {
      if (visual.id !== scan.id || visual.value !== target) setVisual({ id: scan.id, value: target });
      return;
    }
    if (pollingError) return;
    if (Math.abs(target - shown) < .1) {
      if (shown !== target) setVisual({ id: scan.id, value: target });
      return;
    }
    const id = window.setTimeout(() => setVisual({ id: scan.id, value: shown + (target - shown) * .14 }), 16);
    return () => clearTimeout(id);
  }, [scan.id, visual.id, target, shown, reduced, pollingError, active]);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active, scan.id]);
  const endedStages = partial && (scan.reportFormats?.length ?? 0) > 0 && scan.stageIndex === scan.stages.length - 1 ? scan.stages.length : scan.stageIndex;
  const elapsed = seconds(scan, now), ai = scan.aiProgress;
  const moving = active && !reduced && !pollingError;
  const operation = scan.workProgress?.operation ?? scan.stages[scan.stageIndex] ?? "等待调度";
  function action(fn: () => void) {
    try { fn(); reload(); } catch (e) { notify((e as Error).message, "error"); }
  }
  return <>
    <Header eyebrow={'TASK / ' + scan.id}
      title={scan.status === "completed" ? "扫描已完成" : partial ? "扫描已结束 · 部分结果" : scan.status === "failed" ? "扫描失败" : scan.status === "cancelled" ? "扫描已取消" : scan.status === "queued" ? "任务等待中" : "扫描执行中"}
      description={scan.input} action={<StatusBadge status={scan.status}/>}/>
    <Panel title="扫描进度" caption="按实际完成步骤计算流程进度，不代表许可核验通过率">
      {pollingError && <p className="og-warning" role="alert">状态查询失败，进度已暂停更新：{pollingError}</p>}
      <div className="og-progress-summary">
        <strong className="og-progress-percent">{Math.round(shown)}<small>%</small></strong>
        <span>{endedStages} / {scan.stages.length} 个阶段 · {statusLabels[scan.status]}</span>
      </div>
      <div className={`og-scan-meter${moving ? " is-active" : ""}${scan.status === "failed" ? " is-failed" : ""}`}
        role="progressbar" aria-label="扫描流程进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={target}
        aria-valuetext={`${Math.round(target)}%，${statusLabels[scan.status]}${active ? `，${operation}` : ""}`}>
        <div className="og-scan-meter-fill" style={{ width: `${shown}%` }}/>
        {moving && <span className="og-scan-meter-sweep" aria-hidden="true"/>}
      </div>
      {active && <p className={`og-progress-activity${moving ? " is-active" : ""}`}>
        <span aria-hidden="true"/>{pollingError ? "连接中断，等待重新查询" : `正在处理：${operation}`}
        {!pollingError && <small>光带表示正在执行，百分比随实际完成步骤更新</small>}
      </p>}
      <p className="og-muted" role="status">已用时：{duration(elapsed)}。
        {ai ? <>AI 阶段已用时：{duration(ai.elapsedSeconds)}；情境组 {ai.groupsDone} / {ai.groupsTotal}，实际请求 {ai.requests}，缓存命中 {ai.cacheHits}。
          {ai.etaSeconds ? `当前 AI 阶段预计剩余 ${Math.ceil(ai.etaSeconds[0])}–${Math.ceil(ai.etaSeconds[1])} 秒（估算）；报告等后续阶段未计入。` : "当前 AI 阶段正在估算；暂无可靠的总体剩余时间。"}
        </> : active ? "预计剩余时间：正在估算。" : partial ? "本次扫描已结束，保留部分结果与未覆盖原因。" : "进度来自实际执行结果。"}
      </p>
      <ol className="og-stages">{scan.stages.map((stage, i) => <li key={i} className={i < endedStages ? "done" : i === scan.stageIndex && active ? "running" : ""}>
        <span>{i < endedStages ? "✓" : i + 1}</span><div><strong>{stage}</strong><small>{i < endedStages ? partial ? "已结束（详见诊断）" : "已完成" : i === scan.stageIndex && active ? "等待/执行中" : "未执行"}</small></div>
      </li>)}</ol>
      <div className="og-actions"><button onClick={reload}>重新查询任务</button>
        {scan.mode === "mock" && <><button onClick={() => action(() => restartDemo(scan.id))}>重新开始演示</button>{active && <button onClick={() => action(() => skipDemo(scan.id))}>跳过等待</button>}</>}
        {!active && <button className="og-primary" onClick={onResults}>{scan.status === "completed" ? "查看扫描结果" : "查看已有结果与错误"}</button>}
      </div>
    </Panel>
  </>;
}
