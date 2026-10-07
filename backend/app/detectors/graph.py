"""Network-risk detector: is the counterparty part of a likely mule ring?

Transparent weighted score over graph-snapshot features plus live fan-in counters.
For cash-outs the *sender* is the wallet of interest; otherwise the receiver.
"""
from __future__ import annotations

from app.detectors.base import DetectorDeps, ScoringContext, Signal


def graph_risk(f: dict) -> tuple[float, dict]:
    if f.get("type_code") == 1:  # cash_out: look at the wallet cashing out
        fanin = min(1.0, f.get("s_g_comm_fanin", 0.0) / 4.0)
        cashout = min(1.0, f.get("s_g_comm_cashout", 0.0))
        fwd = min(1.0, f.get("s_g_fwd", 0.0))
        live = 1.0 if f.get("s_mins_since_inflow", 1440) < 120 else 0.0  # cashing out fresh money
        young = 1.0 if f.get("s_tenure_days", 999) < 60 else 0.4
    else:
        fanin = min(1.0, f.get("r_g_comm_fanin", 0.0) / 4.0)
        cashout = min(1.0, f.get("r_g_comm_cashout", 0.0))
        fwd = min(1.0, f.get("r_g_fwd", 0.0))
        live = min(1.0, f.get("r_new_senders_24h", 0) / 8.0)
        young = 1.0 if f.get("r_tenure_days", 999) < 60 else 0.4
    # Merchant-aware: a registered shop or online seller with many new payers is normal business,
    # not a collection account. Fan-in evidence counts for much less; forwarding/cash-out still count.
    wallet_is_merchant = f.get("s_merchant_profile" if f.get("type_code") == 1 else "r_merchant_profile", 0) == 1
    merchant = 0.3 if wallet_is_merchant else 1.0
    parts = {"community_fanin": fanin, "community_cashout": cashout, "forwarding": fwd, "live_fanin": live, "youth": young,
             "merchant_profile": float(wallet_is_merchant)}
    score = (0.3 * fanin * merchant + 0.25 * cashout * fanin + 0.2 * fwd + 0.25 * live * merchant) * young
    return round(min(1.0, score), 4), parts


class GraphDetector:
    name = "graph"

    def __init__(self, deps: DetectorDeps) -> None:
        pass

    def score(self, ctx: ScoringContext) -> Signal:
        score, parts = graph_risk(ctx.features)
        reasons = ["R_MULE_NETWORK"] if score >= 0.6 else []
        return Signal(detector=self.name, score=score, reason_codes=reasons, details=parts)
