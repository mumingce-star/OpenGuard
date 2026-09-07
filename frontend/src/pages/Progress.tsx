import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
import { restartDemo, skipDemo } from "../services/scans";
import { Header, Panel, StatusBadge, useNotice } from "../components/ui";
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
  const partial = scan.status === "partial";
  const reported = partial && (scan.reportFormats?.length ?? 0) > 0 && scan.stageIndex === scan.stages.length - 1;
  const endedStages = reported ? scan.stages.length : scan.stageIndex;
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
        eyebrow={"TASK / " + scan.id}
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
        caption={scan.mode === "api" ? `后端进度：${scan.progress}%` : "演示阶段进度"}
      >
        <div className="og-progress-summary">
          <strong>
            {endedStages}
            <small> / {scan.stages.length} 个阶段</small>
          </strong>
          <span>{statusLabels[scan.status]}</span>
        </div>
        <progress
          aria-label="扫描阶段进度"
          max={scan.mode === "api" ? 100 : scan.stages.length}
          value={scan.mode === "api" ? scan.progress : scan.stageIndex}
        />
        {scan.mode === "api" && (
          <p className="og-muted" role="status">
            {scan.status === "partial"
              ? (scan.reportFormats?.length ?? 0) > 0
                ? "本次扫描已结束，已有结果和报告可以查看；部分内容未完成，请核对错误说明。无需等待进度达到 100%。"
                : "本次扫描已结束，已有部分结果，但报告尚不可用；请核对错误说明。无需等待进度达到 100%。"
              : active && scan.stageIndex === 0
                ? "正在获取仓库并执行受控扫描工具；该阶段可能持续数分钟，页面每 2.5 秒查询状态。"
                : active && scan.stageIndex === 5
                  ? "正在逐条生成 AI 建议，风险较多时耗时会增加；页面每 2.5 秒查询状态。"
                  : "进度来自后端实际状态。"}
          </p>
        )}
        <ol className="og-stages">
          {scan.stages.map((stage, i) => (
            <li
              key={i}
              className={
                i < endedStages
                  ? "done"
                  : i === scan.stageIndex && active
                    ? "running"
                    : ""
              }
            >
              <span>{i < endedStages ? "✓" : i + 1}</span>
              <div>
                <strong>{stage}</strong>
                <small>
                  {i < endedStages
                    ? reported && i === scan.stages.length - 1 ? "报告已生成" : partial ? "已结束（详见提示）" : "已完成"
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
