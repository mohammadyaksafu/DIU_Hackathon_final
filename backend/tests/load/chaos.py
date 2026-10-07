"""Chaos test: kill an API worker in the middle of load; no decision may be lost or duplicated.

Each request carries a unique tx_id. A client that sees a connection error retries the SAME tx_id
(as upay's core would), so the idempotency claim must return the original decision, never a second one.

    python tests/load/chaos.py --url http://localhost:8000 --users 12 --seconds 20 --kill-after 8 --kill-cmd "docker compose exec -T api sh -c 'kill -9 $(pgrep -f multiprocessing | head -1)'"

Afterwards, count rows: every tx_id must appear exactly once in scored_transactions.
"""
from __future__ import annotations

import argparse
import random
import subprocess
import threading
import time
import uuid

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=12)
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--kill-after", type=float, default=8)
    ap.add_argument("--kill-cmd", required=True)
    a = ap.parse_args()
    tok = httpx.post(f"{a.url}/api/v1/auth/login", json={"username": "customer", "password": "demo123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    run = "CHAOS" + uuid.uuid4().hex[:6]
    decisions: dict[str, str] = {}
    retries = conflicts = failed = 0
    lock = threading.Lock()
    stop = time.time() + a.seconds

    def worker(i: int) -> None:
        nonlocal retries, conflicts, failed
        rng = random.Random(i)
        n = 0
        with httpx.Client(base_url=a.url, headers=headers, timeout=10) as c:
            while time.time() < stop:
                n += 1
                tx_id = f"{run}-{i}-{n}"
                body = {"tx_id": tx_id, "type": "send_money", "amount": rng.choice([300, 900, 4000]),
                        "sender": f"C{rng.randint(1, 1900):05d}", "receiver": f"C{rng.randint(1, 1900):05d}"}
                first = None
                for attempt in range(6):
                    try:
                        r = c.post("/api/v1/score", json=body)
                        if r.status_code == 200:
                            d = r.json()["decision"]
                            if first is None:
                                first = d
                            elif d != first:
                                with lock:
                                    conflicts += 1
                            break
                    except httpx.HTTPError:
                        pass
                    with lock:
                        retries += 1
                    time.sleep(0.3 * (attempt + 1))
                with lock:
                    if first is None:
                        failed += 1
                    else:
                        decisions[tx_id] = first

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(a.users)]
    for t in threads:
        t.start()
    time.sleep(a.kill_after)
    killed = subprocess.run(a.kill_cmd, shell=True, capture_output=True, text=True)
    print(f"killed a worker at t={a.kill_after}s (exit {killed.returncode})")
    for t in threads:
        t.join()
    print(f"run={run} transfers={len(decisions)} retries={retries} lost={failed} conflicting_decisions={conflicts}")


if __name__ == "__main__":
    main()
