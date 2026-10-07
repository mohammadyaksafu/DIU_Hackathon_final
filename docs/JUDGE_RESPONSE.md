# You asked, we did

Phase 1 score ≈ 83/100. The judges' common message: *"It works on synthetic data in one process. Prove it works on realistic data, at scale, against baselines, with measured human behaviour."* Every row below links to the code or report that answers the comment. Labels: **Measured** (run on this system), **Simulated** (synthetic data), **Estimate** (stated assumption), **Built, awaiting data** (tool ready, no participants yet).

## Problem relevance (18.33 / 20)
| Comment | What we did | Evidence |
|---|---|---|
| Use governed MFS statistics | Cited figures only, each with its source; unattributed numbers marked as such | [EVIDENCE.md §1–2](EVIDENCE.md) (Cited) |
| Quantify false positives vs losses | One explicit cost function used for thresholds, ablation and ROI | [evaluation.md §2](reports/evaluation.md) (Estimate inputs, Simulated result) |
| Prove pre-transaction is the best control point | Control-point table: what is recoverable and what each control costs | [EVIDENCE.md §4](EVIDENCE.md) |
| Cash-out scams at agent points not covered | **New agent cash-out detector**: fresh inflow drained at an agent + agent serving many first-time customers; new demo scenario; WARN, or HOLD with the mule graph | `app/detectors/agent_cashout.py`, scenario "Mule cash-out at an agent" |
| Prioritise by loss and segment | Fraud type × frequency × loss × reversibility × segment matrix | [EVIDENCE.md §3](EVIDENCE.md) |

## AI/ML depth (16.33 / 20)
| Comment | What we did | Evidence |
|---|---|---|
| Full system vs LightGBM-only and rules-only | Ablation: rules → LightGBM → + Isolation Forest → + graph → full system, with PR-AUC, recall @ 1% FPR, loss caught, FP per 10k, HOLDs/day, expected cost, ECE and **bootstrap 95% CIs**, plus marginal contribution | [evaluation.md §1](reports/evaluation.md) (Simulated) |
| Unseen fraud (structuring, new mule rings) | Leave-one-family-out for the model **and** the full system: structuring 0% → 53%, ATO 72% → 100%, refund 47% → 62% thanks to rules/graph/agent layers; unseen-ring test 100% → 97% | [evaluation.md §3](reports/evaluation.md), [robustness.md](reports/robustness.md) |
| Distribution shift | Later time window (99.1% → 94.3%), covariate shift (recall holds at 96.9%, FP burden rises to 87/10k), adversarial drift (96.9% → 86.5%) with calibration under each | [evaluation.md §4](reports/evaluation.md) |
| Cost-sensitive metrics, calibration, FP burden | Expected cost per day, FP per 10k, HOLDs/day per system; ECE 0.0042 → 0.0026 with Platt; reliability table; cost-optimal thresholds compared with learned ones (learned thresholds were already cheaper on test) | [evaluation.md §1, §2, §9](reports/evaluation.md) |
| "Trained on easy fake clues" | Leakage audit (no single feature reaches AUC 0.95); **harder generator** with overlapping behaviour retrained end to end (PR-AUC 0.959, system recall 91.9%); **adversarial rounds** (attack 86.5% → retrain 98.8% → strong attack 87.6% → retrain 98.3%); attack values copied from legitimate traffic so the defender cannot learn attack artefacts | [evaluation.md §5–7](reports/evaluation.md), `generate_data.py hard=True` |
| Drift monitoring | PSI of live vs training features, shared across workers; demonstrated: load-test traffic was flagged as drift | `GET /metrics/drift`, Impact page, [load_test.md](reports/load_test.md) (Measured) |
| PaySim / Elliptic sanity check | **Not done** (needs dataset downloads under Kaggle terms); listed as the next external check | — |

## Business / customer impact (17 / 20)
| Comment | What we did | Evidence |
|---|---|---|
| Cancel rate is assumed | **WARN user study built into the app** (3 randomised arms, consent, anonymous codes, Wilson CIs, complaint-intent question); results feed the Impact page | `/study`, [USER_STUDY.md](USER_STUDY.md) (**Built, awaiting data**) |
| Separate simulated from validated | Impact page has a "Measured vs simulated" panel; every report labels its numbers | Impact page, this table |
| ROI with sensitivity | Net benefit/day, ROI multiple, break-even cancel rate and a tornado over cancel rate, fraud base rate and false-alarm cost | Impact page, `app/api/v1/insights.py` (Simulated) |
| Analyst workload | Hours/day with and without the copilot (Estimate); trial protocol using the recorded `opened_at` / `decided_at` | Impact page, [USER_STUDY.md](USER_STUDY.md) |
| Re-express the 94% claim | Loss value caught with CI, and under shift and LOFO | [evaluation.md](reports/evaluation.md) |

## Prototype quality (12.33 / 15)
| Comment | What we did | Evidence |
|---|---|---|
| Runs on one computer / one process | Several Uvicorn workers sharing feature state, graph edges, rate limits, drift window and metrics in **Redis**; PostgreSQL with **Alembic** migrations | [ARCHITECTURE.md](ARCHITECTURE.md#multi-worker-operation) |
| Idempotency, retries | Key claimed across workers before scoring; retries replay the first decision | `app/services/scoring.py`, test `test_idempotency` |
| HOLD/release consistency | PENDING → SENT/CANCELLED by a conditional update (optimistic lock); test: cancel after release cannot double-complete | `_transition()`, `test_cancel_after_release_cannot_double_complete` |
| Model-version consistency | Each request pins one model + detector set; workers follow activations within 5 s | `AppState.sync_model()` |
| Chaos | Killed a worker under load: **0 lost, 0 duplicated** of 2,177 transfers; worker respawned | [load_test.md](reports/load_test.md) (Measured) |
| Shadow mode before blocking | `mode: shadow | warn | enforce` in the policy; alerts always record the policy decision | `config/policy.yaml` |
| Tests + CI | Unit, API, migration, Redis multi-worker, concurrency and Playwright + axe browser tests in GitHub Actions | `.github/workflows/ci.yml` |
| Kafka ordering | Per-wallet Redis locks give ordering at this scale; Kafka partitioned by wallet is the documented production path (not deployed) | [INTEGRATION.md](INTEGRATION.md) |

## Innovation (8 / 10)
| Comment | What we did | Evidence |
|---|---|---|
| Incremental value of each component | Marginal-contribution table (graph: +7.9 pp fraud flagged, −৳9,636/day cost) and LOFO rescue by rules/graph | [evaluation.md §1, §3](reports/evaluation.md) |
| Warning pop-ups already exist | On-call signal ("are you being told to send this now?"), 20-second cooling-off before "send anyway", "call someone you trust", Bangla voice warning, verified reasons only when facts and SHAP agree | Customer app |

**Novelty in one sentence:** the first pre-transaction MFS defence we know of that fuses device, SIM, behaviour, agent and mule-graph signals, explains them in verified Bangla, and shows its lift over a standard classifier with confidence intervals.

## Scalability & integration (7.67 / 10)
| Comment | What we did | Evidence |
|---|---|---|
| Load test, p95/p99 | 1 → 2 → 4 workers: 52 → 93 → 169 req/s, 0 errors; server p50/p95/p99 11.6 / 26.0 / 35.8 ms | [load_test.md](reports/load_test.md) (Measured, laptop) |
| Failover and monitoring | Prometheus + provisioned Grafana dashboard (profile `monitoring`); worker failover measured; fail-safe `on_scoring_error` | `deploy/monitoring`, [ARCHITECTURE.md](ARCHITECTURE.md) |
| Graph refresh will slow down | Benchmark: rebuild grows ≈linearly with edges in a fixed 14-day window and runs off the request path; under continuous ingestion (2,285 committed transfers in 40 s) rebuilds took 0.83–1.28 s while scoring continued | [graph_benchmark.md](reports/graph_benchmark.md), [load_test.md](reports/load_test.md) (Measured) |
| Integration contract | OpenAPI, sample payloads, sequence diagram, timeout rule | [INTEGRATION.md](INTEGRATION.md) |

## Responsible AI & security (3.33 / 5)
| Comment | What we did | Evidence |
|---|---|---|
| Appeal / release process | "Not a scam? Appeal" button; appealed cases jump the queue with a 15-minute SLA; `legit` releases the HOLD and becomes a label | Customer app, analyst queue, `POST /transactions/{id}/appeal` |
| Drift monitoring, access control, privacy | PSI drift endpoint; roles + audit; privacy and retention rules | [GOVERNANCE.md](GOVERNANCE.md) |
| Honest shopkeepers flagged | Merchant-aware features: merchants-as-senders FPR 2.9% → 0.6%, all legitimate 0.68% → 0.20%, **fraud recall unchanged** (96.9%, age 65+ unchanged) | [evaluation.md §8](reports/evaluation.md) |
| Fairness and calibration by segment | FPR, FNR, warning rate and ECE per segment, with the constraint not to lower recall for high-risk groups. The merchant threshold override now runs in **shadow** (logged, not applied) until validated on governed data | [evaluation.md §8](reports/evaluation.md), `config/policy.yaml` |
| Adversarial probing, endpoint protection | Threat table | [GOVERNANCE.md](GOVERNANCE.md) |

## What still needs real-world input
- **Participants for the WARN study** (tool ready; 60+ people, ~1 day of sessions).
- **upay data** for shadow-mode validation; the system ships with `mode: shadow` for exactly this.
- Optional external sanity checks on PaySim / Elliptic.
