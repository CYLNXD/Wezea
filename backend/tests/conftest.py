"""
Fixtures pytest pour CyberHealth Scanner
-----------------------------------------
- DB en mémoire (SQLite in-memory) isolée par test — ne persiste JAMAIS sur disque
- Override des dépendances FastAPI (get_db)
- Mocks des services externes (Brevo, scheduler)
"""
import os
import uuid

# ── Variables d'env pour les tests — définies AVANT tout import de l'app ──────
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only-32-chars-min")
os.environ.setdefault("CORS_ORIGINS", "http://testserver")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("COOKIE_SAMESITE", "lax")

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# ── DB en mémoire — isolée, ne persiste JAMAIS sur disque ─────────────────────
TEST_DB_URL = "sqlite://"   # ← ":memory:" implicite ; StaticPool = même connexion partagée


@pytest.fixture(scope="session", autouse=True)
def _patch_scheduler():
    """Empêche le scheduler de démarrer pendant les tests."""
    with patch("app.scheduler.start_scheduler", return_value=False):
        yield



@pytest.fixture(scope="session", autouse=True)
def _patch_brevo():
    """Mock tous les appels Brevo (email) pour éviter des envois réels."""
    with (
        patch("app.services.brevo_service.send_welcome_email", new=AsyncMock(return_value=True)),
        patch("app.services.brevo_service.add_registered_user_contact", new=AsyncMock(return_value=True)),
        patch("app.services.brevo_service.update_brevo_contact", new=AsyncMock(return_value=True)),
        patch("app.services.brevo_service.delete_brevo_contact", new=AsyncMock(return_value=True)),
        patch("app.services.brevo_service.send_password_reset_email", new=AsyncMock(return_value=True)),
    ):
        yield


@pytest.fixture()
def test_engine():
    """
    Moteur SQLite en mémoire — scope=function → DB fraîche à chaque test.
    StaticPool garantit que toutes les connexions partagent la même DB en mémoire.

    IMPORTANT : importer app.models AVANT create_all() pour que Base.metadata
    connaisse toutes les tables. Sans cet import, la DB est créée vide quand le
    test est lancé en isolation (les modèles sont sinon importés plus tard, dans
    le fixture `client`, via `from app.main import app`).
    """
    import app.models  # noqa: F401 — enregistre tous les modèles dans Base.metadata
    from app.database import Base
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    """Session DB propre par test — rollback après chaque test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_session):
    """Client HTTP FastAPI avec DB de test injectée."""
    from app.main import app
    from app.database import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_user(db_session):
    """
    Crée un utilisateur directement en DB (sans appel HTTP /auth/register).
    Évite le rate limit sur /auth/register pour les tests qui n'ont pas besoin du flow HTTP.
    """
    from app.models import User
    from app.auth import hash_password, generate_api_key, hash_api_key, mask_api_key

    email = f"dbuser-{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPassword123"
    _raw_key = generate_api_key()
    user = User(
        email=email,
        password_hash=hash_password(password),
        plan="free",
        api_key=_raw_key,
        api_key_hash=hash_api_key(_raw_key),
        api_key_hint=mask_api_key(_raw_key),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return {"email": email, "password": password, "user_id": user.id}


@pytest.fixture()
def registered_user(client):
    """
    Crée et retourne un utilisateur inscrit avec son token JWT.
    Email unique par test (uuid) — évite tout conflit même si la DB n'est pas isolée.
    """
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/auth/register", json={
        "email": email,
        "password": "TestPassword123",
    })
    assert resp.status_code == 201, f"Register failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return {
        "email": email,
        "password": "TestPassword123",
        "token": data["access_token"],
        "user": data["user"],
    }
