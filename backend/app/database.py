"""
Database setup — SQLAlchemy + SQLite
"""
from __future__ import annotations

import os
from sqlalchemy import create_engine, text
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


# ─────────────────────────────────────────────────────────────────────────────
# Migrations versionnées
# ─────────────────────────────────────────────────────────────────────────────

def _apply_migrations():
    """
    Migrations manuelles pour les colonnes ajoutées après la création initiale.
    Chaque migration est identifiée par un numéro et ne s'applique qu'une seule fois
    (enregistrée dans la table `db_migrations`).

    SQLite ne supporte pas ALTER TABLE DROP COLUMN — uniquement ADD COLUMN.
    """
    with engine.connect() as conn:
        # Créer la table de versioning si elle n'existe pas
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS db_migrations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                version    TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.commit()

        def _applied(version: str) -> bool:
            row = conn.execute(
                text("SELECT 1 FROM db_migrations WHERE version = :v"),
                {"v": version},
            ).fetchone()
            return row is not None

        def _mark_applied(version: str) -> None:
            conn.execute(
                text("INSERT OR IGNORE INTO db_migrations (version) VALUES (:v)"),
                {"v": version},
            )
            conn.commit()

        # ── 001 : colonne is_admin ────────────────────────────────────────────
        if not _applied("001_is_admin"):
            _add_column_if_missing(conn, "users", "is_admin", "BOOLEAN DEFAULT 0 NOT NULL")
            _mark_applied("001_is_admin")

        # ── 002 : lien Stripe permanent ───────────────────────────────────────
        if not _applied("002_stripe_customer_id"):
            _add_column_if_missing(conn, "users", "stripe_customer_id", "TEXT")
            _mark_applied("002_stripe_customer_id")

        # ── 003 : surveillance élargie (SSL, ports, techno) ───────────────────
        if not _applied("003_monitoring_extended"):
            _add_column_if_missing(conn, "monitored_domains", "last_ssl_expiry_days", "INTEGER")
            _add_column_if_missing(conn, "monitored_domains", "last_open_ports",      "TEXT")
            _add_column_if_missing(conn, "monitored_domains", "last_technologies",    "TEXT")
            _mark_applied("003_monitoring_extended")

        # ── 004 : scan programmé par domaine ──────────────────────────────────
        if not _applied("004_scan_schedule"):
            _add_column_if_missing(conn, "monitored_domains", "scan_frequency", "TEXT DEFAULT 'weekly'")
            _add_column_if_missing(conn, "monitored_domains", "email_report",   "BOOLEAN DEFAULT 0")
            _mark_applied("004_scan_schedule")

        # ── 005 : white-branding Pro ──────────────────────────────────────────
        if not _applied("005_white_branding"):
            _add_column_if_missing(conn, "users", "wb_enabled",       "BOOLEAN DEFAULT 0")
            _add_column_if_missing(conn, "users", "wb_company_name",  "TEXT")
            _add_column_if_missing(conn, "users", "wb_logo_b64",      "TEXT")
            _add_column_if_missing(conn, "users", "wb_primary_color", "TEXT")
            _mark_applied("005_white_branding")

        # ── 006 : détails complets du scan pour le PDF ───────────────────────
        if not _applied("006_scan_details_json"):
            _add_column_if_missing(conn, "scan_history", "scan_details_json", "TEXT")
            _mark_applied("006_scan_details_json")

        # ── 007 : partage public d'un scan (/r/{uuid}) ───────────────────────
        if not _applied("007_public_share"):
            _add_column_if_missing(conn, "scan_history", "public_share", "BOOLEAN DEFAULT 0 NOT NULL")
            _mark_applied("007_public_share")

        # ── 008 : login_attempts — table créée par Base.metadata.create_all() ─
        if not _applied("008_login_attempts_table"):
            # Rien à ALTER TABLE — la table est gérée par SQLAlchemy ORM
            _mark_applied("008_login_attempts_table")

        # ── 009 : mot de passe oublié — reset token ───────────────────────────
        if not _applied("009_password_reset"):
            _add_column_if_missing(conn, "users", "password_reset_token",   "TEXT")
            _add_column_if_missing(conn, "users", "password_reset_expires", "DATETIME")
            _mark_applied("009_password_reset")

        # ── 010 : Application Scanning — table verified_apps ─────────────────
        if not _applied("010_verified_apps"):
            # La table est gérée par SQLAlchemy ORM (Base.metadata.create_all)
            _mark_applied("010_verified_apps")

        # ── 011 : Blog links — table blog_links ───────────────────────────────
        if not _applied("011_blog_links"):
            # La table est gérée par SQLAlchemy ORM (Base.metadata.create_all)
            _mark_applied("011_blog_links")

        # ── 012 : Monitoring alertes configurables ────────────────────────────
        if not _applied("012_monitoring_alert_config"):
            _add_column_if_missing(conn, "monitored_domains", "ssl_alert_days", "INTEGER DEFAULT 30")
            _add_column_if_missing(conn, "monitored_domains", "alert_config",   "TEXT")
            _mark_applied("012_monitoring_alert_config")

        # ── 013 : Intégrations Slack / Teams ─────────────────────────────────
        if not _applied("013_user_integrations"):
            _add_column_if_missing(conn, "users", "slack_webhook_url", "VARCHAR(512)")
            _add_column_if_missing(conn, "users", "teams_webhook_url", "VARCHAR(512)")
            _mark_applied("013_user_integrations")


# ─────────────────────────────────────────────────────────────────────────────
# Utilitaire : ajouter une colonne si absente
# ─────────────────────────────────────────────────────────────────────────────

def _add_column_if_missing(conn, table: str, column: str, column_def: str):
    """Ajoute une colonne à une table si elle n'existe pas encore."""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    existing = {row[1] for row in result}
    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}"))
        conn.commit()
        print(f"✅ Migration : colonne '{column}' ajoutée à la table '{table}'")
