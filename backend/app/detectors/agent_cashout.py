"""Agent cash-out detector: the last step of a mule chain, when stolen money leaves as cash.

Looks at a cash-out at an agent point from two sides:
  wallet side: money that arrived minutes ago, often from new senders, is being cashed out almost in full
  agent side : this agent is suddenly serving many first-time customers, far above its normal hourly rate
A high score can trigger a WARN (in production: OTP / voice confirmation at the agent) or, together with
the mule-network score, a HOLD.
"""
from __future__ import annotations

from app.detectors.base import DetectorDeps, ScoringContext, Signal


def agent_cashout_risk(f: dict) -> tuple[float, dict]:
    if f.get("type_code") != 1:
        return 0.0, {}
    mins = float(f.get("s_mins_since_inflow", 1440))
    fresh = 1.0 if mins < 60 else 0.5 if mins < 180 else 0.0
    ratio = float(f.get("s_inflow_ratio_24h", 10))
    drain = 1.0 if 0.8 <= ratio <= 1.25 else 0.5 if 0.5 <= ratio < 0.8 else 0.0  # cashing out what just came in
    new_senders = float(f.get("s_new_sender_inflow_1h", 0))
    young = 1.0 if float(f.get("s_tenure_days", 999)) < 60 else 0.0
    velocity = min(1.0, max(float(f.get("a_new_customers_1h", 0)) / 4.0, (float(f.get("a_cashout_rate_ratio", 0)) - 1) / 4.0))
    merchant = 0.5 if f.get("s_merchant_profile", 0) == 1 else 1.0  # shops cash out takings daily
    parts = {"fresh_inflow": fresh, "drains_inflow": drain, "new_sender_inflow": new_senders, "young_wallet": young,
             "agent_velocity": round(velocity, 3)}
    score = (0.4 * fresh * drain + 0.2 * new_senders + 0.1 * young + 0.3 * velocity) * merchant
    return round(min(1.0, score), 4), parts


class AgentCashoutDetector:
    name = "agent_cashout"

    def __init__(self, deps: DetectorDeps) -> None:
        pass

    def score(self, ctx: ScoringContext) -> Signal:
        score, parts = agent_cashout_risk(ctx.features)
        reasons = []
        if score >= 0.5 and parts.get("fresh_inflow", 0) and parts.get("drains_inflow", 0):
            reasons.append("R_AGENT_FRESH_CASHOUT")
        if parts.get("agent_velocity", 0) >= 0.75:
            reasons.append("R_AGENT_VELOCITY")
        return Signal(detector=self.name, score=score, reason_codes=reasons, details=parts)
