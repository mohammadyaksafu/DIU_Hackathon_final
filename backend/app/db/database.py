"""SQLAlchemy engine/session. SQLite by default, PostgreSQL via DATABASE_URL."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        url = settings.sqlalchemy_url
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
        else:  # each worker serves up to 40 concurrent requests; do not make them queue for 5 connections
            kwargs.update(pool_size=settings.db_pool_size, max_overflow=settings.db_pool_size, pool_timeout=10)
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _sqlite_pragmas(conn, _):  # WAL => concurrent readers while writing
                cur = conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    with get_engine().begin() as conn:
        migrate(conn)


def migrate(conn) -> None:
    """Bring the schema to the latest Alembic revision (migrations/versions).

    Databases created before migrations existed (by create_all) are stamped at the initial revision
    first, so their data is kept and later migrations apply on top.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from app.core.config import BACKEND_DIR
    from app.db import models  # noqa: F401  (register tables)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["connection"] = conn
    tables = set(inspect(conn).get_table_names())
    if "alembic_version" not in tables and "alerts" in tables:
        command.stamp(cfg, "0001")
    command.upgrade(cfg, "head")


@contextmanager
def session_scope():
    get_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Used by tests to point at a fresh database."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
