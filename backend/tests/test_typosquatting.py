"""
Tests unitaires — app/typosquatting_checks.py
Zéro réseau réel : socket.gethostbyname est mocké.
"""
from __future__ import annotations

import socket
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest

from app.typosquatting_checks import (
    TyposquattingAuditor,
    TyposquatHit,
    _generate_variants,
    COMMON_TLDS,
    HOMOGLYPHS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(domain: str, resolved: dict[str, str]) -> tuple[list, dict]:
    """
    Lance TyposquattingAuditor sur `domain`.
    `resolved` = {domain: ip} pour les domaines qui "répondent".
    Retourne (findings, details).
    """
    def fake_gethostbyname(d: str) -> str:
        if d in resolved:
            return resolved[d]
        raise socket.gaierror("NXDOMAIN")

    auditor = TyposquattingAuditor(domain, "fr")
    with patch("app.typosquatting_checks.socket.gethostbyname", side_effect=fake_gethostbyname):
        import asyncio
        asyncio.run(auditor.audit())
    return auditor._findings, auditor._details


# ── Tests _generate_variants ──────────────────────────────────────────────────

class TestGenerateVariants:
    def test_tld_swap_present(self):
        variants = [d for d, _ in _generate_variants("example.fr")]
        assert "example.com" in variants

    def test_original_domain_excluded(self):
        variants = [d for d, _ in _generate_variants("example.fr")]
        assert "example.fr" not in variants

    def test_missing_letter(self):
        variants = [d for d, _ in _generate_variants("google.fr")]
        assert "gogle.fr" in variants  # double 'g' removed

    def test_double_letter(self):
        variants = [d for d, _ in _generate_variants("test.fr")]
        assert "tesst.fr" in variants  # 's' doubled

    def test_transposition(self):
        variants = [d for d, _ in _generate_variants("login.fr")]
        assert "olgin.fr" in variants  # l↔o

    def test_homoglyph(self):
        # 'o' → '0'
        variants = [d for d, _ in _generate_variants("google.fr")]
        assert "g0ogle.fr" in variants

    def test_keyboard_neighbor(self):
        # 'g' neighbors include 'f' (qwerty)
        variants = [d for d, _ in _generate_variants("google.fr")]
        neighbor_variants = [d for d, t in _generate_variants("google.fr") if t == "keyboard"]
        assert len(neighbor_variants) > 0

    def test_max_variants_respected(self):
        from app.typosquatting_checks import MAX_VARIANTS
        variants = _generate_variants("verylongdomainname.com")
        assert len(variants) <= MAX_VARIANTS

    def test_no_dot_in_name_returns_empty(self):
        assert _generate_variants("nodot") == []

    def test_short_name_excluded(self):
        # name < 2 chars → empty
        assert _generate_variants("a.com") == []

    def test_variant_types_labeled_correctly(self):
        variants = dict(_generate_variants("test.fr"))
        # All types should be known
        known_types = {"tld", "missing", "double", "transposition", "homoglyph", "keyboard"}
        for vtype in variants.values():
            assert vtype in known_types

    def test_no_duplicate_domains(self):
        variants = [d for d, _ in _generate_variants("example.com")]
        assert len(variants) == len(set(variants))


# ── Tests TyposquatHit ─────────────────────────────────────────────────────────

class TestTyposquatHit:
    def test_to_dict_keys(self):
        hit = TyposquatHit(domain="examp1e.fr", variant_type="homoglyph", ip="1.2.3.4")
        d = hit.to_dict()
        assert d == {"domain": "examp1e.fr", "variant_type": "homoglyph", "ip": "1.2.3.4"}


# ── Tests résultats clean ─────────────────────────────────────────────────────

class TestTyposquattingClean:
    def test_no_hits_no_findings(self):
        findings, details = _run("wezea.fr", {})
        assert findings == []

    def test_clean_status(self):
        _, details = _run("wezea.fr", {})
        assert details.get("status") == "clean"

    def test_clean_hit_count_zero(self):
        _, details = _run("wezea.fr", {})
        assert details.get("hit_count") == 0

    def test_checked_positive(self):
        _, details = _run("wezea.fr", {})
        assert details.get("checked", 0) > 0


# ── Tests avec hits ───────────────────────────────────────────────────────────

class TestTyposquattingHits:
    def _one_hit_domain(self, base: str = "wezea.fr") -> str:
        """Retourne un domaine sosie valide pour `base`."""
        variants = _generate_variants(base)
        return variants[0][0]  # premier variant

    def test_one_hit_medium_severity(self):
        domain = "wezea.fr"
        hit_dom = self._one_hit_domain(domain)
        findings, _ = _run(domain, {hit_dom: "1.2.3.4"})
        assert len(findings) == 1
        assert findings[0].severity == "MEDIUM"

    def test_one_hit_penalty_8(self):
        domain = "wezea.fr"
        hit_dom = self._one_hit_domain(domain)
        findings, _ = _run(domain, {hit_dom: "1.2.3.4"})
        assert findings[0].penalty == 8

    def test_three_hits_high_severity(self):
        domain = "wezea.fr"
        variants = _generate_variants(domain)
        resolved = {v: "1.2.3.4" for v, _ in variants[:3]}
        findings, _ = _run(domain, resolved)
        assert len(findings) == 1
        assert findings[0].severity == "HIGH"
        assert findings[0].penalty == 15

    def test_five_hits_critical_severity(self):
        domain = "wezea.fr"
        variants = _generate_variants(domain)
        resolved = {v: "1.2.3.4" for v, _ in variants[:5]}
        findings, _ = _run(domain, resolved)
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert findings[0].penalty == 25

    def test_hits_in_details(self):
        domain = "wezea.fr"
        variants = _generate_variants(domain)
        hit_dom = variants[0][0]
        _, details = _run(domain, {hit_dom: "9.9.9.9"})
        assert details["status"] == "squatted"
        assert details["hit_count"] == 1
        hits = details["hits"]
        assert len(hits) == 1
        assert hits[0]["domain"] == hit_dom
        assert hits[0]["ip"] == "9.9.9.9"

    def test_examples_in_title(self):
        domain = "wezea.fr"
        variants = _generate_variants(domain)
        hit_dom = variants[0][0]
        findings, _ = _run(domain, {hit_dom: "1.2.3.4"})
        assert hit_dom in findings[0].technical_detail

    def test_finding_category(self):
        domain = "wezea.fr"
        hit_dom = self._one_hit_domain(domain)
        findings, _ = _run(domain, {hit_dom: "1.2.3.4"})
        assert findings[0].category == "Typosquatting"

    def test_recommendation_present(self):
        domain = "wezea.fr"
        hit_dom = self._one_hit_domain(domain)
        findings, _ = _run(domain, {hit_dom: "1.2.3.4"})
        assert findings[0].recommendation != ""


# ── Tests DNS error silencieux ────────────────────────────────────────────────

class TestTyposquattingDnsErrors:
    def test_timeout_is_silent(self):
        """Un timeout DNS ne doit pas lever d'exception."""
        def fake_timeout(d: str) -> str:
            raise OSError("timed out")

        auditor = TyposquattingAuditor("wezea.fr", "fr")
        with patch("app.typosquatting_checks.socket.gethostbyname", side_effect=fake_timeout):
            import asyncio
            asyncio.run(auditor.audit())
        assert auditor._findings == []

    def test_network_error_is_silent(self):
        """Toute erreur réseau doit être silencieuse."""
        def fake_error(d: str) -> str:
            raise Exception("network error")

        auditor = TyposquattingAuditor("wezea.fr", "fr")
        with patch("app.typosquatting_checks.socket.gethostbyname", side_effect=fake_error):
            import asyncio
            asyncio.run(auditor.audit())
        assert auditor._findings == []


# ── Tests root domain ─────────────────────────────────────────────────────────

class TestTyposquattingRootDomain:
    def test_subdomain_uses_root(self):
        """sub.example.com → on génère les variants de example.com."""
        auditor = TyposquattingAuditor("sub.example.com", "fr")
        root = auditor._root_domain()
        assert root == "example.com"

    def test_root_domain_unchanged(self):
        auditor = TyposquattingAuditor("example.com", "fr")
        assert auditor._root_domain() == "example.com"

    def test_subdomain_variants_based_on_root(self):
        """Les variantes générées pour sub.example.com doivent inclure example.fr."""
        auditor = TyposquattingAuditor("sub.example.com", "fr")
        root = auditor._root_domain()
        variants = [d for d, _ in _generate_variants(root)]
        assert "example.fr" in variants

    def test_en_lang_finding_title(self):
        """Lang=en → titre en anglais."""
        domain = "wezea.fr"
        variants = _generate_variants(domain)
        hit_dom = variants[0][0]

        def fake_gethostbyname(d: str) -> str:
            if d == hit_dom:
                return "1.2.3.4"
            raise socket.gaierror()

        auditor = TyposquattingAuditor(domain, "en")
        with patch("app.typosquatting_checks.socket.gethostbyname", side_effect=fake_gethostbyname):
            import asyncio
            asyncio.run(auditor.audit())
        assert "registered" in auditor._findings[0].title.lower()
