"""Train, calibrate, evaluate and register the Shurokkha models.

Steps
 1. Time-based split: train (days < train_end), valid (< valid_end), test (rest; touched once).
 2. Isolation Forest on behavioural-deviation features -> anomaly percentile feature.
 3. Baselines: rules-only, logistic regression, LightGBM without graph features.
 4. LightGBM (small grid, early stopping on validation PR-AUC) + Platt (sigmoid) calibration.
 5. Thresholds from validation: WARN at 1% legit FPR, HOLD at >=90% precision.
 6. Full-system test evaluation through the real policy engine: per-scenario recall,
    fairness slices, business impact (with labelled assumptions), lift table.
 7. Write a versioned registry entry, reports, and seed alerts for the analyst console.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.detectors.anomaly import anomaly_matrix, to_percentile
from app.detectors.base import DetectorDeps, Signal
from app.detectors.agent_cashout import agent_cashout_risk
from app.detectors.graph import graph_risk
from app.detectors.rules import RulesDetector
from app.explain.reason_codes import select_reasons
from app.features.registry import model_feature_names
from app.graph.snapshot import GRAPH_FEATURES
from app.policy.engine import PolicyEngine
from app.services.model_registry import PlattCalibrator

VICTIM_LOSS_SCENARIOS = {"S1_ato", "S2_prize_scam", "S3_refund_scam", "S6_social_engineering"}
ASSUMED_WARN_HEEDED = 0.6  # assumption: share of warned victims who cancel (to be validated in a pilot)


def recall_at_fpr(y: np.ndarray, s: np.ndarray, fpr: float = 0.01) -> tuple[float, float]:
    legit = s[y == 0]
    t = float(np.quantile(legit, 1 - fpr)) if len(legit) else 1.0
    pos = s[y == 1]
    return (float((pos > t).mean()) if len(pos) else 0.0), t


def model_metrics(y: np.ndarray, s: np.ndarray) -> dict:
    r, t = recall_at_fpr(y, s)
    return {
        "pr_auc": round(float(average_precision_score(y, s)), 4),
        "roc_auc": round(float(roc_auc_score(y, s)), 4),
        "recall_at_1pct_fpr": round(r, 4),
    }


def fit_lgbm(X_tr, y_tr, X_va, y_va, params: dict, seed: int) -> lgb.Booster:
    base = {
        "objective": "binary",
        "metric": "average_precision",
        "learning_rate": 0.05,
        "min_data_in_leaf": 40,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "verbose": -1,
        "seed": seed,
        "deterministic": True,
        "num_threads": 4,
    }
    base.update(params)
    return lgb.train(
        base,
        lgb.Dataset(X_tr, y_tr),
        num_boost_round=1500,
        valid_sets=[lgb.Dataset(X_va, y_va)],
        callbacks=[lgb.early_stopping(60, verbose=False)],
    )


def train(data_dir: Path, registry_dir: Path, config_dir: Path, reports_dir: Path, seed: int = 42, verbose: bool = True) -> dict:
    started = time.time()
    raw_meta = json.loads((data_dir / "raw" / "meta.json").read_text(encoding="utf-8"))
    df = pd.read_parquet(data_dir / "features.parquet")
    customers = pd.read_parquet(data_dir / "raw" / "customers.parquet").set_index("id")
    tr = (df.day < raw_meta["train_end_day"]).to_numpy()
    va = ((df.day >= raw_meta["train_end_day"]) & (df.day < raw_meta["valid_end_day"])).to_numpy()
    te = (df.day >= raw_meta["valid_end_day"]).to_numpy()
    y = df.label.to_numpy()

    # ---- 2. anomaly model -----------------------------------------------------
    Xa = anomaly_matrix(df)
    iforest = IsolationForest(n_estimators=150, max_samples=4096, random_state=seed, n_jobs=-1).fit(Xa[tr])
    raw_anom = -iforest.score_samples(Xa)
    quantiles = np.quantile(raw_anom[tr], np.linspace(0, 1, 1001))
    df["anomaly_score"] = to_percentile(raw_anom, quantiles)

    features = model_feature_names() + ["anomaly_score"]
    X = df[features].astype(float).to_numpy()
    no_graph = [f for f in features if f not in GRAPH_FEATURES and f != "anomaly_score"]
    Xng = df[no_graph].astype(float).to_numpy()

    # ---- 3/4. models ------------------------------------------------------------
    best, best_ap, best_params = None, -1.0, None
    grid = [{"num_leaves": 15}, {"num_leaves": 31}, {"num_leaves": 63, "min_data_in_leaf": 60}]
    for params in grid:
        booster = fit_lgbm(X[tr], y[tr], X[va], y[va], params, seed)
        ap = average_precision_score(y[va], booster.predict(X[va]))
        if verbose:
            print(f"  grid {params}: valid PR-AUC={ap:.4f} iters={booster.best_iteration}")
        if ap > best_ap:
            best, best_ap, best_params = booster, ap, params
    booster = best
    calibrator = PlattCalibrator().fit(booster.predict(X[va]), y[va])
    p_all = np.clip(calibrator.predict(booster.predict(X)), 0, 1)
    p_raw_test = booster.predict(X[te])

    booster_ng = fit_lgbm(Xng[tr], y[tr], Xng[va], y[va], best_params, seed)
    logreg = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5))
    logreg.fit(np.nan_to_num(X[tr]), y[tr])

    rules = RulesDetector(DetectorDeps(bundle=None, config_dir=config_dir))
    test_rows = df[te].to_dict("records")
    rule_hits = [rules.evaluate_features(r) for r in test_rows]
    rule_score = np.array([max((h["score"] for h in hits), default=0.0) for hits in rule_hits])

    y_te = y[te]
    lift = {
        "rules_only": model_metrics(y_te, rule_score + 1e-9 * np.arange(len(rule_score)) / len(rule_score)),
        "logistic_regression": model_metrics(y_te, logreg.predict_proba(np.nan_to_num(X[te]))[:, 1]),
        "lightgbm_no_graph_no_anomaly": model_metrics(y_te, booster_ng.predict(Xng[te])),
        "lightgbm_full": model_metrics(y_te, p_raw_test),
    }

    # ---- 5. thresholds from validation ------------------------------------------
    p_va = p_all[va]
    legit_va = p_va[y[va] == 0]
    warn_t = float(max(0.05, np.quantile(legit_va, 0.99)))
    hold_t = None
    for t in np.unique(np.round(p_va, 4))[::-1]:
        sel = p_va >= t
        if sel.sum() >= 5 and y[va][sel].mean() >= 0.9:
            hold_t = float(t)
    hold_t = float(max(hold_t if hold_t is not None else np.quantile(legit_va, 0.999), warn_t + 0.05))

    # ---- 6. full-system evaluation on test through the real policy -------------
    policy = PolicyEngine(config_dir / "policy.yaml")
    policy.set_model_thresholds({"warn_t": warn_t, "hold_t": hold_t})
    p_te = p_all[te]
    anom_te = df.anomaly_score.to_numpy()[te]
    actions, graph_scores, decisions_meta = [], [], []
    for i, row in enumerate(test_rows):
        g, _ = graph_risk(row)
        graph_scores.append(g)
        names = {**row, "lgbm": float(p_te[i]), "anomaly": float(anom_te[i]), "graph": g, "rules": float(rule_score[i]),
                 "agent_cashout": agent_cashout_risk(row)[0]}
        d = policy.decide(names, {h["name"] for h in rule_hits[i]})
        actions.append(d.action)
    actions = np.array(actions)
    flagged = actions != "ALLOW"
    test = df[te].copy()
    test["action"] = actions
    test["flagged"] = flagged
    test["p"] = p_te

    per_scenario = {}
    for scen, grp in test[test.label == 1].groupby("scenario"):
        per_scenario[scen] = {
            "n": int(len(grp)),
            "recall_flagged": round(float(grp.flagged.mean()), 4),
            "recall_hold": round(float((grp.action == "HOLD").mean()), 4),
        }
    n_days_test = int(test.day.nunique())
    tp = int((flagged & (y_te == 1)).sum())
    fp = int((flagged & (y_te == 0)).sum())
    system = {
        "alerts_total": int(flagged.sum()),
        "alerts_per_day": round(float(flagged.sum()) / max(1, n_days_test), 1),
        "precision": round(tp / max(1, tp + fp), 4),
        "recall": round(tp / max(1, int(y_te.sum())), 4),
        "false_positive_rate": round(fp / max(1, int((y_te == 0).sum())), 5),
        "hold_precision": round(float(test[test.action == "HOLD"].label.mean()) if (test.action == "HOLD").any() else 0.0, 4),
        "decisions": {a: int((actions == a).sum()) for a in ("ALLOW", "WARN", "HOLD")},
        "test_transactions": int(len(test)),
        "test_days": n_days_test,
    }

    victim = test[test.scenario.isin(VICTIM_LOSS_SCENARIOS)]
    loss_total = float(victim.amount.sum())
    loss_hold = float(victim[victim.action == "HOLD"].amount.sum())
    loss_warn = float(victim[victim.action == "WARN"].amount.sum())
    business = {
        "victim_loss_total_bdt": round(loss_total),
        "victim_loss_flagged_bdt": round(loss_hold + loss_warn),
        "victim_loss_flagged_share": round((loss_hold + loss_warn) / max(1.0, loss_total), 4),
        "estimated_prevented_bdt": round(loss_hold + ASSUMED_WARN_HEEDED * loss_warn),
        "assumptions": {
            "warn_heeded_rate": ASSUMED_WARN_HEEDED,
            "hold_prevented_rate": 1.0,
            "note": "Estimates on synthetic data. Real effect must be measured in a controlled pilot.",
        },
        "legit_customers_warned_per_day": round(fp / max(1, n_days_test), 1),
        "mule_cashout_value_flagged_bdt": round(float(test[(test.scenario == "S4_mule_cashout") & test.flagged].amount.sum())),
    }

    # Fairness: FPR and alert rate across customer segments (senders that are customers).
    seg = test[(test.label == 0) & test.sender.isin(customers.index)].copy()
    seg = seg.join(customers[["division", "age_band", "kyc_level", "persona"]], on="sender")
    seg["tenure_bucket"] = np.where(seg.s_tenure_days < 90, "<90d", ">=90d")
    fairness = {}
    for col in ["division", "age_band", "kyc_level", "persona", "tenure_bucket"]:
        g = seg.groupby(col).flagged.agg(["mean", "count"])
        g = g[g["count"] >= 200]
        rates = {str(k): {"fpr": round(float(v["mean"]), 5), "n_legit": int(v["count"])} for k, v in g.iterrows()}
        vals = [r["fpr"] for r in rates.values()]
        ratio = (max(vals) / max(min(vals), 1e-4)) if vals else 1.0
        fairness[col] = {"groups": rates, "max_min_ratio": round(ratio, 2), "flag": bool(ratio > 1.25 and max(vals) > 0.005)}

    importance = sorted(zip(features, booster.feature_importance("gain")), key=lambda x: -x[1])
    total_gain = sum(v for _, v in importance) or 1.0

    metrics = {
        "model": {**model_metrics(y_te, p_te), "brier": round(float(brier_score_loss(y_te, p_te)), 5)},
        "lift_table": lift,
        "system": system,
        "per_scenario": per_scenario,
        "business": business,
        "fairness": fairness,
        "thresholds": {"warn_t": round(warn_t, 5), "hold_t": round(hold_t, 5)},
        "feature_importance_top15": [{"feature": f, "gain_share": round(float(v) / total_gain, 4)} for f, v in importance[:15]],
        "data": {k: raw_meta[k] for k in ("n_transactions", "n_fraud", "fraud_rate", "scenario_counts", "n_days", "seed")},
        "split": {"train": int(tr.sum()), "valid": int(va.sum()), "test": int(te.sum()),
                  "train_end_day": raw_meta["train_end_day"], "valid_end_day": raw_meta["valid_end_day"]},
    }

    # ---- 7. registry --------------------------------------------------------------
    version = "lgbm-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    vdir = registry_dir / version
    vdir.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(vdir / "model.txt"), num_iteration=booster.best_iteration)
    joblib.dump(calibrator, vdir / "calibrator.joblib")
    joblib.dump({"model": iforest, "quantiles": quantiles}, vdir / "anomaly.joblib")
    (vdir / "features.json").write_text(json.dumps(features, indent=1), encoding="utf-8")
    (vdir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    meta = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "LightGBM + Platt calibration; IsolationForest anomaly feature",
        "params": {**best_params, "best_iteration": booster.best_iteration},
        "thresholds": {"warn_t": warn_t, "hold_t": hold_t},
        "data_seed": raw_meta["seed"],
        "data_generated_at": raw_meta["generated_at"],
        "n_features": len(features),
    }
    (vdir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (registry_dir / "ACTIVE").write_text(version, encoding="utf-8")

    # Seed alerts (test window) for the analyst console.
    seeds = []
    flagged_idx = np.where(flagged)[0]
    if len(flagged_idx):
        Xf = X[te][flagged_idx]
        contribs = booster.predict(Xf, pred_contrib=True)
        last_day = int(test.day.max())
        rng = np.random.default_rng(seed)
        for j, i in enumerate(flagged_idx):
            row = test_rows[i]
            order = np.argsort(-np.abs(contribs[j][:-1]))[:10]
            contributions = [{"feature": features[k], "value": row.get(features[k]) if features[k] != "anomaly_score" else float(anom_te[i]),
                              "contribution": round(float(contribs[j][k]), 4)} for k in order]
            feats = {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in row.items()
                     if k in features or k in ("amount",)}
            feats["anomaly_score"] = float(anom_te[i])
            sigs = {
                "lgbm": Signal(detector="lgbm", score=float(p_te[i]), details={"contributions": contributions}),
                "rules": Signal(detector="rules", score=float(rule_score[i]), reason_codes=[h["reason"] for h in rule_hits[i]],
                                details={"hits": [h["name"] for h in rule_hits[i]]}),
                "graph": Signal(detector="graph", score=float(graph_scores[i]),
                                reason_codes=["R_MULE_NETWORK"] if graph_scores[i] >= 0.6 else []),
                "anomaly": Signal(detector="anomaly", score=float(anom_te[i]),
                                  reason_codes=["R_BEHAVIOUR_ANOMALY"] if anom_te[i] >= 0.995 else []),
            }
            old = row["day"] < last_day - 2
            resolved = old and rng.random() < 0.6
            seeds.append({
                "tx_id": row["tx_id"], "tx_ts": float(row["ts"]), "tx_type": row["type"], "sender": row["sender"],
                "receiver": row["receiver"], "amount": float(row["amount"]), "decision": str(actions[i]),
                "risk_score": round(float(p_te[i]), 5), "reason_codes": select_reasons(feats, sigs),
                "signals": {k: v.model_dump() for k, v in sigs.items()}, "features": feats, "model_version": version,
                "policy_version": policy.version, "status": "RESOLVED" if resolved else "OPEN",
                "label": ("fraud" if row["label"] == 1 else "legit") if resolved else None,
                "scenario_tag": row["scenario"],
            })
    (data_dir / "seed_alerts.json").write_text(json.dumps(seeds), encoding="utf-8")

    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "metrics.json").write_text(json.dumps({"version": version, **metrics}, indent=2), encoding="utf-8")
    (reports_dir / "fairness.md").write_text(fairness_markdown(version, fairness), encoding="utf-8")
    if verbose:
        print(json.dumps({"version": version, "model": metrics["model"], "lift_table": lift, "system": system,
                          "per_scenario": per_scenario, "business": business}, indent=2))
        print(f"trained in {time.time() - started:.1f}s; {len(seeds)} seed alerts")
    return {"version": version, "metrics": metrics}


def fairness_markdown(version: str, fairness: dict) -> str:
    lines = [f"# Fairness report: {version}", "",
             "False-positive rate (legitimate transactions flagged WARN/HOLD) by customer segment on the held-out test window.",
             "Segments with < 200 legitimate transactions are omitted. A segment is flagged when max/min FPR > 1.25 and max FPR > 0.5%.", ""]
    for col, info in fairness.items():
        lines.append(f"## {col}  (max/min ratio {info['max_min_ratio']}{', ⚠ review' if info['flag'] else ''})")
        lines.append("| group | FPR | legit n |")
        lines.append("|---|---|---|")
        for g, r in info["groups"].items():
            lines.append(f"| {g} | {r['fpr'] * 100:.2f}% | {r['n_legit']} |")
        lines.append("")
    lines.append("Segment attributes (division, age band, KYC level, persona) are **not** model inputs; they are used only for this audit.")
    return "\n".join(lines) + "\n"
