import { useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Scan } from "../types/domain";
import { Header, Empty, Dialog } from "../components/ui";
import { EvidenceReader } from "../components/EvidenceReader";
export default function Graph({
  scan,
  focus,
  filter,
  openRisk,
}: {
  scan: Scan;
  focus: string;
  filter: (k: string, v: string) => void;
  openRisk: (id: string) => void;
}) {
  const risk = scan.risks.find((r) => r.id === focus) ?? scan.risks[0];
  const [selected, setSelected] = useState<string | null>(null),
    [flow, setFlow] = useState<ReactFlowInstance | null>(null);
  const { nodes, edges } = useMemo(() => {
    if (!risk) return { nodes: [], edges: [] };
    const resource = scan.resources.find((r) => r.id === risk.resourceId);
    const nodes: Node[] = [
      {
        id: "resource",
        position: { x: 0, y: 100 },
        data: { label: resource?.name ?? "资源待补充" },
        className: "og-node-resource",
      },
      {
        id: "risk",
        position: { x: 280, y: 100 },
        data: { label: risk.id + " · " + risk.title },
        className: "og-node-risk",
      },
      ...risk.evidenceIds.map((id, i) => ({
        id,
        position: { x: 600, y: i * 130 },
        data: {
          label:
            id +
            " · " +
            (scan.evidence.find((e) => e.id === id)?.label ?? "证据待补充"),
        },
      })),
    ];
    const edges: Edge[] = [
      { id: "resource-risk", source: "resource", target: "risk" },
      ...risk.evidenceIds.map((id) => ({
        id: "edge-" + id,
        source: "risk",
        target: id,
      })),
    ];
    return {
      nodes: nodes.map((node) => ({
        ...node,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      })),
      edges,
    };
  }, [risk, scan]);
  if (!risk)
    return (
      <Empty
        title="暂无风险路径"
        detail="图谱只展示已提供的关联，不推断新关系。"
      />
    );
  return (
    <>
      <Header
        title="证据关系图谱"
        description="选择风险聚焦关联路径；点击节点打开同一证据阅读器。"
        action={
          <button onClick={() => void flow?.fitView({ padding: 0.25 })}>
            重置视图
          </button>
        }
      />
      <div className="og-filters">
        <label className="og-field">
          当前风险
          <select
            aria-label="当前风险"
            value={risk.id}
            onChange={(e) => {
              filter("focus", e.target.value);
              setSelected(null);
            }}
          >
            {scan.risks.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id} · {r.title}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => openRisk(risk.id)}>打开风险详情 →</button>
      </div>
      <div className="og-flow">
        <ReactFlow
          key={risk.id}
          nodes={nodes}
          edges={edges}
          defaultEdgeOptions={{
            type: "smoothstep",
            style: { stroke: "#8b9ebb", strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: "#8b9ebb" },
          }}
          onInit={setFlow}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          minZoom={0.3}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          onNodeClick={(_, node) => setSelected(node.id)}
          colorMode="dark"
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      <p className="og-muted">
        关系来自 resourceId /
        evidenceIds。鼠标滚轮缩放、拖动空白区域平移；也可使用下方按钮通过键盘打开节点证据。
      </p>
      <div className="og-actions" aria-label="节点证据快捷入口">
        {nodes.map((node) => (
          <button key={node.id} onClick={() => setSelected(node.id)}>
            {String(node.data.label)}
          </button>
        ))}
      </div>
      {selected && (
        <Dialog title="关联证据" onClose={() => setSelected(null)}>
          <EvidenceReader
            key={selected}
            scan={scan}
            ids={
              selected === "resource"
                ? (scan.resources.find((r) => r.id === risk.resourceId)
                    ?.evidenceIds ?? [])
                : risk.evidenceIds
            }
            initialId={selected}
          />
        </Dialog>
      )}
    </>
  );
}
