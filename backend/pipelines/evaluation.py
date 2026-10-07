"""Evidence pack for reviewers: ablation, cost, shift, adversarial rounds, leakage, hard data, fairness.

Everything runs on the same time-based split as training (train < valid < test). Thresholds and
calibration are always learned on the validation window; the test window is only scored.

 1. Ablation: rules only -> LightGBM only -> + Isolation Forest -> + graph -> full Shurokkha
    (policy over rules + model + graph + anomaly + agent cash-out), with cost-sensitive metrics,
    ECE and bootstrap 95% confidence intervals, plus the marginal contribution of each layer.
 2. Cost-optimal thresholds from an explicit cost function, compared with the learned thresholds.
 3. Leave-one-fraud-family-out: model alone vs the full system (how much rules/graph/anomaly rescue).
 4. Distribution shift: later time window, covariate shift (more new users, phones, Eid amounts)
    and adversarial drift (lower amounts, slower mules, rotated devices).
 5. Adversarial rounds: attacker evades -> defender retrains on the attack -> attacker escalates.
 6. Leakage audit: single-feature ROC-AUC and gain share; any one feature that separates alone is flagged.
 7. Harder synthetic data (overlapping behaviour, generate_data hard=True): full retrain and evaluation.
 8. Segment fairness: FPR, FNR, warning rate and ECE per segment, and the merchant-aware fix before/after.
 9. Calibration before / after Platt scaling.

Usage:  python -m pipelines.evaluation [--skip-hard]   (writes reports/evaluation.json and .md)
Numbers are on synthetic data. They show method and relative value, not production performance.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from app.detectors.agent_cashout import agent_cashout_risk
from app.detectors.anomaly import anomaly_matrix, to_percentile
from app.detectors.base import DetectorDeps
from app.detectors.graph import graph_risk
from app.detectors.rules import RulesDetector
from app.features.registry import MERCHANT_PERSONAS, model_feature_names
from app.graph.snapshot import GRAPH_FEATURES
from app.policy.engine import PolicyEngine
from app.services.model_registry import PlattCalibrator
from pipelines.robustness import FAMILIES, _ece
from pipelines.train import VICTIM_LOSS_SCENARIOS, fit_lgbm

BACKEND = Path(__file__).resolve().parents[1]
PARAMS = {"num_leaves": 31}

# Cost function (BDT). Stated assumptions, to be replaced with upay's own figures.
COST = {
    "warn_heeded": 0.6,          # share of warned victims who cancel (central assumption; the user study measures it)
    "other_fraud_missed": 200,   # missed mule/structuring transfer: AML exposure + investigation (victim loss counted once)
    "fp_warn": 20,               # friction of an unnecessary warning (time, annoyance, some abandoned payments)
    "fp_hold": 150,              # a legitimate transfer delayed for review (support call, lost goodwill)
    "analyst_cost_per_min": 8,   # loaded analyst cost
    "minutes_per_hold": 6,
    "minutes_per_warn_alert": 1,
}


# ----------------------------------------------------------------------------- helpers
def learned_thresholds(p_va: np.ndarray, y_va: np.ndarray) -> dict:
    """Same rule as train.py: WARN at 1% legitimate FPR, HOLD where precision >= 90%."""
    legit = p_va[y_va == 0]
    warn_t = float(max(0.05, np.quantile(legit, 0.99)))
    hold_t = None
    for t in np.unique(np.round(p_va, 4))[::-1]:
        sel = p_va >= t
        if sel.sum() >= 5 and y_va[sel].mean() >= 0.9:
            hold_t = float(t)
    hold_t = float(max(hold_t if hold_t is not None else np.quantile(legit, 0.999), warn_t + 0.05))
    return {"warn_t": warn_t, "hold_t": hold_t}


def threshold_actions(p: np.ndarray, t: dict) -> np.ndarray:
    return np.where(p >= t["hold_t"], "HOLD", np.where(p >= t["warn_t"], "WARN", "ALLOW"))


def recall_at_fpr(y_va, s_va, y_te, s_te, fpr=0.01) -> float:
    t = float(np.quantile(s_va[y_va == 0], 1 - fpr))
    pos = s_te[y_te == 1]
    return float((pos > t).mean()) if len(pos) else 0.0


class Ctx:
    """Test-window rows with everything the policy needs, recomputable after a perturbation."""

    def __init__(self, df: pd.DataFrame, config_dir: Path, iforest, quantiles) -> None:
        self.df = df.reset_index(drop=True)
        self.rules = RulesDetector(DetectorDeps(bundle=None, config_dir=config_dir))
        self.iforest, self.quantiles = iforest, quantiles
        self.refresh()

    def refresh(self) -> None:
        df = self.df
        df["anomaly_score"] = to_percentile(-self.iforest.score_samples(anomaly_matrix(df)), self.quantiles)
        self.rows = df.to_dict("records")
        self.hits = [self.rules.evaluate_features(r) for r in self.rows]
        self.rule_score = np.array([max((float(h["score"]) for h in hs), default=0.0) for hs in self.hits])
        self.graph = np.array([graph_risk(r)[0] for r in self.rows])
        self.agent = np.array([agent_cashout_risk(r)[0] for r in self.rows])


def policy_actions(ctx: Ctx, p: np.ndarray, thresholds: dict, config_dir: Path, use: set[str] | None = None,
                   policy_path: Path | None = None) -> np.ndarray:
    """Run the real policy engine. `use` limits which detectors exist (ablation)."""
    use = use or {"lgbm", "rules", "graph", "anomaly", "agent_cashout"}
    policy = PolicyEngine(policy_path or config_dir / "policy.yaml")
    policy.set_model_thresholds(thresholds)
    out = []
    an = ctx.df.anomaly_score.to_numpy()
    for i, row in enumerate(ctx.rows):
        names = {**row,
                 "lgbm": float(p[i]) if "lgbm" in use else 0.0,
                 "rules": float(ctx.rule_score[i]) if "rules" in use else 0.0,
                 "graph": float(ctx.graph[i]) if "graph" in use else 0.0,
                 "anomaly": float(an[i]) if "anomaly" in use else 0.0,
                 "agent_cashout": float(ctx.agent[i]) if "agent_cashout" in use else 0.0}
        hits = {h["name"] for h in ctx.hits[i]} if "rules" in use else set()
        out.append(policy.decide(names, hits).action)
    return np.array(out)


def decision_metrics(df: pd.DataFrame, actions: np.ndarray, n_days: int) -> dict:
    y = df.label.to_numpy()
    amt = df.amount.to_numpy()
    victim = df.scenario.isin(VICTIM_LOSS_SCENARIOS).to_numpy()
    flagged = actions != "ALLOW"
    hold, warn = actions == "HOLD", actions == "WARN"
    legit = y == 0
    mule = df.scenario.isin(FAMILIES["mule_network"]).to_numpy()
    c = COST
    missed_loss = amt[victim & ~flagged].sum() + amt[victim & warn].sum() * (1 - c["warn_heeded"])
    other_missed = ((y == 1) & ~victim & ~flagged).sum() * c["other_fraud_missed"]
    friction = (legit & warn).sum() * c["fp_warn"] + (legit & hold).sum() * c["fp_hold"]
    analyst = (hold.sum() * c["minutes_per_hold"] + warn.sum() * c["minutes_per_warn_alert"]) * c["analyst_cost_per_min"]
    return {
        "recall_flagged": round(float(flagged[y == 1].mean()), 4),
        "mule_recall": round(float(flagged[mule].mean()), 4) if mule.any() else None,
        "loss_value_caught": round(float(amt[victim & flagged].sum() / max(1.0, amt[victim].sum())), 4),
        "fp_per_10k": round(float((legit & flagged).sum() / max(1, legit.sum()) * 10_000), 2),
        "holds_per_day": round(float(hold.sum()) / n_days, 1),
        "alerts_per_day": round(float(flagged.sum()) / n_days, 1),
        "precision": round(float(y[flagged].mean()), 4) if flagged.any() else None,
        "expected_cost_per_day_bdt": round(float(missed_loss + other_missed + friction + analyst) / n_days),
        "cost_breakdown_per_day_bdt": {"missed_loss": round(float(missed_loss + other_missed) / n_days),
                                       "customer_friction": round(float(friction) / n_days),
                                       "analyst_time": round(float(analyst) / n_days)},
    }


def bootstrap(df: pd.DataFrame, score: np.ndarray, actions: np.ndarray, b: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    y = df.label.to_numpy()
    amt = df.amount.to_numpy()
    victim = df.scenario.isin(VICTIM_LOSS_SCENARIOS).to_numpy()
    flagged = actions != "ALLOW"
    stats = {"pr_auc": [], "recall_flagged": [], "loss_value_caught": [], "fp_per_10k": []}
    n = len(y)
    for _ in range(b):
        i = rng.integers(0, n, n)
        yi, fi = y[i], flagged[i]
        if yi.sum() == 0 or (yi == 0).sum() == 0:
            continue
        stats["pr_auc"].append(average_precision_score(yi, score[i]))
        stats["recall_flagged"].append(fi[yi == 1].mean())
        vi = victim[i]
        stats["loss_value_caught"].append(amt[i][vi & fi].sum() / max(1.0, amt[i][vi].sum()))
        stats["fp_per_10k"].append(fi[yi == 0].mean() * 10_000)
    return {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in stats.items() if v}


# ----------------------------------------------------------------------------- perturbations
def perturb_covariate(df: pd.DataFrame, rng) -> pd.DataFrame:
    """More new users, more phone changes and an Eid-style spike in legitimate amounts."""
    d = df.copy()
    legit = (d.label == 0).to_numpy()
    new_user = legit & (rng.random(len(d)) < 0.30)
    d.loc[new_user, "s_tenure_days"] = d.loc[new_user, "s_tenure_days"] * 0.1
    d.loc[new_user, "s_hist_count"] = np.minimum(d.loc[new_user, "s_hist_count"], 5)
    phone = legit & (rng.random(len(d)) < 0.10)
    d.loc[phone, ["is_new_device", "recent_device"]] = 1
    d.loc[phone, "s_device_age_hrs"] = 0.0
    d.loc[phone, "new_device_new_recipient"] = d.loc[phone, "is_new_recipient"]
    eid = legit & (rng.random(len(d)) < 0.20)
    _scale_amount(d, eid, 3.0)
    return d


def _legit_sample(d: pd.DataFrame, col: str, n: int, rng) -> np.ndarray:
    """Values drawn from legitimate traffic, so an attack never leaves a constant 'tell' of its own."""
    pool = d.loc[d.label == 0, col].to_numpy()
    return rng.choice(pool, size=n) if len(pool) else np.zeros(n)


def perturb_adversarial(df: pd.DataFrame, strength: float = 1.0, seed: int = 7) -> pd.DataFrame:
    """Fraudsters adapt: smaller amounts, slower mules, older devices. strength 1 = moderate, 2 = strong.

    Changed values are copied from legitimate traffic (with jitter), so the defender cannot simply learn
    the attack's own artefacts.
    """
    rng = np.random.default_rng(seed)
    d = df.copy()
    fraud = (d.label == 1).to_numpy()
    n = int(fraud.sum())
    k = np.clip(rng.normal(1 / (1 + 1.5 * strength), 0.08, n), 0.15, 1.0)
    _scale_amount(d, fraud, k)
    d.loc[fraud, "near_limit"] = 0
    d.loc[fraud, "s_out_cnt_1h"] = _legit_sample(df, "s_out_cnt_1h", n, rng)
    slow = rng.random(n) < min(1.0, 0.5 * strength)
    mins = d.loc[fraud, "s_mins_since_inflow"].to_numpy()
    d.loc[fraud, "s_mins_since_inflow"] = np.where(slow, _legit_sample(df, "s_mins_since_inflow", n, rng), mins)
    d.loc[fraud, "r_new_senders_24h"] = (d.loc[fraud, "r_new_senders_24h"] // (1 + 2 * strength)).astype(d["r_new_senders_24h"].dtype)
    d.loc[fraud, "s_new_sender_inflow_1h"] = 0 if strength >= 1 else d.loc[fraud, "s_new_sender_inflow_1h"]
    old_phone = rng.random(n) < min(1.0, 0.5 * strength)
    idx = d.index[fraud][old_phone]
    d.loc[idx, ["is_new_device", "recent_device", "new_device_new_recipient"]] = 0
    d.loc[idx, "s_device_age_hrs"] = _legit_sample(df, "s_device_age_hrs", len(idx), rng)
    if strength >= 2:  # strong: also act at normal hours and avoid fresh rings
        d.loc[fraud, ["is_night", "night_new_recipient"]] = 0
        d.loc[fraud, "s_hour_freq"] = _legit_sample(df, "s_hour_freq", n, rng)
        for g in ("r_g_comm_fanin", "r_g_comm_cashout", "r_g_fwd", "s_g_comm_fanin", "s_g_comm_cashout", "s_g_fwd"):
            if g in d:
                d.loc[fraud, g] = d.loc[fraud, g] * 0.5
    return d


def _scale_amount(d: pd.DataFrame, mask: np.ndarray, k) -> None:
    d.loc[mask, "amount"] = d.loc[mask, "amount"] * k
    d.loc[mask, "amount_log"] = np.log1p(d.loc[mask, "amount"])
    d.loc[mask, "amount_ratio"] = np.minimum(100.0, d.loc[mask, "amount_ratio"] * k)
    d.loc[mask, "amount_z"] = d.loc[mask, "amount_z"] + np.log(np.asarray(k, dtype=float)) / 0.6
    d.loc[mask, "s_out_sum_24h_ratio"] = d.loc[mask, "s_out_sum_24h_ratio"] * k
    if "amount_to_limit" in d:
        d.loc[mask, "amount_to_limit"] = d.loc[mask, "amount"] / 25_000


# ----------------------------------------------------------------------------- main
def add_profile_features(df: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Older feature files predate the profile/agent features; derive what the rules need."""
    merchants = set(customers.index[customers.persona.isin(MERCHANT_PERSONAS)])
    if "r_merchant_profile" not in df:
        df["r_merchant_profile"] = df.receiver.isin(merchants).astype(float)
        df["s_merchant_profile"] = df.sender.isin(merchants).astype(float)
    for c in ("on_call", "a_cashouts_1h", "a_new_customers_1h", "a_cashout_rate_ratio"):
        if c not in df:
            df[c] = 0.0
    return df


def run(data_dir: Path, config_dir: Path, reports_dir: Path, seed: int = 42, hard: bool = True,
        boot: int = 200, verbose: bool = True) -> dict:
    started = time.time()
    meta = json.loads((data_dir / "raw" / "meta.json").read_text(encoding="utf-8"))
    customers = pd.read_parquet(data_dir / "raw" / "customers.parquet").set_index("id")
    df = add_profile_features(pd.read_parquet(data_dir / "features.parquet"), customers)
    tr = (df.day < meta["train_end_day"]).to_numpy()
    va = ((df.day >= meta["train_end_day"]) & (df.day < meta["valid_end_day"])).to_numpy()
    te = (df.day >= meta["valid_end_day"]).to_numpy()
    y = df.label.to_numpy()
    n_days = int(df[te].day.nunique())

    def log(msg: str) -> None:
        if verbose:
            print(f"  [{time.time() - started:5.0f}s] {msg}")

    # anomaly model on the training window (unsupervised)
    Xa = anomaly_matrix(df)
    iforest = IsolationForest(n_estimators=150, max_samples=4096, random_state=seed, n_jobs=-1).fit(Xa[tr])
    raw = -iforest.score_samples(Xa)
    quantiles = np.quantile(raw[tr], np.linspace(0, 1, 1001))
    df["anomaly_score"] = to_percentile(raw, quantiles)

    base_feats = [f for f in model_feature_names() if f not in GRAPH_FEATURES]
    feats = {"lgbm_only": base_feats, "lgbm_if": base_feats + ["anomaly_score"],
             "lgbm_graph": model_feature_names() + ["anomaly_score"]}
    models, cal, p = {}, {}, {}
    for name, cols in feats.items():
        X = df[cols].astype(float).to_numpy()
        models[name] = fit_lgbm(X[tr], y[tr], X[va], y[va], PARAMS, seed)
        raw_s = models[name].predict(X)
        cal[name] = PlattCalibrator().fit(raw_s[va], y[va])
        p[name] = np.clip(cal[name].predict(raw_s), 0, 1)
        log(f"trained {name}")
    full_cols = feats["lgbm_graph"]
    X_full = df[full_cols].astype(float).to_numpy()

    test = df[te].reset_index(drop=True)
    ctx = Ctx(test.copy(), config_dir, iforest, quantiles)
    y_te, y_va = y[te], y[va]
    rules_va = np.array([max((float(h["score"]) for h in ctx.rules.evaluate_features(r)), default=0.0)
                         for r in df[va].to_dict("records")])
    th = {k: learned_thresholds(v[va], y_va) for k, v in p.items()}

    # ---- 1. ablation -------------------------------------------------------------------------
    systems = {}
    rules_actions = np.where(ctx.rule_score >= 0.9, "HOLD", np.where(ctx.rule_score >= 0.6, "WARN", "ALLOW"))
    configs = [
        ("Rules only", ctx.rule_score, rules_va, rules_actions, ctx.rule_score),
        ("LightGBM only", p["lgbm_only"][te], p["lgbm_only"][va], threshold_actions(p["lgbm_only"][te], th["lgbm_only"]), p["lgbm_only"][te]),
        ("+ Isolation Forest", p["lgbm_if"][te], p["lgbm_if"][va], threshold_actions(p["lgbm_if"][te], th["lgbm_if"]), p["lgbm_if"][te]),
        ("+ Graph features", p["lgbm_graph"][te], p["lgbm_graph"][va], threshold_actions(p["lgbm_graph"][te], th["lgbm_graph"]), p["lgbm_graph"][te]),
    ]
    full_actions = policy_actions(ctx, p["lgbm_graph"][te], th["lgbm_graph"], config_dir)
    fused_te = np.maximum(p["lgbm_graph"][te], ctx.rule_score)
    fused_va = np.maximum(p["lgbm_graph"][va], rules_va)
    configs.append(("Full Shurokkha", fused_te, fused_va, full_actions, p["lgbm_graph"][te]))
    prev = None
    for name, s_te, s_va, actions, prob in configs:
        tie = 1e-9 * np.arange(len(s_te)) / len(s_te)  # deterministic tie-break for step scores (rules)
        m = {"pr_auc": round(float(average_precision_score(y_te, s_te + tie)), 4),
             "recall_at_1pct_fpr": round(recall_at_fpr(y_va, s_va, y_te, s_te), 4),
             **decision_metrics(test, actions, n_days),
             "ece": round(_ece(y_te, np.clip(prob, 0, 1))[0], 5)}
        m["ci95"] = bootstrap(test, s_te + tie, actions, boot, seed)
        if prev is not None:
            m["marginal"] = {"recall_flagged": round(m["recall_flagged"] - prev["recall_flagged"], 4),
                             "mule_recall": round((m["mule_recall"] or 0) - (prev["mule_recall"] or 0), 4),
                             "expected_cost_per_day_bdt": m["expected_cost_per_day_bdt"] - prev["expected_cost_per_day_bdt"]}
        systems[name] = m
        prev = m
        log(f"ablation {name}: recall {m['recall_flagged']:.3f} cost/day {m['expected_cost_per_day_bdt']}")

    # ---- 2. cost-optimal thresholds ----------------------------------------------------------
    va_df = df[va].reset_index(drop=True)
    va_ctx = Ctx(va_df.copy(), config_dir, iforest, quantiles)
    grid_w = sorted(set(np.round(np.geomspace(0.02, 0.5, 8), 4)))
    best = None
    p_va_full = p["lgbm_graph"][va]
    for w in grid_w:
        for h in [x for x in np.round(np.geomspace(0.1, 0.95, 7), 4) if x > w]:
            acts = policy_actions(va_ctx, p_va_full, {"warn_t": float(w), "hold_t": float(h)}, config_dir)
            c = decision_metrics(va_df, acts, int(va_df.day.nunique()))["expected_cost_per_day_bdt"]
            if best is None or c < best[0]:
                best = (c, float(w), float(h))
    opt = {"warn_t": best[1], "hold_t": best[2]}
    opt_actions = policy_actions(ctx, p["lgbm_graph"][te], opt, config_dir)
    cost_opt = {"cost_function": COST, "learned_thresholds": {k: round(v, 4) for k, v in th["lgbm_graph"].items()},
                "cost_optimal_thresholds": opt, "test_learned": decision_metrics(test, full_actions, n_days),
                "test_cost_optimal": decision_metrics(test, opt_actions, n_days)}
    log(f"cost-optimal thresholds {opt}")

    # ---- 3. leave-one-family-out: model alone vs full system ---------------------------------
    scen = df.scenario.to_numpy()
    lofo = {}
    for fam, labels in FAMILIES.items():
        drop = np.isin(scen, labels)
        tr_f, va_f = tr & ~drop, va & ~drop
        booster = fit_lgbm(X_full[tr_f], y[tr_f], X_full[va_f], y[va_f], PARAMS, seed)
        raw_f = booster.predict(X_full)
        c_f = PlattCalibrator().fit(raw_f[va_f], y[va_f])
        p_f = np.clip(c_f.predict(raw_f), 0, 1)
        t_f = learned_thresholds(p_f[va_f], y[va_f])
        fam_te = np.isin(test.scenario.to_numpy(), labels)
        model_flag = threshold_actions(p_f[te], t_f) != "ALLOW"
        sys_flag = policy_actions(ctx, p_f[te], t_f, config_dir) != "ALLOW"
        lofo[fam] = {"n_test": int(fam_te.sum()),
                     "model_alone_recall": round(float(model_flag[fam_te].mean()), 3) if fam_te.any() else None,
                     "full_system_recall": round(float(sys_flag[fam_te].mean()), 3) if fam_te.any() else None,
                     "full_system_fp_per_10k": round(float(sys_flag[y_te == 0].mean() * 10_000), 2)}
        log(f"LOFO {fam}: model {lofo[fam]['model_alone_recall']} system {lofo[fam]['full_system_recall']}")

    # ---- 4. distribution shift -------------------------------------------------------------
    booster_full = models["lgbm_graph"]

    def evaluate_shift(frame: pd.DataFrame, model=booster_full, calib=cal["lgbm_graph"], t=th["lgbm_graph"]) -> dict:
        c2 = Ctx(frame.copy(), config_dir, iforest, quantiles)
        pp = np.clip(calib.predict(model.predict(c2.df[full_cols].astype(float).to_numpy())), 0, 1)
        acts = policy_actions(c2, pp, t, config_dir)
        out = decision_metrics(c2.df, acts, int(c2.df.day.nunique()))
        out["model_recall"] = round(float((threshold_actions(pp, t) != "ALLOW")[c2.df.label.to_numpy() == 1].mean()), 4)
        out["ece"] = round(_ece(c2.df.label.to_numpy(), pp)[0], 5)
        return out

    rng = np.random.default_rng(seed)
    days = sorted(test.day.unique())
    half = days[len(days) // 2]
    shift = {
        "baseline_test": evaluate_shift(test),
        "temporal_first_half": evaluate_shift(test[test.day < half]),
        "temporal_second_half": evaluate_shift(test[test.day >= half]),
        "covariate_shift": evaluate_shift(perturb_covariate(test, rng)),
        "adversarial_drift": evaluate_shift(perturb_adversarial(test, 1.0)),
    }
    log("shift suite done")

    # ---- 5. adversarial rounds -------------------------------------------------------------
    rounds = []
    tr_df = df[tr].reset_index(drop=True)
    model_r, cal_r, th_r = booster_full, cal["lgbm_graph"], th["lgbm_graph"]
    for k, strength in enumerate((1.0, 2.0), start=1):
        attacked_test = perturb_adversarial(test, strength)
        before = evaluate_shift(attacked_test, model_r, cal_r, th_r)
        # defender: add attacked copies of training fraud, retrain, recalibrate, re-threshold
        fraud_tr = tr_df[tr_df.label == 1]
        aug = pd.concat([tr_df, perturb_adversarial(pd.concat([fraud_tr, tr_df[tr_df.label == 0].sample(20_000, random_state=seed)]),
                                                     strength, seed=k).query("label == 1")], ignore_index=True)
        aug["anomaly_score"] = to_percentile(-iforest.score_samples(anomaly_matrix(aug)), quantiles)
        X_aug = aug[full_cols].astype(float).to_numpy()
        model_r = fit_lgbm(X_aug, aug.label.to_numpy(), X_full[va], y_va, PARAMS, seed)
        raw_v = model_r.predict(X_full[va])
        cal_r = PlattCalibrator().fit(raw_v, y_va)
        th_r = learned_thresholds(np.clip(cal_r.predict(raw_v), 0, 1), y_va)
        after = evaluate_shift(attacked_test, model_r, cal_r, th_r)
        clean = evaluate_shift(test, model_r, cal_r, th_r)
        rounds.append({"round": k, "attack_strength": strength,
                       "recall_before_retrain": before["recall_flagged"], "recall_after_retrain": after["recall_flagged"],
                       "fp_per_10k_after": after["fp_per_10k"], "clean_recall_after": clean["recall_flagged"]})
        log(f"adversarial round {k}: {before['recall_flagged']:.3f} -> {after['recall_flagged']:.3f}")

    # ---- 6. leakage audit ------------------------------------------------------------------
    single = []
    for f in full_cols:
        v = test[f].astype(float).fillna(0).to_numpy() if f in test else None
        if v is None or np.all(v == v[0]):
            continue
        auc = roc_auc_score(y_te, v)
        single.append({"feature": f, "single_feature_auc": round(float(max(auc, 1 - auc)), 4)})
    single.sort(key=lambda r: -r["single_feature_auc"])
    gain = booster_full.feature_importance("gain")
    share = sorted(zip(full_cols, gain / max(1e-9, gain.sum())), key=lambda x: -x[1])
    leakage = {"top_single_feature_auc": single[:10],
               "top_gain_share": [{"feature": f, "share": round(float(s), 4)} for f, s in share[:8]],
               "flags": [r["feature"] for r in single if r["single_feature_auc"] >= 0.95]
               + [f for f, s in share if s >= 0.4]}

    # ---- 8. segment fairness + merchant fix ------------------------------------------------
    seg = test.join(customers[["division", "age_band", "kyc_level", "persona"]], on="sender")
    seg["tenure"] = np.where(seg.s_tenure_days < 90, "<90d", ">=90d")
    flag = full_actions != "ALLOW"
    warnf = full_actions == "WARN"
    prob = p["lgbm_graph"][te]
    fairness = {}
    for col in ("division", "age_band", "kyc_level", "persona", "tenure"):
        groups = {}
        for g, idx in seg.groupby(col).groups.items():
            i = np.asarray(seg.index.get_indexer(idx))
            yi = y_te[i]
            if (yi == 0).sum() < 200:
                continue
            groups[str(g)] = {"fpr": round(float(flag[i][yi == 0].mean()), 5),
                              "fnr": round(float((~flag[i])[yi == 1].mean()), 4) if (yi == 1).sum() >= 10 else None,
                              "warn_rate": round(float(warnf[i].mean()), 5),
                              "ece": round(_ece(yi, prob[i])[0], 5), "n": int(len(i)), "n_fraud": int(yi.sum())}
        fairness[col] = groups

    no_merchant = test.copy()
    no_merchant[["r_merchant_profile", "s_merchant_profile"]] = 0.0
    ctx_nm = Ctx(no_merchant, config_dir, iforest, quantiles)
    pol_txt = (config_dir / "policy.yaml").read_text(encoding="utf-8")
    tmp_dir = Path(tempfile.mkdtemp())
    (tmp_dir / "policy.yaml").write_text(pol_txt.replace('when: "s_merchant_profile == 1 and (is_new_recipient == 0 or type_code == 2)"', 'when: "false"'), encoding="utf-8")
    before_actions = policy_actions(ctx_nm, prob, th["lgbm_graph"], config_dir, policy_path=tmp_dir / "policy.yaml")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    merch_send = test.s_merchant_profile.to_numpy() == 1
    merch_recv = test.r_merchant_profile.to_numpy() == 1
    legit = y_te == 0

    def fpr(a, m):
        return round(float((a != "ALLOW")[m & legit].mean() * 100), 3) if (m & legit).any() else None

    def rec(a, m):
        return round(float((a != "ALLOW")[m & ~legit].mean()), 3) if (m & ~legit).any() else None

    merchant_fix = {
        "merchant_senders_fpr_pct": {"before": fpr(before_actions, merch_send), "after": fpr(full_actions, merch_send)},
        "payments_to_merchants_fpr_pct": {"before": fpr(before_actions, merch_recv), "after": fpr(full_actions, merch_recv)},
        "all_legit_fpr_pct": {"before": fpr(before_actions, np.ones_like(legit)), "after": fpr(full_actions, np.ones_like(legit))},
        "fraud_recall": {"before": rec(before_actions, np.ones_like(legit)), "after": rec(full_actions, np.ones_like(legit))},
        "elderly_65plus_fraud_recall": {
            "before": rec(before_actions, (seg.age_band == "65+").to_numpy()),
            "after": rec(full_actions, (seg.age_band == "65+").to_numpy())},
    }
    log("fairness done")

    # ---- 9. calibration before/after ---------------------------------------------------------
    raw_te = booster_full.predict(X_full[te])
    calibration = {"raw": {"ece": round(_ece(y_te, raw_te)[0], 5), "brier": round(float(brier_score_loss(y_te, raw_te)), 5)},
                   "platt": {"ece": round(_ece(y_te, prob)[0], 5), "brier": round(float(brier_score_loss(y_te, prob)), 5)},
                   "reliability_platt": _ece(y_te, prob)[1]}

    # ---- 7. harder synthetic data ------------------------------------------------------------
    prev = reports_dir / "evaluation.json"
    if hard:
        hard_res = run_hard(config_dir, seed, log)
    else:  # reuse the last hard-data run (it takes several minutes and does not depend on this data)
        hard_res = json.loads(prev.read_text(encoding="utf-8")).get("hard_data") if prev.exists() else None

    out = {"seed": seed, "test_days": n_days, "test_transactions": int(te.sum()), "ablation": systems,
           "cost": cost_opt, "lofo": lofo, "shift": shift, "adversarial_rounds": rounds, "leakage": leakage,
           "fairness": fairness, "merchant_fix": merchant_fix, "calibration": calibration, "hard_data": hard_res,
           "seconds": round(time.time() - started, 1)}
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "evaluation.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    (reports_dir / "evaluation.md").write_text(markdown(out), encoding="utf-8")
    return out


def run_hard(config_dir: Path, seed: int, log) -> dict:
    """Generate the overlapping ('hard') dataset, rebuild features, retrain and evaluate end to end."""
    from pipelines.build_features import build
    from pipelines.generate_data import generate
    from pipelines.train import train

    root = Path(tempfile.mkdtemp(prefix="shurokkha-hard-"))
    try:
        shutil.copytree(config_dir, root / "config")
        generate(root / "data" / "raw", 2000, 90, seed, hard=True)
        build(root / "data" / "raw", root / "data", verbose=False)
        res = train(root / "data", root / "registry", root / "config", root / "reports", seed=seed, verbose=False)
        m = res["metrics"]
        log("hard dataset trained")
        return {"model": m["model"], "system": {k: m["system"][k] for k in ("precision", "recall", "false_positive_rate", "alerts_per_day")},
                "lift_table": m["lift_table"], "per_scenario": m["per_scenario"],
                "victim_loss_flagged_share": m["business"]["victim_loss_flagged_share"],
                "fraud_rate": m["data"]["fraud_rate"]}
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ----------------------------------------------------------------------------- report
def _pct(v) -> str:
    return "–" if v is None else f"{v:.1%}"


def _ci(m: dict, k: str, pct: bool = True) -> str:
    ci = m.get("ci95", {}).get(k)
    if not ci:
        return ""
    return f" ({ci[0]:.1%}–{ci[1]:.1%})" if pct else f" ({ci[0]:.1f}–{ci[1]:.1f})"


def markdown(r: dict) -> str:
    L = ["# Evaluation evidence pack", "",
         f"Synthetic data, time-based split, test window = last {r['test_days']} days ({r['test_transactions']:,} transactions).",
         "Thresholds and calibration are learned on the validation window only. Brackets are bootstrap 95% confidence intervals.",
         "These numbers show method and relative value; production performance must come from shadow mode on real traffic.", "",
         "## 1. Ablation: what each layer adds", "",
         "| System | PR-AUC | Recall @ 1% FPR | Fraud flagged | Loss value caught | FP per 10k legit | HOLDs/day | Expected cost/day (৳) | ECE |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, m in r["ablation"].items():
        L.append(f"| {'**' + name + '**' if name.startswith('Full') else name} | {m['pr_auc']:.3f}{_ci(m, 'pr_auc')} | {m['recall_at_1pct_fpr']:.1%} | "
                 f"{m['recall_flagged']:.1%}{_ci(m, 'recall_flagged')} | {m['loss_value_caught']:.1%}{_ci(m, 'loss_value_caught')} | "
                 f"{m['fp_per_10k']:.1f}{_ci(m, 'fp_per_10k', False)} | {m['holds_per_day']} | {m['expected_cost_per_day_bdt']:,} | {m['ece']:.4f} |")
    L += ["", "**Marginal contribution** (each row compared with the row above):", "",
          "| Layer added | Fraud flagged | Mule-ring recall | Expected cost/day |", "|---|---|---|---|"]
    for name, m in r["ablation"].items():
        if "marginal" in m:
            d = m["marginal"]
            L.append(f"| {name} | {d['recall_flagged']:+.1%} | {d['mule_recall']:+.1%} | {d['expected_cost_per_day_bdt']:+,} ৳ |")
    L += ["", "Full Shurokkha's PR-AUC uses the fused score max(model, rules); its decisions come from the real policy engine",
          "(rules, model, graph, anomaly and agent cash-out detectors).", ""]
    c = r["cost"]
    cf = c["cost_function"]
    L += ["## 2. Cost function and cost-optimal thresholds", "",
          "`Cost = missed victim loss + (1 − warn_heeded) × warned victim loss + missed other fraud × ৳" + str(cf["other_fraud_missed"])
          + " + false WARN × ৳" + str(cf["fp_warn"]) + " + false HOLD × ৳" + str(cf["fp_hold"])
          + " + analyst minutes × ৳" + str(cf["analyst_cost_per_min"]) + "`", "",
          f"Assumptions: warn heeded {cf['warn_heeded']:.0%}, {cf['minutes_per_hold']} analyst minutes per HOLD, {cf['minutes_per_warn_alert']} per WARN alert.", "",
          "| Thresholds | warn_t | hold_t | Fraud flagged | FP per 10k | HOLDs/day | Expected cost/day (৳) |", "|---|---|---|---|---|---|---|"]
    for label, t, m in (("Learned (1% FPR / 90% precision)", c["learned_thresholds"], c["test_learned"]),
                        ("Cost-optimal (grid search on validation)", c["cost_optimal_thresholds"], c["test_cost_optimal"])):
        L.append(f"| {label} | {t['warn_t']:.3f} | {t['hold_t']:.3f} | {m['recall_flagged']:.1%} | {m['fp_per_10k']:.1f} | {m['holds_per_day']} | {m['expected_cost_per_day_bdt']:,} |")
    L += ["", "## 3. New fraud families (leave one family out of training)", "",
          "| Family never seen in training | Test cases | Model alone | Full system | Full-system FP per 10k |", "|---|---|---|---|---|"]
    for fam, v in r["lofo"].items():
        L.append(f"| {fam.replace('_', ' ')} | {v['n_test']} | {_pct(v['model_alone_recall'])} | {_pct(v['full_system_recall'])} | {v['full_system_fp_per_10k']:.1f} |")
    L += ["", "The gap between the two columns is what the rules, graph, anomaly and agent cash-out layers add for fraud the model has never seen.", "",
          "## 4. Distribution shift", "",
          "| Setting | Full-system recall | Model-only recall | Loss value caught | FP per 10k | ECE |", "|---|---|---|---|---|---|"]
    names = {"baseline_test": "Test window as generated", "temporal_first_half": "Earlier half of test window",
             "temporal_second_half": "Later half of test window", "covariate_shift": "Covariate shift (30% new users, 10% new phones, Eid amounts ×3)",
             "adversarial_drift": "Adversarial drift (smaller amounts, slower mules, old devices)"}
    for k, m in r["shift"].items():
        L.append(f"| {names[k]} | {m['recall_flagged']:.1%} | {m['model_recall']:.1%} | {m['loss_value_caught']:.1%} | {m['fp_per_10k']:.1f} | {m['ece']:.4f} |")
    L += ["", "Shifts are applied to the test features (a stress test of the decision layer), not by regenerating history.", "",
          "## 5. Adversarial rounds (attacker adapts, defender retrains)", "",
          "| Round | Attack | Recall under attack, before retrain | After retrain on the attack | FP per 10k after | Clean-data recall after |", "|---|---|---|---|---|---|"]
    for a in r["adversarial_rounds"]:
        L.append(f"| {a['round']} | {'moderate' if a['attack_strength'] == 1 else 'strong'} | {a['recall_before_retrain']:.1%} | {a['recall_after_retrain']:.1%} | {a['fp_per_10k_after']:.1f} | {a['clean_recall_after']:.1%} |")
    lk = r["leakage"]
    L += ["", "## 6. Leakage audit", "",
          "A feature that separates fraud from legitimate traffic on its own would be a generator 'tell'.", "",
          "| Feature | ROC-AUC alone |", "|---|---|"]
    L += [f"| {x['feature']} | {x['single_feature_auc']:.3f} |" for x in lk["top_single_feature_auc"][:8]]
    L += ["", "| Feature | Share of model gain |", "|---|---|"]
    L += [f"| {x['feature']} | {x['share']:.1%} |" for x in lk["top_gain_share"]]
    L += ["", f"Flagged (single-feature AUC ≥ 0.95 or gain share ≥ 40%): {', '.join(lk['flags']) if lk['flags'] else 'none'}.", ""]
    h = r.get("hard_data")
    if h:
        L += ["## 7. Harder synthetic data (overlapping behaviour)", "",
              "Legitimate users change phones (4×), replace SIMs, transact at night (2.5×) and send large one-off amounts;",
              "fraudsters copy normal amounts, 40% of takeovers use the victim's own phone, half of mules wait 2–12 hours.", "",
              "| Model (hard data) | PR-AUC | Recall @ 1% FPR |", "|---|---|---|"]
        for k, v in h["lift_table"].items():
            L.append(f"| {k.replace('_', ' ')} | {v['pr_auc']:.3f} | {v['recall_at_1pct_fpr']:.1%} |")
        s = h["system"]
        L += ["", f"Full system on hard data: precision {s['precision']:.1%}, recall {s['recall']:.1%}, FPR {s['false_positive_rate']:.2%}, "
              f"victim-loss value flagged {h['victim_loss_flagged_share']:.1%}.", "",
              "| Scenario | Flagged (hard data) |", "|---|---|"]
        L += [f"| {k} | {v['recall_flagged']:.0%} |" for k, v in h["per_scenario"].items()]
        L.append("")
    mf = r["merchant_fix"]
    L += ["## 8. Fairness by segment", "",
          "Constraint: equalise false-positive burden **without lowering recall for high-risk groups** (elderly, new users).", ""]
    for col, groups in r["fairness"].items():
        L += [f"**{col}**", "", "| Group | FPR | FNR | Warning rate | ECE | Transactions |", "|---|---|---|---|---|---|"]
        for g, v in groups.items():
            L.append(f"| {g} | {v['fpr']:.2%} | {_pct(v['fnr'])} | {v['warn_rate']:.2%} | {v['ece']:.4f} | {v['n']:,} |")
        L.append("")
    L += ["**Merchant-aware fix** (registered shops / online sellers). *Before* = the same system with merchant awareness switched off",
          "(graph fan-in, agent cash-out detector and the policy override); *after* = as deployed. HOLD rules are unchanged:", "",
          "| Measure | Before | After |", "|---|---|---|"]
    labels = {"merchant_senders_fpr_pct": "FPR, merchants as senders (%)", "payments_to_merchants_fpr_pct": "FPR, payments to merchants (%)",
              "all_legit_fpr_pct": "FPR, all legitimate (%)", "fraud_recall": "Fraud recall", "elderly_65plus_fraud_recall": "Fraud recall, age 65+"}
    for k, v in mf.items():
        L.append(f"| {labels[k]} | {v['before'] if v['before'] is not None else '–'} | {v['after'] if v['after'] is not None else '–'} |")
    k = r["calibration"]
    L += ["", "## 9. Calibration", "",
          f"ECE before calibration {k['raw']['ece']:.4f} (Brier {k['raw']['brier']:.4f}); after Platt scaling {k['platt']['ece']:.4f} (Brier {k['platt']['brier']:.4f}).", "",
          "| Predicted | n | Mean predicted | Observed fraud rate |", "|---|---|---|---|"]
    L += [f"| {b['range']} | {b['n']} | {b['mean_predicted']:.4f} | {b['observed_fraud_rate']:.4f} |" for b in k["reliability_platt"]]
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-hard", action="store_true")
    ap.add_argument("--boot", type=int, default=200)
    a = ap.parse_args()
    res = run(BACKEND / "data", BACKEND / "config", BACKEND / "reports", hard=not a.skip_hard, boot=a.boot)
    print(f"done in {res['seconds']}s -> reports/evaluation.md")
