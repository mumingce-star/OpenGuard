import { useEffect, useState, type ReactNode, type MouseEvent } from "react";
import { flushSync } from "react-dom";
import { reportDownloadUrl } from "../services/scans";
import type { Scan, ReportFormat, Risk, Resource } from "../types/domain";
import { statusLabels, severityLabels } from "../types/domain";
import { groupRisks, reportPayload, riskCounts, summarize } from "../services/model";
import { presentDiagnostic } from "../services/assessmentPresentation";
import { DownloadControl, DownloadGlyph, Header, download, useNotice } from "../components/ui";
const chapters = ["执行摘要", "风险清单", "第三方资源", "模型与数据集", "整改建议", "证据附录"];
const formatLabels: Record<ReportFormat, string> = { html: "下载 HTML", json: "下载 JSON", csv: "下载 CSV", resource_inventory: "下载资源清单" };
function focusChapter(target: HTMLElement, behavior: ScrollBehavior) {
 target.focus({ preventScroll: true });
 target.scrollIntoView({ behavior, block: "start" });
}
function navigateChapter(event: MouseEvent<HTMLAnchorElement>, index: number) {
 if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
 const fragment = "#report-" + index, target = document.getElementById(fragment.slice(1));
 if (!target) return;
 event.preventDefault();
 // A native fragment navigation emits popstate in the router and its saved
 // scroll restoration can override the anchor. Keep the pinned URL unchanged
 // except for its chapter fragment, without creating a route-history entry.
 window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search + fragment);
 focusChapter(target, window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
}
const adviceLabel: Record<string, string> = { group_ai: "组级 AI 建议", historical: "历史成员建议", rule: "规则说明", unavailable: "AI 建议暂不可用" };
function Paginated<T>({ rows, label, render, printing }: { rows: T[]; label: string; render: (row: T) => ReactNode; printing: boolean }) {
 const [open, setOpen] = useState(false); const [limit, setLimit] = useState(25); const shown = printing ? rows : open ? rows.slice(0, limit) : [];
 return <details open={open || printing} onToggle={e => { if (!printing) setOpen((e.target as HTMLDetailsElement).open); }}>
   <summary>{label}（{printing ? "打印完整" : open ? `显示 ${shown.length}/${rows.length}` : "展开"}）</summary>
   {shown.map(render)}
   {open && !printing && limit < rows.length && <div className="og-actions"><button onClick={() => setLimit(n => n + 25)}>继续显示后 25 条</button><button onClick={() => setLimit(rows.length)}>显示全部</button></div>}
 </details>;
}
function RiskRows({ rows, scan, printing }: { rows: Risk[]; scan: Scan; printing: boolean }) { return <Paginated rows={rows} printing={printing} label={`原始发现 ${rows.length} 条`} render={r => { const resource = scan.resources.find(x => x.id === r.resourceId); return <div className="og-report-row" key={r.id}><strong>{resource?.name ?? r.resourceId}</strong><span>{resource?.version ?? "版本未知"} · {resource?.origin ?? "来源未知"} · {resource?.license ?? "许可未知"} · {severityLabels[r.severity]}</span><span>证据位置：{scan.evidence.filter(e => r.evidenceIds.includes(e.id)).map(e => e.path ?? e.url ?? e.label).join("；") || "未提供"}；触发：{r.fact ?? "未知"}</span><a href={`/app/scans/${encodeURIComponent(scan.id)}/risks/${encodeURIComponent(r.id)}?mode=${scan.mode}`}>查看原详情与证据（{r.evidenceIds.length}）</a></div>; }}/>; }
function ResourceRows({ rows, printing }: { rows: Resource[]; printing: boolean }) { return <Paginated rows={rows} printing={printing} label={`资源明细 ${rows.length} 项`} render={r => <div className="og-report-row" key={r.id}><strong>{r.name}</strong><span>{r.version ?? "版本未知"} · {r.type} · {r.license ?? "许可未知"}</span><span>来源：{r.origin ?? "未知"}</span><span>资源 ID：{r.id}</span></div>}/>; }
function ScanDiagnostics({ scan }: { scan: Scan }) {
 const diagnostics = scan.diagnostics ?? [];
 return <div className="og-report-diagnostics">
   <h3>运行状态、覆盖范围与未完成项</h3>
   <p>以下记录是扫描执行诊断，不计入许可证风险数量。可恢复标记是保存时的状态，不表示已恢复或会自动重试。</p>
   {diagnostics.length ? diagnostics.map((diagnostic, index) => {
     const shown = presentDiagnostic(diagnostic);
     return <div className="og-report-block" key={`${diagnostic.code}-${index}`}>
       <h4>{shown.title}</h4><p>{shown.detail}</p>
       <p>错误码：<code>{diagnostic.code}</code> · 阶段：{diagnostic.stage ?? "未提供"} · 工具：{diagnostic.tool ?? "未提供"} · 可恢复标记：{diagnostic.recoverable === true ? "是" : diagnostic.recoverable === false ? "否" : "未提供"}</p>
       <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>原始说明：{diagnostic.message}</p>
       {diagnostic.evidence_ids?.length ? <ul>{diagnostic.evidence_ids.map(id => {
         const evidence = scan.evidence.find(item => item.id === id);
         return <li key={id}><code>{id}</code>：{evidence ? evidence.path ?? evidence.url ?? evidence.label : "当前快照未包含该证据，无法确认关联路径"}</li>;
       })}</ul> : <p>关联证据：未提供</p>}
     </div>;
   }) : <p>{scan.error ? `原始诊断：${scan.error}` : "当前快照未提供结构化诊断；不代表整个仓库已核验。"}</p>}
 </div>;
}
export function Report({ scan }: { scan: Scan }) { const notify = useNotice(), s = summarize(scan), groups = groupRisks(scan, scan.risks), counts = riskCounts(scan.risks), [printing, setPrinting] = useState(false); useEffect(() => { const before = () => flushSync(() => setPrinting(true)), after = () => setPrinting(false); addEventListener("beforeprint", before); addEventListener("afterprint", after); return () => { removeEventListener("beforeprint", before); removeEventListener("afterprint", after); }; }, []); const contexts = groups.reduce((n, g) => n + g.groups.length, 0), dataTime = scan.finishedAt ?? scan.createdAt;
 useEffect(() => {
  const fragment = window.location.hash;
  if (!/^#report-[0-5]$/.test(fragment)) return;
  const target = document.getElementById(fragment.slice(1));
  if (target) focusChapter(target, "auto");
 }, [scan.id]);
 const secondaryFormats = scan.reportFormats?.filter(format => format !== "html") ?? [];
 const action = <div className="og-actions og-report-export-actions" aria-label="扫描报告导出">
  {scan.mode === "api" ? <>
   {scan.reportFormats?.includes("html") && <a className="og-download-button og-report-primary-export" href={reportDownloadUrl(scan.id, "html")} download><DownloadGlyph /><span>{formatLabels.html}</span></a>}
   {!scan.reportFormats?.length && <span className="og-report-export-empty">当前任务没有已发布报告</span>}
  </> : <DownloadControl onDownload={() => download(scan.id + "-report.json", JSON.stringify(reportPayload(scan), null, 2), "application/json;charset=utf-8", notify)}>导出演示 JSON</DownloadControl>}
  <button type="button" className="og-download-button og-report-print" onClick={() => window.print()}><DownloadGlyph /><span>打印完整报告 / 保存 PDF</span></button>
  {scan.mode === "api" && secondaryFormats.length > 0 && <details className="og-report-more-formats"><summary>更多格式</summary><div>{secondaryFormats.map(format => <a key={format} className="og-download-button" href={reportDownloadUrl(scan.id, format)} download><DownloadGlyph /><span>{formatLabels[format]}</span></a>)}</div></details>}
 </div>;
 return <div className="og-report-page"><Header title="可复核的扫描报告" description="按目录核对扫描发现、资源与证据，展开明细可查看原始记录。" action={action}/><details className="og-report-version-boundary"><summary>本页保留扫描事实 · 查看版本边界</summary><p>修改用途后的评估与补充材料后的 P2 结果分别留在「项目评估」；固定版本的用途评估报告可在「报告归档与导出」保存。本页扫描附件不会被后续评估覆盖。</p></details><div className="og-report-layout"><nav className="og-report-nav" aria-label="报告目录"><p>报告目录</p>{chapters.map((c, i) => <a href={'#report-' + i} key={c} onClick={event => navigateChapter(event, i)}>{String(i + 1).padStart(2, "0")} / {c}</a>)}</nav><article className="og-report"><header><p>OPENGUARD / EVIDENCE FIRST</p><h1>{scan.project}<br/>合规信息与风险提示报告</h1><p>{scan.mode === "mock" ? "演示数据 · 合成示例" : "真实接口数据"} · {statusLabels[scan.status]}</p></header><dl className="og-report-meta"><dt>任务编号</dt><dd>{scan.id}</dd><dt>数据日期</dt><dd>{dataTime ? new Date(dataTime).toLocaleString() : "后端未提供"}</dd><dt>项目源码修订</dt><dd>{scan.revision ?? "后端未提供"}</dd><dt>扫描数据快照</dt><dd>{scan.snapshotVersion}</dd><dt>渲染版本</dt><dd>frontend-report-v2 · {scan.grouping?.version ?? "兼容投影"}</dd></dl><p className="og-report-disclaimer">历史附件保持不变；此页面仅以当前数据日期和渲染版本预览。OpenGuard 不构成法律意见。</p>
 <section id="report-0" tabIndex={-1} style={{ scrollMarginTop: "100px" }}><h2>01 / 执行摘要</h2><p>终态：{statusLabels[scan.status]}。{s.resources} 项资源、{s.risks} 条发现、{counts.resources} 项受影响资源；{groups.length} 个问题大类、{contexts} 个等价情境组。</p><p>{scan.status === "partial" ? "扫描仅部分完成：已有结果可以查看，但未覆盖项和未完成阶段不能当作已检查。" : scan.status === "failed" ? "扫描失败：当前结果不能当作完整扫描，零发现不能解释为没有风险。" : scan.status === "completed" ? "扫描流程已完成，不代表许可证适用性已获确认。" : "扫描尚未完整结束，请结合任务状态查看已有结果。"} 执行诊断与未完成项见第 06 章，不计入许可证风险数量。</p><p>严重度：{Object.entries(counts.counts).filter(([, n]) => n).map(([level, n]) => `${severityLabels[level as keyof typeof severityLabels]} ${n}`).join(" · ")}。</p></section>
 <section id="report-1" tabIndex={-1} style={{ scrollMarginTop: "100px" }}><h2>02 / 风险清单</h2>{groups.map(category => <div className="og-report-block" key={category.title}><h3>{category.title} · {category.findings} 条发现</h3>{category.groups.map(g => <div className="og-report-group" key={g.key}><h4>{g.title}</h4><p>{g.summary}</p><p>{g.advice?.kind === "group_ai" ? "共同情境建议未逐项审阅；完整建议见第05章。" : `${adviceLabel[g.advice?.kind ?? "rule"]}：${g.advice?.summary ?? "请按逐项证据核对。"}`}</p><RiskRows rows={g.rows} scan={scan} printing={printing}/></div>)}</div>)}</section>
 <section id="report-2" tabIndex={-1} style={{ scrollMarginTop: "100px" }}><h2>03 / 第三方资源</h2><ResourceRows rows={scan.resources.filter(r => !["Model", "Dataset"].includes(r.type))} printing={printing}/></section>
 <section id="report-3" tabIndex={-1} style={{ scrollMarginTop: "100px" }}><h2>04 / 模型与数据集</h2><ResourceRows rows={scan.resources.filter(r => r.type === "Model" || r.type === "Dataset")} printing={printing}/></section>
 <section id="report-4" tabIndex={-1} style={{ scrollMarginTop: "100px" }}><h2>05 / 整改建议</h2>{groups.flatMap(c => c.groups).map(g => <div className="og-report-block" key={g.key}><h3>{g.title}（适用于 {g.findings} 条发现）</h3><p><strong>{adviceLabel[g.advice?.kind ?? "rule"]}</strong>：{g.advice?.summary ?? "请按逐项证据核对。"}</p>{g.advice?.steps?.map((step: string, i: number) => <p key={i}>{i + 1}. {step}</p>)}</div>)}</section>
 <section id="report-5" tabIndex={-1} style={{ scrollMarginTop: "100px" }}><h2>06 / 证据附录</h2><Paginated rows={scan.evidence} printing={printing} label={`证据 ${scan.evidence.length} 条`} render={e => <div className="og-report-block" key={e.id}><h3>{e.label}</h3><p>{e.id} · {e.source} · {e.path ?? e.url ?? "位置未知"}</p><pre>{e.text ?? "原文待补充"}</pre></div>}/><ScanDiagnostics scan={scan}/></section><footer>原始成员与证据完整保留，打印时展开全部明细。</footer></article></div></div>; }
