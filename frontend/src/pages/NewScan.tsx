import { UsageForm } from "../components/UsageForm";
import { emptyUsage } from "../services/assessments";
import { useRef, useState } from "react";
import type { Mode, Scan, ScanInput } from "../types/domain";
import {
  createApiScan,
  createDemo,
  zipLimit,
} from "../services/scans";
import { validateGithub, validateZip } from "../services/model";
import { scenarios, type Scenario } from "../mocks/data";
import { ActionButton, Panel, SegmentedControl, useNotice } from "../components/ui";

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
  const [scenario, setScenario] = useState<Scenario>("standard");
  const picker = useRef<HTMLInputElement>(null),
    lock = useRef(false),
    requestId = useRef(crypto.randomUUID());
  const notify = useNotice();
  function changed() {
    setError("");
    requestId.current = crypto.randomUUID();
  }
  function select(f: File | null) {
    setFile(f);
    changed();
    setError(validateZip(f, zipLimit) ?? "");
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (lock.current) return;
    setError("");
    const problem =
      tab === "github" ? validateGithub(url) : validateZip(file, zipLimit);
    if (problem) {
      setError(problem);
      return;
    }
    lock.current = true;
    setBusy(true);
    try {
      const input: ScanInput = {
        kind: tab,
        url,
        file: file ?? undefined,
        ...(mode === "api" ? { usage } : {}),
      };
      onCreated(
        mode === "mock"
          ? createDemo(scenario)
          : await createApiScan(input, requestId.current),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "任务提交失败，请重试。");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function demo() {
    try {
      onCreated(createDemo(scenario));
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  return (
    <div className="og-new-scan">
      <header className="og-scan-heading">
        <div className="og-scan-introduction">
          <h1>从一个项目开始</h1>
          <p>上传项目，查看资源、证据与评估结果。</p>
        </div>
        <div className="og-scan-mode">
          <div className="og-mode-switch" aria-label="数据模式">
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
          </div>
          {mode === "mock" && <p className="og-mode-note">固定合成演示，不会扫描你选择的项目。</p>}
        </div>
      </header>
      <div className="og-scan-layout">
      <form onSubmit={submit} noValidate aria-label="新建扫描">
        <Panel
          title="选择项目"
          caption={
            mode === "mock"
              ? "选择输入方式，体验固定演示流程"
              : "从公开 GitHub 仓库或本地 ZIP 开始"
          }
        >
          <SegmentedControl label="扫描输入方式" value={tab} disabled={busy} onChange={value => { setTab(value); changed(); }} options={[{ value: 'github', label: <><InputIcon kind="repository" /> GitHub 仓库</> }, { value: 'zip', label: <><InputIcon kind="upload" /> 上传 ZIP</> }]} />
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
              <p className="og-muted">填写公开仓库地址。服务未启用公开 Git 时会提示原因。</p>
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
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  if (!busy) select(e.dataTransfer.files[0] ?? null);
                }}
                aria-busy={busy}
              >
                <div className="og-upload-symbol"><InputIcon kind="archive" /></div>
                <strong>{file ? file.name : dragging ? "松开即可选择此 ZIP" : "拖放 ZIP 文件到这里"}</strong>
                <p>
                  {file
                    ? (file.size / 1024 / 1024).toFixed(2) + " MB"
                    : "或从电脑中选择项目文件"}
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
                  : "支持 ZIP，文件限制以服务提示为准。"}
              </p>
            </div>
          )}
        </Panel>
        {mode === "api" && <UsageForm value={usage} disabled={busy} onChange={value => { setUsage(value); changed(); }} />}
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
        {error && (
          <p id="scan-error" className="og-error" role="alert">
            {error}
          </p>
        )}
        <div className="og-form-footer">
          <p className="og-scan-boundary"><InputIcon kind="info" /><span>{mode === "mock" ? "演示数据不会作为真实项目结果。" : (tab === "zip" ? file : url.trim()) ? "确认项目与用途后，开始扫描。" : "选择 ZIP 或填写仓库地址后可开始。"}</span></p>
          <div className="og-actions">
            {mode === "mock" && <button type="button" disabled={busy} onClick={demo}>
              载入固定演示
            </button>}
            <ActionButton
              className="og-primary"
              disabled={busy || (tab === "zip" ? !file : !url.trim())}
              type="submit"
            >
              {busy
                ? "提交中，请勿重复点击…"
                : mode === "mock"
                  ? "校验输入并播放演示"
                  : "提交真实扫描"}
            </ActionButton>
          </div>
        </div>
      </form>
      <aside className="og-scan-guide" aria-labelledby="scan-guide-title">
        <p className="og-eyebrow">从输入到证据</p>
        <h2 id="scan-guide-title">扫描后你将看到</h2>
        <ol>
          <li><span className="og-guide-icon"><InputIcon kind="repository" /></span><div><h3>资源清单</h3><p>集中查看发现的依赖、模型与数据集引用。</p></div></li>
          <li><span className="og-guide-icon"><InputIcon kind="info" /></span><div><h3>风险与来源证据</h3><p>从待核查线索，回到文件位置与原始依据。</p></div></li>
          <li><span className="og-guide-icon"><InputIcon kind="archive" /></span><div><h3>正式评估与报告</h3><p>查看已保存的评估版本与可用报告，继续复核。</p></div></li>
        </ol>
        <p className="og-guide-boundary">扫描完成不代表项目已合规；证据不足的内容保留未知或待核验状态。</p>
        <details className="og-scan-help"><summary>了解扫描与数据边界</summary><p>只做格式与大小预检，不在浏览器解压或执行项目。</p><p>扫描与安全校验由服务执行。真实接口失败不会切换为演示结果；演示只播放固定合成快照。</p><p>扫描可能部分完成，请结合覆盖范围与证据继续核查。</p></details>
      </aside>
      </div>
    </div>
  );
}
