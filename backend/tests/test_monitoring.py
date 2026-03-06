"""
Tests : monitoring — CRUD domaines surveillés
=============================================
Couvre :
  - GET  /monitoring/domains               → liste (premium uniquement)
  - POST /monitoring/domains               → ajout, doublons, limite plan, domaines invalides
  - DELETE /monitoring/domains/{d}         → suppression (soft delete)
  - PATCH /monitoring/domains/{d}          → mise à jour seuil, fréquence, email_report
  - POST /monitoring/domains/{d}/scan      → scan immédiat (mocké)
  - GET  /monitoring/status                → état du monitoring

Stratégie anti-rate-limit :
  - Les tokens JWT sont générés directement via create_access_token (pas de /auth/login)
  - Les utilisateurs sont créés en DB sans passer par /auth/register
  Cela évite de déclencher les limiteurs 10/hour (/register) ou 30/minute (/login).

Pour TestScanNow : _scan_and_alert est mocké via unittest.mock.patch pour éviter
tout appel réseau réel (le scanner ferait une vraie connexion au domaine cible).
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.models import MonitoredDomain


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str) -> dict:
    """Crée un utilisateur en DB avec le plan spécifié.
    Token généré directement via create_access_token — aucun appel HTTP,
    évite les rate limits de /auth/register et /auth/login.
    """
    import uuid
    from app.models import User
    from app.auth import hash_password, generate_api_key, create_access_token

    email = f"{plan}-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
        plan=plan,
        api_key=generate_api_key(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return {"email": email, "user": user, "token": token}


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Restriction plan gratuit — toutes les routes retournent 403
# ─────────────────────────────────────────────────────────────────────────────

class TestFreeUserBlocked:

    def test_list_domains_free_user_403(self, client, db_session):
        """Un utilisateur free ne peut pas lister les domaines surveillés."""
        creds = _make_user(db_session, "free")
        resp = client.get("/monitoring/domains", headers=_headers(creds["token"]))
        assert resp.status_code == 403

    def test_add_domain_free_user_403(self, client, db_session):
        """Un utilisateur free ne peut pas ajouter un domaine."""
        creds = _make_user(db_session, "free")
        resp = client.post(
            "/monitoring/domains",
            json={"domain": "example.com"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 403

    def test_delete_domain_free_user_403(self, client, db_session):
        """Un utilisateur free ne peut pas supprimer un domaine."""
        creds = _make_user(db_session, "free")
        resp = client.delete(
            "/monitoring/domains/example.com",
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 403

    def test_monitoring_status_free_user_403(self, client, db_session):
        """Un utilisateur free ne peut pas consulter le statut du monitoring."""
        creds = _make_user(db_session, "free")
        resp = client.get("/monitoring/status", headers=_headers(creds["token"]))
        assert resp.status_code == 403

    def test_unauthenticated_401(self, client):
        """Sans token, les routes monitoring retournent 401."""
        resp = client.get("/monitoring/domains")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /monitoring/domains — liste
# ─────────────────────────────────────────────────────────────────────────────

class TestListDomains:

    def test_list_empty_for_new_starter_user(self, client, db_session):
        """Starter sans domaine → liste vide."""
        creds = _make_user(db_session, "starter")
        resp = client.get("/monitoring/domains", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_added_domain(self, client, db_session):
        """Un domaine ajouté en DB apparaît dans la liste."""
        creds = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="wezea.net",
            alert_threshold=10,
            is_active=True,
        ))
        db_session.commit()

        resp = client.get("/monitoring/domains", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        domains = resp.json()
        assert len(domains) == 1
        assert domains[0]["domain"] == "wezea.net"
        assert domains[0]["alert_threshold"] == 10
        assert "scan_frequency" in domains[0]
        assert "email_report" in domains[0]

    def test_list_does_not_show_inactive_domains(self, client, db_session):
        """Les domaines inactifs (soft-deleted) n'apparaissent pas."""
        creds = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="inactive.example.com",
            is_active=False,
        ))
        db_session.commit()

        resp = client.get("/monitoring/domains", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_does_not_show_other_user_domains(self, client, db_session):
        """Un utilisateur ne voit que ses propres domaines."""
        user_a = _make_user(db_session, "starter")
        user_b = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=user_a["user"].id,
            domain="user-a-domain.com",
            is_active=True,
        ))
        db_session.commit()

        resp = client.get("/monitoring/domains", headers=_headers(user_b["token"]))
        assert resp.status_code == 200
        assert resp.json() == []


# ─────────────────────────────────────────────────────────────────────────────
# POST /monitoring/domains — ajout
# ─────────────────────────────────────────────────────────────────────────────

class TestAddDomain:

    def test_add_domain_success_starter(self, client, db_session):
        """Un starter peut ajouter 1 domaine avec succès."""
        creds = _make_user(db_session, "starter")

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "example.com"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "domain" in data
        assert data["domain"] == "example.com"

    def test_add_domain_normalizes_url(self, client, db_session):
        """Les URLs avec https:// et /path sont normalisées vers le FQDN."""
        creds = _make_user(db_session, "starter")

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "https://example.org/path"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 201
        assert resp.json()["domain"] == "example.org"

    def test_add_domain_with_custom_threshold(self, client, db_session):
        """On peut spécifier un seuil d'alerte personnalisé."""
        creds = _make_user(db_session, "starter")

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "threshold.example.com", "alert_threshold": 20},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 201

        domain = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.user_id == creds["user"].id,
            MonitoredDomain.domain == "threshold.example.com",
        ).first()
        assert domain is not None
        assert domain.alert_threshold == 20

    def test_add_domain_duplicate_returns_409(self, client, db_session):
        """Ajouter deux fois le même domaine actif retourne 409.
        Utilise un plan pro car le backend vérifie la limite avant le doublon :
        un starter avec déjà 1 domaine obtient 429 (limite atteinte) avant le 409.
        """
        creds = _make_user(db_session, "pro")

        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="duplicate.example.com",
            is_active=True,
        ))
        db_session.commit()

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "duplicate.example.com"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 409

    def test_add_domain_reactivates_inactive(self, client, db_session):
        """Ré-ajouter un domaine inactif le réactive sans 409."""
        creds = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="reactivate.example.com",
            is_active=False,
        ))
        db_session.commit()

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "reactivate.example.com"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 201

        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "reactivate.example.com",
            MonitoredDomain.user_id == creds["user"].id,
        ).first()
        assert d.is_active is True

    def test_add_domain_starter_limit_1(self, client, db_session):
        """Un starter ne peut pas dépasser 1 domaine (limite du plan)."""
        creds = _make_user(db_session, "starter")

        # Remplir la limite via DB
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="first.example.com",
            is_active=True,
        ))
        db_session.commit()

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "second.example.com"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 429  # limite atteinte

    def test_add_domain_pro_has_no_hard_limit(self, client, db_session):
        """Un pro peut ajouter plusieurs domaines (pas de limite fixe)."""
        creds = _make_user(db_session, "pro")

        for i in range(5):
            db_session.add(MonitoredDomain(
                user_id=creds["user"].id,
                domain=f"pro-domain-{i}.example.com",
                is_active=True,
            ))
        db_session.commit()

        resp = client.post(
            "/monitoring/domains",
            json={"domain": "pro-domain-6.example.com"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 201

    def test_add_localhost_blocked(self, client, db_session):
        """Les domaines SSRF (localhost, IP privées) sont bloqués."""
        creds = _make_user(db_session, "starter")

        for blocked in ["localhost", "127.0.0.1", "192.168.1.1", "169.254.169.254"]:
            resp = client.post(
                "/monitoring/domains",
                json={"domain": blocked},
                headers=_headers(creds["token"]),
            )
            assert resp.status_code in (422, 400), (
                f"Expected 422/400 for {blocked}, got {resp.status_code}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /monitoring/domains/{domain} — suppression
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteDomain:

    def test_delete_existing_domain(self, client, db_session):
        """Supprimer un domaine existant retourne 200 et le marque inactif (soft delete)."""
        creds = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="to-delete.example.com",
            is_active=True,
        ))
        db_session.commit()

        resp = client.delete(
            "/monitoring/domains/to-delete.example.com",
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200

        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "to-delete.example.com",
            MonitoredDomain.user_id == creds["user"].id,
        ).first()
        assert d is not None
        assert d.is_active is False

    def test_delete_nonexistent_domain_404(self, client, db_session):
        """Supprimer un domaine inexistant retourne 404."""
        creds = _make_user(db_session, "starter")

        resp = client.delete(
            "/monitoring/domains/ghost.example.com",
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 404

    def test_delete_other_user_domain_404(self, client, db_session):
        """Supprimer le domaine d'un autre utilisateur retourne 404 (pas 403,
        pour ne pas révéler l'existence du domaine à un tiers)."""
        user_a = _make_user(db_session, "starter")
        user_b = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=user_a["user"].id,
            domain="other-user-domain.com",
            is_active=True,
        ))
        db_session.commit()

        resp = client.delete(
            "/monitoring/domains/other-user-domain.com",
            headers=_headers(user_b["token"]),
        )
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /monitoring/domains/{domain} — mise à jour
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateDomain:

    def _add_domain(self, db_session, user_id: int, domain: str = "patch.example.com") -> None:
        db_session.add(MonitoredDomain(
            user_id=user_id,
            domain=domain,
            alert_threshold=10,
            is_active=True,
        ))
        db_session.commit()

    def test_patch_alert_threshold(self, client, db_session):
        """Mettre à jour le seuil d'alerte."""
        creds = _make_user(db_session, "starter")
        self._add_domain(db_session, creds["user"].id)

        resp = client.patch(
            "/monitoring/domains/patch.example.com",
            json={"alert_threshold": 25},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200

        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.user_id == creds["user"].id,
            MonitoredDomain.domain == "patch.example.com",
        ).first()
        assert d.alert_threshold == 25

    def test_patch_threshold_clamped_max(self, client, db_session):
        """Les valeurs de seuil supérieures à 50 sont bornées à 50."""
        creds = _make_user(db_session, "starter")
        self._add_domain(db_session, creds["user"].id, "clamp.example.com")

        client.patch(
            "/monitoring/domains/clamp.example.com",
            json={"alert_threshold": 999},
            headers=_headers(creds["token"]),
        )
        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "clamp.example.com",
        ).first()
        assert d.alert_threshold == 50

    def test_patch_scan_frequency_all_values(self, client, db_session):
        """Mettre à jour la fréquence de scan avec toutes les valeurs valides."""
        creds = _make_user(db_session, "starter")
        self._add_domain(db_session, creds["user"].id, "freq.example.com")

        for freq in ("biweekly", "monthly", "weekly"):
            resp = client.patch(
                "/monitoring/domains/freq.example.com",
                json={"scan_frequency": freq},
                headers=_headers(creds["token"]),
            )
            assert resp.status_code == 200

            db_session.expire_all()
            d = db_session.query(MonitoredDomain).filter(
                MonitoredDomain.domain == "freq.example.com"
            ).first()
            assert d.scan_frequency == freq

    def test_patch_invalid_scan_frequency_ignored(self, client, db_session):
        """Une fréquence invalide est ignorée silencieusement (valeur inchangée)."""
        creds = _make_user(db_session, "starter")
        self._add_domain(db_session, creds["user"].id, "invalid-freq.example.com")

        resp = client.patch(
            "/monitoring/domains/invalid-freq.example.com",
            json={"scan_frequency": "hourly"},  # valeur invalide
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200  # pas de crash

        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "invalid-freq.example.com",
        ).first()
        assert d.scan_frequency == "weekly"  # valeur par défaut inchangée

    def test_patch_email_report_toggle(self, client, db_session):
        """Activer puis désactiver le rapport email."""
        creds = _make_user(db_session, "starter")
        self._add_domain(db_session, creds["user"].id, "email.example.com")

        # Activer
        resp = client.patch(
            "/monitoring/domains/email.example.com",
            json={"email_report": True},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200
        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "email.example.com"
        ).first()
        assert d.email_report is True

        # Désactiver
        resp = client.patch(
            "/monitoring/domains/email.example.com",
            json={"email_report": False},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200
        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "email.example.com"
        ).first()
        assert d.email_report is False

    def test_patch_nonexistent_domain_404(self, client, db_session):
        """PATCH sur un domaine inexistant retourne 404."""
        creds = _make_user(db_session, "starter")

        resp = client.patch(
            "/monitoring/domains/ghost.example.com",
            json={"alert_threshold": 15},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 404

    def test_patch_other_user_domain_404(self, client, db_session):
        """PATCH sur le domaine d'un autre utilisateur retourne 404."""
        user_a = _make_user(db_session, "starter")
        user_b = _make_user(db_session, "starter")

        db_session.add(MonitoredDomain(
            user_id=user_a["user"].id,
            domain="owned-by-a.com",
            is_active=True,
        ))
        db_session.commit()

        resp = client.patch(
            "/monitoring/domains/owned-by-a.com",
            json={"alert_threshold": 30},
            headers=_headers(user_b["token"]),
        )
        assert resp.status_code == 404

    def test_patch_free_user_403(self, client, db_session):
        """Un utilisateur free ne peut pas faire de PATCH sur le monitoring."""
        creds = _make_user(db_session, "free")

        resp = client.patch(
            "/monitoring/domains/example.com",
            json={"alert_threshold": 15},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# GET /monitoring/status — état du monitoring
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitoringStatus:

    def test_status_starter_user(self, client, db_session):
        """Status pour un starter : limit=1, plan=starter."""
        creds = _make_user(db_session, "starter")

        resp = client.get("/monitoring/status", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "starter"
        assert data["domains_max"] == 1
        assert "domains_used" in data
        assert data["domains_used"] == 0

    def test_status_pro_user_no_limit(self, client, db_session):
        """Status pour un pro : domains_max est None (illimité)."""
        creds = _make_user(db_session, "pro")

        resp = client.get("/monitoring/status", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "pro"
        assert data["domains_max"] is None  # illimité

    def test_status_counts_active_domains_only(self, client, db_session):
        """domains_used ne compte que les domaines actifs (pas les inactifs)."""
        creds = _make_user(db_session, "pro")

        for i in range(3):
            db_session.add(MonitoredDomain(
                user_id=creds["user"].id,
                domain=f"active-{i}.example.com",
                is_active=True,
            ))
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="inactive.example.com",
            is_active=False,
        ))
        db_session.commit()

        resp = client.get("/monitoring/status", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        assert resp.json()["domains_used"] == 3  # seulement les actifs


# ─────────────────────────────────────────────────────────────────────────────
# POST /monitoring/domains/{domain}/scan — scan immédiat
# ─────────────────────────────────────────────────────────────────────────────

def _mock_scan_and_alert():
    """
    Mock de _scan_and_alert qui simule un scan réussi sans appel réseau.
    Met à jour last_score et last_scan_at sur le MonitoredDomain reçu.
    """
    from datetime import datetime, timezone

    async def _fake(monitored, db):
        monitored.last_score      = 82
        monitored.last_risk_level = "low"
        monitored.last_scan_at    = datetime.now(timezone.utc)
        monitored.last_ssl_expiry_days = 90
        monitored.last_open_ports      = '["443", "80"]'
        monitored.last_technologies    = '{"nginx": "1.24.0"}'
        db.commit()

    return _fake


class TestScanNow:

    def _setup(self, db_session, plan: str = "starter", domain: str = "scan-now.example.com"):
        """Crée l'utilisateur et le domaine surveillé nécessaires au test."""
        creds = _make_user(db_session, plan)
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain=domain,
            is_active=True,
        ))
        db_session.commit()
        return creds

    def test_scan_now_returns_200_with_new_score(self, client, db_session):
        """Scan immédiat réussi → retourne les nouvelles valeurs de score et de risque."""
        creds = self._setup(db_session)

        with patch("app.scheduler._scan_and_alert", new=_mock_scan_and_alert()):
            resp = client.post(
                "/monitoring/domains/scan-now.example.com/scan",
                headers=_headers(creds["token"]),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "scan-now.example.com"
        assert data["new_score"] == 82
        assert data["new_risk_level"] == "low"
        assert "scanned_at" in data
        assert data["last_ssl_expiry_days"] == 90

    def test_scan_now_updates_db(self, client, db_session):
        """Après un scan immédiat, les valeurs en DB sont bien mises à jour."""
        creds = self._setup(db_session, domain="db-update.example.com")

        with patch("app.scheduler._scan_and_alert", new=_mock_scan_and_alert()):
            resp = client.post(
                "/monitoring/domains/db-update.example.com/scan",
                headers=_headers(creds["token"]),
            )

        assert resp.status_code == 200

        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "db-update.example.com",
            MonitoredDomain.user_id == creds["user"].id,
        ).first()
        assert d.last_score == 82
        assert d.last_risk_level == "low"
        assert d.last_scan_at is not None

    def test_scan_now_nonexistent_domain_404(self, client, db_session):
        """Scan immédiat sur un domaine non surveillé → 404."""
        creds = _make_user(db_session, "starter")

        with patch("app.scheduler._scan_and_alert", new=_mock_scan_and_alert()):
            resp = client.post(
                "/monitoring/domains/ghost.example.com/scan",
                headers=_headers(creds["token"]),
            )

        assert resp.status_code == 404

    def test_scan_now_inactive_domain_404(self, client, db_session):
        """Scan immédiat sur un domaine inactif (soft-deleted) → 404."""
        creds = _make_user(db_session, "starter")
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="inactive-scan.example.com",
            is_active=False,
        ))
        db_session.commit()

        with patch("app.scheduler._scan_and_alert", new=_mock_scan_and_alert()):
            resp = client.post(
                "/monitoring/domains/inactive-scan.example.com/scan",
                headers=_headers(creds["token"]),
            )

        assert resp.status_code == 404

    def test_scan_now_other_user_domain_404(self, client, db_session):
        """Scan immédiat sur le domaine d'un autre utilisateur → 404."""
        user_a = _make_user(db_session, "starter")
        user_b = _make_user(db_session, "starter")
        db_session.add(MonitoredDomain(
            user_id=user_a["user"].id,
            domain="belongs-to-a.com",
            is_active=True,
        ))
        db_session.commit()

        with patch("app.scheduler._scan_and_alert", new=_mock_scan_and_alert()):
            resp = client.post(
                "/monitoring/domains/belongs-to-a.com/scan",
                headers=_headers(user_b["token"]),
            )

        assert resp.status_code == 404

    def test_scan_now_free_user_403(self, client, db_session):
        """Un utilisateur free ne peut pas déclencher de scan immédiat."""
        creds = _make_user(db_session, "free")

        with patch("app.scheduler._scan_and_alert", new=_mock_scan_and_alert()):
            resp = client.post(
                "/monitoring/domains/some-domain.com/scan",
                headers=_headers(creds["token"]),
            )

        assert resp.status_code == 403

    def test_scan_now_unauthenticated_401(self, client):
        """Sans token → 401."""
        resp = client.post("/monitoring/domains/example.com/scan")
        assert resp.status_code == 401


class TestDomainValidationEdgeCases:
    """Chemins de validation manquants dans monitoring_router.py."""

    def test_domain_too_long_returns_422(self, client, db_session):
        """Domaine > 253 caractères → 422."""
        creds = _make_user(db_session, "starter")
        long_domain = "a" * 254 + ".example.com"
        resp = client.post(
            "/monitoring/domains",
            json={"domain": long_domain},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 422
        assert "253" in resp.json()["detail"] or "long" in resp.json()["detail"].lower()

    def test_invalid_domain_regex_returns_422(self, client, db_session):
        """Domaine ne passant pas le regex (espaces, chars invalides) → 422."""
        creds = _make_user(db_session, "starter")
        resp = client.post(
            "/monitoring/domains",
            json={"domain": "not a valid domain!!"},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 422
        assert "valide" in resp.json()["detail"].lower() or \
               "valid" in resp.json()["detail"].lower()


class TestScanNowEdgeCases:
    """Chemins manquants dans POST /monitoring/domains/{domain}/scan."""

    def test_scan_now_exception_returns_500(self, client, db_session):
        """_scan_and_alert lève une exception → 500."""
        creds = _make_user(db_session, "starter")
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="crash-on-scan.com",
            is_active=True,
        ))
        db_session.commit()

        async def _failing_scan(m, db):
            raise RuntimeError("scan engine KO")

        with patch("app.scheduler._scan_and_alert", new=_failing_scan):
            resp = client.post(
                "/monitoring/domains/crash-on-scan.com/scan",
                headers=_headers(creds["token"]),
            )

        assert resp.status_code == 500


# =============================================================================
# Missing lines in monitoring_router.py:
#   149-150, 155-156 — _parse_json_list/_parse_json_dict exception in list_domains
#   301             — monitored.is_active = body.is_active
#   303             — monitored.checks_config = json.dumps(body.checks_config)
#   362-363, 368-369 — _parse_json_list/_parse_json_dict exception in scan_domain
# =============================================================================

class TestMonitoringMissingPaths:

    def _add_domain_raw(self, db_session, user_id: int, domain: str,
                        open_ports: str | None = None,
                        technologies: str | None = None) -> MonitoredDomain:
        d = MonitoredDomain(
            user_id=user_id,
            domain=domain,
            is_active=True,
        )
        db_session.add(d)
        db_session.commit()
        # Corrompre les colonnes JSON directement en DB
        if open_ports is not None:
            db_session.execute(
                __import__("sqlalchemy").text(
                    "UPDATE monitored_domains SET last_open_ports=:v WHERE domain=:d"
                ),
                {"v": open_ports, "d": domain},
            )
        if technologies is not None:
            db_session.execute(
                __import__("sqlalchemy").text(
                    "UPDATE monitored_domains SET last_technologies=:v WHERE domain=:d"
                ),
                {"v": technologies, "d": domain},
            )
        db_session.commit()
        return d

    def test_list_domains_invalid_json_open_ports_handled(self, client, db_session):
        """_parse_json_list sur open_ports invalide → None sans crash (lines 149-150)."""
        creds = _make_user(db_session, "starter")
        self._add_domain_raw(
            db_session, creds["user"].id, "bad-ports.example.com",
            open_ports="NOT_VALID_JSON",
        )
        resp = client.get("/monitoring/domains", headers=_headers(creds["token"]))
        assert resp.status_code == 200
        domains = resp.json()
        assert len(domains) >= 1
        # open_ports devrait être None (exception silencieuse)
        target = next((d for d in domains if d["domain"] == "bad-ports.example.com"), None)
        assert target is not None
        assert target.get("last_open_ports") is None

    def test_list_domains_invalid_json_technologies_handled(self, client, db_session):
        """_parse_json_dict sur technologies invalide → None sans crash (lines 155-156)."""
        creds = _make_user(db_session, "starter")
        self._add_domain_raw(
            db_session, creds["user"].id, "bad-tech.example.com",
            technologies="!!!NOT_JSON!!!",
        )
        resp = client.get("/monitoring/domains", headers=_headers(creds["token"]))
        assert resp.status_code == 200

    def test_patch_is_active_false(self, client, db_session):
        """PATCH is_active=False met à jour le champ (line 301)."""
        creds = _make_user(db_session, "starter")
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="active-toggle.example.com",
            is_active=True,
        ))
        db_session.commit()
        resp = client.patch(
            "/monitoring/domains/active-toggle.example.com",
            json={"is_active": False},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200
        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "active-toggle.example.com"
        ).first()
        assert d.is_active is False

    def test_patch_checks_config(self, client, db_session):
        """PATCH checks_config sérialise en JSON (line 303)."""
        creds = _make_user(db_session, "starter")
        db_session.add(MonitoredDomain(
            user_id=creds["user"].id,
            domain="config.example.com",
            is_active=True,
        ))
        db_session.commit()
        config = {"ssl": True, "ports": False}
        resp = client.patch(
            "/monitoring/domains/config.example.com",
            json={"checks_config": config},
            headers=_headers(creds["token"]),
        )
        assert resp.status_code == 200
        db_session.expire_all()
        d = db_session.query(MonitoredDomain).filter(
            MonitoredDomain.domain == "config.example.com"
        ).first()
        import json as _json
        assert _json.loads(d.checks_config) == config

    def test_scan_now_invalid_json_open_ports_handled(self, client, db_session):
        """_parse_json_list dans scan_domain avec JSON invalide → None (lines 362-363)."""
        creds = _make_user(db_session, "starter")
        d = self._add_domain_raw(
            db_session, creds["user"].id, "scan-bad-ports.example.com",
            open_ports="INVALID",
        )

        async def _fake_scan(monitored, db):
            monitored.last_open_ports = "INVALID"  # déjà corrompu
            monitored.last_score = 80
            monitored.last_risk_level = "LOW"

        with patch("app.scheduler._scan_and_alert", new=_fake_scan):
            resp = client.post(
                "/monitoring/domains/scan-bad-ports.example.com/scan",
                headers=_headers(creds["token"]),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("new_open_ports") is None

    def test_scan_now_invalid_json_technologies_handled(self, client, db_session):
        """_parse_json_dict dans scan_domain avec JSON invalide → None (lines 368-369)."""
        creds = _make_user(db_session, "starter")
        self._add_domain_raw(
            db_session, creds["user"].id, "scan-bad-tech.example.com",
            technologies="INVALID_JSON",
        )

        async def _fake_scan(monitored, db):
            monitored.last_technologies = "INVALID_JSON"
            monitored.last_score = 75
            monitored.last_risk_level = "MEDIUM"

        with patch("app.scheduler._scan_and_alert", new=_fake_scan):
            resp = client.post(
                "/monitoring/domains/scan-bad-tech.example.com/scan",
                headers=_headers(creds["token"]),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("new_technologies") is None
