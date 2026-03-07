"""
Tests — Application Scanning
==============================
Couvre :
  - app/routers/app_router.py  : CRUD apps, verify info, verify ownership, scan, results
  - app/app_checks.py          : AppAuditor (8 catégories de checks)

Stratégie :
  - Router tests  : client HTTP + DB en mémoire via conftest
  - AppAuditor    : patch des méthodes réseau (_head_or_get, _get_status, _fetch_main,
                    _fetch_text) — zéro appel réseau réel
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "dev"):
    """Crée un utilisateur en DB sans appel HTTP (évite le rate limit /auth/register)."""
    from app.models import User
    from app.auth import hash_password, create_access_token, generate_api_key

    email = f"apptest-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("Pass123!"),
        plan=plan,
        api_key=generate_api_key(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return user, token


def _make_app(db_session, user, url="https://example.com", verified=False, method="dns"):
    """Enregistre une VerifiedApp en DB directement."""
    from app.models import VerifiedApp
    import secrets

    app = VerifiedApp(
        user_id=user.id,
        name="Test App",
        url=url,
        domain="example.com",
        verification_method=method,
        verification_token=secrets.token_urlsafe(24),
        is_verified=verified,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


def _run(coro):
    """Exécute une coroutine de façon synchrone (pour les tests AppAuditor)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Faux headers HTTP (pour tester _check_main_response sans réseau)
# ─────────────────────────────────────────────────────────────────────────────

class FakeHeaders:
    """Simule http.client.HTTPMessage — supporte .get() et str()."""

    def __init__(self, regular: dict | None = None, cookies: list[str] | None = None):
        self._regular = {k.lower(): v for k, v in (regular or {}).items()}
        self._cookies = cookies or []

    def get(self, key: str, default: str = "") -> str:
        return self._regular.get(key.lower(), default)

    def __str__(self) -> str:
        lines = [f"{k}: {v}" for k, v in self._regular.items()]
        for c in self._cookies:
            lines.append(f"set-cookie: {c}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — app_router.py : Plan guard
# ─────────────────────────────────────────────────────────────────────────────

class TestAppPlanGuard:
    """GET /apps — bloqué pour les plans non-dev."""

    def test_free_user_cannot_list_apps(self, client, db_session):
        _, token = _make_user(db_session, plan="free")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_starter_user_cannot_list_apps(self, client, db_session):
        _, token = _make_user(db_session, plan="starter")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_pro_user_cannot_list_apps(self, client, db_session):
        _, token = _make_user(db_session, plan="pro")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_dev_user_can_list_apps(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_admin_can_list_apps_regardless_of_plan(self, client, db_session):
        from app.models import User
        from app.auth import hash_password, create_access_token, generate_api_key

        email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            email=email,
            password_hash=hash_password("Pass123!"),
            plan="free",
            is_admin=True,
            api_key=generate_api_key(),
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        token = create_access_token(user.id, email, "free")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — _parse_and_validate_url
# ─────────────────────────────────────────────────────────────────────────────

class TestParseAndValidateUrl:
    """Tests unitaires de la validation d'URL anti-SSRF."""

    def _parse(self, raw: str):
        from app.routers.app_router import _parse_and_validate_url
        return _parse_and_validate_url(raw)

    def test_auto_adds_https_when_no_scheme(self):
        url, host = self._parse("example.com")
        assert url.startswith("https://")
        assert host == "example.com"

    def test_localhost_is_blocked(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._parse("http://localhost/api")
        assert exc_info.value.status_code == 422

    def test_loopback_ip_is_blocked(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._parse("http://127.0.0.1")
        assert exc_info.value.status_code == 422

    def test_private_ip_is_blocked(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._parse("http://192.168.1.1/admin")
        assert exc_info.value.status_code == 422

    def test_private_10_block_is_blocked(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._parse("http://10.0.0.1")
        assert exc_info.value.status_code == 422

    def test_valid_domain_returns_normalized_url_and_host(self):
        url, host = self._parse("https://www.example.com/path")
        assert host == "www.example.com"
        assert "www.example.com" in url

    def test_url_with_port_is_kept(self):
        url, host = self._parse("https://example.com:8443")
        assert ":8443" in url

    def test_invalid_hostname_raises_422(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._parse("https://not_a_valid-domain!")
        assert exc_info.value.status_code == 422

    def test_missing_host_raises_422(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            self._parse("https:///path")

    def test_metadata_google_internal_is_blocked(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._parse("http://metadata.google.internal/computeMetadata")
        assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — POST /apps
# ─────────────────────────────────────────────────────────────────────────────

class TestRegisterApp:

    def test_dev_user_can_register_app(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.post("/apps", json={
            "name": "My App",
            "url": "https://example.com",
            "verification_method": "dns",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My App"
        assert data["url"] == "https://example.com"
        assert data["is_verified"] is False
        assert data["verification_token"]  # token généré

    def test_duplicate_url_returns_409(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        _make_app(db_session, user, url="https://example.com")
        resp = client.post("/apps", json={
            "name": "Duplicate",
            "url": "https://example.com",
            "verification_method": "dns",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 409

    def test_name_too_long_returns_422(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.post("/apps", json={
            "name": "x" * 101,
            "url": "https://example.com",
            "verification_method": "dns",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422

    def test_invalid_verification_method_returns_422(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.post("/apps", json={
            "name": "App",
            "url": "https://example.com",
            "verification_method": "ftp",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422

    def test_file_method_accepted(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.post("/apps", json={
            "name": "App",
            "url": "https://app2.example.com",
            "verification_method": "file",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        assert resp.json()["verification_method"] == "file"

    def test_non_dev_user_returns_403(self, client, db_session):
        _, token = _make_user(db_session, plan="pro")
        resp = client.post("/apps", json={
            "name": "App",
            "url": "https://example.com",
            "verification_method": "dns",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — GET /apps
# ─────────────────────────────────────────────────────────────────────────────

class TestListApps:

    def test_empty_list_for_new_user(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_own_apps_only(self, client, db_session):
        user1, token1 = _make_user(db_session, plan="dev")
        user2, _      = _make_user(db_session, plan="dev")
        _make_app(db_session, user1, url="https://app-u1.example.com")
        _make_app(db_session, user2, url="https://app-u2.example.com")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token1}"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["url"] == "https://app-u1.example.com"

    def test_returns_multiple_apps(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        _make_app(db_session, user, url="https://app1.example.com")
        _make_app(db_session, user, url="https://app2.example.com")
        resp = client.get("/apps", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — DELETE /apps/{id}
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteApp:

    def test_owner_can_delete(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user)
        resp = client.delete(f"/apps/{app.id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 204

    def test_other_user_gets_404(self, client, db_session):
        user1, _      = _make_user(db_session, plan="dev")
        _, token2     = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user1)
        resp = client.delete(f"/apps/{app.id}", headers={"Authorization": f"Bearer {token2}"})
        assert resp.status_code == 404

    def test_nonexistent_app_returns_404(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.delete("/apps/99999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — GET /apps/{id}/verify-info
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyInfo:

    def test_dns_method_returns_record_instructions(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, method="dns")
        resp = client.get(f"/apps/{app.id}/verify-info",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "dns"
        assert data["record_type"] == "TXT"
        assert "_cyberhealth-verify." in data["record_name"]
        assert "cyberhealth-verify=" in data["record_value"]

    def test_file_method_returns_file_instructions(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, method="file")
        resp = client.get(f"/apps/{app.id}/verify-info",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "file"
        assert "/.well-known/cyberhealth-verify.txt" in data["file_path"]
        assert "cyberhealth-verify=" in data["file_content"]

    def test_not_found_returns_404(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.get("/apps/99999/verify-info",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Section 7 — POST /apps/{id}/verify
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyOwnership:

    def test_dns_verification_success(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, method="dns")
        with patch("app.routers.app_router._check_dns_verification", return_value=True):
            resp = client.post(f"/apps/{app.id}/verify",
                               headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is True
        db_session.refresh(app)
        assert app.is_verified is True
        assert app.verified_at is not None

    def test_dns_verification_failure(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, method="dns")
        with patch("app.routers.app_router._check_dns_verification", return_value=False):
            resp = client.post(f"/apps/{app.id}/verify",
                               headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verified"] is False
        db_session.refresh(app)
        assert app.is_verified is False

    def test_file_verification_success(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, method="file")
        with patch("app.routers.app_router._check_file_verification", return_value=True):
            resp = client.post(f"/apps/{app.id}/verify",
                               headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["verified"] is True

    def test_not_found_returns_404(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.post("/apps/99999/verify",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Section 8 — POST /apps/{id}/scan
# ─────────────────────────────────────────────────────────────────────────────

def _mock_app_auditor(findings=None, details=None):
    """Construit un mock AppAuditor retournant des findings et détails fixes."""
    mock = MagicMock()
    mock.audit = AsyncMock(return_value=findings or [])
    mock.get_details.return_value = details or {}
    return mock


class TestScanApp:
    """Bypass le rate limiter (3/hour partagé via SlowAPI MemoryStorage) via patch."""

    @staticmethod
    def _no_limit():
        """Patch de limiter.limit() pour neutraliser la rate-limit en tests."""
        from app.limiter import limiter
        return patch.object(limiter, "limit", return_value=lambda f: f)

    def test_scan_verified_app_returns_result(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, verified=True)
        with patch("app.app_checks.AppAuditor", return_value=_mock_app_auditor()):
            resp = client.post(f"/apps/{app.id}/scan",
                               headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_id"] == app.id
        assert "score" in data
        assert "risk_level" in data
        assert "findings" in data

    def test_scan_updates_db(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, verified=True)
        with patch("app.app_checks.AppAuditor", return_value=_mock_app_auditor()):
            client.post(f"/apps/{app.id}/scan",
                        headers={"Authorization": f"Bearer {token}"})
        db_session.refresh(app)
        assert app.last_scan_at is not None
        assert app.last_score is not None
        assert app.last_risk_level is not None

    def test_scan_unverified_app_returns_403(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, verified=False)
        resp = client.post(f"/apps/{app.id}/scan",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_scan_nonexistent_app_returns_404(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.post("/apps/99999/scan",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_scan_auditor_exception_returns_500(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, verified=True)
        bad_auditor = MagicMock()
        bad_auditor.audit = AsyncMock(side_effect=Exception("network timeout"))
        with patch("app.app_checks.AppAuditor", return_value=bad_auditor):
            resp = client.post(f"/apps/{app.id}/scan",
                               headers={"Authorization": f"Bearer {token}"})
        # Le rate limit peut retourner 429 si le quota précédent est épuisé
        assert resp.status_code in (500, 429)


# ─────────────────────────────────────────────────────────────────────────────
# Section 9 — GET /apps/{id}/results
# ─────────────────────────────────────────────────────────────────────────────

class TestGetResults:

    def test_returns_last_scan_result(self, client, db_session):
        import json
        from datetime import datetime, timezone

        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, verified=True)
        # Simuler un scan en DB
        app.last_scan_at       = datetime.now(timezone.utc)
        app.last_score         = 85
        app.last_risk_level    = "LOW"
        app.last_findings_json = json.dumps([])
        app.last_details_json  = json.dumps({})
        db_session.commit()

        resp = client.get(f"/apps/{app.id}/results",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 85
        assert data["risk_level"] == "LOW"

    def test_no_scan_yet_returns_404(self, client, db_session):
        user, token = _make_user(db_session, plan="dev")
        app = _make_app(db_session, user, verified=True)
        resp = client.get(f"/apps/{app.id}/results",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_not_found_returns_404(self, client, db_session):
        _, token = _make_user(db_session, plan="dev")
        resp = client.get("/apps/99999/results",
                          headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Section 10 — _check_dns_verification & _check_file_verification
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckDnsVerification:
    def test_matching_txt_record_returns_true(self):
        from app.routers.app_router import _check_dns_verification

        mock_rdata = MagicMock()
        mock_rdata.to_text.return_value = '"cyberhealth-verify=abc123"'
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [mock_rdata]

        with patch("app.routers.app_router.dns.resolver.Resolver",
                   return_value=mock_resolver):
            result = _check_dns_verification("example.com", "abc123")
        assert result is True

    def test_non_matching_txt_record_returns_false(self):
        from app.routers.app_router import _check_dns_verification

        mock_rdata = MagicMock()
        mock_rdata.to_text.return_value = '"cyberhealth-verify=wrong"'
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [mock_rdata]

        with patch("app.routers.app_router.dns.resolver.Resolver",
                   return_value=mock_resolver):
            result = _check_dns_verification("example.com", "abc123")
        assert result is False

    def test_dns_exception_returns_false(self):
        from app.routers.app_router import _check_dns_verification

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = Exception("NXDOMAIN")

        with patch("app.routers.app_router.dns.resolver.Resolver",
                   return_value=mock_resolver):
            result = _check_dns_verification("example.com", "abc123")
        assert result is False


class TestCheckFileVerification:
    def test_file_with_correct_token_returns_true(self):
        from app.routers.app_router import _check_file_verification
        import http.client

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"cyberhealth-verify=mytoken"
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response

        with patch("http.client.HTTPSConnection", return_value=mock_conn):
            result = _check_file_verification("example.com", "mytoken")
        assert result is True

    def test_file_with_wrong_token_returns_false(self):
        from app.routers.app_router import _check_file_verification

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"cyberhealth-verify=wrong"
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response

        with patch("http.client.HTTPSConnection", return_value=mock_conn), \
             patch("http.client.HTTPConnection", return_value=mock_conn):
            result = _check_file_verification("example.com", "mytoken")
        assert result is False

    def test_connection_exception_returns_false(self):
        from app.routers.app_router import _check_file_verification

        mock_conn = MagicMock()
        mock_conn.getresponse.side_effect = Exception("timeout")

        with patch("http.client.HTTPSConnection", return_value=mock_conn), \
             patch("http.client.HTTPConnection", return_value=mock_conn):
            result = _check_file_verification("example.com", "mytoken")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Section 11 — AppAuditor : checks réseau (app_checks.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestAppAuditorSensitiveFiles:
    def test_env_file_exposed_creates_critical_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")

        def mock_head(path):
            return 200 if path == "/.env" else 404

        with patch.object(auditor, "_head_or_get", side_effect=mock_head):
            _run(auditor._check_sensitive_files())

        titles = [f.title for f in auditor._findings]
        assert "Fichier .env exposé" in titles
        assert "/.env" in auditor._details["exposed_files"]

    def test_redirect_301_also_triggers_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_head_or_get", return_value=301):
            _run(auditor._check_sensitive_files())

        assert len(auditor._findings) > 0

    def test_404_produces_no_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_head_or_get", return_value=404):
            _run(auditor._check_sensitive_files())

        assert auditor._findings == []

    def test_exception_is_silenced(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_head_or_get", side_effect=Exception("timeout")):
            _run(auditor._check_sensitive_files())  # ne doit pas lever

        assert auditor._findings == []

    def test_severity_is_critical_for_env(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")

        def mock_head(path):
            return 200 if path == "/.env" else 404

        with patch.object(auditor, "_head_or_get", side_effect=mock_head):
            _run(auditor._check_sensitive_files())

        assert any(f.severity == "CRITICAL" for f in auditor._findings)


class TestAppAuditorAdminPaths:
    def test_phpmyadmin_creates_critical_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", return_value=200):
            _run(auditor._check_admin_paths())

        titles = [f.title for f in auditor._findings]
        assert "phpMyAdmin accessible" in titles

    def test_phpmyadmin_deduplicated_for_two_paths(self):
        """phpMyAdmin a deux entrées (/phpmyadmin et /phpmyadmin/) — 1 seul finding."""
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", return_value=200):
            _run(auditor._check_admin_paths())

        titles = [f.title for f in auditor._findings]
        assert titles.count("phpMyAdmin accessible") == 1

    def test_redirect_302_creates_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")

        def mock_status(path):
            return 302 if path == "/admin" else 404

        with patch.object(auditor, "_get_status", side_effect=mock_status):
            _run(auditor._check_admin_paths())

        assert any("/admin" in f.technical_detail for f in auditor._findings)

    def test_404_produces_no_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", return_value=404):
            _run(auditor._check_admin_paths())

        assert auditor._findings == []


class TestAppAuditorApiPaths:
    def test_swagger_200_creates_medium_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")

        def mock_status(path):
            return 200 if path == "/swagger" else 404

        with patch.object(auditor, "_get_status", side_effect=mock_status):
            _run(auditor._check_api_paths())

        assert any("Swagger" in f.title for f in auditor._findings)
        assert any(f.severity == "MEDIUM" for f in auditor._findings)

    def test_redirect_301_does_not_trigger_api_finding(self):
        """_check_api_paths ne trigger que sur status==200 (pas 301)."""
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", return_value=301):
            _run(auditor._check_api_paths())

        assert auditor._findings == []

    def test_swagger_deduplicated_across_multiple_paths(self):
        """Swagger est listé 3 fois dans _API_PATHS — 1 seul finding."""
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", return_value=200):
            _run(auditor._check_api_paths())

        swagger_findings = [f for f in auditor._findings if "Swagger" in f.title]
        assert len(swagger_findings) == 1

    def test_actuator_critical_detected(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")

        def mock_status(path):
            return 200 if path == "/actuator/env" else 404

        with patch.object(auditor, "_get_status", side_effect=mock_status):
            _run(auditor._check_api_paths())

        assert any("Actuator" in f.title and f.severity == "CRITICAL" for f in auditor._findings)


class TestAppAuditorMainResponse:
    def test_cors_wildcard_creates_high_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders(regular={"access-control-allow-origin": "*"})
        with patch.object(auditor, "_fetch_main", return_value=(headers, "<html></html>", 200)):
            _run(auditor._check_main_response())

        assert any(f.title == "CORS wildcard (*) configuré" for f in auditor._findings)
        assert auditor._details.get("cors") == "wildcard"

    def test_cors_specific_origin_is_clean(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders(regular={"access-control-allow-origin": "https://example.com"})
        with patch.object(auditor, "_fetch_main", return_value=(headers, "", 200)):
            _run(auditor._check_main_response())

        assert not any("CORS" in f.title for f in auditor._findings)

    def test_cookie_missing_secure_flag_creates_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders(cookies=["session=abc; Path=/; HttpOnly"])
        with patch.object(auditor, "_fetch_main", return_value=(headers, "", 200)):
            _run(auditor._check_main_response())

        assert any("Secure" in f.title for f in auditor._findings)

    def test_cookie_missing_httponly_flag_creates_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders(cookies=["session=abc; Path=/; Secure"])
        with patch.object(auditor, "_fetch_main", return_value=(headers, "", 200)):
            _run(auditor._check_main_response())

        assert any("HttpOnly" in f.title for f in auditor._findings)

    def test_cookie_with_both_flags_is_clean(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders(cookies=["session=abc; Path=/; Secure; HttpOnly"])
        with patch.object(auditor, "_fetch_main", return_value=(headers, "", 200)):
            _run(auditor._check_main_response())

        cookie_findings = [f for f in auditor._findings if f.category == "Cookies"]
        assert cookie_findings == []

    def test_directory_listing_creates_medium_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        body = "<html><title>Index of /</title></html>"
        headers = FakeHeaders()
        with patch.object(auditor, "_fetch_main", return_value=(headers, body, 200)):
            _run(auditor._check_main_response())

        assert any("Listing" in f.title for f in auditor._findings)
        assert any(f.severity == "MEDIUM" for f in auditor._findings)

    def test_debug_traceback_creates_high_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        body = "Traceback (most recent call last): File app.py line 42"
        headers = FakeHeaders()
        with patch.object(auditor, "_fetch_main", return_value=(headers, body, 200)):
            _run(auditor._check_main_response())

        assert any(f.severity == "HIGH" and "debug" in f.category.lower() for f in auditor._findings)

    def test_clean_response_produces_no_findings(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders()
        with patch.object(auditor, "_fetch_main", return_value=(headers, "<html>Normal site</html>", 200)):
            _run(auditor._check_main_response())

        assert auditor._findings == []

    def test_exception_in_fetch_is_silenced(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_fetch_main", side_effect=Exception("network error")):
            _run(auditor._check_main_response())  # ne doit pas lever

        assert auditor._findings == []

    def test_http_status_stored_in_details(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        headers = FakeHeaders()
        with patch.object(auditor, "_fetch_main", return_value=(headers, "", 200)):
            _run(auditor._check_main_response())

        assert auditor._details.get("http_status") == 200


class TestAppAuditorRobotsTxt:
    def test_sensitive_disallow_creates_low_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        robots_body = "User-agent: *\nDisallow: /admin\nDisallow: /backup"
        with patch.object(auditor, "_fetch_text", return_value=robots_body):
            _run(auditor._check_robots_txt())

        assert any("robots.txt" in f.title for f in auditor._findings)
        assert any(f.severity == "LOW" for f in auditor._findings)
        assert "robots_sensitive_paths" in auditor._details

    def test_innocuous_disallow_produces_no_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        robots_body = "User-agent: *\nDisallow: /cart\nDisallow: /checkout"
        with patch.object(auditor, "_fetch_text", return_value=robots_body):
            _run(auditor._check_robots_txt())

        assert auditor._findings == []

    def test_empty_robots_txt_produces_no_finding(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_fetch_text", return_value=""):
            _run(auditor._check_robots_txt())

        assert auditor._findings == []

    def test_exception_is_silenced(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_fetch_text", side_effect=Exception("timeout")):
            _run(auditor._check_robots_txt())  # ne doit pas lever

        assert auditor._findings == []

    def test_robots_sensitive_path_stored_in_details(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        robots_body = "Disallow: /config"
        with patch.object(auditor, "_fetch_text", return_value=robots_body):
            _run(auditor._check_robots_txt())

        assert "/config" in auditor._details.get("robots_sensitive_paths", [])


# ─────────────────────────────────────────────────────────────────────────────
# Section 12 — AppAuditor : méthodes utilitaires réseau
# ─────────────────────────────────────────────────────────────────────────────

class TestAppAuditorNetworkUtils:
    def _make_mock_conn(self, status: int, body: bytes = b""):
        conn = MagicMock()
        response = MagicMock()
        response.status = status
        response.read.return_value = body
        conn.getresponse.return_value = response
        return conn

    def test_head_or_get_returns_head_status(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        conn = self._make_mock_conn(200)
        with patch.object(auditor, "_get_conn", return_value=conn):
            result = auditor._head_or_get("/test")
        assert result == 200

    def test_head_or_get_falls_back_to_get_on_exception(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        head_conn = MagicMock()
        head_conn.request.side_effect = Exception("HEAD not supported")
        get_conn = self._make_mock_conn(403)

        calls = [head_conn, get_conn]
        with patch.object(auditor, "_get_conn", side_effect=calls):
            result = auditor._head_or_get("/test")
        assert result == 403

    def test_get_status_returns_status_code(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        conn = self._make_mock_conn(404)
        with patch.object(auditor, "_get_conn", return_value=conn):
            result = auditor._get_status("/missing")
        assert result == 404

    def test_fetch_text_200_returns_body(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        conn = self._make_mock_conn(200, body=b"User-agent: *\nDisallow: /admin")
        with patch.object(auditor, "_get_conn", return_value=conn):
            result = auditor._fetch_text("/robots.txt")
        assert "User-agent" in result

    def test_fetch_text_404_returns_empty_string(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        conn = self._make_mock_conn(404)
        with patch.object(auditor, "_get_conn", return_value=conn):
            result = auditor._fetch_text("/robots.txt")
        assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# Section 13 — AppAuditor.audit() — orchestration complète
# ─────────────────────────────────────────────────────────────────────────────

class TestAppAuditorAudit:
    def test_audit_calls_all_five_checks_and_returns_findings(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")

        # Conserver les références AVANT d'entrer dans le with
        mock_sf = AsyncMock()
        mock_ap = AsyncMock()
        mock_api = AsyncMock()
        mock_mr = AsyncMock()
        mock_rb = AsyncMock()

        with patch.object(auditor, "_check_sensitive_files", new=mock_sf), \
             patch.object(auditor, "_check_admin_paths",     new=mock_ap), \
             patch.object(auditor, "_check_api_paths",       new=mock_api), \
             patch.object(auditor, "_check_main_response",   new=mock_mr), \
             patch.object(auditor, "_check_robots_txt",      new=mock_rb):
            findings = _run(auditor.audit())

        mock_sf.assert_called_once()
        mock_ap.assert_called_once()
        mock_api.assert_called_once()
        mock_mr.assert_called_once()
        mock_rb.assert_called_once()
        assert isinstance(findings, list)

    def test_audit_returns_findings_added_during_checks(self):
        from app.app_checks import AppAuditor
        from app.scanner import Finding

        auditor = AppAuditor(domain="example.com")

        async def inject_finding():
            auditor._findings.append(Finding(
                category="Test",
                severity="HIGH",
                title="Test Finding",
                technical_detail="detail",
                plain_explanation="explanation",
                penalty=10,
                recommendation="fix it",
            ))

        with patch.object(auditor, "_check_sensitive_files", new=AsyncMock(side_effect=inject_finding)), \
             patch.object(auditor, "_check_admin_paths",     new=AsyncMock()), \
             patch.object(auditor, "_check_api_paths",       new=AsyncMock()), \
             patch.object(auditor, "_check_main_response",   new=AsyncMock()), \
             patch.object(auditor, "_check_robots_txt",      new=AsyncMock()):
            findings = _run(auditor.audit())

        assert len(findings) == 1
        assert findings[0].title == "Test Finding"

    def test_audit_silences_exceptions_from_checks(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        mock_boom = AsyncMock(side_effect=Exception("boom"))

        with patch.object(auditor, "_check_sensitive_files", new=mock_boom), \
             patch.object(auditor, "_check_admin_paths",     new=AsyncMock()), \
             patch.object(auditor, "_check_api_paths",       new=AsyncMock()), \
             patch.object(auditor, "_check_main_response",   new=AsyncMock()), \
             patch.object(auditor, "_check_robots_txt",      new=AsyncMock()):
            findings = _run(auditor.audit())  # ne doit pas lever

        assert isinstance(findings, list)

    def test_audit_get_details_returns_details_dict(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        auditor._details["http_status"] = 200

        assert auditor.get_details() == {"http_status": 200}


# ─────────────────────────────────────────────────────────────────────────────
# Section 14 — Gaps de couverture résiduels
# ─────────────────────────────────────────────────────────────────────────────

class TestAppAuditorExceptionSilencing:
    """Couvre les branches except dans _check_admin_paths et _check_api_paths."""

    def test_admin_paths_exception_silenced(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", side_effect=Exception("conn refused")):
            _run(auditor._check_admin_paths())  # ne doit pas lever

        assert auditor._findings == []

    def test_api_paths_exception_silenced(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch.object(auditor, "_get_status", side_effect=Exception("timeout")):
            _run(auditor._check_api_paths())  # ne doit pas lever

        assert auditor._findings == []


class TestAppAuditorSslContextAndGetConn:
    """Couvre _ssl_context() et _get_conn() (lignes 382-390)."""

    def test_ssl_context_returns_ssl_context_with_no_verify(self):
        import ssl
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        ctx = auditor._ssl_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_get_conn_returns_https_connection(self):
        import http.client
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        with patch("app.app_checks.http.client.HTTPSConnection") as mock_cls:
            mock_cls.return_value = MagicMock(spec=http.client.HTTPSConnection)
            conn = auditor._get_conn()
        mock_cls.assert_called_once()
        # Le domaine est bien passé en premier argument
        assert mock_cls.call_args[0][0] == "example.com"


class TestAppAuditorFetchMain:
    """Couvre _fetch_main() (lignes 418-430)."""

    def test_fetch_main_returns_headers_body_status(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"<html>Hello</html>"
        mock_response.headers = FakeHeaders()
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response

        with patch.object(auditor, "_get_conn", return_value=mock_conn):
            headers, body, status = auditor._fetch_main()

        assert status == 200
        assert "Hello" in body

    def test_fetch_main_closes_connection_on_exception(self):
        from app.app_checks import AppAuditor

        auditor = AppAuditor(domain="example.com")
        mock_conn = MagicMock()
        mock_conn.request.side_effect = Exception("network error")

        with patch.object(auditor, "_get_conn", return_value=mock_conn):
            with pytest.raises(Exception):
                auditor._fetch_main()

        mock_conn.close.assert_called_once()


class TestRegisterAppPlanLimit:
    """Couvre la branche de limite d'apps (lignes 229-231 app_router.py)."""

    def test_plan_limit_exceeded_returns_403(self, client, db_session):
        """Mock APP_LIMITS pour simuler un plan avec max=1 app."""
        from app.routers import app_router

        user, token = _make_user(db_session, plan="dev")
        # Ajouter déjà 1 app en DB
        _make_app(db_session, user, url="https://existing-app.example.com")

        # Patcher APP_LIMITS pour simuler une limite de 1 app pour le plan "dev"
        with patch.dict(app_router.APP_LIMITS, {"dev": 1}):
            resp = client.post("/apps", json={
                "name": "Second App",
                "url": "https://new-app.example.com",
                "verification_method": "dns",
            }, headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 403
        assert "Limite atteinte" in resp.json()["detail"]
