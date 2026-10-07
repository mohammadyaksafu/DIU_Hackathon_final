# Architecture

## Request lifecycle: `POST /api/v1/score`

1. **Validate** (Pydantic): wallet-id pattern, amount bounds, enum types, memo length. The memo is never interpreted.
2. **Idempotency:** `Idempotency-Key` header or `tx_id` → a stored response is replayed (`idempotent_replay: true`).
3. **Features** (`app/features`): `FeatureEngine.compute()` reads per-wallet state built only from *earlier, committed* events, then merges graph-snapshot features and registry-derived features. The same code produced the training data, so there is no train/serve skew.
4. **Detectors** (`app/detectors`, order from `config/detectors.yaml`):
   - `rules`: YAML expressions, deterministic, regulator-friendly
   - `anomaly`: Isolation Forest compiled to arrays (1.4 ms/row, equal to scikit-learn); writes `anomaly_score` into the features
   - `lgbm`: LightGBM + Platt calibration (reads `anomaly_score`)
   - `graph`: transparent mule-ring score from community fan-in, cash-out ratio, forwarding, live fan-in; merchant-aware (registered shops and sellers with many new payers are down-weighted)
   - `agent_cashout`: fresh inflow drained at an agent + agent serving many first-time customers (agent-side velocity)
   A detector that throws is recorded as `ok=false`; the decision still happens (degraded).
5. **Policy** (`app/policy`): first matching tier in `config/policy.yaml`, then the rollout `mode` (`shadow` shows ALLOW but logs the alert, `warn` turns HOLD into WARN, `enforce`). The request pins one model + detector set, so a hot swap never mixes versions. Variables marked `model` come from thresholds learned on the validation split; segment overrides adjust them. Expressions run in a whitelisted AST evaluator (no attribute access, no builtins).
6. **Explain** (only for WARN/HOLD): TreeSHAP contributions → reason codes, each guarded by a factual condition → Bangla/English text from `i18n/messages.yaml`.
7. **Persist**: scored transaction (PENDING), alert for WARN/HOLD, audit event, idempotency record.
8. **Customer confirm** (`/transactions/{id}/confirm`): one conditional update moves PENDING → SENT/CANCELLED (a cancel and an analyst release can never both win). `sent` commits the transfer into feature and graph state. `cancelled` after WARN/HOLD counts as *scam averted*. A HOLD cannot be sent until an analyst labels it legit, which releases it automatically.

## Paths
| Path | Work | Budget |
|---|---|---|
| Hot | features, detectors, policy | ~2 ms compute, ~5 ms with DB write |
| Warm | LLM case summary (cached by evidence hash) | ≤ 30 s timeout, circuit breaker, template fallback |
| Cold | graph snapshot (Louvain + PageRank over 14 days of edges), retraining | background thread every 10 min / pipeline |

## Degradation ladder
| Failure | Behaviour |
|---|---|
| LLM unavailable / refusal / ungrounded numbers | Template narrative, UI badge "AI unavailable" |
| Model missing or corrupt | Rules + graph only, `degraded: ["model"]`, health = degraded |
| Single detector exception | Signal `ok=false`, policy treats it as 0, decision continues |
| Whole scoring step fails (feature store / model unreachable) | `on_scoring_error` from the policy: WARN (fail-safe, no block) or ALLOW (fail-open); `degraded_reasons: ["scoring_error:…"]` |
| Redis down at boot | In-memory cache, rate limiter and online state in this worker (run one worker) |
| Redis down while serving | Cache and rate limiter fall back to memory |
| Broken policy edit | Rejected (API) or ignored (file); last good policy stays live |
| Over latency budget | Decision returned with `degraded_reasons: ["latency_budget_exceeded"]` |

## Security
JWT (HS256) with roles `customer` / `analyst` / `admin` (admin passes every role check); per-IP rate limit (shared fixed window in Redis, token bucket in memory as fallback); CORS allow-list; request ids in every log line and response header; append-only audit log; secrets via environment only; LLM sees pseudonymous ids and receives untrusted text inside `<untrusted_data>` tags with an instruction to never follow it.

## Prototype → production
| Concern | Prototype | Production path |
|---|---|---|
| Ingestion | REST `/score` | Kafka/Redpanda, partitioned by wallet |
| Online features | `FeatureEngine` on a Redis wallet store shared by all workers (in-memory fallback) | Feast online store fed by Kafka |
| Schema | Alembic migrations, applied on startup | Same, run as a release step before rollout |
| Serving | In-process LightGBM | Same, horizontally scaled pods |
| Graph | NetworkX batch snapshot | Incremental graph (Neo4j / GraphFrames) |
| Storage | SQLite / Postgres | Partitioned Postgres + Parquet lake for training |
| Rollout | Model registry + ACTIVE | Shadow mode → canary → A/B with champion/challenger |

## Multi-worker operation
| State | Where | Why it is safe with N workers |
|---|---|---|
| Per-wallet feature state | Redis (`app/features/store.py`), seeded once per dataset | per-wallet lock around read-modify-write; tested: two workers compute identical features |
| Live graph edges | Redis list, pulled by each worker before refresh/subgraph | append-only |
| Idempotency | Redis lock on the key + DB record | a retry on another worker replays the first decision |
| Rate limits | Redis fixed window | shared counter |
| Drift window | Redis list (last 5,000 transfers) | shared |
| Metrics | each worker publishes a snapshot to Redis; `/metrics` sums them | Prometheus sees the whole API |
| Policy | YAML file, mtime hot-reload | every worker reloads on change |
| Active model | `ACTIVE` file, checked every 5 s | every worker follows an activation |
| Cases, audit, decisions | PostgreSQL, Alembic migrations | transactions + conditional updates |

Monitoring: `docker compose --profile monitoring up` adds Prometheus and a provisioned Grafana dashboard (`deploy/monitoring`).
