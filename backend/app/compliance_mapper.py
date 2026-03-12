"""
CyberHealth Scanner — Compliance Mapper (NIS2 + RGPD)
======================================================
Mappe les findings de sécurité vers les exigences réglementaires :
  - NIS2  (Directive EU 2022/2555 — Art. 21 §2)
  - RGPD  (Règlement EU 2016/679)

Source unique de vérité : les critères techniques ET les articles
réglementaires sont définis ici. Le PDF (report_service) et le
frontend (CompliancePage) consomment ces données.

Logique pure — aucun appel réseau. Disponible sur tous les plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Severity ranking ────────────────────────────────────────────────────────

_SEV_RANK: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _sev(finding: dict | object) -> int:
    """Retourne le rang de sévérité d'un finding (0 si INFO ou inconnu)."""
    if isinstance(finding, dict):
        return _SEV_RANK.get(str(finding.get("severity", "")), 0)
    return _SEV_RANK.get(str(getattr(finding, "severity", "")), 0)


def _cat(finding: dict | object) -> str:
    if isinstance(finding, dict):
        return str(finding.get("category", ""))
    return str(getattr(finding, "category", ""))


def _title(finding: dict | object) -> str:
    if isinstance(finding, dict):
        return str(finding.get("title", ""))
    return str(getattr(finding, "title", ""))


def _title_lower(finding: dict | object) -> str:
    return _title(finding).lower()


# ── Référentiel NIS2 — Art. 21 §2 ────────────────────────────────────────────

NIS2_ARTICLES: dict[str, dict[str, str]] = {
    "21-2-a": {
        "title":          "Politiques de sécurité des SI",
        "title_en":       "Information system security policies",
        "description":    "Analyse des risques et politiques de sécurité des systèmes d'information.",
        "description_en": "Risk analysis and information system security policies.",
    },
    "21-2-b": {
        "title":          "Gestion des incidents",
        "title_en":       "Incident handling",
        "description":    "Processus de détection, de signalement et de réponse aux incidents.",
        "description_en": "Detection, reporting and response to security incidents.",
    },
    "21-2-e": {
        "title":          "Sécurité et maintenance des systèmes",
        "title_en":       "Security in acquisition and maintenance",
        "description":    "Gestion des vulnérabilités et mises à jour de sécurité.",
        "description_en": "Vulnerability management and security updates.",
    },
    "21-2-g": {
        "title":          "Hygiène informatique de base",
        "title_en":       "Basic cyber hygiene",
        "description":    "Pratiques de base : mises à jour, mots de passe, sécurité email.",
        "description_en": "Basic practices: updates, passwords, email security.",
    },
    "21-2-h": {
        "title":          "Chiffrement et cryptographie",
        "title_en":       "Cryptography and encryption",
        "description":    "Protocoles de chiffrement robustes pour les communications et données.",
        "description_en": "Robust encryption protocols for communications and data.",
    },
    "21-2-i": {
        "title":          "Contrôle d'accès et sécurité RH",
        "title_en":       "Access control and HR security",
        "description":    "Gestion des accès, authentification et sécurité des actifs.",
        "description_en": "Access management, authentication and asset security.",
    },
    "21-2-j": {
        "title":          "Authentification multi-facteurs",
        "title_en":       "Multi-factor authentication",
        "description":    "MFA pour les accès aux systèmes critiques et interfaces d'administration.",
        "description_en": "MFA for critical system access and administration interfaces.",
    },
}


# ── Référentiel RGPD — Articles clés ─────────────────────────────────────────

RGPD_ARTICLES: dict[str, dict[str, str]] = {
    "5-1-f": {
        "title":          "Intégrité et confidentialité",
        "title_en":       "Integrity and confidentiality",
        "description":    "Les données doivent être protégées contre tout traitement non autorisé.",
        "description_en": "Data must be protected against unauthorized or unlawful processing.",
    },
    "25": {
        "title":          "Protection des données dès la conception",
        "title_en":       "Data protection by design",
        "description":    "La sécurité doit être intégrée dans les systèmes dès leur conception.",
        "description_en": "Security must be built into systems from the ground up.",
    },
    "32": {
        "title":          "Sécurité du traitement",
        "title_en":       "Security of processing",
        "description":    "Mesures techniques garantissant un niveau de sécurité adapté au risque.",
        "description_en": "Technical measures ensuring security appropriate to the risk.",
    },
    "33": {
        "title":          "Notification des violations",
        "title_en":       "Breach notification",
        "description":    "Les violations doivent être notifiées à la CNIL dans les 72h.",
        "description_en": "Data breaches must be notified to the supervisory authority within 72h.",
    },
}


# ── 12 critères techniques ──────────────────────────────────────────────────
# Source unique de vérité — consommés par le PDF et le frontend.
# Chaque critère a une fonction `check(findings) -> "pass"|"warn"|"fail"`.

def _check_https(findings: list) -> str:
    """HTTPS & Chiffrement actif."""
    if any(_sev(f) >= 4 and _cat(f) == "SSL / HTTPS" for f in findings):
        return "fail"
    if any(
        any(w in _title_lower(f) for w in ["http", "redirect", "https"])
        and _sev(f) >= 3
        for f in findings
    ):
        return "fail"
    if any(_sev(f) >= 3 and _cat(f) == "SSL / HTTPS" for f in findings):
        return "warn"
    return "pass"


def _check_tls(findings: list) -> str:
    """Protocole TLS à jour."""
    if any(
        any(w in _title_lower(f) for w in ["tls 1.0", "tls 1.1", "tlsv1.0", "tlsv1.1", "deprecated", "cipher faible", "weak cipher"])
        and _sev(f) >= 2
        for f in findings
    ):
        return "fail"
    if any(
        any(w in _title_lower(f) for w in ["perfect forward", "pfs"])
        and _sev(f) >= 2
        for f in findings
    ):
        return "warn"
    return "pass"


def _check_dmarc(findings: list) -> str:
    """Protection anti-usurpation (DMARC)."""
    if any(
        "dmarc" in _title_lower(f) and _sev(f) >= 3
        for f in findings
    ):
        return "fail"
    if any(
        "dmarc" in _title_lower(f) and _sev(f) >= 2
        for f in findings
    ):
        return "warn"
    return "pass"


def _check_headers(findings: list) -> str:
    """En-têtes de sécurité HTTP."""
    if any(_cat(f) == "En-têtes HTTP" and _sev(f) >= 3 for f in findings):
        return "fail"
    if any(_cat(f) == "En-têtes HTTP" and _sev(f) >= 2 for f in findings):
        return "warn"
    return "pass"


def _check_spf(findings: list) -> str:
    """Authentification email (SPF)."""
    if any("spf" in _title_lower(f) and _sev(f) >= 3 for f in findings):
        return "fail"
    if any(
        "spf" in _title_lower(f) and "+all" in _title_lower(f) and _sev(f) >= 2
        for f in findings
    ):
        return "warn"
    return "pass"


def _check_dkim(findings: list) -> str:
    """Signature DKIM des emails."""
    if any("dkim" in _title_lower(f) and _sev(f) >= 2 for f in findings):
        return "fail"
    return "pass"


def _check_dnssec(findings: list) -> str:
    """Sécurité DNS (DNSSEC + CAA)."""
    if any(
        any(w in _title_lower(f) for w in ["dnssec", "caa"]) and _sev(f) >= 1
        for f in findings
    ):
        return "warn"
    return "pass"


def _check_ports(findings: list) -> str:
    """Ports dangereux exposés."""
    if any(
        _cat(f) == "Exposition des Ports"
        and any(w in _title_lower(f) for w in ["rdp", "smb", "mysql", "redis", "mongo", "elastic"])
        and _sev(f) >= 3
        for f in findings
    ):
        return "fail"
    return "pass"


def _check_reputation(findings: list) -> str:
    """Réputation, blacklists et fuites de données."""
    if any(
        (   _cat(f) in ("Réputation du Domaine", "Fuites de données")
         or any(w in _title_lower(f) for w in ["breach", "fuite", "blacklist", "blocklist"]))
        and _sev(f) >= 3
        for f in findings
    ):
        return "fail"
    return "pass"


def _check_credentials(findings: list) -> str:
    """Credentials, fichiers sensibles et accès exposés."""
    if any(
        (   any(w in _title_lower(f) for w in [
                "credential", "secret", "token", "api key", "clé",
                "exposed", "exposé", ".env", "admin", "sensible", "sensitive",
            ])
         or _cat(f) in ("Fichiers sensibles", "Exposition admin", "Secrets exposés"))
        and _sev(f) >= 3
        for f in findings
    ):
        return "fail"
    # Orphaned subdomains = access control issue
    if any(
        any(w in _title_lower(f) for w in ["orphelin", "orphan"])
        and _sev(f) >= 2
        for f in findings
    ):
        return "warn"
    return "pass"


def _check_expiry(findings: list) -> str:
    """Expiration du domaine."""
    if any(
        any(w in _title_lower(f) for w in ["domain", "expir", "renouvell"])
        and _sev(f) == 4
        for f in findings
    ):
        return "fail"
    if any(
        any(w in _title_lower(f) for w in ["domain", "expir", "renouvell"])
        and _sev(f) >= 2
        for f in findings
    ):
        return "warn"
    return "pass"


def _check_versions(findings: list) -> str:
    """Logiciels et versions vulnérables."""
    if any(_cat(f) == "Versions Vulnérables" and _sev(f) == 4 for f in findings):
        return "fail"
    if any(_cat(f) == "Versions Vulnérables" and _sev(f) >= 3 for f in findings):
        return "warn"
    return "pass"


# ── Liste des 12 critères ──────────────────────────────────────────────────

COMPLIANCE_CRITERIA: list[dict[str, Any]] = [
    {
        "id": "https",
        "label_fr": "HTTPS & Chiffrement actif",
        "label_en": "HTTPS & Active Encryption",
        "regulations": ["NIS2", "RGPD"],
        "article_fr": "Art. 21 NIS2 \u00b7 Art. 32 RGPD",
        "article_en": "Art. 21 NIS2 \u00b7 Art. 32 GDPR",
        "desc_fr": "Tout le trafic doit \u00eatre chiffr\u00e9 via HTTPS. Le certificat SSL doit \u00eatre valide et la redirection HTTP \u2192 HTTPS active.",
        "desc_en": "All traffic must be encrypted via HTTPS. SSL certificate must be valid and HTTP \u2192 HTTPS redirect active.",
        "nis2_articles": ["21-2-h"],
        "rgpd_articles": ["5-1-f", "32"],
        "check": _check_https,
    },
    {
        "id": "tls",
        "label_fr": "Protocole TLS \u00e0 jour",
        "label_en": "Up-to-date TLS Protocol",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "TLS 1.2 minimum requis. TLS 1.0 et 1.1 sont officiellement d\u00e9pr\u00e9ci\u00e9s depuis 2021.",
        "desc_en": "TLS 1.2 minimum required. TLS 1.0 and 1.1 have been officially deprecated since 2021.",
        "nis2_articles": ["21-2-h"],
        "rgpd_articles": [],
        "check": _check_tls,
    },
    {
        "id": "dmarc",
        "label_fr": "Protection anti-usurpation (DMARC)",
        "label_en": "Anti-spoofing Protection (DMARC)",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "DMARC avec p=quarantine ou p=reject prot\u00e8ge votre domaine contre le phishing par usurpation d'identit\u00e9.",
        "desc_en": "DMARC with p=quarantine or p=reject protects your domain against impersonation phishing.",
        "nis2_articles": ["21-2-g"],
        "rgpd_articles": [],
        "check": _check_dmarc,
    },
    {
        "id": "headers",
        "label_fr": "En-t\u00eates de s\u00e9curit\u00e9 HTTP",
        "label_en": "HTTP Security Headers",
        "regulations": ["RGPD"],
        "article_fr": "Art. 25 RGPD",
        "article_en": "Art. 25 GDPR",
        "desc_fr": "HSTS, CSP et X-Frame-Options r\u00e9duisent la surface d'attaque XSS/clickjacking et prot\u00e8gent vos visiteurs.",
        "desc_en": "HSTS, CSP and X-Frame-Options reduce the XSS/clickjacking attack surface and protect visitors.",
        "nis2_articles": ["21-2-e", "21-2-a"],
        "rgpd_articles": ["25"],
        "check": _check_headers,
    },
    {
        "id": "spf",
        "label_fr": "Authentification email (SPF)",
        "label_en": "Email Authentication (SPF)",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "SPF strict (-all) emp\u00eache les tiers d'envoyer des emails en usurpant votre domaine.",
        "desc_en": "Strict SPF (-all) prevents third parties from sending emails by spoofing your domain.",
        "nis2_articles": ["21-2-g"],
        "rgpd_articles": [],
        "check": _check_spf,
    },
    {
        "id": "dkim",
        "label_fr": "Signature DKIM des emails",
        "label_en": "DKIM Email Signing",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "DKIM garantit l'int\u00e9grit\u00e9 et l'authenticit\u00e9 cryptographique des emails sortants.",
        "desc_en": "DKIM guarantees the integrity and cryptographic authenticity of outgoing emails.",
        "nis2_articles": ["21-2-g"],
        "rgpd_articles": [],
        "check": _check_dkim,
    },
    {
        "id": "dnssec",
        "label_fr": "S\u00e9curit\u00e9 DNS (DNSSEC + CAA)",
        "label_en": "DNS Security (DNSSEC + CAA)",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "DNSSEC prot\u00e8ge contre la falsification DNS. CAA limite les autorit\u00e9s autoris\u00e9es \u00e0 \u00e9mettre des certificats SSL.",
        "desc_en": "DNSSEC protects against DNS forgery. CAA restricts which CAs can issue SSL certificates.",
        "nis2_articles": ["21-2-g"],
        "rgpd_articles": [],
        "check": _check_dnssec,
    },
    {
        "id": "ports",
        "label_fr": "Ports dangereux expos\u00e9s",
        "label_en": "Dangerous Exposed Ports",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "RDP, SMB, MySQL, Redis, Elasticsearch ne doivent jamais \u00eatre accessibles depuis internet.",
        "desc_en": "RDP, SMB, MySQL, Redis, Elasticsearch must never be accessible from the internet.",
        "nis2_articles": ["21-2-i", "21-2-e"],
        "rgpd_articles": ["32", "25"],
        "check": _check_ports,
    },
    {
        "id": "reputation",
        "label_fr": "R\u00e9putation, blacklists et fuites",
        "label_en": "Reputation, Blacklists and Breaches",
        "regulations": ["NIS2", "RGPD"],
        "article_fr": "Art. 21 NIS2 \u00b7 Art. 32-33 RGPD",
        "article_en": "Art. 21 NIS2 \u00b7 Art. 32-33 GDPR",
        "desc_fr": "Votre domaine et IP ne doivent pas figurer sur les listes noires. Aucune fuite de donn\u00e9es ne doit \u00eatre associ\u00e9e \u00e0 votre domaine.",
        "desc_en": "Your domain and IP must not appear on blacklists. No data breach should be associated with your domain.",
        "nis2_articles": ["21-2-b"],
        "rgpd_articles": ["32", "33", "5-1-f"],
        "check": _check_reputation,
    },
    {
        "id": "credentials",
        "label_fr": "Credentials expos\u00e9s dans le code",
        "label_en": "Exposed Credentials in Code",
        "regulations": ["RGPD"],
        "article_fr": "Art. 32 RGPD",
        "article_en": "Art. 32 GDPR",
        "desc_fr": "Aucune cl\u00e9 API, token ou secret ne doit \u00eatre visible dans le source HTML ou JavaScript public.",
        "desc_en": "No API key, token or secret should be visible in public HTML or JavaScript source.",
        "nis2_articles": ["21-2-i"],
        "rgpd_articles": ["32"],
        "check": _check_credentials,
    },
    {
        "id": "expiry",
        "label_fr": "Expiration du domaine",
        "label_en": "Domain Expiration",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "Un domaine expir\u00e9 rend votre infrastructure inaccessible et peut \u00eatre r\u00e9cup\u00e9r\u00e9 par un acteur malveillant.",
        "desc_en": "An expired domain makes your infrastructure inaccessible and can be seized by a malicious actor.",
        "nis2_articles": ["21-2-e"],
        "rgpd_articles": [],
        "check": _check_expiry,
    },
    {
        "id": "versions",
        "label_fr": "Logiciels et versions vuln\u00e9rables",
        "label_en": "Vulnerable Software Versions",
        "regulations": ["NIS2"],
        "article_fr": "Art. 21 NIS2",
        "article_en": "Art. 21 NIS2",
        "desc_fr": "CMS, serveurs et frameworks doivent \u00eatre \u00e0 jour. Les versions avec CVE connues doivent \u00eatre mises \u00e0 jour.",
        "desc_en": "CMS, servers and frameworks must be up to date. Versions with known CVEs must be updated.",
        "nis2_articles": ["21-2-e", "21-2-a"],
        "rgpd_articles": ["32"],
        "check": _check_versions,
    },
]


# ── Disclaimer ──────────────────────────────────────────────────────────────

DISCLAIMER_FR = (
    "Checks impossibles en scan externe : MFA, plans de continuit\u00e9, "
    "formation, politiques internes, chiffrement au repos. "
    "Ce diagnostic couvre uniquement les mesures techniques v\u00e9rifiables depuis internet."
)
DISCLAIMER_EN = (
    "Checks not possible via external scan: MFA, business continuity plans, "
    "training, internal policies, encryption at rest. "
    "This assessment covers only technical measures verifiable from the internet."
)


# ── Articles non évaluables ────────────────────────────────────────────────
# Articles NIS2 qui ne peuvent PAS être vérifiés par un scan externe.

NOT_ASSESSABLE_NIS2 = {"21-2-j"}  # MFA — impossible de vérifier via un scan externe


# ── Seuils de score ───────────────────────────────────────────────────────────

SCORE_BON         = 80   # >= 80% → bon  (vert)
SCORE_INSUFFISANT = 50   # >= 50% → insuffisant  (amber)
                         # <  50% → critique (rouge)

# Back-compat aliases
SCORE_CONFORME = SCORE_BON
SCORE_PARTIEL  = SCORE_INSUFFISANT


# ── Status labels ───────────────────────────────────────────────────────────

STATUS_LABEL = {
    "fr": {"pass": "Conforme", "warn": "Avertissement", "fail": "Non conforme", "not_assessable": "Non \u00e9valuable", "unknown": "Non v\u00e9rifi\u00e9"},
    "en": {"pass": "Compliant", "warn": "Warning",       "fail": "Non-compliant", "not_assessable": "Not assessable",  "unknown": "Not checked"},
}

STATUS_COLOR = {"pass": "#4ade80", "warn": "#fbbf24", "fail": "#f87171", "not_assessable": "#94a3b8", "unknown": "#94a3b8"}


# ── Dataclasses de résultat ───────────────────────────────────────────────────

@dataclass
class CriterionResult:
    id:           str
    label_fr:     str
    label_en:     str
    regulations:  list[str]
    article_fr:   str
    article_en:   str
    desc_fr:      str
    desc_en:      str
    status:       str          # "pass" | "warn" | "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":           self.id,
            "label_fr":     self.label_fr,
            "label_en":     self.label_en,
            "regulations":  self.regulations,
            "article_fr":   self.article_fr,
            "article_en":   self.article_en,
            "desc_fr":      self.desc_fr,
            "desc_en":      self.desc_en,
            "status":       self.status,
        }


@dataclass
class ArticleResult:
    code:           str
    framework:      str          # "NIS2" | "RGPD"
    title:          str
    title_en:       str
    description:    str
    description_en: str
    compliant:      bool | None  # None = not assessable
    status:         str = "pass"  # "pass" | "warn" | "fail" | "not_assessable"
    triggered_by:   list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code":           self.code,
            "framework":      self.framework,
            "title":          self.title,
            "title_en":       self.title_en,
            "description":    self.description,
            "description_en": self.description_en,
            "compliant":      self.compliant,
            "status":         self.status,
            "triggered_by":   self.triggered_by,
        }


@dataclass
class ComplianceResult:
    nis2_score:    int
    rgpd_score:    int
    overall_level: str           # "bon" | "insuffisant" | "critique"
    nis2:          list[ArticleResult]
    rgpd:          list[ArticleResult]
    criteria:      list[CriterionResult] = field(default_factory=list)
    disclaimer_fr: str = DISCLAIMER_FR
    disclaimer_en: str = DISCLAIMER_EN

    def to_dict(self) -> dict[str, Any]:
        return {
            "nis2_score":     self.nis2_score,
            "rgpd_score":     self.rgpd_score,
            "overall_level":  self.overall_level,
            "nis2":           [a.to_dict() for a in self.nis2],
            "rgpd":           [a.to_dict() for a in self.rgpd],
            "criteria":       [c.to_dict() for c in self.criteria],
            "disclaimer_fr":  self.disclaimer_fr,
            "disclaimer_en":  self.disclaimer_en,
        }


# ── Mapper principal ──────────────────────────────────────────────────────────

class ComplianceMapper:
    """
    Mappe les findings de sécurité vers les articles NIS2 et RGPD.
    Disponible sur tous les plans — le score reflète naturellement
    la complétude des checks (plans supérieurs = plus de checks = score plus précis).
    """

    def analyze(self, findings: list) -> ComplianceResult:
        """
        Analyse les findings et retourne un ComplianceResult.

        findings : liste de Finding dataclasses OU de dicts avec
                   les clés 'category', 'title', 'severity'.
        """
        # 1. Évaluer les 12 critères techniques
        criteria_results = self._evaluate_criteria(findings)

        # 2. Construire le map critère_id → statut
        criteria_status: dict[str, str] = {
            cr.id: cr.status for cr in criteria_results
        }

        # 3. Construire les articles NIS2
        nis2_map: dict[str, ArticleResult] = {}
        for code, info in NIS2_ARTICLES.items():
            art = ArticleResult(
                code=code,
                framework="NIS2",
                title=info["title"],
                title_en=info["title_en"],
                description=info["description"],
                description_en=info["description_en"],
                compliant=None if code in NOT_ASSESSABLE_NIS2 else True,
                status="not_assessable" if code in NOT_ASSESSABLE_NIS2 else "pass",
            )
            nis2_map[code] = art

        # 4. Construire les articles RGPD
        rgpd_map: dict[str, ArticleResult] = {}
        for code, info in RGPD_ARTICLES.items():
            art = ArticleResult(
                code=code,
                framework="RGPD",
                title=info["title"],
                title_en=info["title_en"],
                description=info["description"],
                description_en=info["description_en"],
                compliant=True,
                status="pass",
            )
            rgpd_map[code] = art

        # 5. Propager les résultats des critères vers les articles
        for crit_def in COMPLIANCE_CRITERIA:
            crit_status = criteria_status.get(crit_def["id"], "pass")
            if crit_status == "pass":
                continue

            crit_label = crit_def["label_fr"]

            for art_code in crit_def.get("nis2_articles", []):
                if art_code in nis2_map and nis2_map[art_code].status != "not_assessable":
                    art = nis2_map[art_code]
                    # Pire statut gagne : fail > warn > pass
                    if crit_status == "fail":
                        art.status = "fail"
                        art.compliant = False
                    elif crit_status == "warn" and art.status != "fail":
                        art.status = "warn"
                        art.compliant = False
                    if crit_label and crit_label not in art.triggered_by:
                        art.triggered_by.append(crit_label)

            for art_code in crit_def.get("rgpd_articles", []):
                if art_code in rgpd_map:
                    art = rgpd_map[art_code]
                    if crit_status == "fail":
                        art.status = "fail"
                        art.compliant = False
                    elif crit_status == "warn" and art.status != "fail":
                        art.status = "warn"
                        art.compliant = False
                    if crit_label and crit_label not in art.triggered_by:
                        art.triggered_by.append(crit_label)

        nis2_list = list(nis2_map.values())
        rgpd_list = list(rgpd_map.values())

        nis2_score = _pct_score(nis2_list)
        rgpd_score = _pct_score(rgpd_list)

        return ComplianceResult(
            nis2_score    = nis2_score,
            rgpd_score    = rgpd_score,
            overall_level = _overall_level(nis2_score, rgpd_score),
            nis2          = nis2_list,
            rgpd          = rgpd_list,
            criteria      = criteria_results,
        )

    def _evaluate_criteria(self, findings: list) -> list[CriterionResult]:
        """Évalue les 12 critères techniques et retourne leurs résultats."""
        results = []
        for crit in COMPLIANCE_CRITERIA:
            try:
                status = crit["check"](findings)
            except Exception:
                status = "unknown"
            results.append(CriterionResult(
                id=crit["id"],
                label_fr=crit["label_fr"],
                label_en=crit["label_en"],
                regulations=crit["regulations"],
                article_fr=crit["article_fr"],
                article_en=crit["article_en"],
                desc_fr=crit["desc_fr"],
                desc_en=crit["desc_en"],
                status=status,
            ))
        return results


# ── Helpers privés ────────────────────────────────────────────────────────

def _pct_score(articles: list[ArticleResult]) -> int:
    """Pourcentage d'articles conformes, excluant les not_assessable.

    Pondération : pass=100%, warn=50%, fail=0%.
    """
    assessable = [a for a in articles if a.status != "not_assessable"]
    if not assessable:
        return 100
    total = 0.0
    for a in assessable:
        if a.status == "pass":
            total += 1.0
        elif a.status == "warn":
            total += 0.5
        # fail = 0
    return round(total / len(assessable) * 100)


def _overall_level(nis2: int, rgpd: int) -> str:
    """Niveau global basé sur le score le plus faible des deux frameworks."""
    worst = min(nis2, rgpd)
    if worst >= SCORE_BON:
        return "bon"
    if worst >= SCORE_INSUFFISANT:
        return "insuffisant"
    return "critique"
