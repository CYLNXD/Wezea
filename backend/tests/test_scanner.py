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
