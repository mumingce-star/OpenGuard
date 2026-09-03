import { useRef, useState } from "react";
import type { Mode, Scan, ScanInput } from "../types/domain";
import {
  createApiScan,
  createDemo,
  validateRepository,
  zipLimit,
} from "../services/scans";
import { validateGithub, validateZip } from "../services/model";
import { scenarios, type Scenario } from "../mocks/data";
import { Header, Panel, useNotice } from "../components/ui";
const scopeOptions = [
  "依赖与第三方包",
  "模型与数据集",
  "API 与外部服务",
  "LICENSE / NOTICE",
];
export function NewScan({
  mode,
  onMode,
  onCreated,
}: {
  mode: Mode;
  onMode: (mode: Mode) => void;
  onCreated: (scan: Scan) => void;
}) {
  const [tab, setTab] = useState<"github" | "zip">("github"),
    [url, setUrl] = useState(""),
    [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [access, setAccess] = useState("");
  const [checking, setChecking] = useState(false),
    [scopes, setScopes] = useState(scopeOptions),
    [scenario, setScenario] = useState<Scenario>("standard");
  const picker = useRef<HTMLInputElement>(null),
    lock = useRef(false),
    generation = useRef(0),
    requestId = useRef(crypto.randomUUID());
  const notify = useNotice();
  function changed() {
    generation.current++;
    setAccess("");
    setError("");
    requestId.current = crypto.randomUUID();
  }
  function select(f: File | null) {
    setFile(f);
    changed();
    setError(validateZip(f, zipLimit) ?? "");
  }
  async function check() {
    const problem = validateGithub(url);
    if (problem) {
      setError(problem);
      return;
    }
    const version = generation.current;
    setChecking(true);
    setError("");
    setAccess("");
    try {
      await validateRepository(url);
      if (version === generation.current) setAccess(url.trim());
    } catch (e) {
      if (version === generation.current)
        setError(e instanceof Error ? e.message : "仓库访问校验失败");
    } finally {
      setChecking(false);
    }
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
    if (!scopes.length) {
      setError("请至少选择一种扫描范围。");
      return;
    }
    if (mode === "api" && tab === "github" && access !== url.trim()) {
      setError("请先校验仓库访问状态。");
      return;
    }
    lock.current = true;
    setBusy(true);
    try {
      const input: ScanInput = {
        kind: tab,
        url,
        file: file ?? undefined,
        scopes,
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
      <Header
        eyebrow="START / A TRACEABLE SCAN"
        title="从一个项目开始"
        description="让资源、风险与每条证据在同一任务中保持一致。"
      />
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
      <Panel
        title="扫描输入"
        caption={
          mode === "mock"
            ? "格式体验与真实扫描分开呈现"
            : "请确认后端已实现约定接口"
        }
      >
        <form onSubmit={submit} noValidate>
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
              GitHub 仓库
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
              上传 ZIP
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
              <div className="og-actions">
                <button
                  type="button"
                  disabled={busy || checking || mode === "mock"}
                  onClick={() => void check()}
                >
                  {checking ? "正在校验…" : "校验仓库访问"}
                </button>
                <span className={access ? "og-positive" : "og-muted"}>
                  {access
                    ? "后端已确认仓库可访问"
                    : mode === "mock"
                      ? "演示模式不检查仓库访问"
                      : "尚未校验仓库访问"}
                </span>
              </div>
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
                  : "大小上限未配置；真实 ZIP 上传暂不可用，需团队确认 VITE_MAX_ZIP_MB。"}
              </p>
            </div>
          )}
          <fieldset disabled={busy}>
            <legend>扫描范围</legend>
            <div className="og-check-grid">
              {scopeOptions.map((s) => (
                <label key={s}>
                  <input
                    type="checkbox"
                    checked={scopes.includes(s)}
                    onChange={() => {
                      changed();
                      setScopes((v) =>
                        v.includes(s) ? v.filter((x) => x !== s) : [...v, s],
                      );
                    }}
                  />
                  {s}
                </label>
              ))}
            </div>
          </fieldset>
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
            <button type="button" disabled={busy} onClick={demo}>
              载入固定演示
            </button>
            <button
              className="og-primary"
              disabled={
                busy ||
                checking ||
                (mode === "api" && tab === "zip" && zipLimit === null)
              }
              type="submit"
            >
              {busy
                ? "提交中，请勿重复点击…"
                : mode === "mock"
                  ? "校验输入并播放演示"
                  : "提交真实扫描"}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
