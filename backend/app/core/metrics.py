"""Minimal Prometheus-compatible metrics (no external dependency).

Exposed at GET /metrics in the Prometheus text exposition format.

With several API workers each process counts its own requests. When Redis is available every worker
publishes a snapshot every few seconds, and /metrics (and the latency percentiles) add them up, so
Prometheus sees the whole API whichever worker answers the scrape.
"""
from __future__ import annotations

import bisect
import json
import os
import threading
from collections import defaultdict, deque

_LATENCY_BUCKETS_MS = [5, 10, 25, 50, 75, 100, 150, 250, 500, 1000, 2500]


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self.hist_counts: dict[str, list[int]] = {}
        self.hist_sum: dict[str, float] = defaultdict(float)
        self.recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=5000))

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self.counters[key] += value

    def observe_ms(self, name: str, value_ms: float) -> None:
        with self._lock:
            counts = self.hist_counts.setdefault(name, [0] * (len(_LATENCY_BUCKETS_MS) + 1))
            counts[bisect.bisect_left(_LATENCY_BUCKETS_MS, value_ms)] += 1
            self.hist_sum[name] += value_ms
            self.recent[name].append(value_ms)

    # ---- cross-worker aggregation (Redis) ----------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": [[n, [list(x) for x in lbl], v] for (n, lbl), v in self.counters.items()],
                "hist_counts": {k: list(v) for k, v in self.hist_counts.items()},
                "hist_sum": dict(self.hist_sum),
                "recent": {k: list(v)[-1000:] for k, v in self.recent.items()},
            }

    def publish(self, client) -> None:
        client.setex(f"shurokkha:metrics:{os.getpid()}", 30, json.dumps(self.snapshot()))

    def _all_snapshots(self) -> list[dict] | None:
        from app.core.cache import get_cache

        client = get_cache().redis
        if client is None:
            return None
        try:
            self.publish(client)
            keys = list(client.scan_iter("shurokkha:metrics:*", count=100))
            return [json.loads(raw) for raw in client.mget(keys) if raw] if keys else []
        except Exception:
            return None

    def _merged(self) -> tuple[dict, dict, dict, dict]:
        snaps = self._all_snapshots()
        if snaps is None:
            with self._lock:
                return (dict(self.counters), {k: list(v) for k, v in self.hist_counts.items()}, dict(self.hist_sum),
                        {k: list(v) for k, v in self.recent.items()})
        counters: dict = defaultdict(float)
        hist: dict = {}
        hsum: dict = defaultdict(float)
        recent: dict = defaultdict(list)
        for snap in snaps:
            for n, lbl, v in snap["counters"]:
                counters[(n, tuple(tuple(x) for x in lbl))] += v
            for k, counts in snap["hist_counts"].items():
                hist[k] = [a + b for a, b in zip(hist.get(k, [0] * len(counts)), counts)]
            for k, v in snap["hist_sum"].items():
                hsum[k] += v
            for k, v in snap["recent"].items():
                recent[k].extend(v)
        return dict(counters), hist, dict(hsum), dict(recent)

    def start_publisher(self, interval: float = 5.0) -> None:
        """Background thread: keep this worker's snapshot fresh in Redis (no-op without Redis)."""
        from app.core.cache import get_cache

        def loop() -> None:
            stop = threading.Event()
            while not stop.wait(interval):
                client = get_cache().redis
                if client is not None:
                    try:
                        self.publish(client)
                    except Exception:
                        pass

        threading.Thread(target=loop, name="metrics-publisher", daemon=True).start()

    # ---- queries ------------------------------------------------------------------------------
    def percentile(self, name: str, q: float) -> float | None:
        values = sorted(self._merged()[3].get(name, []))
        if not values:
            return None
        idx = min(len(values) - 1, int(round(q * (len(values) - 1))))
        return round(values[idx], 2)

    def counter_value(self, name: str, **labels) -> float:
        return self.counters.get((name, tuple(sorted(labels.items()))), 0.0)

    def counters_by_label(self, name: str, label: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for (n, labels), v in self._merged()[0].items():
            if n == name:
                key = dict(labels).get(label, "")
                out[key] = out.get(key, 0) + v
        return out

    def render(self) -> str:
        counters, hist, hsum, _ = self._merged()
        lines: list[str] = []
        for (name, labels), value in sorted(counters.items()):
            lbl = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f"shurokkha_{name}{{{lbl}}} {value}")
        for name, counts in hist.items():
            cumulative = 0
            lines.append(f"# TYPE shurokkha_{name} histogram")
            for bound, c in zip(_LATENCY_BUCKETS_MS + ["+Inf"], counts):
                cumulative += c
                lines.append(f'shurokkha_{name}_bucket{{le="{bound}"}} {cumulative}')
            lines.append(f"shurokkha_{name}_sum {hsum.get(name, 0.0)}")
            lines.append(f"shurokkha_{name}_count {cumulative}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
