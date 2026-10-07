"""Drift monitoring: Population Stability Index (PSI) of live features against the training window.

Every scored transaction adds its key features to a rolling window (Redis list shared by all workers,
or memory). GET /api/v1/metrics/drift compares that window with the training distribution:
PSI < 0.10 stable, 0.10-0.25 watch, > 0.25 drifted => retraining recommended (then human sign-off
before the new model is activated).
"""
from __future__ import annotations

import json
import logging
import threading
from collections import deque
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.cache import get_cache
from app.core.config import get_settings

logger = logging.getLogger(__name__)

DRIFT_FEATURES = [
    "amount_log", "amount_ratio", "is_new_recipient", "recent_device", "s_hour_freq", "s_tenure_days",
    "r_new_senders_24h", "hrs_since_sim_swap", "s_mins_since_inflow", "r_g_comm_fanin", "anomaly_score",
]
WINDOW = 5000
KEY = "shurokkha:drift:live"
WATCH, DRIFT = 0.10, 0.25
_mem: deque = deque(maxlen=WINDOW)
_lock = threading.Lock()


def record_live_features(features: dict) -> None:
    row = [float(features.get(f) or 0.0) for f in DRIFT_FEATURES]
    client = get_cache().redis
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.lpush(KEY, json.dumps(row))
            pipe.ltrim(KEY, 0, WINDOW - 1)
            pipe.execute()
            return
        except Exception:
            pass
    with _lock:
        _mem.append(row)


def _live() -> np.ndarray:
    client = get_cache().redis
    rows = None
    if client is not None:
        try:
            rows = [json.loads(x) for x in client.lrange(KEY, 0, WINDOW - 1)]
        except Exception:
            rows = None
    if rows is None:
        with _lock:
            rows = list(_mem)
    return np.array(rows, dtype=float).reshape(-1, len(DRIFT_FEATURES))


@lru_cache(maxsize=1)
def reference() -> dict:
    """Decile bins and proportions of each feature over the training window."""
    s = get_settings()
    meta = json.loads((s.data_dir / "raw" / "meta.json").read_text(encoding="utf-8"))
    df = pd.read_parquet(s.data_dir / "features.parquet")
    df = df[df.day < meta["train_end_day"]]
    out = {}
    for f in DRIFT_FEATURES:
        if f not in df:
            continue
        v = df[f].astype(float).fillna(0).to_numpy()
        edges = np.unique(np.quantile(v, np.linspace(0, 1, 11)))
        if len(edges) < 2:
            edges = np.array([v.min() - 0.5, v.min() + 0.5])
        counts = np.histogram(np.clip(v, edges[0], edges[-1]), bins=edges)[0]
        out[f] = {"edges": edges.tolist(), "expected": (counts / max(1, counts.sum())).tolist()}
    return out


def psi(expected: np.ndarray, actual: np.ndarray, eps: float = 1e-4) -> float:
    e, a = np.clip(expected, eps, None), np.clip(actual, eps, None)
    return float(np.sum((a - e) * np.log(a / e)))


def drift_report(min_rows: int = 200) -> dict:
    live = _live()
    try:
        ref = reference()
    except Exception as exc:  # no training data on this server
        return {"status": "unavailable", "detail": str(exc), "n_live": int(len(live))}
    if len(live) < min_rows:
        return {"status": "insufficient_data", "n_live": int(len(live)), "min_rows": min_rows,
                "thresholds": {"watch": WATCH, "drift": DRIFT}, "features": []}
    rows = []
    for i, f in enumerate(DRIFT_FEATURES):
        if f not in ref:
            continue
        edges = np.array(ref[f]["edges"])
        counts = np.histogram(np.clip(live[:, i], edges[0], edges[-1]), bins=edges)[0]
        value = psi(np.array(ref[f]["expected"]), counts / max(1, counts.sum()))
        rows.append({"feature": f, "psi": round(value, 4),
                     "status": "drift" if value > DRIFT else "watch" if value > WATCH else "stable"})
    rows.sort(key=lambda r: -r["psi"])
    worst = rows[0]["status"] if rows else "stable"
    return {"status": worst, "n_live": int(len(live)), "thresholds": {"watch": WATCH, "drift": DRIFT}, "features": rows,
            "action": "Retraining recommended; a person signs off before activation." if worst == "drift" else "No action needed."}
