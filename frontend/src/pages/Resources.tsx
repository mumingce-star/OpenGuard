import { reportDownloadUrl } from "../services/scans";
import { useEffect, useRef, useState } from "react";
import type { Scan } from "../types/domain";
import { resourceTypes, severityLabels } from "../types/domain";
import { filterResources, resourceCsv } from "../services/model";
import {
  Header,
  Panel,
  Empty,
  SeverityBadge,
  download,
  copyText,
  DownloadGlyph,
  DownloadControl,
  Checkbox,
  SearchGlyph,
  useNotice,
} from "../components/ui";
import { EvidenceReader } from "../components/EvidenceReader";
import { AIResourceCard } from "../components/AIResourceCard";
import { factVerificationLabels } from "../types/domain";
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
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(()=>{const focus=(e:KeyboardEvent)=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();searchInput.current?.focus();}};window.addEventListener('keydown',focus);return()=>window.removeEventListener('keydown',focus);},[]);
  const rows = filterResources(scan, query),
    resource = scan.resources.find((r) => r.id === (selected ?? query.get("resource_id"))) ?? rows[0];
  const aiRows = rows.filter((item) => item.type === "Model" || item.type === "Dataset");
  const sections = resourceTypes.filter(type => type !== "Model" && type !== "Dataset").map(type => ({ type, rows: rows.filter(r => r.type === type) })).filter(section => section.rows.length);
  return (
    <div className="og-v3-resources">
      <Header
        title="第三方资源清单"
        eyebrow={"INVENTORY / " + scan.id}
        description="模型、数据集与其他第三方资源均只展示扫描事实；未知保持未知，Finding 只是待核查线索。"
        action={
          scan.mode === "api" ? (scan.reportFormats?.includes("resource_inventory") ? <a className="og-download-button" href={reportDownloadUrl(scan.id, "resource_inventory")} download><DownloadGlyph /><span>下载完整资源清单</span></a> : <span>资源清单尚未发布</span>) : <DownloadControl
            onDownload={() =>
              download(
                scan.id + "-filtered-resources.csv",
                resourceCsv(scan, rows),
                "text/csv;charset=utf-8",
                notify,
              )
            }
          >
            导出筛选结果 CSV（{rows.length}）
          </DownloadControl>
        }
      />
      <div className="og-filters">
        <label className="og-field og-search-field">
          <span>搜索资源</span>
          <span className="og-search-control"><SearchGlyph /><input
            ref={searchInput}
            type="search"
            value={query.get("q") ?? ""}
            onChange={(e) => filter("q", e.target.value)}
            placeholder="名称、版本、来源…"
          /><kbd>⌘K</kbd></span>
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
        <Checkbox
            checked={query.get("unknown") === "1"}
            onChange={(e) => filter("unknown", e.target.checked ? "1" : "")}
          >
          仅许可待确认
        </Checkbox>
      </div>
      <p className="og-list-context">当前筛选显示 {rows.length} / {scan.resources.length} 项资源<span>筛选不改变扫描事实与许可核验状态</span></p>
      {aiRows.length > 0 && <Panel
        title={`模型与数据集资源卡片 · ${aiRows.length}`}
        caption="Resource、Profile 与 Evidence 分层展示；Profile 缺失不会由名称、Logo、provider 或 source URL 补造。"
      >
        {!aiRows.length ? (
          <Empty
            title="当前筛选没有模型或数据集"
            detail={scan.resources.some(item => item.type === "Model" || item.type === "Dataset")
              ? "调整筛选条件后查看已有模型或数据集资源。"
              : "本次真实扫描未返回模型或数据集 Resource；页面不会使用演示数据填充。"}
          />
        ) : (
          <div className="og-ai-resource-grid">
            {aiRows.map(item => (
              <AIResourceCard key={item.id} scan={scan} resource={item} onEvidence={() => setSelected(item.id)} />
            ))}
          </div>
        )}
      </Panel>}
      <div className="og-v3-resource-grid"><Panel
        title={"其他资源 · " + sections.reduce((total, section) => total + section.rows.length, 0) + " / " + scan.resources.length}
        caption={scan.mode === "api" ? "筛选仅影响当前页面，下载包含完整资源清单" : "全量任务快照 · CSV 仅包含当前筛选结果"}
      >
        {!sections.length ? (
          <Empty title="没有符合条件的其他资源" detail="尝试调整搜索和筛选条件。" />
        ) : (
          <div className="og-resource-list">
            {sections.map(section => <ResourceSection key={section.type} type={section.type} rows={section.rows} scan={scan} select={setSelected} selected={resource?.id}/>)}
          </div>
        )}
      </Panel>
      {resource && (
        <aside className="og-v3-inspector" aria-label="资源证据速览"><header><h2>{resource.name} @ {resource.version??'版本未获取'} 证据速览</h2><button type="button" onClick={()=>void copyText(resource.id,notify)}>复制 资源 ID</button></header><div className="og-v3-inspector-body"><div className="og-v3-kv-grid"><div><small>Package URL</small><strong>{'未提供独立 PURL'}</strong></div><div><small>精确定位位置</small><strong>{(()=>{const e=scan.evidence.find(e=>resource.evidenceIds.includes(e.id));return e?`${e.path??e.label}${e.startLine?': L'+e.startLine:''}`:'未提供';})()}</strong></div><div><small>扫描观测许可</small><strong>{resource.license??'未知'} · {factVerificationLabels[resource.licenseVerification??'unknown']}</strong></div><div><small>关联原始线索</small><strong>{resource.evidenceIds.length} 条引用</strong></div></div>
          <EvidenceReader key={resource.id} scan={scan} ids={resource.evidenceIds} />
          <p className="og-v3-boundary">核验边界：清单中的许可声明不代表完整原文或授权证明，未知与待核验状态保持不变。</p>
          <details><summary>完整资源身份与来源</summary>
          <dl className="og-meta">
            <dt>资源 ID</dt>
            <dd className="og-wrap-id">{resource.id}</dd>
            <dt>类型</dt>
            <dd>{resource.type === "Model" ? "模型" : resource.type === "Dataset" ? "数据集" : resource.type}</dd>
            <dt>provider</dt>
            <dd>{resource.provider ?? "未获取"}</dd>
            <dt>版本</dt>
            <dd>{resource.version ?? "未获取"}</dd>
            <dt>来源</dt>
            <dd>{resource.origin ?? "未获取"}</dd>
            <dt>扫描观测许可</dt>
            <dd>
              {resource.license ?? "未获取"} · {factVerificationLabels[resource.licenseVerification ?? "unknown"]}
            </dd>
            <dt>授权状态</dt>
            <dd>{factVerificationLabels[resource.authorizationStatus ?? "unknown"]}</dd>
          </dl></details>
          <h3>相关待核查线索</h3>
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
          </div></aside>
      )}</div>
    </div>
  );
}
function ResourceSection({ type, rows, scan, select, selected }: { type: string; rows: Scan["resources"]; scan: Scan; select: (id: string) => void; selected?:string }) {
  const [open, setOpen] = useState(true), [page, setPage] = useState(0);
  const key=rows.map(r=>r.id).join('|');
  useEffect(()=>setPage(0),[key]);
  const current=Math.min(page,Math.max(0,Math.ceil(rows.length/10)-1)),visible=rows.slice(current*10,current*10+10);
  const label = ({ Package: "代码组件", Model: "模型", Dataset: "数据集", API: "接口", Service: "服务", Asset: "素材" } as Record<string, string>)[type];
  return <section className="og-resource-section"><button className="og-risk-preview" aria-expanded={open} onClick={() => setOpen(v => !v)}><div><strong>{label}</strong><small>{rows.length} 项资源</small></div><span>{open ? "收起" : "展开"}</span></button>{open && <><div className="og-resource-head"><span>名称 / 版本</span><span>观测许可</span><span>来源</span><span>线索</span></div>{visible.map(r => <button className={'og-resource-row'+(selected===r.id?' is-selected':'')} aria-pressed={selected===r.id} key={r.id} onClick={() => select(r.id)}><div><strong>{r.name}</strong><small>{r.version ?? "版本未获取"}</small></div><span>{r.license ?? "许可未获取"}<small>{factVerificationLabels[r.licenseVerification ?? "unknown"]}</small></span><span title={r.origin??''}>{r.origin ?? "来源未获取"}<small>{scan.evidence.filter(e => r.evidenceIds.includes(e.id)).map(e => e.path ?? e.url ?? e.label).join("；") || "证据不足"}</small></span><span>{scan.risks.filter(x => x.resourceId === r.id).length} →</span></button>)}<footer className="og-v3-panel-foot"><span>显示第 {current*10+1}–{current*10+visible.length} 项，共 {rows.length} 项</span><div className="og-actions"><button disabled={current===0} onClick={()=>setPage(current-1)}>上一页</button><button disabled={(current+1)*10>=rows.length} onClick={()=>setPage(current+1)}>下一页 →</button></div></footer></>}</section>;
}
