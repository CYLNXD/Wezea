"""
Database setup — SQLAlchemy + SQLite
"""
from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./cyberhealth.db")

engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False}  # needed for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables on startup + migrations légères pour colonnes manquantes."""
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _apply_migrations()


def _apply_migrations():
    """
    Migrations manuelles pour les colonnes ajoutées après la création initiale.
    SQLite ne supporte pas ALTER TABLE DROP COLUMN, mais supporte ADD COLUMN.
    """
    with engine.connect() as conn:
        _add_column_if_missing(conn, "users", "is_admin", "BOOLEAN DEFAULT 0 NOT NULL")
        # ── Feature : surveillance élargie ───────────────────────────────
        _add_column_if_missing(conn, "monitored_domains", "last_ssl_expiry_days", "INTEGER")
        _add_column_if_missing(conn, "monitored_domains", "last_open_ports",      "TEXT")
        _add_column_if_missing(conn, "monitored_domains", "last_technologies",    "TEXT")
        # ── Feature : scan programmé ─────────────────────────────────────
        _add_column_if_missing(conn, "monitored_domains", "scan_frequency", "TEXT DEFAULT 'weekly'")
        _add_column_if_missing(conn, "monitored_domains", "email_report",   "BOOLEAN DEFAULT 0")
        # ── Feature : white-branding (Pro) ───────────────────────────────
        _add_column_if_missing(conn, "users", "wb_enabled",       "BOOLEAN DEFAULT 0")
        _add_column_if_missing(conn, "users", "wb_company_name",  "TEXT")
        _add_column_if_missing(conn, "users", "wb_logo_b64",      "TEXT")
        _add_column_if_missing(conn, "users", "wb_primary_color", "TEXT")


def _add_column_if_missing(conn, table: str, column: str, column_def: str):
    """Ajoute une colonne à une table si elle n'existe pas encore."""
    from sqlalchemy import text
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result}
    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}"))
        conn.commit()
        print(f"✅ Migration : colonne '{column}' ajoutée à la table '{table}'")
