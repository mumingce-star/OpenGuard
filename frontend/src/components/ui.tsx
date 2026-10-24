import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
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

export function Checkbox({ children, compact = false, className = '', ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { compact?: boolean; children: ReactNode }) {
  return <label className={`og-choice ${compact ? 'compact' : ''} ${className}`}>
    <input {...props} type="checkbox" />
    <svg className="og-choice-mark" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="5" /><path d="m6 12 4 4 8-9" /></svg>
    <span>{children}</span>
  </label>;
}

export function SegmentedControl<T extends string>({ label, value, options, onChange, disabled }: {
  label: string; value: T; options: { value: T; label: ReactNode }[]; onChange: (value: T) => void; disabled?: boolean;
}) {
  const name = useId();
  const index = Math.max(0, options.findIndex(option => option.value === value));
  return <div className="og-segmented" role="radiogroup" aria-label={label} style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
    <span className="og-segmented-slider" aria-hidden="true" style={{ width: `calc((100% - 8px) / ${options.length})`, transform: `translateX(${index * 100}%)` }} />
    {options.map(option => <label key={option.value}><input type="radio" name={name} value={option.value} checked={value === option.value} disabled={disabled} onChange={() => onChange(option.value)} /><span>{option.label}</span></label>)}
  </div>;
}

export function ActionButton({ kind = 'primary', children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { kind?: 'primary' | 'send' | 'copy' | 'play' | 'remove'; children: ReactNode }) {
  const paths = { primary: 'M5 12h14m-6-6 6 6-6 6', send: 'm3 3 18 9-18 9 4-9-4-9Zm4 9h14', copy: 'M8 8h12v13H8zM4 16H2V2h13v2', play: 'm9 5 11 7-11 7Z', remove: 'M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7' };
  return <button type="button" {...props} className={`og-action-button og-action-${kind} ${className}`}><span className="og-action-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[kind]} /></svg></span><span>{children}</span>{kind === 'copy' && <span className="og-action-hint" aria-hidden="true">复制到剪贴板</span>}</button>;
}

export function HelpTip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  return <span className={`og-help ${open ? 'is-open' : ''} ${dismissed ? 'is-dismissed' : ''}`} onMouseEnter={() => setDismissed(false)} onKeyDown={event => { if (event.key === 'Escape') { setOpen(false); setDismissed(true); } }}>
    <button type="button" aria-label={label} aria-describedby={id} aria-expanded={open} onFocus={() => setDismissed(false)} onClick={() => { setDismissed(false); setOpen(value => !value); }} onBlur={() => setOpen(false)}>?</button>
    <span id={id} role="tooltip">{children}</span>
  </span>;
}

export function DownloadControl({ children, href, filename, format, onDownload, disabled }: {
  children: ReactNode; href?: string; filename?: string; format?: string; onDownload?: () => void | boolean | Promise<void | boolean>; disabled?: boolean;
}) {
  const [state, setState] = useState<'idle' | 'busy' | 'error' | 'started'>('idle');
  const [error, setError] = useState('');
  const lock = useRef(false);
  async function run() {
    if (lock.current || disabled) return;
    lock.current = true; setState('busy'); setError('');
    try {
      if (onDownload) { if (await onDownload() === false) throw new Error('无法生成下载文件，请重试。'); }
      else if (href) {
        const response = await fetch(href, { method: 'GET' });
        if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}），请重试。`);
        if (format && !response.headers.get('content-type')?.toLowerCase().includes(format)) throw new Error('附件格式不匹配，未发起保存。');
        const blob = await response.blob();
        if (!blob.size) throw new Error('附件为空，未发起保存。');
        const url = URL.createObjectURL(blob);
        try {
          const link = document.createElement('a'); link.href = url; link.download = filename ?? 'openguard-report';
          document.body.append(link); link.click(); link.remove();
        } finally { window.setTimeout(() => URL.revokeObjectURL(url), 10000); }
      } else throw new Error('未提供下载来源。');
      setState('started');
    } catch (reason) { setError(reason instanceof Error ? reason.message : '下载失败，请重试。'); setState('error'); }
    finally { lock.current = false; }
  }
  return <span className={`og-download-control ${state}`}>
    <button type="button" className="og-download-button" disabled={disabled || state === 'busy'} aria-busy={state === 'busy'} onClick={() => void run()}><DownloadGlyph /><span>{state === 'busy' ? '正在读取附件…' : children}</span></button>
    {state === 'error' && <span className="og-download-feedback" role="alert">{error}<button type="button" disabled={disabled} onClick={() => void run()}>重试下载</button></span>}
    {state === 'started' && <small role="status">已发起下载，请在浏览器中确认保存。</small>}
  </span>;
}

export function FlipCard({ title, summary, children, index }: { title: string; summary: string; children: ReactNode; index: string }) {
  const [flipped, setFlipped] = useState(false);
  const id = useId();
  return <article className={`og-flip-card ${flipped ? 'is-flipped' : ''}`}>
    <div className="og-flip-inner"><div className="og-flip-front" aria-hidden={flipped}><span>{index} / EXPLAINABLE</span><h3>{title}</h3><p>{summary}</p></div><div id={id} className="og-flip-back" aria-hidden={!flipped}><h3>{title}的边界</h3><p>{children}</p></div></div>
    <button type="button" aria-expanded={flipped} aria-controls={id} onClick={() => setFlipped(value => !value)}>{flipped ? '返回概览' : '查看原理'} <span aria-hidden="true">↗</span></button>
  </article>;
}

export function SearchGlyph() {
  return (
    <svg className="og-ui-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" focusable="false">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.2 4.2" />
    </svg>
  );
}

export function ArrowGlyph() {
  return (
    <svg className="og-ui-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  );
}

export function DownloadGlyph() {
  return (
    <svg className="og-ui-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M12 3v12m-4-4 4 4 4-4M5 19h14" />
    </svg>
  );
}

export function LoadingDots({ label, detail }: { label: string; detail?: string }) {
  return (
    <div className="og-loading-dots" role="status" aria-live="polite">
      <span className="og-loading-dots-visual" aria-hidden="true"><i /><i /><i /></span>
      <strong>{label}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
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
    return true;
  } catch {
    notify("无法生成下载文件，请重试。", "error", () =>
      download(name, data, mime, notify),
    );
    return false;
  } finally {
    if (url) window.setTimeout(() => URL.revokeObjectURL(url!), 10000);
  }
}
