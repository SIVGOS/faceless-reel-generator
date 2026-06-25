"""Additive schema migration: idempotent, adds missing columns, no-op on fresh DB.

No network or heavy deps — a temp SQLite file only.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.database import _apply_additive_migrations


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_adds_missing_columns_to_legacy_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'legacy.db'}")
    # Simulate a pre-v2 DB: users without is_admin, projects without bg/music.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, prompt TEXT)"))

    _apply_additive_migrations(engine)

    assert "is_admin" in _columns(engine, "users")
    assert {"background", "music"} <= _columns(engine, "projects")


def test_migration_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, prompt TEXT)"))

    _apply_additive_migrations(engine)
    # Second run must not raise (columns already present).
    _apply_additive_migrations(engine)
    assert "is_admin" in _columns(engine, "users")


def test_noop_on_empty_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'empty.db'}")
    # No tables yet — create_all would build them with columns already present.
    _apply_additive_migrations(engine)  # must not raise
    assert inspect(engine).get_table_names() == []
