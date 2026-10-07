"""Seeded synthetic MFS data generator with injected, labelled fraud scenarios.

Everything here is synthetic. No real person, phone number or transaction is used.
Assumptions are documented in docs/DATA_ASSUMPTIONS.md.

Normal behaviour: 6 personas with monthly salary/remittance cycles, diurnal patterns,
contact networks, favourite merchants and home agents, plus legitimate noise
(phone changes, legit SIM replacement, password resets, legit near-limit cash-outs,
shopkeepers with high fan-in).

Injected scenarios (label=1):
  S1 account takeover      SIM swap -> password reset -> new device -> night drain
  S2 prize/lottery scam    victim sends round amounts to a ring collector
  S3 'wrong send' refund   stranger sends small bait, victim 'refunds' a larger amount
  S4 money-mule ring       collectors forward to forwarders who cash out within minutes
  S5 structuring           colluding wallets cash out just below the 25k limit
  S6 OTP social eng.       same device, sharply unusual amount to a ring collector

Usage:  python -m pipelines.generate_data --customers 2000 --days 90 --seed 42
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DAY = 86400
HOUR = 3600
MINUTE = 60
BASE_TS = datetime(2026, 5, 31, 18, 0, tzinfo=timezone.utc).timestamp()  # 2026-06-01 00:00 Asia/Dhaka
CASH_OUT_LIMIT = 25_000

DIVISIONS = ["Dhaka", "Chattogram", "Rajshahi", "Khulna", "Sylhet", "Barishal", "Rangpur", "Mymensingh"]
DIV_W = [0.35, 0.18, 0.10, 0.09, 0.07, 0.06, 0.08, 0.07]
FIRST = [
    "Rahima", "Karim", "Nusrat", "Tanvir", "Shirin", "Rafiq", "Sumaiya", "Arif", "Jannat", "Habib",
    "Mitu", "Sabbir", "Farzana", "Imran", "Rupa", "Jahid", "Sadia", "Masud", "Taslima", "Rakib",
    "Nasrin", "Shakil", "Lipi", "Mamun", "Ayesha", "Sohel", "Bristy", "Hasan", "Moushumi", "Faruk",
]
NEW_JOINER_SHARE = 0.10      # legit accounts opened during the window
RECRUITED_MULE_SHARE = 0.5   # mules that are old, 'rented' accounts
ROUND_SHARE = 0.35           # legit p2p amounts rounded to 500
LAST = ["Akter", "Hossain", "Islam", "Rahman", "Begum", "Uddin", "Khatun", "Ahmed", "Sarker", "Mia", "Das", "Chowdhury"]
MERCHANT_CATS = ["grocery", "pharmacy", "restaurant", "fashion", "electronics", "utility_store", "online_shop", "transport"]

PERSONAS = {
    "student": dict(w=0.20, ages=["18-24"], kyc=[1, 2], scale=(250, 600), daily=1.0, night=0.08,
                    mix={"recharge": .30, "payment": .35, "send_contact": .20, "send_shop": .05, "send_new": .04, "cash_out": .06}),
    "garments_worker": dict(w=0.22, ages=["18-24", "25-34", "35-44"], kyc=[1, 1, 2], scale=(300, 800), daily=0.6, night=0.03,
                            mix={"recharge": .30, "payment": .25, "send_contact": .15, "send_shop": .20, "send_new": .03, "cash_out": .07}),
    "remittance_receiver": dict(w=0.12, ages=["45-54", "55-64", "65+"], kyc=[1], scale=(300, 900), daily=0.25, night=0.01,
                                mix={"recharge": .35, "bill": .20, "send_shop": .25, "send_contact": .15, "send_new": .02, "payment": .03}),
    "shopkeeper": dict(w=0.12, ages=["25-34", "35-44", "45-54"], kyc=[2, 3], scale=(800, 2500), daily=0.8, night=0.03,
                       mix={"recharge": .15, "send_contact": .25, "payment": .10, "bill": .10, "send_new": .10, "cash_out": .30}),
    "professional": dict(w=0.22, ages=["25-34", "35-44", "45-54"], kyc=[2, 3], scale=(800, 2500), daily=0.9, night=0.05,
                         mix={"recharge": .15, "payment": .40, "bill": .10, "send_contact": .20, "send_shop": .05, "send_new": .05, "cash_out": .05}),
    "fcommerce_seller": dict(w=0.05, ages=["18-24", "25-34", "35-44"], kyc=[1, 2], scale=(500, 1500), daily=0.5, night=0.10,
                             mix={"recharge": .25, "send_new": .30, "payment": .15, "send_contact": .20, "bill": .10}),
    "freelancer": dict(w=0.12, ages=["18-24", "25-34"], kyc=[1, 2], scale=(400, 1500), daily=0.9, night=0.25,
                       mix={"recharge": .20, "payment": .35, "send_contact": .20, "send_new": .12, "cash_out": .08, "bill": .05}),
}
DAY_HOUR_W = np.array([0, 0, 0, 0, 0, 0, 2, 4, 6, 8, 10, 11, 11, 9, 7, 7, 7, 8, 10, 11, 11, 9, 6, 3], dtype=float)
DAY_HOUR_W /= DAY_HOUR_W.sum()


class Generator:
    def __init__(self, n_customers: int, n_days: int, seed: int, hard: bool = False) -> None:
        # hard=True: overlapping behaviour, so no single clue separates fraud from legitimate use.
        # Legitimate users change phones, replace SIMs, transact at night and send large one-off
        # amounts more often; fraudsters copy normal amounts, reuse the victim's own phone and
        # mules wait hours before forwarding. Used by pipelines/evaluation.py (stress test).
        self.hard = hard
        self.n_customers = n_customers
        self.n_days = n_days
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.tx: list[tuple] = []
        self.events: list[tuple] = []
        self.customers: list[dict] = []
        self.cust_by_id: dict[str, dict] = {}

    # ------------------------------------------------------------------ helpers
    def ts(self, day: int, hour: float, minute: float = 0.0) -> float:
        return BASE_TS + day * DAY + hour * HOUR + minute * MINUTE

    def hour(self, night_share: float) -> float:
        if self.rng.random() < night_share:
            return float(self.rng.uniform(0, 6))
        return float(self.rng.choice(24, p=DAY_HOUR_W) + self.rng.random())

    def amount(self, scale: float, sigma: float = 0.6, lo: float = 10, hi: float = 24_990) -> float:
        a = float(np.clip(self.rng.lognormal(np.log(scale), sigma), lo, hi))
        return float(round(a / 10) * 10)

    def add_tx(self, ts, ttype, amount, sender, receiver, device=None, geo=None, label=0, scenario="normal", channel="app"):
        for w in (sender, receiver):
            c = self.cust_by_id.get(w)
            if c is not None and c["signup_ts"] > ts:
                return
        self.tx.append((ts, ttype, float(amount), sender, receiver, device, geo, channel, int(label), scenario))

    def p2p_amount(self, scale: float) -> float:
        a = self.amount(scale)
        if self.rng.random() < ROUND_SHARE:
            a = float(max(500, round(a / 500) * 500))
        return a

    def pick_many(self, seq, k: int) -> list:
        return [seq[int(i)] for i in self.rng.integers(0, len(seq), size=k)] if k > 0 else []

    def pick(self, seq):
        return seq[int(self.rng.integers(len(seq)))]

    # --------------------------------------------------------------- entities
    def build_entities(self) -> None:
        rng = self.rng
        self.merchants = []
        for i in range(max(60, self.n_customers // 7)):
            div = rng.choice(DIVISIONS, p=DIV_W)
            self.merchants.append({"id": f"M{i + 1:04d}", "category": self.pick(MERCHANT_CATS), "division": div,
                                   "name": f"Synthetic {self.pick(MERCHANT_CATS).replace('_', ' ').title()} {i + 1}"})
        self.agents = []
        for i in range(max(40, self.n_customers // 13)):
            div = rng.choice(DIVISIONS, p=DIV_W)
            self.agents.append({"id": f"A{i + 1:03d}", "division": div, "float_capacity": int(rng.integers(50, 400)) * 1000})
        self.enterprises = [{"id": f"E{i + 1:03d}", "kind": "employer"} for i in range(30)]
        self.enterprises.append({"id": "E900", "kind": "shell"})

        names = list(PERSONAS)
        weights = np.array([PERSONAS[p]["w"] for p in names])
        for i in range(self.n_customers):
            persona = str(rng.choice(names, p=weights / weights.sum()))
            joiner = rng.random() < (0.5 if persona == "fcommerce_seller" else NEW_JOINER_SHARE)
            signup = BASE_TS + float(rng.uniform(0, self.n_days - 5)) * DAY if joiner else BASE_TS - float(rng.uniform(30, 1500)) * DAY
            self._new_customer(f"C{i + 1:05d}", persona, signup_ts=signup)

        by_div: dict[str, list] = {d: [] for d in DIVISIONS}
        for c in self.customers:
            by_div[c["division"]].append(c)
        shops = {d: [c for c in by_div[d] if c["persona"] == "shopkeeper"] for d in DIVISIONS}
        m_by_div = {d: [m for m in self.merchants if m["division"] == d] or self.merchants for d in DIVISIONS}
        a_by_div = {d: [a for a in self.agents if a["division"] == d] or self.agents for d in DIVISIONS}
        earners = [c for c in self.customers if c["persona"] in ("garments_worker", "professional")]

        for c in self.customers:
            same = by_div[c["division"]]
            k = int(rng.integers(2, 6))
            pool = same if rng.random() < 0.7 else self.customers
            c["contacts"] = sorted({self.pick(pool)["id"] for _ in range(k)} - {c["id"]})
            local_shops = [s for s in shops[c["division"]] if s["id"] != c["id"]]
            c["shops"] = sorted({self.pick(local_shops)["id"] for _ in range(2)}) if local_shops else []
            c["merchants"] = [self.pick(m_by_div[c["division"]])["id"] for _ in range(int(rng.integers(3, 9)))]
            c["agents"] = [self.pick(a_by_div[c["division"]])["id"] for _ in range(int(rng.integers(1, 3)))]
            c["employer"] = self.pick(self.enterprises[:30])["id"]
            c["pay_day"] = (7 if c["persona"] == "garments_worker" else 1) + int(rng.integers(0, 3))
            c["family"] = []
        for c in self.customers:
            if c["persona"] == "remittance_receiver" and earners:
                for _ in range(int(rng.integers(1, 3))):
                    self.pick(earners)["family"].append(c["id"])
        self.a_by_div = a_by_div
        self.sellers = [c for c in self.customers if c["persona"] == "fcommerce_seller"]

    def _new_customer(self, cid: str, persona: str, signup_ts: float, role: str = "normal", division: str | None = None) -> dict:
        rng = self.rng
        p = PERSONAS[persona]
        div = division or str(rng.choice(DIVISIONS, p=DIV_W))
        c = {
            "id": cid,
            "name": f"{self.pick(FIRST)} {self.pick(LAST)}",
            "phone": f"SYN-01{int(rng.integers(3, 10))}{int(rng.integers(10_000_000, 99_999_999))}",
            "persona": persona,
            "age_band": self.pick(p["ages"]),
            "division": div,
            "home_geo": f"{div[:3].upper()}-{int(rng.integers(1, 21)):02d}",
            "kyc_level": int(self.pick(p["kyc"])),
            "signup_ts": float(signup_ts),
            "home_device": f"D{cid}-0",
            "device": f"D{cid}-0",
            "scale": float(rng.uniform(*p["scale"])),
            "synthetic_role": role,
            "contacts": [], "shops": [], "merchants": [], "agents": [], "family": [],
        }
        self.customers.append(c)
        self.cust_by_id[cid] = c
        return c

    # --------------------------------------------------------- normal activity
    def geo(self, c: dict) -> str:
        if self.rng.random() < 0.95:
            return c["home_geo"]
        return f"{c['division'][:3].upper()}-{int(self.rng.integers(1, 21)):02d}"

    def normal_activity(self) -> None:
        rng = self.rng
        normal = [c for c in self.customers if c["synthetic_role"] in ("normal", "structuring")]
        # Legitimate noise: phone changes (+ some legit SIM replacements) and password resets.
        device_change_day = {}
        for c in normal:
            if rng.random() < (0.06 if self.hard else 0.015):
                device_change_day[c["id"]] = int(rng.integers(5, self.n_days - 5))
            if rng.random() < (0.08 if self.hard else 0.03):
                d = int(rng.integers(1, self.n_days))
                self.events.append((self.ts(d, self.hour(0.02)), c["id"], "password_reset", 0, "legit_reset"))

        for day in range(self.n_days):
            dom = (datetime.fromtimestamp(BASE_TS + day * DAY + 6 * HOUR, tz=timezone.utc).day)
            for c in normal:
                p = PERSONAS[c["persona"]]
                if device_change_day.get(c["id"]) == day:
                    c["device"] = f"D{c['id']}-1"
                    if rng.random() < (0.6 if self.hard else 0.4):
                        self.events.append((self.ts(day, 9), c["id"], "sim_swap", 0, "legit_sim_replacement"))
                        self.events.append((self.ts(day, 9.5), c["id"], "password_reset", 0, "legit_sim_replacement"))
                    if rng.random() < 0.5:  # e.g. paying for the new phone
                        tgt = self.pick(c["merchants"]) if c["merchants"] and rng.random() < 0.5 else self.pick(self.customers)["id"]
                        kind = "payment" if tgt.startswith("M") else "send_money"
                        amt = float(max(500, round(c["scale"] * rng.uniform(4, 10) / 500) * 500))
                        self.add_tx(self.ts(day, rng.uniform(10, 20)), kind, amt, c["id"], tgt, c["device"], self.geo(c))
                self._monthly(c, day, dom)
                for _ in range(int(rng.poisson(p["daily"]))):
                    self._spend(c, day, p)

    def _monthly(self, c: dict, day: int, dom: int) -> None:
        rng, persona = self.rng, c["persona"]
        if persona in ("garments_worker", "professional") and dom == c["pay_day"]:
            sal = self.amount(12_000 if persona == "garments_worker" else 50_000, 0.25, 6_000, 150_000)
            t = self.ts(day, rng.uniform(10, 14))
            self.add_tx(t, "disbursement", sal, c["employer"], c["id"], scenario="normal")
            if persona == "garments_worker":
                co = min(round(sal * rng.uniform(0.4, 0.8) / 10) * 10, 24_000)
                self.add_tx(t + rng.uniform(0.5, 30) * HOUR, "cash_out", co, c["id"], self.pick(c["agents"]), c["device"], self.geo(c))
            for fam in c["family"]:
                ft = t + rng.uniform(1, 72) * HOUR
                amt = self.amount(3_500 if persona == "garments_worker" else 7_000, 0.3, 1_000, 20_000)
                self.add_tx(ft, "send_money", amt, c["id"], fam, c["device"], self.geo(c))
                rcv = self.cust_by_id[fam]
                self.add_tx(ft + rng.uniform(1, 24) * HOUR, "cash_out", round(amt * rng.uniform(0.6, 0.95) / 10) * 10,
                            fam, self.pick(rcv["agents"]), rcv["device"], self.geo(rcv), channel="ussd")
            if persona == "professional":
                for _ in range(3):
                    self.add_tx(self.ts(day + int(rng.integers(4, 14)), self.hour(0.02)), "bill_pay",
                                self.amount(1_500, 0.5, 200, 8_000), c["id"], "M-BILLER", c["device"], self.geo(c))
        elif persona == "student" and dom in (1, 15):
            self.add_tx(self.ts(day, rng.uniform(10, 19)), "cash_in", self.amount(3_500, 0.35, 1_000, 10_000),
                        self.pick(c["agents"]), c["id"], f"DA-{c['agents'][0]}")
        elif persona == "freelancer" and dom in (5, 20):
            self.add_tx(self.ts(day, rng.uniform(9, 23)), "disbursement", self.amount(9_000, 0.5, 2_000, 60_000),
                        self.pick(self.enterprises[:30])["id"], c["id"])
        elif persona == "fcommerce_seller":
            total = 0.0
            for b in self.pick_many(self.customers, int(rng.poisson(5))):
                if b["id"] == c["id"] or b["synthetic_role"] != "normal":
                    continue
                amt = self.p2p_amount(900)
                before = len(self.tx)
                self.add_tx(self.ts(day, self.hour(0.1)), "send_money", amt, b["id"], c["id"], b["device"], self.geo(b))
                total += amt if len(self.tx) > before else 0.0
            if total > 1000 and rng.random() < 0.8:
                left = round(total * rng.uniform(0.7, 1.0) / 10) * 10
                t = self.ts(day, rng.uniform(20, 23))
                while left > 0:
                    part = min(left, 24_500)
                    self.add_tx(t, "cash_out", float(part), c["id"], self.pick(c["agents"]), c["device"], c["home_geo"])
                    left -= part
                    t += rng.uniform(5, 30) * MINUTE
        elif persona == "shopkeeper":
            if rng.random() < 0.4:
                self.add_tx(self.ts(day, rng.uniform(19, 22)), "cash_out", float(round(rng.uniform(5_000, 24_900) / 10) * 10),
                            c["id"], self.pick(c["agents"]), c["device"], c["home_geo"])
            if rng.random() < 0.08:
                self.add_tx(self.ts(day, rng.uniform(9, 11)), "cash_in", self.amount(12_000, 0.4, 3_000, 25_000),
                            self.pick(c["agents"]), c["id"], f"DA-{c['agents'][0]}")

    def _spend(self, c: dict, day: int, p: dict) -> None:
        rng = self.rng
        kinds, probs = zip(*p["mix"].items())
        kind = rng.choice(kinds, p=np.array(probs) / sum(probs))
        t = self.ts(day, self.hour(min(0.5, p["night"] * 2.5) if self.hard else p["night"]))
        dev, geo = c["device"], self.geo(c)
        ch = "ussd" if c["persona"] == "remittance_receiver" and rng.random() < 0.6 else "app"
        s = c["scale"]
        if kind == "recharge":
            self.add_tx(t, "mobile_recharge", float(self.pick([20, 30, 50, 100, 150, 200, 300, 500])), c["id"], "M-TELCO", dev, geo, channel=ch)
        elif kind == "payment" and c["merchants"]:
            self.add_tx(t, "payment", self.amount(s * 0.8), c["id"], self.pick(c["merchants"]), dev, geo)
        elif kind == "bill":
            self.add_tx(t, "bill_pay", self.amount(900, 0.5, 100, 6_000), c["id"], "M-BILLER", dev, geo, channel=ch)
        elif kind == "send_contact" and c["contacts"]:
            big = self.hard and rng.random() < 0.06  # Eid, medical bills, school fees
            self.add_tx(t, "send_money", self.p2p_amount(s * (6 if big else 1.5)), c["id"], self.pick(c["contacts"]), dev, geo, channel=ch)
        elif kind == "send_shop" and c["shops"]:
            self.add_tx(t, "send_money", self.amount(s * 0.9), c["id"], self.pick(c["shops"]), dev, geo, channel=ch)
        elif kind == "send_new":
            # Strangers are often online sellers (legit fan-in), otherwise any customer.
            pool = self.sellers if self.sellers and self.rng.random() < 0.5 else self.customers
            other = self.pick(pool)
            if other["id"] != c["id"] and other["synthetic_role"] == "normal":
                self.add_tx(t, "send_money", self.p2p_amount(s * 1.5), c["id"], other["id"], dev, geo, channel=ch)
        elif kind == "cash_out":
            self.add_tx(t, "cash_out", self.amount(s * 4, 0.5, 200, 24_900), c["id"], self.pick(c["agents"]), dev, geo, channel=ch)

    # ------------------------------------------------------------------ fraud
    def build_rings(self) -> None:
        rng = self.rng
        n_rings = max(4, self.n_customers // 200)
        self.rings = []
        for r in range(n_rings):
            if r == n_rings - 1:
                start, dur = self.n_days - 11, 11  # one ring active at the end => live demo
            else:
                start, dur = int(rng.integers(3, self.n_days - 14)), int(rng.integers(9, 16))
            div = str(rng.choice(DIVISIONS, p=DIV_W))
            members = []
            for k in range(int(rng.integers(5, 11))):
                cid = f"C9{r:02d}{k:02d}"
                persona = self.pick(["student", "freelancer"])
                if rng.random() < RECRUITED_MULE_SHARE:
                    signup = BASE_TS - float(rng.uniform(60, 1200)) * DAY
                else:
                    signup = BASE_TS + (start - float(rng.uniform(1, 25))) * DAY
                m = self._new_customer(cid, persona, signup, role="mule", division=div)
                members.append(m)
            n_coll = int(rng.integers(2, 4))
            self.rings.append({
                "id": r, "start": start, "end": min(self.n_days - 1, start + dur), "division": div,
                "collectors": [m["id"] for m in members[:n_coll]],
                "forwarders": [m["id"] for m in members[n_coll:]],
                "agents": [self.pick(self.a_by_div[div])["id"] for _ in range(2)],
            })
            for m in members:  # light cover activity
                for d in range(max(0, start - 3), min(self.n_days, start + dur)):
                    if rng.random() < 0.3:
                        self.add_tx(self.ts(d, self.hour(0.05)), "mobile_recharge", float(self.pick([20, 50, 100])), m["id"], "M-TELCO", m["device"], m["home_geo"])

    def build_lone_wallets(self) -> None:
        self.lone_wallets = []
        for k in range(max(6, self.n_customers // 100)):
            m = self._new_customer(f"C8{k:04d}", self.pick(["student", "freelancer", "garments_worker"]),
                                   BASE_TS - float(self.rng.uniform(30, 900)) * DAY, role="mule")
            self.lone_wallets.append(m)

    def _victim(self) -> dict:
        w = {"remittance_receiver": 3.0, "garments_worker": 2.0, "student": 1.2}
        pool = [c for c in self.customers if c["synthetic_role"] == "normal"]
        weights = np.array([w.get(c["persona"], 1.0) for c in pool])
        return pool[int(self.rng.choice(len(pool), p=weights / weights.sum()))]

    def _ring_day(self) -> tuple[dict, int]:
        ring = self.pick(self.rings)
        # Bias toward the final ring so the live demo has an active ring with fan-in.
        if self.rng.random() < 0.15:
            ring = self.rings[-1]
        return ring, int(self.rng.integers(ring["start"], ring["end"] + 1))

    def inject_fraud(self) -> None:
        rng = self.rng
        k = self.n_customers / 1000
        self.collector_inflows: list[tuple] = []

        for _ in range(int(120 * k)):  # S2 prize scam
            ring, day = self._ring_day()
            v = self._victim()
            t = self.ts(day, rng.uniform(8, 23.9))
            coll = self.pick(ring["collectors"])
            if rng.random() < 0.35:  # lone scammer using a rented, otherwise quiet wallet
                coll = self.pick(self.lone_wallets)["id"]
            amt = float(self.pick([500, 1000, 1500, 2000, 2500, 3000, 5000]))
            if self.hard and rng.random() < 0.6:  # fee sized like the victim's normal transfers
                amt = self.amount(v["scale"] * 1.3)
            self.add_tx(t, "send_money", amt, v["id"], coll, v["device"], self.geo(v), 1, "S2_prize_scam")
            self.collector_inflows.append((t, coll, amt, ring))
            if rng.random() < 0.3:
                t2 = t + rng.uniform(10, 60) * MINUTE
                fee = float(self.pick([500, 1000, 1500]))
                self.add_tx(t2, "send_money", fee, v["id"], coll, v["device"], self.geo(v), 1, "S2_prize_scam")
                self.collector_inflows.append((t2, coll, fee, ring))

        for _ in range(int(40 * k)):  # S3 refund scam
            ring, day = self._ring_day()
            v = self._victim()
            t = self.ts(day, rng.uniform(9, 21))
            bait_from = self.pick(ring["forwarders"] or ring["collectors"])
            self.add_tx(t, "send_money", float(round(rng.uniform(200, 1200) / 10) * 10), bait_from, v["id"],
                        self.cust_by_id[bait_from]["device"], None, 1, "S3_refund_bait")
            coll = self.pick(ring["collectors"])
            t2 = t + rng.uniform(3, 30) * MINUTE
            amt = float(round(rng.uniform(2000, 9000) / 100) * 100)
            self.add_tx(t2, "send_money", amt, v["id"], coll, v["device"], self.geo(v), 1, "S3_refund_scam")
            self.collector_inflows.append((t2, coll, amt, ring))

        for i in range(int(25 * k)):  # S1 account takeover
            ring, day = self._ring_day()
            v = self._victim() if rng.random() < 0.5 else self.pick([c for c in self.customers if c["synthetic_role"] == "normal"])
            hour = rng.uniform(0, 5) if rng.random() < 0.7 else rng.uniform(9, 23)
            t = self.ts(day, hour)
            self.events.append((t - rng.uniform(1, 10) * HOUR, v["id"], "sim_swap", 1, "S1_ato"))
            self.events.append((t - rng.uniform(5, 40) * MINUTE, v["id"], "password_reset", 1, "S1_ato"))
            dev = f"DATO-{i:04d}"
            geo = f"{self.pick(DIVISIONS)[:3].upper()}-{int(rng.integers(1, 21)):02d}"
            if self.hard and rng.random() < 0.4:  # stolen phone: the victim's own device and area
                dev, geo = v["device"], v["home_geo"]
            for _ in range(int(rng.integers(2, 5))):
                amt = float(round(np.clip(v["scale"] * rng.uniform(4, 12), 2000, 24_900) / 100) * 100)
                coll = self.pick(ring["collectors"])
                self.add_tx(t, "send_money", amt, v["id"], coll, dev, geo, 1, "S1_ato")
                self.collector_inflows.append((t, coll, amt, ring))
                t += rng.uniform(2, 10) * MINUTE

        for _ in range(int(40 * k)):  # S6 OTP / social-engineering drain
            ring, day = self._ring_day()
            v = self._victim()
            t = self.ts(day, rng.uniform(10, 20))
            for _ in range(int(rng.integers(1, 3))):
                lo_hi = (1.0, 3.0) if self.hard else (1.5, 6)
                amt = float(round(np.clip(v["scale"] * rng.uniform(*lo_hi), 1000, 24_500) / 500) * 500)
                coll = self.pick(ring["collectors"])
                self.add_tx(t, "send_money", amt, v["id"], coll, v["device"], self.geo(v), 1, "S6_social_engineering")
                self.collector_inflows.append((t, coll, amt, ring))
                t += rng.uniform(5, 30) * MINUTE

        # S4 mule-ring flows: forward then cash out within minutes.
        for t, coll, amt, ring in sorted(self.collector_inflows, key=lambda x: x[0]):
            cdev = self.cust_by_id[coll]["device"]
            cgeo = self.cust_by_id[coll]["home_geo"]
            if rng.random() < 0.85 and ring["forwarders"]:
                fwd = self.pick(ring["forwarders"])
                t1 = t + (rng.uniform(2, 12) * HOUR if self.hard and rng.random() < 0.5 else rng.uniform(5, 50) * MINUTE)
                a1 = float(round(amt * rng.uniform(0.9, 0.98) / 10) * 10)
                self.add_tx(t1, "send_money", a1, coll, fwd, cdev, cgeo, 1, "S4_mule_forward")
                fd = self.cust_by_id[fwd]
                t2 = t1 + rng.uniform(10, 120) * MINUTE
                remaining = round(a1 * rng.uniform(0.95, 1.0) / 10) * 10
                while remaining > 0:
                    part = min(remaining, 24_500)
                    self.add_tx(t2, "cash_out", float(part), fwd, self.pick(ring["agents"]), fd["device"], fd["home_geo"], 1, "S4_mule_cashout")
                    remaining -= part
                    t2 += rng.uniform(3, 20) * MINUTE
            else:
                self.add_tx(t + rng.uniform(10, 90) * MINUTE, "cash_out", float(min(amt, 24_500)), coll,
                            self.pick(ring["agents"]), cdev, cgeo, 1, "S4_mule_cashout")

        normal = [c for c in self.customers if c["synthetic_role"] == "normal" and c["persona"] in ("shopkeeper", "freelancer", "professional")]
        for g in range(max(2, int(2 * k))):  # S5 structuring
            members = [self.pick(normal) for _ in range(int(rng.integers(3, 6)))]
            agent = self.pick(self.agents)["id"]
            for d in rng.choice(np.arange(3, self.n_days - 1), size=int(rng.integers(2, 4)), replace=False):
                for m in members:
                    m["synthetic_role"] = "structuring"
                    n_co = int(rng.integers(2, 5))
                    self.add_tx(self.ts(int(d) - 1, rng.uniform(15, 18)), "disbursement", float(n_co * 24_500), "E900", m["id"], label=1, scenario="S5_structuring")
                    t = self.ts(int(d), rng.uniform(10, 13))
                    for _ in range(n_co):
                        self.add_tx(t, "cash_out", float(round(rng.uniform(23_600, 24_990) / 10) * 10), m["id"], agent, m["device"], m["home_geo"], 1, "S5_structuring")
                        t += rng.uniform(20, 90) * MINUTE

    # ------------------------------------------------------------------ output
    def run(self, out_dir: Path) -> dict:
        self.build_entities()
        self.build_rings()
        self.build_lone_wallets()
        self.normal_activity()
        self.inject_fraud()

        end_ts = BASE_TS + self.n_days * DAY
        cols = ["ts", "type", "amount", "sender", "receiver", "device_id", "geo_cell", "channel", "label", "scenario"]
        tx = pd.DataFrame(self.tx, columns=cols)
        tx = tx[(tx.ts >= BASE_TS) & (tx.ts < end_ts)].sort_values("ts", kind="mergesort").reset_index(drop=True)
        tx.insert(0, "tx_id", [f"T{i:08d}" for i in range(len(tx))])
        tx["day"] = ((tx.ts - BASE_TS) // DAY).astype(int)
        tx["is_synthetic"] = True

        ev = pd.DataFrame(self.events, columns=["ts", "wallet", "event", "label", "scenario"])
        ev = ev[(ev.ts >= BASE_TS) & (ev.ts < end_ts)].sort_values("ts").reset_index(drop=True)

        cust = pd.DataFrame([{k: v for k, v in c.items() if k not in ("contacts", "shops", "merchants", "agents", "family", "scale", "device")}
                             | {"typical_amount": round(c["scale"], 2), "is_synthetic": True} for c in self.customers])
        out_dir.mkdir(parents=True, exist_ok=True)
        tx.to_parquet(out_dir / "transactions.parquet", index=False)
        ev.to_parquet(out_dir / "events.parquet", index=False)
        cust.to_parquet(out_dir / "customers.parquet", index=False)
        pd.DataFrame(self.merchants).to_parquet(out_dir / "merchants.parquet", index=False)
        pd.DataFrame(self.agents).to_parquet(out_dir / "agents.parquet", index=False)
        pd.DataFrame(self.enterprises).to_parquet(out_dir / "enterprises.parquet", index=False)

        meta = {
            "seed": self.seed,
            "hard": self.hard,
            "n_customers": self.n_customers,
            "n_days": self.n_days,
            "base_ts": BASE_TS,
            "end_ts": end_ts,
            "train_end_day": int(self.n_days * 0.78),
            "valid_end_day": int(self.n_days * 0.89),
            "cash_out_limit": CASH_OUT_LIMIT,
            "n_transactions": int(len(tx)),
            "n_fraud": int(tx.label.sum()),
            "fraud_rate": round(float(tx.label.mean()), 5),
            "scenario_counts": {k: int(v) for k, v in tx[tx.label == 1].scenario.value_counts().items()},
            "rings": [{k: v for k, v in r.items()} for r in self.rings],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta


def generate(out_dir: Path, customers: int = 2000, days: int = 90, seed: int = 42, hard: bool = False) -> dict:
    return Generator(customers, days, seed, hard).run(out_dir)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--customers", type=int, default=2000)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw")
    args = ap.parse_args()
    m = generate(args.out, args.customers, args.days, args.seed)
    print(json.dumps({k: m[k] for k in ("n_transactions", "n_fraud", "fraud_rate", "scenario_counts")}, indent=2))
