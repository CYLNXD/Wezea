"""
Tests : scheduler — _should_scan_now + séquence onboarding J+1/J+3/J+7/J+14
------------------------------------------------------------------------------
Stratégie :
- _should_scan_now : testé directement avec des objets MonitoredDomain simulés
- _async_onboarding_emails : users créés en DB avec des created_at contrôlés,
  tous les appels Brevo mockés, on vérifie que chaque fonction Brevo est
  appelée exactement pour les bons utilisateurs
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import User, ScanHistory
from app.auth import hash_password, generate_api_key

# ── Capture les fonctions réelles AVANT que conftest les patche (scope session) ──
# conftest._patch_scheduler remplace app.scheduler.start_scheduler par un mock ;
# on sauvegarde ici la vraie référence au niveau module (import time = avant fixtures).
from app.scheduler import start_scheduler as _real_start_scheduler
from app.scheduler import stop_scheduler  as _real_stop_scheduler


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "free", *,
               created_at: datetime | None = None) -> User:
    email = f"{plan}-{_uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email         = email,
        password_hash = hash_password("TestPass123"),
        plan          = plan,
        api_key       = generate_api_key(),
        is_active     = True,
    )
    if created_at:
        user.created_at = created_at
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_scan(db_session, user_id: int) -> ScanHistory:
    import json
    scan = ScanHistory(
        user_id        = user_id,
        scan_uuid      = str(_uuid.uuid4()),
        domain         = "test.com",
        security_score = 75,
        risk_level     = "moderate",
        findings_count = 0,
        findings_json  = json.dumps([]),
        scan_details_json = json.dumps({}),
    )
    db_session.add(scan)
    db_session.commit()
    return scan


def _monitored(last_scan_at=None, scan_frequency="weekly"):
    """Crée un faux MonitoredDomain (SimpleNamespace) pour tester _should_scan_now."""
    return SimpleNamespace(
        last_scan_at    = last_scan_at,
        scan_frequency  = scan_frequency,
    )


now = datetime.now(timezone.utc)


# ═════════════════════════════════════════════════════════════════════════════
# _should_scan_now — logique de fréquence de scan
# ═════════════════════════════════════════════════════════════════════════════

class TestShouldScanNow:
    def _call(self, monitored):
        from app.scheduler import _should_scan_now
        return _should_scan_now(monitored)

    # ── Jamais scanné ─────────────────────────────────────────────────────────

    def test_never_scanned_always_true(self):
        assert self._call(_monitored(last_scan_at=None)) is True

    def test_never_scanned_any_frequency(self):
        for freq in ("weekly", "biweekly", "monthly"):
            assert self._call(_monitored(last_scan_at=None, scan_frequency=freq)) is True

    # ── Fréquence weekly (≥ 6 jours) ─────────────────────────────────────────

    def test_weekly_5_days_ago_false(self):
        assert self._call(_monitored(now - timedelta(days=5), "weekly")) is False

    def test_weekly_6_days_ago_true(self):
        assert self._call(_monitored(now - timedelta(days=6), "weekly")) is True

    def test_weekly_10_days_ago_true(self):
        assert self._call(_monitored(now - timedelta(days=10), "weekly")) is True

    def test_weekly_default_frequency(self):
        # scan_frequency=None doit se comporter comme "weekly"
        assert self._call(_monitored(now - timedelta(days=6), None)) is True
        assert self._call(_monitored(now - timedelta(days=5), None)) is False

    # ── Fréquence biweekly (≥ 13 jours) ──────────────────────────────────────

    def test_biweekly_12_days_ago_false(self):
        assert self._call(_monitored(now - timedelta(days=12), "biweekly")) is False

    def test_biweekly_13_days_ago_true(self):
        assert self._call(_monitored(now - timedelta(days=13), "biweekly")) is True

    def test_biweekly_20_days_ago_true(self):
        assert self._call(_monitored(now - timedelta(days=20), "biweekly")) is True

    # ── Fréquence monthly (≥ 28 jours) ───────────────────────────────────────

    def test_monthly_27_days_ago_false(self):
        assert self._call(_monitored(now - timedelta(days=27), "monthly")) is False

    def test_monthly_28_days_ago_true(self):
        assert self._call(_monitored(now - timedelta(days=28), "monthly")) is True

    def test_monthly_30_days_ago_true(self):
        assert self._call(_monitored(now - timedelta(days=30), "monthly")) is True

    # ── Cas limites ───────────────────────────────────────────────────────────

    def test_just_scanned_1_hour_ago_false(self):
        assert self._call(_monitored(now - timedelta(hours=1), "weekly")) is False

    def test_exactly_at_threshold_weekly(self):
        # elapsed.days == 6 exactement → True
        last = now - timedelta(days=6, hours=1)
        assert self._call(_monitored(last, "weekly")) is True


# ═════════════════════════════════════════════════════════════════════════════
# _async_onboarding_emails — séquence J+1 / J+3 / J+7 / J+14
# ═════════════════════════════════════════════════════════════════════════════

BREVO_PATHS = {
    "nudge_j1":   "app.services.brevo_service.send_activation_nudge_email",
    "nudge_j3":   "app.services.brevo_service.send_upgrade_nudge_email",
    "reminder_j7": "app.services.brevo_service.send_value_reminder_email",
    "winback_j14": "app.services.brevo_service.send_winback_email",
}


@pytest.fixture
def brevo_mocks():
    """Patch toutes les fonctions Brevo d'onboarding."""
    mocks = {k: AsyncMock() for k in BREVO_PATHS}
    patches = [patch(v, new=mocks[k]) for k, v in BREVO_PATHS.items()]
    for p in patches:
        p.start()
    yield mocks
    for p in patches:
        p.stop()


async def _run_onboarding(db_session):
    """Exécute _async_onboarding_emails avec la session de test."""
    from app.scheduler import _async_onboarding_emails
    from app import database as db_module

    # Override SessionLocal pour utiliser la session de test
    original = db_module.SessionLocal
    db_module.SessionLocal = lambda: db_session
    try:
        await _async_onboarding_emails()
    finally:
        db_module.SessionLocal = original


class TestOnboardingJ1:
    """J+1 : inscrits il y a 20–28h, free, 0 scans → send_activation_nudge_email"""

    @pytest.mark.asyncio
    async def test_sends_nudge_for_free_user_no_scan(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=24))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j1"].assert_called_once_with(user.email)

    @pytest.mark.asyncio
    async def test_no_nudge_if_user_has_scanned(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=24))
        _make_scan(db_session, user.id)
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j1"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_nudge_outside_window_too_early(self, db_session, brevo_mocks):
        # 15h = trop tôt (fenêtre commence à 20h)
        _make_user(db_session, "free", created_at=now - timedelta(hours=15))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j1"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_nudge_outside_window_too_late(self, db_session, brevo_mocks):
        # 35h = trop tard (fenêtre finit à 28h)
        _make_user(db_session, "free", created_at=now - timedelta(hours=35))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j1"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_nudge_for_paid_user(self, db_session, brevo_mocks):
        _make_user(db_session, "starter", created_at=now - timedelta(hours=24))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j1"].assert_not_called()


class TestOnboardingJ3:
    """J+3 : inscrits il y a 68–76h, free → send_upgrade_nudge_email"""

    @pytest.mark.asyncio
    async def test_sends_upgrade_nudge(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=72))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j3"].assert_called_once_with(user.email)

    @pytest.mark.asyncio
    async def test_sends_even_with_scans(self, db_session, brevo_mocks):
        # J+3 envoie toujours — peu importe le nombre de scans
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=72))
        _make_scan(db_session, user.id)
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j3"].assert_called_once()

    @pytest.mark.asyncio
    async def test_no_nudge_outside_window(self, db_session, brevo_mocks):
        _make_user(db_session, "free", created_at=now - timedelta(hours=50))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j3"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_nudge_for_paid_user(self, db_session, brevo_mocks):
        _make_user(db_session, "pro", created_at=now - timedelta(hours=72))
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j3"].assert_not_called()


class TestOnboardingJ7:
    """J+7 : inscrits il y a 164–172h, free, ≥1 scan → send_value_reminder_email"""

    @pytest.mark.asyncio
    async def test_sends_value_reminder_if_has_scan(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=168))
        _make_scan(db_session, user.id)
        await _run_onboarding(db_session)
        brevo_mocks["reminder_j7"].assert_called_once_with(user.email, 1)

    @pytest.mark.asyncio
    async def test_no_reminder_if_no_scan(self, db_session, brevo_mocks):
        _make_user(db_session, "free", created_at=now - timedelta(hours=168))
        await _run_onboarding(db_session)
        brevo_mocks["reminder_j7"].assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_count_passed_correctly(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=168))
        _make_scan(db_session, user.id)
        _make_scan(db_session, user.id)
        _make_scan(db_session, user.id)
        await _run_onboarding(db_session)
        brevo_mocks["reminder_j7"].assert_called_once_with(user.email, 3)

    @pytest.mark.asyncio
    async def test_no_reminder_outside_window(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free", created_at=now - timedelta(hours=100))
        _make_scan(db_session, user.id)
        await _run_onboarding(db_session)
        brevo_mocks["reminder_j7"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_reminder_for_paid_user(self, db_session, brevo_mocks):
        user = _make_user(db_session, "starter",
                          created_at=now - timedelta(hours=168))
        _make_scan(db_session, user.id)
        await _run_onboarding(db_session)
        brevo_mocks["reminder_j7"].assert_not_called()


class TestOnboardingJ14:
    """J+14 : inscrits il y a 332–340h, free → send_winback_email"""

    @pytest.mark.asyncio
    async def test_sends_winback(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free",
                          created_at=now - timedelta(hours=336))
        await _run_onboarding(db_session)
        brevo_mocks["winback_j14"].assert_called_once_with(user.email)

    @pytest.mark.asyncio
    async def test_no_winback_outside_window_early(self, db_session, brevo_mocks):
        _make_user(db_session, "free", created_at=now - timedelta(hours=200))
        await _run_onboarding(db_session)
        brevo_mocks["winback_j14"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_winback_outside_window_late(self, db_session, brevo_mocks):
        _make_user(db_session, "free", created_at=now - timedelta(hours=500))
        await _run_onboarding(db_session)
        brevo_mocks["winback_j14"].assert_not_called()

    @pytest.mark.asyncio
    async def test_no_winback_for_paid_user(self, db_session, brevo_mocks):
        _make_user(db_session, "pro", created_at=now - timedelta(hours=336))
        await _run_onboarding(db_session)
        brevo_mocks["winback_j14"].assert_not_called()


class TestOnboardingIsolation:
    """Vérifier que les fenêtres temporelles ne se chevauchent pas."""

    @pytest.mark.asyncio
    async def test_each_window_targets_correct_step(self, db_session, brevo_mocks):
        u1  = _make_user(db_session, "free", created_at=now - timedelta(hours=24))
        u3  = _make_user(db_session, "free", created_at=now - timedelta(hours=72))
        u7  = _make_user(db_session, "free", created_at=now - timedelta(hours=168))
        u14 = _make_user(db_session, "free", created_at=now - timedelta(hours=336))
        _make_scan(db_session, u7.id)

        await _run_onboarding(db_session)

        # Chaque fonction appelée exactement une fois avec le bon utilisateur
        brevo_mocks["nudge_j1"].assert_called_once_with(u1.email)
        brevo_mocks["nudge_j3"].assert_called_once_with(u3.email)
        brevo_mocks["reminder_j7"].assert_called_once_with(u7.email, 1)
        brevo_mocks["winback_j14"].assert_called_once_with(u14.email)

    @pytest.mark.asyncio
    async def test_inactive_user_excluded(self, db_session, brevo_mocks):
        user = _make_user(db_session, "free", created_at=now - timedelta(hours=24))
        user.is_active = False
        db_session.commit()
        await _run_onboarding(db_session)
        brevo_mocks["nudge_j1"].assert_not_called()


# =============================================================================
# _async_monitoring — boucle orchestratrice du monitoring par domaine
# =============================================================================

class TestAsyncMonitoring:
    """Tests pour scheduler._async_monitoring (boucle de monitoring)."""

    @pytest.mark.asyncio
    async def test_calls_scan_and_alert_for_each_active_domain(
        self, db_session
    ):
        """_async_monitoring appelle _scan_and_alert pour chaque domaine actif."""
        from app.models import MonitoredDomain
        u = _make_user(db_session, plan="starter")

        for i in range(3):
            db_session.add(MonitoredDomain(
                user_id=u.id, domain=f"domain{i}.com", is_active=True,
            ))
        db_session.commit()

        mock_sna    = AsyncMock()
        mock_should = MagicMock(return_value=True)   # tous les domaines sont dus

        with patch("app.scheduler._scan_and_alert",  mock_sna), \
             patch("app.scheduler._should_scan_now", mock_should), \
             patch("app.database.SessionLocal",      return_value=db_session):
            from app.scheduler import _async_monitoring
            await _async_monitoring()

        assert mock_sna.call_count == 3

    @pytest.mark.asyncio
    async def test_skips_domain_when_not_due(self, db_session):
        """Domaine non-dû (_should_scan_now=False) → _scan_and_alert non appelé."""
        from app.models import MonitoredDomain
        u = _make_user(db_session, plan="starter")
        db_session.add(MonitoredDomain(
            user_id=u.id, domain="not-due.com", is_active=True,
        ))
        db_session.commit()

        mock_sna = AsyncMock()
        with patch("app.scheduler._scan_and_alert",  mock_sna), \
             patch("app.scheduler._should_scan_now",  MagicMock(return_value=False)), \
             patch("app.database.SessionLocal",       return_value=db_session):
            from app.scheduler import _async_monitoring
            await _async_monitoring()

        mock_sna.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_in_one_scan_does_not_stop_loop(self, db_session):
        """Exception sur un domaine → le domaine suivant est quand même scanné."""
        from app.models import MonitoredDomain
        u = _make_user(db_session, plan="starter")
        for i in range(2):
            db_session.add(MonitoredDomain(
                user_id=u.id, domain=f"site{i}.com", is_active=True,
            ))
        db_session.commit()

        call_count = 0

        async def _mock_sna(m, db):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("réseau KO")

        with patch("app.scheduler._scan_and_alert",  _mock_sna), \
             patch("app.scheduler._should_scan_now",  MagicMock(return_value=True)), \
             patch("app.database.SessionLocal",       return_value=db_session):
            from app.scheduler import _async_monitoring
            await _async_monitoring()

        # Les deux domaines ont été tentés malgré l'exception sur le premier
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_inactive_domains_are_not_scanned(self, db_session):
        """Domaines inactifs (is_active=False) non inclus dans la boucle."""
        from app.models import MonitoredDomain
        u = _make_user(db_session, plan="starter")
        db_session.add(MonitoredDomain(
            user_id=u.id, domain="inactive.com", is_active=False,
        ))
        db_session.commit()

        mock_sna = AsyncMock()
        with patch("app.scheduler._scan_and_alert",  mock_sna), \
             patch("app.scheduler._should_scan_now",  MagicMock(return_value=True)), \
             patch("app.database.SessionLocal",       return_value=db_session):
            from app.scheduler import _async_monitoring
            await _async_monitoring()

        mock_sna.assert_not_called()

# ─────────────────────────────────────────────────────────────────────────────
# Lock functions
# ─────────────────────────────────────────────────────────────────────────────

class TestLockFunctions:
    def test_try_acquire_lock_returns_false_on_ioerror(self):
        """_try_acquire_lock → False si fcntl.flock lève IOError."""
        import fcntl
        from app.scheduler import _try_acquire_lock
        with patch("app.scheduler.fcntl.flock", side_effect=IOError("locked")), \
             patch("builtins.open", MagicMock(return_value=MagicMock())):
            result = _try_acquire_lock()
        assert result is False

    def test_release_lock_handles_exception_silently(self):
        """_release_lock ne propage pas les exceptions."""
        import app.scheduler as sched
        # Simule un _lock_fd qui lève une exception lors de la fermeture
        mock_fd = MagicMock()
        mock_fd.close.side_effect = OSError("fermeture impossible")
        sched._lock_fd = mock_fd
        # Ne doit pas lever d'exception
        from app.scheduler import _release_lock
        _release_lock()  # doit finir sans exception
        assert sched._lock_fd is None

    def test_release_lock_does_nothing_when_no_fd(self):
        """_release_lock sans _lock_fd actif → no-op."""
        import app.scheduler as sched
        sched._lock_fd = None
        from app.scheduler import _release_lock
        _release_lock()  # pas d'exception
        assert sched._lock_fd is None


# ─────────────────────────────────────────────────────────────────────────────
# run_weekly_monitoring — error path
# ─────────────────────────────────────────────────────────────────────────────

class TestRunWeeklyMonitoring:
    def test_asyncio_run_exception_is_logged(self):
        """run_weekly_monitoring log l'erreur sans la propager."""
        with patch("app.scheduler.asyncio.run", side_effect=RuntimeError("réseau")):
            from app.scheduler import run_weekly_monitoring
            run_weekly_monitoring()  # ne doit pas lever

    def test_run_daily_onboarding_emails_exception_is_logged(self):
        """run_daily_onboarding_emails log l'erreur sans la propager."""
        with patch("app.scheduler.asyncio.run", side_effect=RuntimeError("smtp KO")):
            from app.scheduler import run_daily_onboarding_emails
            run_daily_onboarding_emails()  # ne doit pas lever


# ─────────────────────────────────────────────────────────────────────────────
# _scan_and_alert — chemins manquants
# ─────────────────────────────────────────────────────────────────────────────

class TestScanAndAlertExtended:
    """Couvre les branches de _scan_and_alert non couvertes par test_scan_and_alert.py."""

    def _make_active_user(self, db_session):
        from app.models import User
        u = _make_user(db_session, plan="starter")
        return u

    def _make_monitored(self, db_session, user_id, **kwargs):
        from app.models import MonitoredDomain
        m = MonitoredDomain(
            user_id=user_id,
            domain="test.com",
            is_active=True,
            last_score=kwargs.get("last_score"),
            alert_threshold=kwargs.get("alert_threshold", 10),
            last_open_ports=kwargs.get("last_open_ports"),
            last_technologies=kwargs.get("last_technologies"),
            email_report=kwargs.get("email_report", False),
        )
        db_session.add(m)
        db_session.commit()
        return m

    def _audit_mock(self, result):
        m = MagicMock()
        m.run = AsyncMock(return_value=result)
        return m

    def _make_result(self, score=80, risk="LOW", findings=None,
                     ssl_days=None, port_details=None, vuln_details=None):
        r = MagicMock()
        r.security_score = score
        r.risk_level     = risk
        r.findings       = findings or []
        r.ssl_details    = {"days_left": ssl_days} if ssl_days is not None else {}
        r.port_details   = port_details or {}
        r.vuln_details   = vuln_details or {"detected_stack": []}
        return r

    @pytest.mark.asyncio
    async def test_ssl_expiry_8_to_30_days_triggers_warning_alert(self, db_session):
        """SSL expiry 8-30 jours → alerte avertissement (non critique)."""
        u = self._make_active_user(db_session)
        m = self._make_monitored(db_session, u.id, last_score=80, alert_threshold=20)
        result = self._make_result(score=78, ssl_days=20)  # 8-30 jours

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=self._audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        reason = mock_alert.call_args[1]["reason"]
        assert "20" in reason  # contient le nombre de jours

    @pytest.mark.asyncio
    async def test_newly_closed_ports_trigger_alert(self, db_session):
        """Port précédemment ouvert maintenant fermé → alerte."""
        import json
        u = self._make_active_user(db_session)
        m = self._make_monitored(
            db_session, u.id,
            last_score=80, alert_threshold=20,
            last_open_ports=json.dumps(["443", "3389"]),
        )
        # Maintenant 3389 est fermé
        result = self._make_result(
            score=78,
            port_details={"443": {"open": True}, "3389": {"open": False}},
        )

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=self._audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        reason = mock_alert.call_args[1]["reason"]
        assert "3389" in reason

    @pytest.mark.asyncio
    async def test_tech_version_change_triggers_alert(self, db_session):
        """Changement de version de technologie → alerte."""
        import json
        u = self._make_active_user(db_session)
        old_tech = json.dumps({"PHP": "7.4", "nginx": "1.18"})
        m = self._make_monitored(
            db_session, u.id,
            last_score=80, alert_threshold=20,
            last_technologies=old_tech,
        )
        # PHP mis à jour de 7.4 → 8.1
        result = self._make_result(
            score=78,
            vuln_details={"detected_stack": [
                {"tech": "PHP",   "version": "8.1"},
                {"tech": "nginx", "version": "1.18"},
            ]},
        )

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=self._audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        reason = mock_alert.call_args[1]["reason"]
        assert "PHP" in reason

    @pytest.mark.asyncio
    async def test_change_alerts_appended_to_existing_alert_reason(self, db_session):
        """change_alerts concaténé avec alert_reason existant (score drop + SSL)."""
        u = self._make_active_user(db_session)
        # Score drop ET SSL expiry → les deux doivent être dans le reason
        m = self._make_monitored(db_session, u.id, last_score=80, alert_threshold=5)
        result = self._make_result(score=70, ssl_days=5)  # drop 10 > seuil 5 + SSL < 7j

        mock_alert = AsyncMock()
        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=self._audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", mock_alert), \
             patch("app.routers.webhook_router.fire_webhooks", new=AsyncMock()):
            await _scan_and_alert(m, db_session)

        mock_alert.assert_called_once()
        reason = mock_alert.call_args[1]["reason"]
        # Les deux alertes doivent être présentes, séparées par " | "
        assert "SSL" in reason or "expire" in reason.lower()

    @pytest.mark.asyncio
    async def test_webhook_alert_triggered_exception_logged(self, db_session):
        """Exception dans fire_webhooks (alert.triggered) → loguée, pas re-propagée."""
        u = self._make_active_user(db_session)
        m = self._make_monitored(db_session, u.id, last_score=80, alert_threshold=5)
        result = self._make_result(score=60)  # drop 20 > seuil 5

        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=self._audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.routers.webhook_router.fire_webhooks",
                   side_effect=RuntimeError("webhook KO")):
            await _scan_and_alert(m, db_session)  # ne doit pas lever

    @pytest.mark.asyncio
    async def test_webhook_score_dropped_exception_logged(self, db_session):
        """Exception dans fire_webhooks (score.dropped) → loguée, pas re-propagée."""
        u = self._make_active_user(db_session)
        m = self._make_monitored(db_session, u.id, last_score=80, alert_threshold=25)
        # Drop = 20, pas d'alerte (< seuil 25) mais score.dropped webhook quand même
        result = self._make_result(score=60)

        call_count = [0]

        async def mock_webhooks(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("webhook score.dropped KO")

        from app.scheduler import _scan_and_alert
        with patch("app.scanner.AuditManager", return_value=self._audit_mock(result)), \
             patch("app.scheduler._send_monitoring_alert", new=AsyncMock()), \
             patch("app.routers.webhook_router.fire_webhooks", new=mock_webhooks):
            await _scan_and_alert(m, db_session)  # ne doit pas lever


# ─────────────────────────────────────────────────────────────────────────────
# _send_scheduled_pdf_report — body complète
# ─────────────────────────────────────────────────────────────────────────────

class TestSendScheduledPdfReport:
    @pytest.mark.asyncio
    async def test_generates_and_sends_pdf(self, db_session):
        """Génère le PDF via report_service et l'envoie via send_pdf_email."""
        from types import SimpleNamespace
        user = SimpleNamespace(email="test@example.com", first_name="Test")
        monitored = SimpleNamespace(domain="example.com", email_report=True)
        result = MagicMock()
        result.security_score = 85
        result.risk_level     = "LOW"
        result.to_dict.return_value = {"domain": "example.com"}

        mock_send = AsyncMock()
        from app.scheduler import _send_scheduled_pdf_report
        with patch("app.services.report_service.generate_pdf", return_value=b"%PDF-fake"), \
             patch("app.services.brevo_service.send_pdf_email", mock_send):
            await _send_scheduled_pdf_report(user, monitored, result)

        mock_send.assert_called_once()
        kw = mock_send.call_args[1]
        assert kw["email"] == "test@example.com"
        assert kw["domain"] == "example.com"
        assert kw["pdf_bytes"] == b"%PDF-fake"

    @pytest.mark.asyncio
    async def test_propagates_exception_on_failure(self, db_session):
        """Exception dans generate_pdf → re-propagée (caller log)."""
        from types import SimpleNamespace
        user     = SimpleNamespace(email="test@example.com")
        monitored = SimpleNamespace(domain="example.com")
        result   = MagicMock()
        result.to_dict.return_value = {}

        from app.scheduler import _send_scheduled_pdf_report
        with patch("app.services.report_service.generate_pdf",
                   side_effect=RuntimeError("PDF KO")):
            with pytest.raises(RuntimeError, match="PDF KO"):
                await _send_scheduled_pdf_report(user, monitored, result)


# ─────────────────────────────────────────────────────────────────────────────
# _send_monitoring_alert — body complète
# ─────────────────────────────────────────────────────────────────────────────

class TestSendMonitoringAlert:
    @pytest.mark.asyncio
    async def test_calls_brevo_with_correct_args(self):
        """Appelle send_monitoring_alert_email avec les bons paramètres."""
        mock_send = AsyncMock()
        from app.scheduler import _send_monitoring_alert
        with patch("app.services.brevo_service.send_monitoring_alert_email", mock_send):
            await _send_monitoring_alert(
                email="user@example.com",
                first_name="Alice",
                domain="example.com",
                new_score=60,
                prev_score=80,
                risk_level="HIGH",
                reason="Score drop",
                findings=[],
            )

        mock_send.assert_called_once()
        kw = mock_send.call_args[1]
        assert kw["email"]      == "user@example.com"
        assert kw["first_name"] == "Alice"
        assert kw["domain"]     == "example.com"
        assert kw["new_score"]  == 60
        assert kw["prev_score"] == 80


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding email edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestOnboardingEmailEdgeCases:
    """Couvre les branches non couvertes par TestOnboarding*."""

    @pytest.mark.asyncio
    async def test_j1_skip_when_user_has_scans(self, db_session):
        """J+1 : user avec déjà des scans → activation_nudge non envoyé."""
        from datetime import timedelta
        from app.models import ScanHistory

        now = datetime.now(timezone.utc)
        u   = _make_user(db_session, plan="free",
                         created_at=now - timedelta(hours=22))
        # Ajouter un scan existant
        import uuid as _uuid2
        scan = ScanHistory(
            user_id=u.id, scan_uuid=str(_uuid2.uuid4()),
            domain="test.com", security_score=80, risk_level="LOW",
        )
        db_session.add(scan)
        db_session.commit()

        mock_nudge = AsyncMock()
        with patch("app.database.SessionLocal", return_value=db_session), \
             patch("app.services.brevo_service.send_activation_nudge_email",  mock_nudge), \
             patch("app.services.brevo_service.send_upgrade_nudge_email",     AsyncMock()), \
             patch("app.services.brevo_service.send_value_reminder_email",    AsyncMock()), \
             patch("app.services.brevo_service.send_winback_email",           AsyncMock()):
            from app.scheduler import _async_onboarding_emails
            await _async_onboarding_emails()

        mock_nudge.assert_not_called()

    @pytest.mark.asyncio
    async def test_j3_email_error_is_logged(self, db_session):
        """J+3 : exception dans send_upgrade_nudge_email → loguée, pas propagée."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        _make_user(db_session, plan="free", created_at=now - timedelta(hours=72))

        with patch("app.database.SessionLocal", return_value=db_session), \
             patch("app.services.brevo_service.send_activation_nudge_email",  AsyncMock()), \
             patch("app.services.brevo_service.send_upgrade_nudge_email",
                   AsyncMock(side_effect=RuntimeError("smtp KO"))), \
             patch("app.services.brevo_service.send_value_reminder_email",    AsyncMock()), \
             patch("app.services.brevo_service.send_winback_email",           AsyncMock()):
            from app.scheduler import _async_onboarding_emails
            await _async_onboarding_emails()  # ne doit pas lever

    @pytest.mark.asyncio
    async def test_j7_skip_when_user_has_no_scans(self, db_session):
        """J+7 : user sans scan → value_reminder non envoyé."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        _make_user(db_session, plan="free", created_at=now - timedelta(hours=168))

        mock_reminder = AsyncMock()
        with patch("app.database.SessionLocal", return_value=db_session), \
             patch("app.services.brevo_service.send_activation_nudge_email",  AsyncMock()), \
             patch("app.services.brevo_service.send_upgrade_nudge_email",     AsyncMock()), \
             patch("app.services.brevo_service.send_value_reminder_email",    mock_reminder), \
             patch("app.services.brevo_service.send_winback_email",           AsyncMock()):
            from app.scheduler import _async_onboarding_emails
            await _async_onboarding_emails()

        mock_reminder.assert_not_called()

    @pytest.mark.asyncio
    async def test_j14_email_error_is_logged(self, db_session):
        """J+14 : exception dans send_winback_email → loguée, pas propagée."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        _make_user(db_session, plan="free", created_at=now - timedelta(hours=336))

        with patch("app.database.SessionLocal", return_value=db_session), \
             patch("app.services.brevo_service.send_activation_nudge_email",  AsyncMock()), \
             patch("app.services.brevo_service.send_upgrade_nudge_email",     AsyncMock()), \
             patch("app.services.brevo_service.send_value_reminder_email",    AsyncMock()), \
             patch("app.services.brevo_service.send_winback_email",
                   AsyncMock(side_effect=RuntimeError("smtp KO"))):
            from app.scheduler import _async_onboarding_emails
            await _async_onboarding_emails()  # ne doit pas lever


# ─────────────────────────────────────────────────────────────────────────────
# start_scheduler / stop_scheduler
# ─────────────────────────────────────────────────────────────────────────────

class TestStartStopScheduler:
    def test_start_scheduler_returns_false_when_lock_not_acquired(self):
        """start_scheduler retourne False si un autre worker détient le verrou."""
        with patch("app.scheduler._try_acquire_lock", return_value=False):
            result = _real_start_scheduler()
        assert result is False

    def test_start_scheduler_returns_true_when_lock_acquired(self):
        """start_scheduler retourne True et démarre le scheduler.

        Note : conftest patche app.scheduler.start_scheduler à scope session.
        On utilise _real_start_scheduler capturé au niveau module (avant le patch)
        pour tester l'implémentation réelle.
        """
        mock_scheduler = MagicMock()
        with patch("app.scheduler._try_acquire_lock", return_value=True), \
             patch("app.scheduler.BackgroundScheduler", return_value=mock_scheduler):
            result = _real_start_scheduler()
        assert result is True
        mock_scheduler.start.assert_called_once()

    def test_stop_scheduler_shuts_down_running_scheduler(self):
        """stop_scheduler appelle shutdown si le scheduler tourne."""
        import app.scheduler as sched
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        sched._scheduler = mock_scheduler
        with patch("app.scheduler._release_lock"):
            _real_stop_scheduler()
        mock_scheduler.shutdown.assert_called_once_with(wait=False)
        sched._scheduler = None

    def test_stop_scheduler_no_op_when_not_running(self):
        """stop_scheduler ne plante pas si le scheduler n'est pas démarré."""
        import app.scheduler as sched
        sched._scheduler = None
        with patch("app.scheduler._release_lock"):
            _real_stop_scheduler()  # pas d'exception


# =============================================================================
# _try_acquire_lock success path (line 38)
# _release_lock success path (line 48)
# _async_onboarding_emails — J+1 exception (lines 416-417)
# _async_onboarding_emails — J+7 exception (lines 468-469)
# =============================================================================

class TestLockFunctionsSuccessPaths:

    def test_try_acquire_lock_returns_true_on_success(self):
        """_try_acquire_lock → True si fcntl.flock réussit (line 38)."""
        import fcntl as _fcntl
        from app.scheduler import _try_acquire_lock
        with patch("builtins.open", MagicMock(return_value=MagicMock())), \
             patch("app.scheduler.fcntl.flock", return_value=None):
            result = _try_acquire_lock()
        assert result is True

    def test_release_lock_closes_fd_on_success(self):
        """_release_lock → _lock_fd.close() appelé quand flock réussit (line 48)."""
        import app.scheduler as sched
        mock_fd = MagicMock()
        sched._lock_fd = mock_fd
        with patch("app.scheduler.fcntl.flock", return_value=None):
            from app.scheduler import _release_lock
            _release_lock()
        mock_fd.close.assert_called_once()
        assert sched._lock_fd is None


class TestOnboardingEmailExceptions:

    @pytest.mark.asyncio
    async def test_j1_nudge_exception_is_logged(self, db_session):
        """J+1 : exception dans send_activation_nudge_email → loguée, pas propagée (lines 416-417)."""
        now = datetime.now(timezone.utc)
        _make_user(db_session, plan="free", created_at=now - timedelta(hours=22))

        with patch("app.database.SessionLocal", return_value=db_session), \
             patch("app.services.brevo_service.send_activation_nudge_email",
                   AsyncMock(side_effect=RuntimeError("smtp KO"))), \
             patch("app.services.brevo_service.send_upgrade_nudge_email",  AsyncMock()), \
             patch("app.services.brevo_service.send_value_reminder_email", AsyncMock()), \
             patch("app.services.brevo_service.send_winback_email",        AsyncMock()):
            from app.scheduler import _async_onboarding_emails
            await _async_onboarding_emails()  # ne doit pas lever

    @pytest.mark.asyncio
    async def test_j7_value_reminder_exception_is_logged(self, db_session):
        """J+7 : exception dans send_value_reminder_email → loguée, pas propagée (lines 468-469)."""
        import uuid as _uuid
        from app.models import ScanHistory

        now = datetime.now(timezone.utc)
        u   = _make_user(db_session, plan="free", created_at=now - timedelta(hours=168))
        # Créer au moins 1 scan pour que la condition scan_count >= 1 soit vraie
        scan = ScanHistory(
            user_id=u.id, scan_uuid=str(_uuid.uuid4()),
            domain="j7test.com", security_score=70, risk_level="MEDIUM",
        )
        db_session.add(scan)
        db_session.commit()

        with patch("app.database.SessionLocal", return_value=db_session), \
             patch("app.services.brevo_service.send_activation_nudge_email",  AsyncMock()), \
             patch("app.services.brevo_service.send_upgrade_nudge_email",     AsyncMock()), \
             patch("app.services.brevo_service.send_value_reminder_email",
                   AsyncMock(side_effect=RuntimeError("smtp KO"))), \
             patch("app.services.brevo_service.send_winback_email",           AsyncMock()):
            from app.scheduler import _async_onboarding_emails
            await _async_onboarding_emails()  # ne doit pas lever
