"""Stateful, point-in-time feature engine.

The SAME code computes features offline (training replay over the historical stream)
and online (live scoring). This removes train/serve skew by construction:

    for tx in stream_sorted_by_time:
        x = engine.compute(tx)   # uses only state built from strictly earlier events
        engine.update(tx)        # then the transaction becomes history

Online, `compute` runs on /score and `update` runs only when the customer actually
sends the money (/transactions/{id}/confirm). A cancelled scam never pollutes history.
"""
from __future__ import annotations

import math
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass, field

HOUR = 3600.0
DAY = 86400.0
WINDOW = 7 * DAY
DHAKA_OFFSET = 6 * HOUR
CASH_OUT_LIMIT = 25_000.0
CAP_HOURS = 720.0

TX_TYPES = ["send_money", "cash_out", "payment", "cash_in", "mobile_recharge", "bill_pay", "disbursement"]
TX_TYPE_CODE = {t: i for i, t in enumerate(TX_TYPES)}
OUTGOING_TYPES = {"send_money", "cash_out", "payment", "mobile_recharge", "bill_pay"}

# Ordered feature list produced by `compute` (graph + anomaly features are appended later).
STREAM_FEATURES = [
    "amount",
    "amount_log",
    "amount_z",
    "amount_ratio",
    "is_round",
    "type_code",
    "s_out_cnt_1h",
    "s_out_cnt_24h",
    "s_out_sum_24h_ratio",
    "s_distinct_recv_24h",
    "s_same_recv_cnt_24h",
    "is_new_recipient",
    "s_hist_count",
    "s_tenure_days",
    "hour",
    "s_hour_freq",
    "is_night",
    "is_new_device",
    "s_device_count",
    "s_device_age_hrs",
    "hrs_since_sim_swap",
    "hrs_since_pwd_reset",
    "geo_changed",
    "r_tenure_days",
    "r_distinct_senders_24h",
    "r_new_senders_24h",
    "r_in_cnt_24h",
    "r_fwd_ratio_24h",
    "s_mins_since_inflow",
    "s_inflow_ratio_24h",
    "s_new_sender_inflow_1h",
    "near_limit",
    "s_cashout_cnt_24h",
]


# Agent-side cash-out features (computed only for cash-outs at an agent). Used by the agent
# cash-out detector and rules; not model inputs, so adding them needs no retrain.
AGENT_FEATURES = ["a_cashouts_1h", "a_new_customers_1h", "a_cashout_rate_ratio"]


def is_customer_wallet(wallet_id: str) -> bool:
    return wallet_id.startswith("C")


def local_hour(ts: float) -> int:
    return int(((ts + DHAKA_OFFSET) % DAY) // HOUR)


@dataclass
class WalletState:
    first_seen: float | None = None
    out: deque = field(default_factory=deque)  # (ts, amount, receiver, type)
    inn: deque = field(default_factory=deque)  # (ts, amount, sender, type, sender_first_time)
    known_out: dict = field(default_factory=dict)  # receiver -> count
    known_in: set = field(default_factory=set)  # senders seen
    n_out: int = 0
    mean: float = 0.0  # Welford over log1p(amount) of outgoing tx
    m2: float = 0.0
    hours: list = field(default_factory=lambda: [0] * 24)
    devices: dict = field(default_factory=dict)  # device -> first seen ts
    last_geo: str | None = None
    sim_swap: float | None = None
    pwd_reset: float | None = None

    def prune(self, now: float) -> None:
        cutoff = now - WINDOW
        while self.out and self.out[0][0] < cutoff:
            self.out.popleft()
        while self.inn and self.inn[0][0] < cutoff:
            self.inn.popleft()


class FeatureEngine:
    def __init__(self) -> None:
        # A dict offline and in a single worker; a RedisWalletStore when the state is shared (features/store.py).
        # Mutated states are always assigned back, so both backends see every change.
        self.wallets: dict[str, WalletState] = {}
        self.last_ts: float = 0.0

    def _locked(self, *wallet_ids: str):
        locked = getattr(self.wallets, "locked", None)
        return locked(*wallet_ids) if locked else nullcontext()

    # ---- state management -------------------------------------------------
    def _get(self, wallet_id: str) -> WalletState:
        st = self.wallets.get(wallet_id)
        if st is None:
            st = WalletState()
            self.wallets[wallet_id] = st
        return st

    def register_wallet(self, wallet_id: str, signup_ts: float | None, device_id: str | None = None) -> None:
        with self._locked(wallet_id):
            st = self._get(wallet_id)
            if signup_ts is not None and (st.first_seen is None or signup_ts < st.first_seen):
                st.first_seen = signup_ts
            if device_id and device_id not in st.devices:
                st.devices[device_id] = signup_ts or 0.0
            self.wallets[wallet_id] = st

    def ingest_event(self, event: dict) -> None:
        """Security events: sim_swap, password_reset."""
        with self._locked(event["wallet"]):
            st = self._get(event["wallet"])
            if event["event"] == "sim_swap":
                st.sim_swap = event["ts"]
            elif event["event"] == "password_reset":
                st.pwd_reset = event["ts"]
            self.wallets[event["wallet"]] = st
        self.last_ts = max(self.last_ts, event["ts"])

    # ---- features ------------------------------------------------------------
    def compute(self, tx: dict) -> dict:
        now = float(tx["ts"])
        amount = float(tx["amount"])
        ttype = tx["type"]
        s = self.wallets.get(tx["sender"]) or WalletState()
        r = self.wallets.get(tx["receiver"]) or WalletState()
        s.prune(now)
        r.prune(now)

        log_amt = math.log1p(amount)
        if s.n_out >= 3:
            std = max(0.25, math.sqrt(s.m2 / (s.n_out - 1)))
            amount_z = (log_amt - s.mean) / std
        else:
            amount_z = 0.0
        typical = math.expm1(s.mean) if s.n_out >= 1 else None
        amount_ratio = amount / max(typical, 1.0) if typical else 1.0

        # Deques are time-ordered: walk newest -> oldest and stop at the 24h boundary.
        out_1h = out_24h = 0
        out_sum_24h = 0.0
        recv_24h: set = set()
        same_recv_24h = 0
        cashout_24h = 0
        for ts, amt, recv, t in reversed(s.out):
            if now - ts > DAY:
                break
            out_24h += 1
            out_sum_24h += amt
            recv_24h.add(recv)
            if recv == tx["receiver"]:
                same_recv_24h += 1
            if t == "cash_out":
                cashout_24h += 1
            if now - ts <= HOUR:
                out_1h += 1

        last_inflow_ts = s.inn[-1][0] if s.inn else None
        inflow_24h = 0.0
        new_sender_inflow_1h = 0
        for ts, amt, snd, t, first in reversed(s.inn):
            if now - ts > DAY:
                break
            inflow_24h += amt
            if first and t == "send_money" and now - ts <= HOUR:
                new_sender_inflow_1h = 1

        # Receiver-side features only matter for customer wallets (mule detection);
        # agents/merchants/billers receive thousands of tx, so skip them for speed.
        r_senders_24h: set = set()
        r_new_senders_24h: set = set()
        r_in_cnt = 0
        r_in_sum = 0.0
        r_out_sum = 0.0
        if is_customer_wallet(tx["receiver"]):
            for ts, amt, snd, t, first in reversed(r.inn):
                if now - ts > DAY:
                    break
                r_in_cnt += 1
                r_in_sum += amt
                r_senders_24h.add(snd)
                if first:
                    r_new_senders_24h.add(snd)
            for ts, amt, _, _ in reversed(r.out):
                if now - ts > DAY:
                    break
                r_out_sum += amt

        # Agent velocity: how many wallets cashed out here in the last hour, how many of them
        # for the first time, and how that compares with this agent's normal hourly rate.
        a_cash_1h: set = set()
        a_new_1h = 0
        a_ratio = 0.0
        if ttype == "cash_out" and tx["receiver"].startswith("A"):
            for ts, amt, snd, t, first in reversed(r.inn):
                if now - ts > HOUR:
                    break
                if t == "cash_out" and snd not in a_cash_1h:
                    a_cash_1h.add(snd)
                    a_new_1h += int(first)
            span_h = max(1.0, (now - r.inn[0][0]) / HOUR) if r.inn else 1.0
            a_ratio = round(min(20.0, (len(a_cash_1h) + 1) / max(len(r.inn) / span_h, 0.5)), 3)

        hour = local_hour(now)
        total_hours = sum(s.hours)
        hour_freq = (
            (s.hours[(hour - 1) % 24] + s.hours[hour] + s.hours[(hour + 1) % 24]) / total_hours
            if total_hours
            else 0.5
        )
        device = tx.get("device_id")
        geo = tx.get("geo_cell")

        return {
            "amount": amount,
            "amount_log": log_amt,
            "amount_z": round(amount_z, 4),
            "amount_ratio": round(min(amount_ratio, 100.0), 4),
            "is_round": int(amount >= 500 and amount % 500 == 0),
            "type_code": TX_TYPE_CODE.get(ttype, -1),
            "s_out_cnt_1h": out_1h,
            "s_out_cnt_24h": out_24h,
            "s_out_sum_24h_ratio": round(out_sum_24h / max(typical or amount, 1.0), 4),
            "s_distinct_recv_24h": len(recv_24h),
            "s_same_recv_cnt_24h": same_recv_24h,
            "is_new_recipient": int(tx["receiver"] not in s.known_out),
            "s_hist_count": s.n_out,
            "s_tenure_days": round((now - s.first_seen) / DAY, 3) if s.first_seen is not None else 0.0,
            "hour": hour,
            "s_hour_freq": round(hour_freq, 4),
            "is_night": int(hour < 6),
            "is_new_device": int(bool(device) and bool(s.devices) and device not in s.devices),
            "s_device_count": len(s.devices),
            "s_device_age_hrs": round(min(CAP_HOURS, (now - s.devices[device]) / HOUR), 3) if device in s.devices else 0.0,
            "hrs_since_sim_swap": min(CAP_HOURS, (now - s.sim_swap) / HOUR) if s.sim_swap else CAP_HOURS,
            "hrs_since_pwd_reset": min(CAP_HOURS, (now - s.pwd_reset) / HOUR) if s.pwd_reset else CAP_HOURS,
            "geo_changed": int(bool(geo) and s.last_geo is not None and geo != s.last_geo),
            "r_tenure_days": round((now - r.first_seen) / DAY, 3) if r.first_seen is not None else 0.0,
            "r_distinct_senders_24h": len(r_senders_24h),
            "r_new_senders_24h": len(r_new_senders_24h),
            "r_in_cnt_24h": r_in_cnt,
            "r_fwd_ratio_24h": round(min(r_out_sum / r_in_sum, 5.0), 4) if r_in_sum > 0 else 0.0,
            "s_mins_since_inflow": min(1440.0, (now - last_inflow_ts) / 60.0) if last_inflow_ts else 1440.0,
            "s_inflow_ratio_24h": round(min(amount / inflow_24h, 10.0), 4) if inflow_24h > 0 else 10.0,
            "s_new_sender_inflow_1h": new_sender_inflow_1h,
            "near_limit": int(ttype == "cash_out" and amount >= 0.94 * CASH_OUT_LIMIT),
            "s_cashout_cnt_24h": cashout_24h,
            "a_cashouts_1h": len(a_cash_1h),
            "a_new_customers_1h": a_new_1h,
            "a_cashout_rate_ratio": a_ratio,
        }

    def update(self, tx: dict) -> None:
        with self._locked(tx["sender"], tx["receiver"]):
            self._update(tx)

    def _update(self, tx: dict) -> None:
        now = float(tx["ts"])
        amount = float(tx["amount"])
        ttype = tx["type"]
        s = self._get(tx["sender"])
        r = s if tx["receiver"] == tx["sender"] else self._get(tx["receiver"])
        for st in (s, r):
            if st.first_seen is None:
                st.first_seen = now
        s.out.append((now, amount, tx["receiver"], ttype))
        s.known_out[tx["receiver"]] = s.known_out.get(tx["receiver"], 0) + 1
        if ttype in OUTGOING_TYPES:
            s.n_out += 1
            x = math.log1p(amount)
            delta = x - s.mean
            s.mean += delta / s.n_out
            s.m2 += delta * (x - s.mean)
            s.hours[local_hour(now)] += 1
        if tx.get("device_id") and tx["device_id"] not in s.devices:
            s.devices[tx["device_id"]] = now
        if tx.get("geo_cell"):
            s.last_geo = tx["geo_cell"]
        first = tx["sender"] not in r.known_in
        r.inn.append((now, amount, tx["sender"], ttype, first))
        r.known_in.add(tx["sender"])
        s.prune(now)
        r.prune(now)
        self.wallets[tx["sender"]] = s
        self.wallets[tx["receiver"]] = r
        self.last_ts = max(self.last_ts, now)

    def wallet_summary(self, wallet_id: str) -> dict:
        st = self.wallets.get(wallet_id)
        if st is None:
            return {"known": False}
        return {
            "known": True,
            "first_seen": st.first_seen,
            "n_out": st.n_out,
            "typical_amount": round(math.expm1(st.mean), 2) if st.n_out else None,
            "devices": len(st.devices),
            "known_recipients": len(st.known_out),
            "recent_out_7d": len(st.out),
            "recent_in_7d": len(st.inn),
        }
