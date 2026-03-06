"""
Tests : contact_router + newsletter_router
------------------------------------------
contact_router :
  GET  /contact/subjects
  POST /contact  (validation Pydantic + sauvegarde DB + brevo mocké)

newsletter_router :
  POST /newsletter/subscribe  (nouveau, déjà confirmé, ré-abonnement, renvoi token)
  GET  /newsletter/confirm/{token}  (valid, invalide, expiré, déjà confirmé)
  POST /newsletter/unsubscribe  (existant, inconnu → toujours 200)

Tous les appels Brevo sont mockés — aucun email réel n'est envoyé.
"""
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models import ContactMessage, NewsletterSubscription


# ─────────────────────────────────────────────────────────────────────────────
# Patch global Brevo — appliqué à tous les tests du module
# ─────────────────────────────────────────────────────────────────────────────

BREVO_PATCHES = [
    "app.services.brevo_service.send_contact_notification",
    "app.services.brevo_service.send_contact_confirmation",
    "app.services.brevo_service.send_newsletter_confirmation_email",
    "app.services.brevo_service.add_newsletter_contact",
    "app.services.brevo_service.send_newsletter_welcome_email",
    "app.services.brevo_service.remove_newsletter_contact",
]


@pytest.fixture(autouse=True)
def mock_brevo():
    """Neutralise tous les appels Brevo pour chaque test."""
    patches = [patch(p, new=AsyncMock()) for p in BREVO_PATCHES]
    mocks = [p.start() for p in patches]
    yield mocks
    for p in patches:
        p.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_subscription(db_session, email: str, *,
                        confirmed: bool = False,
                        unsubscribed: bool = False,
                        token: str | None = None) -> NewsletterSubscription:
    sub = NewsletterSubscription(
        email        = email,
        token        = token or secrets.token_urlsafe(32),
        confirmed    = confirmed,
        confirmed_at = datetime.now(timezone.utc) if confirmed else None,
        unsubscribed = unsubscribed,
        ip_address   = "127.0.0.1",
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


VALID_CONTACT = {
    "name":    "Alice Martin",
    "email":   "alice@example.com",
    "subject": "Problème technique",
    "message": "Bonjour, j'ai un problème avec mon compte.",
}


# ═════════════════════════════════════════════════════════════════════════════
# Contact Router
# ═════════════════════════════════════════════════════════════════════════════

class TestContactSubjects:
    def test_returns_subjects_list(self, client, db_session):
        resp = client.get("/contact/subjects")
        assert resp.status_code == 200
        data = resp.json()
        assert "subjects" in data
        assert isinstance(data["subjects"], list)
        assert len(data["subjects"]) >= 1

    def test_subjects_no_auth_required(self, client, db_session):
        resp = client.get("/contact/subjects")
        assert resp.status_code == 200

    def test_subjects_includes_expected_values(self, client, db_session):
        resp = client.get("/contact/subjects")
        subjects = resp.json()["subjects"]
        assert "Problème technique" in subjects
        assert "Question sur mon compte" in subjects


class TestContactSubmit:
    def test_valid_contact_returns_201(self, client, db_session):
        resp = client.post("/contact", json=VALID_CONTACT)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "received"
        assert "id" in data

    def test_contact_saved_in_db(self, client, db_session):
        client.post("/contact", json=VALID_CONTACT)
        msg = db_session.query(ContactMessage).filter_by(
            email=VALID_CONTACT["email"]
        ).first()
        assert msg is not None
        assert msg.name    == VALID_CONTACT["name"]
        assert msg.subject == VALID_CONTACT["subject"]
        assert msg.message == VALID_CONTACT["message"]

    def test_name_too_short_returns_422(self, client, db_session):
        bad = {**VALID_CONTACT, "name": "A"}
        resp = client.post("/contact", json=bad)
        assert resp.status_code == 422

    def test_invalid_email_returns_422(self, client, db_session):
        bad = {**VALID_CONTACT, "email": "not-an-email"}
        resp = client.post("/contact", json=bad)
        assert resp.status_code == 422

    def test_message_too_short_returns_422(self, client, db_session):
        bad = {**VALID_CONTACT, "message": "court"}
        resp = client.post("/contact", json=bad)
        assert resp.status_code == 422

    def test_message_too_long_returns_422(self, client, db_session):
        bad = {**VALID_CONTACT, "message": "x" * 5001}
        resp = client.post("/contact", json=bad)
        assert resp.status_code == 422

    def test_invalid_subject_returns_422(self, client, db_session):
        bad = {**VALID_CONTACT, "subject": "Sujet inexistant"}
        resp = client.post("/contact", json=bad)
        assert resp.status_code == 422

    def test_contact_works_without_auth(self, client, db_session):
        # Pas de header Authorization → doit fonctionner (user_id=None en DB)
        resp = client.post("/contact", json=VALID_CONTACT)
        assert resp.status_code == 201

    def test_all_subjects_are_valid_pydantic(self, client, db_session):
        # Valider via Pydantic directement — évite d'épuiser le rate limit HTTP (5/hour)
        # Les 422 de validation précédents comptent aussi contre le compteur SlowAPI
        from app.routers.contact_router import ContactRequest, SUBJECTS
        for subject in SUBJECTS:
            req = ContactRequest(
                name="Test User",
                email="test@example.com",
                subject=subject,
                message="Message de test valide.",
            )
            assert req.subject == subject, f"Subject '{subject}' should be accepted by Pydantic"


# ═════════════════════════════════════════════════════════════════════════════
# Newsletter Router
# ═════════════════════════════════════════════════════════════════════════════

class TestNewsletterSubscribe:
    def test_new_email_returns_202_pending(self, client, db_session):
        resp = client.post("/newsletter/subscribe", json={"email": "new@example.com"})
        assert resp.status_code == 202
        assert resp.json()["status"] == "pending"

    def test_new_subscription_saved_in_db(self, client, db_session):
        client.post("/newsletter/subscribe", json={"email": "save@example.com"})
        sub = db_session.query(NewsletterSubscription).filter_by(
            email="save@example.com"
        ).first()
        assert sub is not None
        assert sub.confirmed is False
        assert sub.token is not None

    def test_already_confirmed_returns_202_silently(self, client, db_session):
        # Déjà abonné et confirmé — pas de doublon, retour discret
        _make_subscription(db_session, "confirmed@example.com", confirmed=True)
        resp = client.post("/newsletter/subscribe", json={"email": "confirmed@example.com"})
        assert resp.status_code == 202
        assert resp.json()["status"] == "pending"

    def test_pending_subscribe_resends_token(self, client, db_session):
        # Déjà en attente → renvoi du token existant (pas de doublon)
        _make_subscription(db_session, "pending@example.com", confirmed=False)
        resp = client.post("/newsletter/subscribe", json={"email": "pending@example.com"})
        assert resp.status_code == 202
        # Un seul enregistrement en DB
        count = db_session.query(NewsletterSubscription).filter_by(
            email="pending@example.com"
        ).count()
        assert count == 1

    def test_unsubscribed_can_resubscribe(self, client, db_session):
        _make_subscription(db_session, "resub@example.com", unsubscribed=True)
        resp = client.post("/newsletter/subscribe", json={"email": "resub@example.com"})
        assert resp.status_code == 202
        # L'enregistrement doit être réactivé
        sub = db_session.query(NewsletterSubscription).filter_by(
            email="resub@example.com"
        ).first()
        assert sub.unsubscribed is False
        assert sub.confirmed is False

    def test_invalid_email_returns_422(self, client, db_session):
        resp = client.post("/newsletter/subscribe", json={"email": "pas-un-email"})
        assert resp.status_code == 422


class TestNewsletterConfirm:
    def test_valid_token_confirms_subscription(self, client, db_session):
        token = secrets.token_urlsafe(32)
        _make_subscription(db_session, "confirm@example.com", token=token)
        resp = client.get(f"/newsletter/confirm/{token}", follow_redirects=False)
        # Redirection 302 vers le frontend
        assert resp.status_code == 302
        assert "newsletter_confirmed=1" in resp.headers["location"]

    def test_confirmed_flag_set_in_db(self, client, db_session):
        token = secrets.token_urlsafe(32)
        _make_subscription(db_session, "flag@example.com", token=token)
        client.get(f"/newsletter/confirm/{token}", follow_redirects=False)
        db_session.expire_all()
        sub = db_session.query(NewsletterSubscription).filter_by(
            email="flag@example.com"
        ).first()
        assert sub.confirmed is True
        assert sub.confirmed_at is not None
        # Le token doit être invalidé après confirmation
        assert sub.token is None

    def test_unknown_token_returns_404(self, client, db_session):
        resp = client.get(f"/newsletter/confirm/{secrets.token_urlsafe(32)}")
        assert resp.status_code == 404

    def test_expired_token_returns_410(self, client, db_session):
        token = secrets.token_urlsafe(32)
        sub = _make_subscription(db_session, "expired@example.com", token=token)
        # Simuler un token créé il y a 49h (> 48h)
        sub.created_at = datetime.now(timezone.utc) - timedelta(hours=49)
        db_session.commit()
        resp = client.get(f"/newsletter/confirm/{token}")
        assert resp.status_code == 410

    def test_already_confirmed_token_redirects_ok(self, client, db_session):
        # Double clic sur le lien de confirmation → redirige quand même (idempotent)
        token = secrets.token_urlsafe(32)
        _make_subscription(db_session, "double@example.com",
                            confirmed=True, token=token)
        resp = client.get(f"/newsletter/confirm/{token}", follow_redirects=False)
        assert resp.status_code == 302


class TestNewsletterUnsubscribe:
    def test_unsubscribe_known_email_returns_200(self, client, db_session):
        _make_subscription(db_session, "bye@example.com", confirmed=True)
        resp = client.post("/newsletter/unsubscribe", json={"email": "bye@example.com"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "unsubscribed"

    def test_unsubscribed_flag_set_in_db(self, client, db_session):
        _make_subscription(db_session, "flag-unsub@example.com", confirmed=True)
        client.post("/newsletter/unsubscribe", json={"email": "flag-unsub@example.com"})
        db_session.expire_all()
        sub = db_session.query(NewsletterSubscription).filter_by(
            email="flag-unsub@example.com"
        ).first()
        assert sub.unsubscribed is True

    def test_unsubscribe_unknown_email_still_returns_200(self, client, db_session):
        # Anti-énumération : 200 même si l'email n'existe pas
        resp = client.post("/newsletter/unsubscribe",
                           json={"email": "ghost@example.com"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "unsubscribed"

    def test_double_unsubscribe_is_idempotent(self, client, db_session):
        _make_subscription(db_session, "idempotent@example.com", confirmed=True)
        client.post("/newsletter/unsubscribe", json={"email": "idempotent@example.com"})
        resp = client.post("/newsletter/unsubscribe",
                           json={"email": "idempotent@example.com"})
        assert resp.status_code == 200


# =============================================================================
# contact_router.py line 81 — GET /contact redirect
# newsletter_router.py line 48 — _get_client_ip X-Forwarded-For
# =============================================================================

class TestContactRedirect:
    """GET /contact → RedirectResponse vers le frontend (line 81)."""

    def test_get_contact_redirects(self, client, db_session):
        """GET /contact retourne une redirection 302."""
        resp = client.get("/contact", follow_redirects=False)
        assert resp.status_code == 302
        assert "contact" in resp.headers["location"]


class TestNewsletterClientIp:
    """_get_ip : couvre line 48 (X-Forwarded-For) en appelant la fonction directement (pas d'HTTP)."""

    def test_get_ip_with_x_forwarded_for(self):
        """X-Forwarded-For header → premier IP extrait (line 48 newsletter_router)."""
        from app.routers.newsletter_router import _get_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {"X-Forwarded-For": "192.0.2.1, 10.0.0.1"}
        request.client = None

        ip = _get_ip(request)
        assert ip == "192.0.2.1"

    def test_get_ip_without_forwarded_for_uses_client_host(self):
        """Sans X-Forwarded-For → request.client.host (line 49)."""
        from app.routers.newsletter_router import _get_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}
        request.client.host = "10.0.0.5"

        ip = _get_ip(request)
        assert ip == "10.0.0.5"

    def test_get_ip_no_client_returns_unknown(self):
        """Sans X-Forwarded-For et client None → 'unknown' (line 49)."""
        from app.routers.newsletter_router import _get_ip
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}
        request.client = None

        ip = _get_ip(request)
        assert ip == "unknown"
