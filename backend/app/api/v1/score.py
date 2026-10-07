"""Scoring, customer confirmation, security events, batch scoring."""
from __future__ import annotations

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import state_dep
from app.core.security import Principal, require_roles
from app.services.scoring import ScoreRequest, SecurityEvent, confirm_transaction, ingest_event, score_transaction
from app.services.state import AppState

router = APIRouter(tags=["scoring"])
MAX_BATCH = 1000


@router.post("/score")
def score(req: ScoreRequest, idempotency_key: str | None = Header(default=None, max_length=128),
          state: AppState = Depends(state_dep), p: Principal = Depends(require_roles("customer", "analyst"))) -> dict:
    """Score one transaction in real time (idempotent via Idempotency-Key header or tx_id)."""
    return score_transaction(state, req, actor=p.username, idempotency_key=idempotency_key)


class ConfirmRequest(BaseModel):
    action: Literal["sent", "cancelled"]


@router.post("/transactions/{tx_id}/confirm")
def confirm(tx_id: str, body: ConfirmRequest, state: AppState = Depends(state_dep),
            p: Principal = Depends(require_roles("customer"))) -> dict:
    """Customer decision after seeing the result. Only sent transfers become history."""
    return confirm_transaction(state, tx_id, body.action, p.username)


class AppealRequest(BaseModel):
    note: str = Field(default="", max_length=500, description="Customer's own words; untrusted, shown to the analyst only")


APPEAL_SLA_MINUTES = 15  # SOP-05 review target


@router.post("/transactions/{tx_id}/appeal")
def appeal(tx_id: str, body: AppealRequest, p: Principal = Depends(require_roles("customer"))) -> dict:
    """'This wasn't fraud': the case jumps the analyst queue. A 'legit' label releases a HOLD and the
    label is stored as feedback for retraining."""
    import time

    from app.db.database import session_scope
    from app.db.models import Alert, AuditLog, ScoredTransaction

    with session_scope() as db:
        st = db.get(ScoredTransaction, tx_id)
        if st is None or st.alert_id is None:
            raise HTTPException(404, "no flagged transaction with this id")
        alert = db.get(Alert, st.alert_id)
        if alert.label is not None:
            return {"transaction_id": tx_id, "status": "already_reviewed", "label": alert.label}
        if alert.appealed_at is None:
            alert.appealed_at = time.time()
            alert.appeal_note = body.note.strip() or None
            if alert.status == "OPEN":
                alert.status = "INVESTIGATING"
            db.add(AuditLog(actor=p.username, event="customer_appeal", tx_id=tx_id, alert_id=alert.id,
                            payload={"note": body.note[:200]}))
        return {"transaction_id": tx_id, "alert_id": alert.id, "status": "appealed", "appealed_at": alert.appealed_at,
                "sla_minutes": APPEAL_SLA_MINUTES}


@router.post("/events")
def security_event(ev: SecurityEvent, state: AppState = Depends(state_dep),
                   p: Principal = Depends(require_roles("customer", "analyst"))) -> dict:
    """Ingest SIM-swap / password-reset events (from telco or auth systems)."""
    return ingest_event(state, ev, p.username)


class BatchRequest(BaseModel):
    transactions: list[ScoreRequest] = Field(max_length=MAX_BATCH)


def _batch(state: AppState, items: list[ScoreRequest]) -> dict:
    results = [score_transaction(state, r, persist=False) for r in items]
    slim = [{k: r[k] for k in ("transaction_id", "decision", "risk_score", "reason_codes", "latency_ms")} for r in results]
    counts = {d: sum(1 for r in results if r["decision"] == d) for d in ("ALLOW", "WARN", "HOLD")}
    return {"count": len(results), "decisions": counts, "results": slim}


@router.post("/score/batch")
def score_batch(body: BatchRequest, state: AppState = Depends(state_dep),
                p: Principal = Depends(require_roles("analyst"))) -> dict:
    """Score up to 1,000 transactions without side effects (what-if / back-testing)."""
    return _batch(state, body.transactions)


@router.post("/score/batch/csv")
async def score_batch_csv(file: UploadFile = File(...), state: AppState = Depends(state_dep),
                          p: Principal = Depends(require_roles("analyst"))) -> dict:
    """CSV with columns: type,amount,sender,receiver[,device_id,geo_cell,channel,tx_id]."""
    raw = await file.read(5_000_000)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    items, errors = [], []
    for i, row in enumerate(reader):
        if len(items) >= MAX_BATCH:
            break
        try:
            items.append(ScoreRequest(**{k: v for k, v in row.items() if v not in (None, "")}))
        except ValidationError as exc:
            errors.append({"row": i + 2, "error": exc.errors()[0]["msg"]})
    if not items:
        raise HTTPException(422, {"message": "no valid rows", "errors": errors[:20]})
    return {**_batch(state, items), "errors": errors[:50]}
