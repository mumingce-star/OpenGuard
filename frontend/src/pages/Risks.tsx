import { useState } from "react";
import type { Scan, Handling } from "../types/domain";
import {
  handlingLabels,
  verificationLabels,
  severityLabels,
  resourceTypes,
} from "../types/domain";
import { filterRisks, groupRisks, riskCounts, severityOrder, aiSourceLabel } from "../services/model";
import { updateHandling } from "../services/scans";
import {
  Header,
  Panel,
  Empty,
  SeverityBadge,
  useNotice,
  copyText,
} from "../components/ui";
import { EvidenceReader } from "../components/EvidenceReader";
export function Risks({
  scan,
  query,
  filter,
  open,
}: {
  scan: Scan;
  query: URLSearchParams;
  filter: (k: string, v: string) => void;
  open: (id: string) => void;
}) {
  const rows = filterRisks(scan, query);
  const groups = groupRisks(scan, rows);
  const counts = riskCounts(rows);
  return (
    <>
      <Header
        title="风险中心"
        eyebrow={"FINDINGS / " + scan.id}
        description="筛选、处理与复扫验证分开记录。所有判断都应回到证据。"
      />
      {!!scan.diagnostics?.length && <Panel title="扫描完整性" caption="以下是扫描执行的未覆盖内容或限制，不计入许可证发现数量。">
        <details>
          <summary>查看 {scan.diagnostics.length} 条扫描诊断</summary>
          {scan.diagnostics.map((d, i) => <div key={i} className="og-source scanner">
            <strong>{d.code}</strong>
            <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{d.message}</p>
            <small>{d.stage ? `阶段：${d.stage}` : ""}{d.tool ? ` · 工具：${d.tool}` : ""}</small>
            {!!d.evidence_ids?.length && <p>证据引用：{d.evidence_ids.join("、")}</p>}
          </div>)}
        </details>
      </Panel>}
      <div className="og-filters">
        <label className="og-field">
          搜索风险
          <input
            value={query.get("q") ?? ""}
            onChange={(e) => filter("q", e.target.value)}
            placeholder="名称、风险编号、资源…"
          />
        </label>
        <label className="og-field">
          严重度
          <select
            aria-label="严重度"
            value={query.get("severity") ?? ""}
            onChange={(e) => filter("severity", e.target.value)}
          >
            <option value="">全部严重度</option>
            {Object.entries(severityLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="og-field">
          处理状态
          <select
            aria-label="处理状态"
            value={query.get("handling") ?? ""}
            onChange={(e) => filter("handling", e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="pending">全部待处理</option>
            {Object.entries(handlingLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="og-field">
          资源类型
          <select
            aria-label="资源类型"
            value={query.get("type") ?? ""}
            onChange={(e) => filter("type", e.target.value)}
          >
            <option value="">全部类型</option>
            {resourceTypes.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
      </div>
      <Panel
        title={"筛选结果 · " + rows.length + " / " + scan.risks.length}
        caption="先筛选原始发现，再按问题分类。展开同类组可逐条核对，报告仍保留全部明细。"
      >
        {!rows.length ? (
          <Empty
            title="没有符合条件的风险"
            detail="可以清空筛选，或返回概览查看本次任务。"
          />
        ) : (
          <div key={scan.id + query.toString()}>
            <p>{counts.resources} 个唯一资源 · {counts.findings} 条发现</p>
            <p>{severityOrder.map(v => `${severityLabels[v]} ${counts.counts[v]}`).join(" · ")}</p>
            {groups.map(group => (
              <RiskCategory key={group.title} group={group} scan={scan} open={open} />
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
export function RiskDetail({
  scan,
  riskId,
  back,
  reload,
}: {
  scan: Scan;
  riskId: string;
  back: () => void;
  reload: () => void;
}) {
  const risk = scan.risks.find((r) => r.id === riskId),
    notify = useNotice(),
    [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  if (!risk)
    return (
      <Empty title="风险编号不存在" detail={"当前任务中没有 " + riskId}>
        <button onClick={back}>返回风险列表</button>
      </Empty>
    );
  const resource = scan.resources.find((r) => r.id === risk.resourceId);
  async function handle(value: Handling) {
    if (!risk) return;
    setBusy(true);
    try {
      await updateHandling(scan.id, risk.id, value, scan.mode);
      notify("处理状态已保存；复扫验证状态没有改变。");
      reload();
    } catch (e) {
      notify((e as Error).message, "error", () => void handle(value));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button className="og-back" onClick={back}>
        ← 返回风险列表（保留筛选）
      </button>
      <Header
        title={risk.title}
        eyebrow={scan.id + " / " + risk.id}
        description={
          (resource?.name ?? "资源待补充") +
          " · " +
          (resource?.license ?? "许可证待确认")
        }
        action={<SeverityBadge value={risk.severity} />}
      />
      <div className="og-review-strip">
        <label>
          处理状态{" "}
          <select
            aria-label="处理状态"
            value={risk.handling}
            disabled={busy || scan.mode === "api"}
            onChange={(e) => void handle(e.target.value as Handling)}
          >
            {Object.entries(handlingLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <span>验证状态：{verificationLabels[risk.verification]}</span>
        <small>{scan.mode === "api" ? "当前扫描结果只读，未提供人工处理或复扫记录" : "人工标记已处理 ≠ 复扫通过"}</small>
      </div>
      <div className="og-detail-layout">
        <div className="og-stack">
          <Panel title="事实、判断与解释">
            <div className="og-source scanner">
              <span>扫描事实</span>
              <p>{risk.fact ?? "扫描事实待补充"}</p>
            </div>
            <div className="og-source rule">
              <span>规则判断 · 需人工复核</span>
              <p>{risk.conclusion ?? "判断依据待补充"}</p>
            </div>
            <div className="og-source ai">
              <span>
                {aiSourceLabel(risk)}
              </span>
              <p style={{ whiteSpace: "pre-wrap" }}>
                {risk.ai.text ??
                  "没有可用 AI 解释。已提供的扫描事实与规则结果仍然可查看。"}
              </p>
            </div>
          </Panel>
          <Panel
            title="证据引用"

          >
            <div className="og-evidence-links">
              {risk.evidenceIds.length ? (
                risk.evidenceIds.map((id) => (
                  <button
                    key={id}
                    onClick={() => setSelected(id)}
                    aria-pressed={selected === id}
                  >
                    {scan.evidence.find((e) => e.id === id)?.label ??
                      "证据待补充"}
                    <small>{id}</small>
                  </button>
                ))
              ) : (
                <p>证据待补充</p>
              )}
            </div>
          </Panel>
          <Panel
            title="整改建议"
            action={
              <button
                disabled={!risk.remediation}
                onClick={() => void copyText(risk.remediation!, notify)}
              >
                复制建议
              </button>
            }
          >
            {risk.remediation?.startsWith("【资源级AI解释】") && <p className="og-warning">来源说明：【资源级AI解释】为模型辅助解释；【扫描事实】【读取范围】【结论边界】及【证据定位】【事实导航】等步骤由程序依据扫描记录整理，不是模型原话，也不表示链接已核验授权。</p>}
            <p style={{ whiteSpace: "pre-wrap" }}>{risk.remediation ?? "未提供生成建议，请依据已列出的原文进行人工复核。"}</p>
            <p className="og-warning">
              完成整改后仍需真实复扫；不预测风险降级或准备度分数。
            </p>
          </Panel>
        </div>
        <Panel title="证据阅读器" caption="原文与结论并排核验">
          <EvidenceReader
            key={risk.id + selected}
            scan={scan}
            ids={risk.evidenceIds}
            initialId={selected}
          />
        </Panel>
      </div>
    </>
  );
}

function RiskCategory({ group, scan, open }: { group: ReturnType<typeof groupRisks>[number]; scan: Scan; open: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  return <section className="og-risk-group">
    <button className="og-risk-preview" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {group.highest && <SeverityBadge value={group.highest} />}
      <div><strong>{group.title}</strong><small>{group.resources} 个唯一资源 · {group.findings} 条发现 · {group.groups.length} 个同类组 · 左侧为实际最高严重度</small>
      <small>{severityOrder.filter(s => group.counts[s]).map(s => `${severityLabels[s]} ${group.counts[s]}`).join(" · ")}</small></div>
      <span>{expanded ? "收起" : "展开"}</span>
    </button>
    {expanded && group.groups.map(g => <RiskMembers key={g.key} group={g} scan={scan} open={open} />)}
  </section>;
}
function RiskMembers({ group, scan, open }: { group: ReturnType<typeof groupRisks>[number]["groups"][number]; scan: Scan; open: (id: string) => void }) {
  const { title } = group;
  const rows = group.rows as import("../types/domain").Risk[];
  const [expanded, setExpanded] = useState(false);
  const [limit, setLimit] = useState(25);
  const counts = riskCounts(rows);
  return <section style={{ paddingLeft: "1rem" }}>
    <button className="og-risk-preview" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {counts.highest && <SeverityBadge value={counts.highest} />}
      <div><strong>{title}</strong><small>{group.summary}</small><small>{counts.resources} 个唯一资源 · {counts.findings} 条发现</small></div>
      <span>{expanded ? "收起明细" : "展开明细"}</span>
    </button>
    {expanded && <>
      <p>分组说明：{group.summary}</p>
      {group.advice && <div className="og-group-advice"><strong>{({ group_ai: "组级 AI 建议", historical: "历史成员建议", rule: "规则说明", unavailable: "AI 建议暂不可用" } as Record<string, string>)[group.advice.kind]}</strong><p>{group.advice.summary}</p>{group.advice.steps.map((step: string, i: number) => <p key={i}>{i + 1}. {step}</p>)}</div>}
      <p>原始规则：{group.rule}</p><p style={{overflowWrap: "anywhere"}}>触发说明：{group.trigger}</p>
      <p>当前显示 {Math.min(limit, rows.length)} / {rows.length} 条原始发现</p>
      {rows.slice(0, limit).map(r => <button className="og-risk-preview" key={r.id} onClick={() => open(r.id)}>
        <SeverityBadge value={r.severity} />
        <div><strong>{r.title}</strong><small>{r.id} · {scan.resources.find(x => x.id === r.resourceId)?.name ?? "待补充"}</small>
        <small>{verificationLabels[r.verification]} · {r.evidenceIds.length} 个证据引用</small></div>
        <span>{handlingLabels[r.handling]} →</span>
      </button>)}
      {limit < rows.length && <button onClick={() => setLimit(n => n + 25)}>继续显示后 25 条（剩余 {rows.length - limit} 条）</button>}
      {limit < rows.length && <button onClick={() => setLimit(rows.length)}>显示全部 {rows.length} 条</button>}
    </>}
  </section>;
}
