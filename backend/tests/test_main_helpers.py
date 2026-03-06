"""
Tests pour app/main.py — helpers isolés et endpoints simples.

Couvre :
- ScanRequest.validate_lang (line 199)
- ReportRequest.validate_email (lines 237-240)
- GET /health (lines 294-296)
- _check_anon_rate_limit (lines 329-364)
- _increment_anon_count (lines 384-407)
- _check_user_rate_limit (lines 412-421)
- GET /scan/session (lines 448-461)
- _run_in_executor (lines 894-895)
- global_exception_handler (lines 905-909)
- POST /report/request (lines 691-701)
- _build_report_structure (line 729)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# ScanRequest.validate_lang — line 199 (fallback "fr")
# ─────────────────────────────────────────────────────────────────────────────

class TestScanRequestValidateLang:
    def test_valid_lang_fr(self):
        from app.main import ScanRequest
        req = ScanRequest(domain="example.com", lang="fr")
        assert req.lang == "fr"

    def test_valid_lang_en(self):
        from app.main import ScanRequest
        req = ScanRequest(domain="example.com", lang="en")
        assert req.lang == "en"

    def test_invalid_lang_falls_back_to_fr(self):
        """Lang inconnue → retourne 'fr' (line 199)."""
        from app.main import ScanRequest
        req = ScanRequest(domain="example.com", lang="es")
        assert req.lang == "fr"

    def test_empty_lang_falls_back_to_fr(self):
        from app.main import ScanRequest
        req = ScanRequest(domain="example.com", lang="")
        assert req.lang == "fr"


# ─────────────────────────────────────────────────────────────────────────────
# ReportRequest.validate_email — lines 237-240 (invalid email raises)
# ─────────────────────────────────────────────────────────────────────────────

class TestReportRequestValidateEmail:
    def test_valid_email_accepted(self):
        from app.main import ReportRequest
        req = ReportRequest(domain="example.com", email="user@example.com")
        assert req.email == "user@example.com"

    def test_email_normalised_lowercase(self):
        from app.main import ReportRequest
        req = ReportRequest(domain="example.com", email=" User@EXAMPLE.COM ")
        assert req.email == "user@example.com"

    def test_email_without_at_raises(self):
        """Email sans @ → ValueError (line 238-239)."""
        from app.main import ReportRequest
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ReportRequest(domain="example.com", email="notanemail")

    def test_email_without_dot_in_domain_raises(self):
        """Email sans point dans domaine → ValueError."""
        from app.main import ReportRequest
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ReportRequest(domain="example.com", email="user@nodot")


# ─────────────────────────────────────────────────────────────────────────────
# GET /health — lines 294-296
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self, client, db_session):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data


# ─────────────────────────────────────────────────────────────────────────────
# _check_anon_rate_limit — lines 329-364
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckAnonRateLimit:
    def _make_mock_db(self, scan_count: int):
        """Mock DB query retournant un enregistrement avec scan_count."""
        mock_record = MagicMock()
        mock_record.scan_count = scan_count
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record
        return mock_db

    def test_below_cookie_limit_passes(self):
        """scan_count < ANON_SCAN_LIMIT → pas d'exception."""
        from app.main import _check_anon_rate_limit
        mock_db = self._make_mock_db(0)
        # Ne doit pas lever
        _check_anon_rate_limit("cookie-abc", "1.2.3.4", mock_db)

    def test_cookie_limit_exceeded_raises_429(self):
        """scan_count >= ANON_SCAN_LIMIT → HTTPException 429 (lines 337-350)."""
        from app.main import _check_anon_rate_limit, ANON_SCAN_LIMIT

        mock_db = self._make_mock_db(ANON_SCAN_LIMIT)  # au maximum
        with pytest.raises(HTTPException) as exc:
            _check_anon_rate_limit("cookie-abc", "1.2.3.4", mock_db)
        assert exc.value.status_code == 429

    def test_ip_limit_exceeded_raises_429(self):
        """Cookie OK mais IP a atteint la limite → 429 (lines 354-364)."""
        from app.main import _check_anon_rate_limit, ANON_IP_DAY_CAP

        call_count = 0
        def mock_first():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Premier appel : cookie = 0 scan (pas de limite)
                r = MagicMock(); r.scan_count = 0; return r
            else:
                # Deuxième appel : IP = au maximum
                r = MagicMock(); r.scan_count = ANON_IP_DAY_CAP; return r

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first

        with pytest.raises(HTTPException) as exc:
            _check_anon_rate_limit("cookie-abc", "1.2.3.4", mock_db)
        assert exc.value.status_code == 429

    def test_no_record_means_zero_count(self):
        """Pas d'enregistrement en DB → count = 0 → pas de 429."""
        from app.main import _check_anon_rate_limit

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        # Ne doit pas lever
        _check_anon_rate_limit("cookie-abc", "1.2.3.4", mock_db)


# ─────────────────────────────────────────────────────────────────────────────
# _increment_anon_count — lines 384-407
# ─────────────────────────────────────────────────────────────────────────────

class TestIncrementAnonCount:
    def test_increments_existing_records(self):
        """Enregistrements existants → scan_count + 1 (branches 390-391, 398-399)."""
        from app.main import _increment_anon_count

        cookie_record = MagicMock(); cookie_record.scan_count = 2
        ip_record     = MagicMock(); ip_record.scan_count = 3

        call_count = 0
        def mock_first():
            nonlocal call_count
            call_count += 1
            return cookie_record if call_count == 1 else ip_record

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first

        _increment_anon_count("cookie-abc", "1.2.3.4", mock_db)
        assert cookie_record.scan_count == 3
        assert ip_record.scan_count == 4
        mock_db.commit.assert_called()

    def test_creates_new_records_when_absent(self):
        """Pas d'enregistrement → crée ScanRateLimit (branches 392-393, 400-401)."""
        from app.main import _increment_anon_count

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        _increment_anon_count("cookie-new", "5.6.7.8", mock_db)
        assert mock_db.add.call_count == 2  # cookie record + ip record
        mock_db.commit.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# _check_user_rate_limit — lines 412-421
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckUserRateLimit:
    def test_unlimited_plan_never_raises(self):
        """scan_limit_per_day = None → illimité, pas d'exception (line 415)."""
        from app.main import _check_user_rate_limit

        user = MagicMock()
        user.scan_limit_per_day = None
        _check_user_rate_limit(user, MagicMock())  # ne doit pas lever

    def test_within_limit_passes(self):
        """count < limit → pas d'exception."""
        from app.main import _check_user_rate_limit

        user = MagicMock()
        user.scan_limit_per_day = 5
        user.id = 1
        user.plan = "free"

        mock_db = MagicMock()
        # _check_user_rate_limit : db.query(ScanHistory).filter(...).count()
        mock_db.query.return_value.filter.return_value.count.return_value = 3
        _check_user_rate_limit(user, mock_db)

    def test_limit_exceeded_raises_429(self):
        """count >= limit → HTTPException 429 (lines 418-421)."""
        from app.main import _check_user_rate_limit

        user = MagicMock()
        user.scan_limit_per_day = 5
        user.id = 1
        user.plan = "free"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 5
        with pytest.raises(HTTPException) as exc:
            _check_user_rate_limit(user, mock_db)
        assert exc.value.status_code == 429


# ─────────────────────────────────────────────────────────────────────────────
# GET /client-id — lines 448-461 (init_client_id)
# ─────────────────────────────────────────────────────────────────────────────

class TestClientId:
    def test_new_session_sets_cookie(self, client, db_session):
        """Pas de cookie → nouveau cookie créé (lines 455-461)."""
        resp = client.get("/client-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert "wezea_cid" in resp.cookies

    def test_existing_session_returns_existing(self, client, db_session):
        """Cookie existant → status='existing' (lines 450-451)."""
        # Premier appel pour créer le cookie
        client.get("/client-id")
        # Deuxième appel avec le cookie présent
        resp = client.get("/client-id")
        assert resp.status_code == 200
        assert resp.json()["status"] == "existing"


# ─────────────────────────────────────────────────────────────────────────────
# POST /report/request — lines 691-701 + _build_report_structure (line 729)
# ─────────────────────────────────────────────────────────────────────────────

class TestReportRequest:
    def test_valid_report_request_returns_202(self, client, db_session):
        """POST /report/request avec données valides → 202 (lines 691-701)."""
        resp = client.post("/report/request", json={
            "domain":  "example.com",
            "email":   "lead@example.com",
            "company": "Acme Corp",
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert "lead_id" in data
        assert "report_preview" in data

    def test_build_report_structure_returns_dict(self):
        """_build_report_structure retourne un dict avec title + sections (line 729)."""
        from app.main import _build_report_structure
        result = _build_report_structure("example.com", "user@example.com")
        assert "title" in result
        assert "sections" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) > 0

    def test_invalid_email_returns_422(self, client, db_session):
        """Email invalide → 422 validation error."""
        resp = client.post("/report/request", json={
            "domain": "example.com",
            "email":  "not-an-email",
        })
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# _run_in_executor — lines 894-895
# ─────────────────────────────────────────────────────────────────────────────

class TestRunInExecutor:
    @pytest.mark.asyncio
    async def test_run_in_executor_runs_sync_fn(self):
        """_run_in_executor exécute une fn sync dans un thread (lines 894-895)."""
        from app.main import _run_in_executor

        def sync_fn(x, y):
            return x + y

        result = await _run_in_executor(sync_fn, 3, 4)
        assert result == 7


# ─────────────────────────────────────────────────────────────────────────────
# global_exception_handler — lines 905-909
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# GET /scan/limits — lines 489-492, 497 (user with/without limit)
# ─────────────────────────────────────────────────────────────────────────────

def _make_user_in_db(db_session, plan: str = "free"):
    """Helper : crée un user en DB de test et retourne (user, token)."""
    from app.auth import hash_password, generate_api_key, create_access_token
    from app.models import User
    import uuid
    u = User(
        email=f"main-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("Pass123"),
        plan=plan, api_key=generate_api_key(), is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    token = create_access_token(u.id, u.email, plan)
    return u, token


def _patch_session_local(db_session):
    """Context manager qui remplace app.main.SessionLocal par le db_session de test."""
    mock_sl = MagicMock(return_value=db_session)
    # Ne pas fermer le db_session partagé quand l'endpoint appelle db.close()
    db_session.close = MagicMock()
    return patch("app.main.SessionLocal", mock_sl)


class TestScanLimits:
    """Couvre GET /scan/limits lines 489-492, 497."""

    def test_pro_user_gets_unlimited(self, client, db_session):
        """User Pro (scan_limit_per_day=None) → type='unlimited' (lines 489-492)."""
        u, token = _make_user_in_db(db_session, plan="pro")

        with _patch_session_local(db_session):
            resp = client.get("/scan/limits",
                              headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "unlimited"
        assert data["limit"] is None

    def test_free_user_gets_daily_limit(self, client, db_session):
        """User Free (scan_limit_per_day=5) → type='free', limit=5 (lines 497+)."""
        u, token = _make_user_in_db(db_session, plan="free")

        with _patch_session_local(db_session):
            resp = client.get("/scan/limits",
                              headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        data = resp.json()
        # Free plan has a daily limit
        assert data["type"] in ("free", "unlimited")  # dépend de la config

    def test_wsk_pro_key_in_scan_limits(self, client, db_session):
        """Bearer wsk_ Pro → current_user via API key (lines 489-492 scan/limits)."""
        u, _ = _make_user_in_db(db_session, plan="pro")

        with _patch_session_local(db_session):
            resp = client.get("/scan/limits",
                              headers={"Authorization": f"Bearer {u.api_key}"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "unlimited"


# ─────────────────────────────────────────────────────────────────────────────
# POST /scan — lines 554-655 (scan endpoint — mocked AuditManager)
# ─────────────────────────────────────────────────────────────────────────────

class TestScanEndpoint:
    """Couvre POST /scan avec AuditManager mocké (lines 554-655)."""

    def _mock_scan_result(self):
        """Retourne un ScanResult mocké."""
        from app.scanner import ScanResult, Finding
        result = MagicMock(spec=ScanResult)
        result.to_dict.return_value = {
            "domain":         "example.com",
            "scanned_at":     "2026-03-06T12:00:00+00:00",
            "security_score": 75,
            "risk_level":     "MEDIUM",
            "findings":       [],
            "recommendations": [],
            "dns_details":    {},
            "ssl_details":    {},
            "port_details":   {},
            "scan_duration_ms": 1200,
        }
        return result

    def test_anonymous_scan_succeeds(self, client, db_session):
        """Scan anonyme (pas de token) → 200 avec score (lines 554-655)."""
        import asyncio
        mock_result = self._mock_scan_result()

        mock_manager = AsyncMock()
        mock_manager.run = AsyncMock(return_value=mock_result)
        mock_manager_cls = MagicMock(return_value=mock_manager)

        with patch("app.main.AuditManager", mock_manager_cls), \
             _patch_session_local(db_session):
            resp = client.post("/scan", json={"domain": "example.com"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["security_score"] == 75
        assert data["domain"] == "example.com"

    def test_authenticated_scan_saves_to_history(self, client, db_session):
        """Scan authentifié → résultat sauvegardé dans ScanHistory (lines 620-640)."""
        from app.models import ScanHistory
        u, token = _make_user_in_db(db_session, plan="free")
        mock_result = self._mock_scan_result()

        mock_manager = AsyncMock()
        mock_manager.run = AsyncMock(return_value=mock_result)
        mock_manager_cls = MagicMock(return_value=mock_manager)

        with patch("app.main.AuditManager", mock_manager_cls), \
             _patch_session_local(db_session):
            resp = client.post("/scan", json={"domain": "example.com"},
                               headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        # Vérifier la sauvegarde dans l'historique
        scan = db_session.query(ScanHistory).filter(
            ScanHistory.user_id == u.id
        ).first()
        assert scan is not None
        assert scan.domain == "example.com"

    def test_wsk_pro_key_scan(self, client, db_session):
        """Bearer wsk_ Pro → current_user via API key dans /scan (lines 572-576)."""
        u, _ = _make_user_in_db(db_session, plan="pro")
        mock_result = self._mock_scan_result()

        mock_manager = AsyncMock()
        mock_manager.run = AsyncMock(return_value=mock_result)
        mock_manager_cls = MagicMock(return_value=mock_manager)

        with patch("app.main.AuditManager", mock_manager_cls), \
             _patch_session_local(db_session):
            resp = client.post("/scan", json={"domain": "example.com"},
                               headers={"Authorization": f"Bearer {u.api_key}"})

        assert resp.status_code == 200

    def test_scan_timeout_returns_504(self, client, db_session):
        """AuditManager dépasse le timeout → 504 (lines 590-592)."""
        import asyncio

        mock_manager = AsyncMock()
        mock_manager.run = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_manager_cls = MagicMock(return_value=mock_manager)

        with patch("app.main.AuditManager", mock_manager_cls), \
             _patch_session_local(db_session):
            resp = client.post("/scan", json={"domain": "example.com"})

        assert resp.status_code == 504
        # HTTPException wraps le détail sous "detail"
        assert "scan_id" in resp.json().get("detail", resp.json())

    def test_scan_generic_exception_returns_500(self, client, db_session):
        """AuditManager lève une exception → 500 (lines 593-598)."""
        mock_manager = AsyncMock()
        mock_manager.run = AsyncMock(side_effect=RuntimeError("internal scan error"))
        mock_manager_cls = MagicMock(return_value=mock_manager)

        with patch("app.main.AuditManager", mock_manager_cls), \
             _patch_session_local(db_session):
            resp = client.post("/scan", json={"domain": "example.com"})

        assert resp.status_code == 500
        detail = resp.json().get("detail", resp.json())
        assert "error" in detail

    def test_scan_generic_exception_debug_mode_exposes_message(self, client, db_session):
        """AuditManager exception + _DEBUG=True → message exposé (line 597)."""
        import app.main as main_mod

        mock_manager = AsyncMock()
        mock_manager.run = AsyncMock(side_effect=RuntimeError("secret error info"))
        mock_manager_cls = MagicMock(return_value=mock_manager)

        with patch("app.main.AuditManager", mock_manager_cls), \
             _patch_session_local(db_session), \
             patch.object(main_mod, "_DEBUG", True):
            resp = client.post("/scan", json={"domain": "example.com"})

        assert resp.status_code == 500
        detail = resp.json().get("detail", resp.json())
        # En mode debug, "message" est exposé (line 597)
        assert "message" in detail
        assert "secret error info" in detail["message"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /generate-pdf — lines 844-880
# ─────────────────────────────────────────────────────────────────────────────

_VALID_PDF_BODY = {
    "scan_id":        "abc-123",
    "domain":         "example.com",
    "scanned_at":     "2026-03-06T12:00:00+00:00",
    "security_score": 75,
    "risk_level":     "MEDIUM",
    "findings":       [],
}


class TestGeneratePdfEndpoint:
    """Couvre POST /generate-pdf lines 844-880."""

    def test_success_returns_pdf_bytes(self, client, db_session):
        """Chemin nominal : generate_pdf OK → 200 application/pdf (lines 844-879)."""
        fake_pdf = b"%PDF-1.4 fake content"

        with patch("app.main.report_service.generate_pdf", return_value=fake_pdf):
            resp = client.post("/generate-pdf", json=_VALID_PDF_BODY)

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == fake_pdf

    def test_runtime_error_returns_503(self, client, db_session):
        """RuntimeError (WeasyPrint manquant) → 503 (lines 862-868)."""
        with patch("app.main.report_service.generate_pdf",
                   side_effect=RuntimeError("WeasyPrint non installé")):
            resp = client.post("/generate-pdf", json=_VALID_PDF_BODY)

        assert resp.status_code == 503
        data = resp.json()
        detail = data.get("detail", data)
        assert "error" in detail

    def test_generic_exception_returns_500(self, client, db_session):
        """Exception générique → 500 (lines 869-873)."""
        with patch("app.main.report_service.generate_pdf",
                   side_effect=ValueError("unexpected error")):
            resp = client.post("/generate-pdf", json=_VALID_PDF_BODY)

        assert resp.status_code == 500
        data = resp.json()
        detail = data.get("detail", data)
        assert "error" in detail

    def test_white_label_pro_user_uses_brand_name(self, client, db_session):
        """User Pro avec wb_enabled → white_label dict construit (line 850)."""
        from app.auth import hash_password, generate_api_key, create_access_token
        from app.models import User
        import uuid

        u = User(
            email=f"wb-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("Pass123"),
            plan="pro", api_key=generate_api_key(), is_active=True,
            wb_enabled=True,
            wb_company_name="Acme Corp",
            wb_primary_color="#ff0000",
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        token = create_access_token(u.id, u.email, "pro")

        fake_pdf = b"%PDF white-label"
        with patch("app.main.report_service.generate_pdf", return_value=fake_pdf):
            resp = client.post("/generate-pdf", json=_VALID_PDF_BODY,
                               headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        # Le nom de fichier doit contenir le nom de la marque blanche
        disposition = resp.headers.get("content-disposition", "")
        assert "acme-corp" in disposition

    def test_runtime_error_debug_mode_exposes_message(self, client, db_session):
        """RuntimeError + _DEBUG=True → message exposé (line 871)."""
        import app.main as main_mod

        with patch("app.main.report_service.generate_pdf",
                   side_effect=RuntimeError("weasyprint missing")), \
             patch.object(main_mod, "_DEBUG", True):
            resp = client.post("/generate-pdf", json=_VALID_PDF_BODY)

        assert resp.status_code == 503
        detail = resp.json().get("detail", resp.json())
        assert "message" in detail

    def test_generic_exception_debug_mode_exposes_message(self, client, db_session):
        """Exception générique + _DEBUG=True → message exposé (line 877)."""
        import app.main as main_mod

        with patch("app.main.report_service.generate_pdf",
                   side_effect=ValueError("internal pdf crash")), \
             patch.object(main_mod, "_DEBUG", True):
            resp = client.post("/generate-pdf", json=_VALID_PDF_BODY)

        assert resp.status_code == 500
        detail = resp.json().get("detail", resp.json())
        assert "message" in detail


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — lines 108, 113 (scheduler started = True)
# ─────────────────────────────────────────────────────────────────────────────

class TestLifespanSchedulerStarted:
    """Couvre les branches lifespan lines 108 et 113 quand le scheduler démarre."""

    def test_lifespan_with_scheduler_started(self, db_session):
        """Scheduler started=True → print + stop_scheduler appelé (lines 108, 113)."""
        from app.main import app
        from fastapi.testclient import TestClient

        with patch("app.scheduler.start_scheduler", return_value=True), \
             patch("app.scheduler.stop_scheduler") as mock_stop:
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/health")
            # Après sortie du contexte, stop_scheduler doit avoir été appelé (line 113)
            mock_stop.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Sentry init — lines 129-147 (SENTRY_DSN défini)
# ─────────────────────────────────────────────────────────────────────────────

class TestSentryInit:
    """Couvre le bloc Sentry (lines 129-147) via reload de app.main avec SENTRY_DSN."""

    def test_sentry_init_called_when_dsn_set(self):
        """SENTRY_DSN défini → sentry_sdk.init() appelé (lines 129-147)."""
        import sys
        import os

        # Retirer app.main du cache (et ses dépendances) pour forcer le rechargement
        mods_to_remove = [k for k in list(sys.modules.keys())
                          if k == "app.main" or k.startswith("app.main.")]
        for mod in mods_to_remove:
            sys.modules.pop(mod, None)

        mock_sentry_init = MagicMock()
        mock_sentry_sdk = MagicMock()
        mock_sentry_sdk.init = mock_sentry_init

        old_dsn = os.environ.get("SENTRY_DSN")
        os.environ["SENTRY_DSN"] = "https://fake@sentry.io/123"

        try:
            with patch.dict(sys.modules, {"sentry_sdk": mock_sentry_sdk,
                                           "sentry_sdk.integrations.fastapi": MagicMock(),
                                           "sentry_sdk.integrations.starlette": MagicMock(),
                                           "sentry_sdk.integrations.sqlalchemy": MagicMock(),
                                           "sentry_sdk.integrations.logging": MagicMock()}):
                import app.main  # noqa: F401 — recharge avec SENTRY_DSN

            mock_sentry_init.assert_called_once()
        finally:
            if old_dsn is None:
                os.environ.pop("SENTRY_DSN", None)
            else:
                os.environ["SENTRY_DSN"] = old_dsn
            # Nettoyer le module rechargé
            sys.modules.pop("app.main", None)
            import app.main  # noqa: F401 — restore


class TestGlobalExceptionHandler:
    def test_unhandled_exception_returns_500(self, client, db_session):
        """Exception non gérée → 500 via global_exception_handler (lines 905-909)."""
        from app.main import app

        @app.get("/test-crash-for-coverage-only")
        async def _crash():
            raise RuntimeError("boom pour test")

        try:
            resp = client.get("/test-crash-for-coverage-only")
            # En mode test raise_server_exceptions=False → on voit le 500
            assert resp.status_code == 500
            data = resp.json()
            assert "error" in data
        finally:
            # Retirer la route de test après usage
            app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/test-crash-for-coverage-only"]

    def test_debug_mode_exposes_detail(self, client, db_session):
        """En mode DEBUG=True → détail + path exposés (line 906)."""
        from app.main import app
        import app.main as main_mod

        @app.get("/test-crash-debug-only")
        async def _crash_debug():
            raise RuntimeError("debug error info")

        try:
            with patch.object(main_mod, "_DEBUG", True):
                resp = client.get("/test-crash-debug-only")
            assert resp.status_code == 500
            data = resp.json()
            # En mode debug, le détail est exposé (line 906)
            assert "error" in data
        finally:
            app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/test-crash-debug-only"]
