"""SHAP contributions + rule hits -> verified reason codes -> plain-language messages.

A reason code is emitted only if its factual condition holds for this transaction, so
an explanation can never claim something untrue (e.g. "new device" when it is not).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable

import yaml

from app.detectors.base import Signal
from app.features.engine import CASH_OUT_LIMIT

_I18N_PATH = Path(__file__).resolve().parents[1] / "i18n" / "messages.yaml"
_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

FEATURE_REASON: dict[str, str] = {
    "is_new_recipient": "R_NEW_RECIPIENT",
    "r_new_senders_24h": "R_RECIPIENT_HIGH_FANIN",
    "r_distinct_senders_24h": "R_RECIPIENT_HIGH_FANIN",
    "r_in_cnt_24h": "R_RECIPIENT_HIGH_FANIN",
    "amount_ratio": "R_UNUSUAL_AMOUNT",
    "amount_z": "R_UNUSUAL_AMOUNT",
    "amount_log": "R_UNUSUAL_AMOUNT",
    "amount": "R_UNUSUAL_AMOUNT",
    "s_out_sum_24h_ratio": "R_UNUSUAL_AMOUNT",
    "is_round": "R_ROUND_AMOUNT",
    "s_hour_freq": "R_UNUSUAL_HOUR",
    "is_night": "R_UNUSUAL_HOUR",
    "hour": "R_UNUSUAL_HOUR",
    "night_new_recipient": "R_UNUSUAL_HOUR",
    "is_new_device": "R_NEW_DEVICE",
    "s_device_count": "R_NEW_DEVICE",
    "s_device_age_hrs": "R_NEW_DEVICE",
    "recent_device": "R_NEW_DEVICE",
    "new_device_new_recipient": "R_NEW_DEVICE",
    "hrs_since_sim_swap": "R_SIM_SWAP_RECENT",
    "hrs_since_pwd_reset": "R_PASSWORD_RESET_RECENT",
    "geo_changed": "R_LOCATION_CHANGE",
    "r_tenure_days": "R_YOUNG_RECIPIENT_ACCOUNT",
    "r_g_in_deg": "R_MULE_NETWORK",
    "r_g_pr_pct": "R_MULE_NETWORK",
    "r_g_comm_size": "R_MULE_NETWORK",
    "r_g_comm_fanin": "R_MULE_NETWORK",
    "r_g_comm_cashout": "R_MULE_NETWORK",
    "r_g_fwd": "R_MULE_NETWORK",
    "s_g_comm_fanin": "R_MULE_NETWORK",
    "s_g_comm_cashout": "R_MULE_NETWORK",
    "s_g_fwd": "R_MULE_NETWORK",
    "r_fwd_ratio_24h": "R_RAPID_FORWARDING",
    "s_mins_since_inflow": "R_RAPID_CASHOUT_AFTER_INFLOW",
    "s_inflow_ratio_24h": "R_RAPID_CASHOUT_AFTER_INFLOW",
    "s_new_sender_inflow_1h": "R_REFUND_PATTERN",
    "near_limit": "R_STRUCTURING",
    "s_cashout_cnt_24h": "R_STRUCTURING",
    "amount_to_limit": "R_STRUCTURING",
    "s_out_cnt_1h": "R_HIGH_VELOCITY",
    "s_out_cnt_24h": "R_HIGH_VELOCITY",
    "s_distinct_recv_24h": "R_HIGH_VELOCITY",
    "s_same_recv_cnt_24h": "R_HIGH_VELOCITY",
    "anomaly_score": "R_BEHAVIOUR_ANOMALY",
    "s_tenure_days": "R_NEW_ACCOUNT",
    "s_hist_count": "R_NEW_ACCOUNT",
}


def _g(f: dict, k: str, d: float = 0.0) -> float:
    v = f.get(k, d)
    return d if v is None else float(v)


CONDITIONS: dict[str, Callable[[dict], bool]] = {
    "R_NEW_RECIPIENT": lambda f: _g(f, "is_new_recipient") == 1,
    "R_RECIPIENT_HIGH_FANIN": lambda f: _g(f, "r_new_senders_24h") >= 3,
    "R_UNUSUAL_AMOUNT": lambda f: _g(f, "amount_ratio") >= 2.5,
    "R_ROUND_AMOUNT": lambda f: _g(f, "is_round") == 1 and _g(f, "is_new_recipient") == 1,
    "R_UNUSUAL_HOUR": lambda f: _g(f, "s_hour_freq", 1) < 0.08 or (_g(f, "is_night") == 1 and _g(f, "s_hour_freq", 1) < 0.2),
    "R_NEW_DEVICE": lambda f: _g(f, "recent_device") == 1,
    "R_SIM_SWAP_RECENT": lambda f: _g(f, "hrs_since_sim_swap", 720) < 72,
    "R_PASSWORD_RESET_RECENT": lambda f: _g(f, "hrs_since_pwd_reset", 720) < 24,
    "R_LOCATION_CHANGE": lambda f: _g(f, "geo_changed") == 1,
    "R_YOUNG_RECIPIENT_ACCOUNT": lambda f: _g(f, "r_tenure_days", 999) < 30 and _g(f, "type_code") == 0,
    "R_MULE_NETWORK": lambda f: (
        (_g(f, "r_g_comm_fanin") >= 1.5 and _g(f, "r_g_fwd") >= 0.8 and _g(f, "r_g_in_deg") >= 5)
        or (_g(f, "type_code") == 1 and _g(f, "s_g_comm_fanin") >= 1.5)
    ),
    "R_RAPID_FORWARDING": lambda f: _g(f, "r_fwd_ratio_24h") >= 0.7,
    "R_RAPID_CASHOUT_AFTER_INFLOW": lambda f: _g(f, "s_mins_since_inflow", 1440) < 60 and _g(f, "s_inflow_ratio_24h", 10) >= 0.7,
    "R_REFUND_PATTERN": lambda f: _g(f, "s_new_sender_inflow_1h") == 1,
    "R_STRUCTURING": lambda f: _g(f, "near_limit") == 1,
    "R_HIGH_VELOCITY": lambda f: _g(f, "s_out_cnt_1h") >= 3 or _g(f, "s_distinct_recv_24h") >= 5,
    "R_BEHAVIOUR_ANOMALY": lambda f: _g(f, "anomaly_score") >= 0.99,
    "R_NEW_ACCOUNT": lambda f: _g(f, "s_tenure_days", 999) < 30,
    "R_ON_CALL": lambda f: _g(f, "on_call") == 1,
    "R_AGENT_FRESH_CASHOUT": lambda f: _g(f, "type_code") == 1 and _g(f, "s_mins_since_inflow", 1440) < 180,
    "R_AGENT_VELOCITY": lambda f: _g(f, "a_new_customers_1h") >= 3 or _g(f, "a_cashout_rate_ratio") >= 4,
}


@lru_cache
def messages() -> dict:
    with open(_I18N_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _params(f: dict) -> dict:
    return {
        "fanin": int(_g(f, "r_new_senders_24h")),
        "ratio": f"{_g(f, 'amount_ratio', 1):.1f}",
        "hours_sim": f"{_g(f, 'hrs_since_sim_swap', 720):.1f}",
        "hours_pwd": f"{_g(f, 'hrs_since_pwd_reset', 720):.1f}",
        "tenure": int(_g(f, "r_tenure_days")),
        "mins": int(_g(f, "s_mins_since_inflow", 1440)),
        "limit": f"{int(CASH_OUT_LIMIT):,}",
        "cnt_1h": int(_g(f, "s_out_cnt_1h")) + 1,
        "agent_new": int(_g(f, "a_new_customers_1h")),
    }


def render_reason(code: str, features: dict, lang: str) -> str:
    tpl = messages()["reasons"].get(code, {}).get(lang) or code
    text = tpl.format(**_params(features))
    return text.translate(_BN_DIGITS) if lang == "bn" else text


def select_reasons(features: dict, signals: dict[str, Signal], top_k: int = 3) -> list[str]:
    """Rules first (deterministic), then SHAP-ranked model drivers, then graph/anomaly."""
    ordered: list[str] = []

    def add(code: str, check: bool = True) -> None:
        if code and code not in ordered and (not check or CONDITIONS.get(code, lambda _: True)(features)):
            ordered.append(code)

    rules = signals.get("rules")
    if rules and rules.ok:
        for code in rules.reason_codes:
            add(code, check=False)
    agent = signals.get("agent_cashout")  # a specific, high-precision detector: its reasons lead
    if agent and agent.ok and agent.score >= 0.6:
        for code in agent.reason_codes:
            add(code)
    lgbm = signals.get("lgbm")
    if lgbm and lgbm.ok:
        for item in lgbm.details.get("contributions", []):
            if item["contribution"] > 0.05:
                add(FEATURE_REASON.get(item["feature"], ""))
    for name, sig in signals.items():  # graph, anomaly, agent cash-out and any plug-in detector
        if name not in ("rules", "lgbm") and sig.ok:
            for code in sig.reason_codes:
                add(code)
    return ordered[:top_k]


def customer_message(decision: str, reasons: list[str], features: dict) -> dict:
    d = messages()["decisions"][decision]
    out = {}
    for lang in ("en", "bn"):
        out[lang] = {
            "title": d["title"][lang],
            "body": d["body"][lang],
            "reasons": [render_reason(c, features, lang) for c in reasons] if decision != "ALLOW" else [],
        }
    return out
