import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { Scan } from "./types/domain";
import { useRoute, scanPath, type Page } from "./hooks/useRoute";
import { useScan } from "./hooks/useScan";
import { createDemo } from "./services/scans";
import {
  NoticeContext,
  Empty,
  StatusBadge,
  Dialog,
  type Notice,
} from "./components/ui";
import { Landing, Brand } from "./pages/Landing";
import { NewScan } from "./pages/NewScan";
import { Overview } from "./pages/Overview";
import { Progress } from "./pages/Progress";
import { Risks, RiskDetail } from "./pages/Risks";
import { Resources } from "./pages/Resources";
import { Report } from "./pages/Report";
const Graph = lazy(() => import("./pages/Graph"));
const items: [Page, string][] = [
  ["new-scan", "新建扫描"],
  ["overview", "扫描概览"],
  ["progress", "扫描进度"],
  ["risks", "风险中心"],
  ["resources", "资源清单"],
  ["graph", "证据图谱"],
  ["report", "合规报告"],
];
function Icon({ index }: { index: number }) {
  const paths = [
    "M12 4v16M4 12h16",
    "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    "M12 3a9 9 0 1 0 9 9M12 7v5l4 2",
    "M12 3 2 21h20ZM12 9v5M12 17v1",
    "M5 3h14v18H5zM8 8h8M8 12h8M8 16h5",
    "M4 4h5v5H4zM15 15h5v5h-5zM15 4h5v5h-5zM9 6h6M6 9v9h9",
    "M5 3h10l4 4v14H5zM8 11h8M8 15h8",
  ];
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[index]} />
    </svg>
  );
}
export function App() {
  const { route, go, filter } = useRoute(),
    { scan, error, loading, reload } = useScan(route.scanId, route.mode);
  const [mobile, setMobile] = useState(false),
    [projecting, setProjecting] = useState(() => {
      try {
        return sessionStorage.getItem("og-projecting") === "1";
      } catch {
        return false;
      }
    });
  const [notice, setNotice] = useState<{
      message: string;
      tone: string;
      retry?: () => void;
    } | null>(null),
    timer = useRef<number | undefined>(undefined);
  const notify: Notice = (message, tone = "success", retry) => {
    clearTimeout(timer.current);
    setNotice({ message, tone, retry });
    if (tone === "success")
      timer.current = window.setTimeout(() => setNotice(null), 5000);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    setMobile(false);
  }, [route.page, route.scanId]);
  function created(s: Scan) {
    go(scanPath(s.id, "progress", s.mode));
  }
  function demo() {
    try {
      created(createDemo());
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  function navigate(page: string, query = "", riskId?: string) {
    if (page === "new-scan" || !route.scanId)
      go("/app/new-scan?mode=" + route.mode);
    else
      go(
        scanPath(
          route.scanId,
          page as Page,
          route.mode,
          new URLSearchParams(query),
          riskId,
        ),
      );
  }
  function toggleProjection() {
    setProjecting((v) => {
      try {
        sessionStorage.setItem("og-projecting", v ? "0" : "1");
      } catch {
        /* session only */
      }
      return !v;
    });
  }
  const nav = (
    <nav aria-label="工作台导航">
      {items.map(([page, label], i) => (
        <button
          key={page}
          className={page === route.page ? "active" : ""}
          aria-current={page === route.page ? "page" : undefined}
          disabled={page !== "new-scan" && !route.scanId}
          onClick={() => {
            setMobile(false);
            navigate(page);
          }}
        >
          <Icon index={i} />
          {label}
          {page === "risks" && scan && <em>{scan.risks.length}</em>}
        </button>
      ))}
    </nav>
  );
  const active = scan && ["queued", "running"].includes(scan.status);
  let content;
  if (route.page === "new-scan")
    content = (
      <NewScan
        key={route.mode}
        mode={route.mode}
        onMode={(mode) => go("/app/new-scan?mode=" + mode)}
        onCreated={created}
      />
    );
  else if (route.page === "not-found")
    content = (
      <Empty title="页面不存在">
        <button onClick={() => navigate("new-scan")}>新建任务</button>
      </Empty>
    );
  else if (loading)
    content = (
      <Empty
        title="正在读取任务…"
        detail="按任务编号恢复状态，不会创建新任务。"
      />
    );
  else if (error)
    content = (
      <Empty title="无法读取当前任务" detail={error}>
        <div className="og-actions">
          <button onClick={reload}>重试读取</button>
          <button onClick={demo}>主动载入演示</button>
          <button onClick={() => navigate("new-scan")}>返回新建扫描</button>
        </div>
      </Empty>
    );
  else if (!scan)
    content = (
      <Empty title="尚未选择扫描任务">
        <button onClick={() => navigate("new-scan")}>新建扫描</button>
      </Empty>
    );
  else if (route.page === "progress")
    content = (
      <Progress
        scan={scan}
        reload={reload}
        onResults={() => navigate("overview")}
      />
    );
  else if (active)
    content = (
      <Empty title="任务尚未完成" detail="扫描中的数据不会冒充最终结果。">
        <button onClick={() => navigate("progress")}>查看进度</button>
      </Empty>
    );
  else if (route.page === "overview")
    content = <Overview scan={scan} go={navigate} />;
  else if (route.page === "risks")
    content = route.riskId ? (
      <RiskDetail
        key={scan.id + route.riskId}
        scan={scan}
        riskId={route.riskId}
        reload={reload}
        back={() =>
          go(scanPath(scan.id, "risks", scan.mode, route.query), true)
        }
        graph={() =>
          navigate("graph", "focus=" + encodeURIComponent(route.riskId))
        }
      />
    ) : (
      <Risks
        scan={scan}
        query={route.query}
        filter={filter}
        open={(id) =>
          go(scanPath(scan.id, "risks", scan.mode, route.query, id))
        }
      />
    );
  else if (route.page === "resources")
    content = (
      <Resources
        scan={scan}
        query={route.query}
        filter={filter}
        openRisk={(id) => navigate("risks", "", id)}
      />
    );
  else if (route.page === "graph")
    content = (
      <Suspense fallback={<Empty title="正在载入图谱…" />}>
        <Graph
          scan={scan}
          focus={route.query.get("focus") ?? ""}
          filter={filter}
          openRisk={(id) => navigate("risks", "", id)}
        />
      </Suspense>
    );
  else if (route.page === "report") content = <Report scan={scan} />;
  return (
    <NoticeContext.Provider value={notify}>
      {route.page === "home" ? (
        <Landing onEnter={() => navigate("new-scan")} onDemo={demo} />
      ) : (
        <div className={"og-app" + (projecting ? " og-projecting" : "")}>
          <a className="og-skip" href="#workspace-main">
            跳到主要内容
          </a>
          <aside className="og-sidebar">
            <Brand onClick={() => go("/")} />
            <div className="og-sidebar-context">
              <span>当前任务</span>
              <strong>{scan?.project ?? "等待输入项目"}</strong>
              <small>{route.scanId || "尚未创建"}</small>
            </div>
            {nav}
            <footer>
              证据先行，结论可溯
              <br />
              合规信息整理 · 非法律意见
            </footer>
          </aside>
          <div className="og-workspace">
            <header className="og-topbar">
              <button
                className="og-menu"
                aria-label="打开导航"
                onClick={() => setMobile(true)}
              >
                ☰
              </button>
              <strong>
                {items.find(([p]) => p === route.page)?.[1] ?? "工作台"}
              </strong>
              <div className="og-actions">
                {scan ? (
                  <StatusBadge status={scan.status} />
                ) : (
                  <span>
                    {loading ? "读取中" : error ? "读取失败" : "未扫描"}
                  </span>
                )}
                <button aria-pressed={projecting} onClick={toggleProjection}>
                  {projecting ? "退出投屏" : "投屏模式"}
                </button>
              </div>
            </header>
            <div className={"og-mode-banner " + route.mode}>
              <strong>
                {route.mode === "mock" ? "演示数据" : "真实接口模式"}
              </strong>
              <span>
                {route.mode === "mock"
                  ? "合成快照 · 不代表真实项目扫描结果"
                  : "仅展示接口返回结果 · 失败不会回退演示"}
              </span>
            </div>
            <main id="workspace-main" className="og-content">
              {scan?.error && (
                <div className="og-error" role="alert">
                  <strong>任务未完整成功：</strong>
                  {scan.error} <button onClick={reload}>重新查询</button>
                </div>
              )}
              {content}
            </main>
          </div>
          {mobile && (
            <Dialog title="工作台导航" onClose={() => setMobile(false)}>
              {nav}
            </Dialog>
          )}
        </div>
      )}
      {notice && (
        <div
          className={"og-toast " + notice.tone}
          role={notice.tone === "error" ? "alert" : "status"}
        >
          <span>{notice.message}</span>
          {notice.retry && <button onClick={notice.retry}>重试</button>}
          <button aria-label="关闭提示" onClick={() => setNotice(null)}>
            ×
          </button>
        </div>
      )}
    </NoticeContext.Provider>
  );
}
