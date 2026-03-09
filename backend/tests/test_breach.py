"""
Tests unitaires — app/breach_checks.py
Pure logique : aucun réseau réel (urllib.request.urlopen mocké).
"""
import json
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import MagicMock, patch

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


def _run(domain: str = "example.com", side_effect=None, return_value=None):
    """Lance l'audit de manière synchrone avec urllib mocké."""
    import asyncio
    auditor = BreachAuditor(domain)
    with patch("urllib.request.urlopen") as mock_open:
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
