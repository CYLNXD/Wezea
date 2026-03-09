"""
Tests unitaires — app/breach_checks.py
Pure logique : aucun réseau réel (urllib.request.urlopen mocké).
"""
import json
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import MagicMock, patch, patch as mock_patch

import pytest

from app.breach_checks import BreachAuditor


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(data: dict | None, status: int = 200):
    """Construit un mock urllib response context manager."""
    mock_resp = MagicMock()
    if data is not None:
        mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _http_error(code: int):
    import urllib.error
    err = urllib.error.HTTPError(url="", code=code, msg="", hdrs=None, fp=None)
    return err


def _run(domain: str = "example.com", side_effect=None, return_value=None, api_key: str = "test-key"):
    """Lance l'audit de manière synchrone avec urllib mocké.

    Par défaut, injecte une clé HIBP fictive pour éviter le court-circuit no_api_key.
    Passer api_key="" pour tester le comportement sans clé.
    """
    import asyncio
    auditor = BreachAuditor(domain)
    env_patch = patch.dict("os.environ", {"HIBP_API_KEY": api_key})
    with env_patch, patch("urllib.request.urlopen") as mock_open:
        if side_effect is not None:
            mock_open.side_effect = side_effect
        elif return_value is not None:
            mock_open.return_value = return_value
        findings = asyncio.run(auditor.audit())
    return findings, auditor.get_details()


# ─────────────────────────────────────────────────────────────────────────────
# TestBreachRootDomain
# ─────────────────────────────────────────────────────────────────────────────

class TestBreachRootDomain:
    def test_subdomain_uses_root(self):
        auditor = BreachAuditor("sub.example.com")
        assert auditor._root_domain() == "example.com"

    def test_simple_domain_unchanged(self):
        auditor = BreachAuditor("example.com")
        assert auditor._root_domain() == "example.com"

    def test_deep_subdomain_uses_root(self):
        auditor = BreachAuditor("a.b.c.example.com")
        assert auditor._root_domain() == "example.com"

    def test_single_label_unchanged(self):
        auditor = BreachAuditor("localhost")
        assert auditor._root_domain() == "localhost"


# ─────────────────────────────────────────────────────────────────────────────
# TestBreachClean — domaine propre (404)
# ─────────────────────────────────────────────────────────────────────────────

class TestBreachClean:
    def test_404_returns_no_findings(self):
        findings, details = _run(side_effect=_http_error(404))
        assert findings == []

    def test_404_sets_status_clean(self):
        _, details = _run(side_effect=_http_error(404))
        assert details.get("status") == "clean"

    def test_404_breach_count_zero(self):
        _, details = _run(side_effect=_http_error(404))
        assert details.get("breach_count") == 0

    def test_empty_response_is_clean(self):
        resp = _make_response({})
        findings, details = _run(return_value=resp)
        assert findings == []
        assert details.get("status") == "clean"


# ─────────────────────────────────────────────────────────────────────────────
# TestBreachFound — domaine dans des fuites
# ─────────────────────────────────────────────────────────────────────────────

class TestBreachFound:
    def test_one_breach_is_high(self):
        resp = _make_response({"Adobe": ["user@example.com"]})
        findings, _ = _run(return_value=resp)
        assert len(findings) == 1
        assert findings[0].severity == "HIGH"
        assert findings[0].penalty == 20

    def test_three_breaches_is_critical(self):
        resp = _make_response({
            "Adobe": ["a@x.com"],
            "LinkedIn": ["b@x.com"],
            "Dropbox": ["c@x.com"],
        })
        findings, _ = _run(return_value=resp)
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert findings[0].penalty == 30

    def test_breach_names_in_technical_detail(self):
        resp = _make_response({"Adobe": ["a@x.com"], "LinkedIn": ["b@x.com"]})
        findings, _ = _run(return_value=resp)
        assert "Adobe" in findings[0].technical_detail
        assert "LinkedIn" in findings[0].technical_detail

    def test_more_than_5_names_truncated_in_detail(self):
        data = {f"Breach{i}": [f"u{i}@x.com"] for i in range(7)}
        resp = _make_response(data)
        findings, details = _run(return_value=resp)
        assert "…" in findings[0].technical_detail
        assert len(details["breach_names"]) <= 10

    def test_details_dict_complete(self):
        resp = _make_response({"Adobe": ["a@x.com"], "LinkedIn": ["b@x.com"]})
        _, details = _run(return_value=resp)
        assert details["status"] == "breached"
        assert details["breach_count"] == 2
        assert "Adobe" in details["breach_names"]

    def test_category_is_fuites(self):
        resp = _make_response({"Adobe": ["a@x.com"]})
        findings, _ = _run(return_value=resp)
        assert findings[0].category == "Fuites de données"


# ─────────────────────────────────────────────────────────────────────────────
# TestBreachSilent — erreurs réseau silencieuses
# ─────────────────────────────────────────────────────────────────────────────

class TestBreachSilent:
    def test_timeout_returns_no_findings(self):
        import socket
        findings, details = _run(side_effect=socket.timeout("timed out"))
        assert findings == []
        assert details == {}

    def test_network_error_returns_no_findings(self):
        import urllib.error
        findings, details = _run(
            side_effect=urllib.error.URLError("Network unreachable")
        )
        assert findings == []
        assert details == {}

    def test_other_http_error_returns_no_findings(self):
        """Un 500 de HIBP ne doit pas pénaliser le score."""
        findings, details = _run(side_effect=_http_error(500))
        assert findings == []
        assert details == {}


# ─────────────────────────────────────────────────────────────────────────────
# TestBreachNoApiKey — comportement sans clé HIBP configurée
# ─────────────────────────────────────────────────────────────────────────────

class TestBreachNoApiKey:
    def test_no_key_returns_no_findings(self):
        """Sans HIBP_API_KEY, aucun finding (pas de pénalité)."""
        findings, _ = _run(api_key="")
        assert findings == []

    def test_no_key_sets_status_no_api_key(self):
        """Sans clé, le status indique no_api_key."""
        _, details = _run(api_key="")
        assert details.get("status") == "no_api_key"

    def test_no_key_does_not_call_urlopen(self):
        """Sans clé, l'URL HIBP n'est jamais appelée."""
        import asyncio
        auditor = BreachAuditor("example.com")
        with patch.dict("os.environ", {"HIBP_API_KEY": ""}), \
             patch("urllib.request.urlopen") as mock_open:
            asyncio.run(auditor.audit())
        mock_open.assert_not_called()

    def test_401_sets_status_no_api_key(self):
        """Un 401 (clé invalide/expirée) retourne no_api_key sans pénalité."""
        findings, details = _run(side_effect=_http_error(401))
        assert findings == []
        assert details.get("status") == "no_api_key"

    def test_key_is_sent_as_header(self):
        """La clé API est envoyée dans le header hibp-api-key."""
        import asyncio
        auditor = BreachAuditor("example.com")
        captured_headers = {}
        def capture_request(req, **kwargs):
            captured_headers.update(req.headers)
            raise _http_error(404)  # domaine propre
        with patch.dict("os.environ", {"HIBP_API_KEY": "my-secret-key"}), \
             patch("urllib.request.urlopen", side_effect=capture_request):
            asyncio.run(auditor.audit())
        # urllib normalise les noms de headers en Title-Case
        assert captured_headers.get("Hibp-api-key") == "my-secret-key"
