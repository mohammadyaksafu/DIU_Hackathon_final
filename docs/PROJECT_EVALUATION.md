# Shurokkha: Independent Project Evaluation

**Evaluated:** 2026-10-04 · commit `9b12b6b` · repo `mohammadyaksafu/DIU_Hackathon_final`
**Viewpoints:** UI/UX design, web design, solution architecture, web development, machine-learning engineering
**Method:** read the code, docs and model reports; ran the test suite (40/40 pass), the production build and the live API; drove the customer demo end to end in a real browser (headless Chrome).

---

## Phase 2 response to the judges (2026-10-07): self-assessment ≈ **95 / 100** on the judges' rubric

The judges scored Phase 1 at ≈ 83 / 100 and asked for **evidence, not features**. Every comment is mapped to code or a report in [JUDGE_RESPONSE.md](JUDGE_RESPONSE.md). This is our own estimate; only the judges award points.

| Criterion | Phase 1 (judges) | Max | Self-assessment | Main evidence added |
|---|---:|---:|---:|---|
| Problem relevance | 18.33 | 20 | 19.5 | Cited MFS statistics, fraud × loss × segment matrix, control-point analysis, agent cash-out module |
| AI/ML depth | 16.33 | 20 | 19 | Ablation with cost + CIs, LOFO model vs system, shift suite, adversarial rounds, leakage audit, harder data, cost-optimal thresholds |
| Business/customer impact | 17.00 | 20 | 18.5 | Measured vs simulated split, ROI + tornado + break-even, user-study tool (no participants yet) |
| Prototype quality | 12.33 | 15 | 14.5 | Multi-worker Redis state, idempotency across workers, optimistic locking, chaos test (0 lost / 0 duplicated), shadow mode, CI browser tests |
| Innovation | 8.00 | 10 | 9 | Marginal-contribution table; on-call signal, cooling-off, trusted-person prompt, voice warning |
| Scalability & integration | 7.67 | 10 | 9.5 | Load test 1/2/4 workers with p95/p99, failover, Prometheus + Grafana, graph benchmark, integration contract |
| Responsible AI & security | 3.33 | 5 | 4.5 | Appeal flow with SLA, merchant-aware fix (FP down, recall unchanged), segment FNR/ECE, drift PSI, governance page |
| **Total** | **≈ 83** | **100** | **≈ 94.5** | |

**Why not 100 yet (honest):** the WARN user study has no participants yet (the tool is ready: about one day of sessions with 60+ people turns "assumed" into "measured"); there is no real upay data for shadow-mode validation; PaySim / Elliptic external checks are not done; Kafka ordering is documented, not deployed. The plan's own note applies: without production data, the mid-90s is close to the ceiling.

## Second round (2026-10-07): **92 / 100**

The engineering items from "what is left" that do not need a retrain were done and verified: 49 backend tests, 12 Playwright browser tests (including axe, 0 WCAG 2.1 AA violations), typecheck, ESLint, production build, `pip-audit` clean.

| # | Area | Before | After | What changed |
|---|---|---:|---:|---|
| 1 | Problem fit & impact | 13 | **14** | Loss prevented shown as a range (৳604,500–৳607,700 for 40–80% of warnings heeded) and analyst time saved (≈9 h/day), with the assumptions on the Impact page |
| 4 | Architecture & code | 13 | **15** | Online feature state, live graph edges and rate limits shared in Redis: several API workers, live history survives restarts, in-memory fallback; Alembic migrations applied on startup (pre-Alembic databases adopted); model activation followed by every worker |
| 7 | Deployment & ops | 5 | **5** | Redis with append-only persistence; `API_WORKERS` setting; browser tests in CI |
| | **Total** | **89** | **92** | |

### Still left
**Only you can do these:** demo video link (README line 5), team name and members, `ADMIN_PASSWORD` on the server, `python -m pipelines.genai_eval` on the server with a Gemini key, and being ready to explain the development timeline.

**Needs a retrain (and then new model card, robustness report, screenshots and Word report numbers):**
- Harder synthetic fraud in the generator, and retraining with the leave-one-out findings (new mule networks are caught 47% by the model alone).
- Seller-specific features for the edge case below (an online seller's first payment to the weakest ring wallet scores just under WARN).
- Real-data validation (shadow mode) is still the only way to prove production performance.

---

## Re-evaluation after fixes (2026-10-04): **89 / 100**

Every finding below that could be fixed in code was fixed and verified: 42 backend tests, typecheck, ESLint, production build, 15 browser checks, and an axe accessibility audit (0 WCAG 2.1 AA violations on all 8 pages).

| # | Area | Before | After | What changed |
|---|---|---:|---:|---|
| 1 | Problem fit & impact | 13 | **13** | Unchanged (loss-prevented range and analyst time saved still to add) |
| 2 | Machine learning | 15 | **18** | Robustness report: leave-one-scenario-out, unseen-ring test, calibration (ECE 0.0024); demo rotates between 5 mule wallets |
| 3 | Generative AI | 8 | **9** | Evaluation harness (100% grounded / valid citations / consistent); found and fixed the "SOP-05 read as 5" bug that silently rejected valid AI summaries |
| 4 | Architecture & code | 12 | **13** | 47 dependency vulnerabilities fixed (FastAPI/Starlette, PyJWT, python-multipart, pytest); strict audit + ESLint in CI; 7 React effect bugs fixed |
| 5 | UI / UX | 11 | **14** | Customer page: phone + 3 tabs; consistent Bangla in the wallet; risk level vs thresholds with "Why HOLD?"; 0 accessibility violations; skip link; analyst start-here guide; screenshots |
| 6 | Security & responsible AI | 6 | **9** | Admin password separated and never shipped to the browser; production disables admin until set; concrete 65+ fairness plan |
| 7 | Deployment & ops | 4 | **5** | `deploy/deploy.sh`: backup, pull, rebuild, health check; nightly backups via cron |
| 8 | Documentation & submission | 6 | **8** | Live URLs in README, Gemini disclosed, report updated (MD + Word with robustness, GenAI eval and screenshots), model card extended |
| | **Total** | **75** | **89** | |

### Why not 100 yet: what is left
**Only you can do these (about +4 points):**
- **Record the demo video** and put its link in README line 5 (the last placeholder).
- **Team name and members** on the report cover and in `docs/PROJECT_TITLE.md` / `docs/PROJECT_REPORT.md`.
- **Set `ADMIN_PASSWORD`** in `deploy/.env` on the server (otherwise Admin stays read-only, which is safe but means you cannot demo live policy edits).
- **Run `python -m pipelines.genai_eval` on the server with a Gemini key**, so the GenAI results cover real AI output, not only the template fallback (locally there is no key).
- Be ready to explain the **development timeline** (the first commit is large).

**Engineering that is bigger than a quick fix (about +5 points):**
- Move online features and the rate limiter to Redis so the API can run several workers (today: one worker, documented).
- Add Alembic database migrations.
- Run the browser tests in CI (they currently run locally against a live stack).
- Harder synthetic fraud in the generator, and retraining with the leave-one-out findings (new mule networks are caught 47% by the model alone).
- Known edge case: an online seller's first payment to the weakest ring wallet scores 0.048, just under WARN, because sellers routinely pay new numbers. This is the same trade-off as the seller false-positive finding; fix it with seller-specific features, not by lowering the threshold for everyone.
- Real-data validation (shadow mode) is the only way to prove production performance; no synthetic project can score 100 on that.

---

## Original evaluation (before fixes)

### Overall score before fixes: **75 / 100**

A strong, unusually complete hackathon project. The architecture and the responsible-AI story are well above typical entries. What holds it back is not the core idea but **credibility details a judge will notice quickly**: results that look too good to be true, a decision display that contradicts itself (a "38% risk" transfer put on HOLD), an admin password that ships to every browser, and submission materials that are still unfinished.

| # | Area | Weight | Score | Verdict |
|---|---|---:|---:|---|
| 1 | Problem fit & real-life impact | 15 | **13** | Excellent framing, very relevant to upay |
| 2 | Machine learning approach | 20 | **15** | Sound method, but synthetic results are not believable as-is |
| 3 | Generative AI use | 10 | **8** | Grounded, guarded, with fallbacks: a mature design |
| 4 | Solution architecture & code quality | 15 | **12** | Clean and modular; single-worker limits |
| 5 | UI / UX & web design | 15 | **11** | Polished visual system; the customer page is overloaded |
| 6 | Security & responsible AI | 10 | **6** | Great responsible-AI design; demo auth is unsafe in public |
| 7 | Deployment & operations | 5 | **4** | Docker, Caddy HTTPS, CI, health and metrics |
| 8 | Documentation & submission readiness | 10 | **6** | Rich docs, but placeholders, a stale report and a commit-history risk |
| | **Total** | **100** | **75** | |

> Score bands: 90+ winning-level polish · 80–89 top-tier · 70–79 strong with fixable gaps · <70 major gaps.
> With the **Priority 1** fixes below (about one working day), this project realistically moves to **84–88**: security +3, documentation +3, ML and UX display +3.

---

## 1. Problem fit & real-life impact (13 / 15)

**Strengths**
- Targets a real, specific harm: prize / refund scams, SIM-swap account takeover and mule cash-out networks hitting first-time MFS users.
- Answers the guideline's three questions (What happened? Why risky? What next?) explicitly, everywhere.
- Persona-driven (Rahima the remittance receiver) and Bangla-first, so it speaks to financial inclusion, not just fraud.
- Impact is quantified in money (94.3% of victim-loss value flagged) with the key assumption stated (60% of warned victims cancel).

**Gaps**
- The "৳606,100 prevented" figure depends on an unvalidated 60% assumption. Present it as a range (for example 40–80%) so judges see you understand the uncertainty.
- No estimate of the analyst workload saved (minutes per case, alerts per analyst per day), which is the number an operations manager asks for first.

---

## 2. Machine learning approach (15 / 20)

**Strengths**
- Correct time-based split (train / validation / test), thresholds learned on validation only, test touched once.
- One feature engine for training replay and live serving, so there is no train/serve skew. This is a production-grade decision most teams miss.
- Hybrid detectors (rules + Isolation Forest + calibrated LightGBM + graph) with an honest **lift table** proving each layer adds value.
- Exact TreeSHAP reasons that are emitted only when factually true. Excellent explainability discipline.
- Model card, fairness report and per-scenario recall: genuinely professional.

**Problems a judge will spot**
1. **Results look too good.** PR-AUC 0.995 and ROC-AUC 0.9998 tell an experienced ML judge "the synthetic data is too easy", not "the model is great". The fraud scenarios are injected with patterns the features were designed to detect, so the evaluation partly measures the generator, not the model.
2. **Thresholds hit their floors.** The model card shows `warn_t = 0.05` (the floor) and `hold_t = 0.10` (floor + 0.05). The learned thresholds collapsed onto the hard-coded minimums, which suggests that score separation is near-perfect (see point 1) and that the thresholds are not really learned.
3. **The risk score contradicts the decision.** In the live demo the prize scam shows **risk 0.385 → HOLD** (and 0.587 → HOLD). A viewer reads "38% risk, yet blocked?" The calibrated probability, the policy tiers and the display are not aligned.
4. **One ring wallet for every scam.** Every prize-scam and takeover demo pays the same wallet (`C90900`), so the demo always hits the most obvious mule. Judges may ask "what about a ring you have not seen?"
5. **No robustness or drift tests:** no results for unseen fraud patterns, adversarial behaviour (a mule that waits before cashing out), or a later time window.

**How to improve**
- Add **harder synthetic fraud**: noisier scams, slower mules, fraud that looks like online sellers. Report a *hard* test set beside the easy one; a believable 0.85–0.92 PR-AUC is more convincing than 0.995.
- Add a **"leave-one-scenario-out"** evaluation: train without, say, the refund scam and test whether it is still caught (generalisation to new fraud).
- Show customers a **risk band** (Low / Medium / High) derived from the policy tier, not the raw calibrated number. Keep the raw score in "Behind the scenes" and explain that HOLD is triggered by policy tiers and rules (for example ATO combo), not by the score alone.
- Recalibrate (isotonic, or Platt on a larger window) and report a **reliability diagram**.
- Rotate ring wallets in the demo scenarios, including one newly formed ring caught only by live fan-in features.

---

## 3. Generative AI use (8 / 10)

**Strengths**
- The LLM narrates and never decides, which is clearly stated and enforced.
- Evidence-only prompts, JSON-schema output, numeric-grounding check, prompt-injection isolation, circuit breaker, timeout, and deterministic fallbacks. This is a mature, safety-first design.
- Provider-agnostic gateway (Gemini or Claude), with BM25 SOP retrieval and citations.

**Gaps**
- No evaluation of the GenAI output itself: no measured groundedness or citation accuracy, and no comparison against the template baseline. Even 20 hand-graded cases would make this score 10/10.
- BM25 retrieval is fine for a handful of SOPs, but there is no evidence of how it fails on paraphrased Bangla questions.
- The new free-form chat ("anything else") widens the attack surface compared with the tightly grounded case summary. Make sure its guardrails are as strict.

---

## 4. Solution architecture & code quality (12 / 15)

**Strengths**
- Clear module boundaries: `features`, `detectors`, `policy`, `explain`, `graph`, `genai`, `services`, `api`.
- Plug-in detectors (one file + one YAML line), hot-reloadable policy, versioned model registry: extensible in exactly the way the on-site "new requirements" round rewards.
- Idempotent scoring, audit log, health / readiness probes, Prometheus metrics, JSON logs.
- 40 backend tests including golden scenarios, fallbacks and a model-quality gate; CI with tests, typecheck, build and gitleaks.

**Gaps**
- **Single worker by design:** online feature state lives in process memory, so the API cannot scale horizontally or survive a restart without losing live state. This is documented honestly, but it is the first thing an architect will challenge.
- **No database migrations** (no Alembic). Schema changes on the Postgres deployment will be manual and risky.
- **The rate limiter is in memory**, so it resets on restart and does not work across instances.
- The `pip-audit` step in CI is `|| true`, so it can never fail the build.
- **Frontend has no tests and no ESLint configuration.** Only a typecheck guards ~2,300 lines of UI.
- The customer page has grown to around 450 lines in one component. Split it into `WalletForm`, `ScenarioPicker`, `PayloadView`, `DecisionCard` and `SafetyExamples`.

**How to improve**
- Move online features to **Redis** (already a dependency) behind the current engine interface. This unlocks multiple workers.
- Add Alembic with an initial migration.
- Use Redis for the rate limiter; make `pip-audit` fail on high-severity issues.
- Add `eslint` (Next.js config) plus a couple of Playwright smoke tests (customer HOLD flow, analyst case page).

---

## 5. UI / UX & web design (11 / 15)

**Strengths**
- Coherent design system: tokens, light and dark themes, consistent cards, buttons and form controls; colour-blind-safe chart palette; status colours always paired with icon and text.
- Strong home page: clear value proposition, a phone-style preview of the real warning, and a numbered decision pipeline.
- The customer warning card is excellent UX: plain Bangla, specific reasons, a clear primary action ("Cancel this transfer").
- The new "data sent to the backend" panel makes the system explainable to judges.

**Problems**
1. **The customer page tries to be three things at once:** a realistic wallet, a teaching page (safety examples with fake `DEMO-…` wallets that do nothing), and a developer view (payload, signals, raw JSON). For a judge it is long and it is unclear which examples are "real". The right-hand safety examples now duplicate the working scenarios below the form.
2. **Mixed languages in one view:** Bangla wallet, English technical labels ("send money", "Behind the scenes", "risk", "lgbm"), Bangla-English hybrids. Pick a rule: the customer side is fully Bangla with an English toggle, and the operator side is fully English.
3. **Raw numbers shown to customers** (risk 0.385 next to HOLD), as covered in the ML section.
4. **Accessibility is partial:** about 45 ARIA attributes in total; no skip-link; no visible keyboard order through the phone mock-up; the `font-mono` used for Bangla values renders unevenly. No Lighthouse or axe audit has been done.
5. **The analyst console has no "first-use" guidance.** A judge landing there does not know which alert to open. A pinned "Start here: case #…" would help.
6. **No screenshots or GIFs** in the README or the report. Judges skim; pictures sell the UX.

**How to improve**
- Restructure the customer page into tabs or a stepper: **① Wallet** (form + scenarios + warning) · **② What the AI saw** (payload + signals) · **③ Learn to spot scams** (the safety examples). Merge the safety examples into the real scenarios ("Try this one live").
- Apply the language rule consistently, translating the remaining English labels on the customer side.
- Run axe or Lighthouse and fix contrast and focus issues; add a skip-to-content link.
- Add a guided "Demo mode" banner: *Step 1 choose Lipi → Step 2 run account takeover → Step 3 open the alert*.

---

## 6. Security & responsible AI (6 / 10)

**Strengths (responsible AI is a highlight)**
- 100% synthetic data, pseudonymous IDs to the LLM, human review for every HOLD, no permanent auto-block, a fairness audit with stated mitigations, verified explanations.
- JWT roles, sandboxed policy expressions, prompt-injection isolation, audit log, secret scanning in CI.

**Critical issue**
- **The admin password ships to every visitor.** The frontend logs in automatically using `NEXT_PUBLIC_DEMO_PASSWORD`, which is compiled into the public JavaScript bundle, and the `admin` user shares that same password. Anyone who opens the live site can obtain an **admin token** and change the live risk policy or the active model through the API directly. Restricting the Admin *page* by IP in Caddy (optional and not enabled by default) does not stop direct API calls with that token unless the admin API path is also blocked.

**How to fix (high priority before judging)**
- Give `admin` (and ideally `analyst`) a **separate password that is never sent to the browser**, and only auto-login the `customer` role, or
- make the live deployment's admin API **read-only** (a feature flag), and enable the Caddy IP block for `/api/v1/admin/*` by default.
- Also: the fairness report flags the **65+ age band** (0.50% FPR, 3.3× the lowest band). Mention a concrete mitigation, not only monitoring, because elderly users are a core persona.

---

## 7. Deployment & operations (4 / 5)

**Strengths:** Docker Compose production stack, Caddy with automatic HTTPS, health checks, restart policies, swap guidance, a clear VPS runbook, and CI on every push.

**Gaps:** deployment is manual (SSH + `git pull`). Add a GitHub Actions deploy job, or at least a one-line `deploy.sh`. No backups are scheduled (the database dump command exists but is never automated). There is no uptime monitoring for the live link judges will use.

---

## 8. Documentation & submission readiness (6 / 10)

**Strengths:** an excellent README (it meets every rulebook §6.2 item), an architecture document, model card, data assumptions, extending guide, disclosures, and the new title, abstract and Word report.

**Must fix before submission**
1. **README placeholders:** `<add-frontend-url-after-deploy>`, `<add-api-url>`, `<add-video-link>` are still in the README (lines 5 and 156). The live URL exists now: https://165-99-219-251.sslip.io.
2. **Team name and members** are placeholders in `PROJECT_TITLE.md`, `PROJECT_REPORT.md` and the Word report.
3. **`DISCLOSURES.md` lists only Claude.** Gemini is now the default provider and must be disclosed (rulebook 4.4).
4. **`docs/PROJECT_REPORT.md` is stale:** it still says "Claude via the Anthropic SDK". Either update it or delete it in favour of the Word report.
5. **Commit-history risk (rulebook 4.1, 4.3, 8.3):** the first commit (2026-10-02) adds **116 files and 10,827 lines at once**. Judges check that work was done during the hackathon; one giant initial commit can look like a pre-built solution. You cannot rewrite this honestly, but you can (a) keep committing small, well-described changes from now on, especially during the on-site round, and (b) be ready to explain the development timeline (the master plan and design notes help).
6. **No demo video yet**, and no screenshots in `docs/`.

---

## Priority action list

### Priority 1: before submission (about one day, the biggest score gain)
| # | Action | Area | Effort |
|---|---|---|---|
| 1 | Separate the admin password from the browser; auto-login customer only; block `/api/v1/admin/*` by default on the public site | Security | 1–2 h |
| 2 | Fill README live URL, video link, team names; add Gemini to DISCLOSURES; update or remove the stale `PROJECT_REPORT.md` | Docs | 1 h |
| 3 | Show customers a risk **band** (Low / Medium / High) from the policy tier, not "risk 0.385"; explain HOLD triggers in "Behind the scenes" | ML + UX | 2 h |
| 4 | Record the demo video following the guided flow (normal → prize scam → account takeover → analyst case → AI summary) | Submission | 2 h |
| 5 | Add 4–6 screenshots to README and the report | Docs | 1 h |

### Priority 2: strengthens the ML story (1–2 days)
| # | Action | Area |
|---|---|---|
| 6 | Add a harder synthetic test set and a leave-one-scenario-out evaluation; report both | ML |
| 7 | Reliability diagram + recalibration; check that thresholds are not stuck at their floors | ML |
| 8 | Rotate ring wallets in scenarios; add a "brand-new ring" demo | ML / Demo |
| 9 | Hand-grade 20 AI case summaries for groundedness and citation accuracy | GenAI |
| 10 | Concrete mitigation for the 65+ false-positive gap | Responsible AI |

### Priority 3: production readiness and polish
| # | Action | Area |
|---|---|---|
| 11 | Restructure the customer page into Wallet / What the AI saw / Learn tabs; one language rule per audience | UX |
| 12 | Split the customer page component; add ESLint and Playwright smoke tests | Frontend |
| 13 | Online features and rate limiter in Redis → multiple API workers | Architecture |
| 14 | Alembic migrations; make `pip-audit` fail on high severity | Backend |
| 15 | Automated deploy job, scheduled database backups, uptime check | Ops |
| 16 | axe / Lighthouse accessibility pass, skip-link, analyst "Start here" guide | UX |

---

## Bottom line

Shurokkha already has what most hackathon projects lack: a real end-to-end system, honest documentation, and responsible-AI thinking built into the architecture rather than added at the end. To win, **make it believable and safe**: fix the exposed admin access, stop showing a raw score that contradicts the decision, present harder and more honest ML results, and finish the submission materials. Those changes are small compared with what is already built, and they address exactly the questions sharp judges will ask.
