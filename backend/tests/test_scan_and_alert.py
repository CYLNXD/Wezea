"""
Tests unitaires pour scheduler._scan_and_alert
===============================================
Stratégie :
  - AuditManager.run() mocké → résultat déterministe
  - _send_monitoring_alert mocké → on vérifie si/comment l'alerte est envoyée
  - fire_webhooks mocké → aucun appel réseau
  - DB : SQLite in-memory via les fixtures conftest (db_session)

On teste :
  1. Comportement avec user inactif / inexistant
  2. Mise à jour en DB (score, risk, last_scan_at, ssl_days, open_ports, tech)
  3. Déclenchement d'alerte (score drop, CRITICAL finding, change_alerts)
  4. Absence d'alerte quand le score est stable
  5. Envoi du rapport PDF quand email_report=True
"""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_finding(title="Test finding", severity="HIGH", penalty=15):
    f = SimpleNamespace()
    f.title    = title
    f.severity = severity
    f.penalty  = penalty
    return f


def _make_scan_result(
    score: int = 75,
    risk: str  = "LOW",
    findings   = None,
    ssl_days: int | None = None,
    port_details: dict | None = None,
    vuln_details: dict | None = None,
):
    """Construit un ScanResult minimal pour les mocks."""
    r = MagicMock()
    r.security_score = score
    r.risk_level     = risk
    r.findings       = findings or []
    r.ssl_details    = {"days_left": ssl_days} if ssl_days is not None else {}
    r.port_details   = port_details or {}
    r.vuln_details   = vuln_details or {"detected_stack": []}
    return r


def _make_monitored(
    db_session,
    user_id: int,
    domain: str = "example.com",
    last_score: int | None = None,
    alert_threshold: int = 10,
    email_report: bool = False,
    last_open_ports: str | None = None,
    last_technologies: str | None = None,
):
    """Crée un MonitoredDomain minimal en DB."""
    from app.models import MonitoredDomain
    m = MonitoredDomain(
        user_id          = user_id,
        domain           = domain,
        is_active        = True,
        last_score       = last_score,
        alert_threshold  = alert_threshold,
        email_report     = email_report,
        last_open_ports  = last_open_ports,
        last_technologies = last_technologies,
    )
    db_session.add(m)
    db_session.commit()
    db_session.refresh(m)
    return m


def _make_active_user(db_session, plan: str = "starter") -> "User":
    import uuid
    from app.models import User
    from app.auth import hash_password, generate_api_key
    email = f"monitor-{uuid.uuid4().hex[:8]}@example.com"
    u = User(
        email         = email,
        password_hash = hash_password("x"),
        plan          = plan,
        api_key       = generate_api_key(),
        is_active     = True,
        first_name    = "Alice",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


# ─────────────────────────────────────────────────────────────────────────────
# Patches communs
# ─────────────────────────────────────────────────────────────────────────────

def _audit_mock(result):
    """Patch AuditManager.run() pour retourner `result`."""
    m = MagicMock()
    m.run = AsyncMock(return_value=result)
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestScanAndAlert:

    @pytest.mark.asyncio
    async def test_inactive_user_skipped(self, db_session):
        """Si l'user n'existe pas ou est inactif, aucun scan n'est lancé."""
        from app.models import User
        from app.auth import hash_password, generate_api_key
        import uuid

        email = f"inactive-{uuid.uuid4().hex[:8]}@example.com"
        u = User(
            email=email, password_hash=hash_password("x"),
            plan="starter", api_key=generate_api_key(), is_active=False,
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)

        monitored = _make_monitored(db_session, u.id)
        from app.scheduler import _scan_and_alert

        with patch("app.scanner.AuditManager") as mock_am:
            await _scan_and_alert(monitored, db_session)
        mock_am.assert_not_called()

    @pytest.mark.asyncio
    async def test_score_updated_in_db(self, db_session):
        """Le score et le risk_level sont mis à jour en DB après le scan."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, last_score=80)
        result = _make_scan_result(score=65, risk="MEDIUM")

        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        db_session.refresh(m)
        assert m.last_score      == 65
        assert m.last_risk_level == "MEDIUM"
        assert m.last_scan_at    is not None

    @pytest.mark.asyncio
    async def test_no_alert_when_score_stable(self, db_session):
        """Pas d'alerte si le score ne baisse pas sous le seuil."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, last_score=75, alert_threshold=10)
        result = _make_scan_result(score=70)  # drop = 5 < seuil 10

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_sent_on_score_drop(self, db_session):
        """Alerte envoyée quand le score chute de plus de alert_threshold."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, last_score=80, alert_threshold=10)
        result = _make_scan_result(score=60)  # drop = 20 >= seuil 10

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        kwargs = mock_alert.call_args[1]
        assert kwargs["new_score"]  == 60
        assert kwargs["prev_score"] == 80
        assert kwargs["domain"]     == m.domain

    @pytest.mark.asyncio
    async def test_alert_sent_on_critical_finding(self, db_session):
        """Alerte envoyée quand un finding CRITICAL est détecté."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, last_score=75, alert_threshold=20)
        # Drop = 5 < seuil, mais finding CRITICAL → alerte quand même
        result = _make_scan_result(
            score=70,
            findings=[_make_finding(severity="CRITICAL", penalty=30)],
        )

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_alert_on_first_scan(self, db_session):
        """Premier scan (last_score=None) → pas d'alerte de baisse de score."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, last_score=None)
        result = _make_scan_result(score=40)  # score bas, mais premier scan

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        # Pas d'alerte de score drop (aucun prev_score), sauf si CRITICAL finding
        # Ici pas de CRITICAL → mock_alert non appelé
        mock_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_ssl_days_updated_in_db(self, db_session):
        """days_left SSL mis à jour en DB après le scan."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id)
        result = _make_scan_result(ssl_days=45)

        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        db_session.refresh(m)
        assert m.last_ssl_expiry_days == 45

    @pytest.mark.asyncio
    async def test_alert_on_ssl_expiry_under_7_days(self, db_session):
        """Alerte envoyée si SSL expire dans ≤ 7 jours."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, last_score=80, alert_threshold=20)
        result = _make_scan_result(score=78, ssl_days=5)

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        reason = mock_alert.call_args[1]["reason"]
        assert "SSL" in reason or "certificat" in reason.lower() or "expire" in reason.lower()

    @pytest.mark.asyncio
    async def test_new_open_port_triggers_alert(self, db_session):
        """Un nouveau port ouvert (non vu avant) déclenche une alerte."""
        u = _make_active_user(db_session)
        # Avant : port 443 ouvert
        m = _make_monitored(
            db_session, u.id,
            last_score=80, alert_threshold=20,
            last_open_ports=json.dumps(["443"]),
        )
        # Après : 443 + 3389 (RDP) ouvert
        result = _make_scan_result(
            score=78,
            port_details={"443": {"open": True}, "3389": {"open": True}},
        )

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        reason = mock_alert.call_args[1]["reason"]
        assert "3389" in reason

    @pytest.mark.asyncio
    async def test_open_ports_saved_in_db(self, db_session):
        """La liste des ports ouverts est persistée en DB."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id)
        result = _make_scan_result(
            port_details={"80": {"open": True}, "443": {"open": True}, "22": {"open": False}},
        )

        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        db_session.refresh(m)
        ports = json.loads(m.last_open_ports)
        assert "80"  in ports
        assert "443" in ports
        assert "22"  not in ports

    @pytest.mark.asyncio
    async def test_pdf_report_sent_when_email_report_enabled(self, db_session):
        """Rapport PDF envoyé si monitored.email_report=True."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, email_report=True)
        result = _make_scan_result()

        mock_pdf = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.scheduler._send_scheduled_pdf_report", mock_pdf), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_pdf.assert_called_once()

    @pytest.mark.asyncio
    async def test_pdf_report_not_sent_when_disabled(self, db_session):
        """Rapport PDF NON envoyé si monitored.email_report=False."""
        u = _make_active_user(db_session)
        m = _make_monitored(db_session, u.id, email_report=False)
        result = _make_scan_result()

        mock_pdf = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=_audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.scheduler._send_scheduled_pdf_report", mock_pdf), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_pdf.assert_not_called()
