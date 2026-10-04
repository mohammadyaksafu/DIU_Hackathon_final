# Model card: Shurokkha risk model (`lgbm-20261001-061952`)

## Intended use
Real-time risk scoring of MFS transfers to (a) warn customers before likely scam payments, (b) hold likely account-takeover / mule transfers for human review, (c) rank analyst alerts. **Not** for credit decisions, account closure or any autonomous irreversible action.

## Model
- LightGBM binary classifier (31 leaves, early-stopped on validation PR-AUC; grid over 15/31/63 leaves), Platt-calibrated on validation.
- 46 features: amount behaviour, velocity, recipient novelty and fan-in, device age, SIM-swap/PIN-reset recency, location change, inflow-to-outflow timing, structuring signals, 9 transaction-graph features (community fan-in, cash-out ratio, forwarding, PageRank), 4 derived features, and the Isolation-Forest anomaly percentile.
- Companion detectors: deterministic rules, Isolation Forest (150 trees), graph risk score. A YAML policy combines them.
- Explanations: exact TreeSHAP (`pred_contrib`) mapped to reason codes, each emitted only if its factual condition holds.

## Data
Synthetic only (see DATA_ASSUMPTIONS.md): 183,479 transactions, 2,170 fraud (1.18%). Split by time: 138,892 train / 22,461 validation / 22,126 test.

## Thresholds (learned on validation)
`warn_t` = max(0.05, 99th percentile of legitimate scores) = 0.05 · `hold_t` = lowest score with ≥90% precision (floor warn_t + 0.05) = 0.10. New accounts (<30 d) use `warn_t × 0.8`.

Both thresholds sit on their safety floors. This is expected when legitimate and fraud scores separate cleanly: 99% of legitimate transfers score below 0.05, so the floor (not the percentile) sets WARN. On harder real data the learned values will rise above the floors; the floors stop thresholds from collapsing towards zero.

## Performance (test window)
| Metric | Value |
|---|---|
| PR-AUC / ROC-AUC | 0.995 / 0.9998 |
| Recall @ 1% FPR | 99.5% |
| System precision / recall (via policy) | 91.7% / 96.2% |
| False-positive rate | 0.24% |
| HOLD precision | 98.2% |
| Victim loss value flagged | 94.3% |

Lift: rules-only PR-AUC 0.166 → logistic regression 0.822 → LightGBM without graph 0.952 → full 0.995. Graph and anomaly features cut missed fraud at 1% FPR from 6.2% to 0.5%.

## Robustness (`python -m pipelines.robustness`, report: docs/reports/robustness.md)
| Test (ML model alone, 1% FPR) | Result |
|---|---|
| Fraud family never seen in training (leave-one-scenario-out) | prize scam 85% · ATO 87% · refund 76% · social engineering 97% · mule networks 47% · structuring 0% |
| Brand-new mule ring (graph features unavailable) | recall 99% → 94%, PR-AUC 0.995 → 0.958 |
| Calibration | ECE 0.0024, Brier 0.0019; mid-range scores are conservative (0.25–0.50 → 96% observed fraud) |

New mule networks and new structuring patterns are the model's weak spots; deterministic rules (near-limit cash-outs, fan-in) and the graph detector cover them in the full system, and new patterns should be added to the generator and retrained as they appear.

## Fairness (test window, FPR on legitimate transactions)
Highest: shopkeepers 0.84%, accounts <90 days 0.54%, age 65+ 0.50%. Lowest: professionals 0.04%. Ratios are large because base FPRs are tiny, but they show a real pattern: high-volume small businesses and new users get more friction. Mitigations: merchant-account onboarding (separate thresholds via `segment_overrides`), seller-specific features, and monitoring this report each retrain.

**Customers aged 65+** (0.50% FPR, 3.3× the lowest band) are a core protected persona, so the fix must not weaken their protection. Plan: (1) keep thresholds unchanged for this group; (2) make the friction gentler: route their WARNs to a call-back from a trained agent in Bangla rather than a blocking screen; (3) investigate the driving features (new device and new recipient are common when family members help elderly users) and add a "trusted helper device" signal; (4) track this group's FPR and cancel-after-warning rate monthly, with a target ratio below 2×.

## Limitations & risks
- Synthetic patterns are easier than real fraud; expect lower real-world performance and drift as fraudsters adapt.
- In-process online features limit the prototype to one API worker.
- Calibration is fitted on a small validation window.
- Graph snapshots refresh every 10 minutes, so brand-new rings are first caught by live fan-in features and rules.

## Path to validation with upay data
1. Offline back-test on governed, anonymised historical data. 2. Shadow mode: score live traffic, no customer impact, compare with existing controls. 3. Controlled pilot with WARN only for a small segment and measure cancel rate, complaints and losses. 4. Enable HOLD with analyst SLAs. 5. Monthly fairness and drift review.
