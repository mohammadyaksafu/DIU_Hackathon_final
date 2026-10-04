"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { NetworkGraph } from "@/components/NetworkGraph";
import { Button, Card, DecisionBadge, ErrorBox, Pill, ScoreBar, Spinner, useApi, RiskLevel } from "@/components/ui";
import { api, fmtBDT, fmtTime } from "@/lib/api";
import type { CaseDetail, Contribution, Narrative, WalletGraph } from "@/lib/types";

const KEY_FEATURES: [string, string][] = [
  ["amount_ratio", "Amount vs usual (×)"],
  ["is_new_recipient", "New recipient"],
  ["r_new_senders_24h", "Recipient: new senders 24h"],
  ["r_tenure_days", "Recipient account age (days)"],
  ["s_tenure_days", "Sender account age (days)"],
  ["recent_device", "New / recent device"],
  ["hrs_since_sim_swap", "Hours since SIM swap"],
  ["hrs_since_pwd_reset", "Hours since PIN reset"],
  ["s_mins_since_inflow", "Minutes since last inflow"],
  ["r_fwd_ratio_24h", "Recipient forward ratio 24h"],
  ["r_g_comm_fanin", "Recipient community fan-in"],
  ["anomaly_score", "Behaviour anomaly percentile"],
];

function fmt(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(v >= 100 ? 0 : 2);
  return v == null ? "–" : String(v);
}

/** SHAP drivers as a diverging bar list: pushes-toward-fraud vs pushes-toward-legit. */
function Drivers({ items }: { items: Contribution[] }) {
  const max = Math.max(...items.map((c) => Math.abs(c.contribution)), 0.001);
  return (
    <div className="space-y-1.5">
      {items.slice(0, 8).map((c) => {
        const w = (Math.abs(c.contribution) / max) * 50;
        const pos = c.contribution > 0;
        return (
          <div key={c.feature} className="grid grid-cols-[minmax(0,10rem)_1fr_3.5rem] items-center gap-2 text-xs" title={`${c.feature} = ${fmt(c.value)}`}>
            <span className="truncate text-ink-2">{c.feature} <span className="text-muted">= {fmt(c.value)}</span></span>
            <div className="relative h-2.5">
              <div className="absolute left-1/2 top-[-2px] h-[14px] w-px bg-axis" />
              <div className={`absolute top-0 h-2.5 ${pos ? "rounded-r bg-series-2" : "rounded-l bg-series-1"}`}
                style={pos ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }} />
            </div>
            <span className="tabular text-right text-ink">{c.contribution > 0 ? "+" : ""}{c.contribution.toFixed(2)}</span>
          </div>
        );
      })}
      <div className="flex justify-between pt-1 text-[11px] text-muted">
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded-sm bg-series-1" />toward legitimate</span>
        <span className="flex items-center gap-1">toward fraud<span className="inline-block h-2 w-3 rounded-sm bg-series-2" /></span>
      </div>
    </div>
  );
}

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const kase = useApi(() => api<CaseDetail>(`/cases/${id}`, { role: "analyst" }), [id]);
  const c = kase.data;
  const focus = c ? (c.tx_type === "cash_out" ? c.sender : c.receiver) : null;
  const graph = useApi(() => (focus ? api<WalletGraph>(`/graph/wallet/${focus}`, { role: "analyst" }) : Promise.resolve(null)), [focus]);
  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [nLoading, setNLoading] = useState(false);
  const [nError, setNError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function summarize(refresh = false) {
    setNLoading(true);
    setNError(null);
    try {
      setNarrative(await api<Narrative>(`/copilot/case-summary/${id}${refresh ? "?refresh=true" : ""}`, { role: "analyst", method: "POST" }));
    } catch (e) {
      setNError((e as Error).message);
    } finally {
      setNLoading(false);
    }
  }

  async function label(l: "fraud" | "legit" | "unsure") {
    setSaving(true);
    setMsg(null);
    try {
      const r = await api<{ status: string; released: boolean }>(`/cases/${id}/feedback`, { role: "analyst", body: { label: l, notes } });
      setMsg(`Saved as ${l}. Status: ${r.status.toLowerCase()}${r.released ? " · held transfer released to the customer" : ""}.`);
      kase.reload();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (kase.loading && !c) return <Spinner label="Loading case" />;
  if (kase.error) return <ErrorBox error={kase.error} onRetry={kase.reload} />;
  if (!c) return null;

  const contributions = c.signals.lgbm?.details?.contributions ?? [];

  return (
    <div className="space-y-4">
      <Link href="/analyst" className="text-sm text-brand underline">← Alert queue</Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-ink">Case #{c.id}</h1>
        <DecisionBadge decision={c.decision} size="lg" />
        <RiskLevel score={c.risk_score} decision={c.decision} />
        <Pill>{c.status.toLowerCase()}{c.label ? ` · ${c.label}` : ""}</Pill>
        {c.customer_action && <Pill tone="brand">customer {c.customer_action}</Pill>}
        {c.ground_truth_scenario && <Pill>synthetic ground truth: {c.ground_truth_scenario}</Pill>}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="What happened" className="lg:col-span-2">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-muted">Type</dt><dd className="text-ink">{c.tx_type.replace("_", " ")}</dd></div>
            <div><dt className="text-xs text-muted">Amount</dt><dd className="tabular text-ink">{fmtBDT(c.amount)}</dd></div>
            <div><dt className="text-xs text-muted">Time (Dhaka)</dt><dd className="tabular text-ink">{fmtTime(c.tx_ts)}</dd></div>
            <div><dt className="text-xs text-muted">Model / policy</dt><dd className="text-xs text-ink">{c.model_version} · v{c.policy_version}</dd></div>
            <div className="col-span-2"><dt className="text-xs text-muted">Sender</dt><dd className="text-ink">{c.sender} <span className="text-xs text-ink-2">{fmt(c.sender_profile.persona)} · {fmt(c.sender_profile.division)}</span></dd></div>
            <div className="col-span-2"><dt className="text-xs text-muted">Receiver</dt><dd className="text-ink">{c.receiver} <span className="text-xs text-ink-2">{fmt(c.receiver_profile.persona)}</span></dd></div>
          </dl>
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Why it is risky</h3>
          <ul className="mt-2 space-y-2">
            {c.reasons.map((r) => (
              <li key={r.code} className="rounded-lg bg-surface-2 p-2.5 text-sm">
                <div className="text-ink">{r.en}</div>
                <div lang="bn" className="mt-0.5 text-ink-2">{r.bn}</div>
                <div className="mt-1 text-[11px] text-muted">{r.code}</div>
              </li>
            ))}
            {c.reasons.length === 0 && <li className="text-sm text-muted">No reason codes recorded.</li>}
          </ul>
        </Card>

        <Card title="Analyst decision" subtitle="Labels feed retraining. 'Legit' on a HOLD releases the transfer.">
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={2000} placeholder="Notes (optional)"
            className="w-full rounded-lg border border-line bg-surface p-2 text-sm" />
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Button variant="danger" disabled={saving} onClick={() => label("fraud")}>Fraud</Button>
            <Button variant="secondary" disabled={saving} onClick={() => label("legit")}>Legit</Button>
            <Button variant="ghost" disabled={saving} onClick={() => label("unsure")}>Unsure</Button>
          </div>
          {msg && <p className="mt-2 text-sm text-ink-2" role="status">{msg}</p>}
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Detector scores</h3>
          <div className="mt-2 space-y-2">
            {Object.values(c.signals).map((s) => <ScoreBar key={s.detector} label={s.detector} value={s.score} />)}
          </div>
          {c.signals.rules?.details?.hits && c.signals.rules.details.hits.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">{c.signals.rules.details.hits.map((h) => <Pill key={h}>rule {h}</Pill>)}</div>
          )}
        </Card>
      </div>

      <Card title="AI investigation copilot" subtitle="Grounded only in this case's evidence and the SOPs. It narrates; it never decides."
        actions={
          <div className="flex gap-2">
            <Button onClick={() => summarize(false)} disabled={nLoading}>{nLoading ? "Generating…" : narrative ? "Regenerate" : "Generate case summary"}</Button>
            {narrative && <Button variant="ghost" onClick={() => summarize(true)} disabled={nLoading}>Bypass cache</Button>}
          </div>
        }>
        {nError && <ErrorBox error={nError} />}
        {!narrative && !nLoading && <p className="text-sm text-muted">Generate a summary to get “what happened / why risky / what next” with SOP citations.</p>}
        {narrative && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <Pill tone="brand">{narrative.source === "llm" ? `AI-generated · ${narrative.model}` : "Rule-based summary (AI unavailable)"}</Pill>
              {narrative.cached && <Pill>cached</Pill>}
              {narrative.fallback_reason && <Pill>fallback: {narrative.fallback_reason}</Pill>}
            </div>
            <p className="font-medium text-ink">{narrative.summary}</p>
            <p className="text-ink-2">{narrative.what_happened}</p>
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Why risky</h4>
              <ul className="mt-1 space-y-1">
                {narrative.why_risky.map((w, i) => (
                  <li key={i} className="text-ink">• {w.point} <span className="text-xs text-muted">[{w.evidence.join(", ")}]</span></li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">Recommended next steps (human decision)</h4>
              <ol className="mt-1 list-decimal space-y-1 pl-5 text-ink">
                {narrative.recommended_actions.map((a, i) => <li key={i}>{a}</li>)}
              </ol>
            </div>
            <div className="flex flex-wrap gap-1">{narrative.citations.map((ct) => <Pill key={ct}>{ct}</Pill>)}</div>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`Money-flow network around ${focus}`} subtitle="2 hops, last 14 days. Hover a wallet for details.">
          {graph.loading ? <Spinner label="Building graph" /> : graph.error ? <ErrorBox error={graph.error} /> : graph.data ? <NetworkGraph graph={graph.data} /> : null}
        </Card>
        <Card title="Model drivers (SHAP)" subtitle="Contribution of each feature to this score, in log-odds">
          {contributions.length ? <Drivers items={contributions} /> : <p className="text-sm text-muted">No model explanation stored (rules-only decision).</p>}
          <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Key facts</h3>
          <table className="mt-1 w-full text-xs">
            <tbody>
              {KEY_FEATURES.filter(([k]) => k in c.features).map(([k, label]) => (
                <tr key={k} className="border-b border-line/70">
                  <td className="py-1 text-ink-2">{label}</td>
                  <td className="tabular py-1 text-right text-ink">{fmt(c.features[k])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Related alerts" subtitle={`${c.related.count} linked by sender/receiver · ${fmtBDT(c.related.total_amount_bdt)} · ${c.related.confirmed_fraud} confirmed fraud`}>
          <ul className="divide-y divide-line text-sm">
            {c.related.items.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 py-1.5">
                <Link href={`/analyst/cases/${r.id}`} className="text-brand underline">#{r.id}</Link>
                <span className="text-xs text-ink-2">{r.sender} → {r.receiver}</span>
                <span className="tabular text-xs">{fmtBDT(r.amount)}</span>
                <DecisionBadge decision={r.decision} />
              </li>
            ))}
            {c.related.items.length === 0 && <li className="py-2 text-muted">None.</li>}
          </ul>
        </Card>
        <Card title="Audit trail" subtitle="Append-only">
          <ol className="space-y-1.5 text-xs">
            {c.audit.map((a, i) => (
              <li key={i} className="flex gap-2">
                <span className="tabular shrink-0 text-muted">{new Date(a.ts * 1000).toLocaleTimeString()}</span>
                <span className="text-ink">{a.event}</span>
                <span className="text-ink-2">by {a.actor}</span>
              </li>
            ))}
            {c.audit.length === 0 && <li className="text-muted">Seeded historical alert (no live audit events yet).</li>}
          </ol>
        </Card>
      </div>
    </div>
  );
}
