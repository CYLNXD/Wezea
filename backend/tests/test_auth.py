"""
Tests : authentification (register, login, JWT, lockout)
"""
import pytest


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
