import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { Scan } from "../types/domain";
import { graphNodeKinds, type GraphNodeKind, type ResourceGraphView } from "../types/p1Graph";
import { edgeAppearance, filterResourceGraph, getResourceGraph, graphEdgeLabels, graphKindLabels, layoutResourceGraph } from "../services/p1Graph";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { Empty, Header, Panel } from "../components/ui";
import { EvidenceReader } from "../components/EvidenceReader";

type Props = { scan: Scan; query: URLSearchParams; filter: (name: string, value: string) => void };
const zoomValues = [0.5, 0.75, 1, 1.25, 1.5];

function selectedKinds(query: URLSearchParams): GraphNodeKind[] {
  const raw = query.get("graph_kinds")?.split(",").filter(Boolean) ?? [];
  return raw.filter((kind): kind is GraphNodeKind => graphNodeKinds.includes(kind as GraphNodeKind));
}

export function Graph({ scan, query, filter }: Props) {
  const [view, setView] = useState<ResourceGraphView | null>(null);
  const [loading, setLoading] = useState(scan.mode === "api");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const reduced = useReducedMotion();
  const search = query.get("graph_q") ?? "";
  const kinds = selectedKinds(query);
  const selectedId = query.get("graph_node") ?? "";
  const requestedZoom = Number(query.get("graph_zoom") ?? "1");
  const zoom = zoomValues.includes(requestedZoom) ? requestedZoom : 1;
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());

  useEffect(() => {
    if (scan.mode !== "api") {
      setLoading(false);
      setView(null);
      setError("");
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getResourceGraph(scan.id, controller.signal).then(setView).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "资源关系图读取失败。");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, attempt]);

  const visible = useMemo(() => view ? filterResourceGraph(view, search, kinds) : { nodes: [], edges: [] }, [view, search, kinds.join(",")]);
  const layout = useMemo(() => layoutResourceGraph(visible.nodes), [visible.nodes]);
  const positions = useMemo(() => new Map(layout.nodes.map((node) => [node.id, node])), [layout.nodes]);
  const selected = view?.nodes.find((node) => node.id === selectedId) ?? null;
  const relatedEdges = selected && view ? view.edges.filter((edge) => edge.source === selected.id || edge.target === selected.id) : [];
  const evidenceNodes = selected && view ? relatedEdges.flatMap((edge) => {
    const other = view.nodes.find((node) => node.id === (edge.source === selected.id ? edge.target : edge.source));
    return other?.kind === "evidence" ? [other] : [];
  }) : [];

  function toggleKind(kind: GraphNodeKind) {
    const active = new Set(kinds.length ? kinds : graphNodeKinds);
    active.has(kind) ? active.delete(kind) : active.add(kind);
    filter("graph_kinds", active.size === graphNodeKinds.length ? "" : graphNodeKinds.filter((item) => active.has(item)).join(","));
  }

  function selectNode(id: string) { filter("graph_node", id); }
  function navigateNode(event: KeyboardEvent<HTMLButtonElement>, id: string) {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNode(id); return; }
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const index = layout.nodes.findIndex((node) => node.id === id);
    const step = event.key === "ArrowUp" || event.key === "ArrowLeft" ? -1 : 1;
    const next = layout.nodes[(index + step + layout.nodes.length) % layout.nodes.length];
    if (next) nodeRefs.current.get(next.id)?.focus();
  }

  if (scan.mode !== "api") return <><Header eyebrow="P1 / RESOURCE GRAPH" title="资源关系图" description="Graph 页面只读取真实冻结接口，演示模式不会合成节点或关系。" /><Empty title="真实图谱不可用于演示数据" detail="请从真实扫描上下文打开此页面。" /></>;
  if (loading) return <><Header eyebrow="P1 / RESOURCE GRAPH" title="资源关系图" description="正在只读加载已存储扫描事实，不会触发扫描、Assessment 或远程请求。" /><Empty title="正在读取资源关系图…" detail="仅请求 GET /api/v1/scans/{scan_id}/graph。" /></>;
  if (error) return <><Header eyebrow="P1 / RESOURCE GRAPH" title="资源关系图" description="读取失败不会回退到 Mock，也不会补造关系。" /><Empty title="无法读取资源关系图" detail={error}><button type="button" onClick={() => setAttempt((value) => value + 1)}>重试真实接口</button></Empty></>;
  if (!view) return <Empty title="资源关系图不可用" detail="接口没有返回可展示的数据。" />;

  return <>
    <Header eyebrow="P1 / RESOURCE GRAPH" title="资源关系图" description="只展示后端 Graph API 返回的事实节点与关系；本图不是 Formal Assessment，许可观测不代表授权，Finding 仅为待核查线索。" />
    {view.coverage.scan_gaps.length > 0 && <div className="og-scan-coverage-notice" role="status"><strong>扫描部分完成，关系图仅覆盖当前已有事实。</strong><span>未出现的资源不代表已删除；覆盖限制：{view.coverage.scan_gaps.join("；")}</span></div>}
    <Panel title={`事实关系 · ${visible.nodes.length} / ${view.coverage.node_count} 节点`} caption={`${visible.edges.length} / ${view.coverage.edge_count} 条后端事实边 · ${view.coverage.scope === "all" ? "全量已有事实" : "后端筛选闭包"}`}>
      <div className="og-graph-toolbar">
        <label className="og-field">搜索节点<input type="search" value={search} placeholder="名称或原始 ID" onChange={(event) => filter("graph_q", event.target.value)} /></label>
        <fieldset><legend>节点类型</legend>{graphNodeKinds.map((kind) => <label key={kind}><input type="checkbox" checked={!kinds.length || kinds.includes(kind)} onChange={() => toggleKind(kind)} />{graphKindLabels[kind]}</label>)}</fieldset>
        <div className="og-graph-zoom" aria-label="图谱缩放"><button type="button" disabled={zoom === zoomValues[0]} onClick={() => filter("graph_zoom", String(zoomValues[Math.max(0, zoomValues.indexOf(zoom) - 1)]))} aria-label="缩小">−</button><output>{Math.round(zoom * 100)}%</output><button type="button" disabled={zoom === zoomValues.at(-1)} onClick={() => filter("graph_zoom", String(zoomValues[Math.min(zoomValues.length - 1, zoomValues.indexOf(zoom) + 1)]))} aria-label="放大">＋</button><button type="button" onClick={() => filter("graph_zoom", "")}>重置</button></div>
      </div>
      <div className="og-graph-legend" aria-label="关系语义图例"><span><i className="solid" />明确包含关系</span><span><i className="dashed" />观测或规则引用</span><span><i className="dotted" />Evidence 支持</span><small>线型依据冻结边类型映射；前端不判断关系置信度。</small></div>
      {!visible.nodes.length ? <Empty title="没有匹配节点" detail={view.nodes.length ? "请调整搜索或类型筛选；后端原图未被改写。" : "后端返回了合法空图，没有可展示的事实节点。"} /> : <div className="og-graph-shell">
        <div className="og-graph-canvas" tabIndex={0} aria-label={`资源关系图画布，共 ${visible.nodes.length} 个节点、${visible.edges.length} 条边`}>
          <div className="og-graph-stage" style={{ width: layout.width * zoom, height: layout.height * zoom }}>
          <svg width="100%" height="100%" viewBox={`0 0 ${layout.width} ${layout.height}`} className={reduced ? "reduced" : ""} role="img" aria-labelledby="graph-title graph-desc">
            <title id="graph-title">扫描 {scan.id} 的资源关系图</title><desc id="graph-desc">使用 Tab 聚焦节点，方向键移动焦点，Enter 或空格打开详情。</desc>
            <g className="og-graph-edges">{visible.edges.map((edge) => { const source = positions.get(edge.source), target = positions.get(edge.target); return source && target ? <line key={edge.id} x1={source.x + 80} y1={source.y + 25} x2={target.x + 80} y2={target.y + 25} className={edgeAppearance(edge.type)} aria-label={graphEdgeLabels[edge.type]} /> : null; })}</g>
          </svg>
          <div className="og-graph-node-layer" style={{ width: layout.width, height: layout.height, transform: `scale(${zoom})` }}>{layout.nodes.map((node) => <button type="button" key={node.id} ref={(element) => { if (element) nodeRefs.current.set(node.id, element); else nodeRefs.current.delete(node.id); }} style={{ left: node.x, top: node.y }} className={`og-graph-node ${node.kind}${selectedId === node.id ? " selected" : ""}`} aria-label={`${graphKindLabels[node.kind]}：${node.label}`} onClick={() => selectNode(node.id)} onKeyDown={(event) => navigateNode(event, node.id)}><span>{graphKindLabels[node.kind]}</span><strong>{node.label.length > 20 ? node.label.slice(0, 19) + "…" : node.label}</strong></button>)}</div>
          </div>
        </div>
        <aside className="og-graph-detail" aria-label="节点详情">{selected ? <><header><span>{graphKindLabels[selected.kind]}</span><button type="button" onClick={() => filter("graph_node", "")} aria-label="关闭节点详情">关闭</button></header><h3>{selected.label}</h3><dl><dt>节点 ID</dt><dd>{selected.id}</dd><dt>原始 source_id</dt><dd>{selected.source_id}</dd><dt>事实关系</dt><dd>{relatedEdges.length} 条</dd></dl>{relatedEdges.length > 0 && <ul>{relatedEdges.map((edge) => <li key={edge.id}><strong>{graphEdgeLabels[edge.type]}</strong><small>{edge.source_refs.map((ref) => ref.pointer).join("；")}</small></li>)}</ul>}{evidenceNodes.length > 0 && <div className="og-graph-evidence-links"><strong>关联 Evidence</strong>{evidenceNodes.map((node) => <button type="button" key={node.id} onClick={() => selectNode(node.id)}>{node.label}</button>)}</div>}{selected.kind === "evidence" && <EvidenceReader key={selected.source_id} scan={scan} ids={[selected.source_id]} initialId={selected.source_id} />}</> : <Empty title="选择节点查看事实" detail="详情只显示后端节点、事实边与 SourcePointer。" />}</aside>
      </div>}
      <p className="og-graph-footnote">视图 {view.view_id} · Graph Schema {view.schema_version} · 算法 {view.provenance.algorithm_version} · 容量 {view.capacity.max_nodes} 节点 / {view.capacity.max_edges} 边</p>
    </Panel>
  </>;
}
