# Shurokkha: What Changed from Phase 1 to Phase 2

**Phase 1 score:** ≈ 83 / 100.
**Judges' common message:** *"It works on synthetic data in one process. Prove it works on realistic data, at scale, against baselines, with measured human behaviour."*

Phase 2 does not add more models for their own sake. It turns Phase 1's claims into measurements and closes the gaps the judges named. Each section below follows the same pattern:

> **Problem in Phase 1** → **What we updated** → **How it works now**

Number labels: **Measured** (run on this system), **Simulated** (synthetic data), **Estimate** (stated assumption), **Built, awaiting data** (tool ready, no participants yet). Full evidence table: [JUDGE_RESPONSE.md](JUDGE_RESPONSE.md).

> **সংক্ষেপে (বাংলা):** ফেজ ১-এ সিস্টেমটি একটি প্রসেসে, শুধু সিন্থেটিক ডেটায় চলত, এবং অনেক সংখ্যা ছিল অনুমান। ফেজ ২-এ আমরা (১) এজেন্ট পয়েন্টে ক্যাশ-আউট প্রতারণা ধরার নতুন ডিটেক্টর যোগ করেছি, (২) বেসলাইনের সাথে তুলনা, কঠিন ডেটা ও ডেটা-শিফটে মডেল যাচাই করেছি, (৩) Redis দিয়ে একাধিক ওয়ার্কারে চালানো ও লোড/কেওস টেস্ট করেছি, (৪) সতর্কবার্তা কতটা কাজ করে তা মাপার জন্য ইউজার স্টাডি বানিয়েছি, এবং (৫) গ্রাহকের আপিল, ড্রিফট মনিটরিং ও ফেয়ারনেস যাচাই যোগ করেছি।

---

## 1. Agent cash-out fraud was not covered

**Problem in Phase 1.** Shurokkha only scored *send money*. The last step of a mule chain, where stolen money is withdrawn as cash at an agent point, was invisible (judge comment: "cash-out scams at agent points not covered").

**What we updated.**
- New detector `backend/app/detectors/agent_cashout.py`.
- New policy rules in `config/policy.yaml` and reason codes in Bangla and English.
- New demo scenario: **"Mule cash-out at an agent"**.

**How it works now.** Every cash-out is checked from two sides:
- **Wallet side:** money that arrived minutes ago, often from new senders, is being cashed out almost in full.
- **Agent side:** the agent is suddenly serving many first-time customers, far above its normal hourly rate.

A high score gives a **WARN** (in production: OTP or voice confirmation at the agent). Together with the mule-network score it gives a **HOLD**.

---

## 2. No proof the AI beats simple baselines

**Problem in Phase 1.** We reported the full system's results, but did not show how much each layer adds or how it compares with rules-only or LightGBM-only.

**What we updated.** New evaluation pipeline `backend/pipelines/evaluation.py` with report [reports/evaluation.md](reports/evaluation.md).

**How it works now.** One time-based split (train < validation < test): thresholds and calibration are learned on validation, and the test window is only scored. The ablation goes rules → LightGBM → + Isolation Forest → + graph → full system and reports:
- PR-AUC, recall at 1% FPR, loss caught, false positives per 10k, HOLDs per day
- expected cost per day and calibration (ECE)
- **bootstrap 95% confidence intervals** and the marginal contribution of each layer

For example, the graph layer adds +7.9 pp fraud flagged and −৳9,636/day expected cost (Simulated).

---

## 3. "Trained on easy fake clues": robustness was not shown

**Problem in Phase 1.** All results came from one easy synthetic dataset. The judges asked about unseen fraud types, distribution shift and data leakage.

**What we updated.** Further sections in the same evaluation pipeline, plus a harder data generator (`generate_data.py`, `hard=True`).

**How it works now (all Simulated):**

| Check | Result |
|---|---|
| Leave-one-fraud-family-out (fraud type never seen in training) | Rules, graph and agent layers rescue what the model misses: structuring 0% → 53%, ATO 72% → 100%, refund 47% → 62% |
| Later time window | Recall 99.1% → 94.3% |
| Covariate shift (more new users, Eid amounts) | Recall holds at 96.9% |
| Adversarial drift (smaller amounts, slower mules) | 96.9% → 86.5% |
| Adversarial rounds | Attack 86.5% → retrain 98.8% → stronger attack 87.6% → retrain 98.3% |
| Leakage audit | No single feature reaches AUC 0.95 |
| Harder synthetic data, full retrain | PR-AUC 0.959, system recall 91.9% |

---

## 4. Ran as one process; could not scale

**Problem in Phase 1.** The online feature state lived in the memory of one API process. A second worker would have its own, inconsistent copy, and live history was lost on restart. The database schema was created with `create_all`, so it had no migrations.

**What we updated.**
- `backend/app/features/store.py`: a Redis-backed wallet store shared by every worker (`FEATURE_STORE=auto|memory|redis`).
- Rate limits, drift window and metrics are also shared through Redis.
- **Alembic migrations** (`backend/migrations/`). Existing databases are stamped and upgraded in place, so no data is lost.
- `API_WORKERS` setting for production.

**How it works now.**
- Several Uvicorn workers read and write the same wallet state in Redis, and live history survives restarts.
- Idempotency: a transaction ID is claimed across workers before scoring, so a retry returns the first decision.
- HOLD/release uses a conditional update, so a cancel after a release cannot complete twice.
- Without Redis the system falls back to memory and runs as a single worker.

**Measured (laptop):**
- Throughput: 1 → 2 → 4 workers gave 52 → 93 → 169 req/s with 0 errors.
- Server-side latency p50 / p95 / p99: 11.6 / 26.0 / 35.8 ms.
- Chaos test (`tests/load/chaos.py`): a worker killed under load lost **0** and duplicated **0** of 2,177 transfers.

Report: [reports/load_test.md](reports/load_test.md).

---

## 5. Graph refresh might slow down as data grows

**Problem in Phase 1.** The mule-ring graph (Louvain + PageRank) was rebuilt from all data, and nothing showed how that cost would grow.

**What we updated.** `backend/pipelines/graph_benchmark.py`, report [reports/graph_benchmark.md](reports/graph_benchmark.md).

**How it works now.**
- **Online path:** per-transaction counters (fan-in, new senders, forwarding ratio, agent velocity) cost the same for every transaction.
- **Batch path:** the graph is rebuilt in the background over a fixed 14-day sliding window, so its size depends on daily traffic, not total history.
- Measured under continuous load: rebuilds took 0.83–1.28 s while scoring continued.

---

## 6. The warning cancel rate was assumed, not measured

**Problem in Phase 1.** Loss-prevented figures assumed that 60% of warned victims cancel the transfer. There was no evidence for that number.

**What we updated.**
- **WARN user study** built into the app: `/study` page and `backend/app/api/v1/study.py`. Protocol and consent text: [USER_STUDY.md](USER_STUDY.md).
- Impact page: a loss-prevented **range**, ROI with sensitivity, and a "Measured vs simulated" panel.

**How it works now.**
- Participants are randomly assigned to three arms: **A** no warning, **B** a generic warning, **C** the Shurokkha Bangla warning with explanations.
- Each sees the same scripted transfers (scams mixed with genuine payments). We record cancel or continue, time to decide and self-reported trust, with anonymous codes only.
- Results come with 95% Wilson confidence intervals. Once enough people have taken part, arm C's measured cancel rate replaces the 60% assumption.
- The Impact page shows net benefit per day, ROI, the break-even cancel rate and a sensitivity (tornado) chart over cancel rate, fraud base rate and false-alarm cost.

Status: **Built, awaiting data** (needs 60+ participants).

---

## 7. No appeal path for customers

**Problem in Phase 1.** A customer whose genuine transfer was held could only wait. There was no way to say "this wasn't fraud".

**What we updated.**
- `POST /transactions/{id}/appeal`.
- An "Not a scam? Appeal" link in the customer app.
- Appealed cases are marked in the analyst queue. Database migration `0002_appeals_and_study`.

**How it works now.**
- An appeal moves the case to the **top of the analyst queue** with a 15-minute SLA (SOP-05).
- If the analyst labels it `legit`, the HOLD is released and the label is stored as training feedback.
- Every appeal is written to the audit log.

---

## 8. No drift monitoring

**Problem in Phase 1.** Nothing would tell us when live traffic stopped looking like the training data.

**What we updated.**
- `backend/app/services/drift.py` and `GET /api/v1/metrics/drift`.
- Prometheus and a provisioned Grafana dashboard (`deploy/monitoring/`, profile `monitoring`).

**How it works now.**
- Each scored transaction adds its key features to a rolling window shared by all workers.
- The **Population Stability Index (PSI)** compares that window with training: below 0.10 is stable, 0.10–0.25 means watch, and above 0.25 means drifted, so retraining is recommended.
- A new model is activated only after human sign-off.
- In testing, load-test traffic was correctly flagged as drift.

---

## 9. Honest shopkeepers were flagged too often (fairness)

**Problem in Phase 1.** Merchants who receive many payments from strangers look like mules, so their false-positive rate was high.

**What we updated.**
- Merchant-aware features.
- A per-segment fairness audit: FPR, FNR, warning rate and calibration per segment.
- A merchant threshold override in `policy.yaml`, running in **shadow** mode (logged, not applied) until it is validated on real data.

**How it works now (Simulated).**
- False-positive rate for merchants as senders: 2.9% → 0.6%.
- False-positive rate for all legitimate transactions: 0.68% → 0.20%.
- **Fraud recall unchanged** at 96.9%, including the 65+ age group.

The Impact page shows the fairness audit for each segment.

---

## 10. Weak warnings: pop-ups already exist

**Problem in Phase 1.** Judges noted that warning pop-ups are not new on their own.

**What we updated.** A new **"Coached on a phone call"** scenario and an on-call signal in the customer app.

**How it works now.**
- The app knows when a call is active and asks the customer: "Are you being told to send this now?"
- High-risk cases add a cooling-off delay before "send anyway", a prompt to call someone you trust, and a Bangla voice warning.
- Reasons are shown only when the facts and the model's explanation agree.

---

## 11. Tests and CI

**Problem in Phase 1.** CI ran backend tests and the frontend lint and build, but the UI itself was never tested end to end.

**What we updated.**
- Playwright browser tests (`frontend/e2e/`) for desktop and mobile, with **axe WCAG 2.1 AA** accessibility checks.
- New CI job `e2e` that runs them against the real stack.
- New backend tests for the Redis multi-worker store, migrations, appeals, the study and concurrency.

**How it works now.** Every push runs:
- backend tests
- frontend lint and build
- browser tests: customer HOLD flow, analyst case, admin lock, mobile layout and accessibility
- secret scanning

---

## 12. Documentation and evidence

New documents for reviewers:

| Document | Purpose |
|---|---|
| [EVIDENCE.md](EVIDENCE.md) | Cited MFS statistics, fraud type × loss × segment matrix, control-point analysis |
| [GOVERNANCE.md](GOVERNANCE.md) | Access control, privacy, retention, threat table, model sign-off |
| [INTEGRATION.md](INTEGRATION.md) | API contract for upay's core: OpenAPI, sample payloads, sequence diagram, timeout rule |
| [USER_STUDY.md](USER_STUDY.md) | WARN study protocol, consent text, analysis plan |
| [JUDGE_RESPONSE.md](JUDGE_RESPONSE.md) | Every judge comment mapped to code and evidence |
| [reports/evaluation.md](reports/evaluation.md), [graph_benchmark.md](reports/graph_benchmark.md), [load_test.md](reports/load_test.md) | Generated reports |

---

## Phase 1 vs Phase 2 at a glance

| Area | Phase 1 | Phase 2 |
|---|---|---|
| Fraud coverage | Send money only | + agent cash-out, + on-call coaching |
| ML evidence | Headline metrics | Ablation with 95% CIs, unseen fraud, shift, adversarial rounds, leakage audit, harder data |
| Scale | One process, in-memory state | Multi-worker, shared Redis state, Alembic migrations, measured load and chaos tests |
| Business impact | Assumed 60% cancel rate | Range + ROI sensitivity; user study to measure it |
| Customer rights | No appeal | Appeal with a 15-minute SLA, releases the HOLD |
| Monitoring | Basic metrics | PSI drift, Prometheus + Grafana |
| Fairness | Not audited | Per-segment audit, merchant FPR cut without losing recall |
| Testing | Backend tests | + Playwright, accessibility, mobile, chaos |

## Still needs real-world input
- **Participants for the WARN study** (60+ people; the tool is ready).
- **upay data** to validate in shadow mode (`mode: shadow` in `policy.yaml` exists for this).
- Optional external checks on public datasets (PaySim, Elliptic).
- **Gemini API key** in production. Without it, the AI chat and copilot fall back to the procedure documents and show "AI unavailable".
