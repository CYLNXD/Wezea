"""
Tests : payment_router
-----------------------
GET  /payment/status           — statut abonnement
POST /payment/create-checkout  — création session Stripe
POST /payment/webhook          — événements Stripe (checkout, invoice, subscription)
POST /payment/cancel           — annulation abonnement

Stratégie :
- Stripe API mockée via unittest.mock (pas d'appels réels)
- stripe.Webhook.construct_event mocké pour injecter des événements arbitraires
- _user_from_subscription + _plan_from_subscription mockés pour les events subscription
"""
import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe as _stripe

from app.models import User, Payment
from app.auth import hash_password, generate_api_key, create_access_token


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "free", *,
               is_admin: bool = False,
               subscription_status: str | None = None,
               stripe_customer_id: str | None = None) -> dict:
    email = f"{plan}-{_uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email         = email,
        password_hash = hash_password("TestPass123"),
        plan          = plan,
        api_key       = generate_api_key(),
        is_active     = True,
        is_admin      = is_admin,
    )
    if subscription_status:
        user.subscription_status = subscription_status
    if stripe_customer_id:
        user.stripe_customer_id = stripe_customer_id
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return {"email": email, "user": user, "token": token}


def _make_payment(db_session, user_id: int, *,
                  status: str = "completed",
                  stripe_session_id: str | None = None) -> Payment:
    payment = Payment(
        user_id           = user_id,
        stripe_session_id = stripe_session_id or f"cs_test_{_uuid.uuid4().hex[:12]}",
        amount            = 990,
        currency          = "EUR",
        status            = status,
    )
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)
    return payment


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fake_event(event_type: str, data: dict) -> dict:
    """Construit un faux événement Stripe pour patch de construct_event."""
    return {
        "type": event_type,
        "id":   f"evt_{_uuid.uuid4().hex[:16]}",
        "data": {"object": data},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fixture globale — neutralise send_upgrade_email
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _mock_upgrade_email():
    """Neutralise send_upgrade_email pour tous les tests de ce module."""
    with patch("app.routers.payment_router.send_upgrade_email", new=AsyncMock()):
        yield


# ═════════════════════════════════════════════════════════════════════════════
# GET /payment/status
# ═════════════════════════════════════════════════════════════════════════════

class TestPaymentStatus:
    def test_free_user_status(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = client.get("/payment/status", headers=_auth(u["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"]          == "free"
        assert data["is_active"]     is False
        assert data["price_monthly"] == 0.0
        assert data["currency"]      == "EUR"

    def test_starter_active_status(self, client, db_session):
        u = _make_user(db_session, "starter", subscription_status="active")
        resp = client.get("/payment/status", headers=_auth(u["token"]))
        data = resp.json()
        assert data["plan"]          == "starter"
        assert data["is_active"]     is True
        assert data["price_monthly"] == 9.90

    def test_pro_active_status(self, client, db_session):
        u = _make_user(db_session, "pro", subscription_status="active")
        data = client.get("/payment/status", headers=_auth(u["token"])).json()
        assert data["plan"]          == "pro"
        assert data["is_active"]     is True
        assert data["price_monthly"] == 19.90

    def test_cancelling_is_not_active(self, client, db_session):
        """subscription_status=cancelling → is_active doit être False."""
        u = _make_user(db_session, "pro", subscription_status="cancelling")
        data = client.get("/payment/status", headers=_auth(u["token"])).json()
        assert data["subscription_status"] == "cancelling"
        assert data["is_active"]           is False

    def test_response_shape(self, client, db_session):
        u = _make_user(db_session, "free")
        data = client.get("/payment/status", headers=_auth(u["token"])).json()
        for key in ("plan", "subscription_status", "subscription_expires_at",
                    "is_active", "price_monthly", "currency"):
            assert key in data

    def test_unauthenticated_returns_401(self, client, db_session):
        assert client.get("/payment/status").status_code == 401


# ═════════════════════════════════════════════════════════════════════════════
# POST /payment/create-checkout
# ═════════════════════════════════════════════════════════════════════════════

class TestCreateCheckout:
    def _mock_session(self, url="https://checkout.stripe.com/pay/cs_test_x", sid="cs_test_x"):
        m = MagicMock()
        m.id  = sid
        m.url = url
        return m

    def test_no_stripe_key_returns_503(self, client, db_session):
        u = _make_user(db_session, "free")
        with patch("stripe.api_key", ""):
            resp = client.post("/payment/create-checkout",
                               json={"plan": "starter"}, headers=_auth(u["token"]))
        assert resp.status_code == 503

    def test_already_subscribed_same_plan_returns_400(self, client, db_session):
        u = _make_user(db_session, "starter", subscription_status="active")
        with patch("stripe.api_key", "sk_test_xxx"):
            resp = client.post("/payment/create-checkout",
                               json={"plan": "starter"}, headers=_auth(u["token"]))
        assert resp.status_code == 400

    def test_pro_cannot_buy_starter_returns_400(self, client, db_session):
        u = _make_user(db_session, "pro", subscription_status="active")
        with patch("stripe.api_key", "sk_test_xxx"):
            resp = client.post("/payment/create-checkout",
                               json={"plan": "starter"}, headers=_auth(u["token"]))
        assert resp.status_code == 400

    def test_returns_checkout_url_and_session_id(self, client, db_session):
        u   = _make_user(db_session, "free")
        sid = f"cs_test_{_uuid.uuid4().hex[:8]}"
        with patch("stripe.api_key", "sk_test_xxx"), \
             patch("stripe.checkout.Session.create",
                   return_value=self._mock_session(sid=sid)):
            resp = client.post("/payment/create-checkout",
                               json={"plan": "starter"}, headers=_auth(u["token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert "checkout_url" in data
        assert data["session_id"] == sid

    def test_creates_payment_record_in_db(self, client, db_session):
        u   = _make_user(db_session, "free")
        sid = f"cs_test_{_uuid.uuid4().hex[:8]}"
        with patch("stripe.api_key", "sk_test_xxx"), \
             patch("stripe.checkout.Session.create",
                   return_value=self._mock_session(sid=sid)):
            client.post("/payment/create-checkout",
                        json={"plan": "starter"}, headers=_auth(u["token"]))
        p = db_session.query(Payment).filter_by(stripe_session_id=sid).first()
        assert p is not None
        assert p.status == "pending"
        assert p.amount == 990   # 9,90 € en centimes

    def test_plan_amounts_are_correct(self):
        """Vérifie les montants sans appel HTTP (éviter le rate limit 5/hour)."""
        from app.routers.payment_router import _PLAN_AMOUNTS
        assert _PLAN_AMOUNTS["starter"] == 990   # 9,90 €
        assert _PLAN_AMOUNTS["pro"]     == 1990  # 19,90 €

    def test_stripe_error_handler_exists(self):
        """Vérifie que le handler 502 est bien en place (analyse de code, pas HTTP)."""
        import inspect
        from app.routers import payment_router
        src = inspect.getsource(payment_router.create_checkout)
        assert "502" in src or "StripeError" in src

    def test_unauthenticated_returns_401(self, client, db_session):
        assert client.post("/payment/create-checkout",
                           json={"plan": "starter"}).status_code == 401


# ═════════════════════════════════════════════════════════════════════════════
# POST /payment/webhook — sécurité
# ═════════════════════════════════════════════════════════════════════════════

class TestWebhookGuard:
    def test_no_webhook_secret_returns_503(self, client, db_session):
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", ""):
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=x"})
        assert resp.status_code == 503

    def test_invalid_signature_returns_400(self, client, db_session):
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("stripe.Webhook.construct_event",
                   side_effect=_stripe.SignatureVerificationError("bad sig", "t=1")):
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=bad"})
        assert resp.status_code == 400


# ═════════════════════════════════════════════════════════════════════════════
# POST /payment/webhook — checkout.session.completed
# ═════════════════════════════════════════════════════════════════════════════

class TestWebhookCheckoutCompleted:
    def _post(self, client, event_type: str, data: dict):
        event = _fake_event(event_type, data)
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("stripe.Webhook.construct_event", return_value=event):
            return client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=ok"})

    def test_upgrades_user_plan(self, client, db_session):
        u = _make_user(db_session, "free")
        self._post(client, "checkout.session.completed", {
            "id":       "cs_upgrade",
            "customer": "cus_x",
            "metadata": {"user_id": str(u["user"].id), "plan": "starter"},
        })
        db_session.refresh(u["user"])
        assert u["user"].plan                == "starter"
        assert u["user"].subscription_status == "active"

    def test_saves_stripe_customer_id(self, client, db_session):
        u   = _make_user(db_session, "free")
        cid = f"cus_{_uuid.uuid4().hex[:8]}"
        self._post(client, "checkout.session.completed", {
            "id": "cs_cid", "customer": cid,
            "metadata": {"user_id": str(u["user"].id), "plan": "starter"},
        })
        db_session.refresh(u["user"])
        assert u["user"].stripe_customer_id == cid

    def test_marks_pending_payment_as_completed(self, client, db_session):
        u   = _make_user(db_session, "free")
        sid = f"cs_test_{_uuid.uuid4().hex[:8]}"
        pay = _make_payment(db_session, u["user"].id,
                            status="pending", stripe_session_id=sid)
        self._post(client, "checkout.session.completed", {
            "id": sid, "customer": "cus_x",
            "metadata": {"user_id": str(u["user"].id), "plan": "starter"},
        })
        db_session.refresh(pay)
        assert pay.status  == "completed"
        assert pay.paid_at is not None

    def test_admin_plan_unchanged_by_stripe(self, client, db_session):
        """Sécurité clé : Stripe ne doit JAMAIS modifier le plan d'un admin."""
        admin = _make_user(db_session, "pro", is_admin=True)
        self._post(client, "checkout.session.completed", {
            "id":       "cs_admin",
            "customer": "cus_admin",
            "metadata": {"user_id": str(admin["user"].id), "plan": "starter"},
        })
        db_session.refresh(admin["user"])
        assert admin["user"].plan == "pro"   # inchangé

    def test_unknown_user_no_crash_returns_ok(self, client, db_session):
        resp = self._post(client, "checkout.session.completed", {
            "id": "cs_ghost", "customer": "cus_ghost",
            "metadata": {"user_id": "9999999", "plan": "starter"},
        })
        assert resp.status_code       == 200
        assert resp.json()["status"]  == "ok"

    def test_returns_ok_status(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = self._post(client, "checkout.session.completed", {
            "id": "cs_ok", "customer": "cus_ok",
            "metadata": {"user_id": str(u["user"].id), "plan": "starter"},
        })
        assert resp.json()["status"] == "ok"


# ═════════════════════════════════════════════════════════════════════════════
# POST /payment/webhook — événements invoice.* + customer.subscription.*
# ═════════════════════════════════════════════════════════════════════════════

class TestWebhookSubscriptionEvents:
    """
    _user_from_subscription et _plan_from_subscription sont mockés
    pour éviter les appels Stripe réels.
    """

    def _post(self, client, event_type: str, data: dict,
              mock_user=None, mock_plan: str = "starter"):
        event = _fake_event(event_type, data)
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("stripe.Webhook.construct_event", return_value=event), \
             patch("app.routers.payment_router._user_from_subscription",
                   return_value=mock_user), \
             patch("app.routers.payment_router._plan_from_subscription",
                   return_value=mock_plan):
            return client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=ok"})

    def test_invoice_succeeded_activates_plan(self, client, db_session):
        u = _make_user(db_session, "free")
        self._post(client, "invoice.payment_succeeded",
                   {"subscription": "sub_1"}, mock_user=u["user"], mock_plan="starter")
        db_session.refresh(u["user"])
        assert u["user"].plan                == "starter"
        assert u["user"].subscription_status == "active"

    def test_invoice_failed_downgrades_to_free(self, client, db_session):
        u = _make_user(db_session, "starter", subscription_status="active")
        self._post(client, "invoice.payment_failed",
                   {"subscription": "sub_2"}, mock_user=u["user"])
        db_session.refresh(u["user"])
        assert u["user"].plan                == "free"
        assert u["user"].subscription_status == "cancelled"

    def test_subscription_deleted_downgrades(self, client, db_session):
        u = _make_user(db_session, "pro", subscription_status="active")
        self._post(client, "customer.subscription.deleted",
                   {"id": "sub_3"}, mock_user=u["user"])
        db_session.refresh(u["user"])
        assert u["user"].plan == "free"

    def test_subscription_updated_active_ensures_plan(self, client, db_session):
        u = _make_user(db_session, "free")
        self._post(client, "customer.subscription.updated",
                   {"id": "sub_4", "status": "active"},
                   mock_user=u["user"], mock_plan="pro")
        db_session.refresh(u["user"])
        assert u["user"].plan == "pro"

    def test_subscription_updated_trialing_ensures_plan(self, client, db_session):
        u = _make_user(db_session, "free")
        self._post(client, "customer.subscription.updated",
                   {"id": "sub_5", "status": "trialing"},
                   mock_user=u["user"], mock_plan="starter")
        db_session.refresh(u["user"])
        assert u["user"].plan == "starter"

    def test_subscription_updated_canceled_downgrades(self, client, db_session):
        u = _make_user(db_session, "pro", subscription_status="active")
        self._post(client, "customer.subscription.updated",
                   {"id": "sub_6", "status": "canceled"},
                   mock_user=u["user"])
        db_session.refresh(u["user"])
        assert u["user"].plan == "free"

    def test_admin_not_downgraded_by_subscription_deleted(self, client, db_session):
        admin = _make_user(db_session, "pro", is_admin=True, subscription_status="active")
        self._post(client, "customer.subscription.deleted",
                   {"id": "sub_admin"}, mock_user=admin["user"])
        db_session.refresh(admin["user"])
        assert admin["user"].plan == "pro"   # inchangé

    def test_unknown_event_type_returns_ok(self, client, db_session):
        resp = self._post(client, "payment_intent.succeeded", {"id": "pi_x"})
        assert resp.status_code      == 200
        assert resp.json()["status"] == "ok"


# ═════════════════════════════════════════════════════════════════════════════
# POST /payment/cancel
# ═════════════════════════════════════════════════════════════════════════════

class TestCancelSubscription:
    def test_free_user_cannot_cancel_returns_400(self, client, db_session):
        u = _make_user(db_session, "free")
        assert client.post("/payment/cancel",
                           headers=_auth(u["token"])).status_code == 400

    def test_sets_status_to_cancelling(self, client, db_session):
        u = _make_user(db_session, "starter", subscription_status="active")
        with patch("stripe.Subscription.list", return_value=MagicMock(data=[])):
            resp = client.post("/payment/cancel", headers=_auth(u["token"]))
        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].subscription_status == "cancelling"

    def test_calls_stripe_modify_cancel_at_period_end(self, client, db_session):
        u = _make_user(db_session, "pro", subscription_status="active",
                       stripe_customer_id="cus_mod_test")
        mock_sub = MagicMock()
        mock_sub.id = "sub_mod_123"
        with patch("stripe.Subscription.list",
                   return_value=MagicMock(data=[mock_sub])), \
             patch("stripe.Subscription.modify") as mock_modify:
            client.post("/payment/cancel", headers=_auth(u["token"]))
        mock_modify.assert_called_once_with("sub_mod_123", cancel_at_period_end=True)

    def test_already_cancelling_is_accepted(self, client, db_session):
        """Idempotent : annuler un abonnement déjà en cours d'annulation → 200."""
        u = _make_user(db_session, "pro", subscription_status="cancelling")
        with patch("stripe.Subscription.list", return_value=MagicMock(data=[])):
            resp = client.post("/payment/cancel", headers=_auth(u["token"]))
        assert resp.status_code == 200

    def test_response_shape(self, client, db_session):
        u = _make_user(db_session, "starter", subscription_status="active")
        with patch("stripe.Subscription.list", return_value=MagicMock(data=[])):
            data = client.post("/payment/cancel",
                               headers=_auth(u["token"])).json()
        assert data["status"]  == "cancelling"
        assert "message" in data

    def test_unauthenticated_returns_401(self, client, db_session):
        assert client.post("/payment/cancel").status_code == 401
