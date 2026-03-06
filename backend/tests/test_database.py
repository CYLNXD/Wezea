"""
Tests pour app/database.py — migrations, get_db, _add_column_if_missing.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from unittest.mock import patch


def _fresh_engine():
    """Crée un moteur SQLite in-memory frais (isolé)."""
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


# ─────────────────────────────────────────────────────────────────────────────
# get_db — lines 23-27
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDb:
    """Couvre get_db() lines 23-27 (yield + close)."""

    def test_get_db_yields_a_session_and_closes(self):
        """Appel direct de get_db() : yield une session, puis ferme proprement."""
        from app.database import get_db

        gen = get_db()
        db = next(gen)  # covers: db = SessionLocal(), yield db (lines 23-25)
        assert db is not None
        try:
            next(gen)    # covers: finally: db.close() (lines 26-27)
        except StopIteration:
            pass  # normal — le générateur est épuisé après le yield


# ─────────────────────────────────────────────────────────────────────────────
# _add_column_if_missing — lines 133-138
# ─────────────────────────────────────────────────────────────────────────────

class TestAddColumnIfMissing:
    """Couvre _add_column_if_missing (lines 133-138)."""

    def test_adds_column_when_absent(self):
        """La colonne n'existe pas → ALTER TABLE + print (lines 135-138)."""
        from app.database import _add_column_if_missing

        eng = _fresh_engine()
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE t1 (id INTEGER PRIMARY KEY)"))
            _add_column_if_missing(conn, "t1", "new_col", "TEXT")

        # Vérifier via une nouvelle connexion (l'ancienne transaction est close après commit)
        with eng.connect() as conn2:
            result = conn2.execute(text("PRAGMA table_info(t1)"))
            cols = [row[1] for row in result]

        assert "new_col" in cols

    def test_skips_existing_column(self):
        """La colonne existe déjà → pas d'erreur, pas d'ALTER TABLE (line 135 False)."""
        from app.database import _add_column_if_missing

        eng = _fresh_engine()
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE t2 (id INTEGER PRIMARY KEY, existing_col TEXT)"))
            # Ne doit pas lever
            _add_column_if_missing(conn, "t2", "existing_col", "TEXT")
            result = conn.execute(text("PRAGMA table_info(t2)"))
            cols = [row[1] for row in result]

        assert cols.count("existing_col") == 1  # pas de doublon


# ─────────────────────────────────────────────────────────────────────────────
# _apply_migrations — lines 60-124 (nested _applied, _mark_applied, migrations)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyMigrations:
    """Couvre _apply_migrations() sur une DB fraîche (toutes les migrations exécutées)."""

    def _run_migrations_on_fresh_engine(self):
        """Crée un moteur, applique les tables, puis _apply_migrations()."""
        import app.database as db_mod
        import app.models  # noqa: F401 — enregistre les modèles dans Base.metadata

        eng = _fresh_engine()
        # Créer tous les modèles (colonnes actuelles)
        db_mod.Base.metadata.create_all(bind=eng)

        with patch.object(db_mod, "engine", eng):
            db_mod._apply_migrations()

        return eng

    def test_apply_migrations_creates_migrations_table(self):
        """_apply_migrations() crée la table db_migrations si absente."""
        eng = self._run_migrations_on_fresh_engine()
        with eng.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='db_migrations'"
            ))
            tables = [row[0] for row in result]
        assert "db_migrations" in tables

    def test_apply_migrations_records_all_versions(self):
        """Toutes les migrations 001-009 sont enregistrées (lines 77,82,89,95,103,108,113,118,124)."""
        eng = self._run_migrations_on_fresh_engine()
        with eng.connect() as conn:
            result = conn.execute(text("SELECT version FROM db_migrations ORDER BY version"))
            versions = {row[0] for row in result}

        expected = {
            "001_is_admin", "002_stripe_customer_id", "003_monitoring_extended",
            "004_scan_schedule", "005_white_branding", "006_scan_details_json",
            "007_public_share", "008_login_attempts_table", "009_password_reset",
        }
        assert expected == versions

    def test_apply_migrations_idempotent(self):
        """Double appel de _apply_migrations() → pas d'erreur (if not _applied → False)."""
        import app.database as db_mod
        import app.models  # noqa: F401

        eng = _fresh_engine()
        db_mod.Base.metadata.create_all(bind=eng)

        with patch.object(db_mod, "engine", eng):
            db_mod._apply_migrations()  # premier appel — applique toutes les migrations
            db_mod._apply_migrations()  # deuxième appel — toutes déjà appliquées (no-op)

        # Pas d'exception = succès; chaque version doit apparaître exactement une fois
        with eng.connect() as conn:
            result = conn.execute(text("SELECT version, COUNT(*) FROM db_migrations GROUP BY version"))
            for version, count in result:
                assert count == 1, f"migration {version} enregistrée {count} fois"

    def test_add_column_if_missing_on_legacy_table(self):
        """Sur une table sans la colonne → ALTER TABLE exécuté (line 136-138 via migration réelle)."""
        import app.database as db_mod
        import app.models  # noqa: F401

        eng = _fresh_engine()
        # Créer SEULEMENT la table users avec une colonne minimale (simule une ancienne version)
        with eng.begin() as conn:
            conn.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL
                )
            """))
            # Créer aussi les tables requises pour les migrations monitoring
            conn.execute(text("""
                CREATE TABLE monitored_domains (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT NOT NULL
                )
            """))

        with patch.object(db_mod, "engine", eng):
            db_mod._apply_migrations()

        # Vérifier que is_admin a été ajouté (lines 76-77)
        with eng.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(users)"))
            cols = [row[1] for row in result]

        assert "is_admin" in cols
        assert "stripe_customer_id" in cols
        assert "password_reset_token" in cols


# ─────────────────────────────────────────────────────────────────────────────
# init_db — ligne 34
# ─────────────────────────────────────────────────────────────────────────────

class TestInitDb:
    """Couvre init_db() : create_all + _apply_migrations."""

    def test_init_db_creates_tables_and_applies_migrations(self):
        """init_db() → tables créées + migrations appliquées."""
        import app.database as db_mod
        import app.models  # noqa: F401

        eng = _fresh_engine()
        with patch.object(db_mod, "engine", eng):
            db_mod.init_db()

        with eng.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ))
            tables = [row[0] for row in result]

        assert "users" in tables
        assert "db_migrations" in tables
