"""Application settings, loaded from environment variables (see .env.example)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Shurokkha API"
    environment: str = "development"

    # Paths
    data_dir: Path = BACKEND_DIR / "data"
    models_dir: Path = BACKEND_DIR / "models" / "registry"
    config_dir: Path = BACKEND_DIR / "config"
    knowledge_dir: Path = BACKEND_DIR / "knowledge" / "sop"

    # Storage
    database_url: str = ""  # default: SQLite file inside data_dir
    redis_url: str = ""  # optional; in-memory cache when empty
    # Threads per worker for request handlers. Scoring is CPU-bound Python, so a few threads per worker
    # (and more workers) beat many threads fighting over one interpreter lock.
    threadpool_size: int = 8
    db_pool_size: int = 20  # PostgreSQL connections per API worker (plus the same again as overflow)
    # Online feature state: auto => Redis when REDIS_URL is reachable (several workers), else memory (one worker)
    feature_store: str = "auto"  # auto | memory | redis

    # Model / scoring
    active_model: str = ""  # registry version; empty => models/registry/ACTIVE
    latency_budget_ms: float = 150.0
    graph_refresh_seconds: int = 600
    seed_on_boot: bool = True
    auto_bootstrap: bool = True  # generate data + train when no model exists

    # GenAI
    llm_provider: str = "auto"  # auto | gemini | anthropic | none
    llm_model: str = "claude-opus-5-5"
    gemini_model: str = "gemini-3.8-flash"
    llm_timeout_seconds: float = 30.0
    llm_effort: str = "low"
    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    # Security
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 720
    auth_required: bool = True
    demo_password: str = "demo123"
    # The admin account never uses the public demo password: the web app ships DEMO_PASSWORD to every
    # browser. Empty => admin uses DEMO_PASSWORD only in development; in production admin login is off.
    admin_password: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_per_minute: int = 1200

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            url = self.database_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        return f"sqlite:///{(self.data_dir / 'shurokkha.db').as_posix()}"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_llm_provider(self) -> str:
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.gemini_api_key or os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        has_key = bool(self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"))
        return "anthropic" if has_key else "none"


@lru_cache
def get_settings() -> Settings:
    return Settings()
