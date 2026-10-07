"""Replay the historical stream through the online FeatureEngine (point-in-time features).

Graph snapshots are rebuilt every `snapshot_every_days` from the trailing 14 days of
edges *before* that moment, so no transaction sees the future.
Outputs:
  data/features.parquet   one row per transaction: features + label + metadata
  data/online_state.pkl   warm engine + graph edges, loaded by the API at boot
"""
from __future__ import annotations

import pickle
import time
from pathlib import Path

import pandas as pd

from app.features.engine import DAY, FeatureEngine
from app.features.registry import MERCHANT_PERSONAS, build_features, set_merchant_profiles
from app.graph.store import GraphStore

META_COLS = ["tx_id", "ts", "day", "type", "amount", "sender", "receiver", "label", "scenario"]


def tx_dict(row) -> dict:
    return {
        "tx_id": row.tx_id,
        "ts": float(row.ts),
        "type": row.type,
        "amount": float(row.amount),
        "sender": row.sender,
        "receiver": row.receiver,
        "device_id": row.device_id,
        "geo_cell": row.geo_cell,
    }


def build(raw_dir: Path, out_dir: Path, snapshot_every_days: int = 2, verbose: bool = True) -> pd.DataFrame:
    started = time.time()
    tx = pd.read_parquet(raw_dir / "transactions.parquet")
    ev = pd.read_parquet(raw_dir / "events.parquet")
    cust = pd.read_parquet(raw_dir / "customers.parquet")

    set_merchant_profiles(cust[cust.persona.isin(MERCHANT_PERSONAS)].id)
    engine = FeatureEngine()
    for c in cust.itertuples(index=False):
        engine.register_wallet(c.id, c.signup_ts, c.home_device)
    # Merchants, agents, billers and employers are long-established wallets.
    established = float(tx.ts.iloc[0]) - 1000 * DAY
    for name in ("merchants", "agents", "enterprises"):
        for wid in pd.read_parquet(raw_dir / f"{name}.parquet").id:
            engine.register_wallet(wid, established)
    for wid in ("M-TELCO", "M-BILLER"):
        engine.register_wallet(wid, established)
    store = GraphStore()

    events = list(ev.itertuples(index=False))
    ei = 0
    base_ts = float(tx.ts.iloc[0]) - (float(tx.ts.iloc[0]) % DAY)
    next_snapshot = base_ts + snapshot_every_days * DAY
    rows: list[dict] = []

    for row in tx.itertuples(index=False):
        t = tx_dict(row)
        while ei < len(events) and events[ei].ts <= t["ts"]:
            e = events[ei]
            engine.ingest_event({"ts": float(e.ts), "wallet": e.wallet, "event": e.event})
            ei += 1
        if t["ts"] >= next_snapshot:
            store.refresh()
            while next_snapshot <= t["ts"]:
                next_snapshot += snapshot_every_days * DAY
        rows.append(build_features(engine, t, store.snapshot))
        engine.update(t)
        store.add_edge(t)

    feats = pd.DataFrame(rows)
    df = pd.concat([tx[META_COLS].reset_index(drop=True), feats.drop(columns=["amount"])], axis=1)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "features.parquet", index=False)

    store.refresh()
    with open(out_dir / "online_state.pkl", "wb") as fh:
        pickle.dump({"engine": engine, "graph_edges": list(store.edges), "built_at": time.time()}, fh)
    if verbose:
        print(f"features: {len(df):,} rows x {feats.shape[1]} features in {time.time() - started:.1f}s")
    return df
