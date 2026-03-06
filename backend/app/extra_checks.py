"""
CyberHealth Scanner — Checks Supplémentaires
=============================================
Modules :
    HttpHeaderAuditor     → En-têtes HTTP de sécurité (HSTS, CSP, X-Frame…)
    EmailSecurityAuditor  → DKIM, MX
    TechExposureAuditor   → Stack technique exposée (CMS, version serveur)
    ReputationAuditor     → Réputation domaine/IP (DNSBL)

Chaque auditeur étend BaseAuditor depuis scanner.py et retourne list[Finding].
"""

from __future__ import annotations

import asyncio
import http.client
import socket
from typing import Any

import dns.resolver
import dns.exception

from app.scanner import BaseAuditor, Finding, SCAN_TIMEOUT_SEC, DNS_LIFETIME_SEC


# ─────────────────────────────────────────────────────────────────────────────
# HttpHeaderAuditor — En-têtes HTTP de sécurité
# ─────────────────────────────────────────────────────────────────────────────

class HttpHeaderAuditor(BaseAuditor):
    """Vérifie la présence des en-têtes HTTP de sécurité."""

    def _get_security_headers(self) -> list[dict]:
        return [
            {
                "name":             "Strict-Transport-Security",
                "penalty":          10,
                "severity":         "HIGH",
                "title":            self._t("HSTS absent", "HSTS missing"),
                "technical_detail": self._t(
                    "L'en-tête Strict-Transport-Security (HSTS) est absent du serveur.",
                    "The Strict-Transport-Security (HSTS) header is missing from the server."
                ),
                "plain_explanation": self._t(
                    "Les navigateurs peuvent se connecter à votre site en HTTP non chiffré, exposant vos visiteurs aux interceptions.",
                    "Browsers can connect to your site over unencrypted HTTP, exposing your visitors to interception."
                ),
                "recommendation":   self._t(
                    "Activer HSTS : Strict-Transport-Security: max-age=31536000; includeSubDomains",
                    "Enable HSTS: Strict-Transport-Security: max-age=31536000; includeSubDomains"
                ),
            },
            {
                "name":             "Content-Security-Policy",
                "penalty":          8,
                "severity":         "MEDIUM",
                "title":            self._t("Content-Security-Policy absent", "Content-Security-Policy missing"),
                "technical_detail": self._t(
                    "Aucune politique CSP définie dans les en-têtes HTTP.",
                    "No CSP policy defined in the HTTP headers."
                ),
                "plain_explanation": self._t(
                    "Sans CSP, votre site est vulnérable aux attaques XSS qui permettent d'injecter du code malveillant dans vos pages.",
                    "Without CSP, your site is vulnerable to XSS attacks that allow malicious code injection into your pages."
                ),
                "recommendation":   self._t(
                    "Définir une politique Content-Security-Policy restrictive limitant les sources de contenu autorisées.",
                    "Define a restrictive Content-Security-Policy limiting allowed content sources."
                ),
            },
            {
                "name":             "X-Frame-Options",
                "penalty":          6,
                "severity":         "MEDIUM",
                "title":            self._t("Protection Clickjacking absente", "Clickjacking protection missing"),
                "technical_detail": self._t(
                    "L'en-tête X-Frame-Options est absent.",
                    "The X-Frame-Options header is missing."
                ),
                "plain_explanation": self._t(
                    "Votre site peut être intégré dans une iframe invisible sur un site malveillant pour tromper vos utilisateurs (clickjacking).",
                    "Your site can be embedded in an invisible iframe on a malicious website to trick your users (clickjacking)."
                ),
                "recommendation":   self._t(
                    "Ajouter X-Frame-Options: DENY ou SAMEORIGIN.",
                    "Add X-Frame-Options: DENY or SAMEORIGIN."
                ),
            },
            {
                "name":             "X-Content-Type-Options",
                "penalty":          4,
                "severity":         "LOW",
                "title":            self._t("X-Content-Type-Options absent", "X-Content-Type-Options missing"),
                "technical_detail": self._t(
                    "L'en-tête X-Content-Type-Options: nosniff est absent.",
                    "The X-Content-Type-Options: nosniff header is missing."
                ),
                "plain_explanation": self._t(
                    "Le navigateur peut interpréter incorrectement le type des fichiers servis, ouvrant la voie à des attaques par confusion de type MIME.",
                    "The browser may incorrectly interpret served file types, opening the door to MIME type confusion attacks."
                ),
                "recommendation":   self._t(
                    "Ajouter X-Content-Type-Options: nosniff à toutes les réponses HTTP.",
                    "Add X-Content-Type-Options: nosniff to all HTTP responses."
                ),
            },
            {
                "name":             "Referrer-Policy",
                "penalty":          2,
                "severity":         "LOW",
                "title":            self._t("Referrer-Policy absent", "Referrer-Policy missing"),
                "technical_detail": self._t(
                    "L'en-tête Referrer-Policy est absent.",
                    "The Referrer-Policy header is missing."
                ),
                "plain_explanation": self._t(
                    "L'URL complète de votre site peut être transmise lors des clics vers des sites externes, exposant des chemins ou paramètres sensibles.",
                    "Your site's full URL may be transmitted when users click to external sites, exposing sensitive paths or parameters."
                ),
                "recommendation":   self._t(
                    "Ajouter Referrer-Policy: strict-origin-when-cross-origin.",
                    "Add Referrer-Policy: strict-origin-when-cross-origin."
                ),
            },
        ]

    async def audit(self) -> list[Finding]:
        try:
            loop = asyncio.get_event_loop()
            headers = await asyncio.wait_for(
                loop.run_in_executor(None, self._fetch_headers_sync),
                timeout=SCAN_TIMEOUT_SEC + 3,
            )
        except (asyncio.TimeoutError, Exception):
            return []

        if headers is None:
            return []

        lower_headers = {k.lower(): v for k, v in headers.items()}
        findings: list[Finding] = []

        for cfg in self._get_security_headers():
            if cfg["name"].lower() not in lower_headers:
                findings.append(Finding(
                    category          = "En-têtes HTTP",
                    severity          = cfg["severity"],
                    title             = cfg["title"],
                    technical_detail  = cfg["technical_detail"],
                    plain_explanation = cfg["plain_explanation"],
                    penalty           = cfg["penalty"],
                    recommendation    = cfg["recommendation"],
                ))

        # Version du serveur exposée
        server = lower_headers.get("server", "")
        if server and any(c.isdigit() for c in server):
            findings.append(Finding(
                category          = "En-têtes HTTP",
                severity          = "LOW",
                title             = self._t("Version du serveur exposée", "Server version exposed"),
                technical_detail  = self._t(
                    f"L'en-tête Server révèle des informations techniques : '{server}'.",
                    f"The Server header reveals technical information: '{server}'."
                ),
                plain_explanation = self._t(
                    "Les attaquants peuvent cibler les versions de logiciels connues pour leurs failles.",
                    "Attackers can target software versions known for their vulnerabilities."
                ),
                penalty           = 3,
                recommendation    = self._t(
                    "Masquer ou neutraliser l'en-tête Server dans la configuration du serveur web.",
                    "Hide or neutralize the Server header in your web server configuration."
                ),
            ))

        # X-Powered-By exposé
        powered_by = lower_headers.get("x-powered-by", "")
        if powered_by:
            findings.append(Finding(
                category          = "En-têtes HTTP",
                severity          = "LOW",
                title             = self._t("Framework exposé (X-Powered-By)", "Framework exposed (X-Powered-By)"),
                technical_detail  = self._t(
                    f"L'en-tête X-Powered-By révèle la stack technique : '{powered_by}'.",
                    f"The X-Powered-By header reveals the technology stack: '{powered_by}'."
                ),
                plain_explanation = self._t(
                    "Les informations sur la technologie utilisée facilitent le ciblage d'exploits spécifiques.",
                    "Information about the technology used makes it easier to target specific exploits."
                ),
                penalty           = 3,
                recommendation    = self._t(
                    "Supprimer l'en-tête X-Powered-By de toutes les réponses HTTP.",
                    "Remove the X-Powered-By header from all HTTP responses."
                ),
            ))

        return findings

    def _fetch_headers_sync(self) -> dict[str, str] | None:
        """Tente HTTPS puis HTTP pour récupérer les en-têtes de réponse."""
        for scheme, cls in [("https", http.client.HTTPSConnection), ("http", http.client.HTTPConnection)]:
            try:
                conn = cls(self.domain, timeout=SCAN_TIMEOUT_SEC)
                conn.request("HEAD", "/", headers={"User-Agent": "Mozilla/5.0 (CyberHealth Security Audit)"})
                resp = conn.getresponse()
                conn.close()
                return dict(resp.getheaders())
            except Exception:
                continue
        return None


# ─────────────────────────────────────────────────────────────────────────────
# EmailSecurityAuditor — DKIM + MX
# ─────────────────────────────────────────────────────────────────────────────

class EmailSecurityAuditor(BaseAuditor):
    """Vérifie la configuration de sécurité email (DKIM, MX)."""

    COMMON_DKIM_SELECTORS = [
        "default", "google", "mail", "dkim", "k1",
        "selector1", "selector2", "s1", "s2", "email",
    ]

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        findings: list[Finding] = []

        # DKIM
        try:
            dkim_found = await asyncio.wait_for(
                loop.run_in_executor(None, self._check_dkim),
                timeout=SCAN_TIMEOUT_SEC,
            )
            if not dkim_found:
                findings.append(Finding(
                    category          = "Sécurité Email",
                    severity          = "MEDIUM",
                    title             = self._t("DKIM non détecté", "DKIM not detected"),
                    technical_detail  = self._t(
                        "Aucune signature DKIM trouvée sur les sélecteurs courants (_domainkey).",
                        "No DKIM signature found on common selectors (_domainkey)."
                    ),
                    plain_explanation = self._t(
                        "Sans DKIM, n'importe qui peut envoyer des emails en se faisant passer pour votre domaine, favorisant le phishing.",
                        "Without DKIM, anyone can send emails impersonating your domain, facilitating phishing."
                    ),
                    penalty           = 8,
                    recommendation    = self._t(
                        "Configurer DKIM chez votre hébergeur ou fournisseur email pour signer cryptographiquement vos emails.",
                        "Configure DKIM with your hosting provider or email provider to cryptographically sign your emails."
                    ),
                ))
        except (asyncio.TimeoutError, Exception):
            pass

        # MX
        try:
            mx_found = await asyncio.wait_for(
                loop.run_in_executor(None, self._check_mx),
                timeout=SCAN_TIMEOUT_SEC,
            )
            if not mx_found:
                findings.append(Finding(
                    category          = "Sécurité Email",
                    severity          = "INFO",
                    title             = self._t("Aucun serveur MX configuré", "No MX server configured"),
                    technical_detail  = self._t(
                        "Aucun enregistrement MX détecté pour ce domaine.",
                        "No MX record detected for this domain."
                    ),
                    plain_explanation = self._t(
                        "Ce domaine ne semble pas recevoir d'emails. Si c'est intentionnel, assurez-vous d'avoir une politique SPF de rejet.",
                        "This domain does not appear to receive emails. If intentional, ensure you have a SPF reject policy."
                    ),
                    penalty           = 0,
                    recommendation    = self._t(
                        "Si ce domaine envoie des emails, ajoutez des enregistrements MX et une politique SPF/DMARC complète.",
                        "If this domain sends emails, add MX records and a complete SPF/DMARC policy."
                    ),
                ))
        except (asyncio.TimeoutError, Exception):
            pass

        return findings

    def _check_dkim(self) -> bool:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = DNS_LIFETIME_SEC  # aligné sur SPF/DMARC (était 4.0, trop court)
        for selector in self.COMMON_DKIM_SELECTORS:
            try:
                resolver.resolve(f"{selector}._domainkey.{self.domain}", "TXT")
                return True
            except Exception:
                continue
        return False

    def _check_mx(self) -> bool:
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = DNS_LIFETIME_SEC  # aligné sur SPF/DMARC (était 4.0, trop court)
            resolver.resolve(self.domain, "MX")
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# TechExposureAuditor — Stack technique exposée
# ─────────────────────────────────────────────────────────────────────────────

class TechExposureAuditor(BaseAuditor):
    """Détecte l'exposition de la stack technique (CMS, frameworks)."""

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        try:
            findings = await asyncio.wait_for(
                loop.run_in_executor(None, self._detect_tech_sync),
                timeout=SCAN_TIMEOUT_SEC + 3,
            )
            return findings
        except (asyncio.TimeoutError, Exception):
            return []

    def _detect_tech_sync(self) -> list[Finding]:
        findings: list[Finding] = []

        body = ""
        headers: dict[str, str] = {}

        for scheme, cls in [("https", http.client.HTTPSConnection), ("http", http.client.HTTPConnection)]:
            try:
                conn = cls(self.domain, timeout=SCAN_TIMEOUT_SEC)
                conn.request("GET", "/", headers={"User-Agent": "Mozilla/5.0 (CyberHealth Security Audit)"})
                resp = conn.getresponse()
                body = resp.read(8192).decode("utf-8", errors="ignore")
                headers = {k.lower(): v for k, v in resp.getheaders()}
                conn.close()
                break
            except Exception:
                continue

        if not body:
            return []

        body_lower = body.lower()

        # ── WordPress ──────────────────────────────────────────────────────────
        is_wp = "wp-content" in body_lower or "wp-json" in body_lower or "wordpress" in body_lower
        if is_wp:
            findings.append(Finding(
                category          = "Exposition Technologique",
                severity          = "MEDIUM",
                title             = self._t("CMS WordPress détecté", "WordPress CMS detected"),
                technical_detail  = self._t(
                    "Des marqueurs WordPress ont été détectés dans le code source de la page d'accueil.",
                    "WordPress markers detected in the homepage source code."
                ),
                plain_explanation = self._t(
                    "WordPress est le CMS le plus attaqué au monde. Les versions non maintenues font l'objet d'attaques automatisées quotidiennes.",
                    "WordPress is the most attacked CMS in the world. Unmaintained versions face automated attacks daily."
                ),
                penalty           = 5,
                recommendation    = self._t(
                    "Maintenir WordPress, les thèmes et plugins à jour. Activer un WAF et la double authentification sur /wp-admin.",
                    "Keep WordPress, themes and plugins up to date. Enable a WAF and two-factor authentication on /wp-admin."
                ),
            ))

            # Interface /wp-admin accessible
            try:
                conn2 = http.client.HTTPSConnection(self.domain, timeout=SCAN_TIMEOUT_SEC)  # était 3s hardcodé
                conn2.request("HEAD", "/wp-admin/", headers={"User-Agent": "Mozilla/5.0"})
                r2 = conn2.getresponse()
                conn2.close()
                if r2.status in (200, 301, 302):
                    findings.append(Finding(
                        category          = "Exposition Technologique",
                        severity          = "HIGH",
                        title             = self._t(
                            "Interface admin WordPress accessible",
                            "WordPress admin interface accessible"
                        ),
                        technical_detail  = self._t(
                            "/wp-admin retourne HTTP " + str(r2.status) + ", accessible publiquement.",
                            "/wp-admin returns HTTP " + str(r2.status) + ", publicly accessible."
                        ),
                        plain_explanation = self._t(
                            "L'interface d'administration est accessible depuis Internet et peut faire l'objet d'attaques par force brute sur les mots de passe.",
                            "The admin interface is accessible from the internet and may be subject to brute-force password attacks."
                        ),
                        penalty           = 10,
                        recommendation    = self._t(
                            "Restreindre l'accès à /wp-admin par liste blanche d'IP ou activer la double authentification.",
                            "Restrict access to /wp-admin by IP whitelist or enable two-factor authentication."
                        ),
                    ))
            except Exception:
                pass

        # ── Drupal ────────────────────────────────────────────────────────────
        if "drupal" in body_lower or "drupal" in str(headers):
            findings.append(Finding(
                category          = "Exposition Technologique",
                severity          = "MEDIUM",
                title             = self._t("CMS Drupal détecté", "Drupal CMS detected"),
                technical_detail  = self._t(
                    "Des marqueurs Drupal ont été détectés dans la page ou les en-têtes.",
                    "Drupal markers detected in the page or headers."
                ),
                plain_explanation = self._t(
                    "Drupal, comme tout CMS, doit être maintenu à jour pour éviter l'exploitation de failles connues.",
                    "Drupal, like any CMS, must be kept up to date to avoid exploitation of known vulnerabilities."
                ),
                penalty           = 4,
                recommendation    = self._t(
                    "Maintenir Drupal et ses modules à jour. Activer les notifications de sécurité automatiques.",
                    "Keep Drupal and its modules up to date. Enable automatic security notifications."
                ),
            ))

        # ── PHP exposé ────────────────────────────────────────────────────────
        powered_by = headers.get("x-powered-by", "")
        if "php" in powered_by.lower() and any(c.isdigit() for c in powered_by):
            findings.append(Finding(
                category          = "Exposition Technologique",
                severity          = "LOW",
                title             = self._t("Version PHP exposée", "PHP version exposed"),
                technical_detail  = self._t(
                    f"X-Powered-By révèle la version PHP : '{powered_by}'.",
                    f"X-Powered-By reveals the PHP version: '{powered_by}'."
                ),
                plain_explanation = self._t(
                    "Connaître la version de PHP facilite la recherche de failles spécifiques à cette version.",
                    "Knowing the PHP version makes it easier to find vulnerabilities specific to that version."
                ),
                penalty           = 4,
                recommendation    = self._t(
                    "Masquer la version PHP dans php.ini : expose_php = Off",
                    "Hide the PHP version in php.ini: expose_php = Off"
                ),
            ))

        return findings


# ─────────────────────────────────────────────────────────────────────────────
# ReputationAuditor — DNSBL
# ─────────────────────────────────────────────────────────────────────────────

class ReputationAuditor(BaseAuditor):
    """Vérifie la réputation du domaine/IP via les listes noires DNS (DNSBL)."""

    DNSBL_SERVERS = [
        "zen.spamhaus.org",
        "bl.spamcop.net",
        "dnsbl.sorbs.net",
    ]

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        findings: list[Finding] = []

        try:
            ip = await asyncio.wait_for(
                loop.run_in_executor(None, self._resolve_ip),
                timeout=SCAN_TIMEOUT_SEC,
            )
            if not ip:
                return []

            blacklisted = await asyncio.wait_for(
                loop.run_in_executor(None, self._check_dnsbl, ip),
                timeout=SCAN_TIMEOUT_SEC,
            )

            if blacklisted:
                findings.append(Finding(
                    category          = "Réputation du Domaine",
                    severity          = "CRITICAL",
                    title             = self._t("Domaine/IP listé en blacklist", "Domain/IP listed on blacklist"),
                    technical_detail  = self._t(
                        f"L'IP {ip} est référencée dans : {', '.join(blacklisted)}.",
                        f"IP {ip} is listed in: {', '.join(blacklisted)}."
                    ),
                    plain_explanation = self._t(
                        "Votre domaine ou serveur est inscrit sur des listes noires. "
                        "Les emails envoyés depuis ce domaine sont probablement bloqués ou marqués comme spam.",
                        "Your domain or server is listed on blacklists. "
                        "Emails sent from this domain are likely blocked or marked as spam."
                    ),
                    penalty           = 20,
                    recommendation    = self._t(
                        "Demander la suppression auprès des opérateurs des blacklists. Vérifier si le serveur a été compromis.",
                        "Request removal from blacklist operators. Check whether the server has been compromised."
                    ),
                ))
            else:
                findings.append(Finding(
                    category          = "Réputation du Domaine",
                    severity          = "INFO",
                    title             = self._t("Réputation email vérifiée", "Email reputation verified"),
                    technical_detail  = self._t(
                        f"L'IP {ip} n'est présente dans aucune liste noire testée.",
                        f"IP {ip} is not listed on any tested blacklist."
                    ),
                    plain_explanation = self._t(
                        "Bonne nouvelle — votre domaine n'est pas blacklisté. "
                        "Vos emails ont plus de chances d'arriver en boîte de réception.",
                        "Good news — your domain is not blacklisted. "
                        "Your emails are more likely to reach the inbox."
                    ),
                    penalty           = 0,
                    recommendation    = self._t(
                        "Maintenir les bonnes pratiques d'envoi email (SPF, DKIM, DMARC) pour préserver cette réputation.",
                        "Maintain good email sending practices (SPF, DKIM, DMARC) to preserve this reputation."
                    ),
                ))

        except (asyncio.TimeoutError, Exception):
            pass

        return findings

    def _resolve_ip(self) -> str | None:
        try:
            return socket.gethostbyname(self.domain)
        except Exception:
            return None

    def _check_dnsbl(self, ip: str) -> list[str]:
        reversed_ip = ".".join(reversed(ip.split(".")))
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 3.0
        blacklisted: list[str] = []
        for dnsbl in self.DNSBL_SERVERS:
            try:
                resolver.resolve(f"{reversed_ip}.{dnsbl}", "A")
                blacklisted.append(dnsbl)
            except Exception:
                continue
        return blacklisted
