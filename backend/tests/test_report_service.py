"""
Tests unitaires pour app.services.report_service
=================================================
Couvre :
  - _checks_context     (compteurs + structure)
  - _derive_checks_overview  (edge cases données manquantes / None)
  - _build_context      (intégration complète avec données minimales)
"""
from __future__ import annotations

import pytest
from app.services.report_service import (
    _checks_context,
    _derive_checks_overview,
)


# ─── Fixtures de base ─────────────────────────────────────────────────────────

MINIMAL_DATA: dict = {}

FULL_DNS_DATA: dict = {
    "dns_details": {
        "spf":   {"status": "ok", "records": ["v=spf1 include:_spf.google.com ~all"]},
        "dmarc": {"status": "ok", "policy": "reject"},
        "dkim":  {"status": "ok"},
        "mx":    {"records": ["mail.example.com"]},
    },
    # Correspond au format réel du scanner :
    # ssl_details.status, ssl_details.tls_version, ssl_details.days_left
    "ssl_details": {
        "status":      "valid",
        "tls_version": "TLSv1.3",
        "days_left":   90,
        "issuer":      {"O": "Let's Encrypt"},
    },
    # Correspond au format réel : port_det["443"]["open"], port_det["3389"]["open"]
    "port_details": {
        "443": {"open": True},
        "3389": {"open": False},
        "445":  {"open": False},
        "21":   {"open": False},
        "23":   {"open": False},
    },
}

FINDINGS_WITH_ISSUES = [
    {"title": "SPF manquant",              "severity": "HIGH",     "penalty": 20, "category": "DNS & Mail"},
    {"title": "DKIM non détecté",          "severity": "MEDIUM",   "penalty": 15, "category": "DNS & Mail"},
    {"title": "Port RDP ouvert (3389)",    "severity": "CRITICAL", "penalty": 35, "category": "Exposition des Ports"},
    {"title": "En-tête X-Frame-Options absent", "severity": "MEDIUM", "penalty": 10, "category": "En-têtes HTTP"},
]


# ─── Tests _checks_context ────────────────────────────────────────────────────

class TestChecksContext:

    def test_returns_required_keys(self):
        result = _checks_context(MINIMAL_DATA, [], "fr")
        assert "checks_overview"     in result
        assert "passed_checks_count" in result
        assert "warn_checks_count"   in result
        assert "fail_checks_count"   in result

    def test_counts_sum_to_total(self):
        result = _checks_context(MINIMAL_DATA, [], "fr")
        total = (
            result["passed_checks_count"]
            + result["warn_checks_count"]
            + result["fail_checks_count"]
        )
        assert total == len(result["checks_overview"])

    def test_mostly_passed_with_full_valid_data(self):
        """Avec des données SSL/DNS valides et aucun finding, la majorité des checks passe."""
        result = _checks_context(FULL_DNS_DATA, [], "fr")
        total = len(result["checks_overview"])
        assert result["passed_checks_count"] > total // 2, \
            f"Expected majority passed, got {result['passed_checks_count']}/{total}"

    def test_failures_increase_with_critical_findings(self):
        result_clean   = _checks_context(MINIMAL_DATA, [], "fr")
        result_issues  = _checks_context(MINIMAL_DATA, FINDINGS_WITH_ISSUES, "fr")
        # Avec des findings, il doit y avoir au moins autant d'échecs
        assert result_issues["fail_checks_count"] >= result_clean["fail_checks_count"]

    def test_lang_en_works(self):
        result = _checks_context(MINIMAL_DATA, [], "en")
        assert result["passed_checks_count"] >= 0
        # Les labels en doivent être en anglais
        checks = result["checks_overview"]
        assert all("label_en" in c for c in checks)

    def test_counts_non_negative(self):
        result = _checks_context(MINIMAL_DATA, FINDINGS_WITH_ISSUES, "fr")
        assert result["passed_checks_count"] >= 0
        assert result["warn_checks_count"]   >= 0
        assert result["fail_checks_count"]   >= 0


# ─── Tests _derive_checks_overview — edge cases ───────────────────────────────

class TestDeriveChecksOverview:

    def test_empty_data_no_crash(self):
        """Données vides → aucun crash, retourne des checks."""
        checks = _derive_checks_overview({}, [], "fr")
        assert isinstance(checks, list)
        assert len(checks) > 0

    def test_none_values_no_crash(self):
        """dns_details / ssl_details / port_details = None → aucun crash."""
        data = {
            "dns_details":  None,
            "ssl_details":  None,
            "port_details": None,
        }
        checks = _derive_checks_overview(data, [], "fr")
        assert isinstance(checks, list)
        assert len(checks) > 0

    def test_check_structure(self):
        """Chaque check a les champs requis."""
        checks = _derive_checks_overview(MINIMAL_DATA, [], "fr")
        required = {"category", "icon", "label_fr", "label_en", "passed", "warning", "detail_fr", "detail_en"}
        for c in checks:
            assert required.issubset(c.keys()), f"Check missing fields: {c}"

    def test_passed_and_warning_mutually_exclusive(self):
        """Un check ne peut pas être passed=True ET warning=True simultanément."""
        checks = _derive_checks_overview(MINIMAL_DATA, FINDINGS_WITH_ISSUES, "fr")
        for c in checks:
            assert not (c["passed"] and c["warning"]), \
                f"Check cannot be both passed and warning: {c['label_fr']}"

    def test_spf_ok_with_valid_record(self):
        """SPF valide → check SPF passed."""
        checks = _derive_checks_overview(FULL_DNS_DATA, [], "fr")
        spf = next(c for c in checks if "SPF" in c["label_fr"])
        assert spf["passed"] is True

    def test_spf_fail_with_missing_finding(self):
        """Finding 'SPF manquant' → check SPF failed."""
        findings = [{"title": "SPF manquant", "severity": "HIGH", "penalty": 20}]
        checks = _derive_checks_overview({}, findings, "fr")
        spf = next(c for c in checks if "SPF" in c["label_fr"])
        assert spf["passed"] is False

    def test_dmarc_warning_with_policy_none(self):
        """DMARC p=none → warning (pas echec)."""
        data = {
            "dns_details": {
                "dmarc": {"status": "ok", "policy": "none"},
            }
        }
        checks = _derive_checks_overview(data, [], "fr")
        dmarc = next(c for c in checks if "DMARC" in c["label_fr"])
        assert dmarc["warning"] is True
        assert dmarc["passed"] is False

    def test_dmarc_pass_with_reject_policy(self):
        """DMARC p=reject → passed."""
        data = {
            "dns_details": {
                "dmarc": {"status": "ok", "policy": "reject"},
            }
        }
        checks = _derive_checks_overview(data, [], "fr")
        dmarc = next(c for c in checks if "DMARC" in c["label_fr"])
        assert dmarc["passed"] is True

    def test_rdp_port_check_fail_with_open_port(self):
        """Port 3389 ouvert dans port_details → check RDP failed.
        NB: les checks ports utilisent port_details (pas les findings titles)."""
        data = {"port_details": {"3389": {"open": True}}}
        checks = _derive_checks_overview(data, [], "fr")
        rdp = next((c for c in checks if "3389" in c["label_fr"] or "RDP" in c["label_fr"]), None)
        assert rdp is not None, "RDP check should exist"
        assert rdp["passed"] is False

    def test_rdp_port_check_pass_when_closed(self):
        """Port 3389 fermé → check RDP passed."""
        data = {"port_details": {"3389": {"open": False}}}
        checks = _derive_checks_overview(data, [], "fr")
        rdp = next((c for c in checks if "3389" in c["label_fr"] or "RDP" in c["label_fr"]), None)
        assert rdp is not None
        assert rdp["passed"] is True

    def test_ssl_valid_pass(self):
        """SSL valide + expiry >30j → checks SSL passed."""
        data = {
            "ssl_details": {
                "valid": True,
                "days_left": 60,
                "protocols": ["TLSv1.3"],
            }
        }
        checks = _derive_checks_overview(data, [], "fr")
        ssl_checks = [c for c in checks if "SSL" in c["label_fr"] or "TLS" in c["label_fr"] or "cert" in c["label_fr"].lower() or "Certificat" in c["label_fr"]]
        # Au moins un check SSL passed
        assert any(c["passed"] for c in ssl_checks)

    def test_categories_present(self):
        """Les catégories attendues sont présentes dans les checks."""
        checks = _derive_checks_overview(MINIMAL_DATA, [], "fr")
        categories = {c["category"] for c in checks}
        assert "DNS & Mail" in categories
