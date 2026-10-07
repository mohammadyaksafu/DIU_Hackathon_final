# Phase 2 evaluation: every judge comment, its status, and the expected mark

**Evaluated:** 2026-10-07 · commit `6349863` on `main` · repo `mohammadyaksafu/DIU_Hackathon_final`
**Method:** each of the 21 Phase 1 comments was checked against the code, the reports and a live run. The run used Docker Compose with 2 API workers, PostgreSQL, Redis, Prometheus and Grafana. Tests: 63 backend tests and 22 Playwright browser tests, all passing locally and in GitHub Actions; no LLM was called. The live run also included a load test (1, 2 and 4 workers) and a chaos test (one worker killed under load).

**Status key:**
- ✅ **Done**: answered with code and evidence.
- 🟡 **Partly done**: answered, but a judge could still ask for more.
- ❌ **Not done**: needs something we cannot produce without outside help (participants or real upay data).

> The marks below are **our estimate**, not the judges' decision. Synthetic evidence can answer most comments, but not the ones that explicitly ask for real data or measured human behaviour.

---

## Summary

| Criterion | Phase 1 | Max | Comments | ✅ | 🟡 | ❌ | Expected Phase 2 | Gap left |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Problem relevance | 18.33 | 20 | 3 | 2 | 1 | 0 | **19.3** | 0.7 |
| AI/ML depth | 16.33 | 20 | 3 | 1 | 2 | 0 | **18.8** | 1.2 |
| Business/customer impact | 17.00 | 20 | 3 | 1 | 1 | 1 | **18.1** | 1.9 |
| Prototype quality | 12.33 | 15 | 3 | 2 | 1 | 0 | **14.2** | 0.8 |
| Innovation | 8.00 | 10 | 3 | 3 | 0 | 0 | **9.3** | 0.7 |
| Scalability & integration | 7.67 | 10 | 3 | 2 | 1 | 0 | **9.4** | 0.6 |
| Responsible AI & security | 3.33 | 5 | 3 | 3 | 0 | 0 | **4.6** | 0.4 |
| **Total** | **≈ 83.0** | **100** | **21** | **14** | **6** | **1** | **≈ 93.7 (likely range 92–95)** | **≈ 6** |

The single biggest remaining gap is **measured customer behaviour** (Business, Judges 2 and 3). The second is **real-data validation**: AI/ML Judge 2, Prototype Judge 1 and Responsible AI Judge 3 all ask for it.

---

## 1. Problem relevance: 18.33 → expected 19.3 / 20

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Governed MFS statistics on scam losses, ATO, mule activity, analyst workload | 🟡 | Cited figures with sources:<br>• 239.3 M accounts and Tk 1.72 trn/month (Bangladesh Bank data)<br>• 1 in 10 users defrauded, average loss > Tk 9,000, compromised PINs and impersonation as the main types (PRI survey, n = 9,279)<br>Unattributed numbers are labelled as unverified. **Missing:** governed ATO, mule and analyst-workload statistics; only upay or Bangladesh Bank can supply these. | `docs/EVIDENCE.md` §1–2 |
| J1 | Cost of false positives vs prevented loss | ✅ | One explicit cost function drives the thresholds, the ablation and the ROI (missed loss, false WARN ৳20, false HOLD ৳150, analyst minutes). | `docs/EVIDENCE.md` §5, `docs/reports/evaluation.md` §2 |
| J1 | Validate pre-transaction as the highest-value control point | ✅ | Control-point table, from account opening to after-the-fact investigation: what is still recoverable at each stage and what each control costs. | `docs/EVIDENCE.md` §4 |
| J2 | Which fraud types and segments carry the largest loss; prioritise | ✅ | Fraud type × frequency × loss × reversibility × segment matrix. Per-segment FNR and FPR are in the evidence pack. | `docs/EVIDENCE.md` §3, evaluation §8 |
| J3 | Misses cash-out scams at local agents | ✅ | New **agent cash-out detector**: it flags money drained at an agent minutes after arrival, and an agent suddenly serving many first-time customers. It has its own policy tiers and a demo scenario ("Mule cash-out at an agent"), and is tested in CI. | `backend/app/detectors/agent_cashout.py` |

**Why not 20:** the loss-by-type figures are qualitative estimates, not governed statistics.

---

## 2. AI/ML depth: 16.33 → expected 18.8 / 20

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Robustness to unseen fraud (structuring, new mule networks) | ✅ | Leave-one-family-out, comparing the model alone with the full system:<br>• structuring 0% → **53%**<br>• account takeover 72% → **100%**<br>• refund scam 47% → **62%**<br>Unseen mule ring (graph features removed): recall 100% → 97%. New mule networks remain the honest weak spot (model 23%, system 31%). | evaluation §3, `docs/reports/robustness.md` |
| J1 | Performance under distribution shift | ✅ | • Later half of the test window: recall 94.3%.<br>• Covariate shift: recall holds at 96.9%, but false alarms rise from 20 to 87 per 10k legitimate transfers.<br>• Adversarial drift: recall 96.9% → 86.5%.<br>Calibration (ECE) is reported for each. | evaluation §4 |
| J1 | Full system vs LightGBM-only and rules-only, with cost-sensitive metrics, calibration and false-positive burden | ✅ | Ablation (rules → LightGBM → + Isolation Forest → + graph → full system) with PR-AUC, recall at 1% FPR, loss caught, false alarms per 10k, HOLDs/day, expected cost per day, ECE and **bootstrap 95% confidence intervals**. Cost per day falls from ৳41,000 (rules only) to ৳7,185 (full system). | evaluation §1 |
| J2 | Validate on real transaction data | ❌ | Cannot be done without upay data. Shadow mode (`mode: shadow`) and the validation path are built and documented. | `config/policy.yaml`, `docs/MODEL_CARD.md` |
| J2 | Robustness to changing / adaptive fraud | ✅ | Adversarial rounds: recall drops to 86.5% under attack and returns to 98.8% after retraining. A stronger attack drops it to 87.6%, and retraining brings it back to 98.3%. Attack values are copied from legitimate traffic, so the retrained model cannot simply learn the attack's own artefacts. | evaluation §5 |
| J3 | "Trained on easy fake clues" | 🟡 | Three checks answer this:<br>• **Leakage audit:** no single feature reaches ROC-AUC 0.95; the largest gain share is 15.7%.<br>• **Harder generator** (legitimate and fraud behaviour overlap), retrained end to end: PR-AUC 0.959, system recall 91.9%.<br>• **Generator made deterministic** (seed 42).<br>Still synthetic, and the external checks on PaySim and Elliptic were not run. | evaluation §6–7 |

Per judge: J1 ✅, J2 🟡 (adaptive fraud done, real data not possible), J3 🟡.

**Why not 20:** no real-data validation and no external benchmark.

---

## 3. Business/customer impact: 17.0 → expected 18.0 / 20

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Translate results into loss prevented, operational savings, friction and ROI | ✅ | Impact page and report:<br>• loss prevented ৳593,300–৳600,300 for 40–80% of warnings heeded<br>• analyst hours saved ≈ 9 per day<br>• friction: false alarms per day<br>• net benefit ≈ ৳55,000/day against ≈ ৳4,600/day running cost<br>• ROI 12.9×, with a break-even point and a tornado (sensitivity) chart | `/dashboard`, `docs/PROJECT_REPORT.md` §6 |
| J2 | "Guessing that most people stop after a warning is unproven" | ❌ | The **WARN user study tool is built**: `/study` with 3 randomised groups, consent screen, anonymous codes, cancel and continue rates with 95% Wilson intervals, and results fed to the Impact page. **No participants yet**, so the cancel rate is still assumed. | `/study`, `docs/USER_STUDY.md` |
| J3 | Controlled WARN experiment; measure complaint rate, friction, analyst time-to-decision; separate simulated from validated | 🟡 | Done:<br>• experiment design and tool<br>• friction measured in the study (genuine payments completed)<br>• analyst time-to-decision tracked live<br>• "Measured vs simulated" panel on the Impact page<br>**Missing:** participants. *(Update: the study now also asks complaint intent, reported per arm with a 95% CI.)* | `/dashboard`, `/study` |

**Why not 20:** this is the largest gap in the project. Two judges explicitly want *measured* behaviour, and that only comes from running the study.

---

## 4. Prototype quality: 12.33 → expected 14.2 / 15

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Shadow-mode testing against real transactions before live blocking | 🟡 | Rollout modes `shadow → warn → enforce` in the hot-reloaded policy. Alerts always record the policy's own decision, so shadow mode builds evidence without touching customers. The real-transaction run itself is not possible without upay. | `config/policy.yaml`, `docs/INTEGRATION.md` |
| J2 | "Runs on only one computer" | ✅ | Several API workers share these through **Redis**:<br>• wallet features<br>• live graph edges<br>• rate limits<br>• drift window<br>• metrics<br>PostgreSQL schema changes are **Alembic** migrations. Docker Compose runs 2 workers (4 in the load test). | `docs/ARCHITECTURE.md` "Multi-worker operation" |
| J3 | Multi-worker with shared state and durable ordering; idempotency, retries, HOLD/release consistency, model-version consistency under concurrency | ✅ | • **Idempotency:** the key is claimed across workers before scoring.<br>• **HOLD/release:** changing PENDING → SENT/CANCELLED is a single conditional update, so a cancel and a release can never both win.<br>• **Model version:** each request pins one model.<br>• **Ordering:** per-wallet Redis locks; Kafka is documented as the production path, not deployed.<br>• **Chaos test:** one worker killed under load lost or duplicated **0 of 2,177** transfers.<br>• **Tests:** two simulated workers compute identical features. | `backend/app/services/scoring.py`, `docs/reports/load_test.md` |

**Why not 15:** there are no real transactions, and Kafka is not deployed. Per-wallet locks are durable enough for this scale, but a strict judge may want an event log.

---

## 5. Innovation: 8.0 → expected 9.3 / 10

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Which elements add detection beyond existing fraud and rule systems | ✅ | Marginal-contribution table (graph layer: +7.9 points of fraud flagged, −৳9,636/day). The leave-one-family-out "rescue" shows what the rules, graph and agent layers add for fraud the model has never seen. | evaluation §1, §3 |
| J2 | "Warning pop-ups are already common" | ✅ | Beyond a pop-up:<br>• on-call signal ("are you being told to send this now?")<br>• 20-second cooling-off before "send anyway"<br>• "call someone you trust"<br>• spoken Bangla warning<br>• one-tap appeal<br>• reasons shown only when the facts agree<br>All are tested in the browser. | Customer app, `frontend/e2e/features.spec.ts` |
| J3 | Measurable value of graph, anomaly, verified explanations and pre-transaction intervention over a conventional classifier | ✅ | Graph and anomaly: ablation with confidence intervals and cost. Pre-transaction: control-point analysis. Verified explanations: the reason-code truthfulness test and the GenAI evaluation (100% grounded). | evaluation §1, `docs/reports/genai_eval.md` |

**Why not 10:** the value of the UX ideas is argued, not yet measured (the user study would also measure it).

---

## 6. Scalability & integration: 7.67 → expected 9.2 / 10

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Load test at production volume; reliability, failover, monitoring, integration with live infrastructure | 🟡 | • **Load test:** 52 → 93 → 169 requests/s with 1 → 2 → 4 workers, 0 errors. Measured on a laptop, not at production volume.<br>• **Failover:** measured with the chaos test.<br>• **Monitoring:** Prometheus plus a provisioned Grafana dashboard.<br>• **Integration contract:** OpenAPI, sample payloads, a sequence diagram and a timeout rule. | `docs/reports/load_test.md`, `deploy/monitoring`, `docs/INTEGRATION.md` |
| J2 | "Drawing group maps every ten minutes will slow down" | ✅ | Benchmark:<br>• rebuild time grows roughly linearly with the edges in a fixed 14-day window and runs off the request path<br>• online graph counters cost well under a millisecond per transfer<br>• partitioning and incremental PageRank documented as the scale-out path | `docs/reports/graph_benchmark.md` |
| J3 | Horizontal scaling validated; p95/p99 under concurrency; ordering and idempotency across workers; graph refresh under continuous ingestion | ✅ | Measured p50/p95/p99 under load: 11.6 / 26.0 / 35.8 ms. Ordering and idempotency verified across workers (chaos test, no duplicate rows). **Update:** graph rebuild under continuous ingestion measured: 12 rebuilds during 2,285 committed transfers in 40 s took 0.83–1.28 s each, while scoring kept serving. | `docs/reports/load_test.md` |

**Why not 10:** throughput was measured on a laptop, not a production cluster. No published peak volume for upay is available to size against.

---

## 7. Responsible AI & security: 3.33 → expected 4.4 / 5

| Judge | Asked for | Status | What answers it | Where |
|---|---|---|---|---|
| J1 | Appeal/release process, drift monitoring, access control, data privacy, regular fairness monitoring | ✅ | • **Appeal:** "Not a scam? Appeal" button; the case jumps the queue with a 15-minute SLA; `legit` releases the HOLD and becomes a training label.<br>• **Drift:** PSI drift endpoint and Impact panel; it correctly flagged the load-test traffic.<br>• **Access and audit:** roles plus an audit log.<br>• **Privacy and retention:** rules in the governance page.<br>• **Fairness:** a segment report every retrain. | `docs/GOVERNANCE.md`, `/dashboard` |
| J2 | Honest shopkeepers with many new buyers flagged too often | ✅ | Merchant-aware features: false alarms for merchants as senders fall from **2.9% to 0.6%**, and for all legitimate transfers from 0.68% to 0.20%. **Fraud recall is unchanged** (96.9%, and unchanged for age 65+). | evaluation §8 |
| J3 | Validate fairness and calibration on independently governed data **before** enabling segment-specific thresholds; measure cancellation, complaints and false positives by segment; do not reduce protection for higher-risk groups | ✅ | FPR, FNR, warning rate and ECE are reported per segment. Protection for high-risk groups is checked (65+ recall unchanged; transfers to new people keep full protection). **Update:** the merchant segment override now runs in **shadow** (`shadow: true`): evaluated and logged on every decision, not applied, until validated on governed data, exactly as this judge asked. Note: the before/after merchant numbers in evaluation §8 were measured with the override enforced; with it in shadow, the part of the merchant-sender reduction that comes from the override waits for that validation. The graph's merchant-awareness stays on because it reduces false alarms without touching thresholds. Cancellation and complaint rates by segment come from the user study (complaint question added) or a pilot. | evaluation §8, `config/policy.yaml` |

**Why not 5:** fairness was validated only on our own synthetic data. The 65+ group's fraud recall (FNR 27%) rests on only 11 test cases, too few to conclude anything.

---

## 8. What would take it from ≈ 93 to 100

Ordered by points per effort. Only the first two are within the team's reach before the next round.

| # | Action | Who | Effort | Likely points |
|---|---|---|---|---|
| 1 | **Run the WARN user study** with 60+ participants (20 per group) on `/study`. Report the cancel rate with its confidence interval, and use group C's lower bound in the impact model. (The complaint-intent question is already in the tool.) | Team | 1 day | +1.5 to +2.5 (Business, Innovation, Responsible AI) |
| 2 | **Analyst workload trial**: 3–5 people triage 50 cases with and without the AI summary. Time and accuracy are already recorded per case. | Team | ½ day | +0.5 (Business) |
| 3 | ~~Put the merchant override in shadow~~ **Done.** | — | — | — |
| 4 | **External sanity check** on PaySim (mobile money) and Elliptic (graph): same pipeline, reported as a transfer test. | Team | 1 day | +0.5 (AI/ML) |
| 5 | ~~Graph refresh under ingestion~~ **Done** (0.83–1.28 s per rebuild under load). | — | — | — |
| 6 | **Shadow-mode run on governed upay data** (offline back-test, then live shadow), reporting the same evidence pack. | upay + team | weeks | +2 to +3 (AI/ML, Prototype, Responsible AI) |
| 7 | Kafka/Redpanda event log partitioned by wallet, if judges insist on durable ordering. | Team | 1–2 days | +0.2 |

**Realistic ceiling:** about **95–96** with items 1–5. Getting from there to 100 needs item 6 (real upay data in shadow mode), which a hackathon team cannot obtain on its own. The Shurokkha 100 plan says the same.

---

## 9. Presenting it (one line per criterion, for the next round)

- **Problem:** "Cited MFS figures + control-point analysis + an agent cash-out module, so cash-out scams are now covered."
- **AI/ML:** "Ablation with confidence intervals and cost; unseen-family, shift and adversarial tests; harder data; no leakage."
- **Business:** "ROI with break-even and sensitivity; measured vs simulated kept separate; user study [results / running]."
- **Prototype:** "Multi-worker with shared Redis state; killing a worker under load lost 0 decisions; shadow mode ready."
- **Innovation:** "Graph layer: +7.9 points of fraud flagged, −৳9.6k/day; beyond a pop-up: call signal, cooling-off, voice, appeal."
- **Scalability:** "Near-linear 1 → 4 workers, p95 26 ms; Grafana monitoring; graph rebuild off the request path."
- **Responsible AI:** "Appeal with SLA, drift monitor, merchant false alarms −79% at unchanged recall, segment FNR and calibration."

Every claim links to evidence in [JUDGE_RESPONSE.md](JUDGE_RESPONSE.md). Label every number on the slides as *Measured*, *Simulated* or *Estimate*.
