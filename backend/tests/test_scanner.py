"""
Tests : scanner.py — Moteur d'audit de sécurité
-------------------------------------------------
ScoreEngine  — calcul score + niveaux de risque (logique pure, aucun mock)
DNSAuditor   — SPF + DMARC (_check_spf / _check_dmarc directs, dns.resolver mocké)
SSLAuditor   — certificats SSL / TLS (socket + ssl mockés)
PortAuditor  — ports critiques (_tcp_connect mocké, _detect_shared_hosting mocké)
"""
from __future__ import annotations

import asyncio
import ssl
import socket
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import dns.exception
import dns.resolver as _dns_resolver
import pytest

from app.scanner import (
    DNSAuditor,
    SSLAuditor,
    PortAuditor,
    ScoreEngine,
    Finding,
    PENALTY_TABLE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _finding(penalty: int, severity: str = "HIGH") -> Finding:
    return Finding(
        category         = "Test",
        severity         = severity,
        title            = "Test finding",
        technical_detail = "",
        plain_explanation= "",
        penalty          = penalty,
        recommendation   = "",
    )


def _dns_records(*texts: str) -> list:
    """Crée des mock DNS records dont .to_text() retourne le texte donné."""
    records = []
    for text in texts:
        r = MagicMock()
        r.to_text.return_value = text
        records.append(r)
    return records


def _mock_resolver_for(records: list, raises=None) -> MagicMock:
    """Crée un mock Resolver.resolve() → records (ou lève raises)."""
    resolver = MagicMock()
    if raises:
        resolver.resolve.side_effect = raises
    else:
        resolver.resolve.return_value = records
    return resolver


def _cert_expiry_str(days: int) -> str:
    """Génère une date d'expiration SSL ± N jours depuis maintenant."""
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%b %d %H:%M:%S %Y GMT")


def _mock_tls_sock(days_left: int = 90, tls_version: str = "TLSv1.3") -> tuple:
    """Crée un mock socket TLS + retourne la date expiry utilisée."""
    expire_str = _cert_expiry_str(days_left)
    sock = MagicMock()
    sock.getpeercert.return_value = {
        "notAfter": expire_str,
        "issuer":   [[["CN", "Let's Encrypt"]]],
        "subject":  [[["CN", "example.com"]]],
    }
    sock.version.return_value = tls_version
    sock.cipher.return_value  = ("AES256-GCM-SHA384", "TLSv1.3", 256)
    return sock, expire_str


# ═════════════════════════════════════════════════════════════════════════════
# ScoreEngine — logique pure
# ═════════════════════════════════════════════════════════════════════════════

class TestScoreEngine:

    def test_no_findings_score_100_low_risk(self):
        score, risk = ScoreEngine.compute([])
        assert score == 100
        assert risk  == "LOW"

    def test_penalty_deducted_correctly(self):
        score, _ = ScoreEngine.compute([_finding(PENALTY_TABLE["spf_missing"])])  # -15
        assert score == 85

    def test_multiple_penalties_cumulate(self):
        findings = [
            _finding(PENALTY_TABLE["dmarc_missing"]),   # -20
            _finding(PENALTY_TABLE["ssl_unreachable"]),  # -30
        ]
        score, _ = ScoreEngine.compute(findings)
        assert score == 50

    def test_score_clamped_at_zero(self):
        score, _ = ScoreEngine.compute([_finding(200)])
        assert score == 0

    def test_info_finding_zero_penalty_no_impact(self):
        score, _ = ScoreEngine.compute([_finding(0)])
        assert score == 100

    def test_risk_low_at_80(self):
        _, risk = ScoreEngine.compute([_finding(20)])   # score = 80
        assert risk == "LOW"

    def test_risk_medium_at_79(self):
        _, risk = ScoreEngine.compute([_finding(21)])   # score = 79
        assert risk == "MEDIUM"

    def test_risk_medium_at_60(self):
        _, risk = ScoreEngine.compute([_finding(40)])   # score = 60
        assert risk == "MEDIUM"

    def test_risk_high_at_59(self):
        _, risk = ScoreEngine.compute([_finding(41)])   # score = 59
        assert risk == "HIGH"

    def test_risk_high_at_40(self):
        _, risk = ScoreEngine.compute([_finding(60)])   # score = 40
        assert risk == "HIGH"

    def test_risk_critical_at_39(self):
        _, risk = ScoreEngine.compute([_finding(61)])   # score = 39
        assert risk == "CRITICAL"

    def test_risk_critical_at_zero(self):
        _, risk = ScoreEngine.compute([_finding(200)])  # score = 0
        assert risk == "CRITICAL"


# ═════════════════════════════════════════════════════════════════════════════
# DNSAuditor — SPF
# ═════════════════════════════════════════════════════════════════════════════

class TestDNSAuditorSPF:
    """Teste _check_spf directement (appel synchrone, dns.resolver mocké)."""

    def _run(self, resolver_mock: MagicMock) -> DNSAuditor:
        auditor = DNSAuditor("example.com")
        with patch("app.scanner.dns.resolver.Resolver", return_value=resolver_mock):
            auditor._check_spf()
        return auditor

    def test_spf_missing_creates_high_finding(self):
        """Aucun enregistrement SPF dans les TXT → finding HIGH."""
        resolver = _mock_resolver_for(_dns_records('"v=other nonsense"'))
        auditor  = self._run(resolver)
        spf = [f for f in auditor._findings if "SPF" in f.title]
        assert len(spf) == 1
        assert spf[0].severity == "HIGH"
        assert spf[0].penalty  == PENALTY_TABLE["spf_missing"]
        assert auditor._details["spf"]["status"] == "missing"

    def test_spf_permissive_plus_all_creates_high_finding(self):
        """+all → SPF mal configuré (tout le monde autorisé à envoyer)."""
        resolver = _mock_resolver_for(_dns_records('"v=spf1 +all"'))
        auditor  = self._run(resolver)
        spf = [f for f in auditor._findings if "SPF" in f.title]
        assert len(spf) == 1
        assert spf[0].severity == "HIGH"
        assert spf[0].penalty  == PENALTY_TABLE["spf_misconfigured"]
        assert auditor._details["spf"]["status"] == "misconfigured"

    def test_spf_tilde_all_valid_no_finding(self):
        """~all (soft fail) → SPF correctement configuré."""
        resolver = _mock_resolver_for(
            _dns_records('"v=spf1 include:_spf.google.com ~all"')
        )
        auditor = self._run(resolver)
        assert not any("SPF" in f.title for f in auditor._findings)
        assert auditor._details["spf"]["status"] == "ok"

    def test_spf_minus_all_strict_no_finding(self):
        """-all (rejet strict) → configuration optimale, aucun finding."""
        resolver = _mock_resolver_for(
            _dns_records('"v=spf1 include:_spf.google.com -all"')
        )
        auditor = self._run(resolver)
        assert not any("SPF" in f.title for f in auditor._findings)

    def test_spf_dns_error_is_graceful(self):
        """Erreur DNS → aucun crash, statut error dans les détails."""
        resolver = _mock_resolver_for([], raises=Exception("DNS timeout"))
        auditor  = self._run(resolver)
        assert auditor._details.get("spf", {}).get("status") == "error"

    def test_spf_no_txt_at_all_creates_missing_finding(self):
        """Aucun enregistrement TXT → finding SPF manquant."""
        resolver = _mock_resolver_for(_dns_records())  # liste vide
        auditor  = self._run(resolver)
        assert auditor._details["spf"]["status"] == "missing"


# ═════════════════════════════════════════════════════════════════════════════
# DNSAuditor — DMARC
# ═════════════════════════════════════════════════════════════════════════════

class TestDNSAuditorDMARC:
    """Teste _check_dmarc directement (appel synchrone, dns.resolver mocké)."""

    def _run(self, resolver_mock: MagicMock) -> DNSAuditor:
        auditor = DNSAuditor("example.com")
        with patch("app.scanner.dns.resolver.Resolver", return_value=resolver_mock):
            auditor._check_dmarc()
        return auditor

    def test_dmarc_nxdomain_creates_high_finding(self):
        """_dmarc.domain n'existe pas → finding HIGH."""
        resolver = _mock_resolver_for([], raises=_dns_resolver.NXDOMAIN())
        auditor  = self._run(resolver)
        dmarc = [f for f in auditor._findings if "DMARC" in f.title]
        assert len(dmarc) == 1
        assert dmarc[0].severity == "HIGH"
        assert dmarc[0].penalty  == PENALTY_TABLE["dmarc_missing"]
        assert auditor._details["dmarc"]["status"] == "missing"

    def test_dmarc_missing_from_txt_response(self):
        """TXT présent mais aucun enregistrement v=DMARC1 → manquant."""
        resolver = _mock_resolver_for(_dns_records('"v=OTHER; p=reject"'))
        auditor  = self._run(resolver)
        assert auditor._details["dmarc"]["status"] == "missing"

    def test_dmarc_policy_none_creates_medium_finding(self):
        """p=none → mode surveillance seulement, finding MEDIUM."""
        resolver = _mock_resolver_for(
            _dns_records('"v=DMARC1; p=none; rua=mailto:d@example.com"')
        )
        auditor = self._run(resolver)
        dmarc = [f for f in auditor._findings if "DMARC" in f.title or "dmarc" in f.title.lower()]
        assert len(dmarc) == 1
        assert dmarc[0].severity == "MEDIUM"
        assert dmarc[0].penalty  == 8

    def test_dmarc_policy_quarantine_no_finding(self):
        """p=quarantine → protection active, aucun finding."""
        resolver = _mock_resolver_for(
            _dns_records('"v=DMARC1; p=quarantine; rua=mailto:d@example.com"')
        )
        auditor = self._run(resolver)
        assert not any("DMARC" in f.title for f in auditor._findings)
        assert auditor._details["dmarc"]["policy"] == "quarantine"

    def test_dmarc_policy_reject_optimal_no_finding(self):
        """p=reject → configuration maximale, aucun finding."""
        resolver = _mock_resolver_for(
            _dns_records('"v=DMARC1; p=reject; rua=mailto:d@example.com"')
        )
        auditor = self._run(resolver)
        assert not any("DMARC" in f.title for f in auditor._findings)
        assert auditor._details["dmarc"]["policy"] == "reject"

    def test_dmarc_generic_error_is_graceful(self):
        """Exception générique non-NXDOMAIN → aucun crash, statut error."""
        resolver = _mock_resolver_for([], raises=dns.exception.DNSException("timeout"))
        auditor  = self._run(resolver)
        assert auditor._details.get("dmarc", {}).get("status") == "error"


# ═════════════════════════════════════════════════════════════════════════════
# SSLAuditor — Certificats SSL / TLS
# ═════════════════════════════════════════════════════════════════════════════

class TestSSLAuditor:
    """Teste _check_ssl directement (socket + ssl entièrement mockés)."""

    def _run(self, tls_sock_mock=None, create_conn_raises=None,
             wrap_raises=None) -> SSLAuditor:
        auditor  = SSLAuditor("example.com")
        mock_ctx = MagicMock()

        if wrap_raises:
            mock_ctx.wrap_socket.side_effect = wrap_raises
        elif tls_sock_mock:
            mock_ctx.wrap_socket.return_value.__enter__.return_value = tls_sock_mock

        conn_mock = MagicMock() if not create_conn_raises else None
        with patch("ssl.create_default_context", return_value=mock_ctx), \
             patch("socket.create_connection",
                   side_effect=create_conn_raises if create_conn_raises else None,
                   return_value=conn_mock):
            auditor._check_ssl()
        return auditor

    def test_valid_cert_no_findings(self):
        """Certificat valide 90 jours, TLS 1.3 → aucun finding."""
        tls_sock, _ = _mock_tls_sock(days_left=90, tls_version="TLSv1.3")
        auditor = self._run(tls_sock)
        assert len(auditor._findings) == 0
        assert auditor._details["status"]      == "valid"
        assert auditor._details["tls_version"] == "TLSv1.3"

    def test_expired_cert_creates_critical_finding(self):
        """Certificat expiré → CRITICAL, pénalité ssl_invalid."""
        tls_sock, _ = _mock_tls_sock(days_left=-5)
        auditor = self._run(tls_sock)
        ssl_findings = [f for f in auditor._findings if f.category == "SSL / HTTPS"]
        assert len(ssl_findings) >= 1
        assert ssl_findings[0].severity == "CRITICAL"
        assert ssl_findings[0].penalty  == PENALTY_TABLE["ssl_invalid"]

    def test_cert_expiring_soon_creates_medium_warning(self):
        """Certificat expirant dans 15 jours (< 30j) → MEDIUM, pénalité 0."""
        tls_sock, _ = _mock_tls_sock(days_left=15)
        auditor = self._run(tls_sock)
        expiry_findings = [
            f for f in auditor._findings
            if "expire" in f.title.lower() or "expir" in f.title.lower()
        ]
        assert len(expiry_findings) == 1
        assert expiry_findings[0].severity == "MEDIUM"
        assert expiry_findings[0].penalty  == 0  # avertissement, pas une pénalité

    def test_cert_valid_long_expiry_not_warned(self):
        """Certificat expirant dans 60 jours (> 30j) → aucun avertissement."""
        tls_sock, _ = _mock_tls_sock(days_left=60)
        auditor = self._run(tls_sock)
        expiry_findings = [
            f for f in auditor._findings
            if "expire" in f.title.lower() or "expir" in f.title.lower()
        ]
        assert len(expiry_findings) == 0

    def test_deprecated_tls_version_creates_high_finding(self):
        """TLSv1.1 (déprécié RFC 8996) → finding HIGH, pénalité tls_old_version."""
        tls_sock, _ = _mock_tls_sock(days_left=90, tls_version="TLSv1.1")
        auditor = self._run(tls_sock)
        tls_findings = [
            f for f in auditor._findings
            if "TLS" in f.title or "tls" in f.title.lower()
        ]
        assert len(tls_findings) >= 1
        assert tls_findings[0].severity == "HIGH"
        assert tls_findings[0].penalty  == PENALTY_TABLE["tls_old_version"]

    def test_tls_1_0_also_deprecated(self):
        """TLSv1.0 → également déprécié → finding HIGH."""
        tls_sock, _ = _mock_tls_sock(days_left=90, tls_version="TLSv1")
        auditor = self._run(tls_sock)
        assert any(f.penalty == PENALTY_TABLE["tls_old_version"] for f in auditor._findings)

    def test_ssl_cert_verification_error_creates_critical(self):
        """SSLCertVerificationError (certificat auto-signé / invalide) → CRITICAL."""
        auditor = self._run(wrap_raises=ssl.SSLCertVerificationError("self-signed cert"))
        assert len(auditor._findings) == 1
        assert auditor._findings[0].severity == "CRITICAL"
        assert auditor._findings[0].penalty  == PENALTY_TABLE["ssl_invalid"]
        assert auditor._details["status"]    == "invalid_cert"

    def test_connection_refused_creates_critical(self):
        """Connexion refusée (port 443 fermé) → CRITICAL, pénalité ssl_unreachable."""
        auditor = self._run(create_conn_raises=ConnectionRefusedError("refused"))
        assert len(auditor._findings) == 1
        assert auditor._findings[0].severity == "CRITICAL"
        assert auditor._findings[0].penalty  == PENALTY_TABLE["ssl_unreachable"]
        assert auditor._details["status"]    == "unreachable"

    def test_socket_timeout_creates_critical(self):
        """Timeout de connexion → CRITICAL."""
        auditor = self._run(create_conn_raises=socket.timeout("timed out"))
        assert auditor._details.get("status") in ("unreachable", "invalid_cert")
        assert len(auditor._findings) >= 1
        assert auditor._findings[0].severity == "CRITICAL"

    def test_details_populated_correctly(self):
        """Vérifie le contenu complet de _details pour un cert valide."""
        tls_sock, _ = _mock_tls_sock(days_left=90, tls_version="TLSv1.3")
        auditor = self._run(tls_sock)
        d = auditor._details
        assert d["status"]      == "valid"
        assert d["tls_version"] == "TLSv1.3"
        assert d["days_left"]   == pytest.approx(90, abs=1)
        assert d["cipher"]      == "AES256-GCM-SHA384"
        assert d["bits"]        == 256


# ═════════════════════════════════════════════════════════════════════════════
# PortAuditor — Ports critiques
# ═════════════════════════════════════════════════════════════════════════════

class TestPortAuditor:
    """
    _tcp_connect est mocké sur l'instance (patch.object).
    _detect_shared_hosting est mocké au niveau module.
    """

    async def _audit(self, open_ports: set[int],
                     is_shared: bool = False, provider: str = "") -> PortAuditor:
        auditor = PortAuditor("example.com")

        def mock_tcp_connect(port: int) -> bool:
            return port in open_ports

        with patch.object(auditor, "_tcp_connect", side_effect=mock_tcp_connect), \
             patch("app.scanner._detect_shared_hosting", return_value=(is_shared, provider)):
            await auditor.audit()
        return auditor

    async def test_all_ports_closed_no_penalized_findings(self):
        """Tous les ports fermés → aucun finding pénalisé."""
        auditor = await self._audit(open_ports=set())
        penalized = [f for f in auditor._findings if f.penalty > 0]
        assert len(penalized) == 0

    async def test_rdp_port_3389_creates_critical(self):
        """Port 3389 (RDP) ouvert → CRITICAL, pénalité rdp_smb."""
        auditor = await self._audit(open_ports={3389})
        rdp = [f for f in auditor._findings if f.severity == "CRITICAL"]
        assert len(rdp) >= 1
        assert rdp[0].penalty == PENALTY_TABLE["rdp_smb"]

    async def test_smb_port_445_creates_critical(self):
        """Port 445 (SMB) ouvert → CRITICAL, pénalité rdp_smb."""
        auditor = await self._audit(open_ports={445})
        smb = [f for f in auditor._findings if f.severity == "CRITICAL"]
        assert len(smb) >= 1
        assert smb[0].penalty == PENALTY_TABLE["rdp_smb"]

    async def test_rdp_and_smb_grouped_in_one_finding(self):
        """RDP + SMB ouverts simultanément → UN seul finding (groupé)."""
        auditor = await self._audit(open_ports={3389, 445})
        rdp_smb = [f for f in auditor._findings if f.penalty == PENALTY_TABLE["rdp_smb"]]
        assert len(rdp_smb) == 1  # ils sont groupés en un seul finding

    async def test_mysql_port_3306_creates_critical(self):
        """Port 3306 (MySQL) ouvert → CRITICAL, pénalité database."""
        auditor = await self._audit(open_ports={3306})
        db = [f for f in auditor._findings if f.penalty == PENALTY_TABLE["database"]]
        assert len(db) >= 1

    async def test_postgresql_port_5432_creates_critical(self):
        """Port 5432 (PostgreSQL) ouvert → CRITICAL, pénalité database."""
        auditor = await self._audit(open_ports={5432})
        db = [f for f in auditor._findings if f.penalty == PENALTY_TABLE["database"]]
        assert len(db) >= 1

    async def test_ftp_port_21_creates_high_finding(self):
        """Port 21 (FTP) ouvert → HIGH, pénalité ftp_telnet."""
        auditor = await self._audit(open_ports={21})
        ftp = [f for f in auditor._findings if f.penalty == PENALTY_TABLE["ftp_telnet"]]
        assert len(ftp) >= 1

    async def test_ssh_port_22_creates_info_no_penalty(self):
        """Port 22 (SSH) ouvert → finding INFO, pénalité 0."""
        auditor = await self._audit(open_ports={22})
        ssh = [f for f in auditor._findings if f.severity == "INFO" and "SSH" in f.title]
        assert len(ssh) == 1
        assert ssh[0].penalty == 0

    async def test_http_https_ports_no_penalized_finding(self):
        """Ports 80 et 443 ouverts → pas de finding pénalisé (ports normaux)."""
        auditor = await self._audit(open_ports={80, 443})
        penalized = [f for f in auditor._findings if f.penalty > 0]
        assert len(penalized) == 0

    async def test_shared_hosting_critical_port_generates_info_not_critical(self):
        """
        Sur hébergement mutualisé, les ports critiques ouverts génèrent
        un finding INFO sans pénalité (l'utilisateur ne contrôle pas le firewall).
        """
        auditor = await self._audit(open_ports={3389, 445, 3306},
                                    is_shared=True, provider="OVH")
        critical = [f for f in auditor._findings if f.severity == "CRITICAL"]
        info     = [f for f in auditor._findings if f.severity == "INFO"]
        assert len(critical) == 0
        assert len(info) >= 1
        assert all(f.penalty == 0 for f in info)

    async def test_port_details_stored_for_all_monitored_ports(self):
        """Les détails de tous les ports monitorés sont présents dans _details."""
        auditor = await self._audit(open_ports=set())
        from app.scanner import MONITORED_PORTS
        for port in MONITORED_PORTS:
            assert port in auditor._details, f"Port {port} absent de _details"


# =============================================================================
# AuditManager — orchestrateur de scans
# =============================================================================

from contextlib import ExitStack
from unittest.mock import AsyncMock


def _mock_auditor(findings=None, details=None):
    """Crée un auditeur mock avec audit() AsyncMock et get_details() stub."""
    m = MagicMock()
    m.audit      = AsyncMock(return_value=findings or [])
    m.get_details = MagicMock(return_value=details or {})
    return m


def _all_auditor_patches(
    dns_mock=None, ssl_mock=None, port_mock=None,
    header_mock=None, email_mock=None, tech_mock=None, rep_mock=None,
    sub_mock=None, vuln_mock=None,
):
    """
    Retourne une liste de patch() pour tous les auditeurs.
    Chaque auditeur peut être remplacé par un mock personnalisé.
    """
    return [
        patch("app.scanner.DNSAuditor",               return_value=dns_mock    or _mock_auditor()),
        patch("app.scanner.SSLAuditor",               return_value=ssl_mock    or _mock_auditor()),
        patch("app.scanner.PortAuditor",              return_value=port_mock   or _mock_auditor()),
        patch("app.extra_checks.HttpHeaderAuditor",   return_value=header_mock or _mock_auditor()),
        patch("app.extra_checks.EmailSecurityAuditor",return_value=email_mock  or _mock_auditor()),
        patch("app.extra_checks.TechExposureAuditor", return_value=tech_mock   or _mock_auditor()),
        patch("app.extra_checks.ReputationAuditor",   return_value=rep_mock    or _mock_auditor()),
        patch("app.advanced_checks.SubdomainAuditor", return_value=sub_mock    or _mock_auditor()),
        patch("app.advanced_checks.VulnVersionAuditor",return_value=vuln_mock  or _mock_auditor()),
    ]


class TestAuditManagerInit:
    """Tests pour AuditManager.__init__ (sélection des auditeurs)."""

    def test_free_plan_no_premium_auditors(self):
        """Plan free → 7 auditeurs de base, 0 premium."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
        assert len(manager._auditors)         == 7
        assert len(manager._premium_auditors) == 0
        assert manager._subdomain_auditor     is None
        assert manager._vuln_auditor          is None

    def test_starter_plan_has_premium_auditors(self):
        """Plan starter → 7 de base + 2 premium (subdomain + vuln)."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="starter")
        assert len(manager._auditors)         == 7
        assert len(manager._premium_auditors) == 2
        assert manager._subdomain_auditor     is not None
        assert manager._vuln_auditor          is not None

    def test_pro_plan_has_premium_auditors(self):
        """Plan pro → même comportement que starter."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="pro")
        assert len(manager._premium_auditors) == 2

    def test_domain_lowercased_and_stripped(self):
        """Le domaine est normalisé en minuscules sans espaces."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("  EXAMPLE.COM  ", plan="free")
        assert manager.domain == "example.com"

    def test_checks_config_excludes_disabled_checks(self):
        """checks_config={dns: False} → DNSAuditor exclu de _auditors."""
        from app.scanner import AuditManager
        dns_cls = MagicMock(return_value=_mock_auditor())
        with ExitStack() as stack:
            patches = _all_auditor_patches(dns_mock=_mock_auditor())
            patches[0] = patch("app.scanner.DNSAuditor", dns_cls)
            for p in patches:
                stack.enter_context(p)
            manager = AuditManager(
                "example.com", plan="free",
                checks_config={"dns": False, "ssl": True, "ports": True,
                               "headers": True, "email": True, "tech": True,
                               "reputation": True},
            )
        # DNS exclu → 6 auditeurs au lieu de 7
        assert len(manager._auditors) == 6
        # La classe DNS n'a pas été utilisée dans _auditors
        dns_cls.assert_called_once()  # instancié mais pas inclus

    def test_no_checks_config_uses_all_auditors(self):
        """Sans checks_config → les 7 auditeurs sont inclus."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com")
        assert len(manager._auditors) == 7


class TestAuditManagerRun:
    """Tests pour AuditManager.run() (orchestration + ScanResult)."""

    @pytest.mark.asyncio
    async def test_run_returns_scan_result_fields(self):
        """run() retourne un ScanResult avec tous les champs attendus."""
        from app.scanner import AuditManager, ScanResult
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        assert isinstance(result, ScanResult)
        assert result.domain           == "example.com"
        assert isinstance(result.security_score, int)
        assert result.risk_level       in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert isinstance(result.findings, list)
        assert isinstance(result.scan_duration_ms, int)
        assert result.scan_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_run_aggregates_findings_from_all_auditors(self):
        """run() fusionne les findings de tous les auditeurs."""
        from app.scanner import AuditManager, Finding
        f1 = Finding(category="DNS & Mail", severity="HIGH",   title="DNS issue",  technical_detail="", plain_explanation="", penalty=15, recommendation="Fix DNS")
        f2 = Finding(category="SSL",        severity="MEDIUM", title="SSL issue",  technical_detail="", plain_explanation="", penalty=10, recommendation="Fix SSL")
        f3 = Finding(category="Ports",      severity="HIGH",   title="Port issue", technical_detail="", plain_explanation="", penalty=12, recommendation="Fix port")
        dns_mock  = _mock_auditor(findings=[f1])
        ssl_mock  = _mock_auditor(findings=[f2])
        port_mock = _mock_auditor(findings=[f3])
        with ExitStack() as stack:
            for p in _all_auditor_patches(
                dns_mock=dns_mock, ssl_mock=ssl_mock, port_mock=port_mock
            ):
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        assert len(result.findings) == 3
        titles = [f.title for f in result.findings]
        assert "DNS issue"  in titles
        assert "SSL issue"  in titles
        assert "Port issue" in titles

    @pytest.mark.asyncio
    async def test_run_findings_sorted_by_penalty_descending(self):
        """Les findings sont triés par penalty décroissant."""
        from app.scanner import AuditManager, Finding
        f_low  = Finding(category="DNS", severity="LOW",    title="Low",  technical_detail="", plain_explanation="", penalty=3,  recommendation="")
        f_high = Finding(category="SSL", severity="HIGH",   title="High", technical_detail="", plain_explanation="", penalty=15, recommendation="")
        f_med  = Finding(category="P",   severity="MEDIUM", title="Med",  technical_detail="", plain_explanation="", penalty=8,  recommendation="")
        with ExitStack() as stack:
            for p in _all_auditor_patches(
                dns_mock=_mock_auditor(findings=[f_low]),
                ssl_mock=_mock_auditor(findings=[f_high]),
                port_mock=_mock_auditor(findings=[f_med]),
            ):
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        assert result.findings[0].penalty >= result.findings[1].penalty
        assert result.findings[1].penalty >= result.findings[2].penalty

    @pytest.mark.asyncio
    async def test_run_exception_in_one_auditor_does_not_stop_others(self):
        """Si un auditeur lève une exception, les autres continuent."""
        from app.scanner import AuditManager, Finding
        bad_auditor = MagicMock()
        bad_auditor.audit = AsyncMock(side_effect=RuntimeError("réseau KO"))
        bad_auditor.get_details = MagicMock(return_value={})
        good_finding = Finding(category="SSL", severity="LOW", title="OK finding", technical_detail="", plain_explanation="", penalty=5, recommendation="")
        with ExitStack() as stack:
            for p in _all_auditor_patches(
                dns_mock=bad_auditor,
                ssl_mock=_mock_auditor(findings=[good_finding]),
            ):
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        # Exception ignorée par gather(return_exceptions=True) → finding SSL présent
        assert any(f.title == "OK finding" for f in result.findings)

    @pytest.mark.asyncio
    async def test_run_no_premium_details_for_free_plan(self):
        """Plan free → subdomain_details et vuln_details vides."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        assert result.subdomain_details == {}
        assert result.vuln_details      == {}

    @pytest.mark.asyncio
    async def test_run_premium_details_populated_for_starter(self):
        """Plan starter → subdomain_details et vuln_details remplis."""
        from app.scanner import AuditManager
        sub_mock  = _mock_auditor(details={"total_found": 3, "subdomains": ["a", "b", "c"]})
        vuln_mock = _mock_auditor(details={"detected_stack": ["PHP/7.4"]})
        with ExitStack() as stack:
            for p in _all_auditor_patches(sub_mock=sub_mock, vuln_mock=vuln_mock):
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="starter")
            result  = await manager.run()
        assert result.subdomain_details == {"total_found": 3, "subdomains": ["a", "b", "c"]}
        assert result.vuln_details      == {"detected_stack": ["PHP/7.4"]}

    @pytest.mark.asyncio
    async def test_run_score_computed_from_findings(self):
        """Le score est calculé à partir des pénalités des findings."""
        from app.scanner import AuditManager, Finding
        # Un finding penalty=20 → score = 80
        f = Finding(category="DNS", severity="HIGH", title="Big issue", technical_detail="", plain_explanation="", penalty=20, recommendation="")
        with ExitStack() as stack:
            for p in _all_auditor_patches(dns_mock=_mock_auditor(findings=[f])):
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        assert result.security_score == 80

    @pytest.mark.asyncio
    async def test_run_empty_auditors_perfect_score(self):
        """Aucun finding → score 100 et risk_level LOW."""
        from app.scanner import AuditManager
        with ExitStack() as stack:
            for p in _all_auditor_patches():
                stack.enter_context(p)
            manager = AuditManager("example.com", plan="free")
            result  = await manager.run()
        assert result.security_score == 100
        assert result.risk_level     == "LOW"


# =============================================================================
# Finding.to_dict() — line 94
# ScanResult.to_dict() — lines 122-123
# BaseAuditor.get_details() — lines 166-167
# =============================================================================

class TestFindingToDict:
    """Finding.to_dict() doit retourner tous les champs."""

    def test_to_dict_returns_all_fields(self):
        from app.scanner import Finding
        f = Finding(
            category="DNS",
            severity="HIGH",
            title="SPF manquant",
            technical_detail="Aucun enregistrement SPF trouvé",
            plain_explanation="Sans SPF, des spammeurs peuvent usurper votre domaine.",
            penalty=15,
            recommendation="Ajoutez un enregistrement TXT SPF à votre DNS.",
        )
        d = f.to_dict()
        assert d["category"]          == "DNS"
        assert d["severity"]          == "HIGH"
        assert d["title"]             == "SPF manquant"
        assert d["technical_detail"]  == "Aucun enregistrement SPF trouvé"
        assert d["plain_explanation"] == "Sans SPF, des spammeurs peuvent usurper votre domaine."
        assert d["penalty"]           == 15
        assert d["recommendation"]    == "Ajoutez un enregistrement TXT SPF à votre DNS."


class TestScanResultToDict:
    """ScanResult.to_dict() doit sérialiser tous les champs."""

    def test_to_dict_basic_fields(self):
        from app.scanner import ScanResult, Finding
        f = Finding(
            category="SSL",
            severity="CRITICAL",
            title="Certificat expiré",
            technical_detail="CN=example.com, expiry=-5d",
            plain_explanation="Le certificat SSL a expiré.",
            penalty=40,
            recommendation="Renouvelez votre certificat SSL.",
        )
        result = ScanResult(
            domain="example.com",
            scanned_at="2026-03-06T12:00:00Z",
            security_score=60,
            risk_level="HIGH",
            findings=[f],
            dns_details={"spf": {"status": "ok"}},
            ssl_details={"status": "expired"},
            port_details={443: {"open": True}},
        )
        d = result.to_dict()
        assert d["domain"]          == "example.com"
        assert d["security_score"]  == 60
        assert d["risk_level"]      == "HIGH"
        assert len(d["findings"])   == 1
        assert d["findings"][0]["severity"] == "CRITICAL"
        assert d["dns_details"]     == {"spf": {"status": "ok"}}
        assert "443" in d["port_details"]   # int keys → str


class TestBaseAuditorGetDetails:
    """BaseAuditor.get_details() doit retourner _details."""

    def test_get_details_returns_internal_dict(self):
        from app.scanner import DNSAuditor
        auditor = DNSAuditor("example.com")
        auditor._details["spf"] = {"status": "ok"}
        details = auditor.get_details()
        assert details == {"spf": {"status": "ok"}}
        assert details is auditor._details  # même objet


# =============================================================================
# DNSAuditor.audit() — lines 177-182
# SSLAuditor.audit() — lines 361-364
# =============================================================================

class TestDNSAuditorAuditMethod:
    """Appel de la méthode audit() complète (appelle _check_spf + _check_dmarc)."""

    @pytest.mark.asyncio
    async def test_audit_calls_both_checks_and_returns_findings(self):
        from app.scanner import DNSAuditor
        auditor = DNSAuditor("example.com")
        with patch.object(auditor, "_check_spf"),  \
             patch.object(auditor, "_check_dmarc"):
            findings = await auditor.audit()
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_audit_returns_same_list_as_internal_findings(self):
        from app.scanner import DNSAuditor, Finding
        auditor = DNSAuditor("example.com")
        sentinel = Finding(
            category="DNS", severity="INFO", title="OK",
            technical_detail="", plain_explanation="", penalty=0, recommendation="",
        )
        def _inject_finding():
            auditor._findings.append(sentinel)

        with patch.object(auditor, "_check_spf", side_effect=_inject_finding), \
             patch.object(auditor, "_check_dmarc"):
            findings = await auditor.audit()
        assert sentinel in findings


class TestSSLAuditorAuditMethod:
    """Appel de la méthode audit() complète (appelle _check_ssl)."""

    @pytest.mark.asyncio
    async def test_audit_calls_check_ssl_and_returns_findings(self):
        from app.scanner import SSLAuditor
        auditor = SSLAuditor("example.com")
        with patch.object(auditor, "_check_ssl"):
            findings = await auditor.audit()
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_audit_returns_findings_from_check_ssl(self):
        from app.scanner import SSLAuditor, Finding
        auditor = SSLAuditor("example.com")
        sentinel = Finding(
            category="SSL", severity="CRITICAL", title="Expiré",
            technical_detail="", plain_explanation="", penalty=40, recommendation="",
        )
        def _inject():
            auditor._findings.append(sentinel)

        with patch.object(auditor, "_check_ssl", side_effect=_inject):
            findings = await auditor.audit()
        assert sentinel in findings


# =============================================================================
# _detect_shared_hosting() — lines 589-601
# =============================================================================

class TestDetectSharedHosting:

    def test_known_shared_hosting_ptr_returns_true(self):
        """PTR du domaine contient un pattern OVH → hébergement mutualisé détecté."""
        from app.scanner import _detect_shared_hosting
        with patch("app.scanner.socket.gethostbyname", return_value="1.2.3.4"), \
             patch("app.scanner.socket.gethostbyaddr", return_value=("hosting.ovh.net", [], [])):
            is_shared, provider = _detect_shared_hosting("example.com")
        assert is_shared is True
        assert provider  != ""

    def test_unknown_ptr_returns_false(self):
        """PTR ne correspond à aucun pattern → pas mutualisé."""
        from app.scanner import _detect_shared_hosting
        with patch("app.scanner.socket.gethostbyname", return_value="1.2.3.4"), \
             patch("app.scanner.socket.gethostbyaddr", return_value=("dedicated.myserver.com", [], [])):
            is_shared, provider = _detect_shared_hosting("example.com")
        assert is_shared is False
        assert provider  == ""

    def test_ptr_lookup_fails_returns_empty_string(self):
        """gethostbyaddr lève une exception → ptr_host="" → no match."""
        from app.scanner import _detect_shared_hosting
        with patch("app.scanner.socket.gethostbyname", return_value="1.2.3.4"), \
             patch("app.scanner.socket.gethostbyaddr", side_effect=Exception("PTR timeout")):
            is_shared, provider = _detect_shared_hosting("example.com")
        assert is_shared is False

    def test_dns_resolution_fails_returns_false(self):
        """gethostbyname lève une exception → (False, '')."""
        from app.scanner import _detect_shared_hosting
        with patch("app.scanner.socket.gethostbyname", side_effect=Exception("NXDOMAIN")):
            is_shared, provider = _detect_shared_hosting("nonexistent.invalid")
        assert is_shared is False
        assert provider  == ""


# =============================================================================
# PortAuditor._check_port() — asyncio.TimeoutError (lines 709-711)
# PortAuditor._tcp_connect() — lines 718-728
# =============================================================================

class TestPortAuditorLowLevel:

    @pytest.mark.asyncio
    async def test_check_port_timeout_returns_closed(self):
        """asyncio.TimeoutError dans _check_port → port marqué fermé."""
        from app.scanner import PortAuditor, MONITORED_PORTS
        auditor = PortAuditor("example.com")
        port = next(iter(MONITORED_PORTS))
        meta = MONITORED_PORTS[port]
        with patch("app.scanner.asyncio.wait_for",
                   side_effect=asyncio.TimeoutError()):
            result = await auditor._check_port(port, meta)
        assert result[port]["open"] is False

    @pytest.mark.asyncio
    async def test_check_port_generic_exception_returns_closed(self):
        """Exception quelconque dans _check_port → port marqué fermé."""
        from app.scanner import PortAuditor, MONITORED_PORTS
        auditor = PortAuditor("example.com")
        port = next(iter(MONITORED_PORTS))
        meta = MONITORED_PORTS[port]
        with patch("app.scanner.asyncio.wait_for",
                   side_effect=OSError("connection refused")):
            result = await auditor._check_port(port, meta)
        assert result[port]["open"] is False

    def test_tcp_connect_returns_true_on_success(self):
        """_tcp_connect: connexion réussie (connect_ex=0) → True."""
        from app.scanner import PortAuditor
        auditor = PortAuditor("example.com")
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        with patch("app.scanner.socket.socket", return_value=mock_sock):
            result = auditor._tcp_connect(443)
        assert result is True
        mock_sock.close.assert_called_once()

    def test_tcp_connect_returns_false_on_refused(self):
        """_tcp_connect: connexion refusée (connect_ex=111) → False."""
        from app.scanner import PortAuditor
        auditor = PortAuditor("example.com")
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 111
        with patch("app.scanner.socket.socket", return_value=mock_sock):
            result = auditor._tcp_connect(443)
        assert result is False
        mock_sock.close.assert_called_once()

    def test_tcp_connect_exception_returns_false(self):
        """_tcp_connect: exception → False, socket toujours fermé."""
        from app.scanner import PortAuditor
        auditor = PortAuditor("example.com")
        mock_sock = MagicMock()
        mock_sock.connect_ex.side_effect = OSError("network error")
        with patch("app.scanner.socket.socket", return_value=mock_sock):
            result = auditor._tcp_connect(443)
        assert result is False
        mock_sock.close.assert_called_once()

    def test_tcp_connect_uses_resolved_ip_if_available(self):
        """_tcp_connect utilise _resolved_ip quand défini."""
        from app.scanner import PortAuditor
        auditor = PortAuditor("example.com")
        auditor._resolved_ip = "1.2.3.4"
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        with patch("app.scanner.socket.socket", return_value=mock_sock):
            result = auditor._tcp_connect(80)
        assert result is True
        # connect_ex appelé avec l'IP pré-résolue, pas le domaine
        mock_sock.connect_ex.assert_called_once_with(("1.2.3.4", 80))
