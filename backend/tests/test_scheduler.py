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
from unittest.mock import AsyncMock, patch

import pytest

from app.models import User, ScanHistory
from app.auth import hash_password, generate_api_key


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
