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
    # ── Nouveaux checks (session 30) ──────────────────────────────────────────
    "DNSSEC non activé":               {"phase": "optimize",  "action_fr": "Activer DNSSEC sur votre registrar de domaine",                                                  "action_en": "Enable DNSSEC at your domain registrar"},
    "DNSSEC not enabled":              {"phase": "optimize",  "action_fr": "Activer DNSSEC sur votre registrar de domaine",                                                  "action_en": "Enable DNSSEC at your domain registrar"},
    "CAA record missing":              {"phase": "optimize",  "action_fr": "Ajouter un enregistrement CAA pour restreindre les CA autorisées à émettre des certificats",    "action_en": "Add a CAA DNS record to restrict which CAs can issue certificates for your domain"},
    "Perfect Forward Secrecy missing": {"phase": "important", "action_fr": "Configurer des suites ECDHE/DHE sur votre serveur TLS pour activer PFS",                        "action_en": "Configure ECDHE/DHE cipher suites on your TLS server to enable PFS"},
    "Cipher faible accepté":           {"phase": "important", "action_fr": "Désactiver les ciphers faibles (3DES, RC4, NULL) sur le serveur TLS",                           "action_en": "Disable weak ciphers (3DES, RC4, NULL) on the TLS server"},
    "Cipher key too short":            {"phase": "important", "action_fr": "Activer des clés TLS d'au moins 128 bits — désactiver les algorithmes faibles",                 "action_en": "Enable TLS keys of at least 128 bits — disable weak algorithms"},
    "Pas de redirection HTTP":         {"phase": "urgent",    "action_fr": "Configurer une redirection 301 permanente HTTP → HTTPS dans votre serveur web",                 "action_en": "Configure a permanent 301 HTTP → HTTPS redirect on your web server"},
    "No HTTP → HTTPS redirect":        {"phase": "urgent",    "action_fr": "Configurer une redirection 301 permanente HTTP → HTTPS dans votre serveur web",                 "action_en": "Configure a permanent 301 HTTP → HTTPS redirect on your web server"},
    "MTA-STS non configuré":           {"phase": "optimize",  "action_fr": "Déployer MTA-STS pour forcer le chiffrement TLS des emails entrants",                           "action_en": "Deploy MTA-STS to enforce TLS encryption for inbound emails"},
    "MTA-STS not configured":          {"phase": "optimize",  "action_fr": "Déployer MTA-STS pour forcer le chiffrement TLS des emails entrants",                           "action_en": "Deploy MTA-STS to enforce TLS encryption for inbound emails"},
    "Permissions-Policy absent":       {"phase": "optimize",  "action_fr": "Ajouter l'en-tête Permissions-Policy pour restreindre les API navigateur exposées",             "action_en": "Add a Permissions-Policy header to restrict exposed browser APIs"},
    "Permissions-Policy missing":      {"phase": "optimize",  "action_fr": "Ajouter l'en-tête Permissions-Policy pour restreindre les API navigateur exposées",             "action_en": "Add a Permissions-Policy header to restrict exposed browser APIs"},
    "Domaine expiré":                  {"phase": "urgent",    "action_fr": "Renouveler le nom de domaine immédiatement — risque de perte irréversible",                     "action_en": "Renew the domain name immediately — risk of irreversible loss"},
    "Domain expired":                  {"phase": "urgent",    "action_fr": "Renouveler le nom de domaine immédiatement — risque de perte irréversible",                     "action_en": "Renew the domain name immediately — risk of irreversible loss"},
    "Domaine expire dans":             {"phase": "urgent",    "action_fr": "Renouveler le nom de domaine en urgence avant son expiration",                                   "action_en": "Renew the domain name urgently before it expires"},
    "Domain expires in":               {"phase": "urgent",    "action_fr": "Renouveler le nom de domaine en urgence avant son expiration",                                   "action_en": "Renew the domain name urgently before it expires"},
    # ── Breach Detection (session 34) ─────────────────────────────────────────
    "Domaine trouvé dans":             {"phase": "urgent",    "action_fr": "Réinitialiser les mots de passe compromis et activer le 2FA sur tous les comptes",            "action_en": "Reset compromised passwords and enable 2FA on all accounts"},
    "Domain found in":                 {"phase": "urgent",    "action_fr": "Réinitialiser les mots de passe compromis et activer le 2FA sur tous les comptes",            "action_en": "Reset compromised passwords and enable 2FA on all accounts"},
    # ── Secret Scanner (session 35) ───────────────────────────────────────────
    "AWS Access Key":                  {"phase": "urgent",    "action_fr": "Révoquer la clé AWS IAM immédiatement et auditer les accès récents dans CloudTrail",         "action_en": "Revoke the AWS IAM key immediately and audit recent access in CloudTrail"},
    "Stripe Live Secret":              {"phase": "urgent",    "action_fr": "Révoquer la clé Stripe sk_live dans Stripe Dashboard → Developers → API keys",               "action_en": "Revoke the sk_live Stripe key in Stripe Dashboard → Developers → API keys"},
    "GitHub Personal Access":         {"phase": "urgent",    "action_fr": "Révoquer le token GitHub dans Settings → Developer settings → Personal access tokens",       "action_en": "Revoke the GitHub token in Settings → Developer settings → Personal access tokens"},
    "PEM Private Key":                 {"phase": "urgent",    "action_fr": "Révoquer et régénérer le certificat TLS — supprimer la clé privée du code frontend",         "action_en": "Revoke and regenerate the TLS certificate — remove the private key from frontend code"},
    "Stripe Test Secret":              {"phase": "important", "action_fr": "Déplacer la clé Stripe test dans les variables d'environnement serveur uniquement",           "action_en": "Move the Stripe test key to server-side environment variables only"},
    "SendGrid API Key":                {"phase": "urgent",    "action_fr": "Révoquer la clé SendGrid et déplacer les appels email dans le backend",                       "action_en": "Revoke the SendGrid key and move email calls to the backend"},
    "Slack Bot":                       {"phase": "urgent",    "action_fr": "Révoquer le token Slack dans votre app → OAuth & Permissions",                               "action_en": "Revoke the Slack token in your app → OAuth & Permissions"},
    "Google API Key":                  {"phase": "important", "action_fr": "Restreindre la clé Google API par domaine HTTP dans Google Cloud Console → Credentials",     "action_en": "Restrict the Google API key by HTTP referrer in Google Cloud Console → Credentials"},
    "Firebase Server Key":             {"phase": "urgent",    "action_fr": "Révoquer la clé serveur Firebase dans Firebase Console → Project Settings → Cloud Messaging","action_en": "Revoke the Firebase server key in Firebase Console → Project Settings → Cloud Messaging"},
    "Brevo":                           {"phase": "urgent",    "action_fr": "Révoquer la clé API Brevo dans SMTP & API → API Keys",                                        "action_en": "Revoke the Brevo API key in SMTP & API → API Keys"},
    # ── DAST actif (session 35) ───────────────────────────────────────────────
    "XSS réfléchi":                    {"phase": "urgent",    "action_fr": "Encoder toutes les sorties HTML côté serveur et activer une Content-Security-Policy stricte", "action_en": "HTML-encode all server-side output and enable a strict Content-Security-Policy"},
    "Reflected XSS":                   {"phase": "urgent",    "action_fr": "Encoder toutes les sorties HTML côté serveur et activer une Content-Security-Policy stricte", "action_en": "HTML-encode all server-side output and enable a strict Content-Security-Policy"},
    "Injection SQL":                   {"phase": "urgent",    "action_fr": "Remplacer les requêtes SQL dynamiques par des requêtes paramétrées (prepared statements)",   "action_en": "Replace dynamic SQL queries with parameterised queries (prepared statements)"},
    "SQL injection":                   {"phase": "urgent",    "action_fr": "Remplacer les requêtes SQL dynamiques par des requêtes paramétrées (prepared statements)",   "action_en": "Replace dynamic SQL queries with parameterised queries (prepared statements)"},
    "Formulaire POST sans":            {"phase": "important", "action_fr": "Ajouter un token CSRF unique et aléatoire sur chaque formulaire POST, validé côté serveur",   "action_en": "Add a unique random CSRF token to every POST form, validated server-side"},
    "POST form without CSRF":          {"phase": "important", "action_fr": "Ajouter un token CSRF unique et aléatoire sur chaque formulaire POST, validé côté serveur",   "action_en": "Add a unique random CSRF token to every POST form, validated server-side"},
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
    infra_findings      = [f for f in findings if f.get("category") == "Infrastructure"]
    breach_findings     = [f for f in findings if f.get("category") == "Fuites de données"]
    # Autres catégories non listées ci-dessus (ex. futures catégories)
    known_cats = {"DNS & Mail", "SSL / HTTPS", "Exposition des Ports", "En-têtes HTTP",
                  "Sécurité Email", "Exposition Technologique", "Réputation du Domaine",
                  "Sous-domaines & Certificats", "Versions Vulnérables", "Fuites de données",
                  "Infrastructure", "Secrets exposés", "Exposed Secrets", "DAST"}
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

    dns_det  = dict(data.get("dns_details",  {}) or {})
    ssl_det  = dict(data.get("ssl_details",  {}) or {})
    port_det = dict(data.get("port_details", {}) or {})

    # ── Gradient de couverture dynamique selon le niveau de risque ────────────
    _cover_gradients = {
        "CRITICAL": "linear-gradient(160deg, #0f172a 0%, #7f1d1d 52%, #450a0a 100%)",
        "HIGH":     "linear-gradient(160deg, #0f172a 0%, #7c2d12 52%, #431407 100%)",
        "MEDIUM":   "linear-gradient(160deg, #0f172a 0%, #1e3a8a 52%, #312e81 100%)",
        "LOW":      "linear-gradient(160deg, #0f172a 0%, #14532d 52%, #052e16 100%)",
    }
    cover_gradient = _cover_gradients.get(risk_level, _cover_gradients["MEDIUM"])

    return {
        # Identifiants
        "domain":           data.get("domain", ""),
        "scan_id":          scan_id,
        "scanned_at":       scanned_at_display,
        "report_date":      datetime.now().strftime("%m/%d/%Y" if lang == "en" else "%d/%m/%Y"),

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
        "infra_findings":       infra_findings,
        "breach_findings":      breach_findings,
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
        # Section "What a hacker sees" — scénarios d'attaque CRITICAL/HIGH
        "hacker_scenarios":  _hacker_scenarios(findings, lang),
        # Gradient couverture dynamique selon risque
        "cover_gradient":    cover_gradient,
        # Benchmark maturité — score moyen des entreprises (injecté par main.py)
        "industry_avg":      int(data.get("industry_avg", 58)),
        # Conformité NIS2 / RGPD — 12 critères mappés depuis les findings
        "compliance":        _build_compliance_context(findings, lang),
    }


# ── Conformité NIS2 / RGPD ────────────────────────────────────────────────────

_SEV_RANK: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

_COMPLIANCE_CRITERIA = [
    # ── 5 critères "basiques" (équivalents à la vue gratuite frontend) ─────────
    {
        "id": "https",
        "label_fr": "HTTPS & Chiffrement actif",
        "label_en": "HTTPS & Active Encryption",
        "regulations": ["NIS2", "RGPD"],
        "article": "Art. 21 NIS2 · Art. 32 RGPD",
        "desc_fr": "Tout le trafic doit être chiffré via HTTPS. Le certificat SSL doit être valide et la redirection HTTP → HTTPS active.",
        "desc_en": "All traffic must be encrypted via HTTPS. SSL certificate must be valid and HTTP → HTTPS redirect active.",
        "check": lambda findings: (
            "fail" if any(
                _SEV_RANK.get(str(f.get("severity","")),0) >= 4 and f.get("category") == "SSL / HTTPS"
                for f in findings
            ) or any(
                any(w in (f.get("title","")).lower() for w in ["http", "redirect", "https"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "warn" if any(
                _SEV_RANK.get(str(f.get("severity","")),0) >= 3 and f.get("category") == "SSL / HTTPS"
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "tls",
        "label_fr": "Protocole TLS à jour",
        "label_en": "Up-to-date TLS Protocol",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "TLS 1.2 minimum requis. TLS 1.0 et 1.1 sont officiellement dépréciés depuis 2021 et ne doivent plus être utilisés.",
        "desc_en": "TLS 1.2 minimum required. TLS 1.0 and 1.1 have been officially deprecated since 2021.",
        "check": lambda findings: (
            "fail" if any(
                any(w in (f.get("title","")).lower() for w in ["tls 1.0", "tls 1.1", "tlsv1.0", "tlsv1.1", "deprecated", "cipher faible"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "warn" if any(
                any(w in (f.get("title","")).lower() for w in ["perfect forward", "pfs"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "dmarc",
        "label_fr": "Protection anti-usurpation (DMARC)",
        "label_en": "Anti-spoofing Protection (DMARC)",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "DMARC avec p=quarantine ou p=reject protège votre domaine contre le phishing par usurpation d'identité.",
        "desc_en": "DMARC with p=quarantine or p=reject protects your domain against impersonation phishing.",
        "check": lambda findings: (
            "fail" if any(
                "dmarc" in (f.get("title","")).lower()
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "warn" if any(
                "dmarc" in (f.get("title","")).lower()
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "headers",
        "label_fr": "En-têtes de sécurité HTTP",
        "label_en": "HTTP Security Headers",
        "regulations": ["RGPD"],
        "article": "Art. 25 RGPD",
        "desc_fr": "HSTS, CSP et X-Frame-Options réduisent la surface d'attaque XSS/clickjacking et protègent vos visiteurs.",
        "desc_en": "HSTS, CSP and X-Frame-Options reduce the XSS/clickjacking attack surface and protect visitors.",
        "check": lambda findings: (
            "fail" if any(
                f.get("category") == "En-têtes HTTP"
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "warn" if any(
                f.get("category") == "En-têtes HTTP"
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "spf",
        "label_fr": "Authentification email (SPF)",
        "label_en": "Email Authentication (SPF)",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "SPF strict (-all) empêche les tiers d'envoyer des emails en usurpant votre domaine.",
        "desc_en": "Strict SPF (-all) prevents third parties from sending emails by spoofing your domain.",
        "check": lambda findings: (
            "fail" if any(
                "spf" in (f.get("title","")).lower()
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "warn" if any(
                "spf" in (f.get("title","")).lower()
                and "+all" in (f.get("title","")).lower()
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "pass"
        ),
    },
    # ── 7 critères "premium" (équivalents à la vue floue frontend) ─────────────
    {
        "id": "dkim",
        "label_fr": "Signature DKIM des emails",
        "label_en": "DKIM Email Signing",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "DKIM garantit l'intégrité et l'authenticité cryptographique des emails sortants.",
        "desc_en": "DKIM guarantees the integrity and cryptographic authenticity of outgoing emails.",
        "check": lambda findings: (
            "fail" if any(
                "dkim" in (f.get("title","")).lower()
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "dnssec",
        "label_fr": "Sécurité DNS (DNSSEC + CAA)",
        "label_en": "DNS Security (DNSSEC + CAA)",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "DNSSEC protège contre la falsification DNS. CAA limite les autorités autorisées à émettre des certificats SSL.",
        "desc_en": "DNSSEC protects against DNS forgery. CAA restricts which certificate authorities can issue SSL certificates.",
        "check": lambda findings: (
            "warn" if any(
                any(w in (f.get("title","")).lower() for w in ["dnssec", "caa"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 1
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "ports",
        "label_fr": "Ports dangereux exposés",
        "label_en": "Dangerous Exposed Ports",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "RDP, SMB, MySQL, Redis, Elasticsearch ne doivent jamais être accessibles depuis internet.",
        "desc_en": "RDP, SMB, MySQL, Redis, Elasticsearch must never be accessible from the internet.",
        "check": lambda findings: (
            "fail" if any(
                f.get("category") == "Exposition des Ports"
                and any(w in (f.get("title","")).lower() for w in ["rdp", "smb", "mysql", "redis", "mongo", "elastic"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "reputation",
        "label_fr": "Réputation et blacklists",
        "label_en": "Reputation and Blacklists",
        "regulations": ["RGPD"],
        "article": "Art. 32 RGPD",
        "desc_fr": "Votre domaine et IP ne doivent pas figurer sur les listes noires email ou malware.",
        "desc_en": "Your domain and IP must not appear on email or malware blacklists.",
        "check": lambda findings: (
            "fail" if any(
                f.get("category") == "Réputation du Domaine"
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "credentials",
        "label_fr": "Credentials exposés dans le code",
        "label_en": "Exposed Credentials in Code",
        "regulations": ["RGPD"],
        "article": "Art. 32 RGPD",
        "desc_fr": "Aucune clé API, token ou secret ne doit être visible dans le source HTML ou JavaScript public.",
        "desc_en": "No API key, token or secret should be visible in public HTML or JavaScript source.",
        "check": lambda findings: (
            "fail" if any(
                any(w in (f.get("title","")).lower() for w in ["credential", "secret", "token", "api key", "clé", "exposed"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "expiry",
        "label_fr": "Expiration du domaine",
        "label_en": "Domain Expiration",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "Un domaine expiré rend votre infrastructure inaccessible et peut être récupéré par un acteur malveillant.",
        "desc_en": "An expired domain makes your infrastructure inaccessible and can be seized by a malicious actor.",
        "check": lambda findings: (
            "fail" if any(
                any(w in (f.get("title","")).lower() for w in ["domain", "expir", "renouvell"])
                and _SEV_RANK.get(str(f.get("severity","")),0) == 4
                for f in findings
            )
            else "warn" if any(
                any(w in (f.get("title","")).lower() for w in ["domain", "expir", "renouvell"])
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 2
                for f in findings
            )
            else "pass"
        ),
    },
    {
        "id": "versions",
        "label_fr": "Logiciels et versions vulnérables",
        "label_en": "Vulnerable Software Versions",
        "regulations": ["NIS2"],
        "article": "Art. 21 NIS2",
        "desc_fr": "CMS, serveurs et frameworks doivent être à jour. Les versions avec CVE connues doivent être mises à jour.",
        "desc_en": "CMS, servers and frameworks must be up to date. Versions with known CVEs must be updated.",
        "check": lambda findings: (
            "fail" if any(
                f.get("category") == "Versions Vulnérables"
                and _SEV_RANK.get(str(f.get("severity","")),0) == 4
                for f in findings
            )
            else "warn" if any(
                f.get("category") == "Versions Vulnérables"
                and _SEV_RANK.get(str(f.get("severity","")),0) >= 3
                for f in findings
            )
            else "pass"
        ),
    },
]

_STATUS_LABEL = {
    "fr": {"pass": "Conforme", "warn": "Avertissement", "fail": "Non conforme", "unknown": "Non vérifié"},
    "en": {"pass": "Compliant", "warn": "Warning",       "fail": "Non-compliant", "unknown": "Not checked"},
}
_STATUS_COLOR = {"pass": "#4ade80", "warn": "#fbbf24", "fail": "#f87171", "unknown": "#94a3b8"}


def _build_compliance_context(findings: list[dict], lang: str = "fr") -> dict:
    """
    Évalue les 12 critères NIS2/RGPD depuis les findings du scan.
    Porte la logique de CompliancePage.tsx côté serveur pour inclusion dans le PDF.

    Retourne :
        {
          criteria: list[dict]   - chaque critère avec son statut
          score: int             - % critères conformes (0-100)
          pass_count: int
          warn_count: int
          fail_count: int
        }
    """
    labels     = _STATUS_LABEL.get(lang, _STATUS_LABEL["fr"])
    label_key  = "label_fr" if lang != "en" else "label_en"
    desc_key   = "desc_fr"  if lang != "en" else "desc_en"

    results = []
    for crit in _COMPLIANCE_CRITERIA:
        try:
            status = crit["check"](findings)
        except Exception:
            status = "unknown"
        results.append({
            "id":           crit["id"],
            "label":        crit[label_key],
            "regulations":  crit["regulations"],
            "article":      crit["article"],
            "desc":         crit[desc_key],
            "status":       status,
            "status_label": labels.get(status, status),
            "status_color": _STATUS_COLOR.get(status, "#94a3b8"),
        })

    pass_count  = sum(1 for r in results if r["status"] == "pass")
    warn_count  = sum(1 for r in results if r["status"] == "warn")
    fail_count  = sum(1 for r in results if r["status"] == "fail")
    total       = len(results)
    score       = round((pass_count / total) * 100) if total else 0

    overall = (
        "fail"    if fail_count >= 3
        else "fail"  if any(r["status"] == "fail" and "NIS2" in r["regulations"] for r in results)
        else "warn"  if fail_count > 0 or warn_count > 0
        else "pass"
    )

    overall_labels = {
        "fr": {"pass": "Conforme", "warn": "Partiellement conforme", "fail": "Non conforme"},
        "en": {"pass": "Compliant", "warn": "Partially compliant",   "fail": "Non-compliant"},
    }
    ol = overall_labels.get(lang, overall_labels["fr"])

    return {
        "criteria":        results,
        "score":           score,
        "pass_count":      pass_count,
        "warn_count":      warn_count,
        "fail_count":      fail_count,
        "total":           total,
        "overall_status":  overall,
        "overall_label":   ol.get(overall, overall),
        "overall_color":   _STATUS_COLOR.get(overall, "#94a3b8"),
    }


def _hacker_scenarios(findings: list[dict], lang: str = "fr") -> list[dict]:
    """
    Génère les scénarios d'attaque pour la section "Ce qu'un pirate voit".
    Filtre les findings CRITICAL et HIGH, et pour chacun retourne un dict avec :
      - title, category, severity (du finding original)
      - attacker_action  : ce que l'attaquant fait concrètement
      - exploit_time     : temps estimé pour exploiter
      - impact           : conséquence concrète pour l'entreprise
      - diagram_target   : cible affichée dans le schéma d'attaque
    """
    fr = lang != "en"

    # Table de correspondance : clé (sous-chaîne du titre) → scénario bilingue
    SCENARIOS = [
        {
            "keys": ["rdp", "smb", "3389", "445"],
            "action_fr":   "Lance un outil de brute-force automatisé sur le port RDP/SMB. "
                           "En quelques minutes, il teste des milliers de combinaisons "
                           "identifiant/mot de passe. Une fois connecté, il déploie un ransomware "
                           "qui chiffre tous vos fichiers et demande une rançon en bitcoin.",
            "action_en":   "Runs an automated brute-force tool against the RDP/SMB port. "
                           "Within minutes, it tests thousands of username/password combinations. "
                           "Once connected, it deploys ransomware that encrypts all your files "
                           "and demands a bitcoin ransom.",
            "time_fr":     "< 1 heure",
            "time_en":     "< 1 hour",
            "impact_fr":   "Tous vos fichiers chiffrés. Rançon moyenne : 50 000 €.",
            "impact_en":   "All files encrypted. Average ransom demand: $50,000.",
            "target_fr":   "Serveur Windows",
            "target_en":   "Windows Server",
        },
        {
            "keys": ["mysql", "3306", "postgresql", "5432", "base de données", "database"],
            "action_fr":   "Détecte le port de base de données ouvert et tente une connexion "
                           "avec des identifiants par défaut (root/root, admin/admin…). "
                           "En cas de succès, il exporte l'intégralité de votre base de données : "
                           "clients, mots de passe, données financières.",
            "action_en":   "Detects the exposed database port and attempts a connection "
                           "using default credentials (root/root, admin/admin…). "
                           "If successful, exports your entire database: "
                           "customers, passwords, financial data.",
            "time_fr":     "< 10 minutes",
            "time_en":     "< 10 minutes",
            "impact_fr":   "Vol total de la base de données. RGPD : amendes jusqu'à 4 % du CA.",
            "impact_en":   "Full database exfiltration. GDPR fines up to 4% of annual revenue.",
            "target_fr":   "Base de données",
            "target_en":   "Database server",
        },
        {
            "keys": ["ftp", "telnet", "21", "23", "texte clair", "plaintext", "cleartext"],
            "action_fr":   "Se place entre votre réseau et votre serveur (attaque man-in-the-middle). "
                           "FTP et Telnet transmettent vos identifiants en clair sur le réseau : "
                           "l'attaquant les capture en temps réel avec un simple outil de sniffing.",
            "action_en":   "Positions itself between your network and server (man-in-the-middle attack). "
                           "FTP and Telnet transmit credentials in plaintext: "
                           "the attacker captures them in real time with a basic sniffing tool.",
            "time_fr":     "Immédiat",
            "time_en":     "Immediate",
            "impact_fr":   "Identifiants volés, accès total au serveur.",
            "impact_en":   "Stolen credentials, full server access.",
            "target_fr":   "Serveur FTP / Telnet",
            "target_en":   "FTP / Telnet server",
        },
        {
            "keys": ["ssl", "certificat", "certificate", "expiré", "expired", "invalide", "invalid", "tls 1.0", "tls 1.1", "tls1.0", "tls1.1"],
            "action_fr":   "Intercepte le trafic entre votre site et vos visiteurs grâce à une "
                           "attaque SSL-stripping ou BEAST/POODLE. Sans certificat valide, "
                           "le navigateur n'alerte plus. L'attaquant lit en clair tous "
                           "les formulaires remplis : mots de passe, numéros de carte, données personnelles.",
            "action_en":   "Intercepts traffic between your site and visitors using "
                           "SSL-stripping or BEAST/POODLE attacks. Without a valid certificate, "
                           "browsers show no warning. The attacker reads all submitted forms "
                           "in plaintext: passwords, card numbers, personal data.",
            "time_fr":     "< 5 minutes sur le même réseau",
            "time_en":     "< 5 minutes on the same network",
            "impact_fr":   "Données de tous vos visiteurs interceptées.",
            "impact_en":   "All visitor data intercepted.",
            "target_fr":   "Site web / visiteurs",
            "target_en":   "Website / visitors",
        },
        {
            "keys": ["spf", "dmarc"],
            "action_fr":   "Envoie des emails en se faisant passer pour votre domaine "
                           "(ex : facture@votre-entreprise.fr). Sans SPF/DMARC, "
                           "les serveurs de messagerie acceptent ces emails sans vérification. "
                           "Vos clients, partenaires et employés reçoivent des emails "
                           "frauduleux qui semblent venir de vous.",
            "action_en":   "Sends emails impersonating your domain "
                           "(e.g. invoice@your-company.com). Without SPF/DMARC, "
                           "mail servers accept these emails without verification. "
                           "Your clients, partners, and employees receive fraudulent emails "
                           "that appear to come from you.",
            "time_fr":     "Immédiat — aucun outil requis",
            "time_en":     "Immediate — no tools required",
            "impact_fr":   "Phishing, fraude au virement, atteinte à la réputation.",
            "impact_en":   "Phishing, wire transfer fraud, brand reputation damage.",
            "target_fr":   "Messagerie de votre domaine",
            "target_en":   "Your email domain",
        },
        {
            "keys": ["wordpress", "wp-admin", "wp admin", "drupal", "cms"],
            "action_fr":   "Identifie le CMS et tente un brute-force sur la page d'administration. "
                           "Des outils comme WPScan testent automatiquement des milliers de "
                           "mots de passe. Une fois connecté, il installe un webshell "
                           "pour prendre le contrôle total du serveur.",
            "action_en":   "Identifies the CMS and brute-forces the admin login page. "
                           "Tools like WPScan automatically test thousands of passwords. "
                           "Once logged in, installs a webshell for full server control.",
            "time_fr":     "1 à 4 heures",
            "time_en":     "1 to 4 hours",
            "impact_fr":   "Site défacé, malware injecté, données volées.",
            "impact_en":   "Defaced site, malware injected, data stolen.",
            "target_fr":   "Interface d'administration",
            "target_en":   "Admin interface",
        },
        {
            "keys": ["apache", "nginx", "iis", "php", "version vulnérable", "vulnerable version", "cve"],
            "action_fr":   "Lit la version du serveur dans les en-têtes HTTP et recherche les "
                           "exploits publics correspondants (CVE). Pour Apache 2.4.49, "
                           "par exemple, une simple requête HTTP suffit pour lire "
                           "n'importe quel fichier du serveur, y compris /etc/passwd.",
            "action_en":   "Reads the server version from HTTP headers and looks up "
                           "public exploits (CVE). For Apache 2.4.49 for instance, "
                           "a single HTTP request is enough to read any file on the server, "
                           "including /etc/passwd.",
            "time_fr":     "< 5 minutes avec un exploit public",
            "time_en":     "< 5 minutes with a public exploit",
            "impact_fr":   "Exécution de code à distance, accès root au serveur.",
            "impact_en":   "Remote code execution, root access to server.",
            "target_fr":   "Serveur web",
            "target_en":   "Web server",
        },
        {
            "keys": ["réputation", "reputation", "blacklist", "dnsbl", "liste noire"],
            "action_fr":   "Votre domaine figure déjà sur des listes noires utilisées par "
                           "les serveurs de messagerie du monde entier. Vos emails légitimes "
                           "sont classés comme spam ou rejetés silencieusement avant "
                           "même d'arriver à destination.",
            "action_en":   "Your domain is already on blacklists used by mail servers worldwide. "
                           "Your legitimate emails are classified as spam or silently rejected "
                           "before even reaching their destination.",
            "time_fr":     "En cours — impact immédiat",
            "time_en":     "Ongoing — immediate impact",
            "impact_fr":   "Emails commerciaux et factures jamais reçus par vos clients.",
            "impact_en":   "Business emails and invoices never received by your clients.",
            "target_fr":   "Délivrabilité email",
            "target_en":   "Email deliverability",
        },
    ]

    result = []
    seen_keys: set[str] = set()

    for f in findings:
        if f.get("severity") not in ("CRITICAL", "HIGH"):
            continue

        title_lower = f.get("title", "").lower()
        cat_lower   = f.get("category", "").lower()
        search_str  = f"{title_lower} {cat_lower}"

        matched = None
        for scenario in SCENARIOS:
            for key in scenario["keys"]:
                if key in search_str:
                    # Déduplique par scénario (ex : SPF + DMARC = 1 seule carte)
                    scenario_id = scenario["keys"][0]
                    if scenario_id in seen_keys:
                        matched = None
                    else:
                        seen_keys.add(scenario_id)
                        matched = scenario
                    break
            if matched is not None or (matched is None and any(k in search_str for k in scenario["keys"])):
                break

        if matched is None:
            continue

        result.append({
            "title":          f.get("title", ""),
            "category":       f.get("category", ""),
            "severity":       f.get("severity", ""),
            "attacker_action": matched["action_fr"] if fr else matched["action_en"],
            "exploit_time":    matched["time_fr"]   if fr else matched["time_en"],
            "impact":          matched["impact_fr"] if fr else matched["impact_en"],
            "diagram_target":  matched["target_fr"] if fr else matched["target_en"],
        })

    return result


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
    # ⚠️  Ne pas inclure "réputation" dans les mots-clés : le finding INFO "Réputation
    #     email vérifiée" (IP propre) contient ce mot et causerait un faux FAIL.
    #     On cherche uniquement les termes propres aux findings négatifs.
    rep_ok = not _failed("liste noire", "blacklist", "dnsbl", "spam")
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
