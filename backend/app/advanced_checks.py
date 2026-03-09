"""
CyberHealth Scanner — Checks Avancés (Starter / Pro)
=====================================================
Modules :
    SubdomainAuditor      → Sous-domaines via Certificate Transparency (crt.sh)
                            + détection de certificats expirés / expirant bientôt
    VulnVersionAuditor    → Détection de versions vulnérables connues
                            (PHP, Apache, nginx, IIS, OpenSSL…) via en-têtes HTTP

Ces modules sont réservés aux plans Starter et Pro.
Chaque auditeur étend BaseAuditor depuis scanner.py.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import re
import socket
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Any

import dns.resolver
import dns.exception

from app.scanner import BaseAuditor, Finding, SCAN_TIMEOUT_SEC


# ─────────────────────────────────────────────────────────────────────────────
# Base de données légère des versions vulnérables connues
# Clé = (tech, version_prefix) → {cve, description, severity}
# ─────────────────────────────────────────────────────────────────────────────

KNOWN_VULNS: list[dict] = [
    # PHP — versions EOL ou critiques
    {
        "tech": "php", "max_version": (7, 4, 99),
        "severity": "CRITICAL",
        "cve": "Multiple CVEs (EOL)",
        "description_fr": "PHP 7.x est en fin de vie depuis novembre 2022. Plus aucun correctif de sécurité n'est publié.",
        "description_en": "PHP 7.x reached end-of-life in November 2022. No security patches are released anymore.",
        "recommendation_fr": "Migrer vers PHP 8.2 ou 8.3 (versions activement maintenues).",
        "recommendation_en": "Migrate to PHP 8.2 or 8.3 (actively maintained versions).",
    },
    {
        "tech": "php", "min_version": (8, 0, 0), "max_version": (8, 0, 99),
        "severity": "HIGH",
        "cve": "Multiple CVEs PHP 8.0 (EOL)",
        "description_fr": "PHP 8.0 est en fin de vie depuis novembre 2023.",
        "description_en": "PHP 8.0 reached end-of-life in November 2023.",
        "recommendation_fr": "Migrer vers PHP 8.2 ou 8.3.",
        "recommendation_en": "Migrate to PHP 8.2 or 8.3.",
    },
    # Apache — versions critiques
    {
        "tech": "apache", "min_version": (2, 4, 49), "max_version": (2, 4, 50),
        "severity": "CRITICAL",
        "cve": "CVE-2021-41773 / CVE-2021-42013",
        "description_fr": "Path traversal critique permettant l'exécution de code à distance (RCE).",
        "description_en": "Critical path traversal allowing remote code execution (RCE).",
        "recommendation_fr": "Mettre à jour Apache immédiatement vers 2.4.51+.",
        "recommendation_en": "Update Apache immediately to 2.4.51+.",
    },
    {
        "tech": "apache", "max_version": (2, 4, 55),
        "severity": "HIGH",
        "cve": "CVE-2023-25690",
        "description_fr": "Requête HTTP frauduleuse (request smuggling) via mod_proxy.",
        "description_en": "HTTP request smuggling via mod_proxy.",
        "recommendation_fr": "Mettre à jour Apache vers 2.4.56+.",
        "recommendation_en": "Update Apache to 2.4.56+.",
    },
    # nginx — versions avec vulnérabilités connues
    {
        "tech": "nginx", "max_version": (1, 20, 1),
        "severity": "HIGH",
        "cve": "CVE-2022-41741 / CVE-2022-41742",
        "description_fr": "Corruption mémoire dans le module ngx_http_mp4_module.",
        "description_en": "Memory corruption in ngx_http_mp4_module.",
        "recommendation_fr": "Mettre à jour nginx vers 1.22.1 ou 1.23.2+.",
        "recommendation_en": "Update nginx to 1.22.1 or 1.23.2+.",
    },
    # IIS — versions anciennes
    {
        "tech": "iis", "max_version": (8, 5, 99),
        "severity": "HIGH",
        "cve": "Multiple CVEs (EOL)",
        "description_fr": "IIS 8.5 et antérieur ne reçoit plus de correctifs de sécurité.",
        "description_en": "IIS 8.5 and earlier no longer receive security patches.",
        "recommendation_fr": "Migrer vers IIS 10 sur Windows Server 2019/2022.",
        "recommendation_en": "Migrate to IIS 10 on Windows Server 2019/2022.",
    },
]


def _parse_version(version_str: str) -> tuple[int, ...] | None:
    """Extrait un tuple (major, minor, patch) depuis une chaîne de version."""
    match = re.search(r"(\d+)\.(\d+)\.?(\d*)", version_str)
    if not match:
        return None
    parts = [int(x) if x else 0 for x in match.groups()]
    return tuple(parts)  # type: ignore[return-value]


def _version_in_range(
    ver: tuple[int, ...],
    min_ver: tuple[int, ...] | None,
    max_ver: tuple[int, ...] | None,
) -> bool:
    """Vérifie si une version est dans un intervalle [min, max]."""
    if min_ver and ver < min_ver:
        return False
    if max_ver and ver > max_ver:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# VulnVersionAuditor — Versions logicielles vulnérables
# ─────────────────────────────────────────────────────────────────────────────

class VulnVersionAuditor(BaseAuditor):
    """
    Détecte les versions de logiciels exposées dans les en-têtes HTTP
    et les croise avec une base de vulnérabilités connues.
    """

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        try:
            findings = await asyncio.wait_for(
                loop.run_in_executor(None, self._check_versions_sync),
                timeout=SCAN_TIMEOUT_SEC + 2,
            )
            return findings
        except (asyncio.TimeoutError, Exception):
            return []

    def get_details(self) -> dict:
        return self._details

    def __init__(self, domain: str, lang: str = "fr") -> None:
        super().__init__(domain, lang)
        self._details: dict[str, Any] = {}

    def _check_versions_sync(self) -> list[Finding]:
        findings: list[Finding] = []
        headers: dict[str, str] = {}

        # Récupérer les en-têtes HTTP
        for scheme, cls in [("https", http.client.HTTPSConnection), ("http", http.client.HTTPConnection)]:
            try:
                conn = cls(self.domain, timeout=SCAN_TIMEOUT_SEC)
                conn.request("HEAD", "/", headers={"User-Agent": "Mozilla/5.0 (CyberHealth Security Audit)"})
                resp = conn.getresponse()
                headers = {k.lower(): v for k, v in resp.getheaders()}
                conn.close()
                break
            except Exception:
                continue

        if not headers:
            return []

        # Extraire les technologies et versions
        detected: list[tuple[str, str, str]] = []  # (tech_name, version_str, raw_header)

        server = headers.get("server", "")
        powered_by = headers.get("x-powered-by", "")
        x_aspnet = headers.get("x-aspnet-version", "")
        x_aspnetmvc = headers.get("x-aspnetmvc-version", "")

        # Apache
        m = re.search(r"Apache[/\s]([\d.]+)", server, re.IGNORECASE)
        if m:
            detected.append(("apache", m.group(1), f"Server: {server}"))

        # nginx
        m = re.search(r"nginx[/\s]([\d.]+)", server, re.IGNORECASE)
        if m:
            detected.append(("nginx", m.group(1), f"Server: {server}"))

        # IIS
        m = re.search(r"IIS[/\s]([\d.]+)", server, re.IGNORECASE)
        if m:
            detected.append(("iis", m.group(1), f"Server: {server}"))

        # PHP via X-Powered-By
        m = re.search(r"PHP[/\s]([\d.]+)", powered_by, re.IGNORECASE)
        if m:
            detected.append(("php", m.group(1), f"X-Powered-By: {powered_by}"))

        # ASP.NET
        if x_aspnet:
            detected.append(("aspnet", x_aspnet, f"X-AspNet-Version: {x_aspnet}"))
        if x_aspnetmvc:
            detected.append(("aspnetmvc", x_aspnetmvc, f"X-AspNetMvc-Version: {x_aspnetmvc}"))

        self._details = {
            "server_header": server,
            "powered_by": powered_by,
            "detected_stack": [{"tech": t, "version": v} for t, v, _ in detected],
        }

        # Croiser avec la base de vulnérabilités
        for tech, version_str, raw_header in detected:
            version = _parse_version(version_str)
            if not version:
                continue

            for vuln in KNOWN_VULNS:
                if vuln["tech"] != tech:
                    continue
                if not _version_in_range(
                    version,
                    vuln.get("min_version"),
                    vuln.get("max_version"),
                ):
                    continue

                severity = vuln["severity"]
                penalty = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 5}.get(severity, 10)

                findings.append(Finding(
                    category          = "Versions Vulnérables",
                    severity          = severity,
                    title             = self._t(
                        f"Version vulnérable détectée : {tech.upper()} {version_str}",
                        f"Vulnerable version detected: {tech.upper()} {version_str}",
                    ),
                    technical_detail  = self._t(
                        f"{raw_header} — {vuln['cve']} : {vuln['description_fr']}",
                        f"{raw_header} — {vuln['cve']}: {vuln['description_en']}",
                    ),
                    plain_explanation = self._t(
                        f"La version {version_str} de {tech.upper()} contient des failles de sécurité connues et activement exploitées.",
                        f"Version {version_str} of {tech.upper()} contains known and actively exploited security vulnerabilities.",
                    ),
                    penalty           = penalty,
                    recommendation    = self._t(
                        vuln["recommendation_fr"],
                        vuln["recommendation_en"],
                    ),
                ))

        return findings


# ─────────────────────────────────────────────────────────────────────────────
# SubdomainAuditor — Certificate Transparency + DNS
# ─────────────────────────────────────────────────────────────────────────────

class SubdomainAuditor(BaseAuditor):
    """
    Énumère les sous-domaines via les logs Certificate Transparency (crt.sh),
    vérifie quels sont actifs (DNS), détecte les certificats expirés/expirant.
    """

    MAX_SUBDOMAINS = 50  # Limite pour éviter les scans trop longs

    def __init__(self, domain: str, lang: str = "fr") -> None:
        super().__init__(domain, lang)
        self._details: dict[str, Any] = {
            "subdomains": [],
            "expired_certs": [],
            "expiring_soon": [],
            "orphaned": [],
            "total_found": 0,
        }

    def get_details(self) -> dict:
        return self._details

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        try:
            findings = await asyncio.wait_for(
                loop.run_in_executor(None, self._audit_sync),
                timeout=20,  # crt.sh peut être lent
            )
            return findings
        except asyncio.TimeoutError:
            return []
        except Exception:
            return []

    def _fetch_crtsh(self) -> list[str]:
        """Interroge crt.sh pour obtenir tous les sous-domaines connus."""
        url = f"https://crt.sh/?q=%.{self.domain}&output=json"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "CyberHealth Security Audit"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []

        subdomains: set[str] = set()
        for entry in data:
            names = entry.get("name_value", "")
            for name in names.split("\n"):
                name = name.strip().lower()
                # Exclure les wildcards et domaines hors scope
                if name.startswith("*"):
                    continue
                if not name.endswith(f".{self.domain}") and name != self.domain:
                    continue
                subdomains.add(name)

        return sorted(subdomains)[:self.MAX_SUBDOMAINS]

    def _resolve_subdomain(self, subdomain: str) -> str | None:
        """
        Résout un sous-domaine en IP via dns.resolver (timeout contrôlé).
        socket.getaddrinfo() peut bloquer 30-60s (timeout OS) — inacceptable en boucle.
        """
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = 3.0   # 3s max par résolution (Python-level, pas OS-level)
            resolver.timeout  = 3.0
            answers = resolver.resolve(subdomain, "A")
            return str(answers[0])
        except (dns.exception.DNSException, Exception):
            return None

    def _check_cert(self, subdomain: str) -> dict | None:
        """
        Vérifie le certificat SSL d'un sous-domaine.
        Retourne None si pas de HTTPS, ou un dict avec expiry info.
        """
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(
                socket.create_connection((subdomain, 443), timeout=3),
                server_hostname=subdomain,
            ) as sock:
                cert = sock.getpeercert()
                not_after_str = cert.get("notAfter", "")
                if not_after_str:
                    # Python ssl retourne "Dec 31 23:59:59 2024 GMT"
                    # %Z est peu fiable cross-platform → on retire le suffixe timezone avant de parser
                    not_after_clean = not_after_str.replace(" GMT", "").replace(" UTC", "").strip()
                    not_after = datetime.strptime(not_after_clean, "%b %d %H:%M:%S %Y")
                    not_after = not_after.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    days_left = (not_after - now).days
                    return {
                        "subdomain": subdomain,
                        "expires_at": not_after.isoformat(),
                        "days_left": days_left,
                        "expired": days_left < 0,
                        "expiring_soon": 0 <= days_left <= 30,
                    }
        except ssl.SSLCertVerificationError:
            return {
                "subdomain": subdomain,
                "expires_at": None,
                "days_left": -1,
                "expired": True,
                "expiring_soon": False,
                "error": "Certificat invalide ou auto-signé",
            }
        except Exception:
            pass
        return None

    def _audit_sync(self) -> list[Finding]:
        findings: list[Finding] = []

        # 1. Récupérer les sous-domaines depuis crt.sh
        subdomains = self._fetch_crtsh()
        self._details["total_found"] = len(subdomains)

        if not subdomains:
            return []

        # 2. Vérifier la résolution DNS de chaque sous-domaine
        active: list[str] = []
        orphaned: list[str] = []

        for sub in subdomains:
            ip = self._resolve_subdomain(sub)
            if ip:
                active.append(sub)
                self._details["subdomains"].append({"subdomain": sub, "ip": ip, "active": True})
            else:
                orphaned.append(sub)
                self._details["subdomains"].append({"subdomain": sub, "ip": None, "active": False})

        # 3. Vérifier les certificats des sous-domaines actifs
        expired_certs: list[dict] = []
        expiring_soon: list[dict] = []

        for sub in active[:20]:  # Limiter à 20 vérifications SSL
            cert_info = self._check_cert(sub)
            if cert_info:
                if cert_info.get("expired"):
                    expired_certs.append(cert_info)
                    self._details["expired_certs"].append(cert_info)
                elif cert_info.get("expiring_soon"):
                    expiring_soon.append(cert_info)
                    self._details["expiring_soon"].append(cert_info)

        self._details["orphaned"] = orphaned

        # 4. Générer les findings

        # Sous-domaines sans résolution DNS :
        # Ces sous-domaines n'ont AUCUN enregistrement DNS actif — ils n'existent que
        # dans les logs Certificate Transparency (crt.sh). Sans entrée DNS, il n'y a
        # AUCUNE surface d'attaque (un attaquant ne peut pas faire de subdomain takeover
        # sans DNS). Ce sont des certificats historiques, pas des orphelins dangereux.
        #
        # ⚠️  Un vrai "orphelin dangereux" (subdomain takeover) nécessite :
        #     DNS actif (CNAME/A) → service tiers désactivé (GitHub Pages, Heroku…)
        #     Dans ce cas le sous-domaine RÉSOUT encore (active=True) mais est vulnérable.
        #
        # On les signale en INFO p=0 pour la transparence, sans pénalité.
        if orphaned:
            count = len(orphaned)
            sample = ", ".join(orphaned[:5])
            if count > 5:
                sample += f" (+{count - 5} {self._t('autres', 'more')})"
            findings.append(Finding(
                category          = "Sous-domaines & Certificats",
                severity          = "INFO",
                title             = self._t(
                    f"{count} certificat(s) historique(s) dans les logs CT",
                    f"{count} historical certificate(s) in CT logs",
                ),
                technical_detail  = self._t(
                    f"Sous-domaines présents dans crt.sh mais sans enregistrement DNS actif : {sample}",
                    f"Subdomains found in crt.sh but with no active DNS record: {sample}",
                ),
                plain_explanation = self._t(
                    "Ces sous-domaines ont eu un certificat SSL par le passé mais n'ont aucune entrée DNS active. "
                    "Sans DNS, ils ne sont pas accessibles et ne présentent aucun risque de subdomain takeover. "
                    "Il s'agit d'enregistrements historiques dans les logs Certificate Transparency.",
                    "These subdomains had an SSL certificate in the past but have no active DNS record. "
                    "Without DNS, they are unreachable and present no subdomain takeover risk. "
                    "These are historical records in Certificate Transparency logs.",
                ),
                penalty           = 0,
                recommendation    = self._t(
                    "Aucune action requise. Les logs CT sont immuables — ces entrées resteront visibles indéfiniment. "
                    "Surveiller uniquement si vous recréez ces sous-domaines dans le DNS.",
                    "No action required. CT logs are immutable — these entries will remain visible indefinitely. "
                    "Monitor only if you re-create these subdomains in DNS.",
                ),
            ))

        # Certificats expirés
        if expired_certs:
            count = len(expired_certs)
            sample = ", ".join(c["subdomain"] for c in expired_certs[:3])
            findings.append(Finding(
                category          = "Sous-domaines & Certificats",
                severity          = "HIGH",
                title             = self._t(
                    f"{count} certificat(s) SSL expiré(s)",
                    f"{count} expired SSL certificate(s)",
                ),
                technical_detail  = self._t(
                    f"Certificats expirés sur : {sample}",
                    f"Expired certificates on: {sample}",
                ),
                plain_explanation = self._t(
                    "Ces sous-domaines ont des certificats SSL expirés. Les visiteurs voient une erreur de sécurité et les navigateurs bloquent l'accès.",
                    "These subdomains have expired SSL certificates. Visitors see a security error and browsers block access.",
                ),
                penalty           = 15,
                recommendation    = self._t(
                    "Renouveler les certificats immédiatement via Let's Encrypt ou votre CA. Activer le renouvellement automatique.",
                    "Renew certificates immediately via Let's Encrypt or your CA. Enable automatic renewal.",
                ),
            ))

        # Certificats expirant dans moins de 30 jours
        if expiring_soon:
            count = len(expiring_soon)
            day_abbr = self._t("j", "d")
            sample_parts = [f"{c['subdomain']} ({c['days_left']}{day_abbr})" for c in expiring_soon[:3]]
            sample = ", ".join(sample_parts)
            findings.append(Finding(
                category          = "Sous-domaines & Certificats",
                severity          = "MEDIUM",
                title             = self._t(
                    f"{count} certificat(s) expirant dans moins de 30 jours",
                    f"{count} certificate(s) expiring within 30 days",
                ),
                technical_detail  = self._t(
                    f"Expiration imminente sur : {sample}",
                    f"Imminent expiration on: {sample}",
                ),
                plain_explanation = self._t(
                    "Ces certificats SSL vont expirer prochainement. Sans renouvellement, les visiteurs verront une erreur de sécurité.",
                    "These SSL certificates are expiring soon. Without renewal, visitors will see a security error.",
                ),
                penalty           = 8,
                recommendation    = self._t(
                    "Planifier le renouvellement maintenant. Activer le renouvellement automatique (certbot --renew-hook).",
                    "Schedule renewal now. Enable automatic renewal (certbot --renew-hook).",
                ),
            ))

        # Bonne nouvelle : peu de sous-domaines exposés
        if active and not expired_certs and not expiring_soon and len(orphaned) == 0:
            findings.append(Finding(
                category          = "Sous-domaines & Certificats",
                severity          = "INFO",
                title             = self._t(
                    f"{len(active)} sous-domaine(s) actif(s) — certificats valides",
                    f"{len(active)} active subdomain(s) — valid certificates",
                ),
                technical_detail  = self._t(
                    f"Sous-domaines détectés via Certificate Transparency : {len(subdomains)} total, {len(active)} actifs.",
                    f"Subdomains detected via Certificate Transparency: {len(subdomains)} total, {len(active)} active.",
                ),
                plain_explanation = self._t(
                    "Tous les sous-domaines actifs ont des certificats SSL valides. Aucun sous-domaine à risque détecté.",
                    "All active subdomains have valid SSL certificates. No at-risk subdomains detected.",
                ),
                penalty           = 0,
                recommendation    = self._t(
                    "Continuer à surveiller régulièrement les sous-domaines et certificats.",
                    "Continue to regularly monitor subdomains and certificates.",
                ),
            ))

        return findings
