# Shurokkha (সুরক্ষা): Project Report

> The formatted version of this report is [Shurokkha_Project_Report.docx](Shurokkha_Project_Report.docx).
AI DEV FEST 2026 · DIU CPC × upay AI Hackathon · Team `<team name>` · `<member names>`

## 1. Problem
For **first-time and low-digital-literacy upay users and upay's risk-operations team**, **social-engineering scams, account takeovers and money-mule networks** cause **irreversible losses, customer distrust and slow manual investigations**. Trust is "foundational to wallet adoption and transaction growth" (upay guideline, Track 01). Victims are often remittance receivers and garments workers who were pressured on a phone call. The money moves through mule wallets and is cashed out within minutes, so once it is sent it is effectively gone.

## 2. Proposed idea
A real-time trust copilot that intervenes **before** money leaves and answers, for every transfer:
**What happened?** (behavioural, device, SIM-swap and network evidence) → **Why is it risky?** (calibrated AI scores + verified reasons, in Bangla) → **What should upay do next?** (ALLOW / WARN the customer / HOLD for a human, with an AI case summary and SOP-cited next steps).

## 3. Implemented solution
- **Customer wallet simulator**: pre-transaction scam interrupt in Bangla/English with cancel / send-anyway; HOLD for takeover-like transfers.
- **Risk API** (`/score`, ~5 ms server-side): feature engine → 4 plug-in detectors → YAML policy → explanations; idempotent, audited.
- **Analyst console**: ranked queue, case view with reasons, SHAP drivers, mule-ring network, related alerts, audit trail, feedback that releases held transfers and feeds retraining.
- **AI copilot & chat**: Gemini (or Claude) case narratives grounded only in an evidence JSON + retrieved SOPs, with a numeric-grounding check and deterministic fallback; SOP Q&A with citations; a page- and case-aware AI chat assistant.
- **Impact dashboard**: lift table, per-scenario recall, business impact, fairness audit, live latency and scams averted.
- **Admin**: live policy editing with validation and hot reload, model registry switching, graph refresh. Read-only for visitors; changes need a separate admin password that is never built into the website.

Screenshots: [docs/screenshots/](screenshots/).

## 4. Key features
F1 real-time scoring · F2 hybrid decision engine · F3 verified Bangla/English reasons · F4 scam interrupt · F5 analyst console & feedback loop · F6 mule-ring graph · F7 grounded AI copilot · F8 impact & fairness dashboard · F9 synthetic data generator (6 scenarios).

## 5. AI approach
**Data.** 90 days of synthetic data for 2,000 customers across 7 personas, including hard legitimate look-alikes (online sellers with many first-time senders, shopkeepers' near-limit cash-outs, legit SIM replacements, new joiners) and six injected fraud scenarios (DATA_ASSUMPTIONS.md).

**Features.** One stateful, point-in-time feature engine is used for both training replay and live serving, so there is no train/serve skew. It produces 46 features, including transaction-graph features from rolling 14-day snapshots (Louvain communities, PageRank, community fan-in and cash-out ratio, forwarding ratio).

**Models.** LightGBM (Platt-calibrated) + Isolation Forest anomaly percentile + transparent graph-risk score + deterministic rules, combined by a YAML policy. Thresholds are learned on a validation window: WARN at 1% legitimate FPR, HOLD at ≥90% precision.

**Explainability.** Exact TreeSHAP contributions mapped to reason codes, each emitted only if its factual condition holds.

**GenAI.** One gateway for Google Gemini (default when a key is set) or Anthropic Claude, with JSON-schema output, a timeout and circuit breaker, and a server-side fallback. The prompt allows only evidence facts. Untrusted text is isolated, and every number in the narrative must exist in the evidence, otherwise a template is used. The LLM never decides.

**Evaluation.** Time-based split with a held-out 10-day test window (22,126 transactions):

| Model | PR-AUC | Recall @ 1% FPR |
|---|---|---|
| Rules only | 0.166 | 15.6% |
| Logistic regression | 0.822 | 80.1% |
| LightGBM, no graph/anomaly | 0.952 | 93.8% |
| **Shurokkha (LightGBM + graph + anomaly)** | **0.995** | **99.5%** |

Full system: precision 91.7%, recall 96.2%, FPR 0.24%, HOLD precision 98.2%. Per-scenario recall: ATO 100%, prize scam 84%, refund scam 100%, mule flows 100%, structuring 94%, social engineering 87%.

**Robustness** (docs/reports/robustness.md). Because synthetic fraud is easier than real fraud, we also test generalisation. Retrained *without* a fraud family, the model still catches it at 1% FPR: prize scam 85%, ATO 87%, refund 76%, social engineering 97%. Weak spots are new mule networks (47%) and new structuring (0%), which the rules and graph detector cover in the full system. With a brand-new mule ring (graph features unavailable), recall falls only from 99% to 94%. Calibration error is 0.0024; mid-range scores are conservative (scores of 0.25–0.50 were fraud 96% of the time).

**GenAI evaluation** (docs/reports/genai_eval.md). 20 case summaries (10 HOLD, 10 WARN): 100% numbers grounded, 100% valid citations, 100% decision-consistent, 100% SOP-referenced actions; fabricated numbers are rejected by the guard. The evaluation also found and fixed a bug in which "SOP-05" was read as the number 5.

## 6. Real-life impact
- **Customers:** 94.3% of victim-loss value was flagged before completion in the test window. Assuming 60% of warned customers cancel (to be measured in a pilot), the estimated loss prevented was ৳606,100 in 10 days of this simulation, at the cost of ≈5 legitimate customers warned per day.
- **Operations:** ranked queue with 98% HOLD precision; case summaries with SOP-cited next steps; median time-to-decision is tracked live.
- **Ecosystem:** mule-ring detection disrupts the cash-out network, not just single transactions.
- **Inclusion:** Bangla-first, plain-language explanations protect first-time users without blocking them.

## 7. Scalability & integration
Pre-authorisation hook (`/score`) + confirm callback; versioned REST API with OpenAPI docs; Docker; Postgres/Redis support; plug-in detectors and hot-reload policy. Production path: shared online feature store (Redis/Feast), streaming ingestion (Kafka), incremental graph processing, shadow → canary → A/B rollout (ARCHITECTURE.md). Validation with upay data: offline back-test → shadow mode → WARN-only pilot → HOLD with SLAs.

## 8. Responsible AI & security
Synthetic data only; pseudonymous ids to the LLM; verified explanations; fairness audit (shopkeepers and new accounts currently show higher FPR → segment overrides / merchant onboarding); human review for every HOLD; no permanent auto-block; sandboxed policy expressions; JWT roles; admin password never shipped to the browser; dependency vulnerability audit in CI (0 known vulnerabilities); rate limiting; prompt-injection isolation; audit log.

## 9. Limitations & future work
Synthetic patterns are easier than real fraud; single-worker online state; small calibration window; BM25 retrieval. Next: shared feature store, real-data shadow evaluation, uplift testing of warning designs, Bangla voice warnings, agent-risk benchmarking.

## 10. Disclosures
See DISCLOSURES.md. External services: Google Gemini API and Anthropic Claude API (both optional). No external datasets or pre-trained models.
