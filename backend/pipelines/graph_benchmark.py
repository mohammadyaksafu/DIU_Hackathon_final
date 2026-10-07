"""Graph refresh benchmark: does the mule-ring snapshot stay affordable as data grows?

The graph has two paths:
  online  per-transaction counters (live fan-in, new senders, forwarding ratio, agent velocity)
          kept in the feature store: constant cost per transaction, no rebuild
  batch   Louvain communities + PageRank over a sliding window (14 days), rebuilt in the background

The window bounds the batch graph: its size depends on traffic per day, not on total history.
This script measures rebuild time for 1-14 day windows and for 1x-4x the synthetic traffic
(wallets cloned with new ids), and the per-transaction cost of the online features.

Usage:  python -m pipelines.graph_benchmark      (writes reports/graph_benchmark.json and .md)
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np

from app.features.engine import DAY
from app.graph.snapshot import compute_snapshot

BACKEND = Path(__file__).resolve().parents[1]


def _time(fn, repeat: int = 1) -> float:
    best = float("inf")
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return best


def run(data_dir: Path, reports_dir: Path, verbose: bool = True) -> dict:
    with open(data_dir / "online_state.pkl", "rb") as fh:
        state = pickle.load(fh)
    edges = list(state["graph_edges"])
    engine = state["engine"]
    end = edges[-1][0]

    windows = []
    for days in (1, 3, 7, 14):
        sub = [e for e in edges if e[0] >= end - days * DAY]
        secs = _time(lambda: compute_snapshot(sub))
        windows.append({"window_days": days, "edges": len(sub), "seconds": round(secs, 2)})
        if verbose:
            print(f"  window {days:>2}d: {len(sub):>7,} edges  {secs:.2f}s")

    scale = []
    base = [e for e in edges if e[0] >= end - 14 * DAY]
    for k in (1, 2, 4):
        big = [(ts, f"{s}~{i}" if i else s, f"{d}~{i}" if i else d, a, t) for i in range(k) for ts, s, d, a, t in base]
        secs = _time(lambda: compute_snapshot(big))
        scale.append({"traffic_multiple": k, "edges": len(big), "seconds": round(secs, 2),
                      "seconds_per_100k_edges": round(secs / len(big) * 100_000, 3)})
        if verbose:
            print(f"  traffic x{k}: {len(big):>8,} edges  {secs:.2f}s")

    # online features: one compute() per transaction, independent of history size
    sample = [{"tx_id": "b", "ts": end + 60, "type": t, "amount": a, "sender": s, "receiver": d, "device_id": None, "geo_cell": None}
              for _, s, d, a, t in base[-2000:]]
    t0 = time.perf_counter()
    for tx in sample:
        engine.compute(tx)
    per_tx_ms = (time.perf_counter() - t0) / len(sample) * 1000

    slope = np.polyfit([s["edges"] for s in scale], [s["seconds"] for s in scale], 1)[0]
    out = {"windows": windows, "scale": scale, "online_feature_ms_per_tx": round(per_tx_ms, 3),
           "seconds_per_million_edges_fit": round(float(slope) * 1e6, 1)}
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "graph_benchmark.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (reports_dir / "graph_benchmark.md").write_text(markdown(out), encoding="utf-8")
    return out


def markdown(r: dict) -> str:
    L = ["# Graph refresh benchmark", "",
         "Batch snapshot = Louvain communities + PageRank over a sliding window, rebuilt in a background thread",
         "(every 10 minutes by default). Scoring never waits for it: each request reads the latest finished snapshot.", "",
         "## Window size (synthetic traffic, 2,000 customers)", "", "| Window | Edges | Rebuild time |", "|---|---|---|"]
    L += [f"| {w['window_days']} days | {w['edges']:,} | {w['seconds']:.2f} s |" for w in r["windows"]]
    L += ["", "## Traffic growth (14-day window, wallets cloned)", "",
          "| Traffic | Edges | Rebuild time | Seconds per 100k edges |", "|---|---|---|---|"]
    L += [f"| {s['traffic_multiple']}× | {s['edges']:,} | {s['seconds']:.2f} s | {s['seconds_per_100k_edges']:.3f} |" for s in r["scale"]]
    L += ["", f"Rebuild time grows roughly linearly with the edges in the window (≈{r['seconds_per_million_edges_fit']} s per million edges on this laptop).",
          "Because the window is fixed, the graph does not grow with total history, only with daily traffic.", "",
          f"Online graph features (live fan-in, new senders, forwarding ratio, agent velocity) cost **{r['online_feature_ms_per_tx']} ms per transaction**",
          "and are updated on every committed transfer, so a brand-new ring shows up immediately, before the next rebuild.", "",
          "## At upay scale", "",
          "- Partition the batch graph by community / region and rebuild partitions in parallel workers.",
          "- Run full Louvain nightly; between runs, update only the neighbourhood of changed wallets (incremental PageRank).",
          "- Keep the online counters in Redis (done) so every API worker sees the same live fan-in.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    run(BACKEND / "data", BACKEND / "reports")
