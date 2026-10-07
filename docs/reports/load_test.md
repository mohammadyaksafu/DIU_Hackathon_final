# Load test, scaling and chaos (measured)

**Setup.** Docker Compose on one Windows laptop (Docker Desktop): FastAPI with N Uvicorn workers sharing state in Redis, PostgreSQL, every request persisted (scored transaction + audit row). Client: `tests/load/bench.py` (closed loop, 20 s, Python threads on the same laptop), random senders/receivers/amounts. Rate limit raised for the test. Measured 2026-10-07.

## Throughput vs workers (16 concurrent users)

| API workers | Throughput | Client p50 | Client p95 | Client p99 | Errors |
|---|---|---|---|---|---|
| 1 | 52.0 req/s | 282 ms | 488 ms | 567 ms | 0 |
| 2 | 93.1 req/s | 174 ms | 324 ms | 423 ms | 0 |
| 4 | 168.6 req/s | 83 ms | 170 ms | 233 ms | 0 |

Throughput scales close to linearly (×1.8 for 2 workers, ×3.2 for 4) because the workers share nothing but Redis and PostgreSQL. With 1 user, client latency is ≈63 ms on every setting; that floor is the Windows → Docker Desktop network path, not the API.

**Server-side scoring latency** (features → detectors → policy → explanation, aggregated over all workers via Redis, during the runs above): p50 **11.6 ms**, p95 **26.0 ms**, p99 **35.8 ms**. Unloaded, a single score takes ≈3–8 ms.

## Chaos: kill a worker under load

`tests/load/chaos.py`, 4 workers, 12 users for 20 s, unique `tx_id` per transfer, clients retry the same `tx_id` on a connection error. At t = 8 s one worker process was killed with `kill -9`.

| Result | Value |
|---|---|
| Transfers decided | 2,177 |
| Client retries after the kill | 2 |
| Lost transfers | **0** |
| Retries that got a different decision | **0** |
| Rows in `scored_transactions` for the run | 2,177 (2,177 distinct) — no duplicates |
| Worker | Uvicorn logged `Child process died` and started a replacement automatically |

## Sizing (estimate)

Bangladesh's MFS sector moved Tk 1.72 trillion in January 2025 (Bangladesh Bank data, see [EVIDENCE.md](../EVIDENCE.md)). upay's share and peak transactions per second are not public, so we do not claim a number. On this laptop one worker sustains ≈40–50 scored-and-persisted requests per second; a production node with 8 workers on server CPUs, with PostgreSQL on its own host, is the starting point to benchmark against upay's real peak. The graph rebuild is off the request path ([graph_benchmark.md](graph_benchmark.md)).

## Drift monitor reacting to the test traffic

The load test sends random sender/receiver pairs and uniform amounts, which look nothing like real customers. After the runs, `GET /metrics/drift` reported **drift** (PSI 6.3 on community fan-in, 3.9 on amount, 1.5 on hour-of-day familiarity) and recommended retraining with human sign-off: the monitor flags exactly this kind of distribution change.
