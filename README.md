# Shurokkha (সুরক্ষা): AI Trust & Financial-Safety Copilot for upay

> **Stop the scam *before* the money leaves.** Shurokkha scores every transfer in milliseconds, explains risk to the customer in plain Bangla, finds money-mule rings in the transaction graph, and gives analysts an AI case summary grounded only in evidence.

**Live demo:** https://165-99-219-251.sslip.io · **API docs:** https://165-99-219-251.sslip.io/docs · **Health:** https://165-99-219-251.sslip.io/health/ready · **Video:** `<add-video-link>` · **Report:** [docs/Shurokkha_Project_Report.docx](docs/Shurokkha_Project_Report.docx)
AI DEV FEST 2026 · DIU CPC × upay AI Hackathon · Track 01 *Trust & Risk Intelligence* (with Track 03 customer empowerment and Track 06 investigation copilot)

> All data in this project is **synthetic**. No real customer, phone number or transaction is used.

---

## 1. Project overview

**Problem.** For first-time and low-digital-literacy MFS users, social-engineering scams ("you won a prize, pay the fee", "wrong send, please refund"), account takeovers after SIM swaps, and money-mule networks cause irreversible losses and erode trust in digital wallets. Risk teams review alerts manually, slowly, and with little context.

**Solution.** A real-time decision-intelligence service that answers the guideline's three questions for every transfer:

| Question | How Shurokkha answers it |
|---|---|
| **What happened?** | Point-in-time behavioural, device, SIM-swap and network features for the transfer |
| **Why is it risky?** | Calibrated ML + anomaly + graph + rule signals, explained with verified SHAP reason codes in Bangla and English |
| **What should upay do next?** | A transparent YAML policy chooses **ALLOW / WARN / HOLD**. WARN interrupts the customer with a Bangla explanation. HOLD goes to a human analyst with an AI case summary and SOP-cited next steps. |

**Purpose.** Protect vulnerable customers, cut fraud losses at a fixed alert budget, and make analysts faster, while staying explainable, fair and human-supervised.

## 2. Features (and how AI is used)

| # | Feature | AI / technique |
|---|---|---|
| F1 | Real-time risk scoring API (`POST /api/v1/score`, ~5 ms server-side) | LightGBM (Platt-calibrated) on 46 point-in-time features |
| F2 | Hybrid decision engine: ALLOW / WARN / HOLD | Rules + ML + anomaly + graph signals → hot-reloadable YAML policy |
| F3 | Verified reason codes in Bangla/English | Exact TreeSHAP contributions → reason codes emitted only if factually true |
| F4 | Customer wallet simulator with the pre-transaction **scam interrupt** | Deterministic templates (customer text never depends on an LLM) |
| F5 | Analyst console: ranked queue, case view, feedback loop | Calibrated risk ranking; labels feed retraining |
| F6 | Money-mule network view | Transaction graph, Louvain communities, PageRank, fan-in / forwarding features |
| F7 | AI investigation copilot + conversational chat | Gemini via server-side API key, page/case-aware answers, BM25 SOP citations, evidence-grounded summaries, deterministic fallbacks |
| F8 | Impact & fairness dashboard | Held-out metrics, lift table, per-scenario recall, FPR by segment, live latency |
| F9 | Synthetic data generator with 6 injected fraud scenarios | Seeded simulation of 7 personas, legit look-alikes and labelled fraud |
| + | Batch / CSV scoring, behaviour anomaly detection | Isolation Forest (compiled single-row scorer, verified equal to scikit-learn) |
| F10 | **Agent cash-out module**: fresh inflow drained at an agent, agent serving many first-time customers | Agent-side velocity features + transparent detector; WARN (OTP / voice confirm) or HOLD with the mule graph |
| F11 | **Beyond a pop-up**: on-call signal, 20 s cooling-off before "send anyway", "call someone you trust", Bangla voice warning | Rule on live call state; Web Speech API; reasons shown only when facts and SHAP agree |
| F12 | **Customer appeal** ("not a scam?") with a 15-minute SLA; appealed cases jump the queue; `legit` releases the HOLD and becomes a training label | Human-in-the-loop feedback |
| F13 | **Rollout modes** `shadow → warn → enforce`, fail-safe `on_scoring_error` | Policy config, hot-reloaded |
| F14 | **WARN user study tool** (`/study`): 3 randomised arms, measured cancel / continue rates with 95% CIs | Experiment design (see [docs/USER_STUDY.md](docs/USER_STUDY.md)) |
| F15 | **Evidence pack**: ablation with cost and CIs, cost-optimal thresholds, leave-one-family-out, distribution shift, adversarial rounds, leakage audit, harder data, segment fairness | [docs/reports/evaluation.md](docs/reports/evaluation.md) |
| F16 | **Scale & operations**: several API workers sharing state in Redis, drift (PSI) monitoring, Prometheus + Grafana, Alembic migrations | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |

**Judges' feedback and what we did:** [docs/JUDGE_RESPONSE.md](docs/JUDGE_RESPONSE.md) · problem evidence with citations: [docs/EVIDENCE.md](docs/EVIDENCE.md) · governance: [docs/GOVERNANCE.md](docs/GOVERNANCE.md) · integration contract: [docs/INTEGRATION.md](docs/INTEGRATION.md)

## Screenshots

| | |
|---|---|
| ![Home](docs/screenshots/01-home.png) **Overview**: value proposition, live results, decision pipeline | ![Customer HOLD](docs/screenshots/03-customer-hold.png) **Scam interrupt**: account takeover held, Bangla explanation |
| ![What the AI saw](docs/screenshots/04-customer-ai-tab.png) **What the AI saw**: exact request, flagged new phone and area, risk level vs thresholds, why HOLD | ![Analyst queue](docs/screenshots/05-analyst-queue.png) **Analyst console**: ranked queue with a start-here guide |
| ![Case](docs/screenshots/06-case.png) **Case view**: evidence, SHAP drivers, mule-ring network, AI summary | ![Impact](docs/screenshots/07-impact.png) **Impact dashboard**: lift, per-scenario recall, fairness |
| ![Admin](docs/screenshots/08-admin-readonly.png) **Admin**: live policy editing, read-only until the admin password is entered | ![Mobile](docs/screenshots/09-mobile-customer.png) **Mobile**: responsive wallet |

## 3. Architecture

```mermaid
flowchart LR
    A[Customer app / partner API] -->|/score| B[FastAPI]
    B --> C[Feature engine<br/>point-in-time, same code offline & online]
    C --> D{Detector registry<br/>detectors.yaml}
    D --> D1[Rules<br/>rules.yaml]
    D --> D2[Isolation Forest]
    D --> D3[LightGBM + calibration]
    D --> D4[Graph mule risk]
    D1 & D2 & D3 & D4 --> E[Policy engine<br/>policy.yaml, hot reload]
    E --> F[SHAP reason codes<br/>bn / en]
    F --> G[Decision ALLOW/WARN/HOLD]
    G --> H[Customer warning]
    G --> I[(Alerts / audit<br/>SQLite or Postgres)]
    I --> J[Analyst console]
    J --> K[LLM gateway + RAG<br/>case narrative]
    J -->|labels| L[Retrain → model registry]
    M[Graph snapshot refresher<br/>cold path] --> C
```

- **Hot path (sync, ~5 ms):** features → detectors → policy → (SHAP only when flagged).
- **Warm path (async-capable):** LLM case summary (cached by evidence hash).
- **Cold path (background):** graph snapshot rebuild every 10 min, retraining via pipeline.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · model: [docs/MODEL_CARD.md](docs/MODEL_CARD.md) · data: [docs/DATA_ASSUMPTIONS.md](docs/DATA_ASSUMPTIONS.md) · extending on-site: [docs/EXTENDING.md](docs/EXTENDING.md)

## 4. Technology stack

| Layer | Technology |
|---|---|
| Languages | Python 3.10+ (3.11 in Docker), TypeScript |
| ML | LightGBM 4.7, scikit-learn 1.7 (Isolation Forest, logistic regression baseline), NetworkX 3.4 (Louvain, PageRank), NumPy, pandas, PyArrow |
| GenAI | Gemini Interactions API (stateless structured JSON; configurable model), optional Anthropic provider; BM25 SOP retrieval (no external vector DB) |
| API | FastAPI 0.115, Pydantic v2, SQLAlchemy 2, PyJWT, Uvicorn |
| Storage | SQLite (default, WAL) or PostgreSQL; optional Redis cache |
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS 4, Recharts 3, d3-force |
| Ops | Docker, docker compose, Alembic migrations, GitHub Actions (tests, typecheck, lint, build, Playwright browser tests, dependency audit, gitleaks), Prometheus-format `/metrics`, JSON logs |

## 5. Requirements

- **Python 3.10+** and **Node.js 20.9+** (22 recommended), *or* Docker 24+ with Compose
- ~2 GB RAM, ~1 GB disk (dependencies + generated data)
- Optional: a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) for chat and AI summaries. The free tier has usage limits that depend on the model/account; check current quotas in AI Studio. Without an AI key, the app uses deterministic fallbacks.
- Optional: PostgreSQL 14+ and Redis 7+ (defaults: SQLite + in-memory cache)

## 6. Installation & setup

### Option A: Docker (one command)
```bash
docker compose up --build        # web http://localhost:3000 · API http://localhost:8000/docs
```
The API image generates the synthetic data and trains the model at build time (deterministic, seed 42; a few minutes).

### Option B: local development
```bash
# 1) Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # optional: edit values (see section 7)
python -m pipelines.run_all        # generate data -> features -> train -> evaluate -> register (~3-4 min)
uvicorn app.main:app --port 8000   # API at http://localhost:8000/docs

# 2) Frontend (new terminal)
cd frontend
npm ci
cp .env.example .env.local         # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                        # http://localhost:3000
```
If you skip `run_all`, the API bootstraps the data and model automatically on first start (`AUTO_BOOTSTRAP=true`).

## 7. Environment variables

Backend (`backend/.env`; all optional, safe defaults):

| Variable | Purpose | Example / default |
|---|---|---|
| `DATABASE_URL` | Postgres URL; empty = SQLite in `backend/data/` | `postgresql://user:pass@host:5432/shurokkha` |
| `REDIS_URL` | Shared online feature state, rate limits, drift window and metrics for several workers; falls back to memory (one worker) | `redis://localhost:6379/0` |
| `FEATURE_STORE` | `auto` (Redis when reachable) · `memory` · `redis` | `auto` |
| `WEB_CONCURRENCY` / `API_WORKERS` | API worker processes (Docker) | `2` |
| `THREADPOOL_SIZE` / `DB_POOL_SIZE` | Handler threads per worker / PostgreSQL connections per worker (+ same overflow) | `8` / `20` |
| `LLM_PROVIDER` | `auto` (prefers Gemini when configured) · `gemini` · `anthropic` · `none` | `auto` |
| `GEMINI_API_KEY` | Enables Gemini chat, case summaries, and SOP answers | `<your-ai-studio-key>` |
| `GEMINI_MODEL` | Gemini model id | `gemini-3.8-flash` |
| `ANTHROPIC_API_KEY` | Optional alternative provider | `<your-key>` |
| `LLM_MODEL` / `LLM_EFFORT` | Anthropic model and effort level | `claude-opus-5-5` / `low` |
| `LLM_TIMEOUT_SECONDS` | Per-call timeout before template fallback | `30` |
| `JWT_SECRET` | Signs access tokens; **change in production** | `<random-32-bytes>` |
| `DEMO_PASSWORD` | Password for demo users `customer` / `analyst` (built into the web app, so treat it as public) | `<choose-one>` (default `demo123`) |
| `ADMIN_PASSWORD` | Admin login (policy / model changes). Never sent to the browser; typed on the Admin page. Empty: admin uses `DEMO_PASSWORD` only when `ENVIRONMENT=development`, otherwise admin login is off | `<random-string>` |
| `ENVIRONMENT` | `development` or `production` (production disables the demo password for admin) | `development` |
| `AUTH_REQUIRED` | Disable only for local experiments | `true` |
| `CORS_ORIGINS` | Allowed web origins (comma-separated; `*.vercel.app` also allowed) | `http://localhost:3000` |
| `RATE_LIMIT_PER_MINUTE` | Per-IP token bucket; `0` disables | `1200` |
| `ACTIVE_MODEL` | Pin a registry version; empty = `models/registry/ACTIVE` | `lgbm-20261001-061952` |
| `SEED_ON_BOOT` / `AUTO_BOOTSTRAP` | Seed demo alerts / train if no model exists | `true` / `true` |
| `LATENCY_BUDGET_MS` | Decisions slower than this are flagged `degraded` | `150` |
| `GRAPH_REFRESH_SECONDS` | Background graph-snapshot interval | `600` |

Frontend (`frontend/.env.local`): `NEXT_PUBLIC_API_URL` (backend URL), `NEXT_PUBLIC_DEMO_PASSWORD` (must match `DEMO_PASSWORD`).

To enable Gemini, create an API key in Google AI Studio and add `GEMINI_API_KEY=...` to `backend/.env` (or the server's `.env` for Docker). `LLM_PROVIDER=auto` selects Gemini when that key is present; alternatively set `LLM_PROVIDER=gemini`. Never put this key in a `NEXT_PUBLIC_*` variable or the frontend. Requests use Gemini's stateless Interactions API (`store=false`); only synthetic demo data should be used, and free-tier model availability/quotas can change.

## 8. Run & build commands

| Task | Command |
|---|---|
| Generate data + train + evaluate | `cd backend && python -m pipelines.run_all` (`--fast` small set, `--skip-data` retrain only) |
| Run API | `cd backend && uvicorn app.main:app --port 8000` |
| Run web (dev) | `cd frontend && npm run dev` |
| Build web | `cd frontend && npm run build && npm start` |
| Everything in containers | `docker compose up --build` |
| Load test | `cd backend && python tests/load/bench.py --users 10 --seconds 20` (results: [docs/reports/load_test.md](docs/reports/load_test.md)) |
| Bank-style load test | `python tests/load/bank_load.py --stages 50,100,200,400,800 --stage-seconds 60 --procs 3` · soak: `--soak 300 --users 100` (set `RATE_LIMIT_PER_MINUTE` high first) |
| Chaos / graph under load | `python tests/load/chaos.py --kill-cmd "..."` · `python tests/load/graph_under_load.py` |
| Evidence pack | `cd backend && python -m pipelines.evaluation` (ablation, cost, shift, adversarial, leakage, hard data, fairness; ~10 min) |
| Robustness / graph benchmark | `python -m pipelines.robustness` · `python -m pipelines.graph_benchmark` |
| With monitoring | `docker compose --profile monitoring up --build` → Grafana http://localhost:3001 |

## 9. Live deployment URL

- **Web:** https://165-99-219-251.sslip.io · **API docs:** https://165-99-219-251.sslip.io/docs · **Health:** https://165-99-219-251.sslip.io/health/ready
- Hosted on a single VPS with Docker Compose: Caddy (automatic HTTPS) → Next.js web + FastAPI API → PostgreSQL + Redis. Step-by-step guide: [docs/DEPLOY_VPS.md](docs/DEPLOY_VPS.md); one-command update: `deploy/deploy.sh`.
- The Admin page is read-only for visitors. Changing the live policy or model needs `ADMIN_PASSWORD`, which is set on the server and never built into the website.

## 10. Testing instructions

```bash
cd backend && python -m pytest          # 49 tests, ~1 min (trains a small model in a temp dir)
cd frontend && npm run typecheck && npm run lint && npm run build
cd frontend && npx playwright install chromium && npm run test:e2e   # 12 browser tests; starts API + web itself
```
The browser tests (Playwright, also run in CI) drive the real stack: the family transfer is allowed and sent, the account takeover is held and cancelled, the analyst's start-here case opens, the impact page shows its estimates, admin stays locked without its password, an axe audit finds no WCAG 2.1 AA violations on five pages, and the customer page fits a phone screen.

The suite covers: expression sandbox safety, policy tiers/overrides/hot-reload, point-in-time features, reason-code truthfulness, Bangla rendering, RAG retrieval, LLM grounding rejection, circuit breaker, rules-only degraded mode, auth/roles, validation, idempotency, HOLD/release flow, scam-averted counting, batch CSV, live policy editing, database migrations (schema equals the models; pre-Alembic databases adopted), Redis-shared online state (two workers compute identical features; seeding keeps live history), shared rate limits, impact estimate ranges, **golden scenarios** (normal → ALLOW; prize scam, refund scam, account takeover, structuring → WARN/HOLD) and a **model quality gate** (ML must beat rules by ≥0.3 PR-AUC, FPR < 2%, every scenario family caught).

**Manual demo script** (5 min):
1. **Customer app** → pick *Sadia (remittance receiver)* → **'You won a prize' scam** → Send → Bangla warning → Cancel.
2. **Account takeover at night** → Send → HOLD with `R_ATO_COMBO`.
3. **Analyst console** → open the top alert → *Generate case summary* → inspect the mule-ring graph → mark Fraud.
4. **Admin** → edit `warn_t` in the policy → Save → re-score the same transfer: the behaviour changes live, with no redeploy.
5. **Impact** → lift table, per-scenario recall, fairness audit.

## 11. Other configuration

| File | What it controls |
|---|---|
| `backend/config/policy.yaml` | Decision tiers, thresholds (`model` = learned from validation), segment overrides; hot-reloaded |
| `backend/config/rules.yaml` | Deterministic guardrail rules (expressions over features) |
| `backend/config/detectors.yaml` | Detector plug-ins and order |
| `backend/config/flags.yaml` | Feature flags exposed to the UI |
| `backend/app/i18n/messages.yaml` | Bangla/English customer texts for every reason code |
| `backend/knowledge/sop/*.md` | Synthetic SOPs used by the copilot (RAG) |
| `backend/models/registry/` | Versioned models (`ACTIVE` marks the served one) |

Demo users: `customer` and `analyst` with `DEMO_PASSWORD`; the web app signs in as them automatically (demo mode). `admin` uses `ADMIN_PASSWORD` and is never signed in automatically: the Admin page is read-only until you enter it.

## 12. Results (held-out test window, synthetic data, deterministic seed-42 model from `pipelines.run_all`)

| Model (same 10-day test set, 22,125 tx) | PR-AUC | Recall @ 1% FPR |
|---|---|---|
| Rules only | 0.167 | 16.0% |
| Logistic regression | 0.819 | 79.3% |
| LightGBM without graph/anomaly features | 0.951 | 93.5% |
| **LightGBM + graph + anomaly (Shurokkha)** | **0.992** | **99.1%** |

Full system through the real policy: **precision 92.4%, recall 96.2%, false-positive rate 0.21%** (≈5 legitimate customers warned per day in this simulation), HOLD precision 98.4%, **93.4% of victim loss value flagged** before completion. Per scenario: account takeover 100%, prize scam 83%, refund scam 100%, mule forward/cash-out 100%, structuring 100%, social engineering 87%.

Measured in Docker on one 4-core laptop ([docs/reports/load_test.md](docs/reports/load_test.md)):
- **Scaling:** 52 → 93 → 169 req/s with 1 → 2 → 4 API workers (0 errors).
- **Bank-style load:** realistic MFS traffic mix, each transfer scored then confirmed and persisted, ramped to **800 concurrent users**. Peak 68 transfers/s (136 req/s), 0 errors up to 200 users, < 0.2% client timeouts at 400–800 users.
- **Soak:** 5 minutes at 100 users, **69 transfers/s with 0 errors** and flat memory.
- **Chaos:** killing a worker mid-load lost or duplicated **0** of 2,177 transfers.
- **Limit:** the laptop CPU is the ceiling, shared by the load generator and the whole stack. The capacity model estimates 60–80 transfers/s per server core.

### Robustness: beyond the easy test ([docs/reports/robustness.md](docs/reports/robustness.md))
Synthetic fraud is easier than real fraud, so we also test what happens when the model meets something new (`python -m pipelines.robustness`):

| Test (ML model alone, 1% FPR operating point) | Result |
|---|---|
| **New fraud pattern**: retrain without one family, test on it | prize scam 87% · ATO 96% · refund 65% · social engineering 97% caught, though never seen in training. Weak spots: new mule networks 43%, new structuring 6%; the full system's rules lift structuring to 53% and ATO to 100% ([evaluation §3](docs/reports/evaluation.md)) |
| **Brand-new mule ring** (graph features unavailable) | recall 100% → **97%**, PR-AUC 0.995 → 0.972: live behaviour features carry most of the signal |
| **Calibration** of the displayed probability | ECE 0.0026. Mid-range scores are *conservative*: transfers scored 0.25–0.50 were fraud 84% of the time, which is why a "38%" transfer is correctly held |
| **Harder data** (overlapping behaviour, full retrain) | PR-AUC 0.959, recall @ 1% FPR 93.8%; full system precision 85.7%, recall 91.9%, FPR 0.37% |
| **Adversarial drift** (smaller amounts, slower mules, old phones) | recall 96.9% → 86.5%; after retraining on the attack 98.8% (round 1) and 98.3% (round 2, strong attack) |


> **Honest caveat:** these are results on our own synthetic data, whose patterns we designed. They show the pipeline works and that graph features add real lift. Real-world performance must be established with governed upay data (shadow mode first; see the model card).

## 13. Responsible AI

- **Privacy:** synthetic data only; the LLM receives pseudonymous wallet ids, never names or phones.
- **Explainability:** every flagged decision carries verified reason codes; analysts see SHAP drivers and feature values.
- **Fairness:** [reports/fairness.md](backend/reports/fairness.md) (generated) compares FPR across division, age band, KYC level, persona and tenure. Current finding: shopkeepers (0.84%) and new accounts (<90 d, 0.54%) see higher FPR. Mitigation levers are segment overrides and merchant-account onboarding.
- **Human oversight:** no permanent automated blocks; HOLD requires an analyst; overrides are audit-logged.
- **Security:** sandboxed policy expressions, input validation, JWT roles, rate limiting, prompt-injection isolation (`<untrusted_data>`), numeric grounding check on LLM output, secrets only via env vars.

## 14. Scaling & limitations

- **Several API workers.** With `REDIS_URL` set, the online state is shared in Redis (`app/features/store.py`): per-wallet feature state, live graph edges and rate-limit counters. The warm state from the training replay is copied into Redis once per dataset, so every worker computes exactly the same features (tested) and live history survives an API restart. Docker Compose runs 2 workers (`WEB_CONCURRENCY`); without Redis the API falls back to one in-memory worker. Next step at real scale: a feature store (Feast) fed by Kafka.
- **Database migrations** with Alembic (`backend/migrations`). The API upgrades the schema on startup; databases created before migrations existed are adopted without data loss. A test fails if a model changes without a migration.
- Graph snapshots are recomputed in batch (cold path); production would use incremental graph processing.
- BM25 retrieval can be swapped for multilingual embeddings behind the same `search()` interface.

## 15. Disclosures & team

See [DISCLOSURES.md](DISCLOSURES.md) for external libraries, models and services. Team: `<names and roles>`.
