import { UsageForm } from "../components/UsageForm";
import { readOnlyPreview } from "../services/assessmentFeedback";
import { fixedSourceNotice } from "../services/fixedSourceNotice";
import { emptyUsage, presets, usageFields } from "../services/assessments";
import { useRef, useState, useEffect } from "react";
import type { Mode, Scan, ScanInput } from "../types/domain";
import {
  createApiScan,
  createDemo,
  zipLimit,
} from "../services/scans";
import { validateGithub, validateZip } from "../services/model";
import { scenarios, type Scenario } from "../mocks/data";
import { ActionButton, SegmentedControl, useNotice } from "../components/ui";
import { markNewScanForProgress } from "../services/scanProgressEntry";
import { accountAuthEnabled } from '../services/auth';

function InputIcon({ kind }: { kind: "repository" | "upload" | "archive" | "info" }) {
  const paths = {
    repository: "M6 3v12a3 3 0 0 0 3 3h6M6 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM18 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM6 9h6a6 6 0 0 1 6 6",
    upload: "M12 16V3m-5 5 5-5 5 5M4 14v6a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6",
    archive: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M10 4h1m0 3h1m-2 3h1m0 3h1m-2 3h2v3h-2Z",
    info: "M12 8h.01M12 11v6M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={paths[kind]} />
    </svg>
  );
}
export function NewScan({
  mode,
  onMode,
  onCreated,
}: {
  mode: Mode;
  onMode: (mode: Mode) => void;
  onCreated: (scan: Pick<Scan, "id" | "mode">) => void;
}) {
  const [tab, setTab] = useState<"github" | "zip">("zip"),
    [url, setUrl] = useState(""),
    [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [usage, setUsage] = useState(emptyUsage);
  const [confirmedInput,setConfirmedInput]=useState<ScanInput|null>(null);
  const active=useRef(true),revision=useRef(0),confirmationRef=useRef<ScanInput|null>(null);
  useEffect(()=>{active.current=true;return()=>{active.current=false;};},[]);
  // The current scan HTTP contract has no material-retention option.
  const resolveLocal = false;
  const [scenario, setScenario] = useState<Scenario>("standard");
  const picker = useRef<HTMLInputElement>(null),
    lock = useRef(false),
    requestId = useRef(crypto.randomUUID());
  const notify = useNotice();
  function changed() {
    revision.current++;confirmationRef.current=null;setConfirmedInput(null);
    setError("");
    requestId.current = crypto.randomUUID();
  }
  function select(f: File | null) {
    if(lock.current)return;
    setFile(f);
    changed();
    setError(validateZip(f, zipLimit) ?? "");
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (lock.current) return;
    if(accountAuthEnabled&&mode!=='api'){setError('账号工作台仅支持真实扫描，请重新打开新建扫描。');return;}
    setError("");
    const problem =
      tab === "github" ? validateGithub(url) : validateZip(file, zipLimit);
    if (problem) {
      setError(problem);
      return;
    }
    if(mode==='api'&&!confirmedInput){
      const frozen=Object.freeze({kind:tab,url,file:file??undefined,usage:Object.freeze({...usage}),resolveLocalMaterials:resolveLocal});
      confirmationRef.current=frozen;setConfirmedInput(frozen);
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => document.getElementById("scan-confirmation")?.scrollIntoView({ block: "center", behavior: "smooth" }));
      return;
    }
    if(mode==='api'&&confirmedInput!==confirmationRef.current)return;
    if(mode==='api'&&readOnlyPreview){setError('只读预览不能开始扫描；确认摘要仅供查看。');return;}
    const token=revision.current;
    lock.current = true;
    setBusy(true);
    try {
      const input: ScanInput = confirmedInput??{
        kind: tab,
        url,
        file: file ?? undefined,
        ...(mode === "api" ? { usage, resolveLocalMaterials: resolveLocal } : {}),
      };
      const created=mode==='mock'?createDemo(scenario):await createApiScan(input,requestId.current);
      if(active.current&&revision.current===token){markNewScanForProgress(created);onCreated(created);}
    } catch (e) {
      if(active.current&&revision.current===token)setError(e instanceof Error ? e.message : "任务提交结果尚未确认，请先读取状态，不要重复提交。");
    } finally {
      lock.current = false;
      if(active.current)setBusy(false);
    }
  }
  function demo() {
    if(accountAuthEnabled)return;
    try {
      const created=createDemo(scenario);markNewScanForProgress(created);onCreated(created);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  return (
    <div className="og-new-scan">
      <header className="og-scan-heading">
        <div className="og-scan-introduction">
          <h1>导入项目源码与用途声明</h1>
          <p>选择待扫描的代码仓库或压缩包，填写七项预期用途作为评估基线。</p>
        </div>
        <div className="og-scan-mode">
          {!accountAuthEnabled&&<div className="og-mode-switch" aria-label="数据模式">
            <button
              disabled={busy}
              aria-pressed={mode === "mock"}
              onClick={() => {
                changed();
                onMode("mock");
              }}
            >
              演示模式
            </button>
            <button
              disabled={busy}
              aria-pressed={mode === "api"}
              onClick={() => {
                changed();
                onMode("api");
              }}
            >
              真实接口
            </button>
          </div>}
          <p className="og-mode-note">
            {mode === "mock"
              ? "演示数据 · 不联网，不读取你的仓库或 ZIP，只播放固定合成快照。"
              : "真实接口 · 地址校验、扫描和文件安全检查由后端执行。失败不会切换为演示结果。"}
          </p>
        </div>
      </header>
      <form onSubmit={submit} noValidate>
        <section className="og-panel og-scan-composer" aria-label="扫描输入与用途"><div className="og-v3-scan-source"><h2 className="og-v3-panel-title">1. 扫描来源与快照</h2>
          <SegmentedControl label="扫描输入方式" value={tab} disabled={busy} onChange={value => { setTab(value); setDragging(false); changed(); }} options={[{ value: 'github', label: <><InputIcon kind="repository" /> GitHub 仓库</> }, { value: 'zip', label: <><InputIcon kind="upload" /> 上传 ZIP</> }]} />
          {tab === "github" ? (
            <div className="og-form-section">
              <label className="og-field og-floating-field">
                <input
                  disabled={busy}
                  type="url"
                  placeholder="https://github.com/owner/repository"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    changed();
                  }}
                  aria-invalid={!!error}
                  aria-describedby="scan-error"
                />
                <span>公开仓库地址</span>
              </label>
              {mode === 'api' && fixedSourceNotice ? <details className="og-fixed-source"><summary>固定 GitHub 版本 · 查看扫描来源</summary><aside className="og-info" role="note">
                <strong>固定 GitHub 版本 · 真实重新扫描</strong>
                <p>本录制入口读取已安全获取的源码快照，每次重新解析资源并保存新结果；不复用历史扫描结论，也不依赖现场网络抓取。</p>
                <p>{fixedSourceNotice.source}<br/>提交：<code>{fixedSourceNotice.revision}</code></p>
              </aside></details> : <p className="og-muted">公开 Git 需由服务管理员启用；提交时由后端校验。</p>}
            </div>
          ) : (
            <div className="og-form-section">
              <div
                className={`og-drop-zone ${dragging ? "is-dragging" : ""}`}
                onDragEnter={() => { if (!busy) setDragging(true); }}
                onDragOver={(e) => e.preventDefault()}
                onDragLeave={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
                }}
                aria-busy={busy}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  if (!busy) select(e.dataTransfer.files[0] ?? null);
                }}
              >
                <div className="og-upload-symbol"><InputIcon kind="archive" /></div>
                <strong>{file ? file.name : dragging ? "松开即可选择此 ZIP" : "拖放 ZIP 文件到这里"}</strong>
                <p>
                  {file
                    ? (file.size / 1024 / 1024).toFixed(2) + " MB"
                    : "只做格式与大小预检，不在浏览器解压或执行项目"}
                </p>
                <input
                  ref={picker}
                  type="file"
                  accept=".zip,application/zip"
                  hidden
                  onChange={(e) => {
                    select(e.target.files?.[0] ?? null);
                    e.target.value = "";
                  }}
                />
                <div className="og-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => picker.current?.click()}
                  >
                    {file ? "重新选择" : "选择 ZIP 文件"}
                  </button>
                  {file && (
                    <ActionButton
                      kind="remove"
                      disabled={busy}
                      onClick={() => {
                        setFile(null);
                        changed();
                      }}
                    >
                      移除文件
                    </ActionButton>
                  )}
                </div>
              </div>
              <p className="og-muted">
                {zipLimit
                  ? "已配置上限：" + zipLimit / 1024 / 1024 + " MB"
                  : "上传大小与解压安全限制由后端检查。"}
              </p>
            </div>
          )}
        <div className="og-v3-pipelines"><h3>默认启用分析管道</h3><p>依赖树与锁定版本解析 <span>静态扫描</span></p><p>许可声明与证据门禁校验 <span>保留缺口</span></p><p>Qwen3 辅助解读 <span>按需开启</span></p></div><p className="og-v3-source-note">未获取完整许可原文的依赖维持「未知 / 待核验」，不自动推断授权通过。</p></div>
        {mode === "api" && <section className="og-scan-usage-step" aria-label="扫描前用途"><h2 className="og-v3-panel-title">2. 项目预期用途声明（7 项）</h2><p className="og-usage-intro">用途信息可选；未回答的事实保持未知，可稍后补充。</p><UsageForm matrix compact value={usage} disabled={busy} onChange={value => { setUsage(value); changed(); }} /></section>}
        </section>
        {mode === "mock" && (
          <label className="og-field">
            固定演示场景
            <select
              aria-label="固定演示场景"
              value={scenario}
              onChange={(e) => setScenario(e.target.value as Scenario)}
            >
              {Object.entries(scenarios).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        )}
        {mode==='api'&&confirmedInput&&<section id="scan-confirmation" className="og-scan-step og-scan-confirmation" aria-label="确认扫描前用途"><header className="og-scan-step-heading"><h2>确认扫描前用途</h2><p>检查输入和用途，确认后才会开始扫描。</p></header><dl className="og-scan-input-summary"><div><dt>扫描输入</dt><dd>{confirmedInput.kind==='github'?confirmedInput.url:confirmedInput.file?.name}</dd></div><div><dt>用途场景</dt><dd>{presets[confirmedInput.usage!.preset]}</dd></div></dl><dl className="og-scan-usage-summary">{Object.entries(usageFields).map(([field,label])=><div key={field}><dt>{label}</dt><dd>{confirmedInput.usage![field as keyof typeof usageFields]===true?'是':confirmedInput.usage![field as keyof typeof usageFields]===false?'否':'暂不确定'}</dd></div>)}</dl><button type="button" disabled={busy} onClick={()=>{confirmationRef.current=null;setConfirmedInput(null);}}>返回检查用途</button>{readOnlyPreview&&<p role="note">只读预览：可检查用途摘要，不能开始扫描。</p>}</section>}
        {error && (
          <p id="scan-error" className="og-error" role="alert">
            {error}
          </p>
        )}
        <div className="og-form-footer">
          <p className="og-scan-boundary"><InputIcon kind="info" /><span>扫描现有依赖与明确的许可证声明；未核验内容保留待核验状态。</span></p>
          <div className="og-actions">
            {mode === "mock" && <button type="button" disabled={busy} onClick={demo}>
              载入固定演示
            </button>}
            <ActionButton
              className="og-primary"
              disabled={busy||(tab==='zip'?!file:!url.trim())||(mode==='api'&&!!confirmedInput&&readOnlyPreview)}
              type="submit"
            >
              {busy
                ? "提交中，请勿重复点击…"
                : mode === "mock"
                  ? "校验输入并播放演示"
                  : confirmedInput ? "开始扫描并评估" : "下一步：确认用途"}
            </ActionButton>
          </div>
        </div>
      </form>
    </div>
  );
}
