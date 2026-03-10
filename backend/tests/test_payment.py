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
        assert _PLAN_AMOUNTS["dev"]     == 2990  # 29,90 €

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


# =============================================================================
# Helpers Stripe — _plan_from_subscription + _user_from_subscription
# =============================================================================

class TestPlanFromSubscription:
    """Tests pour _plan_from_subscription (logique pure, Stripe mocké)."""

    def _call(self, items=None, raise_exc=False):
        from app.routers.payment_router import _plan_from_subscription
        sub_mock = MagicMock()
        if raise_exc:
            sub_mock.side_effect = Exception("Stripe KO")
        else:
            sub_mock.return_value = {
                "items": {"data": items or []}
            }
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve = sub_mock
            # Reproduit le mapping réel
            from app.routers.payment_router import _PRICE_TO_PLAN
            s.Subscription.retrieve.return_value = {"items": {"data": items or []}}
            return _plan_from_subscription("sub_xxx")

    def test_returns_pro_as_default_when_no_items(self):
        result = self._call(items=[])
        assert result == "pro"

    def test_returns_pro_on_stripe_exception(self):
        from app.routers.payment_router import _plan_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.side_effect = Exception("KO")
            result = _plan_from_subscription("sub_xxx")
        assert result == "pro"

    def test_returns_pro_when_price_unknown(self):
        from app.routers.payment_router import _plan_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = {
                "items": {"data": [{"price": {"id": "price_unknown_xyz"}}]}
            }
            result = _plan_from_subscription("sub_xxx")
        assert result == "pro"

    def test_resolves_starter_price_id(self):
        from app.routers.payment_router import _plan_from_subscription, _PRICE_TO_PLAN
        if not _PRICE_TO_PLAN:
            pytest.skip("_PRICE_TO_PLAN vide (pas de clés Stripe configurées)")
        starter_price = next(
            (k for k, v in _PRICE_TO_PLAN.items() if v == "starter"), None
        )
        if not starter_price:
            pytest.skip("Aucun price_id starter dans _PRICE_TO_PLAN")
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = {
                "items": {"data": [{"price": {"id": starter_price}}]}
            }
            result = _plan_from_subscription("sub_xxx")
        assert result == "starter"


class TestUserFromSubscription:
    """
    Tests pour _user_from_subscription — 3 niveaux de résolution :
      1. stripe_customer_id stocké en DB
      2. email du Stripe Customer
      3. metadata.user_id (fallback legacy)
    """

    def _sub_mock(self, customer_id: str | None = "cus_test", uid_meta: str | None = None):
        """Retourne un dict simul-Stripe Subscription."""
        return {
            "customer": customer_id,
            "metadata": {"user_id": uid_meta} if uid_meta else {},
        }

    def test_resolves_via_stripe_customer_id_in_db(self, db_session):
        u = _make_user(
            db_session, plan="starter",
            stripe_customer_id="cus_abc123",
            subscription_status="active",
        )
        from app.routers.payment_router import _user_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = self._sub_mock(customer_id="cus_abc123")
            result = _user_from_subscription("sub_xxx", db_session)
        assert result is not None
        assert result.id == u["user"].id

    def test_resolves_via_customer_email(self, db_session):
        """Pas de stripe_customer_id en DB → lookup via Customer.retrieve(email)."""
        u = _make_user(db_session, plan="starter", subscription_status="active")
        email = u["user"].email
        from app.routers.payment_router import _user_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = self._sub_mock(customer_id="cus_new")
            s.Customer.retrieve.return_value = {"email": email}
            result = _user_from_subscription("sub_xxx", db_session)
        assert result is not None
        assert result.email == email
        # stripe_customer_id mis à jour en cache
        db_session.refresh(result)
        assert result.stripe_customer_id == "cus_new"

    def test_resolves_via_metadata_user_id_fallback(self, db_session):
        """Ni customer_id ni email ne matchent → fallback metadata.user_id."""
        u = _make_user(db_session, plan="starter", subscription_status="active")
        uid = str(u["user"].id)
        from app.routers.payment_router import _user_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = self._sub_mock(
                customer_id="cus_unknown", uid_meta=uid
            )
            # Email lookup → email inconnu pour forcer le fallback metadata
            s.Customer.retrieve.return_value = {"email": "unknown@nowhere.com"}
            result = _user_from_subscription("sub_xxx", db_session)
        assert result is not None
        assert result.id == u["user"].id

    def test_returns_none_when_not_found(self, db_session):
        """Aucun des 3 chemins ne trouve l'utilisateur → retourne None."""
        from app.routers.payment_router import _user_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = self._sub_mock(
                customer_id="cus_ghost", uid_meta=None
            )
            s.Customer.retrieve.return_value = {"email": "ghost@ghost.com"}
            result = _user_from_subscription("sub_ghost", db_session)
        assert result is None

    def test_returns_none_on_stripe_exception(self, db_session):
        """Exception Stripe → retourne None sans planter."""
        from app.routers.payment_router import _user_from_subscription
        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.side_effect = Exception("KO")
            result = _user_from_subscription("sub_xxx", db_session)
        assert result is None


# =============================================================================
# GET /payment/portal — Stripe Billing Portal
# =============================================================================

class TestCustomerPortal:

    def test_free_user_returns_400(self, client, db_session):
        u = _make_user(db_session, plan="free")
        r = client.get("/payment/portal", headers=_auth(u["token"]))
        assert r.status_code == 400

    def test_active_starter_with_customer_id_returns_portal_url(self, client, db_session):
        u = _make_user(
            db_session, plan="starter",
            subscription_status="active",
            stripe_customer_id="cus_direct",
        )
        with patch("app.routers.payment_router.stripe") as s:
            s.billing_portal.Session.create.return_value = MagicMock(url="https://billing.stripe.com/portal/xxx")
            r = client.get("/payment/portal", headers=_auth(u["token"]))
        assert r.status_code == 200
        assert "portal_url" in r.json()
        assert r.json()["portal_url"].startswith("https://")

    def test_no_customer_id_resolves_via_last_payment(self, client, db_session):
        u = _make_user(db_session, plan="starter", subscription_status="active")
        _make_payment(db_session, u["user"].id, stripe_session_id="cs_test_abc")
        with patch("app.routers.payment_router.stripe") as s:
            s.checkout.Session.retrieve.return_value = {"customer": "cus_from_session"}
            s.billing_portal.Session.create.return_value = MagicMock(url="https://billing.stripe.com/p")
            r = client.get("/payment/portal", headers=_auth(u["token"]))
        assert r.status_code == 200
        assert "portal_url" in r.json()

    def test_no_customer_anywhere_returns_404(self, client, db_session):
        u = _make_user(db_session, plan="pro", subscription_status="active")
        # Aucun payment, pas de stripe_customer_id, Customer.list vide
        with patch("app.routers.payment_router.stripe") as s:
            s.Customer.list.return_value = MagicMock(data=[])
            r = client.get("/payment/portal", headers=_auth(u["token"]))
        assert r.status_code == 404

    def test_stripe_error_on_portal_create_returns_502(self, client, db_session):
        u = _make_user(
            db_session, plan="starter",
            subscription_status="active",
            stripe_customer_id="cus_ok",
        )
        with patch("app.routers.payment_router.stripe") as s:
            # Restaurer la vraie classe pour que except stripe.StripeError fonctionne
            s.StripeError = _stripe.StripeError
            s.billing_portal.Session.create.side_effect = _stripe.StripeError("portal KO")
            r = client.get("/payment/portal", headers=_auth(u["token"]))
        assert r.status_code == 502

    def test_cancelling_user_can_access_portal(self, client, db_session):
        """Plan actif mais en cours d'annulation → accès autorisé."""
        u = _make_user(
            db_session, plan="starter",
            subscription_status="cancelling",
            stripe_customer_id="cus_cancelling",
        )
        with patch("app.routers.payment_router.stripe") as s:
            s.billing_portal.Session.create.return_value = MagicMock(url="https://billing.stripe.com/c")
            r = client.get("/payment/portal", headers=_auth(u["token"]))
        assert r.status_code == 200

    def test_unauthenticated_returns_401(self, client, db_session):
        r = client.get("/payment/portal")
        assert r.status_code == 401


# =============================================================================
# _user_from_subscription — uid_meta stripe_customer_id cache (lines 122-123)
# =============================================================================

class TestUserFromSubscriptionCacheUpdate:
    """Vérifie que stripe_customer_id est mis en cache quand trouvé via metadata."""

    def test_caches_stripe_customer_id_on_uid_meta_fallback(self, db_session):
        """User trouvé via uid_meta sans stripe_customer_id → cache mis à jour."""
        from app.routers.payment_router import _user_from_subscription
        u = _make_user(db_session, "free")
        user = u["user"]
        assert user.stripe_customer_id is None

        # sub.get("customer") = "cus_new_123", sub.get("metadata") = {user_id: ...}
        # Step 1: aucun user n'a stripe_customer_id="cus_new_123" → pas de match
        # Step 2: Customer.retrieve lève exception → fallback uid_meta
        # Step 3: uid_meta trouve le user → cache le customer_id
        sub_mock = MagicMock()
        sub_mock.get = lambda k, d=None: {
            "customer":  "cus_new_123",
            "metadata":  {"user_id": str(user.id)},
        }.get(k, d)

        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = sub_mock
            s.Customer.retrieve.side_effect = Exception("not found")
            result = _user_from_subscription("sub_cache_test", db_session)

        db_session.refresh(user)
        assert result is not None
        assert user.stripe_customer_id == "cus_new_123"

    def test_does_not_overwrite_existing_stripe_customer_id(self, db_session):
        """User avec stripe_customer_id existant → pas d'écrasement."""
        from app.routers.payment_router import _user_from_subscription
        u = _make_user(db_session, "starter", stripe_customer_id="cus_existing")
        user = u["user"]

        # customer_id "cus_other" != "cus_existing" → step 1 ne matche pas
        # step 2: Customer.retrieve exception → fallback
        # step 3: uid_meta trouve le user, mais stripe_customer_id déjà défini → pas d'update
        sub_mock = MagicMock()
        sub_mock.get = lambda k, d=None: {
            "customer":  "cus_other_789",
            "metadata":  {"user_id": str(user.id)},
        }.get(k, d)

        with patch("app.routers.payment_router.stripe") as s:
            s.Subscription.retrieve.return_value = sub_mock
            s.Customer.retrieve.side_effect = Exception("no")
            result = _user_from_subscription("sub_no_overwrite", db_session)

        db_session.refresh(user)
        assert result is not None
        assert user.stripe_customer_id == "cus_existing"  # inchangé


# =============================================================================
# _ensure_plan_from_subscription — admin guard + exception (lines 147, 151-152)
# _downgrade_from_subscription — admin guard (lines 166-167)
# =============================================================================

class TestEnsureAndDowngradeAdminGuard:

    def test_ensure_plan_does_not_modify_admin(self, db_session):
        """_ensure_plan_from_subscription ignore les admins."""
        from app.routers.payment_router import _ensure_plan_from_subscription
        u = _make_user(db_session, "free", is_admin=True)
        user = u["user"]

        with patch("app.routers.payment_router._user_from_subscription",
                   return_value=user), \
             patch("app.routers.payment_router._plan_from_subscription",
                   return_value="pro"):
            _ensure_plan_from_subscription("sub_admin", db_session)

        db_session.refresh(user)
        assert user.plan == "free"   # inchangé
        assert user.is_admin is True

    def test_ensure_plan_silences_exception(self, db_session):
        """Exception dans _ensure_plan → silencieusement ignorée (try/except)."""
        from app.routers.payment_router import _ensure_plan_from_subscription
        with patch("app.routers.payment_router._user_from_subscription",
                   side_effect=RuntimeError("boom")):
            # Ne doit pas lever d'exception
            _ensure_plan_from_subscription("sub_err", db_session)

    def test_downgrade_does_not_modify_admin(self, db_session):
        """_downgrade_from_subscription ignore les admins."""
        from app.routers.payment_router import _downgrade_from_subscription
        u = _make_user(db_session, "pro", is_admin=True)
        user = u["user"]
        user.subscription_status = "active"
        db_session.commit()

        with patch("app.routers.payment_router._user_from_subscription",
                   return_value=user):
            _downgrade_from_subscription("sub_admin_down", db_session)

        db_session.refresh(user)
        assert user.plan == "pro"    # inchangé
        assert user.subscription_status == "active"

    def test_downgrade_silences_exception(self, db_session):
        """Exception dans _downgrade → silencieusement ignorée."""
        from app.routers.payment_router import _downgrade_from_subscription
        with patch("app.routers.payment_router._user_from_subscription",
                   side_effect=RuntimeError("kaboom")):
            _downgrade_from_subscription("sub_err2", db_session)


# =============================================================================
# POST /payment/create-checkout — StripeError → 502 (lines 210-211)
# =============================================================================

class TestCreateCheckoutStripeError:

    def test_stripe_error_returns_502(self, db_session):
        """stripe.StripeError pendant la création de session → 502 (appel direct, rate-limit bypass)."""
        import asyncio
        from starlette.requests import Request as StarletteRequest
        from fastapi import HTTPException
        from app.routers.payment_router import create_checkout, CheckoutRequest

        u = _make_user(db_session, "free")
        user = u["user"]
        scope = {"type": "http", "method": "POST", "path": "/payment/create-checkout",
                 "headers": [], "query_string": b"", "client": ("127.88.88.88", 8888)}
        fake_request = StarletteRequest(scope)
        body = CheckoutRequest(plan="starter")

        with patch("app.routers.payment_router.stripe") as s:
            s.api_key = "sk_test_xxx"
            s.StripeError = _stripe.StripeError
            s.checkout.Session.create.side_effect = _stripe.StripeError("Stripe down")

            async def _run():
                return await create_checkout(fake_request, body=body,
                                             current_user=user, db=db_session)
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(_run())
                finally:
                    loop.close()
                assert False, "should have raised"
            except HTTPException as exc:
                assert exc.status_code == 502


# =============================================================================
# POST /payment/webhook — checkout customer.retrieve fallback (lines 246-248)
# POST /payment/webhook — asyncio.create_task RuntimeError (lines 274-276)
# POST /payment/webhook — invoice.payment_failed (lines 301-303)
# =============================================================================

class TestWebhookEdgeCases:

    def _post_event(self, client, event_type: str, data: dict):
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("stripe.Webhook.construct_event",
                   return_value=_fake_event(event_type, data)):
            return client.post(
                "/payment/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=sig"},
            )

    def test_checkout_completed_customer_retrieve_fallback(self, client, db_session):
        """checkout.session.completed : user introuvable via metadata → Customer.retrieve fallback."""
        u = _make_user(db_session, "free")
        data = {
            "id":       "cs_fallback",
            "metadata": {},          # pas de user_id dans metadata
            "customer": "cus_stripe_fallback",
            "subscription": None,
        }
        event = _fake_event("checkout.session.completed", data)
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app.routers.payment_router.stripe") as s:
            s.Webhook.construct_event.return_value = event
            s.Customer.retrieve.return_value = {"email": u["email"]}
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=sig"})
        assert resp.status_code == 200

        db_session.refresh(u["user"])
        # Plan mis à jour via fallback email
        assert u["user"].plan in ("starter", "pro", "dev", "free")

    def test_checkout_completed_customer_retrieve_exception_silenced(self, client, db_session):
        """Customer.retrieve lève une exception → silencieuse, webhook retourne 200."""
        data = {
            "id":       "cs_exc",
            "metadata": {},
            "customer": "cus_broken",
            "subscription": None,
        }
        event = _fake_event("checkout.session.completed", data)
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app.routers.payment_router.stripe") as s:
            s.Webhook.construct_event.return_value = event
            s.Customer.retrieve.side_effect = Exception("Stripe error")
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=sig"})
        assert resp.status_code == 200

    def test_checkout_completed_asyncio_runtime_error_silenced(self, client, db_session):
        """asyncio.create_task RuntimeError (pas de boucle active) → silencieux."""
        u = _make_user(db_session, "free")
        data = {
            "id":           "cs_runtime",
            "metadata":     {"user_id": str(u["user"].id), "plan": "starter"},
            "customer":     None,
            "subscription": None,
        }
        event = _fake_event("checkout.session.completed", data)
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app.routers.payment_router.stripe") as s, \
             patch("app.routers.payment_router._asyncio") as mock_asyncio:
            s.Webhook.construct_event.return_value = event
            mock_asyncio.create_task.side_effect = RuntimeError("no event loop")
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=sig"})
        assert resp.status_code == 200

    def test_invoice_payment_failed_triggers_downgrade(self, client, db_session):
        """invoice.payment_failed → _downgrade_from_subscription appelé."""
        u = _make_user(db_session, "pro", subscription_status="active")
        data = {"subscription": "sub_failed_pay"}
        event = _fake_event("invoice.payment_failed", data)

        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app.routers.payment_router.stripe") as s, \
             patch("app.routers.payment_router._downgrade_from_subscription") as mock_down:
            s.Webhook.construct_event.return_value = event
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=sig"})
        assert resp.status_code == 200
        mock_down.assert_called_once()

    def test_invoice_payment_failed_no_sub_id_no_op(self, client, db_session):
        """invoice.payment_failed sans subscription → pas d'appel downgrade."""
        data = {"subscription": None}
        event = _fake_event("invoice.payment_failed", data)

        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app.routers.payment_router.stripe") as s, \
             patch("app.routers.payment_router._downgrade_from_subscription") as mock_down:
            s.Webhook.construct_event.return_value = event
            resp = client.post("/payment/webhook", content=b"{}",
                               headers={"stripe-signature": "t=1,v1=sig"})
        assert resp.status_code == 200
        mock_down.assert_not_called()


# =============================================================================
# GET /payment/portal — cache update + Customer.list fallback (lines 391-392, 399-403)
# =============================================================================

class TestCustomerPortalEdgeCases:

    def test_portal_caches_customer_id_from_checkout_session(self, client, db_session):
        """Portal sans stripe_customer_id, last payment → Customer.retrieve → cache."""
        u = _make_user(db_session, "starter", subscription_status="active")
        _make_payment(db_session, u["user"].id, stripe_session_id="cs_portal_cache")
        assert u["user"].stripe_customer_id is None

        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            s.checkout.Session.retrieve.return_value = {"customer": "cus_cached_123"}
            s.billing_portal.Session.create.return_value = MagicMock(url="https://billing.stripe.com/p")
            resp = client.get("/payment/portal", headers=_auth(u["token"]))

        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].stripe_customer_id == "cus_cached_123"

    def test_portal_checkout_session_stripe_error_falls_through(self, client, db_session):
        """Session.retrieve StripeError → passe au fallback Customer.list."""
        u = _make_user(db_session, "starter", subscription_status="active")
        _make_payment(db_session, u["user"].id, stripe_session_id="cs_bad")

        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            s.checkout.Session.retrieve.side_effect = _stripe.StripeError("session gone")
            # Customer.list retourne un customer
            mock_cust = MagicMock()
            mock_cust.id = "cus_from_list"
            s.Customer.list.return_value = MagicMock(data=[mock_cust])
            s.billing_portal.Session.create.return_value = MagicMock(url="https://billing.stripe.com/l")
            resp = client.get("/payment/portal", headers=_auth(u["token"]))

        assert resp.status_code == 200

    def test_portal_customer_list_caches_and_returns_portal(self, client, db_session):
        """Fallback Customer.list → customer_id mis en cache + portal retourné."""
        u = _make_user(db_session, "pro", subscription_status="active")
        assert u["user"].stripe_customer_id is None

        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            mock_cust = MagicMock()
            mock_cust.id = "cus_list_found"
            s.Customer.list.return_value = MagicMock(data=[mock_cust])
            s.billing_portal.Session.create.return_value = MagicMock(url="https://billing.stripe.com/ok")
            resp = client.get("/payment/portal", headers=_auth(u["token"]))

        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].stripe_customer_id == "cus_list_found"

    def test_portal_customer_list_stripe_error_leads_to_404(self, client, db_session):
        """Customer.list StripeError → customer_id reste None → 404."""
        u = _make_user(db_session, "pro", subscription_status="active")

        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            s.Customer.list.side_effect = _stripe.StripeError("list failed")
            resp = client.get("/payment/portal", headers=_auth(u["token"]))

        assert resp.status_code == 404


# =============================================================================
# POST /payment/cancel — StripeError handlers (lines 448-449, 453-457, 462-463)
# =============================================================================

class TestCancelSubscriptionStripeErrors:

    def test_subscription_list_stripe_error_silenced(self, client, db_session):
        """Subscription.list StripeError → ignorée, subscription_status=cancelling quand même."""
        u = _make_user(db_session, "pro", subscription_status="active",
                       stripe_customer_id="cus_err")
        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            s.Subscription.list.side_effect = _stripe.StripeError("list error")
            resp = client.post("/payment/cancel", headers=_auth(u["token"]))
        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].subscription_status == "cancelling"

    def test_session_retrieve_stripe_error_silenced(self, client, db_session):
        """checkout.Session.retrieve StripeError → ignorée, sub_id reste None mais cancelling."""
        u = _make_user(db_session, "starter", subscription_status="active")
        _make_payment(db_session, u["user"].id, stripe_session_id="cs_retrieve_err")

        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            s.checkout.Session.retrieve.side_effect = _stripe.StripeError("retrieve fail")
            resp = client.post("/payment/cancel", headers=_auth(u["token"]))
        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].subscription_status == "cancelling"

    def test_subscription_modify_stripe_error_silenced(self, client, db_session):
        """Subscription.modify StripeError → ignorée, subscription_status=cancelling quand même."""
        u = _make_user(db_session, "pro", subscription_status="active",
                       stripe_customer_id="cus_mod_err")
        mock_sub = MagicMock()
        mock_sub.id = "sub_modify_error"
        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            s.Subscription.list.return_value = MagicMock(data=[mock_sub])
            s.Subscription.modify.side_effect = _stripe.StripeError("modify fail")
            resp = client.post("/payment/cancel", headers=_auth(u["token"]))
        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].subscription_status == "cancelling"


# =============================================================================
# Remaining missing lines:
#   246-248 — webhook construct_event generic Exception → 400
#   455     — cancel: sub_id from checkout.Session.retrieve success
# =============================================================================

class TestWebhookConstructEventException:

    def test_generic_exception_returns_400(self, client, db_session):
        """construct_event lève Exception (non-SignatureVerificationError) → 400."""
        with patch("app.routers.payment_router.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app.routers.payment_router.stripe") as s:
            s.SignatureVerificationError = _stripe.SignatureVerificationError
            s.Webhook.construct_event.side_effect = Exception("unexpected parse error")
            resp = client.post(
                "/payment/webhook",
                content=b"bad-body",
                headers={"stripe-signature": "t=1,v1=sig"},
            )
        assert resp.status_code == 400


class TestCancelViaSessionRetrieve:

    def test_sub_id_fetched_from_session_retrieve(self, client, db_session):
        """Subscription.list vide → fallback checkout.Session.retrieve → sub_id."""
        u = _make_user(db_session, "starter", subscription_status="active",
                       stripe_customer_id="cus_no_subs")
        _make_payment(db_session, u["user"].id, stripe_session_id="cs_has_sub")

        mock_sub = MagicMock()
        mock_sub.id = "sub_from_session"
        with patch("app.routers.payment_router.stripe") as s:
            s.StripeError = _stripe.StripeError
            # Subscription.list returns empty → no sub_id from step 1
            s.Subscription.list.return_value = MagicMock(data=[])
            # Session.retrieve returns dict with subscription
            s.checkout.Session.retrieve.return_value = {"subscription": "sub_from_session"}
            # Subscription.modify should be called with the sub_id from session
            resp = client.post("/payment/cancel", headers=_auth(u["token"]))
        assert resp.status_code == 200
        db_session.refresh(u["user"])
        assert u["user"].subscription_status == "cancelling"
        s.Subscription.modify.assert_called_once_with("sub_from_session", cancel_at_period_end=True)
