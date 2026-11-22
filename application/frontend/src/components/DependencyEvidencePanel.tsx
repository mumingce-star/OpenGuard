import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { Scan } from "../types/domain";
import { factVerificationLabels, statusLabels } from "../types/domain";
import {
  appendDependencyEvidencePage,
  readDependencyEvidencePage,
  type DependencyConflictSide,
  type DependencyEvidenceFeed,
  type DependencyEvidenceItem,
  type DependencySource,
  type DependencyVersionConflict,
} from "../services/dependencyEvidence";
import { ApiError } from "../services/scans";
import { EvidenceReader, dependencyEvidenceSourceLabels } from "./EvidenceReader";
import { Empty, Panel } from "./ui";
import "./DependencyEvidencePanel.css";

type SourceFilter = DependencySource | "";

const roleLabels = { observed: "已观察", inferred: "推断发现", unknown: "角色未定" };
const conflictLabels = {
  confirmed: "冲突已确认",
  incomplete: "冲突证据不完整",
  ambiguous: "冲突关联不唯一",
};
const gapLabels: Record<string, string> = {
  evidence_reference_missing: "扫描记录中的证据引用缺失",
  source_sha256_missing: "未提供原文件 SHA-256",
  file_path_unavailable: "原始文件路径不可用",
  source_unclassified: "来源类型未能确定",
  version_unavailable: "未提供版本",
  evidence_limit_exceeded: "只返回部分关联证据",
  conflict_limit_exceeded: "只返回部分版本冲突",
  role_evidence_unavailable: "证据不足，无法判定角色",
  conflict_evidence_missing: "扫描记录中的冲突证据缺失",
  conflict_evidence_unbound: "部分冲突证据未绑定到依赖",
  conflict_evidence_incomplete: "关联的冲突证据不完整",
  declaration_side_unavailable: "声明侧无法确定",
  lock_side_unavailable: "锁文件侧无法确定",
  conflict_ambiguous: "证据关联不唯一",
  conflict_side_evidence_limit_exceeded: "一侧证据超过返回上限",
};

function Gaps({ gaps }: { gaps: readonly string[] }) {
  if (!gaps.length) return null;
  return <ul className="og-dependency-gaps" aria-label="证据缺口">
    {gaps.map(gap => <li key={gap} data-gap={gap} title={gap}>{gapLabels[gap] ?? gap}</li>)}
  </ul>;
}

function ConflictSide({ title, side }: { title: string; side: DependencyConflictSide | null }) {
  return <div className="og-dependency-conflict-side">
    <h5>{title} <strong>{side?.version ?? "无法确定"}</strong></h5>
    {side && <>
      <p className="og-muted">{side.incomplete ? "证据不完整" : "证据完整"} · {side.evidence_returned}/{side.evidence_total} 条证据</p>
      <EvidenceReader references={side.evidence} />
    </>}
  </div>;
}

function ConflictDetails({ conflict }: { conflict: DependencyVersionConflict }) {
  return <section className="og-dependency-conflict" data-conflict-status={conflict.status}>
    <h4>{conflictLabels[conflict.status]}</h4>
    <p className="og-muted">版本冲突 · <code>{conflict.code}</code></p>
    <Gaps gaps={conflict.gaps} />
    <div className="og-dependency-conflict-sides">
      <ConflictSide title="声明版本" side={conflict.declaration} />
      <ConflictSide title="锁文件版本" side={conflict.lock} />
    </div>
  </section>;
}

export function DependencyEvidenceDetails({ item, id }: { item: DependencyEvidenceItem; id: string }) {
  const conflictGaps = new Set(item.conflicts.flatMap(conflict => conflict.gaps));
  const evidenceGaps = item.gaps.filter(gap => !conflictGaps.has(gap));
  return <section id={id} className="og-dependency-detail" aria-label={item.name + "的证据详情"}>
    <h3>证据详情 <small>{item.evidence_returned}/{item.evidence_total} 条</small></h3>
    <Gaps gaps={evidenceGaps} />
    <EvidenceReader references={item.evidence} />
    {item.conflicts.length > 0 && <section className="og-dependency-conflicts" aria-label="版本冲突">
      <h3>版本冲突 <small>{item.conflicts_returned}/{item.conflicts_total} 条</small></h3>
      {item.conflicts.map((conflict, index) => item.conflicts.length === 1
        ? <ConflictDetails conflict={conflict} key={index} />
        : <details className="og-dependency-conflict-disclosure" key={index}>
          <summary>{conflictLabels[conflict.status]} · {conflict.declaration?.version ?? "声明未知"} / {conflict.lock?.version ?? "锁定未知"}</summary>
          <ConflictDetails conflict={conflict} />
        </details>)}
    </section>}
  </section>;
}

function DependencyEvidenceRow({ item, expanded, onToggle }: {
  item: DependencyEvidenceItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  const detailId = useId();
  const verification = [...new Set(item.evidence.map(evidence => factVerificationLabels[evidence.verification_status]))];
  return <li>
    <button type="button"
      className={"og-resource-row og-dependency-row" + (expanded ? " is-selected" : "")}
      data-dependency-resource={item.resource_id}
      aria-expanded={expanded}
      aria-controls={expanded ? detailId : undefined}
      onClick={onToggle}>
      <span className="og-dependency-identity"><strong>{item.name}</strong><small>{item.version ?? "版本未提供"}</small></span>
      <span className="og-dependency-sources">
        {item.sources.length ? item.sources.map(source => <span key={source}>{dependencyEvidenceSourceLabels[source]}</span>) : <span>来源未定</span>}
      </span>
      <span className="og-dependency-state">
        <span>{roleLabels[item.role_state]}</span>
        <small>{verification.length ? verification.join("、") : "未提供核验状态"}</small>
        {(item.incomplete || item.conflicts_total > 0) && <span className="og-dependency-warning">
          {item.conflicts_total > 0 && <span>版本冲突</span>}
          {item.incomplete && <span>证据不完整</span>}
        </span>}
      </span>
      <span className="og-dependency-action">{expanded ? "收起证据详情" : "查看证据详情"}</span>
    </button>
    {expanded && <DependencyEvidenceDetails item={item} id={detailId} />}
  </li>;
}

type LoadingState = { feed: DependencyEvidenceFeed | null; loading: boolean; error: string | null };

const initialState: LoadingState = { feed: null, loading: true, error: null };

function describeError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "dependency_evidence_cursor_stale" || error.code === "dependency_evidence_cursor_invalid") {
      return "当前分页已失效，请从第一页重新读取。";
    }
    if (error.status === 401) return "登录后可读取本次扫描的依赖证据。";
    if (error.status === 403 || error.status === 404) return "扫描不存在、当前账户无权查看或证据接口不可用。";
    return "无法读取依赖证据（HTTP " + error.status + "）。";
  }
  return error instanceof Error ? error.message : "无法读取依赖证据。";
}

function DependencyEvidenceFeedPanel({ scanId, status, revision }: {
  scanId: string;
  status: "completed" | "partial";
  revision?: string | null;
}) {
  const [source, setSource] = useState<SourceFilter>("");
  const [state, setState] = useState<LoadingState>(initialState);
  const [selected, setSelected] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);

  const load = useCallback(async (previous: DependencyEvidenceFeed | null) => {
    const cursor = previous?.next_cursor ?? null;
    if (previous && !cursor) return;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setState({ feed: previous, loading: true, error: null });
    try {
      const page = await readDependencyEvidencePage(scanId, {
        source: source || undefined,
        cursor: cursor ?? undefined,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (page.scan_ref.status !== status || (revision !== undefined && page.scan_ref.revision !== revision)) {
        setSelected(null);
        setState({ feed: null, loading: false, error: "扫描身份已变化，请重新打开本次扫描。" });
        return;
      }
      const feed = appendDependencyEvidencePage(previous, page, cursor);
      setState({ feed, loading: false, error: null });
    } catch (error) {
      if (controller.signal.aborted) return;
      const stale = error instanceof ApiError
        && (error.code === "dependency_evidence_cursor_stale" || error.code === "dependency_evidence_cursor_invalid");
      if (stale) setSelected(null);
      setState({ feed: stale ? null : previous, loading: false, error: describeError(error) });
    }
  }, [scanId, revision, source, status]);

  useEffect(() => {
    void load(null);
    return () => active.current?.abort();
  }, [load]);

  const { feed, loading, error } = state;
  return <section className="og-dependency-evidence" aria-label="依赖与证据" data-dependency-evidence
    data-dependency-scan-status={status} aria-busy={loading} id="dependency-evidence">
    <Panel title="依赖与证据" caption={statusLabels[status]} action={
      <label className="og-field og-dependency-source-filter">
        依赖来源
        <select value={source} onChange={event => {
          const next = event.target.value as SourceFilter;
          if (next === source) return;
          active.current?.abort();
          setSelected(null);
          setState(initialState);
          setSource(next);
        }}>
          <option value="">全部来源</option>
          {Object.entries(dependencyEvidenceSourceLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
        </select>
      </label>
    }>
      {feed && <div className="og-dependency-summary" aria-live="polite">
        <span>已显示 {feed.items.length} / {feed.total} 项</span>
        {feed.incomplete && <span className="og-dependency-warning">本次返回存在证据缺口</span>}
      </div>}
      {loading && !feed && <p className="og-dependency-message" role="status">正在读取依赖证据…</p>}
      {error && <div className="og-dependency-error" role="alert">
        <span>{error}</span>
        <button type="button" onClick={() => {
          setSelected(null);
          void load(null);
        }}>重新读取依赖证据</button>
      </div>}
      {feed && !feed.items.length && <Empty
        title={source ? "此来源没有匹配的依赖" : "本次扫描没有返回依赖"}
        detail={source ? "可选择其他来源查看。" : status === "partial" ? "扫描部分完成，未返回的依赖情况仍待核对。" : undefined}
      />}
      {feed && feed.items.length > 0 && <>
        <div className="og-resource-head og-dependency-head" aria-hidden="true">
          <span>名称 / 版本</span><span>来源</span><span>角色 / 核验状态</span><span>证据</span>
        </div>
        <ul className="og-resource-list og-dependency-list">
          {feed.items.map(item => <DependencyEvidenceRow item={item} key={item.resource_id}
            expanded={selected === item.resource_id}
            onToggle={() => setSelected(current => current === item.resource_id ? null : item.resource_id)}
          />)}
        </ul>
        {feed.next_cursor !== null && <footer className="og-v3-panel-foot">
          <button type="button" disabled={loading} onClick={() => void load(feed)}>
            {loading ? "正在加载更多…" : error ? "重试加载更多" : "加载更多依赖"}
          </button>
        </footer>}
      </>}
    </Panel>
  </section>;
}

export function DependencyEvidencePanel({ scan }: { scan: Scan }) {
  if (scan.mode !== "api" || (scan.status !== "completed" && scan.status !== "partial")) return null;
  return <DependencyEvidenceFeedPanel key={JSON.stringify([scan.id, scan.status, scan.revision, scan.finishedAt])}
    scanId={scan.id} status={scan.status} revision={scan.revision} />;
}
