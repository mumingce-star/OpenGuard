import { reportDownloadUrl } from "../services/scans";
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
  const sections = resourceTypes.map(type => ({ type, rows: rows.filter(r => r.type === type) })).filter(section => section.rows.length);
  return (
    <>
      <Header
        title="第三方资源清单"
        eyebrow={"INVENTORY / " + scan.id}
        description="未知许可保持待确认，未发现风险不等于许可已通过。"
        action={
          scan.mode === "api" ? (scan.reportFormats?.includes("resource_inventory") ? <a href={reportDownloadUrl(scan.id, "resource_inventory")} download>下载完整资源清单</a> : <span>资源清单尚未发布</span>) : <button
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
        caption={scan.mode === "api" ? "筛选仅影响当前页面，下载包含完整资源清单" : "全量任务快照 · CSV 仅包含当前筛选结果"}
      >
        {!rows.length ? (
          <Empty title="没有符合条件的资源" detail="尝试调整搜索和筛选条件。" />
        ) : (
          <div className="og-resource-list">
            {sections.map(section => <ResourceSection key={section.type} type={section.type} rows={section.rows} scan={scan} select={setSelected}/>)}
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
function ResourceSection({ type, rows, scan, select }: { type: string; rows: Scan["resources"]; scan: Scan; select: (id: string) => void }) {
  const [open, setOpen] = useState(false), [limit, setLimit] = useState(25), visible = open ? rows.slice(0, limit) : [];
  const label = ({ Package: "代码组件", Model: "模型", Dataset: "数据集", API: "接口", Service: "服务", Asset: "素材" } as Record<string, string>)[type];
  return <section className="og-resource-section"><button className="og-risk-preview" aria-expanded={open} onClick={() => setOpen(v => !v)}><div><strong>{label}</strong><small>{rows.length} 项资源 · 默认按需显示</small></div><span>{open ? "收起" : "展开"}</span></button>{open && <><div className="og-resource-head"><span>名称 / 版本</span><span>许可状态</span><span>来源</span><span>关联发现</span></div>{visible.map(r => <button className="og-resource-row" key={r.id} onClick={() => select(r.id)}><div><strong>{r.name}</strong><small>{r.version ?? "版本未知"}</small></div><span>{r.license ?? "许可证未知"}<small>{r.licenseStatus === "confirmed" ? "许可已核验" : "许可待确认"}</small></span><span>{r.origin ?? "未提供来源网址"}<small>{scan.evidence.filter(e => r.evidenceIds.includes(e.id)).map(e => e.path ?? e.url ?? e.label).join("；") || "证据位置未知"}</small></span><span>{scan.risks.filter(x => x.resourceId === r.id).length} 个风险 →</span></button>)}<p>当前显示 {visible.length} / {rows.length} 项资源</p>{limit < rows.length && <div className="og-actions"><button onClick={() => setLimit(n => n + 25)}>继续显示后 25 项</button><button onClick={() => setLimit(rows.length)}>显示全部</button></div>}</>}</section>;
}
