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
    TechExposureAuditor,
    ReputationAuditor,
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


# ═════════════════════════════════════════════════════════════════════════════
# TechExposureAuditor — Stack technique exposée
# ═════════════════════════════════════════════════════════════════════════════

class TestTechExposureAuditor:
    """
    _detect_tech_sync testé directement (méthode sync).
    http.client.HTTPSConnection / HTTPConnection mockés.
    """

    def _make_conn(self, body: bytes = b"", headers: list | None = None, status: int = 200) -> MagicMock:
        """Crée un faux objet connexion HTTP retournant body/headers/status."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.getheaders.return_value = headers or []
        mock_resp.status = status
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_resp
        return mock_conn

    def _run(self, body: bytes = b"", headers: list | None = None) -> list:
        """Lance _detect_tech_sync en mockant HTTPS (succès immédiat).
        Le second appel HTTPS (/wp-admin) lève une exception → jamais de HIGH ici.
        Utiliser side_effect explicite pour tester le scénario /wp-admin accessible.
        """
        auditor = TechExposureAuditor("example.com")
        conn_main = self._make_conn(body, headers)
        conn_wp_admin = MagicMock()
        conn_wp_admin.request.side_effect = ConnectionRefusedError("refused")
        with patch("http.client.HTTPSConnection", side_effect=[conn_main, conn_wp_admin]), \
             patch("http.client.HTTPConnection", return_value=MagicMock()):
            return auditor._detect_tech_sync()

    def test_no_body_returns_empty(self):
        """HTTPS et HTTP tous deux en erreur → liste vide."""
        auditor = TechExposureAuditor("example.com")
        err_conn = MagicMock()
        err_conn.request.side_effect = ConnectionRefusedError("refused")
        with patch("http.client.HTTPSConnection", return_value=err_conn), \
             patch("http.client.HTTPConnection", return_value=err_conn):
            findings = auditor._detect_tech_sync()
        assert findings == []

    def test_clean_page_no_findings(self):
        """Page sans marqueurs connus → aucun finding."""
        findings = self._run(b"<html><body>Hello World</body></html>")
        assert findings == []

    def test_wordpress_wp_content_marker(self):
        """Marqueur wp-content → finding MEDIUM, pénalité 5."""
        findings = self._run(b"<html><link href='/wp-content/themes/style.css'></html>")
        wp = [f for f in findings if "WordPress" in f.title]
        assert len(wp) == 1
        assert wp[0].severity == "MEDIUM"
        assert wp[0].penalty  == 5

    def test_wordpress_wp_json_marker(self):
        """Marqueur wp-json → WordPress détecté."""
        findings = self._run(b'<link rel="alternate" href="https://example.com/wp-json/">')
        wp = [f for f in findings if "WordPress" in f.title]
        assert len(wp) == 1

    def test_wordpress_literal_marker(self):
        """Mot 'wordpress' en minuscule dans le body → WordPress détecté."""
        findings = self._run(b"<meta name='generator' content='WordPress 6.4'>")
        wp = [f for f in findings if "WordPress" in f.title]
        assert len(wp) == 1

    def test_wordpress_admin_accessible_200_adds_high(self):
        """/wp-admin retourne 200 → MEDIUM WordPress + HIGH wp-admin."""
        auditor = TechExposureAuditor("example.com")
        conn1 = self._make_conn(b"<html>wp-content/themes</html>")   # page principale
        conn2 = self._make_conn(b"", status=200)                      # /wp-admin
        with patch("http.client.HTTPSConnection", side_effect=[conn1, conn2]):
            findings = auditor._detect_tech_sync()
        severities = {f.severity for f in findings}
        assert "MEDIUM" in severities
        assert "HIGH"   in severities
        assert len(findings) == 2

    def test_wordpress_admin_redirect_302_adds_high(self):
        """/wp-admin retournant 302 → HIGH finding quand même."""
        auditor = TechExposureAuditor("example.com")
        conn1 = self._make_conn(b"wordpress detected")
        conn2 = self._make_conn(b"", status=302)
        with patch("http.client.HTTPSConnection", side_effect=[conn1, conn2]):
            findings = auditor._detect_tech_sync()
        high = [f for f in findings if f.severity == "HIGH"]
        assert len(high) == 1

    def test_wordpress_admin_404_no_high_finding(self):
        """/wp-admin retournant 404 → seulement le finding MEDIUM."""
        auditor = TechExposureAuditor("example.com")
        conn1 = self._make_conn(b"<html>wp-content/themes</html>")
        conn2 = self._make_conn(b"", status=404)
        with patch("http.client.HTTPSConnection", side_effect=[conn1, conn2]):
            findings = auditor._detect_tech_sync()
        assert all(f.severity != "HIGH" for f in findings)
        assert len(findings) == 1

    def test_drupal_in_body_medium(self):
        """Marqueur 'drupal' dans le body → finding MEDIUM, pénalité 4."""
        findings = self._run(b"<html><meta name='Generator' content='Drupal 9'></html>")
        drupal = [f for f in findings if "Drupal" in f.title]
        assert len(drupal) == 1
        assert drupal[0].severity == "MEDIUM"
        assert drupal[0].penalty  == 4

    def test_php_version_exposed_low(self):
        """X-Powered-By: PHP/7.4.33 → finding LOW, pénalité 4."""
        findings = self._run(b"<html></html>", headers=[("X-Powered-By", "PHP/7.4.33")])
        php = [f for f in findings if "PHP" in f.title]
        assert len(php) == 1
        assert php[0].severity == "LOW"
        assert php[0].penalty  == 4

    def test_php_without_version_number_no_finding(self):
        """X-Powered-By: PHP sans numéro de version → pas de finding."""
        findings = self._run(b"<html></html>", headers=[("X-Powered-By", "PHP")])
        php = [f for f in findings if "PHP" in f.title]
        assert len(php) == 0

    def test_https_fail_fallback_http_detects_markers(self):
        """HTTPS échoue → fallback sur HTTP → marqueurs quand même détectés."""
        auditor = TechExposureAuditor("example.com")
        err_conn = MagicMock()
        err_conn.request.side_effect = ConnectionRefusedError("refused")
        http_conn = self._make_conn(b"<html>drupal cms site</html>")
        with patch("http.client.HTTPSConnection", return_value=err_conn), \
             patch("http.client.HTTPConnection", return_value=http_conn):
            findings = auditor._detect_tech_sync()
        assert any("Drupal" in f.title for f in findings)

    def test_wordpress_and_php_combined(self):
        """wp-content + X-Powered-By: PHP/8.1.0 → MEDIUM WordPress + LOW PHP."""
        findings = self._run(
            b"<html><link href='/wp-content/style.css'></html>",
            headers=[("X-Powered-By", "PHP/8.1.0")],
        )
        severities = [f.severity for f in findings]
        assert "MEDIUM" in severities
        assert "LOW"    in severities


# ═════════════════════════════════════════════════════════════════════════════
# ReputationAuditor — DNSBL
# ═════════════════════════════════════════════════════════════════════════════

class TestReputationAuditor:
    """
    _resolve_ip  → socket.gethostbyname mocké
    _check_dnsbl → dns.resolver.Resolver mocké
    audit()      → méthode async, testée directement (asyncio_mode=auto)
    """

    async def test_clean_ip_info_finding_no_penalty(self):
        """IP non blacklistée → finding INFO, pénalité 0."""
        auditor = ReputationAuditor("example.com")
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = Exception("NXDOMAIN")
        with patch("app.extra_checks.socket.gethostbyname", return_value="93.184.216.34"), \
             patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            findings = await auditor.audit()
        assert len(findings) == 1
        assert findings[0].severity == "INFO"
        assert findings[0].penalty  == 0

    async def test_blacklisted_ip_critical_penalty_20(self):
        """IP blacklistée dans tous les DNSBL → finding CRITICAL, pénalité 20."""
        auditor = ReputationAuditor("example.com")
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]   # trouvé partout
        with patch("app.extra_checks.socket.gethostbyname", return_value="1.2.3.4"), \
             patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            findings = await auditor.audit()
        assert len(findings) == 1
        assert findings[0].severity == "CRITICAL"
        assert findings[0].penalty  == 20

    async def test_blacklisted_finding_lists_all_servers(self):
        """Tous les DNSBL dans les détails techniques quand tous matchent."""
        auditor = ReputationAuditor("example.com")
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]
        with patch("app.extra_checks.socket.gethostbyname", return_value="1.2.3.4"), \
             patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            findings = await auditor.audit()
        detail = findings[0].technical_detail
        for dnsbl in ReputationAuditor.DNSBL_SERVERS:
            assert dnsbl in detail

    async def test_blacklisted_by_one_server_still_critical(self):
        """IP blacklistée par 1 seul DNSBL → CRITICAL quand même."""
        auditor = ReputationAuditor("example.com")
        call_count = [0]

        def selective_resolve(query, record_type):
            call_count[0] += 1
            if call_count[0] == 1:
                return [MagicMock()]          # premier DNSBL : blacklisté
            raise Exception("NXDOMAIN")       # les suivants : propres

        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = selective_resolve
        with patch("app.extra_checks.socket.gethostbyname", return_value="5.6.7.8"), \
             patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            findings = await auditor.audit()
        assert findings[0].severity == "CRITICAL"
        assert "zen.spamhaus.org" in findings[0].technical_detail

    async def test_dns_resolution_failure_returns_empty(self):
        """socket.gethostbyname échoue → findings vides (pas de crash)."""
        auditor = ReputationAuditor("example.com")
        with patch("app.extra_checks.socket.gethostbyname", side_effect=Exception("No such host")):
            findings = await auditor.audit()
        assert findings == []

    def test_resolve_ip_returns_string(self):
        """_resolve_ip → string IP si l'hôte est résolu."""
        auditor = ReputationAuditor("example.com")
        with patch("app.extra_checks.socket.gethostbyname", return_value="93.184.216.34"):
            ip = auditor._resolve_ip()
        assert ip == "93.184.216.34"

    def test_resolve_ip_returns_none_on_error(self):
        """_resolve_ip → None si le domaine est introuvable."""
        auditor = ReputationAuditor("example.com")
        with patch("app.extra_checks.socket.gethostbyname", side_effect=Exception("No such host")):
            ip = auditor._resolve_ip()
        assert ip is None

    def test_check_dnsbl_reverses_ip_octets(self):
        """_check_dnsbl inverse les octets de l'IP pour la requête DNS."""
        auditor = ReputationAuditor("example.com")
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = Exception("NXDOMAIN")
        with patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            auditor._check_dnsbl("1.2.3.4")
        first_query = mock_resolver.resolve.call_args_list[0][0][0]
        assert first_query.startswith("4.3.2.1.")

    def test_check_dnsbl_returns_empty_when_clean(self):
        """_check_dnsbl → [] si l'IP n'est dans aucune liste noire."""
        auditor = ReputationAuditor("example.com")
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = Exception("NXDOMAIN")
        with patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            result = auditor._check_dnsbl("1.2.3.4")
        assert result == []

    def test_check_dnsbl_returns_matching_server_names(self):
        """_check_dnsbl → liste des noms de DNSBL où l'IP est trouvée."""
        auditor = ReputationAuditor("example.com")
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [MagicMock()]   # toujours trouvé
        with patch("app.extra_checks.dns.resolver.Resolver", return_value=mock_resolver):
            result = auditor._check_dnsbl("1.2.3.4")
        assert len(result) == len(ReputationAuditor.DNSBL_SERVERS)
        for server in ReputationAuditor.DNSBL_SERVERS:
            assert server in result
