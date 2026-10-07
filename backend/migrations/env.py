"""Alembic environment: uses the app's engine and metadata, so SQLite and PostgreSQL share one history."""
from __future__ import annotations

from alembic import context

from app.db import models  # noqa: F401  (register tables)
from app.db.database import Base, get_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=str(get_engine().url), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:  # called from init_db() with an open connection
        _run(connection)
        return
    with get_engine().connect() as conn:
        _run(conn)


def _run(connection) -> None:
    # render_as_batch: SQLite cannot ALTER most columns in place; batch mode copies the table instead.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
