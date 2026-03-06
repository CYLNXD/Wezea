"""
CyberHealth Scanner — Service de Génération PDF
================================================
Transforme les données JSON d'un scan en rapport PDF professionnel
via le pipeline : données → contexte enrichi → Jinja2 → HTML → WeasyPrint → PDF

Architecture :
    generate_pdf(audit_data)          → bytes (PDF en mémoire)
    _build_context(data)              → dict (contexte Jinja2 enrichi)
    _build_action_plan(findings)      → dict (3 phases d'actions)
    _score_color(score)               → str (couleur hex)
    _risk_color(level)                → str (couleur hex)

Dépendances :
    pip install weasyprint jinja2
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# ── Chemins ───────────────────────────────────────────────────────────────────

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "templates"
)

# Actions par catégorie de finding (pour le plan d'action automatique)
FINDING_ACTIONS: dict[str, dict] = {
    "SPF manquant":               {"phase": "urgent",    "action_fr": "Ajouter un enregistrement SPF sur le DNS",                                          "action_en": "Add an SPF record to your DNS"},
    "SPF missing":                {"phase": "urgent",    "action_fr": "Ajouter un enregistrement SPF sur le DNS",                                          "action_en": "Add an SPF record to your DNS"},
    "SPF mal configuré":          {"phase": "urgent",    "action_fr": "Corriger le qualificateur SPF (remplacer +all par ~all ou -all)",                   "action_en": "Fix the SPF qualifier (replace +all with ~all or -all)"},
    "SPF misconfigured":          {"phase": "urgent",    "action_fr": "Corriger le qualificateur SPF (remplacer +all par ~all ou -all)",                   "action_en": "Fix the SPF qualifier (replace +all with ~all or -all)"},
    "DMARC manquant":             {"phase": "urgent",    "action_fr": "Créer l'enregistrement DMARC (_dmarc.domaine.com)",                                 "action_en": "Create the DMARC record (_dmarc.yourdomain.com)"},
    "DMARC missing":              {"phase": "urgent",    "action_fr": "Créer l'enregistrement DMARC (_dmarc.domaine.com)",                                 "action_en": "Create the DMARC record (_dmarc.yourdomain.com)"},
    "DMARC présent mais en mode": {"phase": "important", "action_fr": "Passer la politique DMARC de p=none à p=quarantine puis p=reject",                  "action_en": "Upgrade DMARC policy from p=none to p=quarantine then p=reject"},
    "DKIM non détecté":           {"phase": "important", "action_fr": "Configurer DKIM pour signer les emails sortants",                                    "action_en": "Configure DKIM to sign outgoing emails"},
    "DKIM not detected":          {"phase": "important", "action_fr": "Configurer DKIM pour signer les emails sortants",                                    "action_en": "Configure DKIM to sign outgoing emails"},
    "Certificat SSL expiré":      {"phase": "urgent",    "action_fr": "Renouveler le certificat SSL immédiatement (Let's Encrypt)",                        "action_en": "Renew the SSL certificate immediately (Let's Encrypt)"},
    "SSL certificate expired":    {"phase": "urgent",    "action_fr": "Renouveler le certificat SSL immédiatement (Let's Encrypt)",                        "action_en": "Renew the SSL certificate immediately (Let's Encrypt)"},
    "Certificat SSL invalide":    {"phase": "urgent",    "action_fr": "Installer un certificat SSL valide signé par une CA reconnue",                      "action_en": "Install a valid SSL certificate signed by a recognised CA"},
    "HTTPS inaccessible":         {"phase": "urgent",    "action_fr": "Activer HTTPS (port 443) et rediriger HTTP → HTTPS",                                "action_en": "Enable HTTPS (port 443) and redirect HTTP → HTTPS"},
    "Certificat SSL expire dans": {"phase": "important", "action_fr": "Planifier le renouvellement du certificat SSL",                                     "action_en": "Schedule SSL certificate renewal"},
    "SSL certificate expires":    {"phase": "important", "action_fr": "Planifier le renouvellement du certificat SSL",                                     "action_en": "Schedule SSL certificate renewal"},
    "Version TLS obsolète":       {"phase": "important", "action_fr": "Désactiver TLS 1.0/1.1 et activer TLS 1.2/1.3 uniquement",                         "action_en": "Disable TLS 1.0/1.1 and enable TLS 1.2/1.3 only"},
    "Port(s) RDP/SMB":            {"phase": "urgent",    "action_fr": "Fermer les ports 3389 et 445 au firewall — utiliser un VPN",                        "action_en": "Close ports 3389 and 445 at the firewall — use a VPN"},
    "Protocole(s) obsolète(s)":   {"phase": "urgent",    "action_fr": "Désactiver FTP (21) et Telnet (23), passer à SFTP et SSH",                         "action_en": "Disable FTP (21) and Telnet (23), switch to SFTP and SSH"},
    "Base(s) de données":         {"phase": "urgent",    "action_fr": "Bloquer les ports BDD (3306/5432) depuis l'internet public",                       "action_en": "Block database ports (3306/5432) from the public internet"},
    "SSH (port 22)":              {"phase": "optimize",  "action_fr": "Désactiver l'auth par mot de passe SSH, utiliser des clés uniquement",              "action_en": "Disable SSH password authentication, use key-based auth only"},
}

DEFAULT_OPTIMIZE_ACTIONS_FR = [
    "Mettre en place une surveillance continue des ports (IDS/IPS)",
    "Activer la journalisation des événements de sécurité (SIEM)",
    "Mettre en place un programme de sensibilisation anti-phishing",
    "Réaliser un test d'intrusion (pentest) annuel",
    "Déployer un gestionnaire de mots de passe d'entreprise",
]

DEFAULT_OPTIMIZE_ACTIONS_EN = [
    "Set up continuous port monitoring (IDS/IPS)",
    "Enable security event logging (SIEM)",
    "Implement an anti-phishing awareness programme",
    "Conduct an annual penetration test",
    "Deploy an enterprise password manager",
]

# ── Jinja2 Environment ────────────────────────────────────────────────────────

def _build_jinja_env() -> Environment:
    env = Environment(
        loader       = FileSystemLoader(TEMPLATES_DIR),
        autoescape   = select_autoescape(["html", "xml"]),
    )

    # Filtres personnalisés
    def format_eur(n: float | int) -> str:
        """Formate un nombre en euros français : 58 000 €"""
        try:
            return f"{int(n):,} €".replace(",", "\u202f")  # espace insécable
        except (TypeError, ValueError):
            return str(n)

    def risk_class(level: str) -> str:
        return {"CRITICAL": "danger", "HIGH": "warning", "MEDIUM": "warning",
                "LOW": "ok"}.get(level, "ok")

    env.filters["format_eur"] = format_eur
    env.filters["risk_class"] = risk_class
    return env


# ── Fonction principale ───────────────────────────────────────────────────────


# ── Strings de traduction pour le template ────────────────────────────────────

PDF_STRINGS: dict[str, dict[str, str]] = {
    "fr": {
        # Couverture
        "report_type":        "Rapport d'Audit Cybersécurité",
        "report_title_1":     "Analyse de l'Empreinte",
        "report_title_2":     "Publique de Sécurité",
        "score_label":        "Security Score Global",
        "out_of":             "sur 100",
        "meta_vulns":         "Vulnérabilités",
        "meta_score":         "SecurityScore",
        "meta_date":          "Date du scan",
        "risk_prefix":        "Niveau de risque :",
        "confidential":       "CONFIDENTIEL",
        "cover_footer_1":     "Ce rapport est destiné exclusivement à",
        # En-têtes courants
        "running_audit":      "Audit Wezea",
        "footer_brand":       "Wezea Security Scanner — Rapport Confidentiel",
        # Sections internes
        "exec_summary":       "SYNTHÈSE EXÉCUTIVE",
        "details_section":    "ANALYSE DÉTAILLÉE DES VULNÉRABILITÉS",
        "action_plan":        "PLAN D'ACTION RECOMMANDÉ",
        "phase_urgent":       "URGENT",
        "phase_important":    "IMPORTANT",
        "phase_optimize":     "OPTIMISATION",
        "no_findings":        "Aucune vulnérabilité détectée",
        "no_findings_sub":    "Votre infrastructure présente une très bonne posture de sécurité.",
        # CTA
        "cta_heading_1":      "Besoin d'aide pour corriger ces vulnérabilités ?",
        "cta_heading_2":      "Notre équipe est là pour vous accompagner.",
        "cta_body":           "Ce rapport vous a montré les risques. Notre équipe vous montre comment les corriger — rapidement, efficacement, et avec un budget adapté à votre structure. Contactez-nous pour un accompagnement",
        "cta_body_strong":    "personnalisé et sans engagement",
        "cta_button":         "→ Contactez-nous",
        # Disclaimer
        "disclaimer":         "Ce rapport a été généré automatiquement par Wezea Security Scanner sur la base d'une analyse passive de l'empreinte publique de {domain} en date du {date}. Il ne constitue pas un audit de sécurité complet (test d'intrusion, audit de code, etc.). Wezea ne saurait être tenu responsable des décisions prises sur la base de ce rapport.",
        "copyright":          "© {year} Wezea · Tous droits réservés · CONFIDENTIEL",
    },
    "en": {
        # Cover
        "report_type":        "Cybersecurity Audit Report",
        "report_title_1":     "Public Security",
        "report_title_2":     "Footprint Analysis",
        "score_label":        "Global Security Score",
        "out_of":             "out of 100",
        "meta_vulns":         "Vulnerabilities",
        "meta_score":         "SecurityScore",
        "meta_date":          "Scan date",
        "risk_prefix":        "Risk level:",
        "confidential":       "CONFIDENTIAL",
        "cover_footer_1":     "This report is intended exclusively for",
        # Running headers
        "running_audit":      "Wezea Audit",
        "footer_brand":       "Wezea Security Scanner — Confidential Report",
        # Internal sections
        "exec_summary":       "EXECUTIVE SUMMARY",
        "details_section":    "DETAILED VULNERABILITY ANALYSIS",
        "action_plan":        "RECOMMENDED ACTION PLAN",
        "phase_urgent":       "URGENT",
        "phase_important":    "IMPORTANT",
        "phase_optimize":     "OPTIMISE",
        "no_findings":        "No vulnerabilities detected",
        "no_findings_sub":    "Your infrastructure has a very good security posture.",
        # CTA
        "cta_heading_1":      "Need help fixing these vulnerabilities?",
        "cta_heading_2":      "Our team is here to help.",
        "cta_body":           "This report has shown you the risks. Our team will show you how to fix them — quickly, efficiently, and within a budget suited to your organisation. Contact us for",
        "cta_body_strong":    "personalised, no-commitment support",
        "cta_button":         "→ Contact us",
        # Disclaimer
        "disclaimer":         "This report was generated automatically by Wezea Security Scanner based on a passive analysis of the public footprint of {domain} on {date}. It does not constitute a complete security audit (penetration testing, code review, etc.). Wezea shall not be held liable for decisions made on the basis of this report.",
        "copyright":          "© {year} Wezea · All rights reserved · CONFIDENTIAL",
    },
}


def generate_pdf(
    audit_data: dict[str, Any],
    lang: str = "fr",
    white_label: dict[str, Any] | None = None,
) -> bytes:
    """
    Génère un rapport PDF en mémoire à partir des données de scan.

    Args:
        audit_data:   Dictionnaire JSON issu de ScanResult.to_dict()
        lang:         Langue du rapport ("fr" | "en")
        white_label:  Dict optionnel avec les champs de marque blanche :
                      { enabled, company_name, logo_b64, primary_color }

    Returns:
        bytes: Contenu binaire du PDF

    Raises:
        RuntimeError: Si WeasyPrint ou Jinja2 échoue
    """
    try:
        from weasyprint import HTML
        from weasyprint.text.fonts import FontConfiguration
    except (ImportError, OSError) as exc:
        # ImportError : paquet pip manquant
        # OSError    : libs système manquantes (libpango, libcairo…)
        logger.error("WeasyPrint init error: %s", exc)
        raise RuntimeError(
            f"WeasyPrint indisponible (dépendances système manquantes ?) : {exc}"
        ) from exc

    env      = _build_jinja_env()
    template = env.get_template("report_template.html")
    context  = _build_context(audit_data, lang, white_label=white_label)

    try:
        html_content = template.render(**context)
    except Exception as exc:
        logger.error("Erreur rendu Jinja2 : %s", exc)
        raise RuntimeError(f"Erreur de rendu du template : {exc}") from exc

    try:
        font_config = FontConfiguration()
        pdf_bytes   = HTML(
            string   = html_content,
            base_url = TEMPLATES_DIR,
        ).write_pdf(font_config=font_config)
        return pdf_bytes
    except Exception as exc:
        logger.error("Erreur WeasyPrint : %s", exc)
        raise RuntimeError(f"Erreur de génération PDF : {exc}") from exc


# ── Construction du contexte Jinja2 ──────────────────────────────────────────

def _build_context(
    data: dict[str, Any],
    lang: str = "fr",
    white_label: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enrichit les données brutes du scan pour le template."""
    score      = int(data.get("security_score", 0))
    risk_level = str(data.get("risk_level", "CRITICAL"))
    findings   = list(data.get("findings", []))
    scan_id    = str(data.get("scan_id", "N/A"))

    # Parsing de la date de scan
    scanned_at_raw = data.get("scanned_at", datetime.now(timezone.utc).isoformat())
    try:
        dt = datetime.fromisoformat(scanned_at_raw.replace("Z", "+00:00"))
        scanned_at_display = (
            dt.strftime("%m/%d/%Y at %H:%M UTC") if lang == "en"
            else dt.strftime("%d/%m/%Y à %H:%M UTC")
        )
    except (ValueError, AttributeError):
        scanned_at_display = scanned_at_raw

    # Groupes par catégorie — toutes les catégories des auditeurs
    dns_findings        = [f for f in findings if f.get("category") == "DNS & Mail"]
    ssl_findings        = [f for f in findings if f.get("category") == "SSL / HTTPS"]
    port_findings       = [f for f in findings if f.get("category") == "Exposition des Ports"]
    header_findings     = [f for f in findings if f.get("category") == "En-têtes HTTP"]
    email_findings      = [f for f in findings if f.get("category") == "Sécurité Email"]
    tech_findings       = [f for f in findings if f.get("category") == "Exposition Technologique"]
    reputation_findings = [f for f in findings if f.get("category") == "Réputation du Domaine"]
    # Autres catégories non listées ci-dessus (ex. futures catégories)
    known_cats = {"DNS & Mail", "SSL / HTTPS", "Exposition des Ports", "En-têtes HTTP",
                  "Sécurité Email", "Exposition Technologique", "Réputation du Domaine",
                  "Sous-domaines & Certificats", "Versions Vulnérables"}
    other_findings = [f for f in findings if f.get("category") not in known_cats]

    # Compteurs
    critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
    high_count     = sum(1 for f in findings if f.get("severity") == "HIGH")
    medium_count   = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    low_count      = sum(1 for f in findings if f.get("severity") == "LOW")

    # ── White-label branding ──────────────────────────────────────────────────
    wb = white_label or {}
    wb_active       = bool(wb.get("enabled")) and bool(wb.get("company_name"))
    wb_company      = wb.get("company_name") or "Wezea"
    wb_logo         = wb.get("logo_b64")      # data URI ou None
    wb_color        = wb.get("primary_color") or "#22d3ee"  # cyan Wezea par défaut

    # Strings adaptées au branding
    base_strings = dict(PDF_STRINGS.get(lang, PDF_STRINGS["fr"]))
    if wb_active:
        if lang == "fr":
            base_strings["running_audit"] = f"Audit {wb_company}"
            base_strings["footer_brand"]  = f"{wb_company} — Rapport Confidentiel"
            base_strings["disclaimer"]    = (
                f"Ce rapport a été généré automatiquement par {wb_company} sur la base d'une "
                f"analyse passive de l'empreinte publique de {{domain}} en date du {{date}}. "
                f"Il ne constitue pas un audit de sécurité complet."
            )
            base_strings["copyright"] = f"© {{year}} {wb_company} · Tous droits réservés · CONFIDENTIEL"
        else:
            base_strings["running_audit"] = f"{wb_company} Audit"
            base_strings["footer_brand"]  = f"{wb_company} — Confidential Report"
            base_strings["disclaimer"]    = (
                f"This report was generated automatically by {wb_company} based on a passive "
                f"analysis of the public footprint of {{domain}} on {{date}}. "
                f"It does not constitute a complete security audit."
            )
            base_strings["copyright"] = f"© {{year}} {wb_company} · All rights reserved · CONFIDENTIAL"

    dns_det  = dict(data.get("dns_details", {}))
    ssl_det  = dict(data.get("ssl_details", {}))
    port_det = dict(data.get("port_details", {}))

    return {
        # Identifiants
        "domain":           data.get("domain", ""),
        "scan_id":          scan_id,
        "scanned_at":       scanned_at_display,
        "report_date":      datetime.now().strftime("%d/%m/%Y"),

        # Langue & strings UI
        "lang":             lang,
        "strings":          base_strings,

        # White-label
        "wb_active":        wb_active,
        "wb_company":       wb_company,
        "wb_logo":          wb_logo,
        "wb_color":         wb_color,

        # Score & risque
        "security_score":   score,
        "risk_level":       risk_level,
        "risk_label":       _risk_label(risk_level, lang),
        "risk_color":       _risk_color(risk_level),
        "score_color":      _score_color(score),

        # Findings — toutes catégories
        "findings":             findings,
        "dns_findings":         dns_findings,
        "ssl_findings":         ssl_findings,
        "port_findings":        port_findings,
        "header_findings":      header_findings,
        "email_findings":       email_findings,
        "tech_findings":        tech_findings,
        "reputation_findings":  reputation_findings,
        "other_findings":       other_findings,
        "critical_count":       critical_count,
        "high_count":           high_count,
        "medium_count":         medium_count,
        "low_count":            low_count,

        # Bilan des vérifications (checks passés + échoués)
        **_checks_context(data, findings, lang),

        # Recommandations & plan
        "recommendations":  list(data.get("recommendations", [])),
        "actions":          _build_action_plan(findings, lang),

        # Données brutes pour les annexes
        "dns_details":      dns_det,
        "ssl_details":      ssl_det,
        "port_details":     port_det,
        "scan_duration_ms": int(data.get("scan_duration_ms", 0)),

        # Données premium (Starter / Pro)
        "subdomain_details": dict(data.get("subdomain_details", {})),
        "vuln_details":      dict(data.get("vuln_details", {})),
        "subdomain_findings": [f for f in findings if f.get("category") == "Sous-domaines & Certificats"],
        "vuln_findings":      [f for f in findings if f.get("category") == "Versions Vulnérables"],
        "is_premium":         bool(data.get("subdomain_details") or data.get("vuln_details")),
    }


def _build_action_plan(findings: list[dict], lang: str = "fr") -> dict[str, list[str]]:
    """
    Génère un plan d'action en 3 phases depuis les findings.
    Retourne : { "urgent": [...], "important": [...], "optimize": [...] }
    """
    action_key = "action_en" if lang == "en" else "action_fr"
    default_optimize = DEFAULT_OPTIMIZE_ACTIONS_EN if lang == "en" else DEFAULT_OPTIMIZE_ACTIONS_FR

    urgent: list[str]    = []
    important: list[str] = []
    optimize: list[str]  = list(default_optimize[:2])  # actions génériques de base

    seen_actions: set[str] = set()

    for finding in findings:
        title = finding.get("title", "")
        # Cherche la première clé correspondante dans le mapping
        for key, info in FINDING_ACTIONS.items():
            if key.lower() in title.lower():
                action = info[action_key]
                if action not in seen_actions:
                    seen_actions.add(action)
                    if info["phase"] == "urgent":
                        urgent.append(action)
                    elif info["phase"] == "important":
                        important.append(action)
                    else:
                        optimize.append(action)
                break

    # Compléter optimize si peu d'items
    for extra in default_optimize[2:]:
        if extra not in seen_actions and len(optimize) < 5:
            optimize.append(extra)

    return {"urgent": urgent, "important": important, "optimize": optimize}


# ── Bilan des vérifications ──────────────────────────────────────────────────

def _checks_context(data: dict, findings: list, lang: str) -> dict:
    """Retourne checks_overview + les 3 compteurs pour le template."""
    checks = _derive_checks_overview(data, findings, lang)
    passed  = sum(1 for c in checks if c["passed"] and not c["warning"])
    warn    = sum(1 for c in checks if c["warning"])
    failed  = sum(1 for c in checks if not c["passed"] and not c["warning"])
    return {
        "checks_overview":       checks,
        "passed_checks_count":   passed,
        "warn_checks_count":     warn,
        "fail_checks_count":     failed,
    }


def _derive_checks_overview(
    data: dict[str, Any],
    findings: list[dict],
    lang: str = "fr",
) -> list[dict]:
    """
    Dérive la liste complète des vérifications effectuées (passées ET échouées)
    à partir des findings et des détails bruts du scan.

    Retourne une liste de dicts :
    {
      category: str,          # Groupe d'affichage
      icon:     str,          # Emoji
      label_fr: str,
      label_en: str,
      passed:   bool,         # True = OK, False = problème détecté
      warning:  bool,         # True = présent mais sous-optimal (ex DMARC p=none)
      detail_fr: str,         # Valeur courte ou statut
      detail_en: str,
    }
    """
    dns_det  = data.get("dns_details",  {}) or {}
    ssl_det  = data.get("ssl_details",  {}) or {}
    port_det = data.get("port_details", {}) or {}

    # Titres de findings en minuscules pour recherche rapide
    failed_titles = {f.get("title", "").lower() for f in findings}

    def _failed(*keywords: str) -> bool:
        return any(any(kw.lower() in t for kw in keywords) for t in failed_titles)

    checks: list[dict] = []

    # ── DNS & Mail ────────────────────────────────────────────────────────────
    spf_status   = dns_det.get("spf",   {}).get("status",  "missing")
    dmarc_status = dns_det.get("dmarc", {}).get("status",  "missing")
    dmarc_policy = dns_det.get("dmarc", {}).get("policy",  "")
    spf_records  = dns_det.get("spf",   {}).get("records", [])

    spf_ok   = (spf_status == "ok")
    spf_warn = (spf_status == "misconfigured")
    checks.append({
        "category": "DNS & Mail" if lang == "fr" else "DNS & Mail",
        "icon": "✉",
        "label_fr": "SPF anti-spoofing",
        "label_en": "SPF anti-spoofing",
        "passed":   spf_ok,
        "warning":  spf_warn,
        "detail_fr": (spf_records[0][:55] + "…" if spf_records and len(spf_records[0]) > 55 else spf_records[0]) if spf_ok else ("Mal configuré (+all)" if spf_warn else "Enregistrement absent"),
        "detail_en": (spf_records[0][:55] + "…" if spf_records and len(spf_records[0]) > 55 else spf_records[0]) if spf_ok else ("Misconfigured (+all)" if spf_warn else "Record absent"),
    })

    dmarc_ok   = (dmarc_status == "ok" and dmarc_policy in ("quarantine", "reject"))
    dmarc_warn = (dmarc_status == "ok" and dmarc_policy == "none")
    checks.append({
        "category": "DNS & Mail",
        "icon": "✉",
        "label_fr": "DMARC anti-phishing",
        "label_en": "DMARC anti-phishing",
        "passed":   dmarc_ok,
        "warning":  dmarc_warn,
        "detail_fr": (f"p={dmarc_policy} ✓" if dmarc_ok else (f"p=none (surveillance seulement)" if dmarc_warn else "Enregistrement absent")),
        "detail_en": (f"p={dmarc_policy} ✓" if dmarc_ok else (f"p=none (monitoring only)" if dmarc_warn else "Record absent")),
    })

    dkim_ok = not _failed("dkim non détecté", "dkim not detected", "dkim")
    checks.append({
        "category": "DNS & Mail",
        "icon": "✉",
        "label_fr": "DKIM signature email",
        "label_en": "DKIM email signing",
        "passed":   dkim_ok,
        "warning":  False,
        "detail_fr": "Signature détectée" if dkim_ok else "Non configuré",
        "detail_en": "Signature detected" if dkim_ok else "Not configured",
    })

    mx_ok = not _failed("mx", "serveur mail absent", "no mail server")
    checks.append({
        "category": "DNS & Mail",
        "icon": "✉",
        "label_fr": "Serveur mail (MX)",
        "label_en": "Mail server (MX)",
        "passed":   mx_ok,
        "warning":  False,
        "detail_fr": "Enregistrement MX présent" if mx_ok else "Aucun MX configuré",
        "detail_en": "MX record present"          if mx_ok else "No MX configured",
    })

    # ── SSL / HTTPS ───────────────────────────────────────────────────────────
    ssl_valid = (ssl_det.get("status") == "valid")
    issuer_name = (ssl_det.get("issuer") or {}).get("organizationName", "") or (ssl_det.get("issuer") or {}).get("O", "")
    checks.append({
        "category": "SSL / HTTPS",
        "icon": "🔒",
        "label_fr": "Certificat SSL valide",
        "label_en": "Valid SSL certificate",
        "passed":   ssl_valid,
        "warning":  False,
        "detail_fr": (issuer_name[:40] or "Valide") if ssl_valid else "Invalide ou absent",
        "detail_en": (issuer_name[:40] or "Valid")  if ssl_valid else "Invalid or absent",
    })

    tls_version = ssl_det.get("tls_version", "")
    tls_ok = tls_version in ("TLSv1.2", "TLSv1.3")
    tls_warn = bool(tls_version) and not tls_ok
    checks.append({
        "category": "SSL / HTTPS",
        "icon": "🔒",
        "label_fr": "Version TLS",
        "label_en": "TLS Version",
        "passed":   tls_ok,
        "warning":  tls_warn,
        "detail_fr": tls_version or "Non détecté",
        "detail_en": tls_version or "Not detected",
    })

    days_left = ssl_det.get("days_left")
    cert_exp_ok   = days_left is not None and int(days_left) > 30
    cert_exp_warn = days_left is not None and 0 < int(days_left) <= 30
    cert_exp_fail = days_left is not None and int(days_left) <= 0
    checks.append({
        "category": "SSL / HTTPS",
        "icon": "🔒",
        "label_fr": "Expiration certificat",
        "label_en": "Certificate expiry",
        "passed":   cert_exp_ok,
        "warning":  cert_exp_warn,
        "detail_fr": (f"{days_left} jours restants" if days_left is not None else "N/A"),
        "detail_en": (f"{days_left} days remaining" if days_left is not None else "N/A"),
    })

    https_open = port_det.get("443", {}).get("open", False)
    checks.append({
        "category": "SSL / HTTPS",
        "icon": "🔒",
        "label_fr": "HTTPS accessible (port 443)",
        "label_en": "HTTPS accessible (port 443)",
        "passed":   https_open,
        "warning":  False,
        "detail_fr": "Port 443 ouvert"        if https_open else "Port 443 inaccessible",
        "detail_en": "Port 443 open"           if https_open else "Port 443 inaccessible",
    })

    hsts_ok = not _failed("strict-transport-security", "hsts")
    checks.append({
        "category": "SSL / HTTPS",
        "icon": "🔒",
        "label_fr": "En-tête HSTS",
        "label_en": "HSTS header",
        "passed":   hsts_ok,
        "warning":  False,
        "detail_fr": "Strict-Transport-Security présent" if hsts_ok else "En-tête manquant",
        "detail_en": "Strict-Transport-Security present" if hsts_ok else "Header missing",
    })

    # ── Ports réseau ──────────────────────────────────────────────────────────
    DANGEROUS_PORTS = {
        3389: ("RDP", "Bureau distant"),
        445:  ("SMB", "Partage Windows"),
        21:   ("FTP", "Transfert non chiffré"),
        23:   ("Telnet", "Protocole obsolète"),
        3306: ("MySQL", "Base de données"),
        5432: ("PostgreSQL", "Base de données"),
        1433: ("MSSQL", "Base de données"),
    }
    for port_num, (svc, label_fr) in DANGEROUS_PORTS.items():
        pdata   = port_det.get(str(port_num), {})
        is_open = pdata.get("open", False)
        checks.append({
            "category": "Ports Réseau",
            "icon": "🌐",
            "label_fr": f"Port {port_num} ({svc})",
            "label_en": f"Port {port_num} ({svc})",
            "passed":   not is_open,
            "warning":  False,
            "detail_fr": "Fermé" if not is_open else f"OUVERT — {label_fr}",
            "detail_en": "Closed" if not is_open else f"OPEN — exposed service",
        })

    # SSH (22) : ouvert = warning (pas forcément dangereux, mais à surveiller)
    ssh_data = port_det.get("22", {})
    ssh_open = ssh_data.get("open", False)
    checks.append({
        "category": "Ports Réseau",
        "icon": "🌐",
        "label_fr": "Port 22 (SSH)",
        "label_en": "Port 22 (SSH)",
        "passed":   not ssh_open,
        "warning":  ssh_open,   # SSH ouvert = warning, pas failure directe
        "detail_fr": "Fermé" if not ssh_open else "Ouvert — auth par clé recommandée",
        "detail_en": "Closed" if not ssh_open else "Open — key-based auth recommended",
    })

    # ── En-têtes HTTP ─────────────────────────────────────────────────────────
    HEADER_CHECKS = [
        ("x-frame-options", "X-Frame-Options (anti-clickjacking)", "X-Frame-Options (clickjacking)"),
        ("content-security-policy", "Content-Security-Policy", "Content-Security-Policy"),
        ("x-content-type-options", "X-Content-Type-Options", "X-Content-Type-Options"),
        ("permissions-policy",     "Permissions-Policy", "Permissions-Policy"),
    ]
    for kw, label_fr, label_en in HEADER_CHECKS:
        ok = not _failed(kw)
        checks.append({
            "category": "En-têtes HTTP",
            "icon": "📋",
            "label_fr": label_fr,
            "label_en": label_en,
            "passed":   ok,
            "warning":  False,
            "detail_fr": "En-tête présent" if ok else "En-tête manquant",
            "detail_en": "Header present"  if ok else "Header missing",
        })

    # ── Réputation ────────────────────────────────────────────────────────────
    rep_ok = not _failed("liste noire", "blacklist", "dnsbl", "spam", "réputation")
    checks.append({
        "category": "Réputation",
        "icon": "🛡",
        "label_fr": "Listes noires (DNSBL)",
        "label_en": "Blacklists (DNSBL)",
        "passed":   rep_ok,
        "warning":  False,
        "detail_fr": "Domaine propre" if rep_ok else "Figurant dans une liste noire",
        "detail_en": "Clean domain"   if rep_ok else "Listed in a blacklist",
    })

    return checks


# ── Helpers couleur ───────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 70:
        return "#16a34a"   # green
    elif score >= 40:
        return "#ea580c"   # orange
    else:
        return "#dc2626"   # red


def _risk_color(level: str) -> str:
    return {
        "CRITICAL": "#dc2626",
        "HIGH":     "#ea580c",
        "MEDIUM":   "#d97706",
        "LOW":      "#16a34a",
    }.get(level, "#64748b")


def _risk_label(level: str, lang: str = "fr") -> str:
    labels = {
        "fr": {"CRITICAL": "Critique", "HIGH": "Élevé",    "MEDIUM": "Modéré", "LOW": "Faible"},
        "en": {"CRITICAL": "Critical", "HIGH": "High",     "MEDIUM": "Moderate","LOW": "Low"},
    }
    return labels.get(lang, labels["fr"]).get(level, level)
