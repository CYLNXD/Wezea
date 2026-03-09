"""
Tests unitaires — app/compliance_mapper.py
Logique pure : aucun réseau, aucune DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from app.compliance_mapper import (
    ComplianceMapper,
    ComplianceResult,
    ArticleResult,
    NIS2_ARTICLES,
    RGPD_ARTICLES,
    SCORE_CONFORME,
    SCORE_PARTIEL,
    _pct_score,
    _overall_level,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

@dataclass
class _Finding:
    """Simulacre de Finding pour les tests (sans dépendance à scanner.py)."""
    category: str
    severity: str
    title:    str
    penalty:  int = 0


def _mapper() -> ComplianceMapper:
    return ComplianceMapper()


def _analyze(*findings: _Finding) -> ComplianceResult:
    return _mapper().analyze(list(findings))


def _nis2(result: ComplianceResult, code: str) -> ArticleResult:
    return next(a for a in result.nis2 if a.code == code)


def _rgpd(result: ComplianceResult, code: str) -> ArticleResult:
    return next(a for a in result.rgpd if a.code == code)


# ─────────────────────────────────────────────────────────────────────────────
# TestScoreHelpers
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreHelpers:
    def _art(self, compliant: bool) -> ArticleResult:
        return ArticleResult("x", "NIS2", "", "", "", "", compliant)

    def test_pct_score_all_compliant(self):
        arts = [self._art(True)] * 7
        assert _pct_score(arts) == 100

    def test_pct_score_none_compliant(self):
        arts = [self._art(False)] * 7
        assert _pct_score(arts) == 0

    def test_pct_score_partial(self):
        arts = [self._art(True)] * 4 + [self._art(False)] * 3   # 4/7
        assert _pct_score(arts) == round(4 / 7 * 100)

    def test_pct_score_empty_returns_100(self):
        assert _pct_score([]) == 100

    def test_overall_both_high(self):
        assert _overall_level(100, 100) == "conforme"

    def test_overall_at_threshold_conforme(self):
        assert _overall_level(SCORE_CONFORME, SCORE_CONFORME) == "conforme"

    def test_overall_just_below_conforme(self):
        assert _overall_level(SCORE_CONFORME - 1, 100) == "partiel"

    def test_overall_at_threshold_partiel(self):
        assert _overall_level(SCORE_PARTIEL, SCORE_PARTIEL) == "partiel"

    def test_overall_below_partiel(self):
        assert _overall_level(SCORE_PARTIEL - 1, SCORE_PARTIEL - 1) == "non_conforme"

    def test_overall_uses_worst_score(self):
        # NIS2=100 mais RGPD=0 → non_conforme
        assert _overall_level(100, 0) == "non_conforme"


# ─────────────────────────────────────────────────────────────────────────────
# TestComplianceEmpty — aucun finding
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceEmpty:
    def test_no_findings_all_nis2_compliant(self):
        result = _analyze()
        assert all(a.compliant for a in result.nis2)

    def test_no_findings_all_rgpd_compliant(self):
        result = _analyze()
        assert all(a.compliant for a in result.rgpd)

    def test_no_findings_nis2_score_100(self):
        assert _analyze().nis2_score == 100

    def test_no_findings_rgpd_score_100(self):
        assert _analyze().rgpd_score == 100

    def test_no_findings_overall_conforme(self):
        assert _analyze().overall_level == "conforme"

    def test_no_findings_triggered_by_empty(self):
        result = _analyze()
        for a in result.nis2 + result.rgpd:
            assert a.triggered_by == []

    def test_nis2_has_7_articles(self):
        assert len(_analyze().nis2) == len(NIS2_ARTICLES)

    def test_rgpd_has_4_articles(self):
        assert len(_analyze().rgpd) == len(RGPD_ARTICLES)


# ─────────────────────────────────────────────────────────────────────────────
# TestInfoSkipped — findings INFO ne déclenchent rien
# ─────────────────────────────────────────────────────────────────────────────

class TestInfoSkipped:
    def test_info_ssl_does_not_trigger(self):
        f = _Finding("SSL/TLS", "INFO", "Certificat valide", 0)
        result = _analyze(f)
        assert _nis2(result, "21-2-h").compliant is True

    def test_info_port_does_not_trigger(self):
        f = _Finding("Ports", "INFO", "Port SSH ouvert", 0)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").compliant is True

    def test_mixed_info_and_high(self):
        info = _Finding("SSL/TLS", "INFO", "Certificat valide", 0)
        high = _Finding("SSL/TLS", "HIGH", "SSL/TLS déprécié TLSv1.0", 20)
        result = _analyze(info, high)
        assert _nis2(result, "21-2-h").compliant is False


# ─────────────────────────────────────────────────────────────────────────────
# TestNIS2Mapping — NIS2 articles déclenchés par les findings
# ─────────────────────────────────────────────────────────────────────────────

class TestNIS2Mapping:
    def test_ssl_triggers_21_2_h(self):
        f = _Finding("SSL/TLS", "HIGH", "SSL/TLS expiré", 20)
        assert _nis2(_analyze(f), "21-2-h").compliant is False

    def test_hsts_triggers_21_2_h(self):
        f = _Finding("Headers HTTP", "HIGH", "HSTS manquant", 10)
        assert _nis2(_analyze(f), "21-2-h").compliant is False

    def test_spf_triggers_21_2_g_only(self):
        # SPF/DMARC/DKIM = hygiène email (21-2-g), pas chiffrement (21-2-h)
        f = _Finding("DNS", "HIGH", "SPF manquant", 15)
        result = _analyze(f)
        assert _nis2(result, "21-2-g").compliant is False
        assert _nis2(result, "21-2-h").compliant is True  # 21-2-h = chiffrement seulement

    def test_dmarc_triggers_21_2_g_not_h(self):
        # DMARC = hygiène email (21-2-g), pas chiffrement (21-2-h)
        f = _Finding("DNS", "MEDIUM", "DMARC présent mais en mode surveillance (p=none)", 8)
        result = _analyze(f)
        assert _nis2(result, "21-2-g").compliant is False
        assert _nis2(result, "21-2-h").compliant is True

    def test_dmarc_triggers_21_2_g(self):
        f = _Finding("DNS", "HIGH", "DMARC manquant", 15)
        assert _nis2(_analyze(f), "21-2-g").compliant is False

    def test_rdp_triggers_21_2_i_and_e(self):
        f = _Finding("Ports", "CRITICAL", "Port RDP exposé (3389)", 30)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").compliant is False
        assert _nis2(result, "21-2-e").compliant is False

    def test_vuln_version_triggers_21_2_e(self):
        f = _Finding("Versions vulnérables", "CRITICAL", "PHP version vulnérable (CVE-2021)", 25)
        assert _nis2(_analyze(f), "21-2-e").compliant is False

    def test_breach_triggers_21_2_b(self):
        f = _Finding("Fuites de données", "CRITICAL", "Domaine trouvé dans 3 fuites de données", 30)
        assert _nis2(_analyze(f), "21-2-b").compliant is False

    def test_admin_panel_triggers_21_2_i(self):
        f = _Finding("Applications", "HIGH", "Panneau admin exposé (/admin)", 10)
        assert _nis2(_analyze(f), "21-2-i").compliant is False

    def test_dnssec_triggers_21_2_g(self):
        f = _Finding("DNS", "LOW", "DNSSEC absent", 3)
        assert _nis2(_analyze(f), "21-2-g").compliant is False

    def test_domain_expiry_triggers_21_2_e(self):
        # Expiration domaine = maintenance/continuité (21-2-e), pas politiques (21-2-a)
        f = _Finding("Domaine", "HIGH", "Domaine expire dans 20 jours", 15)
        result = _analyze(f)
        assert _nis2(result, "21-2-e").compliant is False
        assert _nis2(result, "21-2-a").compliant is True  # 21-2-a = politiques de sécurité

    def test_server_version_exposed_does_not_trigger_21_2_i(self):
        # "Version du serveur exposée" ne doit pas matcher la règle des ports dangereux
        # Corrige le faux positif causé par "exposé"/"exposed" dans les mots-clés ports
        f = _Finding("Headers HTTP", "LOW", "Version du serveur exposée", 3)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").compliant is True   # Faux positif corrigé — plus dans la règle ports

    def test_subdomain_triggers_21_2_i(self):
        f = _Finding("Sous-domaines", "MEDIUM", "Sous-domaines orphelins détectés", 9)
        assert _nis2(_analyze(f), "21-2-i").compliant is False

    def test_reputation_triggers_21_2_b(self):
        f = _Finding("Réputation", "CRITICAL", "Domaine sur liste blacklist", 20)
        assert _nis2(_analyze(f), "21-2-b").compliant is False


# ─────────────────────────────────────────────────────────────────────────────
# TestRGPDMapping — RGPD articles déclenchés par les findings
# ─────────────────────────────────────────────────────────────────────────────

class TestRGPDMapping:
    def test_ssl_triggers_32_and_5_1_f(self):
        f = _Finding("SSL/TLS", "HIGH", "Certificat expiré", 20)
        result = _analyze(f)
        assert _rgpd(result, "32").compliant is False
        assert _rgpd(result, "5-1-f").compliant is False

    def test_hsts_triggers_32(self):
        f = _Finding("Headers HTTP", "HIGH", "HSTS manquant", 10)
        result = _analyze(f)
        assert _rgpd(result, "32").compliant is False

    def test_hsts_does_not_trigger_33(self):
        f = _Finding("Headers HTTP", "HIGH", "HSTS manquant", 10)
        result = _analyze(f)
        assert _rgpd(result, "33").compliant is True  # HSTS n'implique pas violation de données

    def test_port_triggers_32_and_25(self):
        f = _Finding("Ports", "CRITICAL", "Port MySQL exposé (3306)", 30)
        result = _analyze(f)
        assert _rgpd(result, "32").compliant is False
        assert _rgpd(result, "25").compliant is False

    def test_breach_triggers_33_and_5_1_f(self):
        f = _Finding("Fuites de données", "CRITICAL", "Breach HIBP détecté", 30)
        result = _analyze(f)
        assert _rgpd(result, "33").compliant is False
        assert _rgpd(result, "5-1-f").compliant is False

    def test_admin_exposed_triggers_25_and_32(self):
        f = _Finding("Applications", "HIGH", "Fichier .env exposé", 20)
        result = _analyze(f)
        assert _rgpd(result, "25").compliant is False
        assert _rgpd(result, "32").compliant is False

    def test_csp_triggers_25_only(self):
        f = _Finding("Headers HTTP", "MEDIUM", "Content-Security-Policy absent", 8)
        result = _analyze(f)
        assert _rgpd(result, "25").compliant is False


# ─────────────────────────────────────────────────────────────────────────────
# TestTriggeredBy — liste des findings déclencheurs
# ─────────────────────────────────────────────────────────────────────────────

class TestTriggeredBy:
    def test_triggered_by_contains_finding_title(self):
        f = _Finding("SSL/TLS", "HIGH", "TLS 1.0 déprécié", 15)
        art = _nis2(_analyze(f), "21-2-h")
        assert "TLS 1.0 déprécié" in art.triggered_by

    def test_deduplication_same_title(self):
        f1 = _Finding("SSL/TLS", "HIGH", "SSL expiré", 20)
        f2 = _Finding("SSL/TLS", "HIGH", "SSL expiré", 20)
        art = _nis2(_analyze(f1, f2), "21-2-h")
        assert art.triggered_by.count("SSL expiré") == 1

    def test_multiple_findings_accumulate(self):
        f1 = _Finding("SSL/TLS", "HIGH", "SSL expiré", 20)
        f2 = _Finding("SSL/TLS", "HIGH", "TLS 1.0 déprécié", 15)
        art = _nis2(_analyze(f1, f2), "21-2-h")
        assert len(art.triggered_by) == 2

    def test_compliant_article_has_empty_triggered_by(self):
        f = _Finding("SSL/TLS", "HIGH", "SSL expiré", 20)
        result = _analyze(f)
        # Art. 21-2-a (domaine/politique) non déclenché par SSL
        assert _nis2(result, "21-2-a").triggered_by == []


# ─────────────────────────────────────────────────────────────────────────────
# TestDictFindings — findings sous forme de dicts
# ─────────────────────────────────────────────────────────────────────────────

class TestDictFindings:
    def test_dict_finding_triggers_correctly(self):
        f = {"category": "SSL/TLS", "severity": "HIGH", "title": "Certificat expiré"}
        result = _mapper().analyze([f])
        assert _nis2(result, "21-2-h").compliant is False

    def test_dict_info_does_not_trigger(self):
        f = {"category": "SSL/TLS", "severity": "INFO", "title": "Certificat valide"}
        result = _mapper().analyze([f])
        assert _nis2(result, "21-2-h").compliant is True


# ─────────────────────────────────────────────────────────────────────────────
# TestToDict — sérialisation
# ─────────────────────────────────────────────────────────────────────────────

class TestToDict:
    def test_to_dict_has_all_keys(self):
        d = _analyze().to_dict()
        assert "nis2_score" in d
        assert "rgpd_score" in d
        assert "overall_level" in d
        assert "nis2" in d
        assert "rgpd" in d

    def test_article_to_dict_has_all_keys(self):
        result = _analyze()
        art = result.nis2[0].to_dict()
        for key in ("code", "framework", "title", "title_en",
                    "description", "description_en", "compliant", "triggered_by"):
            assert key in art

    def test_overall_level_in_dict(self):
        d = _analyze().to_dict()
        assert d["overall_level"] == "conforme"

    def test_scores_are_ints(self):
        d = _analyze().to_dict()
        assert isinstance(d["nis2_score"], int)
        assert isinstance(d["rgpd_score"], int)
