"""WARN user study: measures, instead of assuming, how many people cancel a scam after a warning.

Three arms, assigned in balance: A no warning, B a generic warning, C the Shurokkha explained Bangla
warning. Each participant sees the same scripted transfers (scams mixed with legitimate payments).
We record cancel/continue, time to decide and self-reported trust. Anonymous: a random code only.
Protocol and consent text: docs/USER_STUDY.md.
"""
from __future__ import annotations

import math
import secrets
import statistics
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.security import Principal, require_roles
from app.db.database import session_scope
from app.db.models import StudyResponse

router = APIRouter(prefix="/study", tags=["user study"])
ARMS = ("A", "B", "C")

# Scripted transfers. `reasons_bn` is what arm C shows; arm B shows one generic line; arm A nothing.
SCENARIOS = [
    {"key": "prize_fee", "is_scam": True, "context_bn": "ফোনে একজন বলছে আপনি ৫০,০০০ টাকার লটারি জিতেছেন, পুরস্কার পেতে ২,০০০ টাকা ফি পাঠাতে হবে।",
     "receiver": "01XXXXXX913 (নতুন নম্বর)", "amount": 2000,
     "reasons_bn": ["আপনি আগে কখনো এই নম্বরে টাকা পাঠাননি।", "গত ২৪ ঘণ্টায় ১১ জন নতুন মানুষ এই নম্বরে টাকা পাঠিয়েছেন।",
                    "upay কখনো পুরস্কার পেতে ফি চায় না।"]},
    {"key": "family_rent", "is_scam": False, "context_bn": "প্রতি মাসের মতো মাকে বাসা ভাড়ার টাকা পাঠাচ্ছেন।",
     "receiver": "মা (পরিচিত নম্বর)", "amount": 3000, "reasons_bn": []},
    {"key": "wrong_send_refund", "is_scam": True, "context_bn": "অপরিচিত নম্বর থেকে ৫০০ টাকা এসেছে, এখন ফোন করে বলছে 'ভুল করে ৫,০০০ পাঠিয়েছি, ফেরত দিন'।",
     "receiver": "01XXXXXX447 (নতুন নম্বর)", "amount": 5000,
     "reasons_bn": ["যে টাকা এসেছে (৫০০) তার চেয়ে অনেক বেশি ফেরত চাওয়া হচ্ছে।", "আপনি আগে কখনো এই নম্বরে টাকা পাঠাননি।"]},
    {"key": "shop_payment", "is_scam": False, "context_bn": "পাড়ার মুদি দোকানে মাসের বাজারের দাম দিচ্ছেন।",
     "receiver": "রহিম স্টোর (দোকান)", "amount": 1200, "reasons_bn": []},
    {"key": "account_block_otp", "is_scam": True, "context_bn": "'upay অফিস' থেকে ফোন: অ্যাকাউন্ট বন্ধ হয়ে যাবে, এখনই একটি নম্বরে ৮,০০০ টাকা পাঠিয়ে যাচাই করুন।",
     "receiver": "01XXXXXX208 (নতুন নম্বর)", "amount": 8000,
     "reasons_bn": ["এই পরিমাণ আপনার সাধারণ লেনদেনের চেয়ে প্রায় ৬ গুণ বেশি।", "নতুন নম্বরে টাকা পাঠানোর সময় আপনি ফোনে কথা বলছেন।",
                    "upay কখনো ফোনে টাকা পাঠিয়ে অ্যাকাউন্ট যাচাই করতে বলে না।"]},
    {"key": "new_seller", "is_scam": False, "context_bn": "ফেসবুক পেজ থেকে প্রথমবার একটি জামা কিনছেন, বিক্রেতা পরিচিত বন্ধুর সুপারিশ করা।",
     "receiver": "01XXXXXX562 (নতুন নম্বর, অনলাইন বিক্রেতা)", "amount": 900,
     "reasons_bn": ["আপনি আগে কখনো এই নম্বরে টাকা পাঠাননি।"]},
]
GENERIC_WARNING_BN = "সতর্কতা: অপরিচিত কাউকে টাকা পাঠানোর আগে যাচাই করুন।"


@router.get("/scenarios")
def scenarios(p: Principal = Depends(require_roles("customer"))) -> dict:
    return {"arms": {"A": "no warning", "B": "generic warning", "C": "Shurokkha explained warning"},
            "generic_warning_bn": GENERIC_WARNING_BN, "scenarios": SCENARIOS}


@router.post("/participants")
def enrol(p: Principal = Depends(require_roles("customer"))) -> dict:
    """New anonymous participant, assigned to the arm with the fewest participants (balanced)."""
    with session_scope() as db:
        counts = dict(db.execute(select(StudyResponse.arm, func.count(func.distinct(StudyResponse.participant)))
                                 .group_by(StudyResponse.arm)).all())
    arm = min(ARMS, key=lambda a: (counts.get(a, 0), secrets.randbelow(100)))
    return {"participant": "P" + secrets.token_hex(4), "arm": arm}


class Response(BaseModel):
    participant: str = Field(pattern=r"^P[0-9a-f]{8}$")
    arm: Literal["A", "B", "C"]
    scenario: str = Field(max_length=32)
    action: Literal["sent", "cancelled"]
    seconds: float = Field(ge=0, le=3600)
    trust: int | None = Field(default=None, ge=1, le=5)
    complaint: bool | None = Field(default=None, description="Would complain to upay about being warned")


@router.post("/responses")
def record(body: Response, p: Principal = Depends(require_roles("customer"))) -> dict:
    scen = next((s for s in SCENARIOS if s["key"] == body.scenario), None)
    if scen is None:
        raise HTTPException(422, "unknown scenario")
    with session_scope() as db:
        db.add(StudyResponse(participant=body.participant, arm=body.arm, scenario=body.scenario,
                             is_scam=int(scen["is_scam"]), action=body.action, seconds=body.seconds, trust=body.trust,
                             complaint=None if body.complaint is None else int(body.complaint)))
    return {"recorded": True}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


@router.get("/results")
def results(p: Principal = Depends(require_roles("analyst"))) -> dict:
    """Measured outcomes per arm with 95% Wilson confidence intervals."""
    with session_scope() as db:
        rows = db.scalars(select(StudyResponse)).all()
        data = [(r.participant, r.arm, r.is_scam, r.action, r.seconds, r.trust, r.complaint) for r in rows]
    arms = {}
    for arm in ARMS:
        a = [d for d in data if d[1] == arm]
        scams = [d for d in a if d[2] == 1]
        legit = [d for d in a if d[2] == 0]
        k_cancel = sum(1 for d in scams if d[3] == "cancelled")
        k_continue = sum(1 for d in legit if d[3] == "sent")
        trust = [d[5] for d in a if d[5] is not None]
        people = {d[0]: d[6] for d in a if d[6] is not None}  # one complaint answer per participant
        k_compl = sum(people.values())
        arms[arm] = {
            "participants": len({d[0] for d in a}),
            "scam_decisions": len(scams),
            "scam_cancel_rate": round(k_cancel / len(scams), 4) if scams else None,
            "scam_cancel_ci95": wilson(k_cancel, len(scams)),
            "legit_decisions": len(legit),
            "legit_continue_rate": round(k_continue / len(legit), 4) if legit else None,
            "legit_continue_ci95": wilson(k_continue, len(legit)),
            "median_seconds": round(statistics.median([d[4] for d in a]), 1) if a else None,
            "mean_trust": round(statistics.mean(trust), 2) if trust else None,
            "complaint_rate": round(k_compl / len(people), 4) if people else None,
            "complaint_ci95": wilson(k_compl, len(people)),
        }
    total = len({d[0] for d in data})
    return {"participants": total, "arms": arms,
            "status": "measured" if total >= 30 else "collecting (aim for 60+ participants, 20 per arm)",
            "note": "Use arm C's scam-cancel rate (lower CI bound) in place of the assumed warn_heeded_rate once n is large enough."}
