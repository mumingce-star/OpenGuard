import { reportDownloadUrl } from "../services/scans";
import type { Scan, ReportFormat } from "../types/domain";
import {
  statusLabels,
  handlingLabels,
  verificationLabels,
} from "../types/domain";
import { reportPayload, summarize } from "../services/model";
import { Header, download, useNotice } from "../components/ui";
const chapters = [
  "执行摘要",
  "风险清单",
  "第三方资源",
  "模型与数据集",
  "整改建议",
  "证据附录",
];
export function Report({ scan }: { scan: Scan }) {
  const notify = useNotice(),
    s = summarize(scan);
  return (
    <>
      <Header
        title="可复核的扫描报告"
        description="报告来自当前任务快照；不重新推断风险，也不生成准备度评分。"
        action={
          <div className="og-actions">
            {scan.mode === "api" ? (scan.reportFormats?.length ? scan.reportFormats.map(format => <a key={format} href={reportDownloadUrl(scan.id, format)} download>{({ html: "下载 HTML", json: "下载 JSON", csv: "下载 CSV", resource_inventory: "下载资源清单" } as Record<ReportFormat, string>)[format]}</a>) : <span>当前任务没有已发布报告</span>) : <button
              onClick={() =>
                download(
                  scan.id + "-report.json",
                  JSON.stringify(reportPayload(scan), null, 2),
                  "application/json;charset=utf-8",
                  notify,
                )
              }
            >
              导出演示 JSON
            </button>}
            <button onClick={() => window.print()}>打印 / 保存 PDF</button>
          </div>
        }
      />
      <div className="og-report-layout">
        <nav className="og-report-nav" aria-label="报告目录">
          {chapters.map((c, i) => (
            <a href={"#report-" + i} key={c}>
              {String(i + 1).padStart(2, "0")} / {c}
            </a>
          ))}
        </nav>
        <article className="og-report">
          <header>
            <p>OPENGUARD / EVIDENCE FIRST</p>
            <h1>
              {scan.project}
              <br />
              合规信息与风险提示报告
            </h1>
            <p>
              {scan.mode === "mock"
                ? "演示数据 · 合成示例 · 非真实扫描"
                : "真实接口数据"}{" "}
              · {statusLabels[scan.status]}
            </p>
          </header>
          <dl className="og-report-meta">
            <dt>任务编号</dt>
            <dd>{scan.id}</dd>
            <dt>扫描开始时间</dt>
            <dd>{scan.createdAt ? new Date(scan.createdAt).toLocaleString() : "后端未提供"}</dd>
            <dt>完成时间</dt>
            <dd>
              {scan.finishedAt
                ? new Date(scan.finishedAt).toLocaleString()
                : "尚未完成"}
            </dd>
            <dt>快照版本</dt>
            <dd>{scan.snapshotVersion}</dd>
          </dl>
          <section id="report-0">
            <h2>01 / 执行摘要</h2>
            <p>
              当前快照包含 {s.resources} 项资源、{s.risks} 个风险提示。其中{" "}
              {s.pending} 个处于待处理或复核中，{s.unknown}{" "}
              项资源的许可尚待确认。
            </p>
            {scan.error && <p>任务错误：{scan.error}</p>}
            <p>
              “已处理”为人工工作记录，不代表复扫验证通过。没有风险提示不等于已经核验所有许可。
            </p>
          </section>
          <section id="report-1">
            <h2>02 / 风险清单</h2>
            {!scan.risks.length ? (
              <p>当前快照没有风险条目，请结合任务状态理解。</p>
            ) : (
              scan.risks.map((r) => (
                <div className="og-report-block" key={r.id}>
                  <h3>
                    {r.id} · {r.title}
                  </h3>
                  <p>扫描事实：{r.fact ?? "待补充"}</p>
                  <p>规则判断：{r.conclusion ?? "待补充"}</p>
                  <p>
                    AI 解释：
                    {r.ai.text ??
                      (r.ai.status === "failed" ? "生成失败" : "暂不可用")}
                  </p>
                  <p>
                    处理：{handlingLabels[r.handling]} / 验证：
                    {verificationLabels[r.verification]}
                  </p>
                  <p>
                    关联资源：{r.resourceId} / 证据：
                    {r.evidenceIds.join("、") || "待补充"}
                  </p>
                </div>
              ))
            )}
          </section>
          <section id="report-2">
            <h2>03 / 第三方资源</h2>
            {scan.resources.length ? (
              scan.resources.map((r) => (
                <div className="og-report-block" key={r.id}>
                  <h3>
                    {r.name} · {r.type}
                  </h3>
                  <p>
                    {r.id} / 版本：{r.version ?? "待补充"} / 来源：
                    {r.origin ?? "待补充"}
                  </p>
                  <p>
                    许可证：{r.license ?? "未知"} /{" "}
                    {r.licenseStatus === "confirmed" ? "已核验" : "待确认"}
                  </p>
                </div>
              ))
            ) : (
              <p>暂无资源数据。</p>
            )}
          </section>
          <section id="report-3">
            <h2>04 / 模型与数据集</h2>
            {scan.resources.filter((r) => ["Model", "Dataset"].includes(r.type))
              .length ? (
              scan.resources
                .filter((r) => ["Model", "Dataset"].includes(r.type))
                .map((r) => (
                  <p key={r.id}>
                    {r.name}：来源 {r.origin ?? "待补充"}；许可{" "}
                    {r.license ?? "待确认"}；证据{" "}
                    {r.evidenceIds.join("、") || "待补充"}。
                  </p>
                ))
            ) : (
              <p>本次未提供模型或数据集条目。</p>
            )}
          </section>
          <section id="report-4">
            <h2>05 / 整改建议</h2>
            {scan.risks.length ? (
              scan.risks.map((r) => (
                <p key={r.id}>
                  {r.id}：{r.remediation ?? "待补充"}
                </p>
              ))
            ) : (
              <p>暂无整改条目。</p>
            )}
          </section>
          <section id="report-5">
            <h2>06 / 证据附录</h2>
            {scan.evidence.map((e) => (
              <div className="og-report-block" key={e.id}>
                <h3>
                  {e.id} · {e.label}
                </h3>
                <p>
                  来源：{e.source} / 位置：{e.path ?? e.url ?? "待补充"}
                  {e.startLine ? " 第 " + e.startLine + " 行起" : ""}
                </p>
                <pre>{e.text ?? "原文待补充"}</pre>
              </div>
            ))}
            {[...new Set(scan.risks.flatMap((r) => r.evidenceIds))]
              .filter((id) => !scan.evidence.some((e) => e.id === id))
              .map((id) => (
                <p key={id}>{id}：原始证据待补充。</p>
              ))}
            {!scan.evidence.length && <p>暂无可展示的证据原文。</p>}
          </section>
          <footer>
            OpenGuard
            仅提供合规信息整理与风险提示，不构成法律意见；请由负责人核对许可原文及适用场景。
          </footer>
        </article>
      </div>
    </>
  );
}
