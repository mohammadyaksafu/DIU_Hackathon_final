"""Graph rebuild time while transfers keep arriving (continuous ingestion).

Runs load in background threads (score + confirm, so committed transfers flow into the graph)
and triggers snapshot rebuilds through the admin API, recording how long each takes.

    python tests/load/graph_under_load.py --url http://localhost:8000 --seconds 40 --admin-password demo123
"""
from __future__ import annotations

import argparse
import random
import statistics
import threading
import time

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=8)
    ap.add_argument("--seconds", type=int, default=40)
    ap.add_argument("--admin-password", default="demo123")
    a = ap.parse_args()
    login = lambda u, p: {"Authorization": "Bearer " + httpx.post(f"{a.url}/api/v1/auth/login", json={"username": u, "password": p}).json()["access_token"]}
    cust, admin = login("customer", "demo123"), login("admin", a.admin_password)
    stop = time.time() + a.seconds
    committed = 0
    lat: list[float] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        nonlocal committed
        rng = random.Random(i)
        with httpx.Client(base_url=a.url, headers=cust, timeout=15) as c:
            while time.time() < stop:
                body = {"type": "send_money", "amount": rng.choice([200, 500, 900]),
                        "sender": f"C{rng.randint(1, 1900):05d}", "receiver": f"C{rng.randint(1, 1900):05d}"}
                t = time.perf_counter()
                r = c.post("/api/v1/score", json=body).json()
                with lock:
                    lat.append((time.perf_counter() - t) * 1000)
                if r.get("decision") == "ALLOW":
                    c.post(f"/api/v1/transactions/{r['transaction_id']}/confirm", json={"action": "sent"})
                    with lock:
                        committed += 1

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(a.users)]
    for t in threads:
        t.start()
    rebuilds = []
    with httpx.Client(base_url=a.url, headers=admin, timeout=120) as c:
        time.sleep(3)
        while time.time() < stop - 3:
            t = time.perf_counter()
            r = c.post("/api/v1/admin/graph/refresh").json()
            rebuilds.append({"seconds": round(time.perf_counter() - t, 2), "wallets": r.get("wallets")})
            time.sleep(2)
    for t in threads:
        t.join()
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))]
    print(f"committed transfers during run: {committed}; scoring requests: {len(lat)}")
    print(f"scoring client p50={p(0.5):.1f}ms p95={p(0.95):.1f}ms p99={p(0.99):.1f}ms while rebuilding")
    print(f"rebuilds: {len(rebuilds)}  seconds min/median/max = {min(r['seconds'] for r in rebuilds)}/"
          f"{statistics.median(r['seconds'] for r in rebuilds)}/{max(r['seconds'] for r in rebuilds)}  wallets {rebuilds[0]['wallets']} -> {rebuilds[-1]['wallets']}")


if __name__ == "__main__":
    main()
