"""
Database setup — SQLAlchemy + SQLite
"""
from __future__ import annotations

import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("cyberhealth.database")

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./cyberhealth.db")

engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False}  # needed for SQLite
)

# WAL mode améliore la concurrence en lecture/écriture (uvicorn multi-workers)
if DB_PATH.startswith("sqlite"):
    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

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

        # ── 015 : 2FA TOTP ────────────────────────────────────────────────────
        if not _applied("015_mfa"):
            _add_column_if_missing(conn, "users", "mfa_enabled", "BOOLEAN DEFAULT 0 NOT NULL")
            _add_column_if_missing(conn, "users", "mfa_secret",  "VARCHAR(64)")
            _mark_applied("015_mfa")

        if not _applied("014_api_key_hash"):
            _add_column_if_missing(conn, "users", "api_key_hash", "VARCHAR(64)")
            _add_column_if_missing(conn, "users", "api_key_hint", "VARCHAR(24)")
            # Backfill : hacher les clés existantes en Python (nécessite SECRET_KEY)
            try:
                from app.auth import hash_api_key, mask_api_key
                rows = conn.execute(
                    text("SELECT id, api_key FROM users WHERE api_key IS NOT NULL AND api_key_hash IS NULL")
                ).fetchall()
                for row in rows:
                    h    = hash_api_key(row[1])
                    hint = mask_api_key(row[1])
                    conn.execute(
                        text("UPDATE users SET api_key_hash=:h, api_key_hint=:hint WHERE id=:id"),
                        {"h": h, "hint": hint, "id": row[0]},
                    )
                if rows:
                    conn.commit()
                    logger.info("Migration 014 : %d clé(s) API hachée(s).", len(rows))
            except Exception as exc:  # pragma: no cover
                logger.warning("Migration 014 backfill échouée : %s", exc)
            _mark_applied("014_api_key_hash")

        # ── 016 : index sur login_attempts.failed_at (performance cleanup) ──
        if not _applied("016_login_attempts_index"):
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_login_attempts_failed_at "
                "ON login_attempts (failed_at)"
            ))
            conn.commit()
            _mark_applied("016_login_attempts_index")

        # ── 017 : Programme partenaire — table partners ────────────────────
        if not _applied("017_partners"):
            # La table est gérée par SQLAlchemy ORM (Base.metadata.create_all)
            _mark_applied("017_partners")

        # ── 018 : Referral partenaire sur users ──────────────────────────────
        if not _applied("018_user_referral"):
            _add_column_if_missing(conn, "users", "referred_by_partner_id", "INTEGER")
            _mark_applied("018_user_referral")

        # ── 019 : Tracking récompense partenaire ─────────────────────────────
        if not _applied("019_partner_reward_tracking"):
            _add_column_if_missing(conn, "partners", "referral_reward_used", "BOOLEAN DEFAULT 0")
            _mark_applied("019_partner_reward_tracking")

        # ── 020 : Checklist conformité NIS2/RGPD ───────────────────────────────
        if not _applied("020_compliance_checklists"):
            # Table gérée par l'ORM (Base.metadata.create_all)
            _mark_applied("020_compliance_checklists")

        # ── 021 : Articles de blog ────────────────────────────────────────────
        if not _applied("021_blog_articles"):
            # Table gérée par l'ORM (Base.metadata.create_all)
            _mark_applied("021_blog_articles")


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
        logger.info("Migration : colonne '%s' ajoutée à la table '%s'", column, table)
