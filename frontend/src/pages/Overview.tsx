import type { Scan } from "../types/domain";
import { resourceTypes, handlingLabels, severityLabels } from "../types/domain";
import { summarize, severityOrder } from "../services/model";
import { Panel, SeverityBadge, Empty } from "../components/ui";

const severityColors = {
  critical: "#fa7188", high: "#ff974d", medium: "#f6c65c",
  low: "#6eaeff", info: "#9eafc8",
};
const resourceColors = ["#6edcec", "#39a8ef", "#5184f5", "#8c9cff", "#b6c6fa", "#a781f5"];
const metricIcons = [
  "M20 6c0 2-3.6 3-8 3S4 8 4 6s3.6-3 8-3 8 1 8 3ZM4 6v12c0 2 3.6 3 8 3s8-1 8-3V6M4 12c0 2 3.6 3 8 3s8-1 8-3",
  "m12 3 10 18H2L12 3Zm0 6v5m0 3v.1",
  "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 4v5l4 2",
  "M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h5",
];

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
    ["全部风险", s.risks, scan.mode === "api" ? "后端规则提示" : "含人工标记已处理", "risks", ""],
    ["待处理风险", s.pending, scan.mode === "api" ? "待人工核验" : "待处理 + 复核中", "risks", "handling=pending"],
    ["许可待确认", s.unknown, "未知或待人工复核", "resources", "unknown=1"],
  ] as const;
  const severities = severityOrder.map((severity) => ({
    severity,
    count: scan.risks.filter((r) => r.severity === severity).length,
  }));
  const resources = resourceTypes.map((type) => ({
    type,
    count: scan.resources.filter((r) => r.type === type).length,
  }));
  const finishedLabel = scan.finishedAt
    ? new Date(scan.finishedAt).toLocaleString()
    : (["queued", "running"].includes(scan.status) ? "尚未完成扫描" : "完成时间未提供");
  return (
    <div className="og-overview">
      <section className="og-overview-summary" aria-labelledby="overview-title">
        <header className="og-overview-heading">
          <div>
            <h1 id="overview-title">扫描概览</h1>
            <div className="og-overview-identity">
              <strong>{scan.project}</strong>
              <span>{scan.id}</span>
              <span>{finishedLabel}</span>
            </div>
          </div>
          <button className="og-overview-progress" onClick={() => go("progress")}>查看扫描阶段 <span aria-hidden="true">→</span></button>
        </header>
        <div className="og-overview-metrics">
          {metrics.map(([label, n, detail, page, q], i) => (
            <button className="og-overview-metric" onClick={() => go(page, q)} key={label}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={metricIcons[i]} /></svg>
              <span className="og-overview-metric-copy">
                <span>{label}</span>
                <strong>{n.toString().padStart(2, "0")}</strong>
                <small>{detail}</small>
              </span>
              <span className="og-overview-arrow" aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
      </section>

      <div className="og-overview-grid">
        <div className="og-overview-priority">
          <Panel
            title="优先查看风险"
            caption="先看证据，再判断；不是自动法律结论"
            action={<button className="og-overview-all" onClick={() => go("risks")}>全部风险 <span aria-hidden="true">→</span></button>}
          >
            {scan.risks.length === 0 ? (
              <Empty
                title={scan.resources.length ? "本次未发现风险提示" : "本次没有资源结果"}
                detail="未发现不代表已完成全部许可核验，请结合扫描状态与覆盖边界确认。"
              />
            ) : (
              <div className="og-overview-risk-list">
                {[...scan.risks]
                  .sort((a, b) => severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity))
                  .slice(0, 3)
                  .map((r) => (
                    <button className="og-overview-risk" key={r.id} onClick={() => go("risks", "", r.id)}>
                      <SeverityBadge value={r.severity} />
                      <span className="og-overview-risk-copy">
                        <strong>{r.title}</strong>
                        <small>{r.id} · {scan.resources.find((x) => x.id === r.resourceId)?.name ?? "资源待补充"}</small>
                      </span>
                      <span className={"og-overview-handling " + r.handling}>{handlingLabels[r.handling]} <span aria-hidden="true">→</span></span>
                    </button>
                  ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="og-overview-statistics">
          <Panel title="风险严重度" caption="全部风险 · 人工处理状态不会改变严重度">
            <div className="og-overview-severity-bar" aria-hidden="true">
              {severities.filter(({ count }) => count > 0).map(({ severity, count }) => (
                <span key={severity} style={{ width: (count / s.risks) * 100 + "%", backgroundColor: severityColors[severity] }}>
                  {count / s.risks >= 0.12 ? Math.round((count / s.risks) * 100) + "%" : ""}
                </span>
              ))}
            </div>
            <div className="og-overview-legend">
              {severities.map(({ severity, count }) => (
                <button key={severity} onClick={() => go("risks", "severity=" + severity)}>
                  <i aria-hidden="true" style={{ backgroundColor: severityColors[severity] }} />
                  <span>{severityLabels[severity]}</span><b>{count}</b>
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="资源构成" caption={"共 " + s.resources + " 项 · 与资源列表/报告一致"}>
            <div className="og-overview-resource-chart">
              <div className="og-overview-donut" aria-hidden="true">
                <svg viewBox="0 0 120 120">
                  <circle className="og-overview-donut-track" cx="60" cy="60" r="47" fill="none" strokeWidth="19" />
                  {resources.map(({ type, count }, i) => {
                    const share = s.resources ? (count / s.resources) * 100 : 0;
                    const offset = s.resources ? resources.slice(0, i).reduce((sum, item) => sum + item.count, 0) / s.resources * 100 : 0;
                    return count > 0 ? <circle key={type} cx="60" cy="60" r="47" fill="none" stroke={resourceColors[i]} strokeWidth="19" pathLength="100" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-offset} transform="rotate(-90 60 60)" /> : null;
                  })}
                </svg>
                <div><strong>{s.resources}</strong><span>项资源</span></div>
              </div>
              <div className="og-overview-legend">
                {resources.map(({ type, count }, i) => (
                  <button key={type} onClick={() => go("resources", "type=" + type)}>
                    <i aria-hidden="true" style={{ backgroundColor: resourceColors[i] }} />
                    <span>{type}</span><b>{count}</b>
                  </button>
                ))}
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
