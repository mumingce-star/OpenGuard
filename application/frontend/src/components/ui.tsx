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
      <span className="og-empty-emblem" aria-hidden="true">
        <svg viewBox="0 0 280 104" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* Corner blueprint registration brackets */}
          <path d="M10 22V10H22M258 10H270V22M10 82V94H22M258 94H270V82" stroke="#9ec0b0" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          {/* Horizontal & vertical axis guidelines */}
          <line x1="20" y1="52" x2="260" y2="52" stroke="#d5e5dd" strokeWidth="1" strokeDasharray="3 3" />
          <line x1="140" y1="8" x2="140" y2="96" stroke="#d5e5dd" strokeWidth="1" strokeDasharray="3 3" />
          {/* Left wing: Dependency & AST node cards */}
          <path d="M82 35C98 35 100 52 112 52M88 69C102 69 102 52 112 52" stroke="#6aa08b" strokeWidth="1.3" strokeDasharray="2.5 2.5" />
          <rect x="26" y="23" width="56" height="24" rx="5" fill="#ffffff" stroke="#b9d5c7" strokeWidth="1.2" />
          <circle cx="36" cy="35" r="3.2" fill="#2f8566" />
          <line x1="44" y1="32" x2="72" y2="32" stroke="#19614b" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="44" y1="38" x2="64" y2="38" stroke="#7da393" strokeWidth="1.3" strokeLinecap="round" />
          <rect x="32" y="57" width="56" height="22" rx="5" fill="#f1f7f4" stroke="#c5ddd1" strokeWidth="1.2" />
          <circle cx="42" cy="68" r="2.8" fill="#5b947e" />
          <line x1="50" y1="65" x2="78" y2="65" stroke="#477d68" strokeWidth="1.4" strokeLinecap="round" />
          <line x1="50" y1="71" x2="68" y2="71" stroke="#8fb0a1" strokeWidth="1.2" strokeLinecap="round" />
          {/* Center: Orbital verification dial & dossier */}
          <circle cx="140" cy="52" r="40" fill="#f6faf8" stroke="#c3dcd0" strokeWidth="1.2" strokeDasharray="4 3" />
          <circle cx="140" cy="52" r="30" fill="#ffffff" stroke="#d5e7de" strokeWidth="1.1" />
          <path d="M140 8V14M140 90V96M96 52H102M178 52H184" stroke="#82ab99" strokeWidth="1.3" strokeLinecap="round" />
          <rect x="124" y="32" width="32" height="40" rx="5" fill="#ecf5f0" stroke="#19614b" strokeWidth="1.5" />
          <line x1="131" y1="41" x2="149" y2="41" stroke="#19614b" strokeWidth="1.6" strokeLinecap="round" />
          <line x1="131" y1="48" x2="149" y2="48" stroke="#3f7c66" strokeWidth="1.4" strokeLinecap="round" />
          <line x1="131" y1="55" x2="143" y2="55" stroke="#78a090" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="151" cy="66" r="8.5" fill="#19614b" stroke="#ffffff" strokeWidth="1.5" />
          <path d="M147.8 66l2.2 2.2 4.2-4.4" stroke="#ffffff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          {/* Right wing: License & Evidence anchor nodes */}
          <path d="M168 52C180 52 182 35 198 35M168 52C180 52 180 69 192 69" stroke="#6aa08b" strokeWidth="1.3" strokeDasharray="2.5 2.5" />
          <rect x="198" y="23" width="56" height="24" rx="5" fill="#ffffff" stroke="#b9d5c7" strokeWidth="1.2" />
          <rect x="205" y="30" width="10" height="10" rx="2.5" fill="#e6f2ec" stroke="#2f8566" strokeWidth="1.2" />
          <line x1="220" y1="32" x2="245" y2="32" stroke="#19614b" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="220" y1="38" x2="238" y2="38" stroke="#7da393" strokeWidth="1.3" strokeLinecap="round" />
          <rect x="192" y="57" width="56" height="22" rx="5" fill="#f1f7f4" stroke="#c5ddd1" strokeWidth="1.2" />
          <circle cx="202" cy="68" r="2.8" fill="#2f8566" />
          <line x1="210" y1="65" x2="238" y2="65" stroke="#477d68" strokeWidth="1.4" strokeLinecap="round" />
          <line x1="210" y1="71" x2="229" y2="71" stroke="#8fb0a1" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </span>
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
