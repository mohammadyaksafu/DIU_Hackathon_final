# Load test, scaling, bank-style load and chaos (measured)

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

## Bank-style load test (realistic traffic, ramp to 800 concurrent users, 5-minute soak)

`tests/load/bank_load.py`: each virtual user behaves like a wallet. It scores a transfer, then confirms it (sent if allowed, cancelled if warned or held), so every transfer is **two requests** and is persisted with its audit row. The mix follows a typical MFS day: send money 60%, merchant payment 20%, cash-out at an agent 12%, bill pay 5%, recharge 3%. Senders are real synthetic customers; receivers are customers, the 285 merchants, the 153 agents and the biller/telco. The load comes from 3 asyncio client processes.

**Hardware: one laptop, Intel Core i5-10310U (4 cores / 8 threads, 1.7 GHz base).** The load generator, Docker Desktop, 6 API workers, PostgreSQL, Redis and monitoring all share these 4 cores. Raw data: [bank_load_ramp.json](bank_load_ramp.json), [bank_load_soak.json](bank_load_soak.json). Measured 2026-10-07.

### Ramp: 60 s per stage, 6 API workers

| Concurrent users | Transfers/s | HTTP requests/s | Server scoring p50 / p95 / p99 | Client end-to-end p50 / p95 / p99 | Errors |
|---|---|---|---|---|---|
| 50 | 64.8 | 129.5 | 35 / 98 / 165 ms | 0.29 / 0.93 / 1.38 s | 0 |
| 100 | 67.8 | 135.5 | 40 / 98 / 155 ms | 0.52 / 2.07 / 2.37 s | 0 |
| 200 | 61.5 | 123.0 | 45 / 112 / 159 ms | 1.36 / 3.10 / 5.58 s | 0 |
| 400 | 37.6 | 75.2 | 57 / 168 / 250 ms | 4.29 / 10.0 / 12.7 s | 9 (0.06%) |
| 800 | 36.4 | 72.5 | 51 / 136 / 193 ms | 9.74 / 18.5 / 25.3 s | 32 (0.15%) |

### Soak: 100 concurrent users for 5 minutes

| Result | Value |
|---|---|
| Sustained throughput | **69.3 transfers/s (138.6 requests/s)**, about 20,800 transfers scored, confirmed and audited |
| Server scoring p50 / p95 / p99 | 39 / 106 / 161 ms |
| Errors | **0** |
| Memory after the soak | API (6 workers) 1.6 GB · PostgreSQL 322 MB · Redis 23 MB: flat, no leak |
| Database after all runs | 85,647 decisions, 159,118 audit rows, 161 MB |

### What the test shows

- **Correct under heavy load.** Up to 200 concurrent users there were 0 errors. At 400 and 800 users fewer than 0.2% of requests failed: they were client-side timeouts while requests queued on a saturated laptop. No decision was lost or duplicated (see the chaos test above).
- **The limit is this laptop's CPU, not the design.** Throughput peaks at about 65–70 transfers/s, because the client and the whole stack share 4 cores. Beyond 200 users the extra users only queue, so latency rises while throughput stays flat or falls.
- **Server scoring stays fast.** The scoring step itself stays at 35–57 ms p50 even at 800 users; the rest of the client latency is queueing.

### Fixes the load test drove

The first bank-style run reached only 75 → 41 transfers/s as load rose, with a server p50 of 1.2 s. Profiling found three causes, now fixed:

1. **Hub wallets re-serialised megabytes.** Agents, billers and the telco receive thousands of transfers, and their full history was rewritten on every update. Now only the last 400 entries of a hub's history are stored in Redis; customer wallets keep their full window, which all model features use.
2. **A per-process lock was held across Redis calls.** In Redis mode the lock is skipped; per-wallet Redis locks keep correctness, and those locks now poll every 2 ms instead of 100 ms.
3. **Too many threads fought over one interpreter.** Each worker now uses 8 handler threads (was 40), with a 20+20 PostgreSQL connection pool per worker. PostgreSQL uses group commit (`commit_delay`) with durability kept (`synchronous_commit` stays on). Score records are inserted, not merged, which saves a SELECT.

Result: server-side scoring p50 at 400 users fell from **1,233 ms to 57 ms** (p99 from 2.9 s to 0.25 s), and the errors at 200 users went from 4 to 0. Peak throughput stayed around 65–75 transfers/s, because the 4-core laptop is the ceiling either way.

### Capacity model for a bank (estimate)

- **Cost per transfer, measured single-threaded inside the API container:**
  - scoring: about 2.5–3.5 ms of CPU;
  - scoring + persistence + confirmation: about 12–16 ms of CPU, most of it database round trips and ORM work.
  - On this throttling laptop CPU these timings vary by up to 3× between runs.
- **Per server core** that is roughly **60–80 transfers/s**.
- **Example sizing:** a peak of **1,000 transfers/s** would need about 16 server cores across 2–3 API nodes behind a load balancer. On top of that: a dedicated PostgreSQL primary, plus a Redis instance or cluster. The design needs no change for this: workers already share all state through Redis and PostgreSQL. This is an **estimate**; upay's real peak is not public, so we size against an example figure only.
- **Next optimisations, if needed:**
  - write decisions in batches (or through Kafka) instead of one transaction per request;
  - use SQLAlchemy Core in place of the ORM on the hot path;
  - move scoring to an async endpoint.

## Graph rebuild under continuous ingestion

`tests/load/graph_under_load.py`, 4 workers, 8 users for 40 s: every allowed transfer was confirmed, so committed edges kept flowing into the shared graph while the mule-ring snapshot was rebuilt 12 times through the admin API.

| Result | Value |
|---|---|
| Transfers committed into the graph during the run | 2,285 |
| Snapshot rebuild time (min / median / max) | 0.83 s / 1.06 s / 1.28 s |
| Scoring latency while rebuilding (client p50 / p95 / p99) | 64 / 97 / 187 ms |

Rebuilds stay around one second under ingestion, and scoring keeps serving from the last finished snapshot meanwhile; the one-second rebuild never blocks a decision.
