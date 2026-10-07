"""Customer wallet simulator: demo customers and one-click scenarios for the live demo.

Scenarios prepare realistic context (e.g. a SIM swap, a stranger's bait transfer) and
return the transfer to score. Scoring still goes through the normal /score endpoint.
"""
from __future__ import annotations

import zlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import state_dep
from app.core.security import Principal, require_roles
from app.features.engine import DAY, HOUR
from app.services.scoring import ingest_committed
from app.services.state import AppState

router = APIRouter(prefix="/simulator", tags=["simulator"])

SCENARIOS = [
    {"key": "normal_contact", "title": "Send money to family", "expected": "ALLOW",
     "description": "A usual transfer to a frequent contact, from the usual phone.",
     "title_bn": "পরিবারকে টাকা পাঠানো",
     "story_bn": "নিয়মিত পরিচিত নম্বরে, নিজের ফোন থেকে, স্বাভাবিক অঙ্কের টাকা পাঠানো হচ্ছে। কোনো ঝুঁকির লক্ষণ নেই।"},
    {"key": "merchant_payment", "title": "Pay a shop", "expected": "ALLOW",
     "description": "Payment to a merchant this customer already uses.",
     "title_bn": "দোকানে পেমেন্ট",
     "story_bn": "গ্রাহক আগে থেকে যে দোকানে কেনাকাটা করেন, সেখানে স্বাভাবিক অঙ্কের পেমেন্ট করছেন।"},
    {"key": "prize_scam", "title": "'You won a prize' scam", "expected": "WARN/HOLD",
     "description": "A caller says you won a prize and must pay a 2,000 BDT fee to a number you have never paid.",
     "title_bn": "'আপনি পুরস্কার জিতেছেন' প্রতারণা",
     "story_bn": "একজন ফোন করে বলল আপনি পুরস্কার জিতেছেন, তবে আগে ২,০০০ টাকা 'ফি' দিতে হবে। নম্বরটিতে আপনি আগে কখনো টাকা পাঠাননি, আর সেটি অনেক মানুষের কাছ থেকে টাকা নিয়ে দ্রুত ক্যাশ আউট করা একটি চক্রের অংশ।"},
    {"key": "refund_scam", "title": "'Wrong send' refund scam", "expected": "WARN/HOLD",
     "description": "A stranger sends 500 BDT, calls to say it was a mistake, and asks for a 5,000 BDT 'refund' to another number.",
     "title_bn": "'ভুল করে টাকা পাঠিয়েছি' প্রতারণা",
     "story_bn": "অচেনা একজন আপনাকে ৫০০ টাকা পাঠিয়ে ফোন করে বলল ভুল হয়েছে, এখন অন্য একটি নম্বরে ৫,০০০ টাকা 'ফেরত' দিন। টোপের টাকার চেয়ে অনেক বেশি এবং ভিন্ন নম্বরে চাওয়া হচ্ছে।"},
    {"key": "account_takeover", "title": "Account takeover at night", "expected": "HOLD",
     "description": "SIM swapped 2 hours ago, PIN reset 10 minutes ago, new phone drains the wallet.",
     "title_bn": "রাতে অ্যাকাউন্ট দখল",
     "story_bn": "প্রতারক ২ ঘণ্টা আগে গ্রাহকের সিম বদলে নিয়েছে, ১০ মিনিট আগে পিন রিসেট করেছে, আর এখন নতুন ফোন থেকে অন্য এলাকা থেকে বড় অঙ্কের টাকা সরিয়ে নিচ্ছে।"},
    {"key": "structuring", "title": "Structured cash-outs", "expected": "WARN/HOLD",
     "description": "Second cash-out today just below the 25,000 BDT limit at the same agent.",
     "title_bn": "সীমার ঠিক নিচে বারবার ক্যাশ আউট",
     "story_bn": "একই এজেন্টে আজ দ্বিতীয়বার ২৫,০০০ টাকার সীমার ঠিক নিচে ক্যাশ আউট করা হচ্ছে, যাতে নজরদারি এড়ানো যায়।"},
    {"key": "on_call_scam", "title": "Coached on a phone call", "expected": "WARN/HOLD",
     "description": "A caller stays on the line and talks the customer into sending twice their usual amount to a new number.",
     "title_bn": "ফোনে কথা বলতে বলতে টাকা পাঠানো",
     "story_bn": "একজন 'অফিসার' ফোনে থেকে গ্রাহককে তাড়া দিচ্ছে, আর গ্রাহক কথা চলা অবস্থায় নতুন একটি নম্বরে সাধারণের দ্বিগুণ টাকা পাঠাচ্ছেন। অ্যাপ জানে কল চলছে।"},
    {"key": "agent_cashout", "title": "Mule cash-out at an agent", "expected": "WARN/HOLD",
     "description": "Three strangers sent money in the last 40 minutes; the wallet now cashes it all out at an agent that is serving many first-time customers.",
     "title_bn": "এজেন্টে মিউল ক্যাশ আউট",
     "story_bn": "গত ৪০ মিনিটে তিনজন অপরিচিত মানুষ এই ওয়ালেটে টাকা পাঠিয়েছে, আর এখন পুরো টাকা একটি এজেন্টে ক্যাশ আউট হচ্ছে। একই এজেন্টে এই এক ঘণ্টায় আরও কয়েকটি নতুন ওয়ালেট একইভাবে টাকা তুলেছে।"},
]


def _ring_wallets(state: AppState, cid: str) -> tuple[list[str], list[str]]:
    """Collector / forwarder wallets of a mule ring that is still active at the end of the data.

    The ring is chosen per customer (stable hash), so different demo customers pay different
    mule wallets instead of one well-known account.
    """
    rings = state.data_meta.get("rings") or []
    if not rings:
        raise HTTPException(503, "no synthetic ring metadata available")
    last_day = max(r["end"] for r in rings)
    active = [r for r in rings if r["end"] >= last_day - 1] or rings[-1:]
    h = zlib.crc32(cid.encode())
    ring = active[h % len(active)]
    collectors = ring["collectors"][(h // len(active)) % len(ring["collectors"]):] + ring["collectors"][: (h // len(active)) % len(ring["collectors"])]
    return collectors, ring["forwarders"] or collectors


def _current_device(state: AppState, wallet: str) -> str | None:
    st = state.engine.wallets.get(wallet)
    if not st or not st.devices:
        return None
    return max(st.devices.items(), key=lambda kv: kv[1])[0]


def _top_contact(state: AppState, wallet: str, prefix: str) -> str | None:
    st = state.engine.wallets.get(wallet)
    if not st:
        return None
    ranked = sorted(((n, w) for w, n in st.known_out.items() if w.startswith(prefix)), reverse=True)
    return ranked[0][1] if ranked else None


@router.get("/customers")
def demo_customers(state: AppState = Depends(state_dep), p: Principal = Depends(require_roles("customer"))) -> list[dict]:
    if state.customers is None:
        return []
    df = state.customers[state.customers.synthetic_role == "normal"]
    df = df[df.signup_ts < state.sim_origin - 120 * DAY]
    out = []
    for persona in ["remittance_receiver", "garments_worker", "student", "professional", "shopkeeper", "fcommerce_seller", "freelancer"]:
        ids = [i for i in df[df.persona == persona].index if state.engine.wallets.get(i) and state.engine.wallets[i].n_out >= 15]
        for cid in ids[:2]:
            row = df.loc[cid]
            summary = state.engine.wallet_summary(cid)
            out.append({
                "id": cid, "name": row["name"], "persona": persona, "division": row["division"], "age_band": row["age_band"],
                "kyc_level": int(row["kyc_level"]), "home_geo": row["home_geo"], "device_id": _current_device(state, cid),
                "typical_amount": summary.get("typical_amount"), "phone": row["phone"],
            })
    return out


@router.get("/scenarios")
def list_scenarios(p: Principal = Depends(require_roles("customer"))) -> list[dict]:
    return SCENARIOS


class RunScenario(BaseModel):
    customer_id: str
    scenario: str


@router.post("/scenarios/run")
def run_scenario(body: RunScenario, state: AppState = Depends(state_dep),
                 p: Principal = Depends(require_roles("customer"))) -> dict:
    """Apply the scenario's context (events / prior transfers) and return the transfer to score."""
    if state.customers is None or body.customer_id not in state.customers.index:
        raise HTTPException(404, "unknown customer")
    cid = body.customer_id
    cust = state.customers.loc[cid]
    now = state.sim_now()
    device = _current_device(state, cid)
    typical = state.engine.wallet_summary(cid).get("typical_amount") or 500.0
    base = {"sender": cid, "device_id": device, "geo_cell": cust["home_geo"], "channel": "app"}
    setup: list[str] = []
    setup_bn: list[str] = []

    if body.scenario == "normal_contact":
        to = _top_contact(state, cid, "C")
        if to is None:
            raise HTTPException(409, "customer has no contacts")
        tx = {**base, "type": "send_money", "receiver": to, "amount": float(round(typical / 10) * 10)}
    elif body.scenario == "merchant_payment":
        to = _top_contact(state, cid, "M0") or "M0001"
        tx = {**base, "type": "payment", "receiver": to, "amount": float(round(typical * 0.8 / 10) * 10)}
    elif body.scenario == "prize_scam":
        collectors, _ = _ring_wallets(state, cid)
        tx = {**base, "type": "send_money", "receiver": collectors[0], "amount": 2000.0}
    elif body.scenario == "refund_scam":
        collectors, forwarders = _ring_wallets(state, cid)
        bait = {"tx_id": None, "ts": now - 12 * 60, "type": "send_money", "amount": 500.0, "sender": forwarders[0],
                "receiver": cid, "device_id": None, "geo_cell": None}
        ingest_committed(state, bait)
        setup.append(f"{forwarders[0]} sent 500 BDT to {cid} 12 minutes ago (bait)")
        setup_bn.append(f"১২ মিনিট আগে {forwarders[0]} থেকে {cid}-এ ৫০০ টাকা এসেছে (টোপ)")
        tx = {**base, "type": "send_money", "receiver": collectors[-1], "amount": 5000.0}
    elif body.scenario == "account_takeover":
        collectors, _ = _ring_wallets(state, cid)
        with state.lock:
            state.engine.ingest_event({"wallet": cid, "event": "sim_swap", "ts": now - 2 * HOUR})
            state.engine.ingest_event({"wallet": cid, "event": "password_reset", "ts": now - 10 * 60})
        setup += ["SIM swap 2 hours ago", "PIN reset 10 minutes ago"]
        setup_bn += ["২ ঘণ্টা আগে সিম বদল (SIM swap)", "১০ মিনিট আগে পিন রিসেট"]
        amount = float(min(24_000, max(3000, round(typical * 8 / 100) * 100)))
        tx = {**base, "type": "send_money", "receiver": collectors[0], "amount": amount,
              "device_id": f"DNEW-{cid}", "geo_cell": "CHA-07" if not str(cust["home_geo"]).startswith("CHA") else "DHA-03"}
    elif body.scenario == "structuring":
        agent = _top_contact(state, cid, "A") or "A001"
        first = {"tx_id": None, "ts": now - 50 * 60, "type": "cash_out", "amount": 24_700.0, "sender": cid,
                 "receiver": agent, "device_id": device, "geo_cell": cust["home_geo"]}
        ingest_committed(state, first)
        setup.append(f"Cash-out of 24,700 BDT at {agent} 50 minutes ago")
        setup_bn.append(f"৫০ মিনিট আগে {agent} এজেন্টে ২৪,৭০০ টাকা ক্যাশ আউট")
        tx = {**base, "type": "cash_out", "receiver": agent, "amount": 24_850.0}
    elif body.scenario == "on_call_scam":
        known = state.engine.wallets.get(cid)
        known_out = known.known_out if known else {}
        stranger = next(w for w in state.customers.index[::-1] if w != cid and w not in known_out)
        setup.append("The app reports an active phone call")
        setup_bn.append("অ্যাপ জানাচ্ছে: এই মুহূর্তে ফোনে কল চলছে")
        tx = {**base, "type": "send_money", "receiver": stranger, "amount": float(max(1000, round(typical * 2 / 100) * 100)),
              "on_call": True}
    elif body.scenario == "agent_cashout":
        collectors, forwarders = _ring_wallets(state, cid)
        agent = _top_contact(state, cid, "A") or "A001"
        # Fresh wallets every run (repeating the demo must show the same pattern): senders that never
        # paid this customer, and cash-out wallets that never used this agent.
        me, ag = state.engine.wallets.get(cid), state.engine.wallets.get(agent)
        paid_me = me.known_in if me else set()
        used_agent = ag.known_in if ag else set()
        mules = list(state.customers.index[state.customers.synthetic_role == "mule"])
        pool = [w for w in dict.fromkeys(forwarders + collectors + mules) if w != cid]
        senders = [w for w in pool if w not in paid_me][:3] or (forwarders + collectors)[:3]
        others_pool = [w for w in pool if w not in used_agent and w not in senders]
        inflow = 0.0
        for i, snd in enumerate(senders):
            amt = 2500.0 + 500 * i
            ingest_committed(state, {"tx_id": None, "ts": now - (40 - 12 * i) * 60, "type": "send_money", "amount": amt,
                                     "sender": snd, "receiver": cid, "device_id": None, "geo_cell": None})
            inflow += amt
        others = others_pool[:4]
        for i, w in enumerate(others):
            ingest_committed(state, {"tx_id": None, "ts": now - (50 - 10 * i) * 60, "type": "cash_out", "amount": 4000.0,
                                     "sender": w, "receiver": agent, "device_id": None, "geo_cell": None})
        setup.append(f"3 strangers sent {inflow:,.0f} BDT in the last 40 minutes")
        setup.append(f"{len(others)} other new wallets cashed out at {agent} in the last hour")
        setup_bn.append(f"গত ৪০ মিনিটে ৩ জন অপরিচিত মানুষ মোট {inflow:,.0f} টাকা পাঠিয়েছে")
        setup_bn.append(f"গত এক ঘণ্টায় {agent} এজেন্টে আরও {len(others)}টি নতুন ওয়ালেট ক্যাশ আউট করেছে")
        # Drain everything that arrived in the last 24 h (earlier demo runs included), up to the limit.
        st = state.engine.wallets.get(cid)
        inflow_24h = sum(x[1] for x in st.inn if now - x[0] <= DAY) if st else inflow
        tx = {**base, "type": "cash_out", "receiver": agent, "amount": float(min(24_900, round(max(inflow, inflow_24h) * 0.97 / 10) * 10))}
    else:
        raise HTTPException(404, "unknown scenario")
    return {"scenario": body.scenario, "setup": setup, "setup_bn": setup_bn, "transaction": tx}
