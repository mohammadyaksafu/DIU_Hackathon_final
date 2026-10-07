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
| PR-AUC / ROC-AUC | 0.992 / 0.9996 (bootstrap 95% CI for PR-AUC 0.986–0.994, fused system score) |
| Recall @ 1% FPR | 99.1% |
| System precision / recall (via policy) | 92.4% / 96.2% |
| False-positive rate | 0.21% |
| HOLD precision | 98.4% |
| Victim loss value flagged | 93.4% (evaluation-pack bootstrap 95% CI for this metric: 91.0–97.7%) |

Lift: rules-only PR-AUC 0.167 → logistic regression 0.819 → LightGBM without graph 0.951 → full 0.992. Full ablation with cost, FP burden, HOLDs/day, ECE and confidence intervals: [reports/evaluation.md](reports/evaluation.md).

## Robustness (`python -m pipelines.robustness`, report: docs/reports/robustness.md)
| Test (ML model alone, 1% FPR) | Result |
|---|---|
| Fraud family never seen in training (leave-one-scenario-out) | prize scam 87% · ATO 96% · refund 65% · social engineering 97% · mule networks 43% · structuring 6% |
| Brand-new mule ring (graph features unavailable) | recall 100% → 97%, PR-AUC 0.995 → 0.972 |
| Calibration | ECE 0.0026 (0.0042 before Platt), Brier 0.0021; mid-range scores are conservative (0.25–0.50 → 84% observed fraud) |
| Harder overlapping data (`generate_data hard=True`, full retrain) | PR-AUC 0.959, recall @ 1% FPR 93.8%; system precision 85.7%, recall 91.9% |
| Adversarial drift / retrain rounds | 96.9% → 86.5% under attack; 98.8% and 98.3% after retraining on rounds 1 and 2 |
| Leakage audit | no single feature reaches ROC-AUC 0.95 alone; top gain share 15.7% (`r_g_fwd`) |

New mule networks and new structuring patterns are the model's weak spots; deterministic rules (near-limit cash-outs, fan-in) and the graph detector cover them in the full system, and new patterns should be added to the generator and retrained as they appear.

## Fairness (test window, FPR on legitimate transactions)
Highest: shopkeepers 0.77%, age 65+ 0.50%, online sellers 0.39%, accounts <90 days 0.36%. Lowest: professionals 0.06%. **Merchant-aware fix (done):** registered shop/seller profiles down-weight fan-in evidence, the agent cash-out detector discounts routine takings, and routine business payments get fewer WARNs while transfers to new people keep full protection. Merchants-as-senders FPR fell from 2.9% to 0.6% and overall FPR from 0.68% to 0.20% with **no loss of fraud recall** (96.9% before and after; age 65+ unchanged). Full segment table with FNR, warning rate and calibration: [reports/evaluation.md §8](reports/evaluation.md).

**Customers aged 65+** (0.50% FPR, 3.3× the lowest band) are a core protected persona, so the fix must not weaken their protection. Plan: (1) keep thresholds unchanged for this group; (2) make the friction gentler: route their WARNs to a call-back from a trained agent in Bangla rather than a blocking screen; (3) investigate the driving features (new device and new recipient are common when family members help elderly users) and add a "trusted helper device" signal; (4) track this group's FPR and cancel-after-warning rate monthly, with a target ratio below 2×.

## Limitations & risks
- Synthetic patterns are easier than real fraud; expect lower real-world performance and drift as fraudsters adapt.
- Online features are shared through Redis (several API workers, survives restarts) but are not yet a full feature store with point-in-time backfills (Feast).
- Fraud recall for the 65+ band is lower than average (FNR 27% on only 11 test frauds): too few cases to conclude, but it is tracked each retrain and must not be traded for fewer warnings.
- Calibration is fitted on a small validation window.
- Graph snapshots refresh every 10 minutes, so brand-new rings are first caught by live fan-in features and rules.

## Path to validation with upay data
1. Offline back-test on governed, anonymised historical data. 2. Shadow mode: score live traffic, no customer impact, compare with existing controls. 3. Controlled pilot with WARN only for a small segment and measure cancel rate, complaints and losses. 4. Enable HOLD with analyst SLAs. 5. Monthly fairness and drift review.
