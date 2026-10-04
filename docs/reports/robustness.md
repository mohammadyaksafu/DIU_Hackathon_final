# Robustness report

Operating point: 1% legitimate FPR (threshold learned on validation). Same time-based split as the headline evaluation.

## 1. Leave-one-scenario-out (new fraud pattern)

The model is retrained **without** one fraud family, then tested on that family.

| Fraud family | Test cases | Recall when seen in training | Recall when never seen |
|---|---|---|---|
| account takeover | 46 | 100% | 87% |
| prize scam | 93 | 97% | 85% |
| refund scam | 34 | 100% | 76% |
| mule network | 355 | 100% | 47% |
| structuring | 17 | 100% | 0% |
| social engineering | 38 | 97% | 97% |

These figures are for the **ML model alone**. In the deployed system the deterministic rules
(near-limit cash-outs, SIM-swap + PIN-reset combo, etc.) and the graph detector run alongside it, which is
why a family the model has never seen (e.g. structuring) is still caught by policy.


## 2. Unseen mule ring (graph features unavailable)

Graph features of every test fraud case are replaced with typical legitimate values, as if the ring were brand new.

| Setting | Recall @ 1% FPR | PR-AUC |
|---|---|---|
| With graph features | 99% | 0.995 |
| Unseen ring (no graph signal) | 94% | 0.958 |

| Fraud family | Recall, unseen ring |
|---|---|
| account takeover | 100% |
| prize scam | 91% |
| refund scam | 88% |
| mule network | 95% |
| structuring | 100% |
| social engineering | 90% |

## 3. Calibration of the displayed fraud probability

Expected calibration error **0.0024**, Brier score 0.0019, base fraud rate 2.63%.

| Predicted probability | Transactions | Mean predicted | Observed fraud rate |
|---|---|---|---|
| 0–0.001 | 21360 | 0.0000 | 0.0001 |
| 0.001–0.01 | 139 | 0.0031 | 0.0432 |
| 0.01–0.05 | 50 | 0.0252 | 0.3200 |
| 0.05–0.1 | 11 | 0.0720 | 0.1818 |
| 0.1–0.25 | 13 | 0.1580 | 0.3846 |
| 0.25–0.5 | 26 | 0.3934 | 0.9615 |
| 0.5–0.75 | 13 | 0.6591 | 1.0000 |
| 0.75–1 | 514 | 0.9855 | 0.9981 |
