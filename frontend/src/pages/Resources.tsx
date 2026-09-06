import { useState } from "react";
import type { Scan } from "../types/domain";
import { resourceTypes, severityLabels } from "../types/domain";
import { filterResources, resourceCsv } from "../services/model";
import {
  Header,
  Panel,
  Empty,
  Dialog,
  SeverityBadge,
  download,
  useNotice,
} from "../components/ui";
import { EvidenceReader } from "../components/EvidenceReader";
export function Resources({
  scan,
  query,
  filter,
  openRisk,
}: {
  scan: Scan;
  query: URLSearchParams;
  filter: (k: string, v: string) => void;
  openRisk: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null),
    notify = useNotice();
  const rows = filterResources(scan, query),
    resource = scan.resources.find((r) => r.id === selected);
  return (
    <>
      <Header
        title="第三方资源清单"
        eyebrow={"INVENTORY / " + scan.id}
        description="未知许可保持待确认，未发现风险不等于许可已通过。"
        action={
          <button
            onClick={() =>
              download(
                scan.id + "-filtered-resources.csv",
                resourceCsv(scan, rows),
                "text/csv;charset=utf-8",
                notify,
              )
            }
          >
            导出筛选结果 CSV（{rows.length}）
          </button>
        }
      />
      <div className="og-filters">
        <label className="og-field">
          搜索资源
          <input
            value={query.get("q") ?? ""}
            onChange={(e) => filter("q", e.target.value)}
            placeholder="名称、版本、来源…"
          />
        </label>
        <label className="og-field">
          类型
          <select
            aria-label="类型"
            value={query.get("type") ?? ""}
            onChange={(e) => filter("type", e.target.value)}
          >
            <option value="">全部类型</option>
            {resourceTypes.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="og-field">
          风险筛选
          <select
            aria-label="风险筛选"
            value={query.get("risk") ?? ""}
            onChange={(e) => filter("risk", e.target.value)}
          >
            <option value="">全部资源</option>
            <option value="any">有关联风险</option>
            {Object.entries(severityLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="og-check">
          <input
            type="checkbox"
            checked={query.get("unknown") === "1"}
            onChange={(e) => filter("unknown", e.target.checked ? "1" : "")}
          />
          仅许可待确认
        </label>
      </div>
      <Panel
        title={"筛选结果 · " + rows.length + " / " + scan.resources.length}
        caption="全量任务快照 · CSV 仅包含当前筛选结果"
      >
        {!rows.length ? (
          <Empty title="没有符合条件的资源" detail="尝试调整搜索和筛选条件。" />
        ) : (
          <div className="og-resource-list">
            {rows.map((r) => (
              <button
                className="og-resource-row"
                key={r.id}
                onClick={() => setSelected(r.id)}
              >
                <div>
                  <strong>{r.name}</strong>
                  <small>
                    {r.version ?? "版本待补充"} · {r.id}
                  </small>
                </div>
                <span>{r.type}</span>
                <span>{r.origin ?? "来源待补充"}</span>
                <span>
                  {r.license ?? "许可证未知"}
                  <small>
                    {r.licenseStatus === "confirmed"
                      ? "许可已核验"
                      : "许可待确认"}
                  </small>
                </span>
                <span>
                  {scan.risks.filter((x) => x.resourceId === r.id).length}{" "}
                  个风险 →
                </span>
              </button>
            ))}
          </div>
        )}
      </Panel>
      {resource && (
        <Dialog
          title={"资源详情 · " + resource.name}
          onClose={() => setSelected(null)}
        >
          <dl className="og-meta">
            <dt>版本</dt>
            <dd>{resource.version ?? "待补充"}</dd>
            <dt>来源</dt>
            <dd>{resource.origin ?? "待补充"}</dd>
            <dt>许可证</dt>
            <dd>
              {resource.license ?? "未知"} ·{" "}
              {resource.licenseStatus === "confirmed" ? "已核验" : "待确认"}
            </dd>
          </dl>
          <h3>相关风险</h3>
          {scan.risks
            .filter((r) => r.resourceId === resource.id)
            .map((r) => (
              <button
                className="og-risk-preview"
                key={r.id}
                onClick={() => {
                  setSelected(null);
                  openRisk(r.id);
                }}
              >
                <SeverityBadge value={r.severity} />
                <strong>{r.title}</strong>
              </button>
            ))}
          <EvidenceReader scan={scan} ids={resource.evidenceIds} />
        </Dialog>
      )}
    </>
  );
}
