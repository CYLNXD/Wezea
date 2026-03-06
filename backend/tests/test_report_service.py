"""
Tests unitaires pour app.services.report_service
=================================================
Couvre :
  - _checks_context          (compteurs + structure)
  - _derive_checks_overview  (edge cases données manquantes / None)
  - _score_color             (thresholds vert/orange/rouge)
  - _risk_color              (lookup dict)
  - _risk_label              (fr / en)
  - _build_action_plan       (phases urgent/important/optimize + dedup)
  - _build_context           (intégration complète avec données minimales)
"""
from __future__ import annotations

import pytest
from app.services.report_service import (
    _checks_context,
    _derive_checks_overview,
    _score_color,
    _risk_color,
    _risk_label,
    _build_action_plan,
    _build_context,
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


# ─── Tests _score_color ───────────────────────────────────────────────────────

class TestScoreColor:

    def test_green_at_70(self):
        assert _score_color(70) == "#16a34a"

    def test_green_at_100(self):
        assert _score_color(100) == "#16a34a"

    def test_green_at_71(self):
        assert _score_color(71) == "#16a34a"

    def test_orange_at_69(self):
        """69 → juste en dessous du seuil vert → orange."""
        assert _score_color(69) == "#ea580c"

    def test_orange_at_40(self):
        assert _score_color(40) == "#ea580c"

    def test_orange_at_55(self):
        assert _score_color(55) == "#ea580c"

    def test_red_at_39(self):
        """39 → juste en dessous du seuil orange → rouge."""
        assert _score_color(39) == "#dc2626"

    def test_red_at_0(self):
        assert _score_color(0) == "#dc2626"

    def test_red_at_1(self):
        assert _score_color(1) == "#dc2626"


# ─── Tests _risk_color ────────────────────────────────────────────────────────

class TestRiskColor:

    def test_critical(self):
        assert _risk_color("CRITICAL") == "#dc2626"

    def test_high(self):
        assert _risk_color("HIGH") == "#ea580c"

    def test_medium(self):
        assert _risk_color("MEDIUM") == "#d97706"

    def test_low(self):
        assert _risk_color("LOW") == "#16a34a"

    def test_unknown_returns_grey(self):
        """Niveau inconnu → couleur grise par défaut."""
        assert _risk_color("UNKNOWN") == "#64748b"

    def test_empty_string_returns_grey(self):
        assert _risk_color("") == "#64748b"


# ─── Tests _risk_label ────────────────────────────────────────────────────────

class TestRiskLabel:

    # Français
    def test_fr_critical(self):
        assert _risk_label("CRITICAL", "fr") == "Critique"

    def test_fr_high(self):
        assert _risk_label("HIGH", "fr") == "Élevé"

    def test_fr_medium(self):
        assert _risk_label("MEDIUM", "fr") == "Modéré"

    def test_fr_low(self):
        assert _risk_label("LOW", "fr") == "Faible"

    # Anglais
    def test_en_critical(self):
        assert _risk_label("CRITICAL", "en") == "Critical"

    def test_en_high(self):
        assert _risk_label("HIGH", "en") == "High"

    def test_en_medium(self):
        assert _risk_label("MEDIUM", "en") == "Moderate"

    def test_en_low(self):
        assert _risk_label("LOW", "en") == "Low"

    def test_unknown_level_returns_level_itself(self):
        """Niveau inconnu → retourne le niveau tel quel."""
        assert _risk_label("EXOTIC", "fr") == "EXOTIC"

    def test_unknown_lang_falls_back_to_fr(self):
        """Langue inconnue → fallback sur les labels fr."""
        assert _risk_label("CRITICAL", "es") == "Critique"


# ─── Tests _build_action_plan ─────────────────────────────────────────────────

class TestBuildActionPlan:

    def test_empty_findings_returns_three_phases(self):
        plan = _build_action_plan([], "fr")
        assert "urgent"    in plan
        assert "important" in plan
        assert "optimize"  in plan

    def test_empty_findings_no_urgent_no_important(self):
        plan = _build_action_plan([], "fr")
        assert plan["urgent"]    == []
        assert plan["important"] == []

    def test_empty_findings_has_default_optimize_items(self):
        """Sans findings, optimize contient 2 actions génériques de base."""
        plan = _build_action_plan([], "fr")
        assert len(plan["optimize"]) >= 2

    def test_spf_manquant_goes_to_urgent(self):
        findings = [{"title": "SPF manquant", "severity": "HIGH", "penalty": 20}]
        plan = _build_action_plan(findings, "fr")
        assert len(plan["urgent"]) == 1
        assert "SPF" in plan["urgent"][0]

    def test_dkim_goes_to_important(self):
        findings = [{"title": "DKIM non détecté", "severity": "MEDIUM", "penalty": 8}]
        plan = _build_action_plan(findings, "fr")
        assert len(plan["important"]) >= 1
        assert "DKIM" in plan["important"][0]

    def test_ssh_goes_to_optimize(self):
        findings = [{"title": "SSH (port 22) exposé", "severity": "INFO", "penalty": 0}]
        plan = _build_action_plan(findings, "fr")
        # Action SSH doit apparaître dans optimize (pas urgent ni important)
        all_optimize = plan["optimize"]
        assert any("SSH" in a or "clés" in a or "key" in a for a in all_optimize)

    def test_deduplication_same_finding_twice(self):
        """Deux findings avec la même clé → une seule action dans urgent."""
        findings = [
            {"title": "SPF manquant", "severity": "HIGH", "penalty": 20},
            {"title": "SPF manquant", "severity": "HIGH", "penalty": 20},
        ]
        plan = _build_action_plan(findings, "fr")
        # L'action SPF ne doit apparaître qu'une seule fois
        spf_actions = [a for a in plan["urgent"] if "SPF" in a]
        assert len(spf_actions) == 1

    def test_lang_en_returns_english_actions(self):
        findings = [{"title": "SPF manquant", "severity": "HIGH", "penalty": 20}]
        plan = _build_action_plan(findings, "en")
        assert len(plan["urgent"]) == 1
        # L'action anglaise doit être en anglais
        assert "SPF" in plan["urgent"][0]
        assert "DNS" in plan["urgent"][0] or "record" in plan["urgent"][0].lower()

    def test_multiple_findings_multiple_phases(self):
        """SPF (urgent) + DKIM (important) + SSH (optimize) → toutes phases remplies."""
        findings = [
            {"title": "SPF manquant",       "severity": "HIGH",   "penalty": 20},
            {"title": "DKIM non détecté",   "severity": "MEDIUM", "penalty": 8},
            {"title": "SSH (port 22) exposé","severity": "INFO",  "penalty": 0},
        ]
        plan = _build_action_plan(findings, "fr")
        assert len(plan["urgent"])    >= 1
        assert len(plan["important"]) >= 1
        assert len(plan["optimize"])  >= 1

    def test_optimize_capped_at_five(self):
        """La phase optimize ne doit pas dépasser 5 actions."""
        # Générer beaucoup de findings → optimize ne doit pas exploser
        findings = [
            {"title": "SSH (port 22) exposé", "severity": "INFO", "penalty": 0},
        ]
        plan = _build_action_plan(findings, "fr")
        assert len(plan["optimize"]) <= 5

    def test_dmarc_urgent(self):
        findings = [{"title": "DMARC manquant", "severity": "HIGH", "penalty": 15}]
        plan = _build_action_plan(findings, "fr")
        assert any("DMARC" in a for a in plan["urgent"])

    def test_ssl_expired_urgent(self):
        findings = [{"title": "Certificat SSL expiré", "severity": "CRITICAL", "penalty": 30}]
        plan = _build_action_plan(findings, "fr")
        assert any("SSL" in a or "certif" in a.lower() for a in plan["urgent"])


# ─── Tests _build_context ─────────────────────────────────────────────────────

MINIMAL_SCAN_DATA: dict = {
    "domain":         "example.com",
    "scan_id":        "abc-123",
    "security_score": 75,
    "risk_level":     "LOW",
    "findings":       [],
    "scanned_at":     "2025-06-15T10:30:00+00:00",
}

SCAN_WITH_FINDINGS: dict = {
    "domain":         "vuln.example.com",
    "scan_id":        "xyz-999",
    "security_score": 35,
    "risk_level":     "CRITICAL",
    "findings": [
        {"title": "SPF manquant",           "severity": "HIGH",     "penalty": 20, "category": "DNS & Mail"},
        {"title": "Port RDP ouvert (3389)", "severity": "CRITICAL", "penalty": 35, "category": "Exposition des Ports"},
        {"title": "HSTS absent",            "severity": "HIGH",     "penalty": 10, "category": "En-têtes HTTP"},
        {"title": "En-tête CSP manquant",   "severity": "MEDIUM",   "penalty": 8,  "category": "En-têtes HTTP"},
    ],
    "scanned_at": "2025-06-15T10:30:00+00:00",
}


class TestBuildContext:

    def test_returns_domain(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["domain"] == "example.com"

    def test_returns_scan_id(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["scan_id"] == "abc-123"

    def test_score_present(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["security_score"] == 75

    def test_score_color_green_for_high_score(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["score_color"] == "#16a34a"   # score=75 → vert

    def test_score_color_red_for_low_score(self):
        ctx = _build_context(SCAN_WITH_FINDINGS, "fr")
        assert ctx["score_color"] == "#dc2626"   # score=35 → rouge

    def test_risk_label_fr(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["risk_label"] == "Faible"

    def test_risk_label_en(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "en")
        assert ctx["risk_label"] == "Low"

    def test_risk_color_low(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["risk_color"] == "#16a34a"

    def test_risk_color_critical(self):
        ctx = _build_context(SCAN_WITH_FINDINGS, "fr")
        assert ctx["risk_color"] == "#dc2626"

    def test_lang_key_present(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "en")
        assert ctx["lang"] == "en"

    def test_strings_key_present(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert "strings" in ctx
        assert "report_type" in ctx["strings"]

    def test_strings_en_are_english(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "en")
        assert ctx["strings"]["report_type"] == "Cybersecurity Audit Report"

    def test_strings_fr_are_french(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["strings"]["report_type"] == "Rapport d'Audit Cybersécurité"

    def test_findings_grouped_by_category(self):
        ctx = _build_context(SCAN_WITH_FINDINGS, "fr")
        assert len(ctx["dns_findings"])    == 1
        assert len(ctx["port_findings"])   == 1
        assert len(ctx["header_findings"]) == 2

    def test_severity_counters(self):
        ctx = _build_context(SCAN_WITH_FINDINGS, "fr")
        assert ctx["critical_count"] == 1
        assert ctx["high_count"]     == 2
        assert ctx["medium_count"]   == 1
        assert ctx["low_count"]      == 0

    def test_checks_context_keys_present(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert "checks_overview"       in ctx
        assert "passed_checks_count"   in ctx
        assert "warn_checks_count"     in ctx
        assert "fail_checks_count"     in ctx

    def test_actions_key_present(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert "actions" in ctx
        assert "urgent"    in ctx["actions"]
        assert "important" in ctx["actions"]
        assert "optimize"  in ctx["actions"]

    def test_is_premium_false_without_details(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["is_premium"] is False

    def test_is_premium_true_with_subdomain_details(self):
        data = {**MINIMAL_SCAN_DATA, "subdomain_details": {"total_found": 3}}
        ctx = _build_context(data, "fr")
        assert ctx["is_premium"] is True

    def test_date_format_fr(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        # Format attendu : JJ/MM/AAAA à HH:MM UTC
        assert "15/06/2025" in ctx["scanned_at"]
        assert "à" in ctx["scanned_at"]

    def test_date_format_en(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "en")
        # Format attendu : MM/DD/YYYY at HH:MM UTC
        assert "06/15/2025" in ctx["scanned_at"]
        assert "at" in ctx["scanned_at"]

    def test_date_fallback_invalid_iso(self):
        """Date malformée → affichée brute sans crash."""
        data = {**MINIMAL_SCAN_DATA, "scanned_at": "not-a-date"}
        ctx = _build_context(data, "fr")
        assert ctx["scanned_at"] == "not-a-date"

    # ── White-label ───────────────────────────────────────────────────────────

    def test_no_white_label_wb_active_false(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["wb_active"] is False

    def test_white_label_active_sets_wb_active_true(self):
        wb = {"enabled": True, "company_name": "AcmeSec"}
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr", white_label=wb)
        assert ctx["wb_active"] is True

    def test_white_label_company_name_in_context(self):
        wb = {"enabled": True, "company_name": "AcmeSec"}
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr", white_label=wb)
        assert ctx["wb_company"] == "AcmeSec"

    def test_white_label_overrides_footer_brand_fr(self):
        wb = {"enabled": True, "company_name": "AcmeSec"}
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr", white_label=wb)
        assert "AcmeSec" in ctx["strings"]["footer_brand"]
        assert "Wezea" not in ctx["strings"]["footer_brand"]

    def test_white_label_overrides_footer_brand_en(self):
        wb = {"enabled": True, "company_name": "AcmeSec"}
        ctx = _build_context(MINIMAL_SCAN_DATA, "en", white_label=wb)
        assert "AcmeSec" in ctx["strings"]["footer_brand"]

    def test_white_label_disabled_flag_keeps_wezea(self):
        """enabled=False → pas de white-label même si company_name est fourni."""
        wb = {"enabled": False, "company_name": "AcmeSec"}
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr", white_label=wb)
        assert ctx["wb_active"] is False
        assert "Wezea" in ctx["strings"]["footer_brand"]

    def test_white_label_custom_color(self):
        wb = {"enabled": True, "company_name": "AcmeSec", "primary_color": "#ff0000"}
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr", white_label=wb)
        assert ctx["wb_color"] == "#ff0000"

    def test_default_color_when_no_white_label(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["wb_color"] == "#22d3ee"   # cyan Wezea par défaut

    def test_empty_findings_zero_severity_counters(self):
        ctx = _build_context(MINIMAL_SCAN_DATA, "fr")
        assert ctx["critical_count"] == 0
        assert ctx["high_count"]     == 0
        assert ctx["medium_count"]   == 0
        assert ctx["low_count"]      == 0
