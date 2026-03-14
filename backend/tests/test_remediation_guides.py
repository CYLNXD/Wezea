"""
Tests — remediation_guides.py
==============================
Couvre : structure des guides, lookup par titre, batch lookup, intégrité des données.
"""
import pytest

from app.remediation_guides import (
    REMEDIATION_GUIDES,
    RemediationGuide,
    RemediationStep,
    get_guide_for_finding,
    get_guides_for_findings,
)


# ── Structure et intégrité ─────────────────────────────────────────────────────


class TestGuideDataIntegrity:
    """Vérifie que chaque guide est correctement formé."""

    def test_all_guides_are_remediation_guide(self):
        for key, guide in REMEDIATION_GUIDES.items():
            assert isinstance(guide, RemediationGuide), f"{key} n'est pas RemediationGuide"

    def test_all_guides_have_steps(self):
        for key, guide in REMEDIATION_GUIDES.items():
            assert len(guide.steps) >= 2, f"{key} a moins de 2 étapes"

    def test_steps_are_ordered(self):
        for key, guide in REMEDIATION_GUIDES.items():
            orders = [s.order for s in guide.steps]
            assert orders == sorted(orders), f"{key} : étapes pas ordonnées"

    def test_all_steps_have_bilingual_actions(self):
        for key, guide in REMEDIATION_GUIDES.items():
            for step in guide.steps:
                assert step.action_fr, f"{key} step {step.order} manque action_fr"
                assert step.action_en, f"{key} step {step.order} manque action_en"

    def test_difficulty_values(self):
        allowed = {"easy", "medium", "advanced"}
        for key, guide in REMEDIATION_GUIDES.items():
            assert guide.difficulty in allowed, f"{key} difficulty={guide.difficulty}"

    def test_estimated_time_positive(self):
        for key, guide in REMEDIATION_GUIDES.items():
            assert guide.estimated_time_min > 0, f"{key} estimated_time_min <= 0"

    def test_key_matches_guide_key(self):
        for key, guide in REMEDIATION_GUIDES.items():
            assert guide.key == key, f"Dict key '{key}' != guide.key '{guide.key}'"

    def test_all_guides_have_bilingual_titles(self):
        for key, guide in REMEDIATION_GUIDES.items():
            assert guide.title_fr, f"{key} manque title_fr"
            assert guide.title_en, f"{key} manque title_en"

    def test_guide_count(self):
        assert len(REMEDIATION_GUIDES) == 15

    def test_premium_guides_exist(self):
        premium = [g for g in REMEDIATION_GUIDES.values() if g.is_premium]
        assert len(premium) >= 3  # DKIM, TLS obsolète, CSP, WordPress


# ── Lookup par titre ────────────────────────────────────────────────────────────


class TestGetGuideForFinding:
    """Teste le matching substring case-insensitive."""

    def test_exact_key_match(self):
        guide = get_guide_for_finding("SPF manquant")
        assert guide is not None
        assert guide.key == "SPF manquant"

    def test_substring_match(self):
        guide = get_guide_for_finding("L'enregistrement SPF manquant pour le domaine")
        assert guide is not None
        assert guide.key == "SPF manquant"

    def test_case_insensitive(self):
        guide = get_guide_for_finding("hsts manquant dans les en-têtes")
        assert guide is not None
        assert guide.key == "HSTS manquant"

    def test_no_match_returns_none(self):
        guide = get_guide_for_finding("Something completely unrelated")
        assert guide is None

    def test_empty_title(self):
        assert get_guide_for_finding("") is None

    def test_dmarc_match(self):
        guide = get_guide_for_finding("DMARC manquant — politique p=none")
        assert guide is not None
        assert guide.key == "DMARC manquant"

    def test_ssl_expired_match(self):
        guide = get_guide_for_finding("Certificat SSL expiré depuis 5 jours")
        assert guide is not None
        assert guide.key == "Certificat SSL expiré"

    def test_domain_expiry_match(self):
        guide = get_guide_for_finding("Domaine expire dans 12 jours")
        assert guide is not None
        assert guide.key == "Domaine expire dans"

    def test_port_rdp_smb_match(self):
        guide = get_guide_for_finding("Port(s) RDP/SMB exposés sur le serveur")
        assert guide is not None
        assert guide.key == "Port(s) RDP/SMB"

    def test_database_exposed_match(self):
        guide = get_guide_for_finding("Base(s) de données exposée(s) sur internet")
        assert guide is not None
        assert guide.key == "Base(s) de données"

    def test_wordpress_match(self):
        guide = get_guide_for_finding("WordPress détecté sur le site")
        assert guide is not None
        assert guide.key == "WordPress détecté"
        assert guide.is_premium is True


# ── Batch lookup ────────────────────────────────────────────────────────────────


class TestGetGuidesForFindings:
    """Teste le batch lookup."""

    def test_batch_returns_dict(self):
        result = get_guides_for_findings(["SPF manquant", "Unknown"])
        assert isinstance(result, dict)
        assert len(result) == 2

    def test_batch_matched_and_unmatched(self):
        result = get_guides_for_findings(["SPF manquant", "Alien check"])
        assert result["SPF manquant"] is not None
        assert result["Alien check"] is None

    def test_batch_empty_list(self):
        result = get_guides_for_findings([])
        assert result == {}

    def test_batch_all_matched(self):
        titles = ["SPF manquant", "DMARC manquant", "HSTS manquant"]
        result = get_guides_for_findings(titles)
        assert all(v is not None for v in result.values())


# ── Dataclass ───────────────────────────────────────────────────────────────────


class TestRemediationStep:
    def test_defaults(self):
        step = RemediationStep(order=1, action_fr="Do", action_en="Do")
        assert step.where_fr == ""
        assert step.where_en == ""
        assert step.verify_fr == ""
        assert step.verify_en == ""
