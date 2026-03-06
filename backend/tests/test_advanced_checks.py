"""
Tests : advanced_checks.py + extra_checks.py
---------------------------------------------
_parse_version          — extraction tuple de version (logique pure)
_version_in_range       — test d'intervalle de version (logique pure)
VulnVersionAuditor      — détection versions vulnérables (HTTP mocké)
HttpHeaderAuditor       — en-têtes de sécurité HTTP (_fetch_headers_sync mocké)
EmailSecurityAuditor    — DKIM + MX (dns.resolver mocké)
"""
from __future__ import annotations

import asyncio
import http.client
from unittest.mock import MagicMock, patch

import dns.exception
import dns.resolver as _dns_resolver
import pytest

from app.advanced_checks import (
    _parse_version,
    _version_in_range,
    VulnVersionAuditor,
    KNOWN_VULNS,
)
from app.extra_checks import (
    HttpHeaderAuditor,
    EmailSecurityAuditor,
)


# ═════════════════════════════════════════════════════════════════════════════
# _parse_version — logique pure
# ═════════════════════════════════════════════════════════════════════════════

class TestParseVersion:

    def test_standard_three_part(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_two_part_patch_defaults_to_zero(self):
        assert _parse_version("2.4") == (2, 4, 0)

    def test_embedded_in_server_header(self):
        assert _parse_version("Apache/2.4.51") == (2, 4, 51)

    def test_embedded_in_php_string(self):
        assert _parse_version("PHP/7.4.33") == (7, 4, 33)

    def test_nginx_version(self):
        assert _parse_version("nginx/1.20.1") == (1, 20, 1)

    def test_invalid_string_returns_none(self):
        assert _parse_version("no-version-here") is None

    def test_empty_string_returns_none(self):
        assert _parse_version("") is None

    def test_major_only_no_match_returns_none(self):
        # "8" alone — no "x.y" pattern
        assert _parse_version("8") is None

    def test_iis_header(self):
        assert _parse_version("Microsoft-IIS/8.5") == (8, 5, 0)


# ═════════════════════════════════════════════════════════════════════════════
# _version_in_range — logique pure
# ═════════════════════════════════════════════════════════════════════════════

class TestVersionInRange:

    def test_version_within_bounds(self):
        assert _version_in_range((2, 4, 50), (2, 4, 49), (2, 4, 50)) is True

    def test_version_below_min(self):
        assert _version_in_range((2, 4, 48), (2, 4, 49), (2, 4, 50)) is False

    def test_version_above_max(self):
        assert _version_in_range((2, 4, 51), (2, 4, 49), (2, 4, 50)) is False

    def test_no_bounds_always_true(self):
        assert _version_in_range((99, 99, 99), None, None) is True

    def test_max_only_below(self):
        assert _version_in_range((7, 4, 33), None, (7, 4, 99)) is True

    def test_max_only_above(self):
        assert _version_in_range((8, 0, 0), None, (7, 4, 99)) is False

    def test_min_only_above(self):
        assert _version_in_range((8, 0, 5), (8, 0, 0), None) is True

    def test_min_only_below(self):
        assert _version_in_range((7, 4, 99), (8, 0, 0), None) is False

    def test_exact_min_boundary(self):
        assert _version_in_range((2, 4, 49), (2, 4, 49), (2, 4, 50)) is True

    def test_exact_max_boundary(self):
        assert _version_in_range((2, 4, 50), (2, 4, 49), (2, 4, 50)) is True


# ═════════════════════════════════════════════════════════════════════════════
# VulnVersionAuditor — détection de versions vulnérables
# ═════════════════════════════════════════════════════════════════════════════

class TestVulnVersionAuditor:
    """
    _check_versions_sync est appelé directement (contourne l'async executor).
    http.client.HTTPSConnection est mocké pour injecter des réponses HTTP.
    Note : _check_versions_sync RETOURNE les findings (pas self._findings).
    """

    def _run(self, headers: list[tuple[str, str]]) -> tuple[list, VulnVersionAuditor]:
        """Lance _check_versions_sync, retourne (findings, auditor)."""
        auditor   = VulnVersionAuditor("example.com")
        mock_conn = MagicMock()
        mock_resp = MagicMock()
        mock_resp.getheaders.return_value = headers
        mock_conn.getresponse.return_value = mock_resp

        with patch("http.client.HTTPSConnection", return_value=mock_conn):
            findings = auditor._check_versions_sync()
        return findings, auditor

    def test_php7_eol_creates_critical_finding(self):
        """PHP 7.4 est EOL depuis nov. 2022 → CRITICAL."""
        findings, _ = self._run([
            ("Server",       "Apache/2.4.58"),
            ("X-Powered-By", "PHP/7.4.33"),
        ])
        php = [f for f in findings if "PHP" in f.title]
        assert len(php) >= 1
        assert php[0].severity == "CRITICAL"
        assert php[0].penalty  == 30

    def test_php8_0_eol_creates_high_finding(self):
        """PHP 8.0 est EOL depuis nov. 2023 → HIGH."""
        findings, _ = self._run([("X-Powered-By", "PHP/8.0.28")])
        php = [f for f in findings if "PHP" in f.title]
        assert len(php) >= 1
        assert php[0].severity == "HIGH"

    def test_php8_2_current_no_finding(self):
        """PHP 8.2 n'est pas EOL → aucun finding PHP."""
        findings, _ = self._run([("X-Powered-By", "PHP/8.2.10")])
        php = [f for f in findings if "PHP" in f.title]
        assert len(php) == 0

    def test_apache_cve_2021_41773_creates_critical(self):
        """Apache 2.4.49 → CVE-2021-41773 path traversal (RCE) → CRITICAL."""
        findings, _ = self._run([("Server", "Apache/2.4.49")])
        apache = [f for f in findings if "APACHE" in f.title or "apache" in f.title.lower()]
        assert len(apache) >= 1
        assert apache[0].severity == "CRITICAL"

    def test_apache_modern_version_no_finding(self):
        """Apache 2.4.58 (récent, hors plage CVE) → aucun finding."""
        findings, _ = self._run([("Server", "Apache/2.4.58")])
        apache = [f for f in findings if "APACHE" in f.title]
        assert len(apache) == 0

    def test_nginx_vulnerable_creates_high_finding(self):
        """nginx 1.20.0 → CVE mémoire → HIGH."""
        findings, _ = self._run([("Server", "nginx/1.20.0")])
        nginx = [f for f in findings if "NGINX" in f.title]
        assert len(nginx) >= 1
        assert nginx[0].severity == "HIGH"

    def test_iis_8_5_creates_high_finding(self):
        """IIS 8.5 EOL → HIGH."""
        findings, _ = self._run([("Server", "Microsoft-IIS/8.5")])
        iis = [f for f in findings if "IIS" in f.title]
        assert len(iis) >= 1

    def test_no_server_header_no_findings(self):
        """Aucun en-tête → _check_versions_sync retourne []."""
        auditor   = VulnVersionAuditor("example.com")
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value.getheaders.return_value = []
        with patch("http.client.HTTPSConnection", return_value=mock_conn):
            result = auditor._check_versions_sync()
        assert result == []

    def test_connection_failure_no_crash(self):
        """Échec de connexion HTTP → retourne [] sans lever d'exception."""
        auditor = VulnVersionAuditor("example.com")
        with patch("http.client.HTTPSConnection", side_effect=Exception("refused")), \
             patch("http.client.HTTPConnection",  side_effect=Exception("refused")):
            result = auditor._check_versions_sync()
        assert result == []

    def test_detected_stack_stored_in_details(self):
        """La stack technique détectée est stockée dans _details."""
        _, auditor = self._run([
            ("Server",       "nginx/1.20.0"),
            ("X-Powered-By", "PHP/7.4.33"),
        ])
        assert "detected_stack" in auditor._details
        techs = [item["tech"] for item in auditor._details["detected_stack"]]
        assert "nginx" in techs
        assert "php" in techs


# ═════════════════════════════════════════════════════════════════════════════
# HttpHeaderAuditor — en-têtes de sécurité HTTP
# ═════════════════════════════════════════════════════════════════════════════

class TestHttpHeaderAuditor:
    """
    _fetch_headers_sync est mocké directement sur l'instance.
    """

    _ALL_SECURE_HEADERS = {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy":   "default-src 'self'",
        "X-Frame-Options":           "DENY",
        "X-Content-Type-Options":    "nosniff",
        "Referrer-Policy":           "strict-origin-when-cross-origin",
    }

    async def _audit(self, headers: dict | None) -> list:
        auditor = HttpHeaderAuditor("example.com")
        with patch.object(auditor, "_fetch_headers_sync", return_value=headers):
            return await auditor.audit()

    async def test_all_security_headers_present_no_findings(self):
        """Tous les en-têtes de sécurité présents → aucun finding."""
        findings = await self._audit(dict(self._ALL_SECURE_HEADERS))
        penalized = [f for f in findings if f.penalty > 0]
        assert len(penalized) == 0

    async def test_hsts_missing_creates_high_finding(self):
        """HSTS absent → finding HIGH, pénalité 10."""
        headers = {k: v for k, v in self._ALL_SECURE_HEADERS.items()
                   if k != "Strict-Transport-Security"}
        findings = await self._audit(headers)
        hsts = [f for f in findings if "HSTS" in f.title or "Strict-Transport" in f.title]
        assert len(hsts) == 1
        assert hsts[0].severity == "HIGH"
        assert hsts[0].penalty  == 10

    async def test_csp_missing_creates_medium_finding(self):
        """CSP absent → finding MEDIUM, pénalité 8."""
        headers = {k: v for k, v in self._ALL_SECURE_HEADERS.items()
                   if k != "Content-Security-Policy"}
        findings = await self._audit(headers)
        csp = [f for f in findings if "CSP" in f.title or "Content-Security" in f.title]
        assert len(csp) == 1
        assert csp[0].severity == "MEDIUM"
        assert csp[0].penalty  == 8

    async def test_server_version_exposed_creates_low_finding(self):
        """En-tête Server avec numéro de version → finding LOW."""
        headers = {**self._ALL_SECURE_HEADERS, "Server": "nginx/1.22.1"}
        findings = await self._audit(headers)
        server = [f for f in findings if "serveur" in f.title.lower() or "server" in f.title.lower()]
        assert len(server) >= 1
        assert server[0].severity == "LOW"

    async def test_x_powered_by_exposed_creates_low_finding(self):
        """X-Powered-By présent → finding LOW, pénalité 3."""
        headers = {**self._ALL_SECURE_HEADERS, "X-Powered-By": "PHP/8.2.0"}
        findings = await self._audit(headers)
        xpb = [f for f in findings if "Powered" in f.title or "powered" in f.title.lower()]
        assert len(xpb) == 1
        assert xpb[0].penalty == 3

    async def test_unreachable_host_returns_empty(self):
        """Hôte injoignable (_fetch_headers_sync retourne None) → [] findings."""
        findings = await self._audit(None)
        assert findings == []

    async def test_all_headers_missing_counts_all_findings(self):
        """Aucun en-tête de sécurité → au moins 5 findings (un par en-tête manquant)."""
        findings = await self._audit({})
        # 5 en-têtes manquants au minimum
        assert len(findings) >= 5


# ═════════════════════════════════════════════════════════════════════════════
# EmailSecurityAuditor — DKIM + MX
# ═════════════════════════════════════════════════════════════════════════════

class TestEmailSecurityAuditor:
    """
    _check_dkim et _check_mx sont testés via mocks DNS.
    """

    def _mock_resolver(self, found: bool):
        resolver = MagicMock()
        if found:
            resolver.resolve.return_value = [MagicMock()]
        else:
            resolver.resolve.side_effect = Exception("NXDOMAIN")
        return resolver

    async def test_dkim_found_no_finding(self):
        """Au moins un sélecteur DKIM trouvé → aucun finding DKIM."""
        auditor = EmailSecurityAuditor("example.com")
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=self._mock_resolver(found=True)):
            findings = await auditor.audit()
        dkim = [f for f in findings if "DKIM" in f.title]
        assert len(dkim) == 0

    async def test_dkim_not_found_creates_medium_finding(self):
        """Aucun sélecteur DKIM trouvé → finding MEDIUM, pénalité 8."""
        auditor = EmailSecurityAuditor("example.com")
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=self._mock_resolver(found=False)):
            findings = await auditor.audit()
        dkim = [f for f in findings if "DKIM" in f.title]
        assert len(dkim) == 1
        assert dkim[0].severity == "MEDIUM"
        assert dkim[0].penalty  == 8

    async def test_mx_found_no_finding(self):
        """Enregistrement MX présent → aucun finding MX."""
        auditor = EmailSecurityAuditor("example.com")
        # DKIM found (premier appel) + MX found (deuxième appel)
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=mock_resolver):
            findings = await auditor.audit()
        mx = [f for f in findings if "MX" in f.title]
        assert len(mx) == 0

    async def test_no_mx_creates_info_finding_no_penalty(self):
        """Aucun enregistrement MX → finding INFO, pénalité 0."""
        auditor = EmailSecurityAuditor("example.com")
        # Sélecteur DKIM trouvé (premier) mais MX absent (second)
        call_count = [0]

        def smart_resolve(domain, record_type):
            call_count[0] += 1
            if record_type == "MX":
                raise _dns_resolver.NXDOMAIN()
            return [MagicMock()]  # DKIM trouvé

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = smart_resolve
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=mock_resolver):
            findings = await auditor.audit()
        mx = [f for f in findings if "MX" in f.title]
        assert len(mx) == 1
        assert mx[0].severity == "INFO"
        assert mx[0].penalty  == 0

    def test_check_dkim_returns_true_when_found(self):
        """_check_dkim → True si un sélecteur répond."""
        auditor = EmailSecurityAuditor("example.com")
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=self._mock_resolver(found=True)):
            assert auditor._check_dkim() is True

    def test_check_dkim_returns_false_when_all_selectors_fail(self):
        """_check_dkim → False si tous les sélecteurs échouent."""
        auditor = EmailSecurityAuditor("example.com")
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=self._mock_resolver(found=False)):
            assert auditor._check_dkim() is False

    def test_check_mx_returns_true_when_found(self):
        """_check_mx → True si MX présent."""
        auditor = EmailSecurityAuditor("example.com")
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=self._mock_resolver(found=True)):
            assert auditor._check_mx() is True

    def test_check_mx_returns_false_when_absent(self):
        """_check_mx → False si aucun MX."""
        auditor = EmailSecurityAuditor("example.com")
        with patch("app.extra_checks.dns.resolver.Resolver",
                   return_value=self._mock_resolver(found=False)):
            assert auditor._check_mx() is False
