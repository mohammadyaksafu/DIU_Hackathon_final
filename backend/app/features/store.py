"""Shared online state in Redis: per-wallet feature state and live graph edges.

In memory (the default) every API worker would keep its own copy of the online state, so the API had
to run as one worker and lost live history on restart. With REDIS_URL set, the warm state built by
the training replay is copied into Redis once, every worker reads and writes the same wallets, and
live history survives restarts.

`RedisWalletStore` behaves like the `dict` the feature engine already uses (`get`, `[]`, `in`), so
the engine code is identical offline (training replay, plain dict) and online (Redis).
"""
from __future__ import annotations

import logging
from collections import deque
from contextlib import contextmanager

import orjson

from app.features.engine import WalletState

logger = logging.getLogger(__name__)

PREFIX = "shurokkha:fs:"
WALLET = PREFIX + "w:"
SEEDED = PREFIX + "seeded"
EDGES = PREFIX + "edges"


def dump_wallet(st: WalletState) -> bytes:
    return orjson.dumps({
        "first_seen": st.first_seen, "out": list(st.out), "inn": list(st.inn), "known_out": st.known_out,
        "known_in": sorted(st.known_in), "n_out": st.n_out, "mean": st.mean, "m2": st.m2, "hours": st.hours,
        "devices": st.devices, "last_geo": st.last_geo, "sim_swap": st.sim_swap, "pwd_reset": st.pwd_reset,
    })


def load_wallet(raw: bytes) -> WalletState:
    d = orjson.loads(raw)
    return WalletState(
        first_seen=d["first_seen"], out=deque(tuple(x) for x in d["out"]), inn=deque(tuple(x) for x in d["inn"]),
        known_out=d["known_out"], known_in=set(d["known_in"]), n_out=d["n_out"], mean=d["mean"], m2=d["m2"],
        hours=d["hours"], devices=d["devices"], last_geo=d["last_geo"], sim_swap=d["sim_swap"], pwd_reset=d["pwd_reset"],
    )


class RedisWalletStore:
    """dict-like view of wallet states stored in Redis (one JSON value per wallet)."""

    def __init__(self, client) -> None:
        self.r = client

    def get(self, wallet_id: str, default=None):
        raw = self.r.get(WALLET + wallet_id)
        return load_wallet(raw) if raw else default

    def __getitem__(self, wallet_id: str) -> WalletState:
        st = self.get(wallet_id)
        if st is None:
            raise KeyError(wallet_id)
        return st

    def __setitem__(self, wallet_id: str, st: WalletState) -> None:
        self.r.set(WALLET + wallet_id, dump_wallet(st))

    def __contains__(self, wallet_id: str) -> bool:
        return bool(self.r.exists(WALLET + wallet_id))

    def __len__(self) -> int:
        return sum(1 for _ in self.r.scan_iter(WALLET + "*", count=1000))

    @contextmanager
    def locked(self, *wallet_ids: str):
        """Serialise read-modify-write of the same wallets across workers (sorted => no deadlock)."""
        locks = [self.r.lock(f"{PREFIX}lock:{w}", timeout=5, blocking_timeout=5) for w in sorted(set(wallet_ids))]
        held = []
        try:
            for lock in locks:
                if not lock.acquire():
                    raise TimeoutError("wallet state is locked by another worker")
                held.append(lock)
            yield
        finally:
            for lock in held:
                try:
                    lock.release()
                except Exception:
                    pass


def seed(client, wallets: dict, fingerprint: str) -> bool:
    """Copy the warm in-memory state into Redis once per dataset; returns True if it seeded.

    The fingerprint identifies the training replay (model version + end of history). If Redis already
    holds that dataset, it is kept as is, including live updates made since, which is what lets the
    online state survive a restart.
    """
    if client.get(SEEDED) == fingerprint.encode():
        return False
    for key in client.scan_iter(WALLET + "*", count=1000):
        client.delete(key)
    client.delete(EDGES)
    pipe = client.pipeline(transaction=False)
    for i, (wid, st) in enumerate(wallets.items(), 1):
        pipe.set(WALLET + wid, dump_wallet(st))
        if i % 2000 == 0:
            pipe.execute()
    pipe.execute()
    client.set(SEEDED, fingerprint)
    logger.info("feature store seeded in redis", extra={"extra_fields": {"wallets": len(wallets)}})
    return True


class SharedEdges:
    """Live graph edges appended by any worker; each worker pulls the ones it has not seen yet."""

    def __init__(self, client) -> None:
        self.r = client
        self.seen = 0

    def push(self, edge: tuple) -> None:
        self.r.rpush(EDGES, orjson.dumps(edge))

    def pull(self) -> list[tuple]:
        raw = self.r.lrange(EDGES, self.seen, -1)
        self.seen += len(raw)
        return [tuple(orjson.loads(x)) for x in raw]


def connect(url: str):
    """A Redis client for the online state (longer timeouts than the cache: seeding moves bulk data)."""
    import redis

    client = redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=2)
    client.ping()
    return client
