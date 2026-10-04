"use client";

import { FormEvent, useState } from "react";

import { Button, Card, DecisionBadge, ErrorBox, Pill, RiskLevel, ScoreBar, Spinner, useApi } from "@/components/ui";
import { api, fmtBDT } from "@/lib/api";
import type { DemoCustomer, Scenario, ScenarioRun, ScoreResponse, TxPayload } from "@/lib/types";

type Lang = "bn" | "en";
const PERSONA_LABEL: Record<string, string> = {
  remittance_receiver: "Remittance receiver",
  garments_worker: "Garments worker",
  student: "Student",
  professional: "Professional",
  shopkeeper: "Shopkeeper",
  fcommerce_seller: "Online seller",
  freelancer: "Freelancer",
};
const TX_TYPES = ["send_money", "payment", "cash_out"];
const EXPECTED_BN: Record<string, string> = { ALLOW: "অনুমোদন (ALLOW)", "WARN/HOLD": "সতর্কতা বা স্থগিত (WARN/HOLD)", HOLD: "স্থগিত (HOLD)" };
const TX_TYPE_BN: Record<string, string> = { send_money: "সেন্ড মানি", payment: "পেমেন্ট", cash_out: "ক্যাশ আউট" };
// Bangla explanation for every field of the /score request body, in the order it is sent.
const FIELD_BN: { key: keyof TxPayload; label: string; help: string }[] = [
  { key: "type", label: "লেনদেনের ধরন", help: "প্রতিটি ধরনের জন্য ঝুঁকির নিয়ম আলাদা" },
  { key: "sender", label: "প্রেরক ওয়ালেট", help: "কে টাকা পাঠাচ্ছেন (সাইন ইন করা গ্রাহক)" },
  { key: "receiver", label: "প্রাপক ওয়ালেট", help: "কার কাছে টাকা যাচ্ছে; নতুন বা সন্দেহজনক কিনা দেখা হয়" },
  { key: "amount", label: "পরিমাণ (টাকা)", help: "গ্রাহকের স্বাভাবিক অঙ্কের সাথে তুলনা করা হয়" },
  { key: "device_id", label: "ফোন / ডিভাইস", help: "নিজের পুরনো ফোন নাকি নতুন ফোন" },
  { key: "geo_cell", label: "এলাকা", help: "গ্রাহকের নিজের এলাকা নাকি অন্য জায়গা" },
  { key: "channel", label: "চ্যানেল", help: "অ্যাপ থেকে লেনদেন" },
];
const SAFETY_EXAMPLES = [
  {
    title: "পুরস্কার জিতেছেন",
    category: "Prize fee scam",
    sender: "অচেনা নম্বর",
    message: "অভিনন্দন! আপনি পুরস্কার জিতেছেন। পুরস্কার পেতে আগে ২,০০০ টাকা পাঠান।",
    warning: "পুরস্কার পাওয়ার আগে টাকা চাইছে",
    advice: "পুরস্কার পাওয়ার জন্য আগে টাকা পাঠাবেন না। পরিচিত অফিসিয়াল নম্বরে যাচাই করুন।",
    demoWallet: "DEMO-PRIZE-01",
    demoAmount: "৳ ২,০০০",
  },
  {
    title: "ভুল করে টাকা পাঠিয়েছি",
    category: "Refund scam",
    sender: "অচেনা নম্বর",
    message: "ভাই, ভুল করে টাকা গেছে। দয়া করে এই অন্য নম্বরে এখনই ফেরত দিন।",
    warning: "ভিন্ন নম্বরে টাকা ফেরত দিতে বলছে",
    advice: "অপরিচিত কারও কথায় অন্য নম্বরে টাকা পাঠাবেন না। লেনদেনের ইতিহাস দেখে অফিসিয়াল সহায়তা নিন।",
    demoWallet: "DEMO-REFUND-02",
    demoAmount: "৳ ৫,০০০",
  },
  {
    title: "OTP বা PIN জানতে চাওয়া",
    category: "Account takeover",
    sender: "ভুয়া সহায়তাকারী",
    message: "আপনার অ্যাকাউন্ট বন্ধ হবে। যাচাইয়ের জন্য OTP আর PIN বলুন।",
    warning: "OTP/PIN চাইছে বা অ্যাকাউন্ট বন্ধের ভয় দেখাচ্ছে",
    advice: "OTP, PIN বা পাসওয়ার্ড কাউকে বলবেন না। upay-এর কর্মীও এগুলো চাইবেন না।",
    demoWallet: "DEMO-FAKE-HELP-03",
    demoAmount: "৳ ১২,০০০",
  },
  {
    title: "তাড়াহুড়া করে টাকা পাঠাতে বলা",
    category: "Social engineering",
    sender: "ফোনে অপরিচিত ব্যক্তি",
    message: "এখনই টাকা পাঠান, কাউকে বলবেন না। পরে সব বুঝিয়ে বলছি।",
    warning: "গোপন রাখতে ও দ্রুত সিদ্ধান্ত নিতে চাপ দিচ্ছে",
    advice: "চাপ দিলে থামুন। প্রাপক ও নম্বর আবার যাচাই করুন, সন্দেহ হলে পাঠাবেন না।",
    demoWallet: "DEMO-UNKNOWN-04",
    demoAmount: "৳ ৮,০০০",
  },
];

export default function CustomerPage() {
  const customers = useApi(() => api<DemoCustomer[]>("/simulator/customers", { role: "customer" }));
  const [picked, setPicked] = useState("");
  // null = the default transfer for the signed-in customer; set once the user or a scenario edits it.
  const [txEdit, setTx] = useState<TxPayload | null>(null);
  const [amountEdit, setAmountInput] = useState<string | null>(null);
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>("bn");
  const scenarios = useApi(() => api<Scenario[]>("/simulator/scenarios", { role: "customer" }));
  const [active, setActive] = useState<{ scenario: Scenario; run: ScenarioRun } | null>(null);
  const [tab, setTab] = useState<"demo" | "ai" | "learn">("demo");
  const TABS = [
    { key: "demo", label: "① ডেমো পরিস্থিতি", hint: "Scenarios" },
    { key: "ai", label: "② এআই কী দেখল", hint: "What the AI saw" },
    { key: "learn", label: "③ প্রতারণা চিনুন", hint: "Learn" },
  ] as const;

  const cid = picked || customers.data?.[0]?.id || "";
  const customer = customers.data?.find((c) => c.id === cid) ?? null;
  const tx: TxPayload | null = txEdit ?? (customer
    ? { type: "send_money", amount: Math.round((customer.typical_amount ?? 500) / 10) * 10, sender: customer.id, receiver: "", device_id: customer.device_id, geo_cell: customer.home_geo, channel: "app" }
    : null);
  const amountInput = amountEdit ?? (tx ? String(tx.amount) : "");

  function chooseCustomer(id: string) {
    setPicked(id);
    setTx(null);
    setAmountInput(null);
    setResult(null);
    setOutcome(null);
    setActive(null);
  }

  /** Ask the backend to prepare a scenario (it records any context, e.g. a SIM swap) and fill the form. */
  async function runScenario(sc: Scenario) {
    if (!customer) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setOutcome(null);
    try {
      const run = await api<ScenarioRun>("/simulator/scenarios/run", { role: "customer", body: { customer_id: customer.id, scenario: sc.key } });
      setTx(run.transaction);
      setAmountInput(String(run.transaction.amount));
      setActive({ scenario: sc, run });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function send(ev?: FormEvent) {
    ev?.preventDefault();
    const amount = Number(amountInput);
    if (!tx || !tx.receiver || !Number.isFinite(amount) || amount <= 0) return;
    setBusy(true);
    setError(null);
    setOutcome(null);
    try {
      const r = await api<ScoreResponse>("/score", { role: "customer", body: { ...tx, amount } });
      setResult(r);
      if (r.decision === "ALLOW") await confirm(r, "sent");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirm(r: ScoreResponse, action: "sent" | "cancelled") {
    const res = await api<{ status: string }>(`/transactions/${r.transaction_id}/confirm`, { role: "customer", body: { action } });
    setOutcome(res.status);
  }

  if (customers.loading) return <Spinner label="Loading demo customers" />;
  if (customers.error) return <ErrorBox error={customers.error} onRetry={customers.reload} />;

  const msg = result?.customer_message[lang];
  // Exactly what the Send button posts to /score.
  const payload: TxPayload | null = tx ? { ...tx, amount: Number(amountInput) || 0 } : null;
  const edited = !!(active && payload && (payload.receiver !== active.run.transaction.receiver || payload.amount !== active.run.transaction.amount || payload.type !== active.run.transaction.type));

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(400px,0.9fr)_minmax(440px,1.1fr)]">
      <section className="space-y-3 xl:sticky xl:top-28">
        <div>
          <p className="text-xs font-semibold uppercase text-brand">upay · secure demo wallet</p>
          <h1 className="mt-1 text-xl font-semibold text-ink">আপনার ওয়ালেট</h1>
          <p className="mt-1 text-sm text-ink-2">টাকা পাঠানোর আগে প্রাপক ও পরিমাণ যাচাই করুন।</p>
        </div>
        <div className="mx-auto w-full max-w-[480px]">
          <div className="rounded-[2rem] border-8 border-ink/85 bg-surface shadow-xl">
            <div className="rounded-t-[1.4rem] bg-brand px-5 pb-5 pt-4 text-brand-ink">
              <div className="flex items-center justify-between text-xs opacity-90">
                <span>{lang === "bn" ? "upay · ডেমো ওয়ালেট" : "upay · demo wallet"}</span>
                <button onClick={() => setLang(lang === "bn" ? "en" : "bn")} className="rounded-full border border-current px-2 py-0.5"
                  aria-label="Switch language" aria-pressed={lang === "en"}>
                  {lang === "bn" ? "English" : "বাংলা"}
                </button>
              </div>
              <label className="mt-3 block text-xs opacity-90" htmlFor="cust">{lang === "bn" ? "যে গ্রাহক হিসেবে লগইন" : "Signed in as"}</label>
              <select id="cust" value={cid} onChange={(e) => chooseCustomer(e.target.value)}
                className="mt-1 w-full rounded-lg bg-white/15 px-2 py-1.5 text-sm text-brand-ink [&>option]:text-black">
                {customers.data?.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} · {PERSONA_LABEL[c.persona] ?? c.persona}</option>
                ))}
              </select>
              {customer && <div className="mt-2 text-xs opacity-90">{customer.id} · {customer.division} · {lang === "bn" ? "সাধারণ লেনদেন" : "usual transfer"} ≈ {fmtBDT(customer.typical_amount)}</div>}
            </div>

            <form onSubmit={send} className="space-y-3 p-5">
              <h2 className="text-sm font-semibold text-ink">{lang === "bn" ? "টাকা পাঠান" : "Send money"}</h2>
              <div className="grid grid-cols-3 gap-1 rounded-lg bg-surface-2 p-1">
                {TX_TYPES.map((t) => (
                  <button type="button" key={t} onClick={() => tx && setTx({ ...tx, type: t })}
                    className={`rounded-md px-2 py-1.5 text-xs ${tx?.type === t ? "bg-surface font-medium text-ink shadow-sm" : "text-ink-2"}`}>
                    {lang === "bn" ? TX_TYPE_BN[t] : t.replace("_", " ")}
                  </button>
                ))}
              </div>
              <label className="block text-xs text-ink-2">
                {lang === "bn" ? "প্রাপকের ওয়ালেট" : "Receiver wallet"}
                <input value={tx?.receiver ?? ""} onChange={(e) => tx && setTx({ ...tx, receiver: e.target.value.trim() })}
                  placeholder="e.g. C00012" className="mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink" required pattern="[A-Za-z0-9_\-]{2,32}" />
              </label>
              <label className="block text-xs text-ink-2">
                {lang === "bn" ? "পরিমাণ (টাকা)" : "Amount (BDT)"}
                <input type="number" min={1} max={1000000} value={amountInput} onChange={(e) => {
                  if (!tx) return;
                  const value = e.target.value.replace(/^0+(?=\d)/, "");
                  setAmountInput(value);
                  if (value !== "") setTx({ ...tx, amount: Number(value) });
                }}
                  className="tabular mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink" required />
              </label>
              {tx?.device_id && tx.device_id !== customer?.device_id && <Pill>{lang === "bn" ? "ভিন্ন ফোন থেকে" : "Using a different phone"}: {tx.device_id}</Pill>}
              <Button type="submit" disabled={busy || !tx?.receiver || !amountInput || Number(amountInput) <= 0} className="w-full">{busy ? "…" : lang === "bn" ? "পাঠান" : "Send"}</Button>
              {error && <ErrorBox error={error} />}
            </form>

            {result && msg && (
              <div className="border-t border-line p-5" aria-live="polite">
                <div className={`rounded-xl border p-4 ${result.decision === "ALLOW" ? "border-good/40 bg-good-soft" : result.decision === "WARN" ? "border-warning/50 bg-warning-soft" : "border-critical/40 bg-critical-soft"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <h3 lang={lang} className="font-semibold text-ink">{msg.title}</h3>
                    <DecisionBadge decision={result.decision} />
                  </div>
                  {msg.reasons.length > 0 && (
                    <ul lang={lang} className="mt-2 space-y-1.5 text-sm text-ink">
                      {msg.reasons.map((r) => <li key={r}>• {r}</li>)}
                    </ul>
                  )}
                  <p lang={lang} className="mt-2 text-xs text-ink-2">{msg.body}</p>
                  {!outcome && result.decision === "WARN" && (
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <Button onClick={() => confirm(result, "cancelled")}>{lang === "bn" ? "বাতিল করুন" : "Cancel"}</Button>
                      <Button variant="secondary" onClick={() => confirm(result, "sent")}>{lang === "bn" ? "তবুও পাঠান" : "Send anyway"}</Button>
                    </div>
                  )}
                  {!outcome && result.decision === "HOLD" && (
                    <div className="mt-3 grid grid-cols-1 gap-2">
                      <Button onClick={() => confirm(result, "cancelled")}>{lang === "bn" ? "লেনদেন বাতিল করুন" : "Cancel this transfer"}</Button>
                      <p className="text-center text-xs text-ink-2">{lang === "bn" ? "অথবা আমাদের টিমের যাচাইয়ের জন্য অপেক্ষা করুন" : "Or wait for our team to verify it"}</p>
                    </div>
                  )}
                  {outcome && (
                    <p className="mt-3 text-sm font-medium text-ink">
                      {outcome === "SENT" ? (lang === "bn" ? "✓ টাকা পাঠানো হয়েছে" : "✓ Money sent") : (lang === "bn" ? "✓ বাতিল হয়েছে, আপনার টাকা নিরাপদ" : "✓ Cancelled. Your money is safe")}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ---------- right: one panel with three tabs, so the page stays short ---------- */}
      <section aria-label="Demo panel" className="min-w-0 space-y-4">
        <div role="tablist" aria-label="Demo panel" className="grid grid-cols-3 gap-1 rounded-2xl border border-line bg-surface-2/70 p-1">
          {TABS.map((t) => (
            <button key={t.key} role="tab" type="button" id={`tab-${t.key}`} aria-selected={tab === t.key} aria-controls={`panel-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`rounded-xl px-2 py-2 text-center transition ${tab === t.key ? "bg-surface text-brand shadow-card" : "text-ink-2 hover:bg-surface/60"}`}>
              <span lang="bn" className="block text-sm font-semibold">{t.label}{t.key === "ai" && result ? " ●" : ""}</span>
              <span className="block text-[10px] text-muted">{t.hint}</span>
            </button>
          ))}
        </div>

        {tab === "demo" && (
          <div role="tabpanel" id="panel-demo" aria-labelledby="tab-demo" className="space-y-4">
          <Card title={<span lang="bn">ডেমো পরিস্থিতি বেছে নিন</span>}
            subtitle={<span lang="bn">একটি পরিস্থিতিতে চাপ দিলে ব্যাকএন্ড প্রয়োজনীয় প্রেক্ষাপট তৈরি করে ফর্মটি পূরণ করবে। তারপর <strong>পাঠান</strong> চাপুন।</span>}>
            {scenarios.loading ? <Spinner label="লোড হচ্ছে" /> : scenarios.error ? <ErrorBox error={scenarios.error} onRetry={scenarios.reload} /> : (
              <div className="grid gap-2">
                {scenarios.data?.map((sc) => {
                  const on = active?.scenario.key === sc.key;
                  const risky = sc.expected !== "ALLOW";
                  return (
                    <button key={sc.key} type="button" onClick={() => runScenario(sc)} disabled={busy || !customer} aria-pressed={on}
                      className={`rounded-xl border p-3 text-left transition disabled:opacity-50 ${on ? "border-brand bg-brand-soft shadow-card" : "border-line bg-surface hover:border-brand/50 hover:bg-surface-2"}`}>
                      <div className="flex items-start justify-between gap-2">
                        <span>
                          <span lang="bn" className="block text-sm font-semibold text-ink">{sc.title_bn ?? sc.title}</span>
                          <span className="block text-[11px] text-muted">{sc.title}</span>
                        </span>
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${risky ? "bg-critical-soft text-critical-text" : "bg-good-soft text-good-text"}`}>
                          {EXPECTED_BN[sc.expected] ?? sc.expected}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </Card>

          {active && (
            <Card title={<span lang="bn">পরিস্থিতির গল্প: {active.scenario.title_bn ?? active.scenario.title}</span>}>
              <p lang="bn" className="text-sm leading-6 text-ink">{active.scenario.story_bn ?? active.scenario.description}</p>
              {(active.run.setup_bn?.length ?? 0) > 0 && (
                <div className="mt-3 rounded-xl border border-warning/50 bg-warning-soft p-3">
                  <p lang="bn" className="text-xs font-semibold text-warning-text">ব্যাকএন্ডে আগে থেকে রেকর্ড করা ঘটনা</p>
                  <ul lang="bn" className="mt-1 space-y-1 text-sm text-ink">
                    {active.run.setup_bn!.map((x) => <li key={x}>• {x}</li>)}
                  </ul>
                  <p lang="bn" className="mt-1 text-[11px] text-ink-2">এগুলো ফর্মে দেখা যায় না, কিন্তু ঝুঁকি হিসাবের সময় ব্যাকএন্ড এগুলো বিবেচনা করে।</p>
                </div>
              )}
            </Card>
          )}
          {result && (
            <button type="button" onClick={() => setTab("ai")} className="w-full rounded-xl border border-brand/30 bg-brand-soft px-4 py-3 text-left text-sm font-semibold text-brand">
              <span lang="bn">ফলাফল এসেছে: এআই কী দেখল এবং কেন এই সিদ্ধান্ত, দেখুন →</span>
            </button>
          )}
          </div>
        )}

        {tab === "ai" && (
          <div role="tabpanel" id="panel-ai" aria-labelledby="tab-ai" className="space-y-4">
          {payload && (
            <Card title={<span lang="bn">ব্যাকএন্ডে যে ডেটা পাঠানো হবে</span>}
              subtitle={<span><code className="rounded bg-surface-2 px-1.5 py-0.5 text-ink">POST /api/v1/score</code> <span lang="bn">· পাঠান চাপলে ঠিক এই ডেটা যায়</span></span>}
              actions={edited ? <Pill>ফর্ম বদলানো হয়েছে</Pill> : undefined}>
              <dl className="divide-y divide-line overflow-hidden rounded-xl border border-line">
                {FIELD_BN.map((f) => {
                  const raw = payload[f.key];
                  const value = raw == null || raw === "" ? "—" : f.key === "amount" ? `${raw}  (${fmtBDT(Number(raw))})` : String(raw);
                  const flag = (f.key === "device_id" && customer && raw && raw !== customer.device_id) || (f.key === "geo_cell" && customer && raw && raw !== customer.home_geo);
                  return (
                    <div key={f.key} className={`grid grid-cols-[minmax(0,9rem)_1fr] gap-3 px-3 py-2 text-sm ${flag ? "bg-critical-soft/60" : ""}`}>
                      <dt>
                        <span lang="bn" className="block font-medium text-ink">{f.label}</span>
                        <code className="text-[11px] text-muted">{f.key}</code>
                      </dt>
                      <dd className="min-w-0">
                        <span className="tabular block break-all font-mono text-ink">{value}</span>
                        <span lang="bn" className="block text-[11px] text-ink-2">
                          {flag ? (f.key === "device_id" ? `নতুন ফোন! গ্রাহকের নিজের ফোন ${customer?.device_id}` : `অন্য এলাকা! গ্রাহকের নিজের এলাকা ${customer?.home_geo}`) : f.key === "type" && raw ? `${TX_TYPE_BN[String(raw)] ?? raw} · ${f.help}` : f.help}
                        </span>
                      </dd>
                    </div>
                  );
                })}
              </dl>
              <details className="mt-3">
                <summary className="cursor-pointer text-xs font-medium text-brand">JSON দেখুন (raw request body)</summary>
                <pre className="mt-2 overflow-x-auto rounded-xl bg-surface-2 p-3 text-xs leading-relaxed text-ink">{JSON.stringify(payload, null, 2)}</pre>
              </details>
              {!active && <p lang="bn" className="mt-2 text-[11px] text-muted">কোনো পরিস্থিতি বাছাই করা হয়নি: এটি আপনার নিজের লেখা লেনদেন।</p>}
            </Card>
          )}
        <Card title="Behind the scenes" subtitle="For judges and analysts: how the risk engine reached its decision. Customers only see the plain-language card in the phone.">
          {!result ? (
            <p className="text-sm text-muted">Send a transfer to see the decision trace.</p>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <DecisionBadge decision={result.decision} size="lg" />
                <RiskLevel score={result.risk_score} decision={result.decision} warnT={result.policy.variables.warn_t} holdT={result.policy.variables.hold_t} />
                <span className="tabular text-sm text-ink-2">latency <strong className="text-ink">{result.latency_ms} ms</strong></span>
                <Pill>model {result.model_version}</Pill>
                <Pill>policy v{result.policy_version}</Pill>
                {result.degraded && <Pill>degraded: {result.degraded_reasons.join(", ")}</Pill>}
              </div>
              <div className="space-y-2">
                {result.signals.map((s) => (
                  <ScoreBar key={s.detector} label={`${s.detector}${s.ok ? "" : " (failed)"}`} value={s.score}
                    threshold={s.detector === "lgbm" ? result.policy.variables.warn_t : undefined} />
                ))}
                <p className="text-[11px] text-muted">Tick on the lgbm bar = WARN threshold for this customer segment{result.policy.overrides.length ? ` (override: ${result.policy.overrides.join(", ")})` : ""}.</p>
              </div>
              <div>
                <div className="text-xs font-medium text-ink-2">Reason codes</div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {result.reason_codes.length ? result.reason_codes.map((r) => <Pill key={r} tone="brand">{r}</Pill>) : <span className="text-xs text-muted">none (allowed)</span>}
                </div>
              </div>
              <div className="rounded-xl bg-surface-2 p-3 text-xs leading-relaxed text-ink-2">
                <strong className="text-ink">Why {result.decision}?</strong> The decision comes from the policy, not from the number alone. The first matching rule was{" "}
                <code className="rounded bg-surface px-1 py-0.5 text-ink">{result.policy.matched}</code>.
                {" "}Typical legitimate transfers score below {((result.policy.variables.warn_t ?? 0.05) * 100).toFixed(0)}%; fraud is about 1% of transfers, so a probability of a few percent is already unusual.
              </div>
              {result.alert_id && (
                <a href={`/analyst/cases/${result.alert_id}`} className="inline-block text-sm font-medium text-brand underline">
                  Open alert #{result.alert_id} in the analyst console →
                </a>
              )}
            </div>
          )}
        </Card>
          </div>
        )}

        {tab === "learn" && (
          <div role="tabpanel" id="panel-learn" aria-labelledby="tab-learn" className="space-y-4">
        <div className="border-l-4 border-warning bg-warning-soft p-4 sm:p-5">
          <p className="text-xs font-semibold uppercase text-warning-text">নিরাপত্তা বার্তা · Safety notice</p>
          <h2 id="safety-title" className="mt-1 text-lg font-semibold text-ink">সন্দেহ হলে থামুন, যাচাই করুন</h2>
          <p lang="bn" className="mt-2 text-sm leading-6 text-ink">
            কাউকে OTP বা PIN দেবেন না। পুরস্কার, ভুল লেনদেন ফেরত, বা অ্যাকাউন্ট বাঁচানোর নামে আগে টাকা পাঠাবেন না।
            টাকা পাঠানোর আগে প্রাপকের নাম ও নম্বর নিশ্চিত করুন।
          </p>
          <p className="mt-2 text-xs text-ink-2">এই সতর্কতাগুলো শুধু শেখার জন্য। নিচের উদাহরণগুলো আপনার ওয়ালেটের তথ্য বদলায় না এবং কোনো লেনদেন শুরু করে না।</p>
        </div>

        <Card title="প্রতারণার উদাহরণ" subtitle="একটি বিষয় খুলে লক্ষণ ও করণীয় দেখুন">
          <div className="divide-y divide-line">
            {SAFETY_EXAMPLES.map((example) => (
              <details key={example.category} className="group py-3 first:pt-0 last:pb-0">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-left">
                  <span>
                    <span className="block text-sm font-medium text-ink">{example.title}</span>
                    <span className="mt-0.5 block text-xs text-muted">{example.category}</span>
                  </span>
                  <span aria-hidden="true" className="text-lg text-brand transition-transform group-open:rotate-45">+</span>
                </summary>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-line bg-surface-2 p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-ink">নমুনা কথোপকথন</span>
                      <span className="text-[10px] font-medium uppercase text-muted">শুধু উদাহরণ</span>
                    </div>
                    <div className="space-y-2 rounded-md bg-surface p-3">
                      <p className="text-[11px] text-muted">{example.sender}</p>
                      <p lang="bn" className="max-w-[95%] rounded-lg rounded-tl-sm bg-brand-soft p-2.5 text-sm leading-6 text-ink">{example.message}</p>
                    </div>
                  </div>
                  <div className="border-l-2 border-warning pl-3">
                    <p className="text-xs font-semibold text-warning-text">সন্দেহের লক্ষণ</p>
                    <p lang="bn" className="mt-1 text-sm font-medium leading-6 text-ink">{example.warning}</p>
                    <p className="mt-3 text-xs font-semibold text-ink-2">আপনি কী করবেন</p>
                    <p lang="bn" className="mt-1 text-sm leading-6 text-ink-2">{example.advice}</p>
                  </div>
                  <details className="group sm:col-span-2">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 border-t border-line pt-3 text-left">
                      <span>
                        <span className="block text-sm font-semibold text-brand">ওয়ালেটে নমুনাটি দেখুন</span>
                        <span className="mt-0.5 block text-xs text-muted">আলাদা, নিরাপদ ডেমো · আসল ওয়ালেটের সঙ্গে যুক্ত নয়</span>
                      </span>
                      <span aria-hidden="true" className="text-lg text-brand transition-transform group-open:rotate-45">+</span>
                    </summary>
                    <div className="mt-3 max-w-sm rounded-xl border border-warning/60 bg-surface p-4">
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-ink">ডেমো ওয়ালেট</span>
                        <span className="rounded bg-warning-soft px-2 py-1 text-[10px] font-bold text-warning-text">শুধু অনুশীলন</span>
                      </div>
                      <div className="space-y-3 rounded-lg bg-surface-2 p-3">
                        <div>
                          <p className="text-[11px] text-muted">নমুনা প্রাপকের নম্বর</p>
                          <p className="mt-0.5 font-mono text-sm font-semibold text-ink">{example.demoWallet}</p>
                        </div>
                        <div>
                          <p className="text-[11px] text-muted">পাঠাতে বলা পরিমাণ</p>
                          <p className="mt-0.5 text-lg font-semibold text-ink">{example.demoAmount}</p>
                        </div>
                        <button type="button" disabled className="w-full rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-brand-ink opacity-70">
                          ডেমো: টাকা পাঠানো বন্ধ
                        </button>
                      </div>
                      <p lang="bn" className="mt-2 text-xs leading-5 text-warning-text">এই নম্বর ও পরিমাণ কাল্পনিক। বোতামটি নিষ্ক্রিয়; কোনো লেনদেন হবে না।</p>
                    </div>
                  </details>
                </div>
              </details>
            ))}
          </div>
        </Card>
          </div>
        )}
      </section>
    </div>
  );
}
