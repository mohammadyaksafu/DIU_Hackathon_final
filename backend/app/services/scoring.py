"""Hot path: features -> detectors -> policy -> explanation -> persisted decision."""
from __future__ import annotations

import logging
import time
from contextlib import nullcontext
import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update

from app.core.cache import get_cache
from app.core.metrics import metrics
from app.db.database import session_scope
from app.db.models import Alert, AuditLog, IdempotencyRecord, ScoredTransaction
from app.detectors.base import ScoringContext
from app.explain.reason_codes import customer_message, select_reasons
from app.features.engine import TX_TYPES
from app.features.registry import build_features
from app.policy.engine import Decision
from app.services.drift import record_live_features
from app.services.state import AppState

logger = logging.getLogger(__name__)
WalletId = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")


class ScoreRequest(BaseModel):
    tx_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    type: Literal[tuple(TX_TYPES)] = "send_money"  # type: ignore[valid-type]
    amount: float = Field(gt=0, le=1_000_000)
    sender: str = WalletId
    receiver: str = WalletId
    device_id: str | None = Field(default=None, max_length=64)
    geo_cell: str | None = Field(default=None, max_length=16)
    channel: Literal["app", "ussd", "api"] = "app"
    ts: float | None = Field(default=None, description="Epoch seconds; defaults to the simulation clock")
    memo: str | None = Field(default=None, max_length=280, description="Untrusted free text; never interpreted")
    on_call: bool = Field(default=False, description="The app reports an active phone call (social-engineering signal)")


class SecurityEvent(BaseModel):
    wallet: str = WalletId
    event: Literal["sim_swap", "password_reset"]
    ts: float | None = None


def _signal_names(ctx: ScoringContext) -> tuple[dict, set[str]]:
    names = dict(ctx.features)
    for name, sig in ctx.signals.items():
        names[name] = sig.score if sig.ok else 0.0
    rules = ctx.signals.get("rules")
    hits = set(rules.details.get("hits", [])) if rules and rules.ok else set()
    return names, hits


def score_transaction(state: AppState, req: ScoreRequest, actor: str = "system", persist: bool = True,
                      idempotency_key: str | None = None) -> dict:
    key = idempotency_key or (f"tx:{req.tx_id}" if req.tx_id else None)
    if not (persist and key):
        return _score(state, req, actor, persist, None)
    # A retried request can land on another worker: claim the key across workers first, so one
    # transaction is never scored twice (two different decisions for the same transfer).
    with get_cache().lock(f"idem:{key}", timeout=10):
        with session_scope() as db:
            rec = db.get(IdempotencyRecord, key)
            if rec is not None:
                metrics.inc("idempotent_replays_total")
                return {**rec.response, "idempotent_replay": True}
        return _score(state, req, actor, persist, key)


def _score(state: AppState, req: ScoreRequest, actor: str, persist: bool, key: str | None) -> dict:
    started = time.perf_counter()
    tx = req.model_dump()
    tx["tx_id"] = req.tx_id or f"L{uuid.uuid4().hex[:15]}"
    tx["ts"] = float(req.ts) if req.ts else state.sim_now()

    state.sync_model()
    # Pin one model + detector set for the whole request: a hot swap mid-request can never
    # produce a decision that mixes two model versions.
    detectors, bundle, policy = state.detectors, state.bundle, state.policy
    ctx = ScoringContext(tx=tx, features={})
    scoring_error = None
    try:
        # In-process lock only for the in-memory engine; the Redis store is safe across threads and workers.
        with nullcontext() if state.shared_state else state.lock:
            ctx.features = build_features(state.engine, tx, state.graph.snapshot)
        detectors.run(ctx)
        names, rule_hits = _signal_names(ctx)
        decision = policy.decide(names, rule_hits)
        if decision.action != "ALLOW":
            detectors.explain(ctx)
    except Exception as exc:  # feature store / model unreachable: apply the configured failure policy
        logger.exception("scoring failed; applying on_scoring_error policy")
        metrics.inc("scoring_errors_total")
        scoring_error = type(exc).__name__
        decision = Decision(policy.on_scoring_error, "on_scoring_error", {}, [])
    shown = policy.apply_mode(decision.action)
    reasons = select_reasons(ctx.features, ctx.signals) if decision.action != "ALLOW" and not scoring_error else []
    latency_ms = (time.perf_counter() - started) * 1000

    failed = [n for n, s in ctx.signals.items() if not s.ok]
    degraded_reasons = list(state.degraded) + [f"detector:{n}" for n in failed]
    if scoring_error:
        degraded_reasons.append(f"scoring_error:{scoring_error}")
    if latency_ms > state.settings.latency_budget_ms:
        degraded_reasons.append("latency_budget_exceeded")
        metrics.inc("latency_budget_exceeded_total")
    lgbm = ctx.signals.get("lgbm")
    risk = lgbm.score if lgbm and lgbm.ok else max((s.score for s in ctx.signals.values() if s.ok), default=0.0)

    response = {
        "transaction_id": tx["tx_id"],
        "decision": shown,
        "policy_decision": decision.action,
        "mode": policy.mode,
        "risk_score": round(float(risk), 5),
        "signals": [{"detector": s.detector, "score": round(s.score, 5), "ok": s.ok, "reason_codes": s.reason_codes}
                    for s in ctx.signals.values()],
        "reason_codes": reasons,
        "customer_message": customer_message(shown, reasons, ctx.features),
        "model_version": bundle.version if bundle else "rules-only",
        "policy_version": policy.version,
        "policy": {"matched": decision.tier_expr, "variables": decision.variables, "overrides": decision.overrides_applied},
        "latency_ms": round(latency_ms, 2),
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
        "simulated_ts": tx["ts"],
    }

    metrics.observe_ms("score_latency_ms", latency_ms)
    metrics.inc("decisions_total", decision=decision.action)
    if degraded_reasons:
        metrics.inc("degraded_decisions_total")
    if not scoring_error:
        record_live_features(ctx.features)
    if persist:
        _persist(state, tx, ctx, response, actor, key)
    return response


def _persist(state: AppState, tx: dict, ctx: ScoringContext, response: dict, actor: str, key: str | None) -> None:
    with session_scope() as db:
        alert_id = None
        if response["policy_decision"] in ("WARN", "HOLD"):  # alerts record the policy decision, in every mode
            alert = Alert(
                tx_id=tx["tx_id"], tx_ts=tx["ts"], tx_type=tx["type"], sender=tx["sender"], receiver=tx["receiver"],
                amount=float(tx["amount"]), decision=response["policy_decision"], risk_score=response["risk_score"],
                reason_codes=response["reason_codes"],
                signals={n: s.model_dump() for n, s in ctx.signals.items()},
                features={k: v for k, v in ctx.features.items()}, model_version=response["model_version"],
                policy_version=response["policy_version"], source="shadow" if response["mode"] == "shadow" else "live",
            )
            db.add(alert)
            db.flush()
            alert_id = alert.id
            response["alert_id"] = alert_id
        stored_tx = {k: tx[k] for k in ("tx_id", "ts", "type", "amount", "sender", "receiver", "device_id", "geo_cell", "channel", "on_call")}
        db.add(ScoredTransaction(tx_id=tx["tx_id"], payload=stored_tx, decision=response["decision"],
                                   risk_score=response["risk_score"], alert_id=alert_id, latency_ms=response["latency_ms"]))
        db.add(AuditLog(actor=actor, event="decision", tx_id=tx["tx_id"], alert_id=alert_id,
                        payload={"decision": response["decision"], "policy_decision": response["policy_decision"],
                                 "mode": response["mode"], "risk": response["risk_score"],
                                 "model_version": response["model_version"], "policy_version": response["policy_version"],
                                 "reasons": response["reason_codes"], "degraded": response["degraded_reasons"]}))
        if key:
            db.add(IdempotencyRecord(key=key, response=response))  # key claimed under the idempotency lock


def ingest_committed(state: AppState, tx: dict) -> None:
    """A transaction that actually happened becomes history for future features."""
    with nullcontext() if state.shared_state else state.lock:  # Redis mode: per-wallet locks inside update()
        state.engine.update(tx)
        state.graph.add_edge(tx)


def confirm_transaction(state: AppState, tx_id: str, action: Literal["sent", "cancelled"], actor: str) -> dict:
    with session_scope() as db:
        st = db.get(ScoredTransaction, tx_id)
        if st is None:
            raise HTTPException(404, "unknown transaction")
        if st.status != "PENDING":
            return {"transaction_id": tx_id, "status": st.status, "unchanged": True}
        if action == "sent" and st.decision == "HOLD":
            raise HTTPException(409, "transaction is on hold pending analyst review")
        if not _transition(db, tx_id, "SENT" if action == "sent" else "CANCELLED"):
            # Another worker (a double-tap, or an analyst release) changed it first.
            db.rollback()
            return {"transaction_id": tx_id, "status": db.get(ScoredTransaction, tx_id).status, "unchanged": True}
        if st.alert_id:
            alert = db.get(Alert, st.alert_id)
            if alert:
                alert.customer_action = action
        db.add(AuditLog(actor=actor, event=f"customer_{action}", tx_id=tx_id, alert_id=st.alert_id,
                        payload={"decision": st.decision}))
        payload, decision = dict(st.payload), st.decision
    if action == "sent":
        ingest_committed(state, payload)
    elif decision in ("WARN", "HOLD"):
        metrics.inc("scams_averted_total")
    metrics.inc("customer_actions_total", action=action, decision=decision)
    return {"transaction_id": tx_id, "status": "SENT" if action == "sent" else "CANCELLED", "decision": decision}


def _transition(db, tx_id: str, new_status: str) -> bool:
    """PENDING -> SENT/CANCELLED as one conditional UPDATE (optimistic lock).

    Two workers acting on the same transfer at once (customer cancels while an analyst releases)
    cannot both win: exactly one UPDATE matches the PENDING row, so money is never both sent and cancelled.
    """
    res = db.execute(update(ScoredTransaction).where(ScoredTransaction.tx_id == tx_id, ScoredTransaction.status == "PENDING")
                     .values(status=new_status).execution_options(synchronize_session=False))
    return res.rowcount == 1


def release_held(state: AppState, alert: Alert) -> bool:
    """Analyst marked a held transaction legitimate: complete it."""
    with session_scope() as db:
        st = db.get(ScoredTransaction, alert.tx_id)
        if st is None or st.status != "PENDING" or not _transition(db, alert.tx_id, "SENT"):
            return False  # already cancelled by the customer, or released by another analyst
        payload = dict(st.payload)
    ingest_committed(state, payload)
    return True


def ingest_event(state: AppState, ev: SecurityEvent, actor: str) -> dict:
    ts = float(ev.ts) if ev.ts else state.sim_now()
    with state.lock:
        state.engine.ingest_event({"wallet": ev.wallet, "event": ev.event, "ts": ts})
    with session_scope() as db:
        db.add(AuditLog(actor=actor, event=f"security_{ev.event}", payload={"wallet": ev.wallet, "ts": ts}))
    return {"wallet": ev.wallet, "event": ev.event, "ts": ts}
