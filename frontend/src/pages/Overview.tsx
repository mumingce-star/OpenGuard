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
  const observed = scan.resources.filter(r => r.license && !/^(unknown|NOASSERTION|none|未知)$/i.test(r.license)).length;
  return <div className="og-overview">
    <header className="og-overview-heading page-head"><div><h1 id="overview-title">{scan.project} 扫描概览</h1><p>{finishedLabel} · 所有数量来自当前扫描，未知与待核验不默认放行。</p></div><div className="og-actions"><button onClick={()=>go('progress')}>查看扫描阶段</button><button className="og-primary" onClick={()=>go('assessment')}>进入项目评估 →</button></div></header>
    <section className="og-v3-kpi" aria-label="扫描事实摘要"><div className="og-overview-inventory"><button onClick={()=>go('resources')}><span>识别第三方资源</span><strong>{scan.resources.length}</strong><small>个资源</small></button><span><span>采集溯源证据链</span><strong>{scan.evidence.length}</strong><small>条证据</small></span></div><div><span>许可依据待核验</span><strong>{scan.risks.filter(r=>r.ruleId==='license-evidence-gate' && r.outcome==='review_required').length}</strong><small>按规则门禁原值统计</small></div><div><span>项目用途与材料评估</span><button onClick={()=>go('assessment')}>查看已保存评估 →</button><small>用途与材料结果独立于扫描事实</small></div></section>
    <aside className="og-v3-callout"><div><strong>建议下一步：在「项目评估」核对用途与对应版本的 LICENSE 原文</strong><p>许可证声明仅作为候选线索，材料缺口与适用边界继续保留。</p></div><button onClick={()=>go('assessment')}>进入评估工作台</button></aside>
    {scan.mode==='api'&&p2WorkbenchEnabled&&<details className="og-v3-assessment-summary"><summary>查看项目用途与材料评估摘要</summary><AutomaticOverview scan={scan} go={go}/></details>}
    <div className="og-overview-grid">
      <div className="og-overview-priority"><Panel title={onlyLicenseGates?'规则严重度与优先核验队列':'规则严重度与优先发现'} action={<button onClick={()=>go('risks')}>查看全部 {scan.risks.length} 条发现 →</button>}>
        <div className="og-v3-severity-bar" aria-hidden="true">{severities.map(({severity,count})=><i key={severity} style={{flex:count,background:severityColors[severity]}}/>)}</div>
        <div className="og-overview-metrics" aria-label="五级风险严重度">{severities.map(({severity,count})=><button className={`og-overview-metric severity-${severity}`} data-severity={severity} onClick={()=>go('risks','severity='+severity)} key={severity} aria-label={`${severityTitles[severity]} ${count} 条，查看对应发现`}><i aria-hidden="true" style={{background:severityColors[severity]}}/><span>{severityTitles[severity]}</span><strong>{count}</strong></button>)}</div>
        <details className="og-formal-severity-details"><summary>查看正式规则严重度与原扫描统计</summary><p>{severityContext}</p><small>零高风险不代表许可已确认或已获授权；未知和待核验不会被自动升级为高风险。</small></details>
        {scan.risks.length===0?<Empty title={scan.resources.length?'本次未发现风险提示':'本次没有资源结果'} detail="未发现不代表已完成全部许可核验，请结合扫描状态与覆盖边界确认。"/>:<div className="og-overview-risk-list">{[...scan.risks].sort((a,b)=>severityOrder.indexOf(a.severity)-severityOrder.indexOf(b.severity)).slice(0,5).map(r=><button className="og-overview-risk" key={r.id} onClick={()=>go('risks','',r.id)}><span className="og-overview-risk-copy"><strong>{scan.resources.find(x=>x.id===r.resourceId)?.name??'资源待补充'} <small>{scan.resources.find(x=>x.id===r.resourceId)?.version??'版本待确认'}</small></strong><small>{r.ruleId==='license-evidence-gate'&&r.outcome==='review_required'?'许可依据待核验':r.title}</small></span><SeverityBadge value={r.severity}/><span>{r.evidenceIds.length} 条证据</span><span className="og-overview-handling">{handlingLabels[r.handling]} →</span></button>)}</div>}
        <footer className="og-v3-panel-foot"><span>展示前 {Math.min(5,scan.risks.length)} 项，共 {scan.risks.length} 条发现</span><button onClick={()=>go('resources')}>在资源清单展开全部 →</button></footer>
      </Panel></div>
      <div className="og-overview-statistics"><Panel title="资源构成与许可线索态势" action={<button onClick={()=>go('graph')}>查看关系图 →</button>}>
        <div className="og-overview-resource-chart"><div className="og-overview-donut" aria-hidden="true"><svg viewBox="0 0 120 120"><circle className="og-overview-donut-track" cx="60" cy="60" r="47" fill="none" strokeWidth="12"/>{resources.map(({type,count},i)=>{const share=s.resources?count/s.resources*100:0,offset=s.resources?resources.slice(0,i).reduce((sum,x)=>sum+x.count,0)/s.resources*100:0;return count>0?<circle key={type} cx="60" cy="60" r="47" fill="none" stroke={resourceColors[i]} strokeWidth="12" pathLength="100" strokeDasharray={`${share} ${100-share}`} strokeDashoffset={-offset} transform="rotate(-90 60 60)"/>:null;})}</svg><div><strong>{s.resources}</strong><span>项资源</span></div></div><div className="og-overview-legend">{resources.map(({type,count},i)=><button key={type} onClick={()=>go('resources','type='+type)}><i aria-hidden="true" style={{backgroundColor:resourceColors[i]}}/><span>{type}</span><b>{count}</b></button>)}</div></div>
        <div className="og-v3-coverage"><h3>许可证观测覆盖率 <span>{observed} / {s.resources}</span></h3><div className="og-v3-coverage-track"><i style={{width:(s.resources?observed/s.resources*100:0)+'%'}}/></div><p>已观测声明 <strong>{observed}</strong></p><p>未观测声明 <strong>{s.resources-observed}</strong></p></div>
        <p className="og-v3-boundary">边界提醒：清单声明不等于授权确认。完整原文、精确版本与用途须在项目评估中逐项核对。</p>
      </Panel></div>
    </div>
    <aside className="auto-reading-guide overview-reading-guide"><details><summary>如何阅读概览与处理分类</summary><p>资源是第三方组件记录，证据是来源片段；证据数量不是准确率。处理分类不等于规则严重度。</p></details></aside>

    {scan.mode==='api'&&!p2WorkbenchEnabled&&<section className="og-overview-usage"><OverviewDecision scanId={scan.id}/></section>}
    <details className="og-overview-scan-id"><summary>扫描身份</summary><code>{scan.id}</code></details>
  </div>;
}
