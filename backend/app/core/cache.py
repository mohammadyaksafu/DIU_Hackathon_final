"""Small cache abstraction: Redis when REDIS_URL is set and reachable, else in-memory TTL dict.

Degrades silently to memory if Redis goes away (graceful degradation ladder, plan section 11).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager, nullcontext
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Cache:
    def __init__(self) -> None:
        self._mem: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._redis = None
        url = get_settings().redis_url
        if url:
            try:
                import redis  # optional dependency

                client = redis.Redis.from_url(url, socket_timeout=0.2, socket_connect_timeout=0.5)
                client.ping()
                self._redis = client
                logger.info("cache backend: redis")
            except Exception as exc:  # pragma: no cover - depends on infra
                logger.warning("redis unavailable, using in-memory cache: %s", exc)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    @property
    def redis(self):
        """The shared Redis client, or None when running on in-memory fallbacks."""
        return self._redis

    def lock(self, name: str, timeout: float = 60.0):
        """A lock shared by every API worker (Redis), or a no-op with a single in-memory worker."""
        if self._redis is None:
            return nullcontext()
        return _redis_lock(self._redis, f"shurokkha:lock:{name}", timeout)

    def get(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                self._redis = None
        with self._lock:
            item = self._mem.get(key)
            if not item:
                return None
            expires, raw = item
            if expires < time.time():
                self._mem.pop(key, None)
                return None
            return json.loads(raw)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        raw = json.dumps(value, default=str)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, raw)
                return
            except Exception:
                self._redis = None
        with self._lock:
            if len(self._mem) > 5000:
                self._mem.clear()
            self._mem[key] = (time.time() + ttl, raw)


@contextmanager
def _redis_lock(client, key: str, timeout: float):
    lock = client.lock(key, timeout=timeout, blocking_timeout=timeout)
    if not lock.acquire():
        raise TimeoutError(f"could not acquire {key}")
    try:
        yield
    finally:
        try:
            lock.release()
        except Exception:  # expired while held; the work is done either way
            pass


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
