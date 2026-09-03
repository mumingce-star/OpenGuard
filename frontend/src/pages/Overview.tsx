import type { Scan } from "../types/domain";
import { resourceTypes, handlingLabels } from "../types/domain";
import { summarize, severityOrder } from "../services/model";
import { Header, Panel, SeverityBadge, Empty } from "../components/ui";
export function Overview({
  scan,
  go,
}: {
  scan: Scan;
  go: (page: string, query?: string, riskId?: string) => void;
}) {
  const s = summarize(scan);
  const metrics = [
    ["发现资源", s.resources, "全量快照中的资源", "resources", ""],
    ["全部风险", s.risks, "含人工标记已处理", "risks", ""],
    ["待处理风险", s.pending, "待处理 + 复核中", "risks", "handling=pending"],
    ["许可待确认", s.unknown, "未知或待人工复核", "resources", "unknown=1"],
  ] as const;
  return (
    <>
      <Header
        title="扫描概览"
        eyebrow={"SCAN / " + scan.id}
        description={
          scan.project +
          " · " +
          (scan.finishedAt
            ? new Date(scan.finishedAt).toLocaleString()
            : "尚未完成扫描")
        }
        action={<button onClick={() => go("progress")}>查看扫描阶段 →</button>}
      />
      <div className="og-metrics">
        {metrics.map(([label, n, detail, page, q], i) => (
          <button
            className={"og-metric tone-" + i}
            onClick={() => go(page, q)}
            key={label}
          >
            <span>
              {label}
              <i>↗</i>
            </span>
            <strong>{n.toString().padStart(2, "0")}</strong>
            <small>{detail}</small>
          </button>
        ))}
      </div>
      <div className="og-columns">
        <Panel
          title="风险严重度"
          caption="全部风险 · 人工处理状态不会改变严重度"
        >
          {severityOrder.map((severity) => {
            const n = scan.risks.filter((r) => r.severity === severity).length;
            return (
              <button
                className="og-bar-row"
                key={severity}
                onClick={() => go("risks", "severity=" + severity)}
              >
                <SeverityBadge value={severity} />
                <span className="og-bar">
                  <i
                    style={{ width: (s.risks ? (n / s.risks) * 100 : 0) + "%" }}
                  />
                </span>
                <b>{n}</b>
              </button>
            );
          })}
        </Panel>
        <Panel
          title="资源构成"
          caption={"共 " + s.resources + " 项 · 与资源列表/报告一致"}
        >
          {resourceTypes.map((type) => {
            const n = scan.resources.filter((r) => r.type === type).length;
            return (
              <button
                key={type}
                className="og-bar-row"
                onClick={() => go("resources", "type=" + type)}
              >
                <span>{type}</span>
                <span className="og-bar">
                  <i
                    style={{
                      width: (s.resources ? (n / s.resources) * 100 : 0) + "%",
                    }}
                  />
                </span>
                <b>{n}</b>
              </button>
            );
          })}
        </Panel>
      </div>
      <Panel
        title="优先查看风险"
        caption="先看证据，再判断；不是自动法律结论"
        action={<button onClick={() => go("risks")}>全部风险 →</button>}
      >
        {scan.risks.length === 0 ? (
          <Empty
            title={
              scan.resources.length ? "本次未发现风险提示" : "本次没有资源结果"
            }
            detail="未发现不代表已完成全部许可核验，请结合扫描状态与覆盖边界确认。"
          />
        ) : (
          [...scan.risks]
            .sort(
              (a, b) =>
                severityOrder.indexOf(a.severity) -
                severityOrder.indexOf(b.severity),
            )
            .slice(0, 3)
            .map((r) => (
              <button
                className="og-risk-preview"
                key={r.id}
                onClick={() => go("risks", "", r.id)}
              >
                <SeverityBadge value={r.severity} />
                <div>
                  <strong>{r.title}</strong>
                  <small>
                    {r.id} ·{" "}
                    {scan.resources.find((x) => x.id === r.resourceId)?.name ??
                      "资源待补充"}
                  </small>
                </div>
                <span>{handlingLabels[r.handling]} →</span>
              </button>
            ))
        )}
      </Panel>
    </>
  );
}
