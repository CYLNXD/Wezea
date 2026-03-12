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
    CriterionResult,
    NIS2_ARTICLES,
    RGPD_ARTICLES,
    COMPLIANCE_CRITERIA,
    NOT_ASSESSABLE_NIS2,
    SCORE_BON,
    SCORE_INSUFFISANT,
    SCORE_CONFORME,
    SCORE_PARTIEL,
    DISCLAIMER_FR,
    DISCLAIMER_EN,
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


def _criterion(result: ComplianceResult, crit_id: str) -> CriterionResult:
    return next(c for c in result.criteria if c.id == crit_id)


# ─────────────────────────────────────────────────────────────────────────────
# TestScoreHelpers
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreHelpers:
    def _art(self, status: str) -> ArticleResult:
        return ArticleResult("x", "NIS2", "", "", "", "", compliant=(status == "pass"), status=status)

    def test_pct_score_all_pass(self):
        arts = [self._art("pass")] * 7
        assert _pct_score(arts) == 100

    def test_pct_score_all_fail(self):
        arts = [self._art("fail")] * 7
        assert _pct_score(arts) == 0

    def test_pct_score_partial_warn(self):
        # 4 pass + 3 warn = (4*1.0 + 3*0.5) / 7 = 5.5/7 = 78.57 → 79
        arts = [self._art("pass")] * 4 + [self._art("warn")] * 3
        assert _pct_score(arts) == round(5.5 / 7 * 100)

    def test_pct_score_mixed_fail_pass(self):
        # 4 pass + 3 fail = 4/7 = 57.14 → 57
        arts = [self._art("pass")] * 4 + [self._art("fail")] * 3
        assert _pct_score(arts) == round(4 / 7 * 100)

    def test_pct_score_empty_returns_100(self):
        assert _pct_score([]) == 100

    def test_pct_score_excludes_not_assessable(self):
        arts = [self._art("pass")] * 3 + [ArticleResult("x", "NIS2", "", "", "", "", None, "not_assessable")]
        assert _pct_score(arts) == 100  # 3/3 = 100%

    def test_overall_both_high(self):
        assert _overall_level(100, 100) == "bon"

    def test_overall_at_threshold_bon(self):
        assert _overall_level(SCORE_BON, SCORE_BON) == "bon"

    def test_overall_just_below_bon(self):
        assert _overall_level(SCORE_BON - 1, 100) == "insuffisant"

    def test_overall_at_threshold_insuffisant(self):
        assert _overall_level(SCORE_INSUFFISANT, SCORE_INSUFFISANT) == "insuffisant"

    def test_overall_below_insuffisant(self):
        assert _overall_level(SCORE_INSUFFISANT - 1, SCORE_INSUFFISANT - 1) == "critique"

    def test_overall_uses_worst_score(self):
        # NIS2=100 mais RGPD=0 → critique
        assert _overall_level(100, 0) == "critique"

    def test_backcompat_aliases(self):
        assert SCORE_CONFORME == SCORE_BON
        assert SCORE_PARTIEL == SCORE_INSUFFISANT


# ─────────────────────────────────────────────────────────────────────────────
# TestComplianceEmpty — aucun finding
# ─────────────────────────────────────────────────────────────────────────────

class TestComplianceEmpty:
    def test_no_findings_assessable_nis2_pass(self):
        result = _analyze()
        for a in result.nis2:
            if a.code not in NOT_ASSESSABLE_NIS2:
                assert a.status == "pass"
                assert a.compliant is True

    def test_no_findings_not_assessable_nis2(self):
        result = _analyze()
        for code in NOT_ASSESSABLE_NIS2:
            art = _nis2(result, code)
            assert art.status == "not_assessable"
            assert art.compliant is None

    def test_no_findings_all_rgpd_pass(self):
        result = _analyze()
        assert all(a.status == "pass" for a in result.rgpd)

    def test_no_findings_nis2_score_100(self):
        assert _analyze().nis2_score == 100

    def test_no_findings_rgpd_score_100(self):
        assert _analyze().rgpd_score == 100

    def test_no_findings_overall_bon(self):
        assert _analyze().overall_level == "bon"

    def test_no_findings_triggered_by_empty(self):
        result = _analyze()
        for a in result.nis2 + result.rgpd:
            assert a.triggered_by == []

    def test_nis2_has_7_articles(self):
        assert len(_analyze().nis2) == len(NIS2_ARTICLES)

    def test_rgpd_has_4_articles(self):
        assert len(_analyze().rgpd) == len(RGPD_ARTICLES)

    def test_no_findings_criteria_all_pass(self):
        result = _analyze()
        assert all(c.status == "pass" for c in result.criteria)

    def test_no_findings_has_12_criteria(self):
        assert len(_analyze().criteria) == len(COMPLIANCE_CRITERIA)


# ─────────────────────────────────────────────────────────────────────────────
# TestInfoSkipped — findings INFO ne déclenchent rien
# ─────────────────────────────────────────────────────────────────────────────

class TestInfoSkipped:
    def test_info_ssl_does_not_trigger(self):
        f = _Finding("SSL / HTTPS", "INFO", "Certificat valide", 0)
        result = _analyze(f)
        assert _nis2(result, "21-2-h").status == "pass"

    def test_info_port_does_not_trigger(self):
        f = _Finding("Exposition des Ports", "INFO", "Port SSH ouvert", 0)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").status == "pass"

    def test_mixed_info_and_high(self):
        info = _Finding("SSL / HTTPS", "INFO", "Certificat valide", 0)
        high = _Finding("SSL / HTTPS", "HIGH", "SSL/TLS déprécié TLSv1.0", 20)
        result = _analyze(info, high)
        assert _nis2(result, "21-2-h").compliant is False


# ─────────────────────────────────────────────────────────────────────────────
# TestNIS2Mapping — NIS2 articles déclenchés par les critères
# ─────────────────────────────────────────────────────────────────────────────

class TestNIS2Mapping:
    def test_ssl_expired_triggers_21_2_h(self):
        # Certificat expiré → _check_https → cat "SSL / HTTPS" sev >= 4 → fail
        f = _Finding("SSL / HTTPS", "CRITICAL", "Certificat SSL expiré", 20)
        assert _nis2(_analyze(f), "21-2-h").compliant is False

    def test_ssl_high_triggers_21_2_h_warn(self):
        # SSL HIGH sans keyword spécifique → _check_https 3rd check → warn
        f = _Finding("SSL / HTTPS", "HIGH", "Certificat expire bientôt", 10)
        result = _analyze(f)
        assert _nis2(result, "21-2-h").status == "warn"

    def test_hsts_triggers_21_2_e_and_a(self):
        # HSTS manquant → _check_headers → links to 21-2-e, 21-2-a (not 21-2-h)
        f = _Finding("En-têtes HTTP", "HIGH", "HSTS manquant", 10)
        result = _analyze(f)
        assert _nis2(result, "21-2-e").compliant is False
        assert _nis2(result, "21-2-a").compliant is False

    def test_spf_triggers_21_2_g_only(self):
        f = _Finding("DNS & Mail", "HIGH", "SPF manquant", 15)
        result = _analyze(f)
        assert _nis2(result, "21-2-g").compliant is False
        assert _nis2(result, "21-2-h").status == "pass"

    def test_dmarc_warn_triggers_21_2_g(self):
        f = _Finding("DNS & Mail", "MEDIUM", "DMARC présent mais en mode surveillance (p=none)", 8)
        result = _analyze(f)
        assert _nis2(result, "21-2-g").compliant is False

    def test_dmarc_missing_triggers_21_2_g(self):
        f = _Finding("DNS & Mail", "HIGH", "DMARC manquant", 15)
        assert _nis2(_analyze(f), "21-2-g").compliant is False

    def test_rdp_triggers_21_2_i_and_e(self):
        f = _Finding("Exposition des Ports", "CRITICAL", "Port RDP exposé (3389)", 30)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").compliant is False
        assert _nis2(result, "21-2-e").compliant is False

    def test_vuln_version_triggers_21_2_e_and_a(self):
        f = _Finding("Versions Vulnérables", "CRITICAL", "PHP version vulnérable (CVE-2021)", 25)
        result = _analyze(f)
        assert _nis2(result, "21-2-e").compliant is False
        assert _nis2(result, "21-2-a").compliant is False

    def test_breach_triggers_21_2_b(self):
        f = _Finding("Fuites de données", "CRITICAL", "Domaine trouvé dans 3 fuites de données", 30)
        assert _nis2(_analyze(f), "21-2-b").compliant is False

    def test_admin_panel_triggers_21_2_i(self):
        f = _Finding("Exposition admin", "HIGH", "Panneau admin exposé (/admin)", 10)
        assert _nis2(_analyze(f), "21-2-i").compliant is False

    def test_dnssec_triggers_21_2_g(self):
        f = _Finding("DNS & Mail", "LOW", "DNSSEC absent", 3)
        assert _nis2(_analyze(f), "21-2-g").compliant is False

    def test_domain_expiry_triggers_21_2_e(self):
        f = _Finding("Infrastructure", "HIGH", "Domaine expire dans 20 jours", 15)
        result = _analyze(f)
        assert _nis2(result, "21-2-e").compliant is False

    def test_server_version_low_does_not_trigger_21_2_i(self):
        # LOW severity "exposée" in title shouldn't trigger credentials (sev >= 3)
        f = _Finding("En-têtes HTTP", "LOW", "Version du serveur exposée", 3)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").status == "pass"

    def test_subdomain_orphan_triggers_21_2_i(self):
        f = _Finding("Sous-domaines & Certificats", "MEDIUM", "Sous-domaines orphelins détectés", 9)
        result = _analyze(f)
        assert _nis2(result, "21-2-i").compliant is False

    def test_reputation_triggers_21_2_b(self):
        f = _Finding("Réputation du Domaine", "CRITICAL", "Domaine sur liste blacklist", 20)
        assert _nis2(_analyze(f), "21-2-b").compliant is False

    def test_21_2_j_always_not_assessable(self):
        f = _Finding("SSL / HTTPS", "CRITICAL", "Certificat SSL expiré", 20)
        result = _analyze(f)
        art = _nis2(result, "21-2-j")
        assert art.status == "not_assessable"
        assert art.compliant is None


# ─────────────────────────────────────────────────────────────────────────────
# TestRGPDMapping — RGPD articles déclenchés par les critères
# ─────────────────────────────────────────────────────────────────────────────

class TestRGPDMapping:
    def test_ssl_triggers_32_and_5_1_f(self):
        f = _Finding("SSL / HTTPS", "CRITICAL", "Certificat expiré", 20)
        result = _analyze(f)
        assert _rgpd(result, "32").compliant is False
        assert _rgpd(result, "5-1-f").compliant is False

    def test_hsts_triggers_25(self):
        f = _Finding("En-têtes HTTP", "HIGH", "HSTS manquant", 10)
        result = _analyze(f)
        assert _rgpd(result, "25").compliant is False

    def test_hsts_does_not_trigger_33(self):
        f = _Finding("En-têtes HTTP", "HIGH", "HSTS manquant", 10)
        result = _analyze(f)
        assert _rgpd(result, "33").status == "pass"

    def test_port_triggers_32_and_25(self):
        f = _Finding("Exposition des Ports", "CRITICAL", "Port MySQL exposé (3306)", 30)
        result = _analyze(f)
        assert _rgpd(result, "32").compliant is False
        assert _rgpd(result, "25").compliant is False

    def test_breach_triggers_33_and_5_1_f(self):
        f = _Finding("Fuites de données", "CRITICAL", "Breach HIBP détecté", 30)
        result = _analyze(f)
        assert _rgpd(result, "33").compliant is False
        assert _rgpd(result, "5-1-f").compliant is False

    def test_admin_exposed_triggers_25_and_32(self):
        f = _Finding("Fichiers sensibles", "HIGH", "Fichier .env exposé", 20)
        result = _analyze(f)
        assert _rgpd(result, "32").compliant is False

    def test_csp_triggers_25_only(self):
        f = _Finding("En-têtes HTTP", "MEDIUM", "Content-Security-Policy absent", 8)
        result = _analyze(f)
        assert _rgpd(result, "25").compliant is False


# ─────────────────────────────────────────────────────────────────────────────
# TestTriggeredBy — liste des findings déclencheurs
# ─────────────────────────────────────────────────────────────────────────────

class TestTriggeredBy:
    def test_triggered_by_contains_criterion_label(self):
        f = _Finding("SSL / HTTPS", "HIGH", "TLS 1.0 déprécié", 15)
        art = _nis2(_analyze(f), "21-2-h")
        # triggered_by now contains criterion labels, not finding titles
        assert len(art.triggered_by) > 0

    def test_deduplication_same_criterion(self):
        f1 = _Finding("SSL / HTTPS", "HIGH", "TLS 1.0 déprécié", 20)
        f2 = _Finding("SSL / HTTPS", "HIGH", "TLS 1.1 déprécié", 15)
        art = _nis2(_analyze(f1, f2), "21-2-h")
        # Both trigger _check_tls → same criterion label, deduplicated
        labels = art.triggered_by
        assert len(labels) == len(set(labels))

    def test_multiple_criteria_accumulate(self):
        f1 = _Finding("SSL / HTTPS", "CRITICAL", "Certificat SSL expiré", 20)
        f2 = _Finding("SSL / HTTPS", "HIGH", "TLS 1.0 déprécié", 15)
        art = _nis2(_analyze(f1, f2), "21-2-h")
        # Both https and tls criteria trigger → 2 labels
        assert len(art.triggered_by) == 2

    def test_pass_article_has_empty_triggered_by(self):
        f = _Finding("SSL / HTTPS", "CRITICAL", "Certificat SSL expiré", 20)
        result = _analyze(f)
        # Art. 21-2-g (email/DNS) not triggered by SSL
        assert _nis2(result, "21-2-g").triggered_by == []


# ─────────────────────────────────────────────────────────────────────────────
# TestDictFindings — findings sous forme de dicts
# ─────────────────────────────────────────────────────────────────────────────

class TestDictFindings:
    def test_dict_finding_triggers_correctly(self):
        f = {"category": "SSL / HTTPS", "severity": "CRITICAL", "title": "Certificat expiré"}
        result = _mapper().analyze([f])
        assert _nis2(result, "21-2-h").compliant is False

    def test_dict_info_does_not_trigger(self):
        f = {"category": "SSL / HTTPS", "severity": "INFO", "title": "Certificat valide"}
        result = _mapper().analyze([f])
        assert _nis2(result, "21-2-h").status == "pass"


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
        assert "criteria" in d
        assert "disclaimer_fr" in d
        assert "disclaimer_en" in d

    def test_article_to_dict_has_all_keys(self):
        result = _analyze()
        art = result.nis2[0].to_dict()
        for key in ("code", "framework", "title", "title_en",
                    "description", "description_en", "compliant", "status", "triggered_by"):
            assert key in art

    def test_criterion_to_dict_has_all_keys(self):
        result = _analyze()
        crit = result.criteria[0].to_dict()
        for key in ("id", "label_fr", "label_en", "regulations",
                    "article_fr", "article_en", "desc_fr", "desc_en", "status"):
            assert key in crit

    def test_overall_level_in_dict(self):
        d = _analyze().to_dict()
        assert d["overall_level"] == "bon"

    def test_scores_are_ints(self):
        d = _analyze().to_dict()
        assert isinstance(d["nis2_score"], int)
        assert isinstance(d["rgpd_score"], int)

    def test_disclaimer_present(self):
        d = _analyze().to_dict()
        assert d["disclaimer_fr"] == DISCLAIMER_FR
        assert d["disclaimer_en"] == DISCLAIMER_EN

    def test_criteria_serialized(self):
        d = _analyze().to_dict()
        assert isinstance(d["criteria"], list)
        assert len(d["criteria"]) == 12


# ─────────────────────────────────────────────────────────────────────────────
# TestCriteria — évaluation des 12 critères techniques
# ─────────────────────────────────────────────────────────────────────────────

class TestCriteria:
    def test_https_pass_no_findings(self):
        assert _criterion(_analyze(), "https").status == "pass"

    def test_https_fail_critical_ssl(self):
        f = _Finding("SSL / HTTPS", "CRITICAL", "Certificat SSL expiré", 20)
        assert _criterion(_analyze(f), "https").status == "fail"

    def test_https_warn_high_ssl(self):
        f = _Finding("SSL / HTTPS", "HIGH", "Certificat expire bientôt", 10)
        assert _criterion(_analyze(f), "https").status == "warn"

    def test_tls_fail_deprecated(self):
        f = _Finding("SSL / HTTPS", "HIGH", "TLS 1.0 déprécié", 15)
        assert _criterion(_analyze(f), "tls").status == "fail"

    def test_tls_warn_pfs_missing(self):
        f = _Finding("SSL / HTTPS", "MEDIUM", "Perfect Forward Secrecy absent", 8)
        assert _criterion(_analyze(f), "tls").status == "warn"

    def test_dmarc_fail_missing(self):
        f = _Finding("DNS & Mail", "HIGH", "DMARC manquant", 15)
        assert _criterion(_analyze(f), "dmarc").status == "fail"

    def test_dmarc_warn_p_none(self):
        f = _Finding("DNS & Mail", "MEDIUM", "DMARC en mode surveillance (p=none)", 8)
        assert _criterion(_analyze(f), "dmarc").status == "warn"

    def test_headers_fail_hsts(self):
        f = _Finding("En-têtes HTTP", "HIGH", "HSTS manquant", 10)
        assert _criterion(_analyze(f), "headers").status == "fail"

    def test_headers_warn_medium(self):
        f = _Finding("En-têtes HTTP", "MEDIUM", "CSP absent", 8)
        assert _criterion(_analyze(f), "headers").status == "warn"

    def test_spf_fail_missing(self):
        f = _Finding("DNS & Mail", "HIGH", "SPF manquant", 15)
        assert _criterion(_analyze(f), "spf").status == "fail"

    def test_dkim_fail_missing(self):
        f = _Finding("Sécurité Email", "MEDIUM", "DKIM absent", 8)
        assert _criterion(_analyze(f), "dkim").status == "fail"

    def test_dnssec_warn_absent(self):
        f = _Finding("DNS & Mail", "LOW", "DNSSEC absent", 3)
        assert _criterion(_analyze(f), "dnssec").status == "warn"

    def test_ports_fail_rdp(self):
        f = _Finding("Exposition des Ports", "CRITICAL", "Port RDP exposé (3389)", 30)
        assert _criterion(_analyze(f), "ports").status == "fail"

    def test_ports_pass_ssh(self):
        # SSH is not in the dangerous ports list
        f = _Finding("Exposition des Ports", "INFO", "Port SSH ouvert", 0)
        assert _criterion(_analyze(f), "ports").status == "pass"

    def test_reputation_fail_blacklist(self):
        f = _Finding("Réputation du Domaine", "CRITICAL", "IP blacklistée", 20)
        assert _criterion(_analyze(f), "reputation").status == "fail"

    def test_reputation_fail_breach(self):
        f = _Finding("Fuites de données", "CRITICAL", "Breach HIBP", 30)
        assert _criterion(_analyze(f), "reputation").status == "fail"

    def test_credentials_fail_env(self):
        f = _Finding("Fichiers sensibles", "HIGH", "Fichier .env exposé", 20)
        assert _criterion(_analyze(f), "credentials").status == "fail"

    def test_credentials_fail_admin(self):
        f = _Finding("Exposition admin", "HIGH", "Panneau admin exposé", 10)
        assert _criterion(_analyze(f), "credentials").status == "fail"

    def test_credentials_warn_orphan_subdomains(self):
        f = _Finding("Sous-domaines & Certificats", "MEDIUM", "Sous-domaines orphelins détectés", 9)
        assert _criterion(_analyze(f), "credentials").status == "warn"

    def test_expiry_fail_expired(self):
        f = _Finding("Infrastructure", "CRITICAL", "Domaine expiré", 50)
        assert _criterion(_analyze(f), "expiry").status == "fail"

    def test_expiry_warn_soon(self):
        f = _Finding("Infrastructure", "HIGH", "Domaine expire dans 20 jours", 15)
        assert _criterion(_analyze(f), "expiry").status == "warn"

    def test_versions_fail_critical(self):
        f = _Finding("Versions Vulnérables", "CRITICAL", "PHP 7.4 vulnérable", 25)
        assert _criterion(_analyze(f), "versions").status == "fail"

    def test_versions_warn_high(self):
        f = _Finding("Versions Vulnérables", "HIGH", "nginx 1.20 vulnérable", 12)
        assert _criterion(_analyze(f), "versions").status == "warn"


# ─────────────────────────────────────────────────────────────────────────────
# TestNotAssessable — articles non évaluables par scan externe
# ─────────────────────────────────────────────────────────────────────────────

class TestNotAssessable:
    def test_21_2_j_not_assessable_empty(self):
        result = _analyze()
        art = _nis2(result, "21-2-j")
        assert art.status == "not_assessable"
        assert art.compliant is None

    def test_21_2_j_not_affected_by_findings(self):
        # Even with tons of findings, 21-2-j stays not_assessable
        f = _Finding("SSL / HTTPS", "CRITICAL", "Certificat SSL expiré", 20)
        result = _analyze(f)
        assert _nis2(result, "21-2-j").status == "not_assessable"

    def test_not_assessable_excluded_from_score(self):
        # 21-2-j (not_assessable) should not count in nis2_score
        result = _analyze()
        # All 6 assessable articles pass → 100%
        assert result.nis2_score == 100


# ─────────────────────────────────────────────────────────────────────────────
# TestDisclaimer — disclaimer présent dans le résultat
# ─────────────────────────────────────────────────────────────────────────────

class TestDisclaimer:
    def test_disclaimer_fr_present(self):
        result = _analyze()
        assert result.disclaimer_fr == DISCLAIMER_FR
        assert "MFA" in result.disclaimer_fr

    def test_disclaimer_en_present(self):
        result = _analyze()
        assert result.disclaimer_en == DISCLAIMER_EN
        assert "MFA" in result.disclaimer_en

    def test_disclaimer_in_to_dict(self):
        d = _analyze().to_dict()
        assert d["disclaimer_fr"] == DISCLAIMER_FR
        assert d["disclaimer_en"] == DISCLAIMER_EN


# ─────────────────────────────────────────────────────────────────────────────
# TestSeverityWeighting — pondération par sévérité
# ─────────────────────────────────────────────────────────────────────────────

class TestSeverityWeighting:
    def test_warn_criterion_gives_warn_article(self):
        # PFS missing → tls criterion "warn" → 21-2-h gets "warn"
        f = _Finding("SSL / HTTPS", "MEDIUM", "Perfect Forward Secrecy absent", 8)
        result = _analyze(f)
        art = _nis2(result, "21-2-h")
        assert art.status == "warn"
        assert art.compliant is False

    def test_fail_overrides_warn(self):
        # Two findings: one gives warn, other gives fail → article gets fail
        f1 = _Finding("SSL / HTTPS", "MEDIUM", "Perfect Forward Secrecy absent", 8)
        f2 = _Finding("SSL / HTTPS", "HIGH", "TLS 1.0 déprécié", 15)
        result = _analyze(f1, f2)
        art = _nis2(result, "21-2-h")
        assert art.status == "fail"

    def test_score_with_warn_articles(self):
        # Create a scenario where some articles are warn
        f = _Finding("SSL / HTTPS", "MEDIUM", "Perfect Forward Secrecy absent", 8)
        result = _analyze(f)
        # tls criterion is "warn" → 21-2-h gets "warn" → weighted 50%
        # Other articles pass → 100% each
        # NIS2 score: 5 pass (21-2-a, 21-2-b, 21-2-e, 21-2-g, 21-2-i) + 1 warn (21-2-h) + 1 not_assessable (21-2-j)
        # = (5*1.0 + 1*0.5) / 6 = 5.5/6 = 91.67 → 92
        assert result.nis2_score == round(5.5 / 6 * 100)
