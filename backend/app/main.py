"""Shurokkha API: AI trust & financial-safety copilot (FastAPI entry point)."""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select, text

from app.api.deps import get_gateway, get_retriever
from app.api.v1 import admin, auth, cases, insights, score, simulator, study
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.logging import request_id_var, setup_logging
from app.core.metrics import metrics
from app.core.ratelimit import RateLimitMiddleware
from app.db.database import init_db, session_scope
from app.db.models import Alert
from app.services.state import get_state

logger = logging.getLogger("shurokkha")


def seed_alerts() -> int:
    """Load analyst-console demo alerts (test window of the synthetic data) once."""
    settings = get_settings()
    path = settings.data_dir / "seed_alerts.json"
    with session_scope() as db:
        if (db.scalar(select(func.count()).select_from(Alert)) or 0) > 0 or not path.exists():
            return 0
        seeds = json.loads(path.read_text(encoding="utf-8"))
        now = time.time()
        for s in seeds:
            db.add(Alert(**s, source="seed", created_at=now - (seeds[-1]["tx_ts"] - s["tx_ts"])))
        return len(seeds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging()
    started = time.time()
    with get_cache().lock("migrate", timeout=120):  # several workers boot at once
        init_db()
    state = get_state()
    state.boot()
    if settings.seed_on_boot:
        with get_cache().lock("seed-alerts"):
            n = seed_alerts()
        if n:
            logger.info("seeded alerts", extra={"extra_fields": {"count": n}})
    get_retriever()
    state.start_background()
    metrics.start_publisher()
    logger.info("startup complete", extra={"extra_fields": {
        "seconds": round(time.time() - started, 2), "model": state.bundle.version if state.bundle else None,
        "llm": get_gateway().status(), "degraded": state.degraded}})
    yield
    state.stop()


settings = get_settings()
app = FastAPI(
    title="Shurokkha API",
    version="1.0.0",
    description="Real-time transaction risk scoring, scam interruption, mule-ring detection and an evidence-grounded "
                "investigation copilot for MFS. All data is synthetic.",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled error")
        metrics.inc("http_errors_total", path=request.url.path)
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
    finally:
        request_id_var.reset(token)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = rid
    response.headers["x-response-time-ms"] = f"{elapsed:.1f}"
    metrics.inc("http_requests_total", method=request.method, status=str(response.status_code))
    return response


for r in (auth.router, score.router, simulator.router, cases.router, insights.router, admin.router, study.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": "Shurokkha API", "docs": "/docs", "health": "/health/ready"}


@app.get("/health/live", tags=["ops"])
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", tags=["ops"])
def ready():
    state = get_state()
    checks: dict = {}
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
    checks["model"] = state.bundle.version if state.bundle else "missing (rules-only mode)"
    checks["detectors"] = state.detectors.names if state.detectors else []
    checks["policy_version"] = state.policy.version
    checks["graph_snapshot_wallets"] = len(state.graph.snapshot)
    checks["llm"] = get_gateway().status()
    checks["cache"] = get_cache().backend
    checks["online_state"] = "redis (shared by all workers)" if state.shared_state else "memory (single worker)"
    healthy = checks["database"] == "ok" and bool(checks["detectors"])
    status = "ok" if healthy and not state.degraded else ("degraded" if healthy else "unavailable")
    return JSONResponse({"status": status, "degraded": state.degraded, "checks": checks}, status_code=200 if healthy else 503)


@app.get("/metrics", include_in_schema=False)
def prometheus() -> PlainTextResponse:
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
