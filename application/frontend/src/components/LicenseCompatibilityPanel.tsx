import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { Scan } from "../types/domain";
import { statusLabels } from "../types/domain";
import {
  compatibilityStatusLabels,
  compatibilityStatuses,
  readLicenseCompatibility,
  targetSourceLabels,
  type CompatibilityStatus,
  type LicenseCompatibilityReport,
  type PairwiseConflict,
  type TargetAssessment,
} from "../services/licenseCompatibility";
import { ApiError } from "../services/scans";
import { Empty, Panel } from "./ui";
import "./LicenseCompatibilityPanel.css";

type StatusFilter = CompatibilityStatus | "";

const defaultTargets = [
  "PROPRIETARY", "AGPL-3.0-only", "AGPL-3.0-or-later", "Apache-2.0", "BSD-2-Clause",
  "BSD-3-Clause", "CC-BY-4.0", "CC-BY-NC-4.0", "CC0-1.0", "CDDL-1.0", "EPL-2.0",
  "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later", "ISC",
  "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
  "MIT", "MPL-2.0", "Unlicense",
];

const matrixShortLabels: Record<CompatibilityStatus, string> = {
  COMPATIBLE: "兼容",
  CONDITIONAL: "条件",
  REVIEW_REQUIRED: "复核",
  INCOMPATIBLE: "冲突",
  UNKNOWN: "未知",
};

function describeCompatError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return "登录后可查看项目级许可证兼容矩阵。";
    if (error.status === 400) return "所选目标许可证无效，请选择受支持的 SPDX 标识或 PROPRIETARY。";
    if (error.status === 403 || error.status === 404) return "扫描不存在或当前账户无权查看兼容矩阵。";
    return "无法读取许可证兼容矩阵（HTTP " + error.status + "）。";
  }
  return error instanceof Error ? error.message : "无法读取许可证兼容矩阵。";
}

function StatusPill({ status }: { status: CompatibilityStatus }) {
  return <span className={`og-compat-pill is-${status.toLowerCase()}`} data-compat-status={status}>
    {compatibilityStatusLabels[status]}
  </span>;
}

function AssessmentRow({ item, expanded, onToggle }: {
  item: TargetAssessment;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detailId = useId();
  return <li>
    <button
      type="button"
      className={"og-resource-row og-compat-row" + (expanded ? " is-selected" : "")}
      data-compat-resource={item.resource_id}
      aria-expanded={expanded}
      aria-controls={expanded ? detailId : undefined}
      onClick={onToggle}
    >
      <span className="og-compat-identity">
        <strong>{item.name}</strong>
        <small>{item.version ?? "版本未提供"} · {item.ecosystem}</small>
      </span>
      <span className="og-compat-license">
        <code>{item.declared_license ?? "未声明"}</code>
        {item.chosen_branch && <small>可选分支：{item.chosen_branch}</small>}
      </span>
      <span><StatusPill status={item.status} /></span>
      <span className="og-compat-action">{expanded ? "收起详情" : "查看依据"}</span>
    </button>
    {expanded && <div id={detailId} className="og-compat-detail">
      <p><strong>规则编号：</strong><code>{item.rule_id}</code></p>
      <p>{item.rationale}</p>
      {item.obligations.length > 0 && <ul className="og-compat-obligations">
        {item.obligations.map(text => <li key={text}>{text}</li>)}
      </ul>}
      {item.evidence_ids.length > 0 && <p className="og-muted">关联证据：{item.evidence_ids.join("、")}</p>}
    </div>}
  </li>;
}

function PairwiseCard({ conflict }: { conflict: PairwiseConflict }) {
  return <article className="og-compat-pair-card" data-pair-status={conflict.status}>
    <header>
      <div>
        <strong><code>{conflict.license_a}</code> ↔ <code>{conflict.license_b}</code></strong>
        <small> · <code>{conflict.rule_id}</code></small>
      </div>
      <StatusPill status={conflict.status} />
    </header>
    <p>{conflict.rationale}</p>
    <p className="og-muted">
      {conflict.license_a}（{conflict.components_a.map(c => c.name).join("、")}） vs{" "}
      {conflict.license_b}（{conflict.components_b.map(c => c.name).join("、")}）
    </p>
  </article>;
}

export type CompatibilityPanelState = {
  report: LicenseCompatibilityReport | null;
  supportedTargets: string[];
  loading: boolean;
  error: string | null;
};

export const initialCompatibilityPanelState: CompatibilityPanelState = {
  report: null,
  supportedTargets: defaultTargets,
  loading: true,
  error: null,
};

export function compatLoadStarted(state: CompatibilityPanelState): CompatibilityPanelState {
  return { ...state, report: null, loading: true, error: null };
}

export function compatLoadSucceeded(
  _state: CompatibilityPanelState,
  report: LicenseCompatibilityReport,
): CompatibilityPanelState {
  return {
    report,
    supportedTargets: report.supported_targets.length > 0 ? report.supported_targets : defaultTargets,
    loading: false,
    error: null,
  };
}

export function compatLoadFailed(state: CompatibilityPanelState, error: string): CompatibilityPanelState {
  return { ...state, report: null, loading: false, error };
}

export function LicenseCompatibilityView({
  report,
  supportedTargets = defaultTargets,
  loading,
  error,
  targetChoice,
  statusFilter,
  onTargetChange,
  onStatusFilterChange,
  onRetry,
}: {
  report: LicenseCompatibilityReport | null;
  supportedTargets?: string[];
  loading: boolean;
  error: string | null;
  targetChoice: string;
  statusFilter: StatusFilter;
  onTargetChange: (value: string) => void;
  onStatusFilterChange: (value: StatusFilter) => void;
  onRetry: () => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const targets = report?.supported_targets ?? supportedTargets;
  const filteredRows = report
    ? (statusFilter ? report.target_assessments.filter(item => item.status === statusFilter) : report.target_assessments)
    : [];

  return <section className="og-compat-panel" aria-label="项目级许可证兼容矩阵" data-license-compatibility>
    <Panel
      title="项目级许可证兼容矩阵"
      caption={report ? `${statusLabels[report.scan_ref.status]} · ${report.rule_version}` : "静态兼容评估"}
      action={
        <label className="og-field og-compat-target-select">
          目标发布许可证
          <select
            aria-label="目标发布许可证"
            value={targetChoice}
            onChange={event => {
              setExpandedId(null);
              onTargetChange(event.target.value);
            }}
          >
            <option value="">自动推导（根包声明）</option>
            {targets.map(item => <option key={item} value={item}>
              {item === "PROPRIETARY" ? "PROPRIETARY（闭源商业）" : item}
            </option>)}
          </select>
        </label>
      }
    >
      {loading && !report && <p className="og-compat-message" role="status">正在计算许可证兼容矩阵…</p>}
      {error && <div className="og-compat-error" role="alert">
        <span>{error}</span>
        <button type="button" onClick={onRetry}>重新加载兼容矩阵</button>
      </div>}
      {report && <>
        <div className="og-compat-banner">
          <div className="og-compat-target-meta">
            <span>综合结论：<StatusPill status={report.summary.overall_status} /></span>
            <span>
              当前目标：<strong>{report.target.license ?? "未确立（UNKNOWN）"}</strong>
              <small> · {targetSourceLabels[report.target.source]}</small>
            </span>
          </div>
          <div className="og-compat-usage-chips" aria-label="适用用途声明">
            {([
              ["commercial", "商业用途"],
              ["distributed", "对外分发"],
              ["modified", "源码修改"],
              ["network_service", "网络服务"],
            ] as const).map(([key, label]) => (
              <span key={key} className={report.usage[key] ? "is-active" : "is-inactive"}>
                {label}：{report.usage[key] ? "是" : "否"}
              </span>
            ))}
          </div>
        </div>

        <div className="og-compat-counts" role="group" aria-label="按兼容状态筛选">
          <button
            type="button"
            className={statusFilter === "" ? "is-selected" : ""}
            onClick={() => onStatusFilterChange("")}
          >
            全部 <strong>{report.target_assessments.length}</strong>
          </button>
          {compatibilityStatuses.map(status => (
            <button
              key={status}
              type="button"
              className={`is-${status.toLowerCase()}` + (statusFilter === status ? " is-selected" : "")}
              onClick={() => onStatusFilterChange(statusFilter === status ? "" : status)}
            >
              {compatibilityStatusLabels[status]} <strong>{report.summary.target_counts[status]}</strong>
            </button>
          ))}
        </div>

        <div className="og-compat-section">
          <h4>目标 ← 依赖兼容性明细（{filteredRows.length} / {report.target_assessments.length}）</h4>
          {filteredRows.length === 0 ? (
            <Empty
              title={statusFilter ? "当前筛选状态下无依赖组件" : "本次扫描未发现外部依赖组件"}
              detail={statusFilter ? "可切换上方状态筛选或选择“全部”查看完整列表。" : undefined}
            />
          ) : (
            <ul className="og-resource-list og-compat-list">
              {filteredRows.map(item => (
                <AssessmentRow
                  key={item.resource_id}
                  item={item}
                  expanded={expandedId === item.resource_id}
                  onToggle={() => setExpandedId(cur => cur === item.resource_id ? null : item.resource_id)}
                />
              ))}
            </ul>
          )}
        </div>

        <div className="og-compat-section">
          <h4>依赖 ↔ 依赖两两冲突与兼容矩阵（冲突 {report.summary.pairwise_counts.INCOMPATIBLE} · 复核 {report.summary.pairwise_counts.REVIEW_REQUIRED}）</h4>
          {report.pairwise_conflicts.length === 0 ? (
            <p className="og-muted">已观察到的依赖许可证之间未发现互斥或待复核冲突。</p>
          ) : (
            <div className="og-compat-pairs">
              {report.pairwise_conflicts.map(conflict => (
                <PairwiseCard key={`${conflict.license_a}::${conflict.license_b}`} conflict={conflict} />
              ))}
            </div>
          )}

          {report.matrix.licenses.length >= 2 && (
            <div className="og-compat-matrix-wrap">
              <table className="og-compat-matrix" aria-label="依赖许可证 N×N 兼容矩阵">
                <thead>
                  <tr>
                    <th>依赖许可证</th>
                    {report.matrix.licenses.map((lic, index) => (
                      <th key={lic} scope="col" title={lic}>#{index + 1}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.matrix.licenses.map((rowLic, rowIdx) => (
                    <tr key={rowLic}>
                      <th scope="row" title={rowLic}>#{rowIdx + 1} <code>{rowLic}</code></th>
                      {report.matrix.licenses.map((colLic, colIdx) => {
                        const cell = report.matrix.cells[rowIdx * report.matrix.licenses.length + colIdx];
                        return (
                          <td
                            key={colLic}
                            className={`is-${cell.status.toLowerCase()}`}
                            title={`${rowLic} × ${colLic}: ${compatibilityStatusLabels[cell.status]} (${cell.rule_id})`}
                          >
                            {matrixShortLabels[cell.status]}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {report.matrix.truncated && <p className="og-muted">矩阵仅展示前 30 种去重许可证，完整冲突列表以上方为准。</p>}
            </div>
          )}
        </div>

        <footer className="og-compat-limits">
          <p>{report.limitations.join(" ")}</p>
        </footer>
      </>}
    </Panel>
  </section>;
}

function LiveLicenseCompatibilityPanel({ scanId }: { scanId: string }) {
  const [targetChoice, setTargetChoice] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [panelState, setPanelState] = useState<CompatibilityPanelState>(initialCompatibilityPanelState);
  const active = useRef<AbortController | null>(null);

  const load = useCallback(async (target: string) => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setPanelState(prev => compatLoadStarted(prev));
    try {
      const next = await readLicenseCompatibility(scanId, {
        targetLicense: target || undefined,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setPanelState(prev => compatLoadSucceeded(prev, next));
    } catch (err) {
      if (controller.signal.aborted) return;
      setPanelState(prev => compatLoadFailed(prev, describeCompatError(err)));
    }
  }, [scanId]);

  useEffect(() => {
    void load(targetChoice);
    return () => active.current?.abort();
  }, [load, targetChoice]);

  return <LicenseCompatibilityView
    report={panelState.report}
    supportedTargets={panelState.supportedTargets}
    loading={panelState.loading}
    error={panelState.error}
    targetChoice={targetChoice}
    statusFilter={statusFilter}
    onTargetChange={setTargetChoice}
    onStatusFilterChange={setStatusFilter}
    onRetry={() => void load(targetChoice)}
  />;
}

export function LicenseCompatibilityPanel({ scan }: { scan: Scan }) {
  if (scan.mode !== "api" || (scan.status !== "completed" && scan.status !== "partial")) return null;
  return <LiveLicenseCompatibilityPanel
    key={JSON.stringify([scan.id, scan.status, scan.revision, scan.finishedAt])}
    scanId={scan.id}
  />;
}
