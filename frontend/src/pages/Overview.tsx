import type { Scan } from "../types/domain";
import { resourceTypes, handlingLabels } from "../types/domain";
import { summarize, severityOrder } from "../services/model";
import { Panel, SeverityBadge, Empty } from "../components/ui";
import { OverviewDecision } from "../components/DecisionBrief";
import { p2WorkbenchEnabled } from "../services/p2";
import { AutomaticOverview } from "../components/AutomaticProjectAssessment";

const severityColors = {
  critical: "var(--og-severity-critical, #fa7188)", high: "var(--og-severity-high, #ff974d)", medium: "var(--og-severity-medium, #f6c65c)",
  low: "var(--og-severity-low, #6eaeff)", info: "var(--og-severity-info, #9eafc8)",
};
const resourceColors = ["var(--og-resource-1, #88d3c5)", "var(--og-resource-2, #70b9c7)", "var(--og-resource-3, #89abc9)", "var(--og-resource-4, #a7bdc6)", "var(--og-resource-5, #9cc1b3)", "var(--og-resource-6, #c4c8b1)"];
const severityEnglish = { critical: "CRITICAL", high: "HIGH", medium: "MEDIUM", low: "LOW", info: "INFO" };
const severityTitles = { critical: "严重风险", high: "高风险", medium: "中风险", low: "低风险", info: "信息提示" };


export function Overview({
  scan,
  go,
}: {
  scan: Scan;
  go: (page: string, query?: string, riskId?: string) => void;
}) {
  const s = summarize(scan);
  const severities = severityOrder.map((severity) => ({
    severity,
    count: scan.risks.filter((r) => r.severity === severity).length,
  }));
  const allInformational = scan.risks.length > 0 && scan.risks.every(r => r.severity === "info");
  const onlyLicenseGates = allInformational && scan.risks.every(r => r.ruleId === "license-evidence-gate" && r.outcome === "review_required");
  const severityContext = onlyLicenseGates
    ? `当前 ${scan.risks.length} 条均为许可依据待核验提示，未发现严重、高、中、低风险规则命中。`
    : allInformational
      ? `当前 ${scan.risks.length} 条均为信息级规则提示，未发现严重、高、中、低风险规则命中。`
      : `按后端规则严重度展示 ${scan.risks.length} 条发现；与人工处理进度、许可核验状态分别统计。`;
  const resources = resourceTypes.map((type) => ({
    type,
    count: scan.resources.filter((r) => r.type === type).length,
  }));
  const finishedLabel = scan.finishedAt
    ? new Date(scan.finishedAt).toLocaleString()
    : (["queued", "running"].includes(scan.status) ? "尚未完成扫描" : "完成时间未提供");
  return (
    <div className="og-overview">
      <section className="og-overview-intro" aria-labelledby="overview-title">
        <header className="og-overview-heading">
          <div>
            <h1 id="overview-title">扫描概览</h1>
            <div className="og-overview-identity">
              <strong>{scan.project}</strong>
              <span>{finishedLabel}</span>
            </div>
          </div>
          <button className="og-overview-progress" onClick={() => go("progress")}>查看扫描阶段 <span aria-hidden="true">→</span></button>
        </header>
        <div className="og-overview-inventory"><button onClick={() => go("resources")}><strong>{scan.resources.length}</strong> 个资源</button><span><strong>{scan.evidence.length}</strong> 条证据</span></div>
      </section>
        <aside className="auto-reading-guide overview-reading-guide" aria-label="扫描概览阅读指南">
          <details><summary>如何阅读概览与处理分类</summary>
          <p>先看组件的处理分类，再进入“项目评估”查看具体做法。分类帮助安排检查顺序，不是风险高低排名。</p><dl>
            <div><dt>资源</dt><dd>项目使用的第三方软件包等组件。一个组件的一次记录不等于一项风险。</dd></div>
            <div><dt>证据</dt><dd>支持判断的文件或来源记录。同一个组件可以有多条证据，证据数量不是准确率。</dd></div>
            <div><dt>处理分类与风险</dt><dd>下方分类帮助安排检查顺序；正式规则风险另行展示。材料未核验不会自动算作高风险。</dd></div>
          </dl></details>
        </aside>
        {scan.mode === "api" && p2WorkbenchEnabled && <AutomaticOverview scan={scan} go={go}/>}
        <details className="og-formal-severity-details"><summary>查看正式规则严重度与原扫描统计</summary>
        <div className="og-overview-metrics" aria-label="五级风险严重度">
          {severities.map(({ severity, count }) => (
            <button className={`og-overview-metric severity-${severity}`} data-severity={severity} onClick={() => go("risks", "severity=" + severity)} key={severity} aria-label={`${severityTitles[severity]} ${count} 条，查看对应发现`}>
              <span className="og-overview-metric-copy">
                <span><i aria-hidden="true" style={{ backgroundColor: severityColors[severity] }} />{severityTitles[severity]}</span>
                <strong>{count}</strong>
                <small>{severityEnglish[severity]}</small>
              </span>
              <span className="og-overview-arrow" aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
        <div className="og-overview-severity-context"><p>{severityContext}</p><small>零高风险不代表许可已确认或已获授权；未知和待核验不会被自动升级为高风险。</small></div>
        </details>
        <details className="og-overview-scan-id"><summary>扫描身份</summary><code>{scan.id}</code></details>

      {scan.mode === "api" && !p2WorkbenchEnabled && <section className="og-overview-usage"><OverviewDecision scanId={scan.id} /></section>}
      <details className="og-formal-severity-details"><summary>查看原始规则发现与资源类型分布</summary>
      <div className="og-overview-grid">
        <div className="og-overview-priority">
          <Panel
            title={onlyLicenseGates ? "优先核对许可依据" : "优先查看规则发现"}
            caption="先看证据，再判断；不是自动法律结论"
            action={<button className="og-overview-all" onClick={() => go("risks")}>全部发现 <span aria-hidden="true">→</span></button>}
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
                        <strong>{r.ruleId === "license-evidence-gate" && r.outcome === "review_required" ? "许可依据待核验" : r.title}</strong>
                        <small>{scan.resources.find((x) => x.id === r.resourceId)?.name ?? "资源待补充"} · {scan.resources.find((x) => x.id === r.resourceId)?.version ?? "版本待确认"}</small>
                      </span>
                      <span className={"og-overview-handling " + r.handling}>{handlingLabels[r.handling]} <span aria-hidden="true">→</span></span>
                    </button>
                  ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="og-overview-statistics">
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
      </details>
    </div>
  );
}
