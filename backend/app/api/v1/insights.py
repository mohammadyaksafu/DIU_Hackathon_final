"""Graph view and impact dashboard metrics."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import get_gateway, state_dep
from app.core.cache import get_cache
from app.core.metrics import metrics
from app.core.security import Principal, require_roles
from app.db.database import session_scope
from app.db.models import Alert, ScoredTransaction
from app.services.drift import drift_report
from app.services.state import AppState

router = APIRouter(tags=["insights"])

# Assumptions behind the impact estimates. They are stated, not measured: a pilot must measure them.
WARN_HEEDED_RANGE = (0.4, 0.6, 0.8)  # share of warned victims who cancel (low, central, high)
MINUTES_PER_CASE_MANUAL = 15.0  # analyst gathers history, network and SOP by hand (SOP-05 review target)
MINUTES_PER_CASE_COPILOT = 6.0  # evidence pack, ring graph, reason codes and AI summary prepared
PRODUCTIVE_HOURS_PER_ANALYST_DAY = 6.0
ANALYST_COST_PER_MIN = 8.0  # BDT, loaded cost
FP_FRICTION_BDT = 50.0  # average cost of flagging a legitimate transfer (warning or delay)
INFRA_COST_PER_DAY = 1500.0  # BDT: API, database, Redis, monitoring (two small servers)


def _net(hold_d: float, warn_d: float, fp_d: float, alerts_d: float, cancel: float = 0.6, base: float = 1.0,
         fp_cost: float = FP_FRICTION_BDT) -> float:
    prevented = base * (hold_d + cancel * warn_d)
    cost = fp_d * fp_cost + alerts_d * MINUTES_PER_CASE_COPILOT * ANALYST_COST_PER_MIN + INFRA_COST_PER_DAY
    return prevented - cost


def _roi(hold_d: float, warn_d: float, fp_d: float, alerts_d: float) -> dict:
    """Net benefit per day and a one-at-a-time sensitivity (tornado) over the uncertain inputs."""
    central = _net(hold_d, warn_d, fp_d, alerts_d)
    cost_d = fp_d * FP_FRICTION_BDT + alerts_d * MINUTES_PER_CASE_COPILOT * ANALYST_COST_PER_MIN + INFRA_COST_PER_DAY
    tornado = [
        {"input": "Warned victims who cancel", "low_label": "20%", "high_label": "90%",
         "low": round(_net(hold_d, warn_d, fp_d, alerts_d, cancel=0.2)), "high": round(_net(hold_d, warn_d, fp_d, alerts_d, cancel=0.9))},
        {"input": "Fraud base rate", "low_label": "×0.5", "high_label": "×2",
         "low": round(_net(hold_d, warn_d, fp_d, alerts_d, base=0.5)), "high": round(_net(hold_d, warn_d, fp_d, alerts_d, base=2.0))},
        {"input": "Cost of a false alarm", "low_label": "৳200", "high_label": "৳20",
         "low": round(_net(hold_d, warn_d, fp_d, alerts_d, fp_cost=200)), "high": round(_net(hold_d, warn_d, fp_d, alerts_d, fp_cost=20))},
    ]
    tornado.sort(key=lambda t: -(t["high"] - t["low"]))
    if hold_d >= cost_d:
        break_even = "Pays for itself at any cancel rate: held transfers alone cover the running cost."
        break_even_rate = 0.0
    else:
        break_even_rate = round((cost_d - hold_d) / warn_d, 3) if warn_d > 0 else None
        break_even = f"Pays for itself if more than {break_even_rate:.0%} of warned victims cancel." if break_even_rate is not None else "n/a"
    return {"net_benefit_per_day_bdt": round(central), "running_cost_per_day_bdt": round(cost_d),
            "roi_multiple": round((central + cost_d) / cost_d, 1) if cost_d else None,
            "break_even": break_even, "break_even_cancel_rate": break_even_rate, "tornado": tornado,
            "assumptions": {"false_alarm_cost_bdt": FP_FRICTION_BDT, "analyst_cost_per_min_bdt": ANALYST_COST_PER_MIN,
                            "minutes_per_case": MINUTES_PER_CASE_COPILOT, "infra_cost_per_day_bdt": INFRA_COST_PER_DAY}}


def impact_estimates(offline: dict) -> dict:
    """Loss prevented as a range over the warning-heeded assumption, and analyst time per day."""
    business, system = offline.get("business") or {}, offline.get("system") or {}
    if not business or not system:
        return {}
    flagged = float(business["victim_loss_flagged_bdt"])
    central_rate = float(business["assumptions"]["warn_heeded_rate"])
    # Training stores HOLD + rate x WARN; split it back into the two parts.
    warn_loss = (flagged - float(business["estimated_prevented_bdt"])) / max(1e-9, 1.0 - central_rate)
    hold_loss = flagged - warn_loss
    low, mid, high = (round(hold_loss + r * warn_loss) for r in WARN_HEEDED_RANGE)
    alerts = float(system["alerts_per_day"])
    manual_h = alerts * MINUTES_PER_CASE_MANUAL / 60
    copilot_h = alerts * MINUTES_PER_CASE_COPILOT / 60
    days = max(1, int(system.get("test_days") or 1))
    roi = _roi(hold_loss / days, warn_loss / days, float(business.get("legit_customers_warned_per_day", 0)), alerts)
    return {
        "roi": roi,
        "loss_prevented_bdt": {"low": low, "central": mid, "high": high, "warn_heeded_range": list(WARN_HEEDED_RANGE),
                               "held_share_of_flagged_loss": round(hold_loss / max(1.0, flagged), 4),
                               "test_days": system.get("test_days")},
        "analyst_workload": {
            "alerts_per_day": alerts,
            "minutes_per_case": {"manual": MINUTES_PER_CASE_MANUAL, "with_copilot": MINUTES_PER_CASE_COPILOT},
            "analyst_hours_per_day": {"manual": round(manual_h, 1), "with_copilot": round(copilot_h, 1)},
            "hours_saved_per_day": round(manual_h - copilot_h, 1),
            "analysts_needed": {"manual": round(manual_h / PRODUCTIVE_HOURS_PER_ANALYST_DAY, 1),
                                "with_copilot": round(copilot_h / PRODUCTIVE_HOURS_PER_ANALYST_DAY, 1)},
        },
        "note": "Assumptions, not measurements: warning-heeded rate and minutes per case must be measured in a pilot. "
                "HOLD is assumed to stop the loss, which holds only while analysts do not release fraud (HOLD precision "
                f"{system.get('hold_precision', 0):.1%} on the test window).",
    }


@router.get("/graph/wallet/{wallet_id}")
def wallet_graph(wallet_id: str, hops: int = Query(default=2, ge=1, le=3), state: AppState = Depends(state_dep),
                 p: Principal = Depends(require_roles("analyst"))) -> dict:
    cache = get_cache()
    key = f"graph:{wallet_id}:{hops}:{state.graph.snapshot_built_at}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    result = state.graph.subgraph(wallet_id, hops=hops)
    cache.set(key, result, ttl=60)
    return result


def _evidence_labels() -> dict:
    """What is measured on this server vs what is simulated / estimated (shown side by side)."""
    from app.api.v1.study import results as study_results
    from app.core.security import Principal as _P

    study = study_results(_P(username="system", role="analyst"))
    c = study["arms"]["C"]
    return {
        "measured": [
            {"metric": "Scoring latency p50 / p95 / p99 (ms)", "value": [metrics.percentile("score_latency_ms", q) for q in (0.5, 0.95, 0.99)]},
            {"metric": "WARN user study: scam-cancel rate, Shurokkha warning", "value": c["scam_cancel_rate"],
             "ci95": c["scam_cancel_ci95"], "n": c["scam_decisions"], "status": study["status"]},
            {"metric": "WARN user study: participants", "value": study["participants"]},
        ],
        "simulated": ["Loss prevented (synthetic test window)", "Analyst hours saved", "Net benefit and ROI", "Model and system metrics"],
    }


@router.get("/metrics/impact")
def impact(state: AppState = Depends(state_dep), p: Principal = Depends(require_roles("analyst"))) -> dict:
    offline = state.bundle.metrics if state.bundle else {}
    with session_scope() as db:
        by_decision = dict(db.execute(select(ScoredTransaction.decision, func.count()).group_by(ScoredTransaction.decision)).all())
        by_status = dict(db.execute(select(Alert.status, func.count()).group_by(Alert.status)).all())
        labelled = db.execute(select(Alert.decision, Alert.label, func.count()).where(Alert.label.is_not(None))
                              .group_by(Alert.decision, Alert.label)).all()
        cancelled = db.scalar(select(func.count()).select_from(Alert).where(Alert.customer_action == "cancelled")) or 0
        protected = db.scalar(select(func.coalesce(func.sum(Alert.amount), 0)).where(Alert.customer_action == "cancelled")) or 0
        ttd = db.execute(select(Alert.decided_at - Alert.opened_at).where(Alert.decided_at.is_not(None), Alert.opened_at.is_not(None))).scalars().all()
        alerts_total = db.scalar(select(func.count()).select_from(Alert)) or 0

    label_stats: dict = {}
    for decision, label, n in labelled:
        label_stats.setdefault(decision, {})[label] = n
    precision = {}
    for decision, counts in label_stats.items():
        decided = counts.get("fraud", 0) + counts.get("legit", 0)
        precision[decision] = round(counts.get("fraud", 0) / decided, 4) if decided else None
    ttd_sorted = sorted(t for t in ttd if t is not None and t >= 0)

    return {
        "model_version": state.bundle.version if state.bundle else "rules-only",
        "offline": offline,
        "estimates": impact_estimates(offline),
        "evidence": _evidence_labels(),
        "live": {
            "scored_by_decision": by_decision,
            "alerts_total": alerts_total,
            "alerts_by_status": by_status,
            "analyst_labels": label_stats,
            "analyst_confirmed_precision": precision,
            "scams_averted": int(cancelled),
            "amount_protected_bdt": float(protected),
            "median_time_to_decision_s": round(ttd_sorted[len(ttd_sorted) // 2], 1) if ttd_sorted else None,
            "decisions_this_process": metrics.counters_by_label("decisions_total", "decision"),
        },
        "latency_ms": {
            "p50": metrics.percentile("score_latency_ms", 0.50),
            "p95": metrics.percentile("score_latency_ms", 0.95),
            "p99": metrics.percentile("score_latency_ms", 0.99),
        },
        "system": {
            "degraded": state.degraded,
            "llm": get_gateway().status(),
            "cache_backend": get_cache().backend,
            "policy_version": state.policy.version,
            "detectors": state.detectors.names if state.detectors else [],
        },
    }


@router.get("/metrics/drift")
def drift(p: Principal = Depends(require_roles("analyst"))) -> dict:
    """PSI of live features against the training window (retraining trigger)."""
    return drift_report()
