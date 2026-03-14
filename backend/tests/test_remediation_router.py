"""
Tests — remediation_router.py endpoints
========================================
GET  /remediation/guide?title=X&lang=fr
POST /remediation/guides
"""
import json
import uuid

import pytest

from app.auth import create_access_token, hash_password
from app.models import User


def _make_user(db_session, plan="free"):
    email = f"remed-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=hash_password("Test123"), plan=plan)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth(user):
    token = create_access_token(user.id, user.email, user.plan)
    return {"Authorization": f"Bearer {token}"}


# ── GET /remediation/guide ──────────────────────────────────────────────────────


class TestGetGuide:
    def test_guide_found(self, client):
        resp = client.get("/remediation/guide", params={"title": "SPF manquant"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "SPF manquant"
        assert data["difficulty"] == "easy"
        assert data["step_count"] >= 2
        assert len(data["steps"]) >= 2

    def test_guide_not_found(self, client):
        resp = client.get("/remediation/guide", params={"title": "XYZ unknown"})
        assert resp.status_code == 404

    def test_guide_lang_en(self, client):
        resp = client.get("/remediation/guide", params={"title": "HSTS manquant", "lang": "en"})
        assert resp.status_code == 200
        data = resp.json()
        assert "Enable" in data["title"] or "HSTS" in data["title"]
        # Steps should be in English
        assert data["steps"][0]["action"]  # non-empty

    def test_guide_substring_match(self, client):
        resp = client.get("/remediation/guide", params={"title": "L'enregistrement DMARC manquant pour le domaine"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "DMARC manquant"

    def test_guide_case_insensitive(self, client):
        resp = client.get("/remediation/guide", params={"title": "certificat ssl expiré depuis 3 jours"})
        assert resp.status_code == 200

    def test_premium_guide_locked_anonymous(self, client):
        """Premium guide without auth → steps locked."""
        resp = client.get("/remediation/guide", params={"title": "DKIM non détecté"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_premium"] is True
        assert data["locked"] is True
        assert data["steps"] == []
        assert data["step_count"] >= 2  # count visible even if locked

    def test_premium_guide_locked_free_user(self, client, db_session):
        user = _make_user(db_session, plan="free")
        resp = client.get("/remediation/guide", params={"title": "DKIM non détecté"}, headers=_auth(user))
        assert resp.status_code == 200
        assert resp.json()["locked"] is True

    def test_premium_guide_unlocked_starter(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        resp = client.get("/remediation/guide", params={"title": "DKIM non détecté"}, headers=_auth(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["locked"] is False
        assert len(data["steps"]) >= 2

    def test_premium_guide_unlocked_pro(self, client, db_session):
        user = _make_user(db_session, plan="pro")
        resp = client.get("/remediation/guide", params={"title": "WordPress détecté"}, headers=_auth(user))
        assert resp.status_code == 200
        assert resp.json()["locked"] is False

    def test_non_premium_guide_always_unlocked(self, client):
        """Non-premium guides are always open, even without auth."""
        resp = client.get("/remediation/guide", params={"title": "SPF manquant"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_premium"] is False
        assert data["locked"] is False
        assert len(data["steps"]) >= 2


# ── POST /remediation/guides (batch) ───────────────────────────────────────────


class TestBatchGuides:
    def test_batch_mixed(self, client):
        resp = client.post("/remediation/guides", json={
            "titles": ["SPF manquant", "Unknown finding", "HSTS manquant"],
            "lang": "fr",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["SPF manquant"] is not None
        assert data["Unknown finding"] is None
        assert data["HSTS manquant"] is not None

    def test_batch_empty(self, client):
        resp = client.post("/remediation/guides", json={"titles": [], "lang": "fr"})
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_batch_lang_en(self, client):
        resp = client.post("/remediation/guides", json={
            "titles": ["SPF manquant"],
            "lang": "en",
        })
        data = resp.json()
        guide = data["SPF manquant"]
        assert guide is not None
        assert "Add" in guide["title"] or "SPF" in guide["title"]

    def test_batch_premium_locked_no_auth(self, client):
        resp = client.post("/remediation/guides", json={
            "titles": ["DKIM non détecté", "SPF manquant"],
        })
        data = resp.json()
        assert data["DKIM non détecté"]["locked"] is True
        assert data["SPF manquant"]["locked"] is False

    def test_batch_premium_unlocked_with_starter(self, client, db_session):
        user = _make_user(db_session, plan="starter")
        resp = client.post("/remediation/guides", json={
            "titles": ["DKIM non détecté"],
        }, headers=_auth(user))
        data = resp.json()
        assert data["DKIM non détecté"]["locked"] is False
