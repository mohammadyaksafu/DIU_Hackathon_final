"""Bank-style load test: staged ramp of concurrent users with realistic MFS traffic.

Each virtual user loops: score a transfer, then (like a real wallet) confirm it when allowed or
cancel when warned/held. Traffic mix follows a typical MFS day: send money 60%, merchant payment 20%,
cash-out at an agent 12%, bill pay 5%, recharge 3%. Every request is persisted (decision, audit row).

Several client processes generate load (one asyncio event loop each), so the client is not the bottleneck.

    python tests/load/bank_load.py --url http://localhost:8000 --stages 50,100,200,400 --stage-seconds 60 --procs 4
    python tests/load/bank_load.py --soak 600 --users 100      # sustained 10-minute soak

Writes a JSON summary (and prints a Markdown table) per stage.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing as mp
import random
import time

import httpx

MIX = [("send_money", 0.60), ("payment", 0.20), ("cash_out", 0.12), ("bill_pay", 0.05), ("mobile_recharge", 0.03)]


def _tx(rng: random.Random) -> dict:
    t = rng.choices([m[0] for m in MIX], [m[1] for m in MIX])[0]
    sender = f"C{rng.randint(1, 2000):05d}"
    if t == "send_money":
        recv, amt = f"C{rng.randint(1, 2000):05d}", rng.choice([200, 300, 500, 800, 1000, 1500, 2000, 3000, 5000])
    elif t == "payment":
        recv, amt = f"M{rng.randint(1, 285):04d}", rng.choice([120, 250, 400, 650, 900, 1500])
    elif t == "cash_out":
        recv, amt = f"A{rng.randint(1, 153):03d}", rng.choice([1000, 2000, 3000, 5000, 8000, 12000])
    elif t == "bill_pay":
        recv, amt = "M-BILLER", rng.choice([300, 600, 900, 1500])
    else:
        recv, amt = "M-TELCO", rng.choice([20, 50, 100, 200])
    return {"type": t, "amount": amt, "sender": sender, "receiver": recv}


async def _user(client: httpx.AsyncClient, seed: int, stop: float, out: dict) -> None:
    rng = random.Random(seed)
    while time.time() < stop:
        t0 = time.perf_counter()
        try:
            r = await client.post("/api/v1/score", json=_tx(rng))
            dt = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                out["errors"] += 1
                out["status"][str(r.status_code)] = out["status"].get(str(r.status_code), 0) + 1
                continue
            body = r.json()
            out["lat"].append(dt)
            out["server"].append(body.get("latency_ms", 0.0))
            out["decisions"][body["decision"]] = out["decisions"].get(body["decision"], 0) + 1
            action = "sent" if body["decision"] == "ALLOW" else "cancelled"
            c = await client.post(f"/api/v1/transactions/{body['transaction_id']}/confirm", json={"action": action})
            out["confirms"] += int(c.status_code == 200)
        except httpx.HTTPError as exc:
            out["errors"] += 1
            out["status"][type(exc).__name__] = out["status"].get(type(exc).__name__, 0) + 1


async def _proc_main(url: str, token: str, users: int, seconds: float, seed: int) -> dict:
    out = {"lat": [], "server": [], "errors": 0, "status": {}, "decisions": {}, "confirms": 0}
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    async with httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=30, limits=limits) as c:
        stop = time.time() + seconds
        await asyncio.gather(*(_user(c, seed * 10_000 + i, stop, out) for i in range(users)))
    return out


def _worker(args) -> dict:
    return asyncio.run(_proc_main(*args))


def run_stage(url: str, token: str, users: int, seconds: float, procs: int, seed: int) -> dict:
    per = [users // procs + (1 if i < users % procs else 0) for i in range(procs)]
    started = time.time()
    with mp.Pool(procs) as pool:
        parts = pool.map(_worker, [(url, token, n, seconds, seed + i) for i, n in enumerate(per) if n])
    elapsed = time.time() - started
    lat = sorted(x for p in parts for x in p["lat"])
    srv = sorted(x for p in parts for x in p["server"])
    pct = lambda v, q: round(v[min(len(v) - 1, int(q * len(v)))], 1) if v else None
    decisions: dict = {}
    status: dict = {}
    for p in parts:
        for k, v in p["decisions"].items():
            decisions[k] = decisions.get(k, 0) + v
        for k, v in p["status"].items():
            status[k] = status.get(k, 0) + v
    n = len(lat)
    errors = sum(p["errors"] for p in parts)
    return {"users": users, "seconds": round(elapsed, 1), "scored": n, "confirms": sum(p["confirms"] for p in parts),
            "throughput_scores_per_s": round(n / elapsed, 1),
            "throughput_requests_per_s": round((n + sum(p["confirms"] for p in parts)) / elapsed, 1),
            "client_p50_ms": pct(lat, 0.5), "client_p95_ms": pct(lat, 0.95), "client_p99_ms": pct(lat, 0.99),
            "server_p50_ms": pct(srv, 0.5), "server_p95_ms": pct(srv, 0.95), "server_p99_ms": pct(srv, 0.99),
            "errors": errors, "error_rate": round(errors / max(1, n + errors), 5), "status": status, "decisions": decisions}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--stages", default="50,100,200,400")
    ap.add_argument("--stage-seconds", type=float, default=60)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--soak", type=float, default=0, help="seconds; runs one long stage with --users")
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--out", default="bank_load.json")
    a = ap.parse_args()
    token = httpx.post(f"{a.url}/api/v1/auth/login", json={"username": "customer", "password": "demo123"}).json()["access_token"]
    stages = [(a.users, a.soak)] if a.soak else [(int(u), a.stage_seconds) for u in a.stages.split(",")]
    results = []
    for i, (users, secs) in enumerate(stages):
        r = run_stage(a.url, token, users, secs, min(a.procs, users), seed=1000 * (i + 1))
        results.append(r)
        print(f"users={users:>4} scores/s={r['throughput_scores_per_s']:>7} req/s={r['throughput_requests_per_s']:>7} "
              f"client p50/p95/p99={r['client_p50_ms']}/{r['client_p95_ms']}/{r['client_p99_ms']} ms "
              f"server p50/p95/p99={r['server_p50_ms']}/{r['server_p95_ms']}/{r['server_p99_ms']} ms errors={r['errors']}", flush=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)


if __name__ == "__main__":
    main()
