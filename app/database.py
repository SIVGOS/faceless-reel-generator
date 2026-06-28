"""SQLAlchemy engine, session factory, and base class."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


# Additive, idempotent column migrations for already-created tables. SQLite's
# ADD COLUMN only accepts a constant default and no UNIQUE — fine for these.
# (table, column, DDL type + default). Each is applied only if absent, so this
# is safe to run on every startup. Column *renames* are not handled here: this
# project wipes its dev DB on breaking schema changes (pre-deploy, no prod data).
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("users", "is_admin", "BOOLEAN NOT NULL DEFAULT 0"),
    ("projects", "background", "VARCHAR(512)"),
    ("projects", "music", "VARCHAR(512)"),
    ("projects", "language", "VARCHAR(16) NOT NULL DEFAULT 'auto'"),
]


# check_same_thread=False is required because FastAPI may touch the
# connection across threads when running sync endpoints in the threadpool.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _apply_additive_migrations(bind: Engine) -> None:
    """Add any missing columns to existing tables. Idempotent, no-op on fresh DB."""
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    with bind.begin() as conn:
        for table, column, ddl in _ADDITIVE_COLUMNS:
            if table not in existing_tables:
                continue  # create_all just built it with the column already present
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    """Create all tables, then apply additive column migrations. Idempotent."""
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations(engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
