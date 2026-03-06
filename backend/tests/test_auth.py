"""
Tests : authentification (register, login, JWT, lockout, forgot/reset password,
        profile, delete account, change-password, change-email, white-label)
"""
import io
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock


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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers communs — création d'utilisateur en DB (sans HTTP)
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "free", password: str = "TestPass123") -> dict:
    """Crée un utilisateur directement en DB et retourne email + token JWT."""
    import uuid as _uuid
    from app.models import User
    from app.auth import hash_password, generate_api_key, create_access_token

    email = f"user-{plan}-{_uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password(password),
        plan=plan,
        api_key=generate_api_key(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return {"email": email, "password": password, "token": token, "user": user}


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /auth/profile
# ─────────────────────────────────────────────────────────────────────────────

def test_update_profile_first_and_last_name(client, db_session):
    """Met à jour le prénom et le nom en une seule requête."""
    u = _make_user(db_session)
    resp = client.patch(
        "/auth/profile",
        json={"first_name": "Alice", "last_name": "Martin"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["first_name"] == "Alice"
    assert data["last_name"] == "Martin"


def test_update_profile_first_name_only(client, db_session):
    """Mise à jour partielle : seul le prénom est fourni."""
    u = _make_user(db_session)
    resp = client.patch(
        "/auth/profile",
        json={"first_name": "Bob"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Bob"
    assert resp.json()["last_name"] is None   # inchangé


def test_update_profile_unauthenticated(client):
    """Sans token → 401."""
    resp = client.patch("/auth/profile", json={"first_name": "X"})
    assert resp.status_code == 401


def test_update_profile_returns_user_response(client, db_session):
    """La réponse contient bien tous les champs UserResponse."""
    u = _make_user(db_session)
    resp = client.patch(
        "/auth/profile",
        json={"first_name": "Carol"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    data = resp.json()
    for field in ("id", "email", "plan", "api_key", "first_name", "last_name", "is_admin"):
        assert field in data, f"Champ manquant : {field}"


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /auth/account
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_account_success(client, db_session):
    """Suppression de compte avec mot de passe correct → 200."""
    u = _make_user(db_session, password="DeleteMe123!")
    resp = client.request(
        "DELETE",
        "/auth/account",
        json={"password": "DeleteMe123!"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert "supprimé" in resp.json()["message"].lower()


def test_delete_account_wrong_password(client, db_session):
    """Mauvais mot de passe → 400."""
    u = _make_user(db_session)
    resp = client.request(
        "DELETE",
        "/auth/account",
        json={"password": "WrongPassword999"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 400


def test_delete_account_user_no_longer_in_db(client, db_session):
    """Après suppression, l'utilisateur n'existe plus en DB."""
    from app.models import User
    u = _make_user(db_session)
    user_id = u["user"].id
    client.request(
        "DELETE",
        "/auth/account",
        json={"password": u["password"]},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == user_id).first() is None


def test_delete_account_unauthenticated(client):
    """Sans token → 401."""
    resp = client.request("DELETE", "/auth/account", json={"password": "x"})
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/change-password
# ─────────────────────────────────────────────────────────────────────────────

def test_change_password_success(client, db_session):
    """Changement de mot de passe avec mot de passe actuel correct."""
    u = _make_user(db_session, password="OldPass123!")
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert "succès" in resp.json()["message"].lower() or "success" in resp.json()["message"].lower()


def test_change_password_wrong_current(client, db_session):
    """Mauvais mot de passe actuel → 400."""
    u = _make_user(db_session)
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "WrongOldPass!", "new_password": "NewPass456!"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 400


def test_change_password_new_too_short(client, db_session):
    """Nouveau mot de passe trop court → 422."""
    u = _make_user(db_session)
    resp = client.post(
        "/auth/change-password",
        json={"current_password": u["password"], "new_password": "abc"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 422


def test_change_password_actually_updates_hash(client, db_session):
    """Après changement, le nouveau mdp fonctionne au login."""
    u = _make_user(db_session, password="OldPass123!")
    client.post(
        "/auth/change-password",
        json={"current_password": "OldPass123!", "new_password": "NewPass456!"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    # Le nouveau mot de passe doit permettre la connexion
    resp = client.post("/auth/login", json={"email": u["email"], "password": "NewPass456!"})
    assert resp.status_code == 200


def test_change_password_unauthenticated(client):
    """Sans token → 401."""
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "x", "new_password": "NewPass456!"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/change-email
# ─────────────────────────────────────────────────────────────────────────────

def test_change_email_success(client, db_session):
    """Changement d'email avec mot de passe correct."""
    u = _make_user(db_session)
    resp = client.post(
        "/auth/change-email",
        json={"new_email": "newemail@example.com", "current_password": u["password"]},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200


def test_change_email_wrong_password(client, db_session):
    """Mauvais mot de passe → 400."""
    u = _make_user(db_session)
    resp = client.post(
        "/auth/change-email",
        json={"new_email": "other@example.com", "current_password": "WrongPass999"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 400


def test_change_email_duplicate(client, db_session):
    """Email déjà utilisé par un autre compte → 409."""
    a = _make_user(db_session)
    b = _make_user(db_session)
    # Tente de prendre l'email de `a`
    resp = client.post(
        "/auth/change-email",
        json={"new_email": a["email"], "current_password": b["password"]},
        headers={"Authorization": f"Bearer {b['token']}"},
    )
    assert resp.status_code == 409


def test_change_email_invalid_format(client, db_session):
    """Email invalide → 422."""
    u = _make_user(db_session)
    resp = client.post(
        "/auth/change-email",
        json={"new_email": "not-an-email", "current_password": u["password"]},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 422


def test_change_email_unauthenticated(client):
    """Sans token → 401."""
    resp = client.post(
        "/auth/change-email",
        json={"new_email": "x@example.com", "current_password": "x"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# White-label endpoints (GET / PATCH / POST logo / DELETE logo)
# Réservé au plan Pro — les utilisateurs non-Pro reçoivent 403
# ─────────────────────────────────────────────────────────────────────────────

def _make_pro(db_session) -> dict:
    return _make_user(db_session, plan="pro")


def test_white_label_get_free_user_403(client, db_session):
    """Plan free → 403 sur GET /auth/white-label."""
    u = _make_user(db_session, plan="free")
    resp = client.get("/auth/white-label", headers={"Authorization": f"Bearer {u['token']}"})
    assert resp.status_code == 403


def test_white_label_get_pro_user_200(client, db_session):
    """Plan Pro → 200 avec les champs attendus."""
    u = _make_pro(db_session)
    resp = client.get("/auth/white-label", headers={"Authorization": f"Bearer {u['token']}"})
    assert resp.status_code == 200
    data = resp.json()
    for field in ("enabled", "company_name", "primary_color", "has_logo"):
        assert field in data


def test_white_label_patch_set_company_name(client, db_session):
    """PATCH met à jour le nom de l'entreprise."""
    u = _make_pro(db_session)
    resp = client.patch(
        "/auth/white-label",
        json={"company_name": "AcmeSec"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["company_name"] == "AcmeSec"


def test_white_label_patch_set_color(client, db_session):
    """PATCH met à jour la couleur primaire (#RRGGBB)."""
    u = _make_pro(db_session)
    resp = client.patch(
        "/auth/white-label",
        json={"primary_color": "#ff0099"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["primary_color"] == "#ff0099"


def test_white_label_patch_invalid_color(client, db_session):
    """Couleur hex invalide → 422."""
    u = _make_pro(db_session)
    resp = client.patch(
        "/auth/white-label",
        json={"primary_color": "rouge"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 422


def test_white_label_patch_company_name_too_long(client, db_session):
    """Nom > 100 caractères → 422."""
    u = _make_pro(db_session)
    resp = client.patch(
        "/auth/white-label",
        json={"company_name": "A" * 101},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 422


def test_white_label_patch_enable_toggle(client, db_session):
    """On peut activer/désactiver le white-label via le champ enabled."""
    u = _make_pro(db_session)
    resp = client.patch(
        "/auth/white-label",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_white_label_patch_free_user_403(client, db_session):
    """Plan free → 403 sur PATCH /auth/white-label."""
    u = _make_user(db_session, plan="free")
    resp = client.patch(
        "/auth/white-label",
        json={"company_name": "Evil"},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 403


def test_white_label_logo_upload_png(client, db_session):
    """Upload d'un PNG valide → 200 + has_logo=True."""
    import io
    u = _make_pro(db_session)
    # PNG minimal valide (8x8 pixels, 1 byte couleur)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100   # fake PNG header + padding
    resp = client.post(
        "/auth/white-label/logo",
        files={"file": ("logo.png", io.BytesIO(fake_png), "image/png")},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["has_logo"] is True


def test_white_label_logo_upload_too_large(client, db_session):
    """Logo > 200 Ko → 422."""
    import io
    u = _make_pro(db_session)
    big_data = b"X" * (201 * 1024)
    resp = client.post(
        "/auth/white-label/logo",
        files={"file": ("logo.png", io.BytesIO(big_data), "image/png")},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 422


def test_white_label_logo_upload_invalid_type(client, db_session):
    """Format non supporté (exe) → 422."""
    import io
    u = _make_pro(db_session)
    resp = client.post(
        "/auth/white-label/logo",
        files={"file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 422


def test_white_label_logo_upload_free_user_403(client, db_session):
    """Plan free → 403 sur upload logo."""
    import io
    u = _make_user(db_session, plan="free")
    resp = client.post(
        "/auth/white-label/logo",
        files={"file": ("logo.png", io.BytesIO(b"\x89PNG"), "image/png")},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 403


def test_white_label_logo_delete_success(client, db_session):
    """Suppression du logo → 200 + has_logo=False."""
    import io
    u = _make_pro(db_session)
    # D'abord uploader un logo
    client.post(
        "/auth/white-label/logo",
        files={"file": ("logo.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50), "image/png")},
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    # Puis le supprimer
    resp = client.delete(
        "/auth/white-label/logo",
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["has_logo"] is False


def test_white_label_logo_delete_free_user_403(client, db_session):
    """Plan free → 403 sur DELETE logo."""
    u = _make_user(db_session, plan="free")
    resp = client.delete(
        "/auth/white-label/logo",
        headers={"Authorization": f"Bearer {u['token']}"},
    )
    assert resp.status_code == 403


# =============================================================================
# Google OAuth — POST /auth/google
# =============================================================================

def _google_idinfo(email="alice@gmail.com", sub="goog_sub_123",
                   given_name="Alice", family_name="Smith",
                   email_verified=True):
    """Construit un faux idinfo Google."""
    return {
        "email": email, "sub": sub,
        "given_name": given_name, "family_name": family_name,
        "email_verified": email_verified,
    }


class TestGoogleAuth:

    def test_no_client_id_returns_503(self, client, db_session):
        """GOOGLE_CLIENT_ID non configuré → 503."""
        with patch("app.routers.auth_router.GOOGLE_CLIENT_ID", ""):
            resp = client.post("/auth/google", json={"id_token": "tok"})
        assert resp.status_code == 503

    def test_invalid_token_returns_401(self, client, db_session):
        """Token Google invalide → 401."""
        with patch("app.routers.auth_router.GOOGLE_CLIENT_ID", "test-client-id"), \
             patch("google.oauth2.id_token.verify_oauth2_token") as mock_g:
            mock_g.side_effect = ValueError("bad token")
            resp = client.post("/auth/google", json={"id_token": "bad"})
        assert resp.status_code == 401

    def test_new_user_created_returns_token(self, client, db_session):
        """Nouvel utilisateur → créé en DB + token JWT retourné."""
        from app.models import User
        idinfo = _google_idinfo(email="new@gmail.com", sub="sub_new")
        with patch("app.routers.auth_router.GOOGLE_CLIENT_ID", "test-client-id"), \
             patch("google.oauth2.id_token.verify_oauth2_token") as mock_g, \
             patch("app.routers.auth_router._send_welcome_sync"):
            mock_g.return_value = idinfo
            resp = client.post("/auth/google", json={"id_token": "valid_tok"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        # Vérifier que l'user a bien été créé en DB
        user = db_session.query(User).filter(User.email == "new@gmail.com").first()
        assert user is not None
        assert user.google_id == "sub_new"
        assert user.password_hash.startswith("!google:")

    def test_existing_user_by_google_id_returns_token(self, client, db_session):
        """User déjà lié par google_id → token retourné sans recréation."""
        from app.models import User
        from app.auth import hash_password, generate_api_key
        # Créer un user avec google_id
        existing = User(
            email="existing@gmail.com",
            password_hash="!google:sub_existing",
            plan="free",
            api_key=generate_api_key(),
            google_id="sub_existing",
        )
        db_session.add(existing)
        db_session.commit()
        db_session.refresh(existing)

        idinfo = _google_idinfo(email="existing@gmail.com", sub="sub_existing")
        with patch("app.routers.auth_router.GOOGLE_CLIENT_ID", "test-client-id"), \
             patch("google.oauth2.id_token.verify_oauth2_token") as mock_g, \
             patch("app.routers.auth_router._send_welcome_sync"):
            mock_g.return_value = idinfo
            resp = client.post("/auth/google", json={"id_token": "valid_tok"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_existing_user_by_email_links_google_id(self, client, db_session):
        """User existant sans google_id → google_id lié sur email match."""
        from app.models import User
        from app.auth import hash_password, generate_api_key
        existing = User(
            email="link@example.com",
            password_hash=hash_password("pass"),
            plan="free",
            api_key=generate_api_key(),
        )
        db_session.add(existing)
        db_session.commit()
        db_session.refresh(existing)

        idinfo = _google_idinfo(email="link@example.com", sub="sub_link")
        with patch("app.routers.auth_router.GOOGLE_CLIENT_ID", "test-client-id"), \
             patch("google.oauth2.id_token.verify_oauth2_token") as mock_g, \
             patch("app.routers.auth_router._send_welcome_sync"):
            mock_g.return_value = idinfo
            resp = client.post("/auth/google", json={"id_token": "valid_tok"})
        assert resp.status_code == 200
        db_session.refresh(existing)
        assert existing.google_id == "sub_link"

    def test_unverified_email_returns_400(self, client, db_session):
        """Email Google non vérifié → 400."""
        idinfo = _google_idinfo(email_verified=False)
        with patch("app.routers.auth_router.GOOGLE_CLIENT_ID", "test-client-id"), \
             patch("google.oauth2.id_token.verify_oauth2_token") as mock_g:
            mock_g.return_value = idinfo
            resp = client.post("/auth/google", json={"id_token": "valid_tok"})
        assert resp.status_code == 400


# =============================================================================
# Guards Google — change-password + change-email bloqués pour comptes Google
# =============================================================================

class TestGoogleUserGuards:

    def test_change_password_blocked_for_google_user(self, client, db_session):
        """Compte Google (password_hash=!google:…) → 400 sur change-password."""
        from app.models import User
        from app.auth import generate_api_key, create_access_token
        u = User(
            email="guser@gmail.com",
            password_hash="!google:sub_xyz",
            plan="free", api_key=generate_api_key(),
            google_id="sub_xyz",
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        token = create_access_token(u.id, u.email, u.plan)

        resp = client.post(
            "/auth/change-password",
            json={"current_password": "irrelevant", "new_password": "NewPass123!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "Google" in resp.json()["detail"]

    def test_change_email_blocked_for_google_user(self, client, db_session):
        """Compte Google → 400 sur change-email."""
        from app.models import User
        from app.auth import generate_api_key, create_access_token
        u = User(
            email="guser2@gmail.com",
            password_hash="!google:sub_yyy",
            plan="free", api_key=generate_api_key(),
            google_id="sub_yyy",
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        token = create_access_token(u.id, u.email, u.plan)

        resp = client.post(
            "/auth/change-email",
            json={"new_email": "new@example.com", "current_password": "irrelevant"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "Google" in resp.json()["detail"]


# =============================================================================
# get_optional_user — API key (wsk_) path
# =============================================================================

class TestOptionalUserApiKey:
    """Tests pour le fallback API key dans get_optional_user."""

    def test_api_key_pro_user_authenticated(self, client, db_session):
        """Clé API wsk_ valide pour un Pro → authentifié via l'endpoint /auth/me."""
        from app.models import User
        from app.auth import generate_api_key
        u = User(
            email="prouser@example.com",
            password_hash="!google:stub",
            plan="pro",
            api_key=generate_api_key(),
            is_active=True,
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {u.api_key}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == u.email

    def test_api_key_starter_not_authorized(self, client, db_session):
        """Clé API wsk_ pour Starter → non-autorisé (Pro uniquement)."""
        from app.models import User
        from app.auth import generate_api_key
        u = User(
            email="starteruser@example.com",
            password_hash="pass",
            plan="starter",
            api_key=generate_api_key(),
            is_active=True,
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)

        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {u.api_key}"})
        # Starter ne peut pas utiliser l'API key
        assert resp.status_code == 401
