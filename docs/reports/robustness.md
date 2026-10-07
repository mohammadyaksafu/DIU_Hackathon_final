# Robustness report

Operating point: 1% legitimate FPR (threshold learned on validation). Same time-based split as the headline evaluation.

## 1. Leave-one-scenario-out (new fraud pattern)

The model is retrained **without** one fraud family, then tested on that family.

| Fraud family | Test cases | Recall when seen in training | Recall when never seen |
|---|---|---|---|
| account takeover | 46 | 100% | 96% |
| prize scam | 93 | 97% | 87% |
| refund scam | 34 | 100% | 65% |
| mule network | 355 | 100% | 43% |
| structuring | 17 | 100% | 6% |
| social engineering | 38 | 100% | 97% |

These figures are for the **ML model alone**. In the deployed system the deterministic rules
(near-limit cash-outs, SIM-swap + PIN-reset combo, etc.) and the graph detector run alongside it, which is
why a family the model has never seen (e.g. structuring) is still caught by policy.


## 2. Unseen mule ring (graph features unavailable)

Graph features of every test fraud case are replaced with typical legitimate values, as if the ring were brand new.

| Setting | Recall @ 1% FPR | PR-AUC |
|---|---|---|
| With graph features | 100% | 0.995 |
| Unseen ring (no graph signal) | 97% | 0.972 |

| Fraud family | Recall, unseen ring |
|---|---|
| account takeover | 100% |
| prize scam | 97% |
| refund scam | 94% |
| mule network | 97% |
| structuring | 100% |
| social engineering | 97% |

## 3. Calibration of the displayed fraud probability

Expected calibration error **0.0026**, Brier score 0.0021, base fraud rate 2.63%.

| Predicted probability | Transactions | Mean predicted | Observed fraud rate |
|---|---|---|---|
| 0–0.001 | 21308 | 0.0000 | 0.0001 |
| 0.001–0.01 | 196 | 0.0028 | 0.0561 |
| 0.01–0.05 | 42 | 0.0202 | 0.1190 |
| 0.05–0.1 | 22 | 0.0678 | 0.6364 |
| 0.1–0.25 | 14 | 0.1851 | 0.7857 |
| 0.25–0.5 | 19 | 0.3954 | 0.8421 |
| 0.5–0.75 | 14 | 0.6247 | 1.0000 |
| 0.75–1 | 510 | 0.9879 | 1.0000 |
