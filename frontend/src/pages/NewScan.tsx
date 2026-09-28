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
import { Panel, useNotice } from "../components/ui";

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
          <p>让资源、风险与每条证据在同一任务中保持一致。</p>
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
          <p className="og-mode-note">
            {mode === "mock"
              ? "演示数据 · 不联网，不读取你的仓库或 ZIP，只播放固定合成快照。"
              : "真实接口 · 地址校验、扫描和文件安全检查由后端执行。失败不会切换为演示结果。"}
          </p>
        </div>
      </header>
      <form onSubmit={submit} noValidate>
        <Panel
          title="扫描输入"
          caption={
            mode === "mock"
              ? "格式体验与真实扫描分开呈现"
              : "请确认后端已实现约定接口"
          }
        >
          <div className="og-tabs">
            <button
              type="button"
              aria-pressed={tab === "github"}
              disabled={busy}
              onClick={() => {
                setTab("github");
                changed();
              }}
            >
              <InputIcon kind="repository" /> GitHub 仓库
            </button>
            <button
              type="button"
              aria-pressed={tab === "zip"}
              disabled={busy}
              onClick={() => {
                setTab("zip");
                changed();
              }}
            >
              <InputIcon kind="upload" /> 上传 ZIP
            </button>
          </div>
          {tab === "github" ? (
            <div className="og-form-section">
              <label className="og-field">
                公开仓库地址
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
              </label>
              <p className="og-muted">公开 Git 需由服务管理员启用；提交时由后端校验。</p>
            </div>
          ) : (
            <div className="og-form-section">
              <div
                className="og-drop-zone"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!busy) select(e.dataTransfer.files[0] ?? null);
                }}
              >
                <div className="og-upload-symbol"><InputIcon kind="archive" /></div>
                <strong>{file ? file.name : "拖放 ZIP 文件到这里"}</strong>
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
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setFile(null);
                        changed();
                      }}
                    >
                      移除文件
                    </button>
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
          <p className="og-scan-boundary"><InputIcon kind="info" /><span>扫描现有依赖与明确的许可证声明；未核验内容保留待核验状态。</span></p>
          <div className="og-actions">
            {mode === "mock" && <button type="button" disabled={busy} onClick={demo}>
              载入固定演示
            </button>}
            <button
              className="og-primary"
              disabled={busy}
              type="submit"
            >
              {busy
                ? "提交中，请勿重复点击…"
                : mode === "mock"
                  ? "校验输入并播放演示"
                  : "提交真实扫描"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
