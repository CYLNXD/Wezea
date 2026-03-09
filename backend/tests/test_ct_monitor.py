"""
Tests unitaires — app/ct_monitor.py
Zéro réseau réel : urllib.request.urlopen est mocké.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from app.ct_monitor import (
    CertTransparencyAuditor,
    CertRecord,
    _KNOWN_CA_KEYWORDS,
    RECENT_URGENT_DAYS,
    RECENT_WARN_DAYS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cert(
    common_name: str = "example.com",
    name_value:  str = "example.com",
    issuer_name: str = "O=Let's Encrypt, CN=R3",
    days_ago:    int = 60,
) -> dict:
    """Crée un dict de certificat simulant la réponse crt.sh."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    logged = dt.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "common_name":  common_name,
        "name_value":   name_value,
        "issuer_name":  issuer_name,
        "logged_at":    logged,
        "not_before":   logged,
        "not_after":    (dt + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _run(domain: str, certs: list[dict]) -> tuple[list, dict]:
    """Lance CertTransparencyAuditor avec une liste de certs mockée."""
    raw = json.dumps(certs).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = raw

    auditor = CertTransparencyAuditor(domain, "fr")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        asyncio.run(auditor.audit())
    return auditor._findings, auditor._details


def _run_error(domain: str) -> tuple[list, dict]:
    """Lance l'auditeur avec une erreur réseau."""
    import urllib.error
    auditor = CertTransparencyAuditor(domain, "fr")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        asyncio.run(auditor.audit())
    return auditor._findings, auditor._details


# ── Tests CertRecord ──────────────────────────────────────────────────────────

class TestCertRecord:
    def test_to_dict_keys(self):
        r = CertRecord(
            common_name="sub.example.com",
            name_value="sub.example.com",
            issuer="Let's Encrypt",
            logged_at="2025-01-01",
            not_before="2025-01-01",
            not_after="2025-04-01",
        )
        d = r.to_dict()
        assert set(d.keys()) == {"common_name", "name_value", "issuer", "logged_at", "not_before", "not_after"}

    def test_to_dict_values(self):
        r = CertRecord("x", "y", "z", "a", "b", "c")
        assert r.to_dict()["common_name"] == "x"
        assert r.to_dict()["issuer"] == "z"


# ── Tests utilitaires statiques ───────────────────────────────────────────────

class TestParseIssuer:
    def _parse(self, s: str) -> str:
        return CertTransparencyAuditor._parse_issuer(s)

    def test_extracts_O(self):
        assert self._parse("C=US, O=Let's Encrypt, CN=R3") == "Let's Encrypt"

    def test_extracts_CN_fallback(self):
        assert self._parse("CN=MyCA") == "MyCA"

    def test_empty_string(self):
        assert self._parse("") == ""

    def test_truncates_long_unknown(self):
        s = "X" * 100
        result = CertTransparencyAuditor._parse_issuer(s)
        assert len(result) <= 60


class TestParseDate:
    def _parse(self, s: str):
        return CertTransparencyAuditor._parse_date(s)

    def test_iso_format(self):
        dt = self._parse("2024-06-15T12:00:00")
        assert dt is not None
        assert dt.year == 2024 and dt.month == 6 and dt.day == 15

    def test_space_format(self):
        dt = self._parse("2024-06-15 12:00:00")
        assert dt is not None

    def test_date_only(self):
        dt = self._parse("2024-06-15")
        assert dt is not None
        assert dt.year == 2024

    def test_empty(self):
        assert self._parse("") is None

    def test_invalid(self):
        assert self._parse("not-a-date") is None


class TestIsKnownCA:
    def _check(self, s: str) -> bool:
        return CertTransparencyAuditor._is_known_ca(s)

    def test_letsencrypt_known(self):
        assert self._check("Let's Encrypt")

    def test_r3_known(self):
        assert self._check("R3")

    def test_digicert_known(self):
        assert self._check("DigiCert Inc")

    def test_unknown_ca(self):
        assert not self._check("ShadyCA Corp")

    def test_case_insensitive(self):
        assert self._check("LETSENCRYPT")


# ── Tests réseau en erreur ─────────────────────────────────────────────────────

class TestCtNetworkError:
    def test_network_error_no_findings(self):
        findings, _ = _run_error("example.com")
        assert findings == []

    def test_network_error_no_data_status(self):
        _, details = _run_error("example.com")
        assert details.get("status") == "no_data"
        assert details.get("total_found") == 0

    def test_empty_response_no_findings(self):
        findings, details = _run("example.com", [])
        assert findings == []
        assert details["status"] == "no_data"


# ── Tests avec certs normaux (CA connues) ──────────────────────────────────────

class TestCtCleanCerts:
    def test_old_certs_no_findings(self):
        """Certs anciens (>30j) d'une CA connue → 0 findings."""
        certs = [_make_cert(days_ago=90), _make_cert(days_ago=120)]
        findings, details = _run("example.com", certs)
        assert findings == []
        assert details["status"] == "certs_found"

    def test_details_total_found(self):
        certs = [_make_cert(days_ago=90)] * 5
        _, details = _run("example.com", certs)
        assert details["total_found"] == 5

    def test_details_issuers_populated(self):
        certs = [_make_cert(issuer_name="O=Let's Encrypt, CN=R3", days_ago=90)]
        _, details = _run("example.com", certs)
        assert len(details["issuers"]) > 0

    def test_details_wildcard_count(self):
        certs = [
            _make_cert(common_name="*.example.com", days_ago=90),
            _make_cert(days_ago=90),
        ]
        _, details = _run("example.com", certs)
        assert details["wildcard_count"] == 1

    def test_recent_7days_known_ca_info_finding(self):
        """Cert récent (<7j) d'une CA connue → INFO p=0."""
        certs = [_make_cert(issuer_name="O=Let's Encrypt, CN=R3", days_ago=1)]
        findings, _ = _run("example.com", certs)
        assert len(findings) == 1
        assert findings[0].severity == "INFO"
        assert findings[0].penalty == 0

    def test_recent_30days_no_finding_if_known(self):
        """Cert de 15j d'une CA connue → pas de finding MEDIUM."""
        certs = [_make_cert(issuer_name="O=DigiCert Inc, CN=DigiCert", days_ago=15)]
        findings, _ = _run("example.com", certs)
        # Peut être INFO mais pas MEDIUM (penalty>0)
        for f in findings:
            assert f.penalty == 0

    def test_high_volume_info_finding(self):
        """Plus de 100 certs (CA connues, anciens) → INFO p=0."""
        certs = [_make_cert(days_ago=60)] * 101
        findings, _ = _run("example.com", certs)
        assert len(findings) == 1
        assert findings[0].severity == "INFO"
        assert findings[0].penalty == 0


# ── Tests avec certs suspects ────────────────────────────────────────────────

class TestCtSuspiciousCerts:
    def test_recent_unknown_ca_medium_finding(self):
        """Cert <7j d'une CA inconnue → MEDIUM p=8."""
        certs = [_make_cert(
            issuer_name="O=ShadyCA Corp",
            days_ago=2,
        )]
        findings, _ = _run("example.com", certs)
        assert len(findings) == 1
        assert findings[0].severity == "MEDIUM"
        assert findings[0].penalty == 8

    def test_recent_unknown_ca_hit_count_in_title(self):
        """Le nombre de certs suspects apparaît dans le titre."""
        certs = [
            _make_cert(issuer_name="O=ShadyCA Corp", days_ago=1),
            _make_cert(issuer_name="O=AnotherBadCA", days_ago=3),
        ]
        findings, _ = _run("example.com", certs)
        assert "2" in findings[0].title

    def test_wildcard_unknown_ca_high_finding(self):
        """Wildcard cert récent (<30j) d'une CA inconnue → HIGH p=12."""
        certs = [_make_cert(
            common_name="*.example.com",
            name_value="*.example.com",
            issuer_name="O=ShadyCA Corp",
            days_ago=10,
        )]
        findings, _ = _run("example.com", certs)
        high = [f for f in findings if f.severity == "HIGH"]
        assert len(high) == 1
        assert high[0].penalty == 12

    def test_wildcard_known_ca_no_high_finding(self):
        """Wildcard cert d'une CA connue → pas de finding HIGH."""
        certs = [_make_cert(
            common_name="*.example.com",
            issuer_name="O=Let's Encrypt, CN=R3",
            days_ago=10,
        )]
        findings, _ = _run("example.com", certs)
        high = [f for f in findings if f.severity == "HIGH"]
        assert len(high) == 0

    def test_wildcard_unknown_ca_old_no_high_finding(self):
        """Wildcard cert d'une CA inconnue MAIS ancien (>30j) → pas de HIGH."""
        certs = [_make_cert(
            common_name="*.example.com",
            issuer_name="O=ShadyCA Corp",
            days_ago=45,
        )]
        findings, _ = _run("example.com", certs)
        high = [f for f in findings if f.severity == "HIGH"]
        assert len(high) == 0

    def test_finding_category_ct(self):
        certs = [_make_cert(issuer_name="O=ShadyCA Corp", days_ago=2)]
        findings, _ = _run("example.com", certs)
        assert findings[0].category == "Certificate Transparency"

    def test_finding_has_recommendation(self):
        certs = [_make_cert(issuer_name="O=ShadyCA Corp", days_ago=2)]
        findings, _ = _run("example.com", certs)
        assert findings[0].recommendation != ""


# ── Tests root domain ─────────────────────────────────────────────────────────

class TestCtRootDomain:
    def test_subdomain_uses_root(self):
        a = CertTransparencyAuditor("sub.example.com", "fr")
        assert a._root_domain() == "example.com"

    def test_root_unchanged(self):
        a = CertTransparencyAuditor("example.com", "fr")
        assert a._root_domain() == "example.com"

    def test_deep_subdomain(self):
        a = CertTransparencyAuditor("a.b.c.example.com", "fr")
        assert a._root_domain() == "example.com"


# ── Tests lang=en ─────────────────────────────────────────────────────────────

class TestCtLangEn:
    def test_en_finding_title_in_english(self):
        certs = [_make_cert(issuer_name="O=ShadyCA Corp", days_ago=1)]
        raw = json.dumps(certs).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = raw

        auditor = CertTransparencyAuditor("example.com", "en")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            asyncio.run(auditor.audit())
        assert auditor._findings
        # Titre en anglais contient "certificate" (pas "certificat")
        assert "certificate" in auditor._findings[0].title.lower()

    def test_info_finding_en(self):
        certs = [_make_cert(issuer_name="O=Let's Encrypt", days_ago=1)]
        raw = json.dumps(certs).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = raw

        auditor = CertTransparencyAuditor("example.com", "en")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            asyncio.run(auditor.audit())
        # Titre INFO en anglais
        assert "certificate" in auditor._findings[0].title.lower()
