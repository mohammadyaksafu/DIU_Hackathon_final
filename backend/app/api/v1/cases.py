"""Analyst console: alert queue, case detail, status, feedback, AI case summary, SOP Q&A."""
from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import get_copilot, state_dep
from app.core.security import Principal, require_roles
from app.db.database import session_scope
from app.db.models import Alert, AuditLog, Feedback, Narrative
from app.explain.reason_codes import render_reason
from app.genai.copilot import build_evidence, evidence_hash
from app.services.scoring import release_held
from app.services.state import AppState

router = APIRouter(tags=["cases"])
STATUSES = ("OPEN", "INVESTIGATING", "RESOLVED", "DISPUTED")


def _summary(a: Alert) -> dict:
    return {
        "id": a.id, "tx_id": a.tx_id, "created_at": a.created_at, "tx_ts": a.tx_ts, "tx_type": a.tx_type,
        "sender": a.sender, "receiver": a.receiver, "amount": a.amount, "decision": a.decision,
        "risk_score": a.risk_score, "reason_codes": a.reason_codes, "status": a.status, "label": a.label,
        "customer_action": a.customer_action, "source": a.source,
        "appealed_at": a.appealed_at, "appeal_note": a.appeal_note,
    }


@router.get("/alerts")
def list_alerts(
    status: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    appealed: bool = Query(default=False, description="Only cases the customer appealed"),
    q: str | None = Query(default=None, max_length=32),
    sort: Literal["risk", "newest"] = "risk",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=100),
    p: Principal = Depends(require_roles("analyst")),
) -> dict:
    with session_scope() as db:
        stmt = select(Alert)
        if status:
            stmt = stmt.where(Alert.status.in_(status.split(",")))
        if decision:
            stmt = stmt.where(Alert.decision.in_(decision.split(",")))
        if appealed:
            stmt = stmt.where(Alert.appealed_at.is_not(None))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Alert.sender.like(like), Alert.receiver.like(like), Alert.tx_id.like(like)))
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        # Open customer appeals come first (SLA), then the chosen order.
        appeal_first = (Alert.appealed_at.is_(None)) | (Alert.label.is_not(None))
        order = (appeal_first, Alert.risk_score.desc(), Alert.id.desc()) if sort == "risk" else (appeal_first, Alert.created_at.desc(), Alert.id.desc())
        rows = db.scalars(stmt.order_by(*order).offset((page - 1) * size).limit(size)).all()
        return {"total": total, "page": page, "size": size, "items": [_summary(a) for a in rows]}


def _load(db, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return alert


def _related(db, alert: Alert) -> dict:
    rows = db.scalars(
        select(Alert).where(Alert.id != alert.id, or_(Alert.receiver == alert.receiver, Alert.sender == alert.sender,
                                                      Alert.sender == alert.receiver))
        .order_by(Alert.tx_ts.desc()).limit(20)
    ).all()
    return {
        "count": len(rows),
        "same_receiver": sum(1 for r in rows if r.receiver == alert.receiver),
        "total_amount_bdt": round(sum(r.amount for r in rows)),
        "confirmed_fraud": sum(1 for r in rows if r.label == "fraud"),
        "items": [_summary(r) for r in rows[:10]],
    }


@router.get("/cases/{alert_id}")
def case_detail(alert_id: int, state: AppState = Depends(state_dep), p: Principal = Depends(require_roles("analyst"))) -> dict:
    with session_scope() as db:
        alert = _load(db, alert_id)
        if alert.opened_at is None:
            alert.opened_at = time.time()
        related = _related(db, alert)
        audit = db.scalars(select(AuditLog).where(or_(AuditLog.alert_id == alert.id, AuditLog.tx_id == alert.tx_id))
                           .order_by(AuditLog.ts)).all()
        feats = alert.features or {}
        return {
            **_summary(alert),
            "signals": alert.signals,
            "features": feats,
            "model_version": alert.model_version,
            "policy_version": alert.policy_version,
            "reasons": [{"code": c, "en": render_reason(c, feats, "en"), "bn": render_reason(c, feats, "bn")} for c in alert.reason_codes],
            "sender_profile": {**state.customer_profile(alert.sender), **state.engine.wallet_summary(alert.sender)},
            "receiver_profile": {**state.customer_profile(alert.receiver), **state.engine.wallet_summary(alert.receiver)},
            "related": related,
            "audit": [{"ts": a.ts, "actor": a.actor, "event": a.event, "payload": a.payload} for a in audit],
            "opened_at": alert.opened_at,
            "decided_at": alert.decided_at,
            "ground_truth_scenario": alert.scenario_tag if alert.source == "seed" else None,
        }


class StatusUpdate(BaseModel):
    status: Literal[STATUSES]  # type: ignore[valid-type]


@router.patch("/cases/{alert_id}/status")
def update_status(alert_id: int, body: StatusUpdate, p: Principal = Depends(require_roles("analyst"))) -> dict:
    with session_scope() as db:
        alert = _load(db, alert_id)
        old = alert.status
        alert.status = body.status
        db.add(AuditLog(actor=p.username, event="status_change", alert_id=alert_id, tx_id=alert.tx_id,
                        payload={"from": old, "to": body.status}))
        return _summary(alert)


class FeedbackRequest(BaseModel):
    label: Literal["fraud", "legit", "unsure"]
    notes: str = Field(default="", max_length=2000)


@router.post("/cases/{alert_id}/feedback")
def feedback(alert_id: int, body: FeedbackRequest, state: AppState = Depends(state_dep),
             p: Principal = Depends(require_roles("analyst"))) -> dict:
    """Analyst label: resolves the case; 'legit' on a HOLD completes the transfer. Labels feed retraining."""
    with session_scope() as db:
        alert = _load(db, alert_id)
        alert.label = body.label
        alert.status = "RESOLVED" if body.label != "unsure" else "INVESTIGATING"
        alert.decided_at = time.time()
        if alert.opened_at is None:
            alert.opened_at = alert.decided_at
        db.add(Feedback(alert_id=alert_id, analyst=p.username, label=body.label, notes=body.notes))
        db.add(AuditLog(actor=p.username, event="feedback", alert_id=alert_id, tx_id=alert.tx_id,
                        payload={"label": body.label, "notes": body.notes[:200]}))
        snapshot = _summary(alert)
        decision = alert.decision
    released = False
    if body.label == "legit" and decision == "HOLD":
        with session_scope() as db:
            released = release_held(state, db.get(Alert, alert_id))
    return {**snapshot, "released": released}


@router.post("/copilot/case-summary/{alert_id}")
def case_summary(alert_id: int, refresh: bool = False, state: AppState = Depends(state_dep),
                 p: Principal = Depends(require_roles("analyst"))) -> dict:
    copilot = get_copilot()
    with session_scope() as db:
        alert = _load(db, alert_id)
        related = _related(db, alert)
        related.pop("items", None)
        graph_info = state.graph.snapshot.get(alert.receiver if alert.tx_type != "cash_out" else alert.sender)
        sop = copilot.sop_for_reasons(alert.reason_codes, alert.decision)
        evidence = build_evidence(alert, related, graph_info, state.customer_profile(alert.sender),
                                  state.customer_profile(alert.receiver), sop)
        key = evidence_hash(evidence, copilot.gateway.model)
        cached = None if refresh else db.get(Narrative, key)
        if cached is not None:
            return {**cached.content, "cached": True, "evidence": evidence}
    result = copilot.case_summary(evidence)
    if result.get("source") == "llm":
        with session_scope() as db:
            db.merge(Narrative(evidence_hash=key, alert_id=alert_id, provider=copilot.gateway.provider, content=result))
            db.add(AuditLog(actor=p.username, event="ai_case_summary", alert_id=alert_id, payload={"provider": copilot.gateway.provider}))
    return {**result, "cached": False, "evidence": evidence}


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    page_context: str = Field(default="", max_length=160)
    alert_id: int | None = Field(default=None, ge=1)


@router.post("/copilot/ask")
def ask(body: AskRequest, p: Principal = Depends(require_roles("analyst"))) -> dict:
    return get_copilot().ask(body.question)


@router.post("/copilot/chat")
def chat(body: ChatRequest, state: AppState = Depends(state_dep),
         p: Principal = Depends(require_roles("analyst", "customer"))) -> dict:
    copilot = get_copilot()
    evidence = None
    analyst_context = p.role in ("analyst", "admin")
    if body.alert_id is not None and not analyst_context:
        raise HTTPException(403, "Case context is only available to analysts")
    if body.alert_id is not None:
        with session_scope() as db:
            alert = _load(db, body.alert_id)
            related = _related(db, alert)
            related.pop("items", None)
            graph_info = state.graph.snapshot.get(alert.receiver if alert.tx_type != "cash_out" else alert.sender)
            sop = copilot.sop_for_reasons(alert.reason_codes, alert.decision)
            evidence = build_evidence(
                alert, related, graph_info, state.customer_profile(alert.sender),
                state.customer_profile(alert.receiver), sop,
            )
    turns = [turn.model_dump() for turn in body.history]
    return copilot.chat(body.message, turns, body.page_context, evidence, allow_sop=analyst_context)
