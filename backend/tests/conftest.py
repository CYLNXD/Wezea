"""
Fixtures pytest pour CyberHealth Scanner
-----------------------------------------
- DB en mémoire (SQLite) isolée pour chaque test
- Override des dépendances FastAPI (get_db)
- Mocks des services externes (Brevo, scheduler)
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# ── Base de données de test en mémoire ────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_cyberhealth.db"


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
    ):
        yield


@pytest.fixture(scope="session")
def test_engine():
    from app.database import Base
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


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
def registered_user(client):
    """Crée et retourne un utilisateur inscrit avec son token JWT."""
    resp = client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "TestPassword123",
    })
    assert resp.status_code == 201
    data = resp.json()
    return {
        "email": "test@example.com",
        "password": "TestPassword123",
        "token": data["access_token"],
        "user": data["user"],
    }
