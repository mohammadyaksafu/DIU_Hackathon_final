"""Per-client-IP rate limiter middleware.

With Redis the limit is shared by every API worker and survives restarts (fixed one-minute window);
without Redis, or if Redis fails, it falls back to an in-process token bucket.
"""
from __future__ import annotations

import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.cache import get_cache


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int) -> None:
        super().__init__(app)
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def _allow_redis(self, client, key: str) -> bool:
        window = int(time.time() // 60)
        rkey = f"shurokkha:rl:{key}:{window}"
        pipe = client.pipeline()
        pipe.incr(rkey)
        pipe.expire(rkey, 61)
        count, _ = pipe.execute()
        return int(count) <= self.capacity

    def _allow_memory(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            tokens, last = self.buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            allowed = tokens >= 1
            self.buckets[key] = (tokens - 1 if allowed else tokens, now)
        return allowed

    async def dispatch(self, request, call_next):
        if self.capacity <= 0 or request.url.path.startswith("/health"):
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        client = get_cache().redis
        try:
            allowed = self._allow_redis(client, key) if client is not None else self._allow_memory(key)
        except Exception:
            allowed = self._allow_memory(key)
        if not allowed:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "1"})
        return await call_next(request)
