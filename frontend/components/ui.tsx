"use client";

import { ReactNode, useCallback, useEffect, useEffectEvent, useState } from "react";

import type { Decision } from "@/lib/types";

export function Card({ title, subtitle, actions, children, className = "" }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-[0.95rem] font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** Consistent page title block: optional eyebrow, title, description and right-side actions. */
export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 pb-1">
      <div className="min-w-0">
        {eyebrow && <p className="text-xs font-semibold uppercase tracking-wider text-brand">{eyebrow}</p>}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function RefreshButton({ onClick, busy }: { onClick: () => void; busy?: boolean }) {
  return (
    <Button variant="secondary" onClick={onClick} disabled={busy}>
      <svg viewBox="0 0 24 24" className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <path d="M21 12a9 9 0 1 1-2.64-6.36M21 4v5h-5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Refresh
    </Button>
  );
}

const DECISION_STYLE: Record<Decision, { cls: string; icon: string; label: string }> = {
  ALLOW: { cls: "bg-good-soft text-good-text border-good/40", icon: "✓", label: "Allow" },
  WARN: { cls: "bg-warning-soft text-warning-text border-warning/50", icon: "!", label: "Warn" },
  HOLD: { cls: "bg-critical-soft text-critical-text border-critical/40", icon: "■", label: "Hold" },
};

/** Status colour always paired with an icon + text label (never colour alone). */
export function DecisionBadge({ decision, size = "sm" }: { decision: Decision; size?: "sm" | "lg" }) {
  const s = DECISION_STYLE[decision];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border font-semibold ${s.cls} ${size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs"}`}>
      <span aria-hidden>{s.icon}</span>
      {s.label}
    </span>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "brand" }) {
  const cls = tone === "brand" ? "bg-brand-soft text-brand" : "bg-surface-2 text-ink-2";
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}

export function Button({ children, onClick, variant = "primary", disabled, type = "button", className = "" }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean; type?: "button" | "submit"; className?: string;
}) {
  const styles = {
    primary: "bg-brand text-brand-ink shadow-raised hover:brightness-110",
    secondary: "border border-line bg-surface text-ink shadow-card hover:border-axis hover:bg-surface-2",
    danger: "bg-critical text-white shadow-raised hover:brightness-110",
    ghost: "text-ink-2 hover:bg-surface-2",
  }[variant];
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex min-h-9 items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition active:scale-[0.98] disabled:active:scale-100 disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}>
      {children}
    </button>
  );
}

export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-line bg-surface p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-raised">
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-brand to-brand-2 opacity-70 transition group-hover:opacity-100" aria-hidden />
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="tabular mt-1.5 text-2xl font-semibold tracking-tight text-ink">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-2">{hint}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-brand" />
      {label}…
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-critical/40 bg-critical-soft p-3 text-sm text-critical-text" role="alert">
      <strong>Something went wrong.</strong> {error}
      {onRetry && (
        <button onClick={onRetry} className="ml-2 underline">Retry</button>
      )}
    </div>
  );
}

/**
 * Risk level relative to the policy's own thresholds. A calibrated fraud probability of 0.38 looks
 * "low" in isolation, but with a ~1% base rate and a HOLD line near 0.10 it is very high, so the
 * raw number is always shown next to the thresholds it is judged against.
 */
export function RiskLevel({ score, warnT, holdT, decision }: { score: number; warnT?: number; holdT?: number; decision: Decision }) {
  const level = decision === "HOLD" ? "High" : decision === "WARN" ? "Medium" : "Low";
  const cls = { High: "bg-critical-soft text-critical-text border-critical/40", Medium: "bg-warning-soft text-warning-text border-warning/50", Low: "bg-good-soft text-good-text border-good/40" }[level];
  const ref = decision === "HOLD" ? holdT : decision === "WARN" ? warnT : warnT;
  const ratio = ref && ref > 0 ? score / ref : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-sm text-ink-2">
      <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{level} risk</span>
      <span className="tabular">
        fraud probability <strong className="text-ink">{(score * 100).toFixed(1)}%</strong>
        {holdT != null && warnT != null && (
          <span className="text-muted"> · WARN from {(warnT * 100).toFixed(0)}%, HOLD from {(holdT * 100).toFixed(0)}%{ratio && decision !== "ALLOW" ? ` (${ratio.toFixed(1)}× the ${decision} line)` : ""}</span>
        )}
      </span>
    </span>
  );
}

/** Horizontal meter for a 0..1 score; value is always printed next to the bar. */
export function ScoreBar({ value, label, threshold }: { value: number; label: string; threshold?: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="grid grid-cols-[6.5rem_1fr_3.5rem] items-center gap-2 text-xs">
      <span className="text-ink-2">{label}</span>
      <div className="relative h-2 rounded-full bg-surface-2">
        <div className="h-2 rounded-full bg-series-1" style={{ width: `${pct}%` }} />
        {threshold != null && (
          <div className="absolute -top-1 h-4 w-px bg-ink-2" style={{ left: `${threshold * 100}%` }} title={`threshold ${threshold.toFixed(3)}`} />
        )}
      </div>
      <span className="tabular text-right text-ink">{value.toFixed(3)}</span>
    </div>
  );
}

/** Small data-loading hook with retry. Refetches when `deps` change or `reload()` is called. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<{ data: T | null; error: string | null; done: string | null }>({ data: null, error: null, done: null });
  const [nonce, setNonce] = useState(0);
  const key = `${JSON.stringify(deps)}#${nonce}`;
  const load = useEffectEvent(() => fn());

  useEffect(() => {
    let alive = true;
    load()
      .then((data) => alive && setState({ data, error: null, done: key }))
      .catch((e: Error) => alive && setState((s) => ({ data: s.data, error: e.message, done: key })));
    return () => {
      alive = false;
    };
  }, [key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T | null) => setState((s) => ({ ...s, data })), []);
  // Loading until the request for the current key has settled; stale data stays visible meanwhile.
  return { data: state.data, error: state.done === key ? state.error : null, loading: state.done !== key, reload, setData };
}
