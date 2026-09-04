import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import type { Severity, ScanStatus } from "../types/domain";
import { severityLabels, statusLabels } from "../types/domain";
export type Notice = (
  message: string,
  tone?: "success" | "error",
  retry?: () => void,
) => void;
export const NoticeContext = createContext<Notice>(() => {});
export const useNotice = () => useContext(NoticeContext);
export function Header({
  title,
  description,
  eyebrow,
  action,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  action?: ReactNode;
}) {
  return (
    <div className="og-page-header">
      <div>
        <p className="og-eyebrow">{eyebrow ?? "OPENGUARD / WORKSPACE"}</p>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function Panel({
  title,
  caption,
  children,
  action,
}: {
  title: string;
  caption?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="og-panel">
      <header className="og-panel-title">
        <div>
          <h2>{title}</h2>
          {caption && <p>{caption}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}
export function Empty({
  title,
  detail,
  children,
}: {
  title: string;
  detail?: string;
  children?: ReactNode;
}) {
  return (
    <div className="og-empty">
      <span aria-hidden="true">◇</span>
      <h2>{title}</h2>
      {detail && <p>{detail}</p>}
      {children}
    </div>
  );
}
export function SeverityBadge({ value }: { value: Severity }) {
  return <span className={"og-badge " + value}>{severityLabels[value]}</span>;
}
export function StatusBadge({ status }: { status: ScanStatus }) {
  return <span className={"og-badge " + status}>{statusLabels[status]}</span>;
}
export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const active = document.activeElement as HTMLElement;
    const dialog = ref.current;
    dialog?.showModal();
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = old;
      active?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="og-dialog"
      aria-label={title}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button type="button" onClick={onClose} aria-label="关闭面板">
          关闭 ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
export async function copyText(value: string, notify: Notice) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error();
    await navigator.clipboard.writeText(value);
    notify("已复制到剪贴板。");
  } catch {
    notify(
      "复制失败，请允许剪贴板权限后重试，或手动选择文本复制。",
      "error",
      () => void copyText(value, notify),
    );
  }
}
export function download(
  name: string,
  data: string,
  mime: string,
  notify: Notice,
) {
  let url: string | undefined;
  try {
    url = URL.createObjectURL(new Blob([data], { type: mime }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    notify("已发起下载，请在浏览器下载列表中确认保存。");
  } catch {
    notify("无法生成下载文件，请重试。", "error", () =>
      download(name, data, mime, notify),
    );
  } finally {
    if (url) window.setTimeout(() => URL.revokeObjectURL(url!), 10000);
  }
}
