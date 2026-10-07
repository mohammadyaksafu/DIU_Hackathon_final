# Shurokkha (সুরক্ষা): Phase 1 Results and the Plan to 100/100

**Project:** AI Trust & Financial-Safety Copilot for upay. **Contest:** AI Hackathon 2026.

---

## 1. Where you stand

| Criterion | Score | Max | Gap | % achieved |
|---|---|---|---|---|
| Problem relevance | 18.33 | 20 | 1.67 | 92% |
| AI/ML depth | 16.33 | 20 | **3.67** | 82% |
| Business/customer impact | 17.00 | 20 | **3.00** | 85% |
| Prototype quality | 12.33 | 15 | **2.67** | 82% |
| Innovation | 8.00 | 10 | 2.00 | 80% |
| Scalability & integration | 7.67 | 10 | **2.33** | 77% |
| Responsible AI & security | 3.33 | 5 | 1.67 | **67%** |
| **Total** | **≈ 83.0** | **100** | **17.0** | **83%** |

**What the judges agree on.** The architecture, the explainability, and the Bangla UX are strong. They are not docking you for missing features. They are docking you for **missing evidence**.

**The single message across all 21 comments:**

> *"It works on synthetic data in one process. Prove it works on realistic data, at scale, against baselines, with measured human behaviour."*

To reach 100, you do not need to build more models. You need to turn claims into measurements.

---

## 2. Five cross-cutting themes

If you fix these five themes, nearly every comment is answered. They are ordered by total points at stake.

| # | Theme | Criteria it fixes | Points at stake |
|---|---|---|---|
| T1 | **Ablation vs baselines, using cost-sensitive metrics** | AI/ML, Innovation, Business | ~6 |
| T2 | **Robustness beyond "easy" synthetic data** (unseen fraud, distribution shift, harder generator) | AI/ML, Prototype | ~4 |
| T3 | **Horizontal scaling proof** (multi-worker, shared state, ordering, idempotency, p95/p99) | Prototype, Scalability | ~4 |
| T4 | **Measured intervention effectiveness** (the WARN experiment) | Business, Responsible AI | ~3 |
| T5 | **Evidence and governance** (real MFS statistics, cash-out coverage, appeals, drift, fairness) | Problem, Responsible AI | ~3 |

---

## 3. Criterion-by-criterion plan

### 3.1 Problem relevance (18.33/20, +1.67)

**What the judges said**
- Use governed MFS statistics on scam losses, account takeover, mule activity, and analyst workload.
- Quantify the cost of false positives against the losses you prevent.
- Prove that the pre-transaction moment is the highest-value control point.
- **Coverage gap:** cash-out scams at agent points are not covered.
- Prioritize by which fraud types and customer segments carry the most loss.

**Actions**
1. **Evidence slide with cited sources only.** Pull figures from:
   - Bangladesh Bank MFS monthly statistics (accounts, transaction value, agents)
   - Bangladesh Bank and BFIU annual reports, and any MFS fraud circulars
   - BTRC SIM-registration and SIM-replacement guidance (SIM-swap context)
   - Published reports from CID or DMP cyber units on MFS scams
   - Credible news investigations (Prothom Alo, The Daily Star, TBS)

   Every number gets a citation. Never present an estimate as a statistic. Label estimates as estimates.
2. **Fraud-type × loss × segment matrix.** Rows are social engineering, SIM-swap/ATO, mules, and agent cash-out fraud. Columns are frequency, average loss, reversibility, and the most affected segment. Use it to justify your priority order.
3. **Control-point analysis.** Draw a timeline: account opening → login → SIM change → beneficiary add → **send money (Shurokkha)** → cash-out → post-hoc investigation. For each stage, show what is recoverable and what each control costs. This demonstrates why pre-transaction is the highest-value point instead of just asserting it.
4. **Close the cash-out gap (Judge 3).** Add an **Agent Cash-Out module**:
   - Detects fresh-inflow → immediate full cash-out (the classic mule pattern)
   - Flags the same agent serving many newly-funded accounts
   - Adds a velocity check on the agent side
   - Optionally sends an OTP or "voice confirm" for high-risk cash-outs

   Even a working detector plus a dashboard tab answers this comment.
5. **False positive vs prevented loss.** Show the cost function you optimise:
   `Cost = (missed fraud × loss) + (false positives × friction cost) + (HOLDs × analyst minutes × cost/minute)`

### 3.2 AI/ML depth (16.33/20, +3.67, the biggest gap)

**What the judges said**
- Show robustness to **unseen** fraud: structuring and new mule networks.
- Report results under **distribution shift**.
- Compare the **full system against LightGBM-only and rule-only** controls.
- Use cost-sensitive metrics, calibration, and false-positive burden, not synthetic held-out accuracy.
- "Trained on easy fake clues": the synthetic data has leakage or trivially separable signals.

**Actions**
1. **Ablation table (most important deliverable).** Run every configuration on the same test set:

   | System | PR-AUC | Recall @ 1% FPR | Loss-value caught | FP per 10k txns | Analyst HOLDs/day | Expected cost (৳) | ECE |
   |---|---|---|---|---|---|---|---|
   | Rules only | | | | | | | |
   | LightGBM only | | | | | | | |
   | + Isolation Forest | | | | | | | |
   | + Graph features (PageRank/Louvain) | | | | | | | |
   | **Full Shurokkha** | | | | | | | |

   Add bootstrap 95% confidence intervals. This one table also answers Innovation and Business.
2. **Leave-one-fraud-type-out (LOFO) test.** Train without structuring, then test on structuring. Repeat for each fraud type and for new mule rings. This is the direct answer to "previously unseen fraud mechanisms." Report how much the anomaly and graph layers rescue compared with LightGBM alone. That gap is your argument for keeping them.
3. **Distribution-shift suite.**
   - Temporal split: train on weeks 1–6, test on weeks 7–8 (no random split)
   - Covariate shift: change the Eid/salary-day spike, the device mix, and the new-user share
   - Adversarial drift: fraudsters lower amounts below thresholds, slow velocity, and rotate devices

   Report degradation curves and show your calibration under shift.
4. **Fix the "easy fake clues" problem.**
   - Audit for leakage: are any features deterministic tells of the generator (e.g., `is_new_device` always 1 for fraud)? Run SHAP on the synthetic data. If one feature dominates, it is a leak.
   - Rebuild the generator with **overlap**: legitimate users also get new devices, send at night, and pay new merchants; fraudsters mimic normal amounts.
   - Add an **adversarial fraudster agent** that tunes behaviour to evade your current model. Retrain, re-attack, and report the rounds.
   - Optionally validate on public benchmarks to show transfer: **PaySim** (mobile-money simulator modelled on an African MFS), IEEE-CIS Fraud, and the Elliptic dataset for graph/mule detection. Present these as "external sanity checks," not real upay data.
5. **Calibration and thresholds.** Show reliability diagrams, ECE/Brier before and after calibration, and **cost-optimal thresholds** for ALLOW/WARN/HOLD derived from the cost function instead of hand-picked values.
6. **Drift monitoring hook.** Track PSI/CSI on top features and alert when retraining is needed. This also feeds Responsible AI.

### 3.3 Business/customer impact (17/20, +3)

**What the judges said**
- Translate model results into fraud loss prevented, operational savings, friction, and ROI.
- The cancellation rate after a warning is **assumed, not measured**.
- Run a **controlled WARN experiment**.
- Separate simulated benefit from validated outcomes.

**Actions**
1. **Run the WARN experiment now, at small scale.** You cannot get upay users, but you can run a **controlled user study**:
   - 40–100 participants (SUST students, family members, rickshaw/shop owners for realism)
   - A clickable prototype with scripted scam scenarios ("your bKash/upay account will be blocked, send ৳5,000…") mixed with legitimate payments
   - Arms: (A) no warning, (B) generic warning, (C) Shurokkha Bangla explained warning
   - Measure: scam-cancel rate, legitimate-continue rate (friction), time to decide, self-reported trust, complaint intent
   - Report with confidence intervals. Even n≈60 turns "assumed" into "measured." Get informed consent and keep it anonymous.
2. **Two-column impact model.** Never mix these:

   | Validated (measured) | Simulated (modelled) |
   |---|---|
   | Cancel rate from user study | Loss prevented at upay scale |
   | Analyst time-to-decision from dashboard trial | Annual ROI |
   | Latency from load test | Complaint volume at scale |

3. **ROI model with sensitivity analysis.** `Net benefit = prevented loss − (FP friction cost + analyst cost + infra cost)`. Show a tornado chart over cancel rate, fraud base rate, and FP cost. Show a break-even point: "Shurokkha pays for itself if cancel rate > X%."
4. **Analyst workload trial.** Have 3–5 people triage 50 cases with and without the AI summary. Measure time per case and accuracy.
5. **Re-express the 94.3% claim.** Judges liked it. Keep it, but state it as "94.3% of victim-loss value on held-out synthetic data (95% CI …)." Then add the same metric under shift and LOFO.

### 3.4 Prototype quality (12.33/15, +2.67)

**What the judges said**
- It runs on only one computer.
- Show concurrent multi-worker operation with shared online feature state and durable ordering.
- Verify idempotency, retries, HOLD/release consistency, and model-version consistency.
- Plan shadow mode before live blocking.

**Actions**
1. **Multi-worker architecture (docker-compose is enough):**
   ```
   Load balancer (nginx) → N × FastAPI scoring workers (stateless)
                                     │
            Redis (online feature store: velocity counters, device/SIM state, graph scores)
                                     │
            Kafka/Redpanda (transaction log, partitioned by account_id → per-account ordering)
                                     │
            Postgres (cases, HOLD/release decisions, audit log)
            Model registry (MLflow or a simple versioned artifact store)
   ```
2. **Correctness guarantees with tests:**
   - **Idempotency:** each request carries `txn_id`. Store results in Redis with `SETNX` plus a TTL so a retried request returns the identical decision.
   - **Ordering:** partition by `account_id` so velocity features are never computed out of order.
   - **Atomic features:** Redis `INCR`/Lua scripts. Show that two workers updating the same account give the correct count.
   - **HOLD/release consistency:** use a state machine (PENDING → HOLD → RELEASED/BLOCKED) with optimistic locking, and test concurrent analyst actions.
   - **Model-version pinning:** every decision logs `model_version` and `policy_version`. Show hot-swapping without mixed-version decisions for one transaction.
3. **Chaos demo:** kill a worker mid-load and show no lost or duplicated decisions.
4. **Shadow mode:** add `mode: shadow | warn | enforce` to the policy config. In shadow mode, decisions are logged but never shown. This is the documented path to real-traffic validation.
5. **Test suite plus CI badge:** unit, integration, and concurrency tests on GitHub Actions. Show the green badge on a slide.

### 3.5 Innovation (8/10, +2)

**What the judges said**
- Show the incremental value of each component over a conventional classifier.
- Warning pop-ups already exist, so explain what is new.

**Actions**
1. **Reuse the ablation table (§3.2) with a "marginal contribution" column**, for example: "Graph layer adds +X% recall on mule rings at the same FPR."
2. **Differentiate the UX beyond a pop-up.** Ideas you can show:
   - **Scam-script detection:** if the user is on an active call while sending money (a common social-engineering signal), show a "Are you being told to send this right now?" interstitial.
   - **Cooling-off timer** for high-risk first-time beneficiaries, with an option to call a trusted contact.
   - **"Trusted person" confirmation:** a family member approves large transfers, which suits Bangladeshi household finance.
   - **Voice warning in Bangla** for low-literacy users.
   - **Grounded explanations:** reasons appear only when SHAP and the facts agree. Judges already liked this, so make it the headline.
3. **One-sentence novelty claim:** *"The first pre-transaction MFS defence that fuses device, SIM, behaviour, and mule-graph signals and explains them in verified Bangla, with measured lift over a standard classifier."*

### 3.6 Scalability & integration (7.67/10, +2.33)

**What the judges said**
- Load-test at production volume, and report p95/p99 latency.
- Show failover and monitoring.
- Graph refresh every 10 minutes will slow down as data grows.

**Actions**
1. **Load test with Locust or k6:** step from 100 → 1k → 5k+ requests/sec across 1, 2, 4, and 8 workers. Report throughput, p50/p95/p99, and error rate. Show a near-linear scaling chart.
2. **Context sizing:** compare your tested throughput with upay's public peak volume (cite the source) and state how many workers production needs.
3. **Incremental graph analytics instead of a full 10-minute rebuild:**
   - Streaming/incremental PageRank (update only the affected neighbourhood)
   - Incremental community detection, or Louvain run only on changed subgraphs
   - Sliding time window (e.g., 30 days) to bound graph size
   - Offline full recompute nightly; online cheap features (degree, fan-in/fan-out, 2-hop new-account ratio) in Redis

   Benchmark refresh time against graph size and show it stays bounded.
4. **Observability:** Prometheus and Grafana dashboard for latency, decision mix, model scores, and drift. Add health checks and a **fail-open/fail-safe policy**: if scoring times out, fall back to rules only. This is a strong point to show.
5. **Integration contract:** OpenAPI spec, sample payloads, and a sequence diagram showing exactly where Shurokkha sits in the upay send-money flow (synchronous call with timeout budget).

### 3.7 Responsible AI & security (3.33/5, +1.67, lowest percentage)

**What the judges said**
- Add a customer appeal/release process, drift monitoring, access controls, and data privacy.
- Honest shopkeepers with many new buyers may get flagged too often.
- Validate fairness and calibration by segment, and do not weaken protection for high-risk groups.

**Actions**
1. **Merchant false-positive fix (Judge 2):** add a **merchant/agent profile**. A known merchant with many new payers is *normal*. Make the graph and velocity features merchant-aware. Show FPR for merchants before and after.
2. **Segment fairness report:** FPR, FNR, warning rate, and calibration by segment (new vs old accounts, region/division, rural vs urban agent, device tier, age band where available). Make the constraint explicit: *equalize false-positive burden without lowering recall for high-risk segments*.
3. **Customer appeal flow:** "This wasn't fraud" button → case to analyst → SLA (e.g., released within N minutes) → feedback label returns to retraining. Show it in the app demo.
4. **Governance one-pager:**
   - Role-based access control (analyst, supervisor, admin) plus audit logs of every HOLD/release
   - PII handling: pseudonymised IDs, encryption at rest and in transit, retention limits. Reference Bangladesh's data-protection framework and Bangladesh Bank guidelines (verify the current status before citing).
   - Model cards and a datasheet for the synthetic data
   - Drift monitoring with retraining triggers, and a human sign-off before any model promotion
   - LLM guardrails: the AI summary may only use retrieved case facts; log prompts and outputs; use deterministic fallback.
5. **Security threats:** briefly address adversarial probing (fraudsters testing thresholds), rate limiting, and protecting model endpoints.

---

## 4. Priority roadmap (points per effort)

| Priority | Task | Est. effort | Points likely recovered |
|---|---|---|---|
| 🔴 1 | Ablation table + cost-sensitive metrics + CIs | 1–2 days | 3–4 |
| 🔴 2 | LOFO + temporal/shift tests + harder generator | 2–3 days | 2–3 |
| 🔴 3 | Multi-worker docker-compose (Redis + Kafka) + idempotency/ordering tests + load test p95/p99 | 2–3 days | 3–4 |
| 🟠 4 | WARN user study (n≈60) | 3–5 days | 2–3 |
| 🟠 5 | Cited MFS evidence slide + control-point analysis | 1 day | 1–1.5 |
| 🟠 6 | Merchant-aware features + segment fairness report + appeal flow | 1–2 days | 1–1.5 |
| 🟡 7 | Agent cash-out module | 1–2 days | 0.5–1 |
| 🟡 8 | Incremental graph refresh benchmark | 1–2 days | 0.5–1 |
| 🟡 9 | Observability, fail-safe, governance one-pager, model card | 1 day | 0.5–1 |

If you only have one week, do items 1, 2, 3, and 5. They target the largest gaps and the most-repeated comments.

---

## 5. Presentation changes for the next round

1. **Open with the evidence slide** (real, cited MFS figures), not the architecture.
2. **"You asked, we did" slide.** Map each judge comment to the result you produced. Judges reward visible responsiveness more than anything else.
3. **One slide each** for the ablation table, the robustness/shift results, the load-test chart, and the user-study results.
4. **Label every number** as *Measured*, *Simulated*, or *Estimated*.
5. **Live demo:** multi-worker load → kill a worker → no lost decisions → analyst releases a HOLD → customer appeal flows through.
6. **Close with a deployment path:** shadow mode → WARN-only pilot → limited HOLD → full enforcement, each with go/no-go metrics.

---

## 6. Honest note on "100/100"

Some comments can only be fully answered with **real upay transaction data** (Judge 1, Prototype: "shadow-mode testing against real transactions"). A hackathon team usually cannot get that. The strongest move is to:
- Do everything that *is* possible (ablations, shift tests, scaling proof, user study)
- Present a concrete **shadow-mode pilot proposal** with the exact metrics you would report to upay

That is close to the ceiling a judge can award without production data. Realistically, completing the 🔴 and 🟠 items should move you from **~83 into the mid-90s**.

---

## 7. Final checklist

- [x] Ablation table (rules / LGBM / +IF / +graph / full) with cost-sensitive metrics and CIs → docs/reports/evaluation.md §1
- [x] Leave-one-fraud-type-out results (structuring, new mule rings) → evaluation.md §3, robustness.md
- [x] Temporal and adversarial distribution-shift results → evaluation.md §4–5
- [~] Leakage audit + harder synthetic generator (done, evaluation.md §6–7); PaySim/Elliptic sanity check not done
- [x] Calibration (reliability table, ECE before/after) + cost-optimal thresholds → evaluation.md §2, §9
- [~] Multi-worker deployment with Redis feature store (done); Kafka documented as production path, not deployed
- [x] Idempotency, retry, HOLD/release, and model-version concurrency (code + tests + chaos run)
- [x] Load test: throughput + p95/p99 across 1, 2, 4 workers → docs/reports/load_test.md
- [x] Graph refresh benchmark → docs/reports/graph_benchmark.md
- [x] Shadow / warn / enforce modes (config/policy.yaml)
- [~] WARN user study: tool built (/study, docs/USER_STUDY.md); participants still needed
- [x] ROI model split into Measured vs Simulated, with sensitivity analysis (Impact page)
- [x] Cited MFS fraud statistics + control-point analysis → docs/EVIDENCE.md
- [x] Agent cash-out detection module (app/detectors/agent_cashout.py + demo scenario)
- [x] Merchant-aware features + segment fairness report → evaluation.md §8
- [x] Customer appeal flow + docs/GOVERNANCE.md + model card update
- [x] Prometheus + Grafana dashboard (profile monitoring) + on_scoring_error fail-safe
- [x] "You asked, we did" → docs/JUDGE_RESPONSE.md
