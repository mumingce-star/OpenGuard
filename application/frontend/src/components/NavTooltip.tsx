import { cloneElement, useId, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type ReactElement } from 'react';
import { createPortal } from 'react-dom';

/** A body portal keeps rail labels outside the sidebar's scrolling clip. */
export function NavTooltip({ label, disabledReason, enabled, children }: {
  label: string;
  disabledReason?: string;
  enabled: boolean;
  children: ReactElement<ButtonHTMLAttributes<HTMLButtonElement>>;
}) {
  const id = useId();
  const anchor = useRef<HTMLSpanElement>(null);
  const tooltip = useRef<HTMLSpanElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0 });
  const visible = enabled && (hovered || focused) && !dismissed;
  function show() {
    window.dispatchEvent(new CustomEvent('openguard:nav-tooltip-open', { detail: id }));
    setDismissed(false);
  }

  useLayoutEffect(() => {
    if (!visible) return;
    function update() {
      const rect = anchor.current?.getBoundingClientRect();
      const tip = tooltip.current?.getBoundingClientRect();
      if (!rect || !tip) return;
      if (!rect.width || !rect.height) { setDismissed(true); return; }
      const rail = anchor.current?.closest('.og-sidebar')?.getBoundingClientRect();
      setPosition({
        left: Math.max(12, Math.min(Math.max(rect.right, rail?.right ?? rect.right) + 10, window.innerWidth - tip.width - 12)),
        top: Math.max(12, Math.min(rect.top + (rect.height - tip.height) / 2, window.innerHeight - tip.height - 12)),
      });
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape') setDismissed(true);
    }
    function closeOtherLabel(event: Event) {
      if ((event as CustomEvent<string>).detail !== id) setDismissed(true);
    }
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    window.addEventListener('keydown', escape);
    window.addEventListener('openguard:nav-tooltip-open', closeOtherLabel);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('keydown', escape);
      window.removeEventListener('openguard:nav-tooltip-open', closeOtherLabel);
    };
  }, [visible, id]);

  return <span
    ref={anchor}
    className="og-nav-item"
    data-disabled={disabledReason ? 'true' : undefined}
    tabIndex={enabled && disabledReason ? 0 : undefined}
    role={enabled && disabledReason ? 'group' : undefined}
    aria-label={enabled && disabledReason ? `${label}，不可用：${disabledReason}` : undefined}
    aria-disabled={disabledReason ? true : undefined}
    aria-describedby={enabled && disabledReason && visible ? id : undefined}
    onPointerEnter={() => { setHovered(true); show(); }}
    onPointerLeave={() => setHovered(false)}
    onFocusCapture={() => { setFocused(true); show(); }}
    onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false); }}
  >
    {cloneElement(children, { 'aria-describedby': visible ? id : undefined })}
    {visible && createPortal(<span ref={tooltip} id={id} className="og-nav-tooltip" role="tooltip" style={position}>
      <span>{label}</span>
      {disabledReason && <small>不可用：{disabledReason}</small>}
    </span>, document.body)}
  </span>;
}
