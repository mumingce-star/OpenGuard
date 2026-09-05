import { useState } from "react";
import type { Scan, Handling } from "../types/domain";
import {
  handlingLabels,
  verificationLabels,
  severityLabels,
  resourceTypes,
} from "../types/domain";
import { filterRisks } from "../services/model";
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
  return (
    <>
      <Header
        title="风险中心"
        eyebrow={"FINDINGS / " + scan.id}
        description="筛选、处理与复扫验证分开记录。所有判断都应回到证据。"
      />
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
        caption="点击风险查看它自己的资源、依据与原文"
      >
        {!rows.length ? (
          <Empty
            title="没有符合条件的风险"
            detail="可以清空筛选，或返回概览查看本次任务。"
          />
        ) : (
          rows.map((r) => (
            <button
              className="og-risk-preview"
              key={r.id}
              onClick={() => open(r.id)}
            >
              <SeverityBadge value={r.severity} />
              <div>
                <strong>{r.title}</strong>
                <small>
                  {r.id} · {r.outcome ?? "演示风险"} ·{" "}
                  {scan.resources.find((x) => x.id === r.resourceId)?.name ??
                    "待补充"}
                </small>
                <small>
                  {verificationLabels[r.verification]} · {r.evidenceIds.length}{" "}
                  个证据引用
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
                AI 解释 ·{" "}
                {risk.ai.status === "ready"
                  ? "辅助内容"
                  : risk.ai.status === "failed"
                    ? "生成失败"
                    : "暂不可用"}
              </span>
              <p>
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
            <p>{risk.remediation ?? "整改建议待补充"}</p>
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
