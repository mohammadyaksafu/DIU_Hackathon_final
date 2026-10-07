# ---- Shurokkha API ----
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
# Generate the synthetic dataset and train the model at build time (deterministic, seed 42),
# so the container boots in seconds with a ready model and warm feature state.
RUN python -m pipelines.run_all
RUN useradd -m appuser && chown -R appuser /app
USER appuser
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fs http://localhost:${PORT}/health/live || exit 1
# WEB_CONCURRENCY > 1 needs REDIS_URL: the online feature state is then shared in Redis (see README "Scaling").
ENV WEB_CONCURRENCY=1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --workers ${WEB_CONCURRENCY}"]
