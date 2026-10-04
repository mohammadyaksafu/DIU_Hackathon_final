"use client";

import Link from "next/link";
import { useState } from "react";

import { Card, DecisionBadge, ErrorBox, PageHeader, Pill, RefreshButton, Spinner, useApi } from "@/components/ui";
import { api, fmtBDT, fmtTime } from "@/lib/api";
import type { AlertSummary } from "@/lib/types";

interface Page {
  total: number;
  page: number;
  size: number;
  items: AlertSummary[];
}

const STATUS = ["OPEN", "INVESTIGATING", "RESOLVED", "DISPUTED"];

export default function AnalystQueue() {
  const [status, setStatus] = useState("OPEN,INVESTIGATING");
  const [decision, setDecision] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"risk" | "newest">("risk");
  const [page, setPage] = useState(1);
  const size = 20;

  const params = new URLSearchParams({ page: String(page), size: String(size), sort });
  if (status) params.set("status", status);
  if (decision) params.set("decision", decision);
  if (q) params.set("q", q);
  const { data, error, loading, reload } = useApi(() => api<Page>(`/alerts?${params}`, { role: "analyst" }), [params.toString()]);
  const pages = data ? Math.max(1, Math.ceil(data.total / size)) : 1;

  return (
    <div className="space-y-4">
      <PageHeader eyebrow="Analyst console" title="Alert queue"
        description="Ranked by calibrated risk. HOLD cases block a transfer until reviewed (SOP-05: 15-minute target)."
        actions={<RefreshButton onClick={reload} busy={loading} />} />

      {data && data.items.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-brand/25 bg-brand-soft/60 px-4 py-3 text-sm">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-brand-ink" aria-hidden>?</span>
          <p className="min-w-0 flex-1 text-ink-2">
            <strong className="text-ink">Start here:</strong> open the highest-risk case to see the evidence, the mule-ring network and the AI case summary, then label it.
            To follow a live transfer end to end, run a scenario in the <Link href="/customer" className="font-medium text-brand underline">Customer app</Link> and use its alert link.
          </p>
          <Link href={`/analyst/cases/${data.items[0].id}`} className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-brand-ink shadow-raised hover:brightness-110">
            Open case #{data.items[0].id} →
          </Link>
        </div>
      )}

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filters">
        <select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="rounded-lg border border-line bg-surface px-3 py-2 text-sm">
          <option value="OPEN,INVESTIGATING">Open + investigating</option>
          {STATUS.map((s) => <option key={s} value={s}>{s.toLowerCase()}</option>)}
          <option value="">All statuses</option>
        </select>
        <select aria-label="Filter by decision" value={decision} onChange={(e) => { setDecision(e.target.value); setPage(1); }} className="rounded-lg border border-line bg-surface px-3 py-2 text-sm">
          <option value="">All decisions</option>
          <option value="HOLD">Hold</option>
          <option value="WARN">Warn</option>
        </select>
        <select aria-label="Sort order" value={sort} onChange={(e) => setSort(e.target.value as "risk" | "newest")} className="rounded-lg border border-line bg-surface px-3 py-2 text-sm">
          <option value="risk">Highest risk first</option>
          <option value="newest">Newest first</option>
        </select>
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Search wallet or tx id" aria-label="Search wallet or transaction id"
          className="min-w-48 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm sm:flex-none" />
      </div>

      {error && <ErrorBox error={error} onRetry={reload} />}
      <Card>
        {loading && !data ? <Spinner /> : (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                  <th className="py-2 pr-3 font-medium">Alert</th>
                  <th className="py-2 pr-3 font-medium">Decision</th>
                  <th className="py-2 pr-3 text-right font-medium">Risk</th>
                  <th className="py-2 pr-3 text-right font-medium">Amount</th>
                  <th className="py-2 pr-3 font-medium">From → To</th>
                  <th className="py-2 pr-3 font-medium">Top reasons</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 font-medium">Time (Dhaka)</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((a) => (
                  <tr key={a.id} className="border-b border-line/70 transition-colors hover:bg-brand-soft/40">
                    <td className="py-2 pr-3">
                      <Link href={`/analyst/cases/${a.id}`} className="font-medium text-brand underline-offset-2 hover:underline">#{a.id}</Link>
                      {a.source === "live" && <span className="ml-1"><Pill tone="brand">live</Pill></span>}
                    </td>
                    <td className="py-2 pr-3"><DecisionBadge decision={a.decision} /></td>
                    <td className="tabular py-2 pr-3 text-right">{a.risk_score.toFixed(3)}</td>
                    <td className="tabular py-2 pr-3 text-right">{fmtBDT(a.amount)}</td>
                    <td className="py-2 pr-3 text-xs text-ink-2">{a.tx_type.replace("_", " ")}<br /><span className="text-ink">{a.sender} → {a.receiver}</span></td>
                    <td className="py-2 pr-3"><div className="flex max-w-xs flex-wrap gap-1">{a.reason_codes.slice(0, 2).map((r) => <Pill key={r}>{r.replace("R_", "")}</Pill>)}</div></td>
                    <td className="py-2 pr-3 text-xs">
                      {a.status.toLowerCase()}
                      {a.label && <span className="ml-1 text-muted">({a.label})</span>}
                      {a.customer_action && <div className="text-muted">customer {a.customer_action}</div>}
                    </td>
                    <td className="tabular py-2 text-xs text-ink-2">{fmtTime(a.tx_ts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.items.length === 0 && <p className="py-6 text-center text-sm text-muted">No alerts match these filters.</p>}
          </div>
        )}
        {data && (
          <div className="mt-3 flex items-center justify-between text-sm text-ink-2">
            <span className="tabular">{data.total.toLocaleString()} alerts</span>
            <div className="flex items-center gap-2">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-lg border border-line bg-surface px-3 py-1.5 shadow-card transition hover:bg-surface-2 disabled:opacity-40">Prev</button>
              <span className="tabular">{page} / {pages}</span>
              <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-lg border border-line bg-surface px-3 py-1.5 shadow-card transition hover:bg-surface-2 disabled:opacity-40">Next</button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
