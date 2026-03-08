"""
Tests unitaires pour app.services.brevo_service
================================================
Stratégie :
  • _send / _contacts_request → mock httpx.AsyncClient directement
  • Fonctions email haut-niveau → 2 catégories :
    1. Patchées par conftest à session scope (send_welcome_email, etc.)
       → référence originale sauvée à l'import (avant que conftest les remplace)
       → mock _send / _contacts_request pour tester leur logique interne
    2. Non patchées par conftest → testées normalement via svc.*
       → mock _send / _contacts_request selon le cas
  • add_newsletter_contact / remove_newsletter_contact → httpx mocké directement
    (elles ne passent pas par _contacts_request)

Zéro réseau réel — zéro dépendance Brevo.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Sauvegarder les fonctions RÉELLES avant que le conftest session-scope
#    les remplace (les imports se font à la collecte, avant les fixtures) ──────
import app.services.brevo_service as _svc

_real_send_welcome          = _svc.send_welcome_email
_real_send_reset            = _svc.send_password_reset_email
_real_add_registered        = _svc.add_registered_user_contact
_real_update_contact        = _svc.update_brevo_contact
_real_delete_contact        = _svc.delete_brevo_contact


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_response(status_code: int, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    return r


def _mock_http_client(response: MagicMock) -> MagicMock:
    """Simule AsyncClient context-manager pour httpx."""
    mock_client = AsyncMock()
    mock_client.post   = AsyncMock(return_value=response)
    mock_client.put    = AsyncMock(return_value=response)
    mock_client.delete = AsyncMock(return_value=response)
    mock_client.get    = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__  = AsyncMock(return_value=False)
    return mock_client


# ─────────────────────────────────────────────────────────────────────────────
# _send — helper HTTP bas niveau
# ─────────────────────────────────────────────────────────────────────────────

class TestSend:

    @pytest.mark.asyncio
    async def test_no_api_key_returns_false(self):
        """Sans BREVO_API_KEY, _send retourne False sans appel réseau."""
        with patch.object(_svc, "BREVO_API_KEY", ""):
            result = await _svc._send({"subject": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(200))):
            result = await _svc._send({"subject": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_201_returns_true(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(201))):
            result = await _svc._send({"subject": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_400_returns_false(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(400, "Bad Request"))):
            result = await _svc._send({"subject": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_500_returns_false(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(500))):
            result = await _svc._send({"subject": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_network_exception_returns_false(self):
        """Une exception réseau ne propage pas l'erreur."""
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aexit__  = AsyncMock(return_value=False)
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await _svc._send({"subject": "test"})
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# _contacts_request — helper contacts bas niveau
# ─────────────────────────────────────────────────────────────────────────────

class TestContactsRequest:

    @pytest.mark.asyncio
    async def test_no_api_key_returns_false(self):
        with patch.object(_svc, "BREVO_API_KEY", ""):
            result = await _svc._contacts_request("post", "https://example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(200))):
            result = await _svc._contacts_request("post", "https://example.com", json={})
        assert result is True

    @pytest.mark.asyncio
    async def test_204_returns_true(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(204))):
            result = await _svc._contacts_request("delete", "https://example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_404_returns_false(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(404))):
            result = await _svc._contacts_request("get", "https://example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aexit__  = AsyncMock(return_value=False)
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await _svc._contacts_request("post", "https://example.com")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# send_welcome_email  (conftest la remplace → on teste la vraie via _real_*)
# ─────────────────────────────────────────────────────────────────────────────

class TestSendWelcomeEmail:

    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _real_send_welcome("user@example.com")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_payload_contains_email(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _real_send_welcome("hello@example.com")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "hello@example.com"

    @pytest.mark.asyncio
    async def test_returns_false_when_send_fails(self):
        with patch.object(_svc, "_send", AsyncMock(return_value=False)):
            result = await _real_send_welcome("user@example.com")
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# send_password_reset_email  (conftest la remplace → _real_*)
# ─────────────────────────────────────────────────────────────────────────────

class TestSendPasswordResetEmail:

    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _real_send_reset("x@x.com", "https://wezea.net/?reset_token=abc")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_url_is_escaped(self):
        """URL avec HTML doit être échappée dans le contenu de l'email."""
        mock_send = AsyncMock(return_value=True)
        malicious = "https://evil.com/<script>alert(1)</script>"
        with patch.object(_svc, "_send", mock_send):
            await _real_send_reset("x@x.com", malicious)
        html = mock_send.call_args[0][0]["htmlContent"]
        assert "<script>" not in html

    @pytest.mark.asyncio
    async def test_payload_to_field(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _real_send_reset("reset@example.com", "https://wezea.net/reset")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "reset@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# add_registered_user_contact  (conftest la remplace → _real_*)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddRegisteredUserContact:

    @pytest.mark.asyncio
    async def test_uses_post_method(self):
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_add_registered("user@example.com")
        method = mock_req.call_args[0][0]
        assert method == "post"

    @pytest.mark.asyncio
    async def test_includes_list_id_2(self):
        """Le contact doit être ajouté à la liste 2 (utilisateurs inscrits)."""
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_add_registered("user@example.com")
        payload = mock_req.call_args[1]["json"]
        assert 2 in payload["listIds"]

    @pytest.mark.asyncio
    async def test_with_first_and_last_name(self):
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_add_registered("u@u.com", first_name="Alice", last_name="Martin")
        payload = mock_req.call_args[1]["json"]
        assert payload["attributes"]["FIRSTNAME"] == "Alice"
        assert payload["attributes"]["LASTNAME"]  == "Martin"


# ─────────────────────────────────────────────────────────────────────────────
# update_brevo_contact  (conftest la remplace → _real_*)
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateBrevoContact:

    @pytest.mark.asyncio
    async def test_uses_put_method(self):
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_update_contact("user@example.com", "pro")
        method = mock_req.call_args[0][0]
        assert method == "put"

    @pytest.mark.asyncio
    async def test_sets_plan_attribute(self):
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_update_contact("user@example.com", "starter")
        payload = mock_req.call_args[1]["json"]
        assert payload["attributes"]["PLAN"] == "starter"


# ─────────────────────────────────────────────────────────────────────────────
# delete_brevo_contact  (conftest la remplace → _real_*)
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteBrevoContact:

    @pytest.mark.asyncio
    async def test_uses_delete_method(self):
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_delete_contact("user@example.com")
        method = mock_req.call_args[0][0]
        assert method == "delete"

    @pytest.mark.asyncio
    async def test_url_contains_email(self):
        mock_req = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_req):
            await _real_delete_contact("user@example.com")
        url = mock_req.call_args[0][1]
        assert "user@example.com" in url


# ─────────────────────────────────────────────────────────────────────────────
# send_monitoring_alert_email  (non patchée par conftest)
# ─────────────────────────────────────────────────────────────────────────────

class TestSendMonitoringAlertEmail:

    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_monitoring_alert_email(
                email="admin@example.com", first_name="Alice",
                domain="example.com", new_score=45, prev_score=70,
                risk_level="HIGH", reason="Score dropped", findings=[],
            )
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_fields_are_escaped(self):
        """Champs utilisateur (domain, first_name, reason) → HTML-échappés."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_monitoring_alert_email(
                email="x@x.com",
                first_name="<b>Bob</b>",
                domain='evil<script>alert(1)</script>.com',
                new_score=30, prev_score=60, risk_level="CRITICAL",
                reason="<img onerror=alert(1)>",
                findings=[],
            )
        html = mock_send.call_args[0][0]["htmlContent"]
        assert "<script>" not in html
        assert "<img" not in html
        assert "<b>Bob</b>" not in html

    @pytest.mark.asyncio
    async def test_subject_contains_domain_and_score(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_monitoring_alert_email(
                email="x@x.com", first_name="X", domain="target.com",
                new_score=55, prev_score=80, risk_level="HIGH",
                reason="Score drop", findings=[],
            )
        subject = mock_send.call_args[0][0]["subject"]
        assert "target.com" in subject
        assert "55" in subject


# ─────────────────────────────────────────────────────────────────────────────
# send_upgrade_email  (non patchée par conftest)
# ─────────────────────────────────────────────────────────────────────────────

class TestSendUpgradeEmail:

    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_upgrade_email("user@example.com", "pro")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_payload_to_field(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_upgrade_email("upgrade@example.com", "starter")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "upgrade@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# send_contact_notification  (non patchée par conftest)
# ─────────────────────────────────────────────────────────────────────────────

class TestSendContactNotification:

    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_contact_notification(
                name="Alice", email="alice@example.com",
                subject="Question", message="Hello !"
            )
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_message_is_escaped(self):
        """Champs du formulaire → HTML-échappés."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_contact_notification(
                name="<script>hack</script>",
                email="h@h.com",
                subject="XSS <attempt>",
                message="<img onerror='alert(1)'>",
            )
        html = mock_send.call_args[0][0]["htmlContent"]
        assert "<script>" not in html
        assert "<img" not in html


# ─────────────────────────────────────────────────────────────────────────────
# Newsletter functions — httpx utilisé directement (non via _contacts_request)
# ─────────────────────────────────────────────────────────────────────────────

class TestNewsletterFunctions:

    @pytest.mark.asyncio
    async def test_add_newsletter_contact_returns_false_without_api_key(self):
        with patch.object(_svc, "BREVO_API_KEY", ""):
            result = await _svc.add_newsletter_contact("news@example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_add_newsletter_contact_returns_true_on_success(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(201))):
            result = await _svc.add_newsletter_contact("news@example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_add_newsletter_contact_exception_returns_false(self):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aexit__  = AsyncMock(return_value=False)
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await _svc.add_newsletter_contact("news@example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_newsletter_contact_returns_false_without_api_key(self):
        with patch.object(_svc, "BREVO_API_KEY", ""):
            result = await _svc.remove_newsletter_contact("news@example.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_newsletter_contact_returns_true_on_success(self):
        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=_mock_http_client(_make_response(200))):
            result = await _svc.remove_newsletter_contact("news@example.com")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_newsletter_confirmation_delegates_to_send(self):
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_newsletter_confirmation_email("sub@example.com", "tok-abc")
        assert result is True
        mock_send.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding emails — J+1 / J+3 / J+7 / J+14
# ─────────────────────────────────────────────────────────────────────────────

class TestOnboardingEmails:
    @pytest.mark.asyncio
    async def test_send_activation_nudge_delegates_to_send(self):
        """send_activation_nudge_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_activation_nudge_email("user@example.com")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_activation_nudge_to_field(self):
        """send_activation_nudge_email : destinataire correct."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_activation_nudge_email("user@example.com")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_send_upgrade_nudge_delegates_to_send(self):
        """send_upgrade_nudge_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_upgrade_nudge_email("user@example.com")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_upgrade_nudge_to_field(self):
        """send_upgrade_nudge_email : destinataire correct."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_upgrade_nudge_email("user@example.com")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_send_value_reminder_delegates_to_send(self):
        """send_value_reminder_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_value_reminder_email("user@example.com", 3)
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_value_reminder_includes_scan_count(self):
        """send_value_reminder_email : le nombre de scans est dans le HTML."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_value_reminder_email("user@example.com", 5)
        payload = mock_send.call_args[0][0]
        assert "5" in payload["htmlContent"]

    @pytest.mark.asyncio
    async def test_send_winback_delegates_to_send(self):
        """send_winback_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_winback_email("user@example.com")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_winback_to_field(self):
        """send_winback_email : destinataire correct."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_winback_email("user@example.com")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "user@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# send_monitoring_alert_email — findings non vides
# ─────────────────────────────────────────────────────────────────────────────

class TestSendMonitoringAlertWithFindings:
    @pytest.mark.asyncio
    async def test_findings_rendered_in_html(self):
        """Quand findings non vides, leur titre apparaît dans le HTML."""
        from types import SimpleNamespace
        findings = [
            SimpleNamespace(title="Certificat SSL expiré"),
            SimpleNamespace(title="Port RDP ouvert"),
        ]
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_monitoring_alert_email(
                email="user@example.com",
                first_name="Alice",
                domain="example.com",
                new_score=55,
                prev_score=80,
                risk_level="HIGH",
                reason="Score drop",
                findings=findings,
            )
        payload = mock_send.call_args[0][0]
        assert "Certificat SSL expir" in payload["htmlContent"]
        assert "Port RDP ouvert"      in payload["htmlContent"]


# ─────────────────────────────────────────────────────────────────────────────
# send_pdf_email
# ─────────────────────────────────────────────────────────────────────────────

class TestSendPdfEmail:
    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        """send_pdf_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_pdf_email(
                email="user@example.com",
                domain="example.com",
                pdf_bytes=b"%PDF-fake",
                score=85,
                risk_level="LOW",
            )
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_attachment_is_base64_encoded(self):
        """Le PDF est encodé en base64 dans le payload."""
        import base64
        raw = b"%PDF-1.4 fake content"
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_pdf_email(
                email="user@example.com",
                domain="example.com",
                pdf_bytes=raw,
                score=75,
                risk_level="MEDIUM",
            )
        payload = mock_send.call_args[0][0]
        assert "attachment" in payload
        encoded = payload["attachment"][0]["content"]
        assert base64.b64decode(encoded) == raw

    @pytest.mark.asyncio
    async def test_to_field_correct(self):
        """send_pdf_email : destinataire correct."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_pdf_email(
                email="report@example.com",
                domain="example.com",
                pdf_bytes=b"pdf",
                score=90,
                risk_level="LOW",
            )
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "report@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# send_contact_confirmation
# ─────────────────────────────────────────────────────────────────────────────

class TestSendContactConfirmation:
    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        """send_contact_confirmation délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_contact_confirmation("Alice", "alice@example.com")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_to_field_correct(self):
        """send_contact_confirmation : envoyé à l'utilisateur, pas à Wezea."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_contact_confirmation("Bob", "bob@example.com")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "bob@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# send_newsletter_welcome_email
# ─────────────────────────────────────────────────────────────────────────────

class TestSendNewsletterWelcomeEmail:
    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        """send_newsletter_welcome_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_newsletter_welcome_email("news@example.com")
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_to_field_correct(self):
        """send_newsletter_welcome_email : destinataire correct."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_newsletter_welcome_email("sub@example.com")
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "sub@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# add_newsletter_contact — chemin fallback (r.status_code non 2xx)
# ─────────────────────────────────────────────────────────────────────────────

class TestAddNewsletterContactFallback:
    @pytest.mark.asyncio
    async def test_fallback_list_add_on_non_2xx(self):
        """Si POST createContact renvoie 400 (contact existant), on tente POST /lists/.../add."""
        # Les deux appels utilisent client.post() — side_effect liste pour séquencer les réponses
        # Premier appel (POST createContact) → 400
        # Deuxième appel (POST lists/add) → 200
        first_response  = _make_response(400)
        second_response = _make_response(200)

        mock_client = AsyncMock()
        mock_client.post   = AsyncMock(side_effect=[first_response, second_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)

        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await _svc.add_newsletter_contact("existing@example.com")

        assert result is True
        # Vérifier que le fallback POST /lists/.../add a été appelé (2 appels au total)
        assert mock_client.post.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# remove_newsletter_contact — exception handler
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveNewsletterContactException:
    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        """remove_newsletter_contact : exception réseau → False."""
        mock_client = AsyncMock()
        mock_client.post       = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__  = AsyncMock(return_value=False)

        with patch.object(_svc, "BREVO_API_KEY", "fake-key"), \
             patch("httpx.AsyncClient", return_value=mock_client):
            result = await _svc.remove_newsletter_contact("user@example.com")

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Lead Generation — add_lead_contact + send_lead_report_email
# ─────────────────────────────────────────────────────────────────────────────

class TestAddLeadContact:
    @pytest.mark.asyncio
    async def test_delegates_to_contacts_request(self):
        """add_lead_contact délègue à _contacts_request (liste 4, attrs DOMAIN)."""
        mock_cr = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_cr):
            result = await _svc.add_lead_contact("lead@example.com", "example.com")
        assert result is True
        mock_cr.assert_called_once()
        _, url, kwargs = mock_cr.call_args[0][0], mock_cr.call_args[0][1], mock_cr.call_args[1]
        assert "listIds" in kwargs["json"]
        assert _svc.LEADS_LIST_ID in kwargs["json"]["listIds"]

    @pytest.mark.asyncio
    async def test_domain_attribute_set(self):
        """add_lead_contact : attribut DOMAIN transmis dans le payload."""
        mock_cr = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_cr):
            await _svc.add_lead_contact("lead@example.com", "my-domain.fr")
        payload = mock_cr.call_args[1]["json"]
        assert payload["attributes"]["DOMAIN"] == "my-domain.fr"

    @pytest.mark.asyncio
    async def test_lead_source_attribute_set(self):
        """add_lead_contact : attribut LEAD_SOURCE = 'landing_report'."""
        mock_cr = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_cr):
            await _svc.add_lead_contact("lead@example.com", "example.com")
        payload = mock_cr.call_args[1]["json"]
        assert payload["attributes"]["LEAD_SOURCE"] == "landing_report"

    @pytest.mark.asyncio
    async def test_update_enabled(self):
        """add_lead_contact : updateEnabled=True (contact existant mis à jour)."""
        mock_cr = AsyncMock(return_value=True)
        with patch.object(_svc, "_contacts_request", mock_cr):
            await _svc.add_lead_contact("existing@example.com", "example.com")
        payload = mock_cr.call_args[1]["json"]
        assert payload["updateEnabled"] is True


class TestSendLeadReportEmail:
    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        """send_lead_report_email délègue à _send."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_lead_report_email(
                email="lead@example.com",
                domain="example.com",
                pdf_bytes=b"%PDF-fake",
                score=72,
                risk_level="MEDIUM",
            )
        assert result is True
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_pdf_attachment_base64(self):
        """Le PDF est encodé en base64 dans l'attachment."""
        import base64
        raw = b"%PDF-1.4 lead report"
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_lead_report_email(
                email="lead@example.com",
                domain="example.com",
                pdf_bytes=raw,
                score=60,
                risk_level="HIGH",
            )
        payload = mock_send.call_args[0][0]
        encoded = payload["attachment"][0]["content"]
        assert base64.b64decode(encoded) == raw

    @pytest.mark.asyncio
    async def test_recipient_correct(self):
        """Le destinataire correspond à l'email fourni."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_lead_report_email(
                email="client@agency.com",
                domain="example.com",
                pdf_bytes=b"pdf",
                score=85,
                risk_level="LOW",
            )
        payload = mock_send.call_args[0][0]
        assert payload["to"][0]["email"] == "client@agency.com"

    @pytest.mark.asyncio
    async def test_risk_color_critical(self):
        """Risque CRITICAL → couleur rouge dans le HTML."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_lead_report_email(
                email="lead@example.com",
                domain="example.com",
                pdf_bytes=b"pdf",
                score=20,
                risk_level="CRITICAL",
            )
        payload = mock_send.call_args[0][0]
        assert "#f87171" in payload["htmlContent"]

    @pytest.mark.asyncio
    async def test_risk_color_unknown_fallback(self):
        """Niveau de risque inconnu → couleur grise par défaut."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_lead_report_email(
                email="lead@example.com",
                domain="example.com",
                pdf_bytes=b"pdf",
                score=50,
                risk_level="",
            )
        payload = mock_send.call_args[0][0]
        assert "#94a3b8" in payload["htmlContent"]


class TestSendWeeklyMonitoringDigest:
    """Tests for send_weekly_monitoring_digest()."""

    @pytest.mark.asyncio
    async def test_delegates_to_send(self):
        """La fonction appelle _send avec le bon sujet."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            result = await _svc.send_weekly_monitoring_digest(
                email="user@example.com",
                first_name="Alice",
                domains=[{
                    "domain": "example.com",
                    "score": 80,
                    "risk_level": "LOW",
                    "ssl_expiry_days": 45,
                    "last_scan_at": "01/03/2026",
                    "open_ports": ["443"],
                }],
            )
        assert result is True
        assert mock_send.called
        payload = mock_send.call_args[0][0]
        assert "Résumé hebdomadaire" in payload["subject"]

    @pytest.mark.asyncio
    async def test_subject_contains_domain_count(self):
        """Le sujet mentionne le nombre de domaines."""
        mock_send = AsyncMock(return_value=True)
        domains = [
            {"domain": "a.com", "score": 70, "risk_level": "MEDIUM",
             "ssl_expiry_days": None, "last_scan_at": "01/03/2026", "open_ports": []},
            {"domain": "b.com", "score": 50, "risk_level": "HIGH",
             "ssl_expiry_days": 7, "last_scan_at": "02/03/2026", "open_ports": ["80", "443"]},
        ]
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_weekly_monitoring_digest(
                email="user@example.com",
                first_name="Bob",
                domains=domains,
            )
        payload = mock_send.call_args[0][0]
        assert "2" in payload["subject"]

    @pytest.mark.asyncio
    async def test_no_api_key_returns_false(self):
        """Pas de clé API → False sans appel réseau."""
        original_key = _svc.BREVO_API_KEY
        try:
            _svc.BREVO_API_KEY = ""
            result = await _svc.send_weekly_monitoring_digest(
                email="user@example.com",
                first_name="Test",
                domains=[],
            )
        finally:
            _svc.BREVO_API_KEY = original_key
        assert result is False

    @pytest.mark.asyncio
    async def test_critical_domain_appears_first(self):
        """Les domaines CRITICAL/HIGH sont triés en premier."""
        mock_send = AsyncMock(return_value=True)
        domains = [
            {"domain": "good.com",     "score": 90, "risk_level": "LOW",
             "ssl_expiry_days": None, "last_scan_at": "01/03/2026", "open_ports": []},
            {"domain": "bad.com",      "score": 20, "risk_level": "CRITICAL",
             "ssl_expiry_days": None, "last_scan_at": "01/03/2026", "open_ports": []},
        ]
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_weekly_monitoring_digest(
                email="user@example.com",
                first_name="User",
                domains=domains,
            )
        payload = mock_send.call_args[0][0]
        html = payload["htmlContent"]
        # CRITICAL domain should appear before the LOW domain in the HTML
        assert html.index("bad.com") < html.index("good.com")

    @pytest.mark.asyncio
    async def test_ssl_warning_shown_for_expiring_certs(self):
        """Un SSL expirant dans moins de 14j affiche un avertissement."""
        mock_send = AsyncMock(return_value=True)
        with patch.object(_svc, "_send", mock_send):
            await _svc.send_weekly_monitoring_digest(
                email="user@example.com",
                first_name="User",
                domains=[{
                    "domain": "expiring.com",
                    "score": 60,
                    "risk_level": "MEDIUM",
                    "ssl_expiry_days": 5,
                    "last_scan_at": "01/03/2026",
                    "open_ports": [],
                }],
            )
        html = mock_send.call_args[0][0]["htmlContent"]
        assert "5j" in html
        assert "#ef4444" in html  # couleur d'alerte rouge


# ─────────────────────────────────────────────────────────────────────────────
# send_slack_alert / send_teams_alert
# ─────────────────────────────────────────────────────────────────────────────

class TestSendSlackAlert:
    """Tests pour send_slack_alert()."""

    @pytest.mark.asyncio
    async def test_slack_alert_returns_true_on_200(self):
        """HTTP 200 de Slack → True."""
        from app.services.brevo_service import send_slack_alert
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=AsyncMock(return_value=mock_resp)))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            result = await send_slack_alert("https://hooks.slack.com/services/T/B/abc", "example.com", 45, "HIGH", ["SSL expiré"])
        assert result is True

    @pytest.mark.asyncio
    async def test_slack_alert_returns_false_on_non_200(self):
        """HTTP 400 de Slack → False."""
        from app.services.brevo_service import send_slack_alert
        mock_resp = MagicMock()
        mock_resp.status_code = 400

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=AsyncMock(return_value=mock_resp)))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            result = await send_slack_alert("https://hooks.slack.com/services/T/B/abc", "example.com", 45, "HIGH", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_slack_alert_returns_false_on_exception(self):
        """Exception réseau → False (silencieux)."""
        from app.services.brevo_service import send_slack_alert

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=AsyncMock(side_effect=Exception("timeout"))))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            result = await send_slack_alert("https://hooks.slack.com/services/T/B/abc", "example.com", 45, "CRITICAL", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_slack_alert_empty_url_returns_false(self):
        """URL vide → False sans appel réseau."""
        from app.services.brevo_service import send_slack_alert
        result = await send_slack_alert("", "example.com", 45, "HIGH", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_slack_alert_payload_contains_domain(self):
        """Le payload envoyé à Slack contient le domaine."""
        from app.services.brevo_service import send_slack_alert
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        captured_payload = {}

        async def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=capture_post))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            await send_slack_alert("https://hooks.slack.com/services/T/B/abc", "test-domain.com", 55, "MEDIUM", ["Score bas"])

        payload_str = str(captured_payload)
        assert "test-domain.com" in payload_str


class TestSendTeamsAlert:
    """Tests pour send_teams_alert()."""

    @pytest.mark.asyncio
    async def test_teams_alert_returns_true_on_202(self):
        """HTTP 202 de Teams → True."""
        from app.services.brevo_service import send_teams_alert
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=AsyncMock(return_value=mock_resp)))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            result = await send_teams_alert("https://myco.webhook.office.com/webhookb2/abc", "example.com", 30, "CRITICAL", ["RDP exposé"])
        assert result is True

    @pytest.mark.asyncio
    async def test_teams_alert_empty_url_returns_false(self):
        """URL vide → False sans appel réseau."""
        from app.services.brevo_service import send_teams_alert
        result = await send_teams_alert("", "example.com", 30, "CRITICAL", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_teams_alert_returns_false_on_exception(self):
        """Exception réseau → False (silencieux)."""
        from app.services.brevo_service import send_teams_alert

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=AsyncMock(side_effect=Exception("conn refused"))))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            result = await send_teams_alert("https://myco.webhook.office.com/webhookb2/abc", "example.com", 30, "HIGH", [])
        assert result is False

    @pytest.mark.asyncio
    async def test_teams_alert_payload_contains_domain(self):
        """Le payload envoyé à Teams contient le domaine."""
        from app.services.brevo_service import send_teams_alert
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        captured_payload = {}

        async def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock(post=capture_post))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_ctx
            await send_teams_alert("https://myco.webhook.office.com/webhookb2/abc", "teams-test.com", 40, "HIGH", ["Port ouvert"])

        payload_str = str(captured_payload)
        assert "teams-test.com" in payload_str
