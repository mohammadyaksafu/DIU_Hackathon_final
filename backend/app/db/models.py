"""Persistent tables: alerts/cases, feedback, scored transactions, audit log, idempotency, narratives."""
from __future__ import annotations

import time

from sqlalchemy import JSON, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> float:
    return time.time()


class Alert(Base):
    """An alert is created for every WARN/HOLD decision; analysts work it as a case."""

    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tx_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    tx_ts: Mapped[float] = mapped_column(Float)
    tx_type: Mapped[str] = mapped_column(String(32))
    sender: Mapped[str] = mapped_column(String(32), index=True)
    receiver: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    risk_score: Mapped[float] = mapped_column(Float, index=True)
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(64), default="")
    policy_version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)  # OPEN|INVESTIGATING|RESOLVED|DISPUTED
    label: Mapped[str | None] = mapped_column(String(16), nullable=True)  # fraud|legit|unsure
    customer_action: Mapped[str | None] = mapped_column(String(16), nullable=True)  # sent|cancelled
    source: Mapped[str] = mapped_column(String(16), default="live")  # live|seed
    scenario_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)  # synthetic ground truth (seed only)
    opened_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Customer appeal ("this wasn't fraud"): jumps the analyst queue, answered within the SOP-05 SLA.
    appealed_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    appeal_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_alerts_status_risk", "status", "risk_score"),)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    analyst: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=_now)


class ScoredTransaction(Base):
    """Every scored request; the customer later confirms (sent) or cancels it."""

    __tablename__ = "scored_transactions"
    tx_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    payload: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)  # PENDING|SENT|CANCELLED
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)


class AuditLog(Base):
    """Append-only record of every decision and analyst action."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[float] = mapped_column(Float, default=_now, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    event: Mapped[str] = mapped_column(String(48), index=True)
    tx_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    response: Mapped[dict] = mapped_column(JSON)


class Narrative(Base):
    """Cached AI case summaries keyed by evidence hash."""

    __tablename__ = "narratives"
    evidence_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    provider: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict] = mapped_column(JSON)


class StudyResponse(Base):
    """One decision in the WARN user study (anonymous; participant is a random code)."""

    __tablename__ = "study_responses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    participant: Mapped[str] = mapped_column(String(32), index=True)
    arm: Mapped[str] = mapped_column(String(1), index=True)  # A no warning | B generic | C Shurokkha
    scenario: Mapped[str] = mapped_column(String(32))
    is_scam: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))  # sent | cancelled
    seconds: Mapped[float] = mapped_column(Float)
    trust: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 self-reported
