import { useEffect, useRef, useState } from "react";
import type { Scan } from "./types/domain";
import { useRoute, readRoute, historyPath, scanPath, type Page } from "./hooks/useRoute";
import { useScan } from "./hooks/useScan";
import { createDemo } from "./services/scans";
import { isFixedSourceScan } from "./services/fixedSourceNotice";
import { presentDiagnostic } from "./services/assessmentPresentation";
import {
  NoticeContext,
  Empty,
  StatusBadge,
  Dialog,
  type Notice,
} from "./components/ui";
import { Landing, Brand } from "./pages/Landing";
import { NewScan } from "./pages/NewScan";
import "./pages/NewScan.css";
import "./pages/History.css";
import { Overview } from "./pages/Overview";
import { Progress } from "./pages/Progress";
import { Risks, RiskDetail } from "./pages/Risks";
import { Resources } from "./pages/Resources";
import { Graph } from "./pages/Graph";
import { Remediation } from "./pages/Remediation";
import { ScanDiff } from "./pages/ScanDiff";
import { Assessment } from "./pages/Assessment";
import { ProjectChat } from "./pages/ProjectChat";
import { Assistant } from "./pages/Assistant";
import { Report } from "./pages/Report";
import { ReportV2 } from "./pages/ReportV2";
import "./pages/reportArchive.css";
import { reportNavigationQuery, reportSnapshotQuery } from "./services/reportV2";
import { p2WorkbenchEnabled } from "./services/p2";
import { officialSourcesEnabled } from "./services/officialSources";
import { History } from "./pages/History";
import { accountAuthEnabled, type AccountUser } from './services/auth';
import { NavTooltip } from './components/NavTooltip';
const items: [Page, string][] = [
  ["new-scan", "新建扫描"],
  ["progress", "扫描进度"],
  ["overview", "扫描概览"],
  ["assessment", "项目评估"],
  ["report", "合规报告"],
  ["report-v2", "报告归档与导出"],
  ["history", "扫描历史"],
  ["assistant", "项目智询"],
  ["risks", "风险中心"],
  ["resources", "资源清单"],
  ["graph", "资源关系图"],
  ["remediation", "整改任务"],
  ["diff", "扫描差异"],
];
const navigationIcons: Partial<Record<Page, string>> = {
  "new-scan": "M12 4v16M4 12h16",
  progress: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 7v5l4 2",
  overview: "M4 20V10h4v10M10 20V4h4v16M16 20v-7h4v7",
  assessment: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  report: "M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h5",
  "report-v2": "M5 3h10l4 4v14H5zM14 3v5h5M8 12h8m-8 4h3m3-1 2 2 3-4",
  history: "M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l4 2",
  chat: "M4 4h16v12H9l-5 4V4ZM8 8h8M8 12h5",
  assistant: "M4 4h16v12H9l-5 4V4ZM8 8h8M8 12h5",
  risks: "M12 3 2 21h20ZM12 9v5M12 17v1",
  resources: "M4 3h16v5H4zM4 10h16v5H4zM4 17h16v4H4zM7 5.5h.1M7 12.5h.1M7 19h.1",
  graph: "M3 3h6v6H3zM15 3h6v6h-6zM15 15h6v6h-6zM9 6h6M6 9v9h9",
  remediation: "M9 4h11M9 12h11M9 20h11M3 3l2 2 2-3M3 11l2 2 2-3M3 19l2 2 2-3",
  diff: "M8 3v18M16 3v18M4 7l4-4 4 4M12 17l4 4 4-4",
};
function Icon({ page }: { page: Page }) {
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
      <path d={navigationIcons[page] ?? navigationIcons.overview} />
    </svg>
  );
}
export function App({accountUser,onAccountLogout}:{accountUser?:AccountUser;onAccountLogout?:()=>Promise<void>}={}) {
  const { route, go, filter } = useRoute(),
    { scan, error, loading, reload } = useScan(route.scanId, route.mode);
  const chatMode = route.page === "assistant" || (route.page === "chat" && p2WorkbenchEnabled);
  const [railCompact, setRailCompact] = useState(chatMode);
  const [mobile, setMobile] = useState(false),
    [projecting, setProjecting] = useState(() => {
      try {
        return sessionStorage.getItem("og-projecting") === "1";
      } catch {
        return false;
      }
    });
  const [logoutBusy,setLogoutBusy]=useState(false),[logoutError,setLogoutError]=useState('');
  async function logout(){if(logoutBusy||!onAccountLogout)return;setLogoutBusy(true);setLogoutError('');try{await onAccountLogout();}catch(e){setLogoutError(e instanceof Error?e.message:'退出未完成，请重试。');setLogoutBusy(false);}}
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
    setRailCompact(chatMode);
  }, [route.page, route.scanId, route.riskId]);
  function created(s: Pick<Scan, "id" | "mode">) {
    go(scanPath(s.id, "progress", s.mode));
  }
  function demo() {
    if(accountAuthEnabled){navigate('new-scan');return;}
    try {
      created(createDemo());
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  function navigate(page: string, query = "", riskId?: string) {
    if (page === "assistant") {
      const params = new URLSearchParams({mode:"api"});
      if (route.scanId) params.set("project_scan",route.scanId);
      go("/app/assistant?"+params); return;
    }
    if (!query && page !== "history" && page !== "new-scan") {
      // P2 pins successful writes with replaceState; read the actual URL rather
      // than an earlier hook snapshot so navigation preserves that result.
      const current = readRoute();
      query = reportNavigationQuery(current.scanId, route.scanId, current.query).toString();
    }
    if (page === "history")
      go(historyPath(new URLSearchParams(query)));
    else if (page === "new-scan" || !route.scanId)
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
  function selectAssessment(id: string) {
    const params = new URLSearchParams(route.query);
    if (id !== params.get("assessment_id")) {
      for (const key of ["snapshot_id", "p2_result", "p2_result_id", "p2_revision", "assessment_version", "report_id", "notice_id"]) params.delete(key);
    }
    params.set("assessment_id", id);
    go(scanPath(route.scanId, route.page, route.mode, params));
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
  function navButton([page, label]: [Page, string], compact: boolean) {
    const disabled = !(["new-scan", "history", "assistant"].includes(page)) && !route.scanId;
    return <NavTooltip key={page} label={label} enabled={compact} disabledReason={disabled ? "请先选择或创建扫描任务" : undefined}>
      <button className={page === route.page ? "active" : ""} aria-label={label} title={compact ? undefined : label} aria-current={page === route.page ? "page" : undefined} disabled={disabled} onClick={() => { setMobile(false); setRailCompact(page === "assistant" || page === "chat"); navigate(page); }}><Icon page={page} /><span className="og-nav-label">{label}</span>{page === "risks" && scan && <em>{scan.risks.length}</em>}</button>
    </NavTooltip>;
  }
  const detailPages: Page[] = ["risks", "resources", "graph", "remediation", "diff"];
  function navigation(compact: boolean) {
    return <nav aria-label="工作台导航" className="og-workspace-nav">{compact ? items.map(item => navButton(item, true)) : <>
      <span className="og-nav-group-title">评估主流程</span>{items.filter(([p]) => !detailPages.includes(p) && p !== 'history' && p !== 'assistant').map(item => navButton(item, false))}
      <span className="og-nav-group-title">证据与风险</span>{items.filter(([p]) => detailPages.includes(p)).map(item => navButton(item, false))}
      <span className="og-nav-group-title">辅助工具</span>{items.filter(([p]) => p === 'assistant' || p === 'history').reverse().map(item => navButton(item, false))}
    </>}</nav>;
  }
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
  else if (route.page === "assistant")
    content = <Assistant query={route.query} go={go} username={accountUser?.username} />;
  else if (route.page === "history")
    content = <History query={route.query} go={go} />;
  else if (route.page === "not-found")
    content = (
      <Empty title="页面不存在">
        <button onClick={() => navigate("new-scan")}>新建任务</button>
      </Empty>
    );
  else if (route.page === "diff")
    content = <ScanDiff targetId={route.scanId} mode={route.mode} query={route.query} go={go} />;
  else if (loading)
    content = (
      <Empty
        title="正在读取任务…"
        detail="按任务编号恢复状态，不会创建新任务。"
      />
    );
  else if (error && !scan)
    content = (
      <Empty title="无法读取当前任务" detail={error}>
        <div className="og-actions">
          <button onClick={reload}>重试读取</button>
          {!accountAuthEnabled&&<button onClick={demo}>主动载入演示</button>}
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
        onResults={() => navigate(scan.mode === "api" ? "assessment" : "overview")}
        pollingError={error}
      />
    );
  else if (active)
    content = (
      <Empty title="任务尚未完成" detail="扫描中的数据不会冒充最终结果。">
        <button onClick={() => navigate("progress")}>查看进度</button>
      </Empty>
    );
  else if (scan.mode === "api" && scan.resultsReady === false)
    content = <Empty title="结果尚未就绪" detail={scan.error ?? "任务尚未产生可读取的结果，请查看扫描进度。"}><button onClick={() => navigate("progress")}>查看扫描进度</button></Empty>;
  else if (route.page === "chat" && p2WorkbenchEnabled)
    content = <ProjectChat key={scan.id} scan={scan} query={route.query} go={go} />;
  else if (route.page === "assessment" || route.page === "chat")
    content = (
      <Assessment
        key={scan.mode + scan.id}
        scan={scan}
        query={route.query}
        selectVersion={selectAssessment}
        openResources={() => navigate("resources")}
        initialChatOpen={route.page === "chat"}
      />
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
  else if (route.page === "graph") content = <Graph scan={scan} query={route.query} filter={filter} />;
  else if (route.page === "remediation") content = <Remediation scan={scan} query={route.query} filter={filter} openRisk={id => navigate("risks", "", id)} />;
  else if (route.page === "report") content = <Report key={scan.mode + scan.id} scan={scan} />;
  else if (route.page === "report-v2") content = <ReportV2 key={scan.mode + scan.id} scan={scan} query={route.query} open={(assessmentId, snapshotId) => {
    const current = readRoute();
    const params = reportSnapshotQuery(current.scanId, scan.id, current.query, assessmentId, snapshotId);
    go(scanPath(scan.id, "report-v2", scan.mode, params));
  }} />;
  return (
    <NoticeContext.Provider value={notify}>
      {route.page === "home" ? (
        <Landing onEnter={() => navigate("new-scan")} onDemo={demo} accountMode={accountAuthEnabled} user={accountUser??null} />
      ) : (
        <div className={"og-app og-ui-refined og-workspace-light" + (projecting ? " og-projecting" : "") + (railCompact ? " og-workspace-rail-compact" : "") + (chatMode ? " og-chat-shell" : "")}>
          <a className="og-skip" href="#workspace-main">
            跳到主要内容
          </a>
          <aside className="og-sidebar">
            <Brand onClick={() => go("/")} compact={railCompact} />
            <button className="og-workspace-rail-toggle" aria-label={railCompact ? "展开工作台导航" : "收起工作台导航"} aria-expanded={!railCompact} onClick={() => setRailCompact(v => !v)} title={railCompact ? "展开导航" : "收起导航"}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg></button>
            <div className="og-sidebar-context">
              <span>{route.page === "history" ? "历史视图" : "当前任务"}</span>
              <strong>{route.page === "history" ? "全部扫描任务" : scan?.project ?? "等待输入项目"}</strong>
              <small>{route.page === "history" ? "真实接口 · 只读查询" : route.scanId || "尚未创建"}</small>
            </div>
            {navigation(railCompact)}
            <footer className="og-sidebar-user"><span className="og-user-avatar" aria-hidden="true">{accountUser?.username.slice(0,1).toUpperCase() ?? 'U'}</span><span className="og-user-name">{accountUser?.username ?? '本地工作台'}</span>{accountUser && <button aria-label="退出登录" title="退出登录" onClick={()=>void logout()} disabled={logoutBusy}>{logoutBusy?'…':'退出'}</button>}{logoutError&&<span className="account-logout-error" role="alert">{logoutError}</span>}</footer>
          </aside>
          <div className="og-workspace">
            <header className="og-topbar">
              <button
                className="og-menu"
                aria-label="打开导航"
                aria-haspopup="dialog"
                aria-expanded={mobile}
                onClick={() => setMobile(true)}
              >
                ☰
              </button>
              <strong className="og-breadcrumb"><span>{scan?.project ?? "工作台"} / </span>
                {items.find(([p]) => p === route.page)?.[1] ?? "工作台"}
              </strong>
              <div className="og-actions">
            <details className={"og-mode-banner og-mode-status " + route.mode}><summary>{route.mode === "mock" ? "演示数据" : isFixedSourceScan(scan) ? "真实接口 · 固定快照" : "真实接口"}</summary><div>
              <strong>
                {route.mode === "mock" ? "演示数据" : "真实接口模式"}
              </strong>
              <span>
                {route.mode === "mock"
                  ? "合成快照 · 不代表真实项目扫描结果"
                  : isFixedSourceScan(scan)
                    ? officialSourcesEnabled
                      ? "固定 GitHub 源码快照 · 本次重新扫描 · 官方补证与 Qwen 状态见项目评估"
                      : "固定 GitHub 源码快照 · 本次重新扫描 · 未调用 Qwen3"
                  : p2WorkbenchEnabled && route.page === "assessment"
                    ? "真实扫描数据 · 预生成评估展示稿单独标注来源"
                    : "仅展示接口返回结果 · 失败不会回退演示"}
              </span>
            </div></details>
                {route.page === "assistant" ? (
                  <span>本机 Qwen3</span>
                ) : route.page === "history" ? (
                  <span>只读历史</span>
                ) : scan ? (
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
            <main id="workspace-main" className="og-content">
              {scan?.error && (
                <div
                  className={
                    scan.status === "failed"
                      ? "og-error"
                      : "og-scan-coverage-notice"
                  }
                  role="alert"
                >
                  <strong>
                    {["queued", "running"].includes(scan.status)
                      ? "扫描仍在执行，当前已有覆盖提示。"
                      : scan.status === "partial"
                        ? `扫描部分完成：有 ${scan.diagnostics?.length ?? 1} 项覆盖限制。`
                        : "任务未完整成功。"}
                  </strong>

                  {scan.diagnostics?.length ? (
                    <>
                      <span>
                        已有资源与发现仍可查看，但当前结果不能视为完整覆盖。
                      </span>

                      {route.page !== "assessment" && (
                      <ul className="og-scan-diagnostic-list">
                        {scan.diagnostics.map((diagnostic, index) => {
                          const shown = presentDiagnostic(diagnostic);
                          return (
                            <li key={`${diagnostic.code}-${index}`}>
                              <strong>{shown.title}</strong>
                              <span>{shown.detail}</span>
                            </li>
                          );
                        })}
                      </ul>
                      )}

                      <details className="og-technical-diagnostics">
                        <summary>{route.page === "assessment" ? "查看扫描覆盖说明与技术诊断" : "查看技术诊断"}</summary>
                        {scan.diagnostics.map((diagnostic, index) => (
                          <p
                            key={`${diagnostic.code}-raw-${index}`}
                            style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                          >
                            {route.page === "assessment" && <><strong>{presentDiagnostic(diagnostic).title}</strong><br />{presentDiagnostic(diagnostic).detail}<br /></>}
                            {diagnostic.code}：{diagnostic.message}
                          </p>
                        ))}
                        {route.page === "assessment" && <button onClick={reload}>重新查询</button>}
                      </details>
                    </>
                  ) : (
                    <span>{scan.error}</span>
                  )}

                  {(route.page !== "assessment" || !scan.diagnostics?.length) && <button onClick={reload}>重新查询</button>}
                </div>
              )}
              {content}
            </main>
          </div>
          {mobile && (
            <Dialog title="工作台导航" onClose={() => setMobile(false)}>
              {navigation(false)}
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
