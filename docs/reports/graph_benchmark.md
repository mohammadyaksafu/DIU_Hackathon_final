# Graph refresh benchmark

Batch snapshot = Louvain communities + PageRank over a sliding window, rebuilt in a background thread
(every 10 minutes by default). Scoring never waits for it: each request reads the latest finished snapshot.

## Window size (synthetic traffic, 2,000 customers)

| Window | Edges | Rebuild time |
|---|---|---|
| 1 days | 1,308 | 0.66 s |
| 3 days | 3,983 | 0.21 s |
| 7 days | 9,300 | 0.46 s |
| 14 days | 18,471 | 0.74 s |

## Traffic growth (14-day window, wallets cloned)

| Traffic | Edges | Rebuild time | Seconds per 100k edges |
|---|---|---|---|
| 1× | 18,471 | 0.77 s | 4.175 |
| 2× | 36,942 | 1.35 s | 3.656 |
| 4× | 73,884 | 4.03 s | 5.458 |

Rebuild time grows roughly linearly with the edges in the window (≈60.8 s per million edges on this laptop).
Because the window is fixed, the graph does not grow with total history, only with daily traffic.

Online graph features (live fan-in, new senders, forwarding ratio, agent velocity) cost **0.056 ms per transaction**
and are updated on every committed transfer, so a brand-new ring shows up immediately, before the next rebuild.

## At upay scale

- Partition the batch graph by community / region and rebuild partitions in parallel workers.
- Run full Louvain nightly; between runs, update only the neighbourhood of changed wallets (incremental PageRank).
- Keep the online counters in Redis (done) so every API worker sees the same live fan-in.
