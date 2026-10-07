# Evaluation evidence pack

Synthetic data, time-based split, test window = last 10 days (22,125 transactions).
Thresholds and calibration are learned on the validation window only. Brackets are bootstrap 95% confidence intervals.
These numbers show method and relative value; production performance must come from shadow mode on real traffic.

## 1. Ablation: what each layer adds

| System | PR-AUC | Recall @ 1% FPR | Fraud flagged | Loss value caught | FP per 10k legit | HOLDs/day | Expected cost/day (৳) | ECE |
|---|---|---|---|---|---|---|---|---|
| Rules only | 0.167 (13.9%–19.9%) | 15.4% | 15.3% (12.1%–18.3%) | 54.1% (46.1%–61.2%) | 13.9 (9.7–18.6) | 4.4 | 40,999 | 0.0231 |
| LightGBM only | 0.954 (94.2%–96.4%) | 94.8% | 87.8% (84.9%–90.3%) | 80.6% (73.9%–86.1%) | 33.9 (27.8–42.2) | 50.2 | 17,653 | 0.0057 |
| + Isolation Forest | 0.953 (94.1%–96.3%) | 95.2% | 89.0% (86.3%–91.3%) | 83.5% (77.0%–89.2%) | 34.4 (28.8–42.8) | 48.9 | 16,813 | 0.0056 |
| + Graph features | 0.995 (99.2%–99.7%) | 99.5% | 96.9% (95.6%–98.2%) | 94.7% (91.0%–97.7%) | 6.5 (3.7–9.7) | 55.7 | 7,177 | 0.0026 |
| **Full Shurokkha** | 0.990 (98.6%–99.4%) | 99.5% | 96.9% (95.6%–98.2%) | 94.7% (91.0%–97.7%) | 20.4 (15.3–26.0) | 55.8 | 7,185 | 0.0026 |

**Marginal contribution** (each row compared with the row above):

| Layer added | Fraud flagged | Mule-ring recall | Expected cost/day |
|---|---|---|---|
| LightGBM only | +72.5% | +92.4% | -23,346 ৳ |
| + Isolation Forest | +1.2% | -0.3% | -840 ৳ |
| + Graph features | +7.9% | +3.1% | -9,636 ৳ |
| Full Shurokkha | +0.0% | +0.0% | +8 ৳ |

Full Shurokkha's PR-AUC uses the fused score max(model, rules); its decisions come from the real policy engine
(rules, model, graph, anomaly and agent cash-out detectors).

## 2. Cost function and cost-optimal thresholds

`Cost = missed victim loss + (1 − warn_heeded) × warned victim loss + missed other fraud × ৳200 + false WARN × ৳20 + false HOLD × ৳150 + analyst minutes × ৳8`

Assumptions: warn heeded 60%, 6 analyst minutes per HOLD, 1 per WARN alert.

| Thresholds | warn_t | hold_t | Fraud flagged | FP per 10k | HOLDs/day | Expected cost/day (৳) |
|---|---|---|---|---|---|---|
| Learned (1% FPR / 90% precision) | 0.050 | 0.100 | 96.9% | 20.4 | 55.8 | 7,185 |
| Cost-optimal (grid search on validation) | 0.020 | 0.449 | 97.1% | 26.9 | 53.3 | 8,501 |

## 3. New fraud families (leave one family out of training)

| Family never seen in training | Test cases | Model alone | Full system | Full-system FP per 10k |
|---|---|---|---|---|
| account takeover | 46 | 71.7% | 100.0% | 20.0 |
| prize scam | 93 | 47.3% | 47.3% | 16.7 |
| refund scam | 34 | 47.1% | 61.8% | 21.8 |
| mule network | 355 | 22.8% | 31.3% | 20.9 |
| structuring | 17 | 0.0% | 52.9% | 19.5 |
| social engineering | 38 | 84.2% | 84.2% | 19.0 |

The gap between the two columns is what the rules, graph, anomaly and agent cash-out layers add for fraud the model has never seen.

## 4. Distribution shift

| Setting | Full-system recall | Model-only recall | Loss value caught | FP per 10k | ECE |
|---|---|---|---|---|---|
| Test window as generated | 96.9% | 96.9% | 94.7% | 20.4 | 0.0026 |
| Earlier half of test window | 99.1% | 99.1% | 97.7% | 22.3 | 0.0016 |
| Later half of test window | 94.3% | 94.3% | 90.9% | 18.5 | 0.0036 |
| Covariate shift (30% new users, 10% new phones, Eid amounts ×3) | 96.9% | 96.9% | 94.7% | 87.3 | 0.0016 |
| Adversarial drift (smaller amounts, slower mules, old devices) | 86.5% | 85.6% | 82.4% | 20.4 | 0.0085 |

Shifts are applied to the test features (a stress test of the decision layer), not by regenerating history.

## 5. Adversarial rounds (attacker adapts, defender retrains)

| Round | Attack | Recall under attack, before retrain | After retrain on the attack | FP per 10k after | Clean-data recall after |
|---|---|---|---|---|---|
| 1 | moderate | 86.5% | 98.8% | 20.0 | 95.4% |
| 2 | strong | 87.6% | 98.3% | 22.3 | 94.0% |

## 6. Leakage audit

A feature that separates fraud from legitimate traffic on its own would be a generator 'tell'.

| Feature | ROC-AUC alone |
|---|---|
| anomaly_score | 0.851 |
| s_hist_count | 0.816 |
| s_mins_since_inflow | 0.811 |
| s_g_comm_cashout | 0.758 |
| s_inflow_ratio_24h | 0.755 |
| s_g_comm_fanin | 0.754 |
| amount | 0.732 |
| amount_log | 0.732 |

| Feature | Share of model gain |
|---|---|
| r_g_fwd | 15.7% |
| s_mins_since_inflow | 12.2% |
| r_tenure_days | 8.5% |
| s_hist_count | 7.4% |
| s_new_sender_inflow_1h | 5.6% |
| s_g_fwd | 5.1% |
| type_code | 4.8% |
| anomaly_score | 4.3% |

Flagged (single-feature AUC ≥ 0.95 or gain share ≥ 40%): none.

## 7. Harder synthetic data (overlapping behaviour)

Legitimate users change phones (4×), replace SIMs, transact at night (2.5×) and send large one-off amounts;
fraudsters copy normal amounts, 40% of takeovers use the victim's own phone, half of mules wait 2–12 hours.

| Model (hard data) | PR-AUC | Recall @ 1% FPR |
|---|---|---|
| rules only | 0.091 | 10.0% |
| logistic regression | 0.676 | 67.6% |
| lightgbm no graph no anomaly | 0.850 | 82.0% |
| lightgbm full | 0.959 | 93.8% |

Full system on hard data: precision 85.7%, recall 91.9%, FPR 0.37%, victim-loss value flagged 89.4%.

| Scenario | Flagged (hard data) |
|---|---|
| S1_ato | 100% |
| S2_prize_scam | 72% |
| S3_refund_bait | 89% |
| S3_refund_scam | 100% |
| S4_mule_cashout | 100% |
| S4_mule_forward | 99% |
| S6_social_engineering | 64% |

## 8. Fairness by segment

Constraint: equalise false-positive burden **without lowering recall for high-risk groups** (elderly, new users).

**division**

| Group | FPR | FNR | Warning rate | ECE | Transactions |
|---|---|---|---|---|---|
| Barishal | 0.00% | 25.0% | 0.00% | 0.0030 | 1,382 |
| Chattogram | 0.27% | 1.4% | 0.30% | 0.0037 | 3,973 |
| Dhaka | 0.23% | 4.5% | 0.30% | 0.0031 | 7,601 |
| Khulna | 0.29% | 14.3% | 0.29% | 0.0038 | 1,717 |
| Mymensingh | 0.06% | 0.0% | 0.06% | 0.0018 | 1,670 |
| Rajshahi | 0.31% | 5.0% | 0.31% | 0.0011 | 2,277 |
| Rangpur | 0.06% | 0.0% | 0.06% | 0.0007 | 1,662 |
| Sylhet | 0.21% | 11.1% | 0.14% | 0.0021 | 1,440 |

**age_band**

| Group | FPR | FNR | Warning rate | ECE | Transactions |
|---|---|---|---|---|---|
| 18-24 | 0.10% | 1.8% | 0.14% | 0.0030 | 7,639 |
| 25-34 | 0.27% | 1.5% | 0.23% | 0.0013 | 5,608 |
| 35-44 | 0.30% | 4.2% | 0.34% | 0.0023 | 4,657 |
| 45-54 | 0.20% | 14.3% | 0.30% | 0.0030 | 3,004 |
| 55-64 | 0.00% | 6.7% | 0.00% | 0.0070 | 405 |
| 65+ | 0.50% | 27.3% | 0.49% | 0.0134 | 409 |

**kyc_level**

| Group | FPR | FNR | Warning rate | ECE | Transactions |
|---|---|---|---|---|---|
| 1.0 | 0.16% | 4.5% | 0.20% | 0.0043 | 7,986 |
| 2.0 | 0.22% | 1.5% | 0.23% | 0.0018 | 9,893 |
| 3.0 | 0.29% | 3.6% | 0.31% | 0.0010 | 3,843 |

**persona**

| Group | FPR | FNR | Warning rate | ECE | Transactions |
|---|---|---|---|---|---|
| fcommerce_seller | 0.39% | 9.1% | 0.39% | 0.0028 | 1,555 |
| freelancer | 0.19% | 0.8% | 0.11% | 0.0012 | 2,776 |
| garments_worker | 0.10% | 5.6% | 0.13% | 0.0034 | 3,906 |
| professional | 0.04% | 2.7% | 0.08% | 0.0012 | 4,754 |
| remittance_receiver | 0.27% | 18.6% | 0.26% | 0.0118 | 1,150 |
| shopkeeper | 0.73% | 5.0% | 0.80% | 0.0014 | 2,891 |
| student | 0.07% | 0.8% | 0.15% | 0.0031 | 4,690 |

**tenure**

| Group | FPR | FNR | Warning rate | ECE | Transactions |
|---|---|---|---|---|---|
| <90d | 0.29% | 1.1% | 0.27% | 0.0022 | 2,982 |
| >=90d | 0.19% | 4.0% | 0.22% | 0.0027 | 19,143 |

**Merchant-aware fix** (registered shops / online sellers). *Before* = the same system with merchant awareness switched off
(graph fan-in, agent cash-out detector and the policy override); *after* = as deployed. HOLD rules are unchanged:

| Measure | Before | After |
|---|---|---|
| FPR, merchants as senders (%) | 2.877 | 0.612 |
| FPR, payments to merchants (%) | 0.128 | 0.1 |
| FPR, all legitimate (%) | 0.678 | 0.204 |
| Fraud recall | 0.969 | 0.969 |
| Fraud recall, age 65+ | 0.727 | 0.727 |

## 9. Calibration

ECE before calibration 0.0042 (Brier 0.0032); after Platt scaling 0.0026 (Brier 0.0021).

| Predicted | n | Mean predicted | Observed fraud rate |
|---|---|---|---|
| 0–0.001 | 21308 | 0.0000 | 0.0001 |
| 0.001–0.01 | 196 | 0.0028 | 0.0561 |
| 0.01–0.05 | 42 | 0.0202 | 0.1190 |
| 0.05–0.1 | 22 | 0.0678 | 0.6364 |
| 0.1–0.25 | 14 | 0.1851 | 0.7857 |
| 0.25–0.5 | 19 | 0.3954 | 0.8421 |
| 0.5–0.75 | 14 | 0.6247 | 1.0000 |
| 0.75–1 | 510 | 0.9879 | 1.0000 |
