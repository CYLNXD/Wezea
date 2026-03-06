"""
Tests : webhook_router — GET/POST/DELETE /webhooks + POST /webhooks/{id}/test
------------------------------------------------------------------------------
Stratégie :
- Users Pro/Free créés directement en DB (_make_user) — zéro rate-limit
- Livraison HTTP mockée via respx (AsyncClient httpx) pour POST /{id}/test
- fire_webhooks() testé en isolation avec mock httpx
"""
import json
import uuid as _uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models import User, Webhook
from app.auth import hash_password, generate_api_key, create_access_token


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(db_session, plan: str = "pro") -> dict:
    email = f"{plan}-{_uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("TestPass123"),
        plan=plan,
        api_key=generate_api_key(),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id, email, plan)
    return {"email": email, "user": user, "token": token}


def _make_webhook(db_session, user_id: int, *,
                  url: str = "https://example.com/hook",
                  events: list | None = None,
                  is_active: bool = True) -> Webhook:
    hook = Webhook(
        user_id   = user_id,
        url       = url,
        secret    = "test-secret-abc123",
        events    = json.dumps(events or ["scan.completed"]),
        is_active = is_active,
    )
    db_session.add(hook)
    db_session.commit()
    db_session.refresh(hook)
    return hook


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


VALID_WEBHOOK = {
    "url":    "https://hooks.example.com/wezea",
    "events": ["scan.completed", "alert.triggered"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Guard — plan Pro requis
# ─────────────────────────────────────────────────────────────────────────────

class TestWebhookGuard:
    def test_unauthenticated_returns_401(self, client, db_session):
        resp = client.get("/webhooks")
        assert resp.status_code == 401

    def test_free_user_returns_403(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = client.get("/webhooks", headers=_auth(u["token"]))
        assert resp.status_code == 403

    def test_starter_user_returns_403(self, client, db_session):
        u = _make_user(db_session, "starter")
        resp = client.get("/webhooks", headers=_auth(u["token"]))
        assert resp.status_code == 403

    def test_pro_user_can_access(self, client, db_session):
        u = _make_user(db_session, "pro")
        resp = client.get("/webhooks", headers=_auth(u["token"]))
        assert resp.status_code == 200

    def test_403_detail_mentions_upgrade(self, client, db_session):
        u = _make_user(db_session, "free")
        resp = client.post("/webhooks", json=VALID_WEBHOOK, headers=_auth(u["token"]))
        assert resp.status_code == 403
        detail = resp.json().get("detail", {})
        assert "upgrade_url" in detail


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhooks
# ─────────────────────────────────────────────────────────────────────────────

class TestListWebhooks:
    def test_empty_list_for_new_pro_user(self, client, db_session):
        u = _make_user(db_session, "pro")
        resp = client.get("/webhooks", headers=_auth(u["token"]))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_own_webhooks_only(self, client, db_session):
        u1 = _make_user(db_session, "pro")
        u2 = _make_user(db_session, "pro")
        _make_webhook(db_session, u1["user"].id, url="https://u1.com/hook")
        _make_webhook(db_session, u2["user"].id, url="https://u2.com/hook")

        resp = client.get("/webhooks", headers=_auth(u1["token"]))
        assert len(resp.json()) == 1
        assert resp.json()[0]["url"] == "https://u1.com/hook"

    def test_inactive_webhooks_not_returned(self, client, db_session):
        u = _make_user(db_session, "pro")
        _make_webhook(db_session, u["user"].id, url="https://active.com/hook", is_active=True)
        _make_webhook(db_session, u["user"].id, url="https://inactive.com/hook", is_active=False)

        resp = client.get("/webhooks", headers=_auth(u["token"]))
        assert len(resp.json()) == 1
        assert resp.json()[0]["url"] == "https://active.com/hook"

    def test_response_shape(self, client, db_session):
        u = _make_user(db_session, "pro")
        _make_webhook(db_session, u["user"].id)
        resp = client.get("/webhooks", headers=_auth(u["token"]))
        hook = resp.json()[0]
        assert "id" in hook
        assert "url" in hook
        assert "events" in hook
        assert "is_active" in hook
        assert "created_at" in hook
        assert "last_fired_at" in hook
        assert "last_status" in hook

    def test_events_returned_as_list(self, client, db_session):
        u = _make_user(db_session, "pro")
        _make_webhook(db_session, u["user"].id,
                      events=["scan.completed", "alert.triggered"])
        hook = client.get("/webhooks", headers=_auth(u["token"])).json()[0]
        assert isinstance(hook["events"], list)
        assert "scan.completed" in hook["events"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhooks
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateWebhook:
    def test_create_returns_201(self, client, db_session):
        u = _make_user(db_session, "pro")
        resp = client.post("/webhooks", json=VALID_WEBHOOK, headers=_auth(u["token"]))
        assert resp.status_code == 201

    def test_create_returns_secret_once(self, client, db_session):
        u = _make_user(db_session, "pro")
        resp = client.post("/webhooks", json=VALID_WEBHOOK, headers=_auth(u["token"]))
        data = resp.json()
        assert "secret" in data
        assert len(data["secret"]) > 0

    def test_secret_not_exposed_in_list(self, client, db_session):
        u = _make_user(db_session, "pro")
        client.post("/webhooks", json=VALID_WEBHOOK, headers=_auth(u["token"]))
        hooks = client.get("/webhooks", headers=_auth(u["token"])).json()
        assert "secret" not in hooks[0]

    def test_custom_secret_accepted(self, client, db_session):
        u = _make_user(db_session, "pro")
        body = {**VALID_WEBHOOK, "secret": "my-custom-secret-key"}
        resp = client.post("/webhooks", json=body, headers=_auth(u["token"]))
        assert resp.status_code == 201
        assert resp.json()["secret"] == "my-custom-secret-key"

    def test_url_must_start_with_http(self, client, db_session):
        u = _make_user(db_session, "pro")
        bad = {**VALID_WEBHOOK, "url": "ftp://not-http.com/hook"}
        resp = client.post("/webhooks", json=bad, headers=_auth(u["token"]))
        assert resp.status_code == 422

    def test_invalid_event_returns_422(self, client, db_session):
        u = _make_user(db_session, "pro")
        bad = {**VALID_WEBHOOK, "events": ["scan.completed", "invalid.event"]}
        resp = client.post("/webhooks", json=bad, headers=_auth(u["token"]))
        assert resp.status_code == 422

    def test_empty_events_returns_422(self, client, db_session):
        u = _make_user(db_session, "pro")
        bad = {**VALID_WEBHOOK, "events": []}
        resp = client.post("/webhooks", json=bad, headers=_auth(u["token"]))
        assert resp.status_code == 422

    def test_limit_5_webhooks_per_account(self, client, db_session):
        u = _make_user(db_session, "pro")
        for i in range(5):
            _make_webhook(db_session, u["user"].id, url=f"https://hook{i}.com/wh")
        # Le 6ème doit être refusé
        resp = client.post("/webhooks", json=VALID_WEBHOOK, headers=_auth(u["token"]))
        assert resp.status_code == 429

    def test_all_valid_events_accepted(self, client, db_session):
        u = _make_user(db_session, "pro")
        body = {
            "url":    "https://example.com/hook",
            "events": ["scan.completed", "alert.triggered", "score.dropped"],
        }
        resp = client.post("/webhooks", json=body, headers=_auth(u["token"]))
        assert resp.status_code == 201

    def test_webhook_saved_in_db(self, client, db_session):
        u = _make_user(db_session, "pro")
        client.post("/webhooks", json=VALID_WEBHOOK, headers=_auth(u["token"]))
        hook = db_session.query(Webhook).filter_by(
            user_id=u["user"].id
        ).first()
        assert hook is not None
        assert hook.url == VALID_WEBHOOK["url"]
        assert hook.is_active is True


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /webhooks/{id}
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteWebhook:
    def test_delete_own_webhook_returns_200(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)
        resp = client.delete(f"/webhooks/{hook.id}", headers=_auth(u["token"]))
        assert resp.status_code == 200

    def test_deleted_webhook_disappears_from_list(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)
        client.delete(f"/webhooks/{hook.id}", headers=_auth(u["token"]))
        hooks = client.get("/webhooks", headers=_auth(u["token"])).json()
        assert all(h["id"] != hook.id for h in hooks)

    def test_delete_is_soft_deactivation(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)
        client.delete(f"/webhooks/{hook.id}", headers=_auth(u["token"]))
        db_session.expire_all()
        # Le Webhook doit toujours exister en DB — juste is_active=False
        still_exists = db_session.query(Webhook).filter_by(id=hook.id).first()
        assert still_exists is not None
        assert still_exists.is_active is False

    def test_delete_other_users_webhook_returns_404(self, client, db_session):
        u1 = _make_user(db_session, "pro")
        u2 = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u1["user"].id)
        resp = client.delete(f"/webhooks/{hook.id}", headers=_auth(u2["token"]))
        assert resp.status_code == 404

    def test_delete_unknown_webhook_returns_404(self, client, db_session):
        u = _make_user(db_session, "pro")
        resp = client.delete("/webhooks/999999", headers=_auth(u["token"]))
        assert resp.status_code == 404

    def test_delete_after_create_reduces_count(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)
        assert len(client.get("/webhooks", headers=_auth(u["token"])).json()) == 1
        client.delete(f"/webhooks/{hook.id}", headers=_auth(u["token"]))
        assert len(client.get("/webhooks", headers=_auth(u["token"])).json()) == 0


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhooks/{id}/test
# ─────────────────────────────────────────────────────────────────────────────

class TestTestWebhook:
    def test_successful_delivery_returns_delivered_true(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.post = AsyncMock(return_value=mock_resp)

            resp = client.post(f"/webhooks/{hook.id}/test", headers=_auth(u["token"]))

        assert resp.status_code == 200
        data = resp.json()
        assert data["delivered"] is True
        assert data["status"] == 200

    def test_failed_delivery_returns_delivered_false(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_resp = AsyncMock()
            mock_resp.status_code = 500
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.post = AsyncMock(return_value=mock_resp)

            resp = client.post(f"/webhooks/{hook.id}/test", headers=_auth(u["token"]))

        assert resp.status_code == 200
        assert resp.json()["delivered"] is False
        assert resp.json()["status"] == 500

    def test_network_error_returns_status_zero(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.post = AsyncMock(side_effect=Exception("Connection refused"))

            resp = client.post(f"/webhooks/{hook.id}/test", headers=_auth(u["token"]))

        assert resp.status_code == 200
        assert resp.json()["delivered"] is False
        assert resp.json()["status"] == 0

    def test_test_unknown_webhook_returns_404(self, client, db_session):
        u = _make_user(db_session, "pro")
        resp = client.post("/webhooks/999999/test", headers=_auth(u["token"]))
        assert resp.status_code == 404

    def test_test_other_users_webhook_returns_404(self, client, db_session):
        u1 = _make_user(db_session, "pro")
        u2 = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u1["user"].id)
        resp = client.post(f"/webhooks/{hook.id}/test", headers=_auth(u2["token"]))
        assert resp.status_code == 404

    def test_test_inactive_webhook_returns_404(self, client, db_session):
        u = _make_user(db_session, "pro")
        hook = _make_webhook(db_session, u["user"].id, is_active=False)
        resp = client.post(f"/webhooks/{hook.id}/test", headers=_auth(u["token"]))
        assert resp.status_code == 404


class TestWebhookValidation:
    """Chemins de validation non couverts dans webhook_router.py."""

    def test_url_too_long_returns_422(self, client, db_session):
        """URL > 512 caractères → 422."""
        u = _make_user(db_session, "pro")
        long_url = "https://example.com/" + "a" * 500
        resp = client.post(
            "/webhooks",
            json={"url": long_url, "events": ["scan.complete"]},
            headers=_auth(u["token"]),
        )
        assert resp.status_code == 422
        assert "trop longue" in resp.json()["detail"].lower() or \
               "512" in resp.json()["detail"]


class TestFireWebhooks:
    """Couverture de fire_webhooks (lignes 255-266)."""

    @pytest.mark.asyncio
    async def test_delivers_to_matching_hook(self, db_session):
        """fire_webhooks appelle _deliver pour les hooks dont l'event correspond."""
        from app.models import Webhook
        import json, time as _time
        from unittest.mock import AsyncMock, patch

        u = _make_user(db_session, "pro")
        hook = Webhook(
            user_id=u["user"].id,
            url="https://hook.example.com/cb",
            events=json.dumps(["scan.complete"]),
            secret="sec",
            is_active=True,
        )
        db_session.add(hook)
        db_session.commit()

        mock_deliver = AsyncMock()
        from app.routers.webhook_router import fire_webhooks
        with patch("app.routers.webhook_router._deliver", mock_deliver):
            await fire_webhooks(
                user_id=u["user"].id,
                event="scan.complete",
                payload={"data": {"score": 80}},
                db=db_session,
            )

        mock_deliver.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_hook_with_different_event(self, db_session):
        """fire_webhooks ne livre pas si l'event ne correspond pas."""
        from app.models import Webhook
        import json
        from unittest.mock import AsyncMock, patch

        u = _make_user(db_session, "pro")
        hook = Webhook(
            user_id=u["user"].id,
            url="https://hook.example.com/cb",
            events=json.dumps(["alert.triggered"]),
            secret="sec",
            is_active=True,
        )
        db_session.add(hook)
        db_session.commit()

        mock_deliver = AsyncMock()
        from app.routers.webhook_router import fire_webhooks
        with patch("app.routers.webhook_router._deliver", mock_deliver):
            await fire_webhooks(
                user_id=u["user"].id,
                event="scan.complete",  # différent de alert.triggered
                payload={},
                db=db_session,
            )

        mock_deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_in_deliver_is_silenced(self, db_session):
        """Exception dans _deliver → silencieuse, fire_webhooks ne lève pas."""
        from app.models import Webhook
        import json
        from unittest.mock import AsyncMock, patch

        u = _make_user(db_session, "pro")
        hook = Webhook(
            user_id=u["user"].id,
            url="https://hook.example.com/cb",
            events=json.dumps(["scan.complete"]),
            secret="sec",
            is_active=True,
        )
        db_session.add(hook)
        db_session.commit()

        from app.routers.webhook_router import fire_webhooks
        with patch("app.routers.webhook_router._deliver",
                   AsyncMock(side_effect=RuntimeError("delivery KO"))):
            await fire_webhooks(
                user_id=u["user"].id,
                event="scan.complete",
                payload={},
                db=db_session,
            )  # ne doit pas lever
