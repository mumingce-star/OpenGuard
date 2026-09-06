import { useEffect, useRef, useState } from "react";
import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
import { restartDemo, skipDemo } from "../services/scans";
import { Header, Panel, StatusBadge, useNotice } from "../components/ui";
import { useReducedMotion } from "../hooks/useReducedMotion";

function progressTarget(scan: Scan) {
  const fallback = Math.round((scan.stageIndex / Math.max(1, scan.stages.length)) * 100);
  const value = typeof scan.progress === "number" && Number.isFinite(scan.progress)
    ? scan.progress
    : fallback;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function useAnimatedProgress(scanId: string, target: number, reducedMotion: boolean) {
  const [displayed, setDisplayed] = useState(0);
  const current = useRef(0);
  const currentScan = useRef(scanId);

  useEffect(() => {
    let start = current.current;
    if (currentScan.current !== scanId) {
      currentScan.current = scanId;
      current.current = 0;
      start = 0;
      setDisplayed(0);
    }
    const nextTarget = Math.max(start, target);
    if (reducedMotion || nextTarget === start) {
      current.current = nextTarget;
      setDisplayed(nextTarget);
      return;
    }

    const duration = Math.min(1200, Math.max(360, (nextTarget - start) * 18));
    const startedAt = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const elapsed = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - Math.pow(1 - elapsed, 3);
      const value = Math.min(nextTarget, Math.round(start + (nextTarget - start) * eased));
      if (value !== current.current) {
        current.current = value;
        setDisplayed(value);
      }
      if (elapsed < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [reducedMotion, scanId, target]);

  return displayed;
}

export function Progress({
  scan,
  reload,
  onResults,
}: {
  scan: Scan;
  reload: () => void;
  onResults: () => void;
}) {
  const notify = useNotice();
  const completed = scan.status === "completed";
  const active = ["queued", "running"].includes(scan.status);
  const reducedMotion = useReducedMotion();
  const target = progressTarget(scan);
  const displayedProgress = useAnimatedProgress(scan.id, target, reducedMotion);
  const runningStage = active ? scan.stages[scan.stageIndex] : null;
  const aiRunning = runningStage === "AI 辅助";
  function action(fn: () => void) {
    try {
      fn();
      reload();
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  return (
    <>
      <Header
        eyebrow={"任务 / " + scan.id}
        title={
          completed
            ? "扫描已完成"
            : scan.status === "partial"
              ? "扫描部分完成"
              : scan.status === "cancelled"
                ? "扫描已取消"
                : scan.status === "failed"
                ? "扫描失败"
                : scan.status === "queued"
                  ? "任务等待中"
                  : "扫描执行中"
        }
        description={scan.input}
        action={<StatusBadge status={scan.status} />}
      />
      <Panel
        title="阶段进度"
        caption={scan.mode === "api" ? `后端实际进度：${target}%` : "演示阶段进度"}
      >
        <div className="og-progress-summary">
          <strong>
            {displayedProgress}
            <small>%</small>
          </strong>
          <span>
            {scan.stageIndex} / {scan.stages.length} 个阶段已完成 · {statusLabels[scan.status]}
          </span>
        </div>
        <div
          className="og-progress-track"
          role="progressbar"
          aria-label="扫描总体进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={displayedProgress}
          aria-valuetext={`${displayedProgress}%`}
        >
          <span
            className={`og-progress-fill${active ? " active" : ""}`}
            style={{ width: `${displayedProgress}%` }}
          />
        </div>
        {runningStage && (
          <p className={`og-progress-live${aiRunning ? " ai" : ""}`} role="status" aria-live="polite">
            <span aria-hidden="true" />
            {aiRunning
              ? "Qwen3 正在逐条生成待复核建议；风险越多，等待时间越长。页面每 2.5 秒读取真实状态。"
              : `正在执行“${runningStage}”；页面每 2.5 秒读取真实状态。`}
          </p>
        )}
        <ol className="og-stages">
          {scan.stages.map((stage, i) => (
            <li
              key={i}
              className={
                i < scan.stageIndex
                  ? "done"
                  : i === scan.stageIndex && active
                    ? "running"
                    : ""
              }
            >
              <span>{i < scan.stageIndex ? "✓" : i + 1}</span>
              <div>
                <strong>{stage}</strong>
                <small>
                  {i < scan.stageIndex
                    ? "已完成"
                    : i === scan.stageIndex
                      ? active
                        ? "等待/执行中"
                        : scan.status === "failed"
                          ? "失败"
                          : "待确认"
                      : "未执行"}
                </small>
              </div>
            </li>
          ))}
        </ol>
        <div className="og-actions">
          <button onClick={reload}>重新查询任务</button>
          {scan.mode === "mock" && (
            <>
              <button onClick={() => action(() => restartDemo(scan.id))}>
                重新开始演示
              </button>
              {active && (
                <button onClick={() => action(() => skipDemo(scan.id))}>
                  跳过等待
                </button>
              )}
            </>
          )}
          {!active && (
            <button className="og-primary" onClick={onResults}>
              {completed ? "查看扫描结果" : "查看已有结果与错误"}
            </button>
          )}
        </div>
        <p className="og-muted">
          任务编号用于刷新恢复，不会因刷新而重新创建任务。当前未开放取消接口。
        </p>
      </Panel>
    </>
  );
}
