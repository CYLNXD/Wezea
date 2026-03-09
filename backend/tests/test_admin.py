"""
Tests : admin_router — GET/PATCH/DELETE /admin/users + /admin/stats + /admin/metrics
--------------------------------------------------------------------------------------
Stratégie :
- Users créés directement en DB (_make_user) — zéro HTTP register/login
- Admin créé avec is_admin=True
- Tous les appels utilisent des JWT générés via create_access_token()
"""
import uuid as _uuid
from datetime import datetime, timezone

import pytest

from app.models import User, ScanHistory
from app.auth import hash_password, generate_api_key, create_access_token


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "free", *, is_admin: bool = False) -> dict:
    email = f"{plan}-{_uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
        plan=plan,
        api_key=generate_api_key(),
        is_active=True,
        is_admin=is_admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return {"email": email, "user": user, "token": token}


def _make_scan(db_session, user_id: int) -> ScanHistory:
    import json
    scan = ScanHistory(
        user_id=user_id,
        scan_uuid=str(_uuid.uuid4()),
        domain="test.com",
        security_score=75,
        risk_level="moderate",
        findings_count=1,
        findings_json=json.dumps([]),
        scan_details_json=json.dumps({}),
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    return scan


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Guard — non-admin ne peut pas accéder aux endpoints admin
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminGuard:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/admin/users")
        assert resp.status_code == 401

    def test_free_user_returns_403(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = client.get("/admin/users", headers=_auth(u["token"]))
        assert resp.status_code == 403

    def test_starter_user_returns_403(self, client, db_session):
        u = _make_user(db_session, "starter")
        resp = client.get("/admin/users", headers=_auth(u["token"]))
        assert resp.status_code == 403

    def test_pro_user_without_admin_flag_returns_403(self, client, db_session):
        u = _make_user(db_session, "pro", is_admin=False)
        resp = client.get("/admin/users", headers=_auth(u["token"]))
        assert resp.status_code == 403

    def test_admin_user_can_access(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/users", headers=_auth(admin["token"]))
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/users
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminListUsers:
    def test_returns_all_users(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        _make_user(db_session, "free")
        _make_user(db_session, "starter")
        resp = client.get("/admin/users", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        # Au moins admin + 2 nouveaux users
        assert len(data) >= 3

    def test_response_shape(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/users", headers=_auth(admin["token"]))
        u = resp.json()[0]
        assert "id" in u
        assert "email" in u
        assert "plan" in u
        assert "is_active" in u
        assert "is_admin" in u
        assert "scan_count" in u
        assert "created_at" in u

    def test_scan_count_is_correct(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "starter")
        _make_scan(db_session, target["user"].id)
        _make_scan(db_session, target["user"].id)

        resp = client.get("/admin/users", headers=_auth(admin["token"]))
        users = resp.json()
        found = next(u for u in users if u["email"] == target["email"])
        assert found["scan_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /admin/users/{user_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminUpdateUser:
    def test_change_plan_to_starter(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")
        resp = client.patch(
            f"/admin/users/{target['user'].id}",
            json={"plan": "starter"},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["plan"] == "starter"

    def test_change_plan_to_free_clears_subscription(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "starter")
        # Mettre un subscription_status actif
        target["user"].subscription_status = "active"
        db_session.commit()

        resp = client.patch(
            f"/admin/users/{target['user'].id}",
            json={"plan": "free"},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "free"

    def test_deactivate_user(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")
        resp = client.patch(
            f"/admin/users/{target['user'].id}",
            json={"is_active": False},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_reactivate_user(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")
        target["user"].is_active = False
        db_session.commit()
        resp = client.patch(
            f"/admin/users/{target['user'].id}",
            json={"is_active": True},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_invalid_plan_returns_400(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")
        resp = client.patch(
            f"/admin/users/{target['user'].id}",
            json={"plan": "enterprise"},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 400

    def test_admin_cannot_modify_self(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.patch(
            f"/admin/users/{admin['user'].id}",
            json={"plan": "free"},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 400

    def test_unknown_user_returns_404(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.patch(
            "/admin/users/999999",
            json={"plan": "pro"},
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 404

    def test_non_admin_returns_403(self, client, db_session):
        regular = _make_user(db_session, "free")
        target = _make_user(db_session, "free")
        resp = client.patch(
            f"/admin/users/{target['user'].id}",
            json={"plan": "pro"},
            headers=_auth(regular["token"]),
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /admin/users/{user_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminDeleteUser:
    def test_delete_user_returns_204(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")
        resp = client.delete(
            f"/admin/users/{target['user'].id}",
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 204

    def test_deleted_user_no_longer_in_list(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")
        client.delete(f"/admin/users/{target['user'].id}", headers=_auth(admin["token"]))
        resp = client.get("/admin/users", headers=_auth(admin["token"]))
        emails = [u["email"] for u in resp.json()]
        assert target["email"] not in emails

    def test_admin_cannot_delete_self(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.delete(
            f"/admin/users/{admin['user'].id}",
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 400

    def test_unknown_user_returns_404(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.delete("/admin/users/999999", headers=_auth(admin["token"]))
        assert resp.status_code == 404

    def test_non_admin_returns_403(self, client, db_session):
        regular = _make_user(db_session, "free")
        target = _make_user(db_session, "free")
        resp = client.delete(
            f"/admin/users/{target['user'].id}",
            headers=_auth(regular["token"]),
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminStats:
    def test_stats_shape(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/stats", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert "total_users" in data
        assert "active_users" in data
        assert "pro_users" in data
        assert "free_users" in data
        assert "total_scans" in data

    def test_stats_counts_are_consistent(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        _make_user(db_session, "free")
        _make_user(db_session, "starter")
        resp = client.get("/admin/stats", headers=_auth(admin["token"]))
        data = resp.json()
        assert data["total_users"] >= 3
        # free_users + pro_users == total_users
        assert data["free_users"] + data["pro_users"] == data["total_users"]

    def test_scan_count_in_stats(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        _make_scan(db_session, admin["user"].id)
        _make_scan(db_session, admin["user"].id)
        resp = client.get("/admin/stats", headers=_auth(admin["token"]))
        assert resp.json()["total_scans"] >= 2

    def test_non_admin_returns_403(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = client.get("/admin/stats", headers=_auth(u["token"]))
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminMetrics:
    def test_metrics_shape(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/metrics", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert "mrr_cents" in data
        assert "plan_breakdown" in data
        assert "revenue_30d_cents" in data
        assert "conversions_30d" in data
        assert "churns_30d" in data
        assert "new_signups_30d" in data
        assert "active_users_7d" in data
        assert "conversion_rate" in data
        assert "signups_last_30d" in data
        assert "scans_last_14d" in data

    def test_plan_breakdown_has_all_plans(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/metrics", headers=_auth(admin["token"]))
        pb = resp.json()["plan_breakdown"]
        assert "free" in pb
        assert "starter" in pb
        assert "pro" in pb

    def test_mrr_includes_active_subscriptions(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        # Créer un user starter avec subscription active
        paid = _make_user(db_session, "starter")
        paid["user"].subscription_status = "active"
        db_session.commit()

        resp = client.get("/admin/metrics", headers=_auth(admin["token"]))
        data = resp.json()
        # 1 starter actif → MRR >= 990 centimes
        assert data["mrr_cents"] >= 990

    def test_conversion_rate_is_percentage(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/metrics", headers=_auth(admin["token"]))
        rate = resp.json()["conversion_rate"]
        assert 0 <= rate <= 100

    def test_signups_last_30d_is_list(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/metrics", headers=_auth(admin["token"]))
        signups = resp.json()["signups_last_30d"]
        assert isinstance(signups, list)
        # Chaque entrée doit avoir date + count
        for entry in signups:
            assert "date" in entry
            assert "count" in entry

    def test_scans_last_14d_is_list(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True)
        _make_scan(db_session, admin["user"].id)
        resp = client.get("/admin/metrics", headers=_auth(admin["token"]))
        scans = resp.json()["scans_last_14d"]
        assert isinstance(scans, list)
        assert len(scans) >= 1

    def test_non_admin_returns_403(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = client.get("/admin/metrics", headers=_auth(u["token"]))
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# GET/DELETE /admin/purge-scans
# ─────────────────────────────────────────────────────────────────────────────

class TestPurgeScans:
    """Tests pour la purge RGPD des scans anciens."""

    def test_dry_run_no_old_scans(self, client, db_session):
        """Dry-run sans scans anciens → scans_to_delete=0."""
        admin = _make_user(db_session, "pro", is_admin=True)
        _make_scan(db_session, admin["user"].id)  # scan récent
        resp = client.get("/admin/purge-scans", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["scans_to_delete"] == 0

    def test_dry_run_with_old_scans(self, client, db_session):
        """Dry-run avec des scans anciens → scans_to_delete > 0."""
        from datetime import timedelta
        admin = _make_user(db_session, "pro", is_admin=True)
        # Créer un scan avec une date ancienne
        scan = _make_scan(db_session, admin["user"].id)
        scan.created_at = datetime.now(timezone.utc) - timedelta(days=100)
        db_session.commit()

        resp = client.get("/admin/purge-scans?retention_days=90", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["scans_to_delete"] >= 1
        assert data["retention_days"] == 90
        assert data["dry_run"] is True

    def test_execute_purge_deletes_old_scans(self, client, db_session):
        """DELETE /admin/purge-scans supprime les scans anciens et retourne le count."""
        from datetime import timedelta
        from unittest.mock import patch
        admin = _make_user(db_session, "pro", is_admin=True)

        # Créer 2 scans anciens + 1 scan récent
        scan1 = _make_scan(db_session, admin["user"].id)
        scan2 = _make_scan(db_session, admin["user"].id)
        recent_scan = _make_scan(db_session, admin["user"].id)
        scan1.created_at = datetime.now(timezone.utc) - timedelta(days=95)
        scan2.created_at = datetime.now(timezone.utc) - timedelta(days=91)
        # recent_scan garde created_at=now
        db_session.commit()

        resp = client.delete("/admin/purge-scans?retention_days=90", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is False
        assert data["scans_deleted"] >= 2
        assert data["retention_days"] == 90

        # Le scan récent doit encore exister
        from app.models import ScanHistory
        still_exists = db_session.query(ScanHistory).filter(ScanHistory.id == recent_scan.id).first()
        assert still_exists is not None

    def test_execute_purge_non_admin_forbidden(self, client, db_session):
        """DELETE /admin/purge-scans → 403 pour non-admin."""
        u = _make_user(db_session, "pro")
        resp = client.delete("/admin/purge-scans", headers=_auth(u["token"]))
        assert resp.status_code == 403

    def test_dry_run_custom_retention(self, client, db_session):
        """dry-run avec retention_days=30 → cutoff correct."""
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.get("/admin/purge-scans?retention_days=30", headers=_auth(admin["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["retention_days"] == 30
        assert "cutoff" in data


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/users/{user_id}/reset-2fa
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminReset2FA:

    def _make_user_with_2fa(self, db_session) -> dict:
        """Crée un user avec 2FA activée."""
        import pyotp
        info = _make_user(db_session, "free")
        info["user"].mfa_enabled = True
        info["user"].mfa_secret = pyotp.random_base32()
        db_session.commit()
        db_session.refresh(info["user"])
        return info

    def test_admin_reset_2fa_success(self, client, db_session):
        """Admin peut réinitialiser la 2FA d'un user → 200, mfa_enabled=False en DB."""
        admin = _make_user(db_session, "pro", is_admin=True)
        target = self._make_user_with_2fa(db_session)
        assert target["user"].mfa_enabled is True

        resp = client.post(
            f"/admin/users/{target['user'].id}/reset-2fa",
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        db_session.refresh(target["user"])
        assert target["user"].mfa_enabled is False
        assert target["user"].mfa_secret is None

    def test_admin_reset_2fa_user_not_found(self, client, db_session):
        """User inexistant → 404."""
        admin = _make_user(db_session, "pro", is_admin=True)
        resp = client.post("/admin/users/999999/reset-2fa", headers=_auth(admin["token"]))
        assert resp.status_code == 404

    def test_admin_reset_2fa_not_enabled(self, client, db_session):
        """2FA non activée sur ce compte → 400."""
        admin = _make_user(db_session, "pro", is_admin=True)
        target = _make_user(db_session, "free")  # mfa_enabled=False par défaut
        resp = client.post(
            f"/admin/users/{target['user'].id}/reset-2fa",
            headers=_auth(admin["token"]),
        )
        assert resp.status_code == 400

    def test_non_admin_reset_2fa_forbidden(self, client, db_session):
        """Non-admin ne peut pas réinitialiser la 2FA → 403."""
        regular = _make_user(db_session, "pro")
        target = self._make_user_with_2fa(db_session)
        resp = client.post(
            f"/admin/users/{target['user'].id}/reset-2fa",
            headers=_auth(regular["token"]),
        )
        assert resp.status_code == 403
