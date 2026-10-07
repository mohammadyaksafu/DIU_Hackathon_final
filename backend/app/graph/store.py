"""Online graph store: trailing edge window + latest snapshot + k-hop subgraph queries."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.features.engine import DAY
from app.graph.snapshot import GRAPH_EDGE_TYPES, compute_snapshot

GRAPH_WINDOW_DAYS = 14


class GraphStore:
    def __init__(self, window_days: int = GRAPH_WINDOW_DAYS) -> None:
        self.window = window_days * DAY
        self.edges: deque = deque()  # (ts, src, dst, amount, type)
        self.snapshot: dict[str, dict] = {}
        self.snapshot_built_at: float | None = None
        self.shared = None  # features.store.SharedEdges when several workers share live edges via Redis
        self._lock = threading.RLock()

    def add_edge(self, tx: dict) -> None:
        if tx["type"] not in GRAPH_EDGE_TYPES:
            return
        edge = (float(tx["ts"]), tx["sender"], tx["receiver"], float(tx["amount"]), tx["type"])
        if self.shared is not None:
            self.shared.push(edge)
            self._sync()
            return
        with self._lock:
            self.edges.append(edge)

    def _sync(self) -> None:
        """Pull live edges that other workers added (no-op without Redis)."""
        if self.shared is None:
            return
        with self._lock:
            self.edges.extend(self.shared.pull())

    def _prune(self) -> None:
        if not self.edges:
            return
        cutoff = self.edges[-1][0] - self.window
        while self.edges and self.edges[0][0] < cutoff:
            self.edges.popleft()

    def refresh(self) -> dict:
        self._sync()
        with self._lock:
            self._prune()
            edges = list(self.edges)
        snap = compute_snapshot(edges)
        with self._lock:
            self.snapshot = snap
            self.snapshot_built_at = time.time()
        return snap

    def subgraph(self, wallet: str, hops: int = 2, max_nodes: int = 60) -> dict:
        """k-hop neighbourhood (both directions) aggregated by wallet pair."""
        self._sync()
        with self._lock:
            edges = list(self.edges)
            snap = self.snapshot
        adj: dict[str, set] = defaultdict(set)
        agg: dict[tuple, list] = {}
        for ts, src, dst, amount, ttype in edges:
            adj[src].add(dst)
            adj[dst].add(src)
            key = (src, dst)
            if key not in agg:
                agg[key] = [0, 0.0, ttype, ts]
            agg[key][0] += 1
            agg[key][1] += amount
            agg[key][3] = max(agg[key][3], ts)

        nodes = {wallet}
        frontier = {wallet}
        for _ in range(hops):
            nxt = set()
            for node in frontier:
                # Agents/merchants are hubs; do not expand through them.
                if node != wallet and node[:1] in ("A", "M"):
                    continue
                for nb in sorted(adj.get(node, ())):
                    if nb not in nodes and len(nodes) + len(nxt) < max_nodes:
                        nxt.add(nb)
            nodes |= nxt
            frontier = nxt

        out_nodes = []
        for node in nodes:
            info = snap.get(node, {})
            kind = {"A": "agent", "M": "merchant", "E": "enterprise"}.get(node[:1], "customer")
            out_nodes.append(
                {
                    "id": node,
                    "kind": kind,
                    "community": info.get("comm", -1),
                    "in_deg": info.get("in_deg", 0),
                    "comm_fanin": info.get("comm_fanin", 0.0),
                    "comm_cashout": info.get("comm_cashout", 0.0),
                    "fwd_ratio": info.get("fwd_ratio", 0.0),
                    "focus": node == wallet,
                }
            )
        out_edges = [
            {"source": s, "target": d, "count": c, "amount": round(a, 2), "type": t, "last_ts": lt}
            for (s, d), (c, a, t, lt) in agg.items()
            if s in nodes and d in nodes
        ]
        return {"wallet": wallet, "hops": hops, "nodes": out_nodes, "edges": out_edges, "snapshot": snap.get(wallet)}
