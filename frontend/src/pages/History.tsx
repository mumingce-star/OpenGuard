import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { Empty, Header, StatusBadge } from "../components/ui";
import { historyPath, scanPath } from "../hooks/useRoute";
import {
  getHistory,
  historyQueryFromSearch,
  historySearch,
  historyTarget,
} from "../services/p1History";
import { statusLabels, type ScanStatus } from "../types/domain";
import type {
  HistoryPage,
  HistoryQuery,
  HistorySourceType,
  ScanHistoryItem,
} from "../types/p1History";

const sourceLabels: Record<HistorySourceType, string> = {
  git: "Git 仓库",
  zip: "ZIP 上传",
  local: "本地来源",
};

const stageLabels: Record<ScanHistoryItem["stage"], string> = {
  queued: "等待调度",
  ingestion: "安全接收",
  inventory: "文件清单",
  scan: "扫描分析",
  normalize: "事实归一",
  rules: "规则判断",
  ai_assist: "AI 辅助",
  report: "报告生成",
  completed: "全部完成",
};

function formatTime(value: string | null) {
  if (!value) return "尚未完成";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function shortRevision(value: string | null) {
  return value ? value.slice(0, 12) : "未提供 revision";
}

function itemLabel(item: ScanHistoryItem) {
  return item.project_identity.method === "canonical_github_repo_v1"
    ? item.project_identity.key.replace(/^github\.com\//, "")
    : item.source;
}

function HistoryRow({ item, open }: { item: ScanHistoryItem; open: () => void }) {
  const partial = item.status === "partial";
  const activate = (event: KeyboardEvent<HTMLLIElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  };
  return (
    <li
      className={`og-history-row ${item.status}`}
      tabIndex={0}
      role="link"
      aria-label={`打开扫描 ${itemLabel(item)}`}
      onClick={open}
      onKeyDown={activate}
    >
      <div className="og-history-project">
        <div className="og-history-row-title">
          <strong>{itemLabel(item)}</strong>
          <span className="og-badge">{sourceLabels[item.source_type]}</span>
        </div>
        <span>{item.source}</span>
        <small>
          {shortRevision(item.revision)} · {item.project_identity.key}
        </small>
      </div>

      <div className="og-history-status">
        <StatusBadge status={item.status} />
        <span>{stageLabels[item.stage]}</span>
        {partial && <small>已有结果可查看，覆盖范围不完整</small>}
      </div>

      <div className="og-history-time">
        <span>创建 {formatTime(item.created_at)}</span>
        <small>完成 {formatTime(item.finished_at)}</small>
      </div>

      <div className="og-history-counts" aria-label="扫描事实数量">
        <span><strong>{item.component_count}</strong>组件</span>
        <span><strong>{item.ai_asset_count}</strong>AI 资源</span>
        <span><strong>{item.finding_count}</strong>待核查线索</span>
      </div>

      <div className="og-history-assessment">
        {item.latest_assessment ? (
          <>
            <strong>正式评估 v{item.latest_assessment.version}</strong>
            <small>{item.latest_assessment.assessment_id}</small>
          </>
        ) : (
          <>
            <strong>尚无正式评估</strong>
            <small>只读查看不会自动创建</small>
          </>
        )}
      </div>

      <button
        type="button"
        className="og-history-open"
        onClick={(event) => {
          event.stopPropagation();
          open();
        }}
      >
        打开任务 <span aria-hidden="true">→</span>
      </button>
    </li>
  );
}

export function History({
  query,
  go,
}: {
  query: URLSearchParams;
  go: (url: string, restore?: boolean) => void;
}) {
  const queryKey = query.toString();
  const parsed = useMemo(() => {
    try {
      return { value: historyQueryFromSearch(new URLSearchParams(queryKey)), error: null };
    } catch (error) {
      return {
        value: null,
        error: error instanceof Error ? error.message : "历史查询链接无效。",
      };
    }
  }, [queryKey]);
  const [result, setResult] = useState<HistoryPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [draft, setDraft] = useState(() => ({
    q: query.get("q") ?? "",
    status: query.get("status") ?? "",
    sourceType: query.get("source_type") ?? "",
    projectKey: query.get("project_key") ?? "",
    limit: query.get("limit") ?? "20",
  }));

  useEffect(() => {
    setDraft({
      q: query.get("q") ?? "",
      status: query.get("status") ?? "",
      sourceType: query.get("source_type") ?? "",
      projectKey: query.get("project_key") ?? "",
      limit: query.get("limit") ?? "20",
    });
  }, [queryKey]);

  useEffect(() => {
    if (!parsed.value) {
      setResult(null);
      setError(parsed.error);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getHistory(parsed.value, controller.signal)
      .then((page) => {
        if (!controller.signal.aborted) setResult(page);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setResult(null);
          setError(reason instanceof Error ? reason.message : "读取扫描历史失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [parsed.value, parsed.error, revision]);

  function apply(event: FormEvent) {
    event.preventDefault();
    const next: HistoryQuery = {
      limit: Number(draft.limit),
      ...(draft.status ? { status: draft.status as ScanStatus } : {}),
      ...(draft.sourceType ? { sourceType: draft.sourceType as HistorySourceType } : {}),
      ...(draft.q.trim() ? { q: draft.q.trim() } : {}),
      ...(draft.projectKey.trim() ? { projectKey: draft.projectKey.trim() } : {}),
    };
    go(historyPath(historySearch(next)));
  }

  function open(item: ScanHistoryItem) {
    const target = historyTarget(item);
    const detailQuery = new URLSearchParams();
    if (target.assessmentId) detailQuery.set("assessment_id", target.assessmentId);
    go(scanPath(item.scan_id, target.page, "api", detailQuery));
  }

  const activeFilters = [
    parsed.value?.q && `搜索：${parsed.value.q}`,
    parsed.value?.status && `状态：${statusLabels[parsed.value.status]}`,
    parsed.value?.sourceType && `来源：${sourceLabels[parsed.value.sourceType]}`,
    parsed.value?.projectKey && `项目：${parsed.value.projectKey}`,
  ].filter(Boolean) as string[];

  return (
    <section className="og-history">
      <Header
        eyebrow="OPENGUARD / HISTORY"
        title="扫描历史"
        description="按服务端稳定顺序查看真实扫描记录；本页只读，不会启动扫描、生成评估或调用 AI。"
        action={
          <button type="button" onClick={() => setRevision((value) => value + 1)} disabled={loading}>
            {loading ? "读取中…" : "刷新记录"}
          </button>
        }
      />

      <form className="og-panel og-history-filters" onSubmit={apply}>
        <div className="og-history-filter-grid">
          <label className="og-field og-history-search">
            搜索公开项目或仓库
            <input
              value={draft.q}
              onChange={(event) => setDraft((value) => ({ ...value, q: event.target.value }))}
              placeholder="例如 openai 或 github.com/owner/repo"
            />
          </label>
          <label className="og-field">
            扫描状态
            <select value={draft.status} onChange={(event) => setDraft((value) => ({ ...value, status: event.target.value }))}>
              <option value="">全部状态</option>
              <option value="queued">等待中</option>
              <option value="running">执行中</option>
              <option value="completed">已完成</option>
              <option value="partial">扫描部分完成</option>
              <option value="failed">失败</option>
              <option value="cancelled">已取消</option>
            </select>
          </label>
          <label className="og-field">
            来源类型
            <select value={draft.sourceType} onChange={(event) => setDraft((value) => ({ ...value, sourceType: event.target.value }))}>
              <option value="">全部来源</option>
              <option value="git">Git 仓库</option>
              <option value="zip">ZIP 上传</option>
              <option value="local">本地来源</option>
            </select>
          </label>
          <label className="og-field">
            项目标识
            <input
              value={draft.projectKey}
              onChange={(event) => setDraft((value) => ({ ...value, projectKey: event.target.value }))}
              placeholder="精确 project_key"
            />
          </label>
          <label className="og-field og-history-limit">
            每批数量
            <select value={draft.limit} onChange={(event) => setDraft((value) => ({ ...value, limit: event.target.value }))}>
              <option value="20">20 条</option>
              <option value="50">50 条</option>
              <option value="100">100 条</option>
            </select>
          </label>
        </div>
        <div className="og-history-filter-actions">
          <div className="og-history-filter-summary" aria-live="polite">
            {activeFilters.length ? activeFilters.map((filter) => <span key={filter}>{filter}</span>) : <small>当前未限制筛选条件</small>}
          </div>
          <div className="og-actions">
            <button type="button" onClick={() => go(historyPath())}>重置筛选</button>
            <button type="submit" className="og-primary">应用筛选</button>
          </div>
        </div>
      </form>

      <div className="og-history-list-heading">
        <div>
          <strong>{result ? `当前批次 ${result.items.length} 条` : "真实扫描记录"}</strong>
          <small>排序：创建时间从新到旧，同一时间按扫描编号升序</small>
        </div>
        {parsed.value?.cursor && <span className="og-badge">已恢复分页位置</span>}
      </div>

      {loading ? (
        <div className="og-history-loading" role="status" aria-live="polite">
          <span /><span /><span />
          <p>正在读取真实历史记录…</p>
        </div>
      ) : error ? (
        <Empty title="无法读取扫描历史" detail={error}>
          <div className="og-actions">
            <button onClick={() => setRevision((value) => value + 1)}>重试读取</button>
            <button onClick={() => go(historyPath())}>返回筛选首页</button>
          </div>
        </Empty>
      ) : result && result.items.length === 0 ? (
        <Empty
          title={activeFilters.length ? "没有符合条件的扫描" : "还没有扫描记录"}
          detail={activeFilters.length ? "可以调整筛选条件后重试；空结果不代表任务失败。" : "创建首个真实扫描后，记录会出现在这里。"}
        >
          <div className="og-actions">
            {activeFilters.length > 0 && <button onClick={() => go(historyPath())}>清除筛选</button>}
            <button className="og-primary" onClick={() => go("/app/new-scan?mode=api")}>新建扫描</button>
          </div>
        </Empty>
      ) : result ? (
        <ol className="og-history-list">
          {result.items.map((item) => <HistoryRow key={item.scan_id} item={item} open={() => open(item)} />)}
        </ol>
      ) : null}

      {result && result.items.length > 0 && (
        <nav className="og-history-pagination" aria-label="历史记录分页">
          <div>
            <strong>游标分页</strong>
            <small>服务端不提供总页数；使用浏览器返回可回到上一批记录。</small>
          </div>
          <div className="og-actions">
            {parsed.value?.cursor && (
              <button
                type="button"
                onClick={() => {
                  const first = new URLSearchParams(queryKey);
                  first.delete("cursor");
                  go(historyPath(first));
                }}
              >
                返回筛选首页
              </button>
            )}
            <button
              type="button"
              className="og-primary"
              disabled={!result.next_cursor}
              onClick={() => {
                const next = new URLSearchParams(queryKey);
                next.set("cursor", result.next_cursor!);
                go(historyPath(next));
              }}
            >
              {result.next_cursor ? "下一批记录" : "已到最后一批"}
            </button>
          </div>
        </nav>
      )}
    </section>
  );
}
