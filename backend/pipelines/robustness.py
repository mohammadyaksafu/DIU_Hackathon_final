"""Robustness evaluation: how well does the model hold up beyond the easy, in-distribution test?

The headline test (train.py) mixes all fraud scenarios into training, so it measures how well the
model recognises patterns it has already seen. This script answers the harder questions a reviewer
should ask, on the same time-based split (train < valid < test):

 1. Leave-one-scenario-out: retrain WITHOUT one fraud family, then measure recall on that family in
    the test window. This approximates a brand-new fraud pattern.
 2. Unseen ring: replace the graph features of test fraud with typical legitimate values, as if the
    mule ring were brand new and not yet in the graph snapshot. Only live behaviour features remain.
 3. Calibration: expected calibration error (ECE), Brier score and a reliability table, so the
    "fraud probability" shown in the UI can be trusted as a probability.

Recall is measured at the operating point used in production: the 1% legitimate-FPR threshold,
learned on the validation window (never on test).

Usage:  python -m pipelines.robustness            (writes reports/robustness.json and .md)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, brier_score_loss

from app.detectors.anomaly import anomaly_matrix, to_percentile
from app.features.registry import model_feature_names
from app.graph.snapshot import GRAPH_FEATURES
from app.services.model_registry import PlattCalibrator
from pipelines.train import fit_lgbm

BACKEND = Path(__file__).resolve().parents[1]

# Fraud families (scenario labels from the generator). Refund bait + refund payment are one family,
# as are mule forwarding + mule cash-out.
FAMILIES = {
    "account_takeover": ["S1_ato"],
    "prize_scam": ["S2_prize_scam"],
    "refund_scam": ["S3_refund_bait", "S3_refund_scam"],
    "mule_network": ["S4_mule_forward", "S4_mule_cashout"],
    "structuring": ["S5_structuring"],
    "social_engineering": ["S6_social_engineering"],
}


def _threshold_at_fpr(y: np.ndarray, s: np.ndarray, fpr: float = 0.01) -> float:
    return float(np.quantile(s[y == 0], 1 - fpr))


CAL_EDGES = [0.0, 0.001, 0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 1.0000001]


def _ece(y: np.ndarray, p: np.ndarray) -> tuple[float, list[dict]]:
    """Expected calibration error over fixed probability bins (fine near 0, where most traffic is)."""
    idx = np.clip(np.searchsorted(CAL_EDGES, p, side="right") - 1, 0, len(CAL_EDGES) - 2)
    table, err = [], 0.0
    for b in range(len(CAL_EDGES) - 1):
        m = idx == b
        if not m.any():
            continue
        pred, obs = float(p[m].mean()), float(y[m].mean())
        err += m.mean() * abs(pred - obs)
        hi = min(CAL_EDGES[b + 1], 1.0)
        table.append({"range": f"{CAL_EDGES[b]:.3g}–{hi:.3g}", "n": int(m.sum()), "mean_predicted": round(pred, 4), "observed_fraud_rate": round(obs, 4)})
    return float(err), table


def run(data_dir: Path, reports_dir: Path, seed: int = 42, verbose: bool = True) -> dict:
    started = time.time()
    meta = json.loads((data_dir / "raw" / "meta.json").read_text(encoding="utf-8"))
    df = pd.read_parquet(data_dir / "features.parquet")
    tr = (df.day < meta["train_end_day"]).to_numpy()
    va = ((df.day >= meta["train_end_day"]) & (df.day < meta["valid_end_day"])).to_numpy()
    te = (df.day >= meta["valid_end_day"]).to_numpy()
    y = df.label.to_numpy()
    scen = df.scenario.to_numpy()

    # Same anomaly feature as train.py (fitted on the training window only).
    Xa = anomaly_matrix(df)
    iforest = IsolationForest(n_estimators=150, max_samples=4096, random_state=seed, n_jobs=-1).fit(Xa[tr])
    raw = -iforest.score_samples(Xa)
    df["anomaly_score"] = to_percentile(raw, np.quantile(raw[tr], np.linspace(0, 1, 1001)))
    features = model_feature_names() + ["anomaly_score"]
    X = df[features].astype(float).to_numpy()
    params = {"num_leaves": 31}

    # ---- baseline: all scenarios in training (the headline setting) -----------------------------
    base = fit_lgbm(X[tr], y[tr], X[va], y[va], params, seed)
    t_base = _threshold_at_fpr(y[va], base.predict(X[va]))
    s_te = base.predict(X[te])
    in_dist = {}
    for fam, labels in FAMILIES.items():
        m = np.isin(scen[te], labels)
        in_dist[fam] = float((s_te[m] > t_base).mean()) if m.any() else None

    # ---- 1. leave-one-scenario-out --------------------------------------------------------------
    loso = {}
    for fam, labels in FAMILIES.items():
        drop = np.isin(scen, labels)
        tr_f, va_f = tr & ~drop, va & ~drop  # the model never sees this family
        booster = fit_lgbm(X[tr_f], y[tr_f], X[va_f], y[va_f], params, seed)
        t = _threshold_at_fpr(y[va_f], booster.predict(X[va_f]))
        m = te & drop
        rec = float((booster.predict(X[m]) > t).mean()) if m.any() else None
        loso[fam] = {"n_test": int(m.sum()), "recall_seen": round(in_dist[fam], 3) if in_dist[fam] is not None else None,
                     "recall_unseen": round(rec, 3) if rec is not None else None}
        if verbose:
            print(f"  LOSO {fam:<20} seen {in_dist[fam]:.3f}  unseen {rec:.3f}  (n={int(m.sum())})")

    # ---- 2. unseen ring: graph features of test fraud set to typical legitimate values ----------
    gcols = [features.index(f) for f in GRAPH_FEATURES if f in features]
    X_cold = X[te].copy()
    legit_median = np.nanmedian(X[tr & (y == 0)][:, gcols], axis=0)
    fraud_te = y[te] == 1
    X_cold[np.ix_(fraud_te, gcols)] = legit_median
    s_cold = base.predict(X_cold)
    cold = {"recall_with_graph": round(float((s_te[fraud_te] > t_base).mean()), 3),
            "recall_unseen_ring": round(float((s_cold[fraud_te] > t_base).mean()), 3),
            "pr_auc_with_graph": round(float(average_precision_score(y[te], s_te)), 4),
            "pr_auc_unseen_ring": round(float(average_precision_score(y[te], s_cold)), 4)}
    cold["by_family"] = {}
    for fam, labels in FAMILIES.items():
        m = np.isin(scen[te], labels)
        if m.any():
            cold["by_family"][fam] = round(float((s_cold[m] > t_base).mean()), 3)

    # ---- 3. calibration ------------------------------------------------------------------------
    cal = PlattCalibrator().fit(base.predict(X[va]), y[va])
    p_te = np.clip(cal.predict(s_te), 0, 1)
    ece, table = _ece(y[te], p_te)
    calibration = {"ece": round(ece, 5), "brier": round(float(brier_score_loss(y[te], p_te)), 5),
                   "base_rate": round(float(y[te].mean()), 5), "reliability": table}

    out = {"seed": seed, "operating_point": "1% legitimate FPR (threshold learned on validation)",
           "leave_one_scenario_out": loso, "unseen_ring": cold, "calibration": calibration,
           "seconds": round(time.time() - started, 1)}
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "robustness.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (reports_dir / "robustness.md").write_text(_markdown(out), encoding="utf-8")
    return out


def _markdown(r: dict) -> str:
    lines = ["# Robustness report", "",
             f"Operating point: {r['operating_point']}. Same time-based split as the headline evaluation.", "",
             "## 1. Leave-one-scenario-out (new fraud pattern)", "",
             "The model is retrained **without** one fraud family, then tested on that family.", "",
             "| Fraud family | Test cases | Recall when seen in training | Recall when never seen |", "|---|---|---|---|"]
    for fam, v in r["leave_one_scenario_out"].items():
        lines.append(f"| {fam.replace('_', ' ')} | {v['n_test']} | {v['recall_seen']:.0%} | {v['recall_unseen']:.0%} |")
    c = r["unseen_ring"]
    lines += ["", "These figures are for the **ML model alone**. In the deployed system the deterministic rules",
              "(near-limit cash-outs, SIM-swap + PIN-reset combo, etc.) and the graph detector run alongside it, which is",
              "why a family the model has never seen (e.g. structuring) is still caught by policy.", ""]
    lines += ["", "## 2. Unseen mule ring (graph features unavailable)", "",
              "Graph features of every test fraud case are replaced with typical legitimate values, as if the ring were brand new.", "",
              "| Setting | Recall @ 1% FPR | PR-AUC |", "|---|---|---|",
              f"| With graph features | {c['recall_with_graph']:.0%} | {c['pr_auc_with_graph']:.3f} |",
              f"| Unseen ring (no graph signal) | {c['recall_unseen_ring']:.0%} | {c['pr_auc_unseen_ring']:.3f} |", "",
              "| Fraud family | Recall, unseen ring |", "|---|---|"]
    for fam, v in c["by_family"].items():
        lines.append(f"| {fam.replace('_', ' ')} | {v:.0%} |")
    k = r["calibration"]
    lines += ["", "## 3. Calibration of the displayed fraud probability", "",
              f"Expected calibration error **{k['ece']:.4f}**, Brier score {k['brier']:.4f}, base fraud rate {k['base_rate']:.2%}.", "",
              "| Predicted probability | Transactions | Mean predicted | Observed fraud rate |", "|---|---|---|---|"]
    for b in k["reliability"]:
        lines.append(f"| {b['range']} | {b['n']} | {b['mean_predicted']:.4f} | {b['observed_fraud_rate']:.4f} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    res = run(BACKEND / "data", BACKEND / "reports")
    print(json.dumps({k: v for k, v in res.items() if k != "calibration"} | {"ece": res["calibration"]["ece"]}, indent=2))
