"""
CyberHealth Scanner — Compliance Mapper (NIS2 + RGPD)
======================================================
Mappe les findings de sécurité vers les exigences réglementaires :
  - NIS2  (Directive EU 2022/2555 — Art. 21 §2)
  - RGPD  (Règlement EU 2016/679)

Logique pure — aucun appel réseau. Disponible sur tous les plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


# ── Règles de mapping : keywords → articles violés ───────────────────────────
# Format : (keywords, nis2_articles, rgpd_articles)
# Les keywords sont cherchés en minuscule dans "category + title" du finding.

COMPLIANCE_RULES: list[tuple[list[str], list[str], list[str]]] = [
    # SSL/TLS — chiffrement des communications
    (
        ["ssl", "tls", "certificat", "certificate", "expiré", "expired",
         "auto-signé", "self-signed", "déprécié", "deprecated", "pfs",
         "cipher", "clé courte", "weak key"],
        ["21-2-h"],
        ["5-1-f", "32"],
    ),
    # HSTS — forcer HTTPS
    (
        ["hsts", "strict-transport", "http→https", "http to https",
         "redirect", "port 80"],
        ["21-2-h"],
        ["32"],
    ),
    # Email security — SPF, DMARC, DKIM, MTA-STS
    # Art. 21-2-g (hygiène email) uniquement — SPF/DMARC/DKIM ≠ chiffrement (pas 21-2-h)
    (
        ["spf", "dmarc", "dkim", "mta-sts"],
        ["21-2-g"],
        [],
    ),
    # Ports dangereux / services exposés
    # "exposé"/"exposed" retirés : trop génériques (matchent "Version du serveur exposée")
    (
        ["rdp", "smb", "ftp", "telnet", "redis", "mongodb",
         "elasticsearch", "docker", "mysql", "postgresql",
         "service ouvert", "port ouvert"],
        ["21-2-i", "21-2-e"],
        ["32", "25"],
    ),
    # Versions vulnérables / CVE / logiciels obsolètes
    (
        ["version", "vulnérable", "vulnerable", "cve", "obsolète",
         "outdated", "php", "apache", "nginx", "iis", "asp.net"],
        ["21-2-e"],
        ["32"],
    ),
    # Headers de sécurité HTTP — CSP, X-Frame, Permissions-Policy
    (
        ["content-security-policy", "csp", "x-frame-options",
         "permissions-policy", "x-content-type", "server header",
         "header", "entête"],
        ["21-2-e"],
        ["25"],
    ),
    # Fuites de données / HIBP
    (
        ["fuite", "breach", "compromis", "hibp", "pwned", "données"],
        ["21-2-b"],
        ["33", "5-1-f"],
    ),
    # Fichiers sensibles exposés / panneaux admin non protégés
    (
        [".env", ".git", "admin", "phpinfo", "phpMyAdmin", "debug",
         "backup", "sensible", "sensitive", "swagger", "openapi",
         "actuator", "cors", "directory listing", "listing"],
        ["21-2-i", "21-2-e"],
        ["25", "32"],
    ),
    # Réputation / blacklist — incident potentiel en cours
    (
        ["réputation", "blacklist", "spam", "malware", "liste noire"],
        ["21-2-b"],
        ["33"],
    ),
    # DNSSEC / CAA — infrastructure DNS
    (
        ["dnssec", "caa"],
        ["21-2-g"],
        [],
    ),
    # Expiration du nom de domaine — Art. 21-2-e (maintenance), pas 21-2-a (politiques)
    (
        ["expire", "expiration", "domaine expiré", "domain expir"],
        ["21-2-e"],
        [],
    ),
    # Sous-domaines orphelins
    (
        ["orphelin", "orphan", "sous-domaine", "subdomain"],
        ["21-2-i"],
        ["32"],
    ),
]


# ── Seuils de score ───────────────────────────────────────────────────────────

SCORE_CONFORME  = 80   # ≥ 80 % → conforme  (vert)
SCORE_PARTIEL   = 50   # ≥ 50 % → partiel   (amber)
                       # < 50 % → non_conforme (rouge)


# ── Dataclasses de résultat ───────────────────────────────────────────────────

@dataclass
class ArticleResult:
    code:           str
    framework:      str          # "NIS2" | "RGPD"
    title:          str
    title_en:       str
    description:    str
    description_en: str
    compliant:      bool
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
            "triggered_by":   self.triggered_by,
        }


@dataclass
class ComplianceResult:
    nis2_score:    int
    rgpd_score:    int
    overall_level: str           # "conforme" | "partiel" | "non_conforme"
    nis2:          list[ArticleResult]
    rgpd:          list[ArticleResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nis2_score":    self.nis2_score,
            "rgpd_score":    self.rgpd_score,
            "overall_level": self.overall_level,
            "nis2":          [a.to_dict() for a in self.nis2],
            "rgpd":          [a.to_dict() for a in self.rgpd],
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
        # Initialisation : tous les articles commencent conformes
        nis2_map: dict[str, ArticleResult] = {
            code: ArticleResult(
                code=code,
                framework="NIS2",
                title=info["title"],
                title_en=info["title_en"],
                description=info["description"],
                description_en=info["description_en"],
                compliant=True,
            )
            for code, info in NIS2_ARTICLES.items()
        }
        rgpd_map: dict[str, ArticleResult] = {
            code: ArticleResult(
                code=code,
                framework="RGPD",
                title=info["title"],
                title_en=info["title_en"],
                description=info["description"],
                description_en=info["description_en"],
                compliant=True,
            )
            for code, info in RGPD_ARTICLES.items()
        }

        # Seuls les findings non-INFO déclenchent une non-conformité
        for finding in findings:
            if isinstance(finding, dict):
                severity = finding.get("severity", "INFO")
                category = finding.get("category", "")
                title    = finding.get("title", "")
            else:
                severity = getattr(finding, "severity", "INFO")
                category = getattr(finding, "category", "")
                title    = getattr(finding, "title", "")

            if severity == "INFO":
                continue

            haystack = (category + " " + title).lower()

            for keywords, nis2_arts, rgpd_arts in COMPLIANCE_RULES:
                if not any(kw in haystack for kw in keywords):
                    continue

                for code in nis2_arts:
                    if code in nis2_map:
                        nis2_map[code].compliant = False
                        if title and title not in nis2_map[code].triggered_by:
                            nis2_map[code].triggered_by.append(title)

                for code in rgpd_arts:
                    if code in rgpd_map:
                        rgpd_map[code].compliant = False
                        if title and title not in rgpd_map[code].triggered_by:
                            rgpd_map[code].triggered_by.append(title)

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
        )


# ── Helpers privés ────────────────────────────────────────────────────────────

def _pct_score(articles: list[ArticleResult]) -> int:
    """Pourcentage d'articles conformes (arrondi à l'entier)."""
    if not articles:
        return 100
    compliant = sum(1 for a in articles if a.compliant)
    return round(compliant / len(articles) * 100)


def _overall_level(nis2: int, rgpd: int) -> str:
    """Niveau global basé sur le score le plus faible des deux frameworks."""
    worst = min(nis2, rgpd)
    if worst >= SCORE_CONFORME:
        return "conforme"
    if worst >= SCORE_PARTIEL:
        return "partiel"
    return "non_conforme"
