import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Check, ChevronDown, Loader2, X } from "lucide-react";

export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

export function Card({ className = "", children }) {
  return (
    <div
      className={cx(
        "rounded-xl border border-slate-200 bg-white shadow-card",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const BUTTON_VARIANTS = {
  primary:
    "bg-brand-600 text-white hover:bg-brand-700 focus-visible:ring-brand-500 shadow-sm",
  secondary:
    "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 focus-visible:ring-slate-400",
  ghost: "text-slate-600 hover:bg-slate-100 focus-visible:ring-slate-400",
  danger:
    "bg-white text-red-600 border border-red-200 hover:bg-red-50 focus-visible:ring-red-400",
};

export function Button({
  variant = "primary",
  className = "",
  loading = false,
  disabled,
  children,
  ...props
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold",
        "transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1",
        "disabled:cursor-not-allowed disabled:opacity-60",
        BUTTON_VARIANTS[variant],
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 size={15} className="animate-spin" />}
      {children}
    </button>
  );
}

const BADGE_TONES = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  red: "bg-red-50 text-red-700 ring-red-600/20",
  slate: "bg-slate-100 text-slate-600 ring-slate-500/20",
  brand: "bg-brand-50 text-brand-700 ring-brand-600/20",
  amber: "bg-amber-50 text-amber-700 ring-amber-600/20",
  violet: "bg-violet-50 text-violet-700 ring-violet-600/20",
};

export function Badge({ tone = "slate", children, className = "" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        BADGE_TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  );
}

const inputBase =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30";

export function Input(props) {
  return <input className={cx(inputBase, props.className)} {...props} />;
}

export function Textarea(props) {
  return <textarea className={cx(inputBase, "resize-y", props.className)} {...props} />;
}

export function Select({ className = "", children, ...props }) {
  return (
    <select className={cx(inputBase, "pr-8", className)} {...props}>
      {children}
    </select>
  );
}

// Checkbox dropdown. `value` is the list of selected options; an empty list
// means "all" (shown as `allLabel`). onChange normalizes full/empty back to [].
export function MultiSelect({ options, value, onChange, allLabel = "All", className = "" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const effective = value.length === 0 ? options : value;
  const label =
    value.length === 0 || value.length === options.length
      ? allLabel
      : value.length === 1
      ? value[0]
      : `${value.length} selected`;

  const toggle = (opt) => {
    let next = effective.includes(opt)
      ? effective.filter((o) => o !== opt)
      : [...effective, opt];
    if (next.length === 0 || next.length === options.length) next = [];
    onChange(next);
  };

  return (
    <div ref={ref} className={cx("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={options.length === 0}
        className={cx(inputBase, "flex items-center justify-between gap-2 disabled:opacity-60")}
      >
        <span className="truncate">{options.length === 0 ? allLabel : label}</span>
        <ChevronDown size={14} className="shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 max-h-64 w-56 overflow-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          <button
            type="button"
            onClick={() => onChange([])}
            className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            {allLabel}
            {value.length === 0 && <Check size={14} className="text-brand-600" />}
          </button>
          <div className="my-1 border-t border-slate-100" />
          {options.map((opt) => (
            <label
              key={opt}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              <input
                type="checkbox"
                checked={effective.includes(opt)}
                onChange={() => toggle(opt)}
                className="h-3.5 w-3.5 accent-brand-600"
              />
              <span className="truncate">{opt}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400">
      <Loader2 size={16} className="animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-50 text-red-600">
        <AlertTriangle size={18} />
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-800">Something went wrong</p>
        <p className="mt-0.5 text-sm text-slate-500">{error?.message || "Unknown error"}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center gap-3 py-14 text-center">
      {Icon && (
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
          <Icon size={20} />
        </div>
      )}
      <div>
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer, maxWidth = "max-w-lg" }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  // Portal to <body> so the page's scroll/overflow context can't clip the
  // fixed overlay, and the modal is measured against the real viewport.
  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex min-h-full items-center justify-center p-4">
        <div
          className={cx(
            "relative flex max-h-[85dvh] w-full flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl animate-fade-in",
            maxWidth
          )}
        >
          <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-4">
            <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              <X size={18} />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <div className="flex shrink-0 justify-end gap-2 border-t border-slate-100 px-5 py-3">
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
