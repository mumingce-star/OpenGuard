import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { Scan } from "../types/domain";
import type { GraphNode, ResourceGraphView } from "../types/p1Graph";
import { edgeAppearance, focusResourceGraph, getResourceGraph, graphEdgeLabels, graphKindLabels, graphNodeSize, layoutResourceGraph, resourceGraphChoices } from "../services/p1Graph";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { ArrowGlyph, Empty, Header, LoadingDots, SearchGlyph } from "../components/ui";
import { EvidenceReader } from "../components/EvidenceReader";
import { fitResourceGraph } from "./graphViewport";
import "./Graph.css";

const zoomValues = [0.5, 0.65, 0.85, 1, 1.25, 1.5];
type Props = { scan: Scan; query: URLSearchParams; filter: (name: string, value: string) => void };


export function GraphReadingGuide({ project, resourceLabel, sourceLabel, onReadSource }: {
  project: string;
  resourceLabel: string;
  sourceLabel: string | null;
  onReadSource?: () => void;
}) {
  return <aside className="og-graph-reading-guide" aria-label="图谱阅读说明">
    <span className="og-graph-guide-eyebrow">第一次看关系图？</span>
    <h2>从左到右，找到判断的出处</h2>
    <ol>
      <li><strong>项目</strong><span>你正在检查的软件项目。</span></li>
      <li><strong>组件</strong><span>项目用到的第三方软件或 AI 资源。</span></li>
      <li><strong>观测 / 线索</strong><span>扫描看到的许可信息，以及需要关注的事项。</span></li>
      <li><strong>来源 / 条款要求</strong><span>查看记录来自哪个文件；部分节点也会列出条款要求。</span></li>
    </ol>
    <div className="og-graph-guide-lines"><h3>连线在说什么？</h3>
      <p><i className="solid" /><span><strong>实线</strong>：项目包含这个资源。</span></p>
      <p><i className="dashed" /><span><strong>虚线</strong>：连到许可观测、线索或规则要求。</span></p>
      <p><i className="dotted" /><span><strong>点线</strong>：可以沿线查找来源证据。</span></p>
      <small>线型表示关系类别，不是风险等级或置信度；出现许可观测不等于已经获得授权。</small>
    </div>
    <div className="og-graph-guide-example"><h3>用当前资源读一遍</h3>
      <p>在 <strong>{project}</strong> 中，当前查看的是 <strong>{resourceLabel}</strong>。</p>
      {sourceLabel ? <><p>这条来源记录：<span className="og-graph-guide-source">{sourceLabel}</span></p><p>可以打开原文，看清扫描依据。</p>{onReadSource && <button className="og-arrow-button" type="button" onClick={onReadSource}><span>查看这条来源</span><ArrowGlyph /></button>}</> : <p>当前资源没有已关联的来源节点；不补造原文或关系。</p>}
    </div>
    <p className="og-graph-guide-help">点击图中方框查看详情。默认自动适配画布；放大后可在图内滚动。键盘可用 Tab、方向键和 Enter。</p>
  </aside>;
}

export function Graph({ scan, query, filter }: Props) {
  const [view, setView] = useState<ResourceGraphView | null>(null);
  const [loading, setLoading] = useState(scan.mode === "api");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const reduced = useReducedMotion();
  const search = query.get("graph_q") ?? "";
  const requestedId = query.get("graph_resource") ?? "";
  const selectedId = query.get("graph_node") ?? "";
  const requestedZoom = query.get("graph_zoom");
  const manualScale = requestedZoom !== null && zoomValues.includes(Number(requestedZoom)) ? Number(requestedZoom) : null;
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());

  useEffect(() => {
    if (scan.mode !== "api") { setLoading(false); setView(null); setError(""); return; }
    const controller = new AbortController();
    setLoading(true); setError("");
    getResourceGraph(scan.id, controller.signal).then(setView).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "资源关系图读取失败。");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [scan.id, scan.mode, attempt]);

  const choices = useMemo(() => view ? resourceGraphChoices(view, search) : [], [view, search]);
  const allResources = useMemo(() => view ? resourceGraphChoices(view) : [], [view]);
  const resource = choices.find(node => node.id === requestedId) ?? (requestedId && !search ? null : choices[0]) ?? null;
  const visible = useMemo(() => view && resource ? focusResourceGraph(view, resource.id) : { nodes: [], edges: [] }, [view, resource]);
  const layout = useMemo(() => layoutResourceGraph(visible.nodes), [visible.nodes]);
  const viewport = useMemo(() => fitResourceGraph(layout, canvasSize, manualScale), [layout, canvasSize, manualScale]);
  const zoom = viewport.scale;
  const lowerZoom = [...zoomValues].reverse().find(value => value < zoom - .001);
  const higherZoom = zoomValues.find(value => value > zoom + .001);
  const positions = useMemo(() => new Map(viewport.nodes.map(node => [node.id, node])), [viewport.nodes]);
  const selected = visible.nodes.find(node => node.id === selectedId) ?? resource;
  const relatedEdges = selected && view ? view.edges.filter(edge => edge.source === selected.id || edge.target === selected.id) : [];
  const evidenceNodes = visible.nodes.filter(node => node.kind === "evidence");
  const readingEvidence = selected?.kind === "evidence" ? selected : evidenceNodes[0] ?? null;
  const laneNames = ["项目", "当前资源", "许可观测 / 线索", "证据 / 义务"];
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const measure = () => setCanvasSize(previous => {
      const next = { width: canvas.clientWidth, height: canvas.clientHeight };
      return previous.width === next.width && previous.height === next.height ? previous : next;
    });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [loading, error, resource?.id]);
  function displayNode(node: GraphNode) {
    if (node.kind === "evidence") {
      const evidence = scan.evidence.find(item => item.id === node.source_id);
      const labels: Record<string, string> = { manifest_field: "依赖清单字段", tool_output: "扫描工具记录", file: "文件原文", source_file: "源码文件", license_text: "许可原文", metadata: "来源元数据" };
      const label = labels[evidence?.sourceKind ?? node.label] ?? labels[node.label] ?? evidence?.label ?? node.label;
      const detail = evidence?.path ?? evidence?.url ?? evidence?.source ?? "后端保存的来源记录";
      return { label, detail };
    }
    if (node.kind === "license_observation" && ["NOASSERTION", "UNKNOWN", "NONE"].includes(node.label)) return { label: "许可待核对", detail: "扫描尚未确认许可表达式" };
    if (node.kind === "finding" && node.label === "License evidence requires verification") return { label: "许可依据待核验", detail: "保留来源与版本核对线索" };
    return { label: node.label, detail: graphKindLabels[node.kind] };
  }
  function navigateNode(event: KeyboardEvent<HTMLButtonElement>, id: string) {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); filter("graph_node", id); return; }
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const index = layout.nodes.findIndex(node => node.id === id);
    const step = event.key === "ArrowUp" || event.key === "ArrowLeft" ? -1 : 1;
    const next = layout.nodes[(index + step + layout.nodes.length) % layout.nodes.length];
    if (next) nodeRefs.current.get(next.id)?.focus();
  }
  if (scan.mode !== "api") return <><Header title="资源与依据关系" description="查看当前扫描保存的真实资源、许可观测和来源证据。" /><Empty title="请先选择真实扫描" detail="演示数据不会合成关系图。" /></>;
  if (loading) return <><Header title="资源与依据关系" description="正在读取已保存的扫描事实。" /><LoadingDots label="正在读取关系图" detail="不会重新扫描或生成判断。" /></>;
  if (error) return <><Header title="资源与依据关系" description="关系图来自当前扫描保存的真实事实。" /><Empty title="关系图暂不可用" detail={error}><button className="og-arrow-button" type="button" onClick={() => setAttempt(value => value + 1)}><span>重新读取</span><ArrowGlyph /></button></Empty></>;
  if (!view) return <Empty title="关系图不可用" detail="当前没有可展示的数据。" />;

  return <div className="og-graph-page">
    <header className="og-graph-heading"><div><h1>资源与依据关系</h1><p>{scan.project} · 选择资源，追溯许可观测和来源证据</p></div><div className="og-graph-counts"><span><strong>{allResources.length}</strong> 资源</span><span><strong>{view.nodes.filter(node => node.kind === "evidence").length}</strong> 证据</span><span><strong>{view.edges.length}</strong> 关系</span></div></header>
    {view.coverage.scan_gaps.length > 0 && <div className="og-scan-coverage-notice" role="status"><strong>当前图谱保留扫描覆盖缺口。</strong><span>{view.coverage.scan_gaps.join("；")}</span></div>}
    <section className="og-panel og-graph-focus-panel" aria-label="按资源查看依据">
      <div className="og-graph-focus-controls">
        <label className="og-field og-search-field"><span>查找资源</span><span className="og-search-control"><SearchGlyph /><input type="search" value={search} placeholder="资源名称或完整 ID" onChange={event => filter("graph_q", event.target.value)} /></span></label>
        <label className="og-field">当前资源 · {choices.length} 项可选<select value={resource?.id ?? ""} onChange={event => filter("graph_resource", event.target.value)}><option value="" disabled>选择资源</option>{choices.map(node => <option value={node.id} key={node.id}>{node.label}</option>)}</select></label>
        <div className="og-graph-zoom" aria-label="图谱缩放"><button type="button" disabled={lowerZoom === undefined} onClick={() => lowerZoom !== undefined && filter("graph_zoom", String(lowerZoom))} aria-label="缩小">−</button><div className="og-graph-zoom-value"><output>{Math.round(zoom * 100)}%</output><small>{viewport.auto ? "自动适配" : "手动缩放"}</small></div><button type="button" disabled={higherZoom === undefined} onClick={() => higherZoom !== undefined && filter("graph_zoom", String(higherZoom))} aria-label="放大">＋</button><button type="button" onClick={() => filter("graph_zoom", "")}>重置</button></div>
      </div>
      {!resource ? <Empty title={requestedId && !search ? "所选资源不在当前扫描中" : "没有匹配资源"} detail="原始图谱保留不变，请重新选择或调整搜索。"><button onClick={() => filter(requestedId && !search ? "graph_resource" : "graph_q", "")}>显示可用资源</button></Empty> : <>
        <div className="og-graph-focus-title"><strong>{resource.label}</strong><span>当前展示 {visible.nodes.length} 个节点 · {visible.edges.length} 条事实关系</span></div>
        <div className="og-graph-legend" aria-label="关系语义图例"><span><i className="solid" />包含关系</span><span><i className="dashed" />许可观测与规则引用</span><span><i className="dotted" />来源证据支持</span></div>
        <div className="og-graph-explained">
        <div ref={canvasRef} className="og-graph-canvas og-focused-canvas" tabIndex={0} aria-label={`资源 ${resource.label} 的关系图，共 ${visible.nodes.length} 个节点、${visible.edges.length} 条边`}>
          <div className="og-focused-stage" style={{ width: viewport.width * zoom, height: (viewport.height + 36) * zoom, left: viewport.offsetX, top: viewport.offsetY, "--og-graph-node-font": `${13 * Math.min(1.3, 1 / viewport.fittedScale)}px`, "--og-graph-node-small": `${9 * Math.min(1.3, 1 / viewport.fittedScale)}px` } as CSSProperties}>
            <div className="og-graph-lanes" style={{ width: layout.width, transform: `scale(${zoom})` }}>{laneNames.map((name, index) => <span key={name} style={{ left: 26 + index * 236, width: graphNodeSize.width }}>{name}</span>)}</div>
            <svg width="100%" height="100%" viewBox={`0 -36 ${viewport.width} ${viewport.height + 36}`} className={reduced ? "reduced" : ""} role="img" aria-labelledby="graph-title graph-desc"><title id="graph-title">{resource.label} 的资源依据图</title><desc id="graph-desc">所有连线来自保存的扫描事实；Tab 聚焦节点，方向键移动焦点，Enter 查看依据。</desc><g className="og-graph-edges">{visible.edges.map(edge => {
              const source = positions.get(edge.source), target = positions.get(edge.target);
              if (!source || !target) return null;
              const forward = source.x <= target.x;
              const sx = source.x + (forward ? graphNodeSize.width : 0), tx = target.x + (forward ? 0 : graphNodeSize.width);
              const sy = source.y + graphNodeSize.height / 2, ty = target.y + graphNodeSize.height / 2;
              const midpoint = (sx + tx) / 2;
              return <path key={edge.id} d={`M ${sx} ${sy} C ${midpoint} ${sy}, ${midpoint} ${ty}, ${tx} ${ty}`} className={edgeAppearance(edge.type)}><title>{graphEdgeLabels[edge.type]}</title></path>;
            })}</g></svg>
            <div className="og-graph-node-layer" style={{ width: viewport.width, height: viewport.height + 36, transform: `scale(${zoom})` }}>{viewport.nodes.map(node => <button type="button" key={node.id} ref={element => { if (element) nodeRefs.current.set(node.id, element); else nodeRefs.current.delete(node.id); }} style={{ left: node.x, top: node.y + 36 }} className={`og-graph-node ${node.kind}${selected?.id === node.id ? " selected" : ""}`} aria-label={`${graphKindLabels[node.kind]}：${displayNode(node).label}`} title={`${displayNode(node).label} · ${displayNode(node).detail}`} onClick={() => filter("graph_node", node.id)} onKeyDown={event => navigateNode(event, node.id)}><span>{graphKindLabels[node.kind]}</span><strong>{displayNode(node).label}</strong>{node.kind === "evidence" && <small>{displayNode(node).detail}</small>}</button>)}</div>
          </div>
        </div>
        <GraphReadingGuide project={scan.project} resourceLabel={resource.label} sourceLabel={readingEvidence ? `${displayNode(readingEvidence).label} · ${displayNode(readingEvidence).detail}` : null} onReadSource={readingEvidence ? () => filter("graph_node", readingEvidence.id) : undefined} />
        </div>
        {selected && <aside className="og-focused-detail" aria-label="节点详情"><div><span className="og-graph-detail-kind">{graphKindLabels[selected.kind]}</span><h3>{displayNode(selected).label}</h3><p>{selected.kind === "component" || selected.kind === "ai_asset" ? `当前资源连接 ${relatedEdges.length} 条已保存关系；右侧证据节点可打开原文。` : selected.kind === "evidence" ? "以下原文按 Evidence 身份精确读取。" : "此节点是一项扫描观测或规则引用，不代表授权或义务已经履行。"}</p><details><summary>查看技术身份与关系来源</summary><dl><dt>原始标签</dt><dd>{selected.label}</dd><dt>节点</dt><dd>{selected.id}</dd><dt>原始对象</dt><dd>{selected.source_id}</dd></dl><ul>{relatedEdges.map(edge => <li key={edge.id}><strong>{graphEdgeLabels[edge.type]}</strong><small>{edge.source_refs.map(ref => ref.pointer).join("；")}</small></li>)}</ul></details></div><div className="og-focused-evidence">{selected.kind === "evidence" ? <EvidenceReader key={selected.source_id} scan={scan} ids={[selected.source_id]} initialId={selected.source_id} /> : <><strong>关联来源 · {evidenceNodes.length}</strong>{evidenceNodes.length ? evidenceNodes.map(node => <button key={node.id} onClick={() => filter("graph_node", node.id)}><span className="og-graph-evidence-name"><strong>{displayNode(node).label}</strong><small>{displayNode(node).detail}</small></span><span className="og-arrow-button"><span>查看原文</span><ArrowGlyph /></span></button>) : <p>当前后端关系中未提供该资源的证据节点。</p>}</>}</div></aside>}
      </>}
      <p className="og-graph-footnote">关系图是事实视图，许可观测不等于授权结论；未显示的资源仍可通过上方搜索和选择读取。</p><details className="og-graph-provenance"><summary>图谱版本与覆盖身份</summary><p>视图 {view.view_id} · Schema {view.schema_version} · 算法 {view.provenance.algorithm_version}</p><p>后端原图：{view.coverage.node_count} 节点 / {view.coverage.edge_count} 条边 · {view.coverage.scope === "all" ? "全部已有事实" : "后端筛选事实"}</p></details>
    </section>
  </div>;
}
