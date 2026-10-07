"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { health } from "@/lib/api";

// Stroke icons (24px grid), drawn inline so the nav has no icon-library dependency.
const ICONS: Record<string, string> = {
  overview: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  customer: "M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM11 18h2",
  analyst: "M4 5h16M4 12h10M4 19h7M17 15l2 2 3-4",
  chat: "M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  copilot: "M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 4zM8 8h8M8 12h5",
  impact: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  study: "M9 3h6M10 3v6L4 19a1 1 0 0 0 .9 1.5h14.2A1 1 0 0 0 20 19l-6-10V3M7 14h10",
  admin: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
};

const LINKS = [
  { href: "/", label: "Overview", icon: "overview" },
  { href: "/customer", label: "Customer app", icon: "customer" },
  { href: "/analyst", label: "Analyst console", icon: "analyst" },
  { href: "/chat", label: "AI chat", icon: "chat" },
  { href: "/copilot", label: "SOP copilot", icon: "copilot" },
  { href: "/dashboard", label: "Impact", icon: "impact" },
  { href: "/study", label: "User study", icon: "study" },
  { href: "/admin", label: "Admin", icon: "admin" },
];

function Icon({ name, className = "h-4 w-4" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={ICONS[name]} />
    </svg>
  );
}

export function Nav() {
  const path = usePathname();
  const [status, setStatus] = useState<string>("checking");
  // The menu is open only for the page it was opened on, so navigating closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === path;

  useEffect(() => {
    let alive = true;
    const check = () => health().then((h) => alive && setStatus(h.status)).catch(() => alive && setStatus("offline"));
    check();
    const t = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // On the customer app, the chat opens in customer mode.
  const hrefFor = (href: string) => (href === "/chat" && path.startsWith("/customer") ? "/chat?audience=customer" : href);
  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  const tone = {
    ok: { dot: "bg-good", pill: "border-good/30 bg-good-soft text-good-text" },
    degraded: { dot: "bg-warning", pill: "border-warning/40 bg-warning-soft text-warning-text" },
    checking: { dot: "bg-axis", pill: "border-line bg-surface-2 text-muted" },
  }[status] ?? { dot: "bg-critical", pill: "border-critical/30 bg-critical-soft text-critical-text" };

  return (
    <header className="sticky top-0 z-30 border-b border-line/80 bg-surface/80 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5">
        <Link href="/" className="flex shrink-0 items-center gap-2.5 font-semibold text-ink">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-brand-2 text-brand-ink shadow-raised" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3l7 3v6c0 4.5-3 7.7-7 9-4-1.3-7-4.5-7-9V6l7-3z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
          </span>
          <span className="leading-tight">
            <span className="block tracking-tight">Shurokkha</span>
            <span lang="bn" className="block text-[11px] font-normal text-muted">সুরক্ষা · AI Trust Copilot</span>
          </span>
        </Link>

        <nav className="ml-4 hidden items-center gap-0.5 rounded-xl border border-line bg-surface-2/60 p-1 xl:flex" aria-label="Main">
          {LINKS.map((l) => {
            const active = isActive(l.href);
            return (
              <Link key={l.href} href={hrefFor(l.href)} aria-current={active ? "page" : undefined}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${active ? "bg-surface font-medium text-brand shadow-card" : "text-ink-2 hover:bg-surface/70 hover:text-ink"}`}>
                <Icon name={l.icon} />
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${tone.pill}`} title="API health" role="status">
            <span className="relative flex h-2 w-2">
              {status === "ok" && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${tone.dot}`} />}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${tone.dot}`} />
            </span>
            API {status}
          </span>
          <button className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-surface text-ink-2 xl:hidden" onClick={() => setOpenOn(open ? null : path)}
            aria-expanded={open} aria-label={open ? "Close menu" : "Open menu"}>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
              <path d={open ? "M6 6l12 12M18 6L6 18" : "M4 7h16M4 12h16M4 17h16"} />
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <nav className="animate-rise grid gap-1 border-t border-line px-4 py-3 sm:grid-cols-2 xl:hidden" aria-label="Mobile">
          {LINKS.map((l) => {
            const active = isActive(l.href);
            return (
              <Link key={l.href} href={hrefFor(l.href)} aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm ${active ? "bg-brand-soft font-medium text-brand" : "text-ink-2 hover:bg-surface-2"}`}>
                <Icon name={l.icon} />
                {l.label}
              </Link>
            );
          })}
        </nav>
      )}

      <div className="border-t border-brand/10 bg-brand-soft/70 px-4 py-1 text-center text-[11px] text-brand">
        Demo prototype: all customers, wallets and transactions are synthetic. No real personal data.
      </div>
    </header>
  );
}
