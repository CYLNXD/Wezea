"""
Tests : authentification (register, login, JWT, lockout, forgot/reset password)
"""
import pytest
from datetime import datetime, timedelta, timezone


# ─────────────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────────────

def test_register_success(client):
    resp = client.post("/auth/register", json={
        "email": "newuser@example.com",
        "password": "StrongPass123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["plan"] == "free"


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "StrongPass123"}
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()


def test_register_password_too_short(client):
    resp = client.post("/auth/register", json={
        "email": "short@example.com",
        "password": "abc",
    })
    assert resp.status_code == 422  # Pydantic validation error


def test_register_invalid_email(client):
    resp = client.post("/auth/register", json={
        "email": "not-an-email",
        "password": "ValidPass123",
    })
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

def test_login_success(client, registered_user):
    resp = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == registered_user["email"]


def test_login_wrong_password(client, registered_user):
    resp = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": "WrongPassword!",
    })
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


def test_login_unknown_email(client):
    resp = client.post("/auth/login", json={
        "email": "ghost@example.com",
        "password": "Whatever123",
    })
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# JWT / /auth/me
# ─────────────────────────────────────────────────────────────────────────────

def test_me_with_valid_token(client, registered_user):
    resp = client.get("/auth/me", headers={
        "Authorization": f"Bearer {registered_user['token']}"
    })
    assert resp.status_code == 200
    assert resp.json()["email"] == registered_user["email"]


def test_me_without_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_token(client):
    resp = client.get("/auth/me", headers={
        "Authorization": "Bearer invalidtoken.fake.jwt"
    })
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Lockout : 5 échecs consécutifs → 429
# ─────────────────────────────────────────────────────────────────────────────

def test_login_lockout_after_5_failures(client, registered_user):
    """Après 5 mauvais mots de passe, l'IP est bloquée pendant 15 min."""
    for _ in range(5):
        client.post("/auth/login", json={
            "email": registered_user["email"],
            "password": "BadPassword!",
        })
    resp = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": "BadPassword!",
    })
    assert resp.status_code == 429
    assert "tentatives" in resp.json()["detail"].lower() or "réessayez" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Mot de passe oublié — POST /auth/forgot-password
# ─────────────────────────────────────────────────────────────────────────────
# Note : on utilise `db_user` (création directe en DB) pour éviter le rate
# limit sur /auth/register qui est à 10/heure en production.

def test_forgot_password_returns_200_for_valid_email(client, db_user):
    """forgot-password retourne 200 même si l'email existe (anti-énumération)."""
    resp = client.post("/auth/forgot-password", json={"email": db_user["email"]})
    assert resp.status_code == 200
    assert "lien" in resp.json()["message"].lower() or "reset" in resp.json()["message"].lower()


def test_forgot_password_returns_200_for_unknown_email(client):
    """forgot-password retourne toujours 200 même si l'email n'existe pas."""
    resp = client.post("/auth/forgot-password", json={"email": "nope@example.com"})
    assert resp.status_code == 200


def test_forgot_password_stores_token_in_db(client, db_user, db_session):
    """forgot-password stocke un token de réinitialisation en DB."""
    from app.models import User
    client.post("/auth/forgot-password", json={"email": db_user["email"]})
    db_session.expire_all()   # recharge depuis la DB
    user = db_session.query(User).filter(User.email == db_user["email"]).first()
    assert user is not None
    assert user.password_reset_token is not None
    assert len(user.password_reset_token) >= 20
    assert user.password_reset_expires is not None
    # Expiry dans moins d'1h10min (on tolère la marge d'exécution du test)
    # SQLite peut retourner des datetimes naïfs — normalisation timezone-safe
    now = datetime.now(timezone.utc)
    expires = user.password_reset_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    delta = expires - now
    assert timedelta(minutes=0) < delta <= timedelta(hours=1, minutes=5)


def test_forgot_password_no_token_for_google_account(client, db_session):
    """forgot-password ne génère pas de token pour un compte Google."""
    from app.models import User
    google_user = User(
        email="google@example.com",
        password_hash="!google:fake_sub_id",
        plan="free",
        google_id="fake_sub_id",
    )
    db_session.add(google_user)
    db_session.commit()

    client.post("/auth/forgot-password", json={"email": "google@example.com"})
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == "google@example.com").first()
    assert user.password_reset_token is None  # pas de token pour les comptes Google


# ─────────────────────────────────────────────────────────────────────────────
# Réinitialisation — POST /auth/reset-password
# ─────────────────────────────────────────────────────────────────────────────

def test_reset_password_valid_token(client, db_user, db_session):
    """Un token valide permet de changer le mot de passe et de se reconnecter."""
    from app.models import User

    # Demander un reset
    client.post("/auth/forgot-password", json={"email": db_user["email"]})
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == db_user["email"]).first()
    token = user.password_reset_token
    assert token is not None

    # Réinitialiser le mot de passe
    resp = client.post("/auth/reset-password", json={
        "token": token,
        "new_password": "NewSuperPass456",
    })
    assert resp.status_code == 200
    assert "succès" in resp.json()["message"].lower() or "success" in resp.json()["message"].lower()

    # Vérifier que le token a été effacé
    db_session.expire_all()
    user = db_session.query(User).filter(User.email == db_user["email"]).first()
    assert user.password_reset_token is None
    assert user.password_reset_expires is None

    # Se connecter avec le nouveau mot de passe
    login_resp = client.post("/auth/login", json={
        "email": db_user["email"],
        "password": "NewSuperPass456",
    })
    assert login_resp.status_code == 200


def test_reset_password_invalid_token(client):
    """Un token inconnu retourne 400."""
    resp = client.post("/auth/reset-password", json={
        "token": "totalement-invalide-aaabbbccc",
        "new_password": "NewPassword123",
    })
    assert resp.status_code == 400


def test_reset_password_token_already_used(client, db_user, db_session):
    """Un token utilisé une fois ne peut pas être réutilisé."""
    import secrets as _secrets
    from app.models import User

    # Injecter le token directement en DB (pas d'appel HTTP) pour éviter le rate limit
    user = db_session.query(User).filter(User.email == db_user["email"]).first()
    token = _secrets.token_urlsafe(32)
    user.password_reset_token   = token
    user.password_reset_expires = datetime.now() + timedelta(hours=1)
    db_session.commit()

    # Première utilisation — OK
    resp1 = client.post("/auth/reset-password", json={
        "token": token,
        "new_password": "Password123First",
    })
    assert resp1.status_code == 200

    # Deuxième utilisation — doit échouer (token effacé)
    resp2 = client.post("/auth/reset-password", json={
        "token": token,
        "new_password": "Password456Second",
    })
    assert resp2.status_code == 400


def test_reset_password_expired_token(client, db_user, db_session):
    """Un token expiré retourne 400."""
    import secrets as _secrets
    from app.models import User

    # Injecter un token expiré directement en DB
    user = db_session.query(User).filter(User.email == db_user["email"]).first()
    token = _secrets.token_urlsafe(32)
    user.password_reset_token   = token
    user.password_reset_expires = datetime.now() - timedelta(hours=2)   # déjà expiré
    db_session.commit()

    resp = client.post("/auth/reset-password", json={
        "token": token,
        "new_password": "NewPassword123",
    })
    assert resp.status_code == 400
    assert "expir" in resp.json()["detail"].lower()


def test_reset_password_short_password(client, db_user, db_session):
    """Un nouveau mot de passe trop court est rejeté par Pydantic (422)."""
    import secrets as _secrets
    from app.models import User

    # Injecter un token valide directement en DB
    user = db_session.query(User).filter(User.email == db_user["email"]).first()
    token = _secrets.token_urlsafe(32)
    user.password_reset_token   = token
    user.password_reset_expires = datetime.now() + timedelta(hours=1)
    db_session.commit()

    resp = client.post("/auth/reset-password", json={
        "token": token,
        "new_password": "short",  # < 8 chars
    })
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Tests API key — authentification via wsk_ prefix
# ─────────────────────────────────────────────────────────────────────────────

def _make_pro_with_api_key(db_session) -> dict:
    """Crée un utilisateur Pro en DB avec une clé API valide."""
    import uuid as _uuid
    from app.models import User
    from app.auth import hash_password, generate_api_key, create_access_token

    email = f"pro-apikey-{_uuid.uuid4().hex[:8]}@example.com"
    api_key = generate_api_key()
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
        plan="pro",
        api_key=api_key,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return {"email": email, "api_key": api_key, "user": user}


def test_api_key_format_starts_with_wsk(db_session):
    """Les clés API générées commencent par 'wsk_'."""
    creds = _make_pro_with_api_key(db_session)
    assert creds["api_key"].startswith("wsk_"), (
        f"API key should start with 'wsk_', got: {creds['api_key'][:8]}"
    )


def test_api_key_auth_on_me_endpoint(client, db_session):
    """Une clé API valide (plan Pro) permet d'accéder à /auth/me."""
    creds = _make_pro_with_api_key(db_session)
    resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {creds['api_key']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == creds["email"]


def test_api_key_auth_free_user_rejected(client, db_session):
    """Une clé API d'un utilisateur free doit être rejetée (plan Pro requis)."""
    import uuid as _uuid
    from app.models import User
    from app.auth import hash_password, generate_api_key

    email = f"free-apikey-{_uuid.uuid4().hex[:8]}@example.com"
    api_key = generate_api_key()
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
        plan="free",
        api_key=api_key,
    )
    db_session.add(user)
    db_session.commit()

    resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 401


def test_api_key_wrong_prefix_rejected(client, db_session):
    """Un token avec un mauvais préfixe n'est pas reconnu comme clé API."""
    creds = _make_pro_with_api_key(db_session)
    # Remplacer wsk_ par un préfixe invalide
    bad_token = "bad_" + creds["api_key"][4:]
    resp = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 401


def test_api_key_regenerate_changes_key(client, db_session):
    """Régénérer la clé API produit une nouvelle clé wsk_ différente."""
    creds = _make_pro_with_api_key(db_session)
    from app.auth import create_access_token
    token = create_access_token(creds["user"].id, creds["email"], "pro")

    resp = client.post(
        "/auth/api-key/regenerate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    new_key = resp.json()["api_key"]
    assert new_key.startswith("wsk_")
    assert new_key != creds["api_key"]
