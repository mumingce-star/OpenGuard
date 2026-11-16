import type { PositionedGraphNode } from "../types/p1Graph";
import { graphNodeSize } from "../services/p1Graph";

type Layout = { nodes: PositionedGraphNode[]; width: number; height: number };
/** Visual coordinates only: graph identities, relationships and source references are unchanged. */
export function fitResourceGraph(layout: Layout, box: { width: number; height: number }, manualScale: number | null = null) {
  const padding = 18, heading = 36, margin = 26;
  const width = Math.max(1, layout.width), height = Math.max(graphNodeSize.height + margin * 2, layout.height);
  const availableWidth = Math.max(1, box.width - padding * 2), availableHeight = Math.max(1, box.height - padding * 2);
  const measured = box.width > padding * 2 && box.height > padding * 2;
  // On very narrow screens keep labels readable; overflow remains scrollable inside the canvas.
  const fitted = measured ? Math.max(.65, Math.min(1.25, availableWidth / width, availableHeight / (height + heading))) : .85;
  const scale = manualScale !== null && Number.isFinite(manualScale) && manualScale > 0 ? manualScale : fitted;
  const contentHeight = measured ? Math.max(height, availableHeight / scale - heading) : height;
  const span = height - margin * 2 - graphNodeSize.height;
  const extra = contentHeight - height;
  const nodes = layout.nodes.map(node => ({ ...node, y: span > 0 ? margin + (node.y - margin) * (span + extra) / span : node.y + extra / 2 }));
  return {
    nodes, width, height: contentHeight, scale, fittedScale: fitted,
    offsetX: measured ? Math.max(padding, (box.width - width * scale) / 2) : 0,
    offsetY: padding,
    auto: manualScale === null,
  };
}
