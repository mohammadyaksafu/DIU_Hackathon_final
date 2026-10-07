"use client";

import { useState } from "react";

import { Button, Card, ErrorBox, PageHeader, Spinner, useApi } from "@/components/ui";
import { api, fmtBDT, fmtPct } from "@/lib/api";

interface StudyScenario {
  key: string;
  is_scam: boolean;
  context_bn: string;
  receiver: string;
  amount: number;
  reasons_bn: string[];
}
interface StudyConfig {
  arms: Record<string, string>;
  generic_warning_bn: string;
  scenarios: StudyScenario[];
}
interface ArmResult {
  participants: number;
  scam_decisions: number;
  scam_cancel_rate: number | null;
  scam_cancel_ci95: [number, number] | null;
  legit_decisions: number;
  legit_continue_rate: number | null;
  legit_continue_ci95: [number, number] | null;
  median_seconds: number | null;
  mean_trust: number | null;
  complaint_rate?: number | null;
  complaint_ci95?: [number, number] | null;
}
interface Results {
  participants: number;
  status: string;
  arms: Record<string, ArmResult>;
}
interface Answer {
  scenario: string;
  action: "sent" | "cancelled";
  seconds: number;
}

const ARM_LABEL: Record<string, string> = { A: "A · no warning", B: "B · generic warning", C: "C · Shurokkha explained warning" };
const ci = (c: [number, number] | null) => (c ? ` (${fmtPct(c[0], 0)}–${fmtPct(c[1], 0)})` : "");

export default function StudyPage() {
  const config = useApi(() => api<StudyConfig>("/study/scenarios", { role: "customer" }));
  const results = useApi(() => api<Results>("/study/results", { role: "analyst" }));
  const [consent, setConsent] = useState(false);
  const [who, setWho] = useState<{ participant: string; arm: string } | null>(null);
  const [step, setStep] = useState(0);
  const [stage, setStage] = useState<"transfer" | "confirm">("transfer");
  const [shownAt, setShownAt] = useState(0);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [trust, setTrust] = useState<number | null>(null);
  const [complaint, setComplaint] = useState<boolean | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (config.loading) return <Spinner label="Loading study" />;
  if (config.error || !config.data) return <ErrorBox error={config.error ?? "Study unavailable"} onRetry={config.reload} />;
  const scenarios = config.data.scenarios;
  const current = who && step < scenarios.length ? scenarios[step] : null;

  async function start() {
    setError(null);
    try {
      const r = await api<{ participant: string; arm: string }>("/study/participants", { role: "customer", method: "POST" });
      setWho(r);
      setStep(0);
      setStage("transfer");
      setAnswers([]);
      setDone(false);
      setTrust(null);
      setComplaint(null);
      setShownAt(performance.now());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function decide(action: "sent" | "cancelled") {
    if (!current) return;
    setAnswers([...answers, { scenario: current.key, action, seconds: Math.round((performance.now() - shownAt) / 100) / 10 }]);
    setStep(step + 1);
    setStage("transfer");
    setShownAt(performance.now());
  }

  async function finish() {
    if (!who) return;
    setError(null);
    try {
      for (const a of answers) {
        await api("/study/responses", { role: "customer", body: { participant: who.participant, arm: who.arm, ...a, trust, complaint } });
      }
      setDone(true);
      results.reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // What the participant sees after pressing "Send", by arm.
  const warning = current && who
    ? who.arm === "A" ? null
      : who.arm === "B" ? [config.data.generic_warning_bn]
        : current.reasons_bn.length ? current.reasons_bn : null
    : null;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Measured, not assumed" title="WARN user study"
        description="A short, anonymous experiment that measures how many people cancel a scam transfer after a warning, and how many still complete genuine payments. Participants are randomly assigned to one of three arms." />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(320px,440px)_1fr]">
        <Card title={<span lang="bn">অংশগ্রহণকারীর স্ক্রিন</span>}>
          {!who || done ? (
            <div className="space-y-3 text-sm">
              {done && <p lang="bn" className="rounded-lg bg-good-soft p-3 text-good-text">ধন্যবাদ! আপনার উত্তর জমা হয়েছে।</p>}
              <p lang="bn" className="leading-6 text-ink">
                এটি একটি ছোট গবেষণা। আপনাকে ৬টি টাকা পাঠানোর পরিস্থিতি দেখানো হবে। প্রতিটিতে আপনি নিজে হলে কী করতেন, তা বেছে নিন।
                কোনো আসল টাকা নেই, নাম বা ফোন নম্বর নেওয়া হয় না, যেকোনো সময় থামতে পারেন।
              </p>
              <label className="flex items-start gap-2 text-ink">
                <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span lang="bn">আমি বুঝেছি এবং স্বেচ্ছায় অংশ নিতে রাজি।</span>
              </label>
              <Button disabled={!consent} onClick={start} className="w-full">{done ? "Next participant" : "শুরু করুন · Start"}</Button>
            </div>
          ) : current ? (
            <div className="space-y-3">
              <p className="text-xs text-muted">Transfer {step + 1} of {scenarios.length} · participant {who.participant}</p>
              <p lang="bn" className="rounded-lg bg-surface-2 p-3 text-sm leading-6 text-ink">{current.context_bn}</p>
              <dl className="grid grid-cols-[6rem_1fr] gap-1 text-sm">
                <dt lang="bn" className="text-ink-2">প্রাপক</dt><dd lang="bn" className="text-ink">{current.receiver}</dd>
                <dt lang="bn" className="text-ink-2">পরিমাণ</dt><dd className="tabular text-ink">{fmtBDT(current.amount)}</dd>
              </dl>
              {stage === "transfer" ? (
                <div className="grid grid-cols-2 gap-2">
                  <Button onClick={() => (warning ? setStage("confirm") : decide("sent"))}><span lang="bn">পাঠান</span></Button>
                  <Button variant="secondary" onClick={() => decide("cancelled")}><span lang="bn">পাঠাব না</span></Button>
                </div>
              ) : (
                <div className="rounded-xl border border-warning/50 bg-warning-soft p-3">
                  <p lang="bn" className="font-semibold text-ink">একটু থামুন, এটি প্রতারণা হতে পারে</p>
                  <ul lang="bn" className="mt-1 space-y-1 text-sm text-ink">{warning!.map((w) => <li key={w}>• {w}</li>)}</ul>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <Button onClick={() => decide("cancelled")}><span lang="bn">বাতিল করুন</span></Button>
                    <Button variant="secondary" onClick={() => decide("sent")}><span lang="bn">তবুও পাঠান</span></Button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <p lang="bn" className="text-ink">শেষ প্রশ্ন: এই অ্যাপের সতর্কবার্তায় আপনি কতটা ভরসা করবেন? (১ = একদম না, ৫ = পুরোপুরি)</p>
              <div className="flex gap-2" role="radiogroup" aria-label="Trust rating">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} type="button" role="radio" aria-checked={trust === n} onClick={() => setTrust(n)}
                    className={`h-10 w-10 rounded-lg border ${trust === n ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink"}`}>{n}</button>
                ))}
              </div>
              <p lang="bn" className="text-ink">এই অ্যাপ সতর্কবার্তা দেখালে আপনি কি upay-এর কাছে অভিযোগ করতেন?</p>
              <div className="flex gap-2" role="radiogroup" aria-label="Complaint intent">
                {[{ v: true, l: "হ্যাঁ" }, { v: false, l: "না" }].map((o) => (
                  <button key={o.l} type="button" role="radio" aria-checked={complaint === o.v} onClick={() => setComplaint(o.v)}
                    className={`h-10 rounded-lg border px-4 ${complaint === o.v ? "border-brand bg-brand text-brand-ink" : "border-line bg-surface text-ink"}`}>{o.l}</button>
                ))}
              </div>
              <Button onClick={finish} disabled={trust == null || complaint == null} className="w-full">Submit</Button>
            </div>
          )}
          {error && <div className="mt-3"><ErrorBox error={error} /></div>}
        </Card>

        <Card title="Results so far" subtitle="95% Wilson confidence intervals. Arm C's scam-cancel rate replaces the assumed 60% once enough people have taken part."
          actions={<button type="button" onClick={results.reload} className="text-xs font-medium text-brand underline">Refresh</button>}>
          {results.loading && !results.data ? <Spinner /> : results.error ? <ErrorBox error={results.error} onRetry={results.reload} /> : results.data && (
            <>
              <p className="mb-3 text-sm text-ink-2">{results.data.participants} participants · {results.data.status}</p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                      <th className="py-2 pr-3 font-medium">Arm</th>
                      <th className="py-2 pr-3 font-medium">People</th>
                      <th className="py-2 pr-3 font-medium">Scams cancelled</th>
                      <th className="py-2 pr-3 font-medium">Genuine payments completed</th>
                      <th className="py-2 pr-3 font-medium">Median time</th>
                      <th className="py-2 pr-3 font-medium">Trust (1–5)</th>
                      <th className="py-2 font-medium">Would complain</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(results.data.arms).map(([arm, r]) => (
                      <tr key={arm} className="border-b border-line/70">
                        <td className="py-2 pr-3 text-ink">{ARM_LABEL[arm]}</td>
                        <td className="tabular py-2 pr-3">{r.participants}</td>
                        <td className="tabular py-2 pr-3">{fmtPct(r.scam_cancel_rate, 0)}{ci(r.scam_cancel_ci95)}</td>
                        <td className="tabular py-2 pr-3">{fmtPct(r.legit_continue_rate, 0)}{ci(r.legit_continue_ci95)}</td>
                        <td className="tabular py-2 pr-3">{r.median_seconds != null ? `${r.median_seconds}s` : "–"}</td>
                        <td className="tabular py-2 pr-3">{r.mean_trust ?? "–"}</td>
                        <td className="tabular py-2">{fmtPct(r.complaint_rate ?? null, 0)}{ci(r.complaint_ci95 ?? null)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-muted">Protocol, consent text and analysis plan: docs/USER_STUDY.md. Run with 60+ participants (20 per arm).</p>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
