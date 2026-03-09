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
            {
                "name":             "Permissions-Policy",
                "penalty":          2,
                "severity":         "LOW",
                "title":            self._t("Permissions-Policy absent", "Permissions-Policy missing"),
                "technical_detail": self._t(
                    "L'en-tête Permissions-Policy est absent. "
                    "Aucune restriction n'est définie sur l'accès aux APIs sensibles du navigateur.",
                    "The Permissions-Policy header is missing. "
                    "No restrictions are defined on access to sensitive browser APIs."
                ),
                "plain_explanation": self._t(
                    "Sans Permissions-Policy, du code tiers embarqué (publicités, trackers) peut accéder "
                    "à la caméra, au microphone ou à la géolocalisation de vos visiteurs sans leur consentement explicite.",
                    "Without Permissions-Policy, embedded third-party code (ads, trackers) may access "
                    "your visitors' camera, microphone, or geolocation without explicit consent."
                ),
                "recommendation":   self._t(
                    "Ajouter Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=() "
                    "pour désactiver les APIs non utilisées.",
                    "Add Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=() "
                    "to disable unused browser APIs."
                ),
            },
        ]

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()

        # ── Check HTTP → HTTPS redirect ──────────────────────────────────────
        try:
            redirects_to_https = await asyncio.wait_for(
                loop.run_in_executor(None, self._check_http_redirect),
                timeout=SCAN_TIMEOUT_SEC + 2,
            )
            if redirects_to_https is False:
                self._findings.append(Finding(
                    category="En-têtes HTTP",
                    severity="HIGH",
                    title=self._t(
                        "Pas de redirection HTTP → HTTPS",
                        "No HTTP → HTTPS redirect"
                    ),
                    technical_detail=self._t(
                        f"Le serveur répond sur http://{self.domain} sans rediriger vers HTTPS. "
                        "Les connexions non chiffrées sont acceptées.",
                        f"The server responds on http://{self.domain} without redirecting to HTTPS. "
                        "Unencrypted connections are accepted."
                    ),
                    plain_explanation=self._t(
                        "Vos visiteurs qui tapent votre adresse sans 'https://' se connectent en clair. "
                        "Leurs données (formulaires, cookies, mots de passe) circulent sans chiffrement "
                        "et peuvent être interceptées sur n'importe quel réseau Wi-Fi.",
                        "Visitors who type your address without 'https://' connect in plaintext. "
                        "Their data (forms, cookies, passwords) travels unencrypted "
                        "and can be intercepted on any Wi-Fi network."
                    ),
                    penalty=10,
                    recommendation=self._t(
                        "Configurez une redirection 301 permanente de HTTP vers HTTPS dans votre serveur web "
                        "(nginx: return 301 https://$host$request_uri; / Apache: RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]). "
                        "Activez également HSTS pour verrouiller les connexions futures.",
                        "Configure a permanent 301 redirect from HTTP to HTTPS in your web server "
                        "(nginx: return 301 https://$host$request_uri; / Apache: RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]). "
                        "Also enable HSTS to lock future connections."
                    ),
                ))
        except (asyncio.TimeoutError, Exception):
            pass

        # ── En-têtes de sécurité HTTPS ───────────────────────────────────────
        try:
            headers = await asyncio.wait_for(
                loop.run_in_executor(None, self._fetch_headers_sync),
                timeout=SCAN_TIMEOUT_SEC + 3,
            )
        except (asyncio.TimeoutError, Exception):
            return self._findings

        if headers is None:
            return self._findings

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

        return self._findings + findings

    def _check_http_redirect(self) -> bool | None:
        """
        Vérifie si une requête HTTP (port 80) redirige vers HTTPS.
        Retourne True si redirection HTTPS, False si pas de redirection, None si port 80 fermé.
        """
        try:
            conn = http.client.HTTPConnection(self.domain, timeout=SCAN_TIMEOUT_SEC)
            conn.request("HEAD", "/", headers={"User-Agent": "Mozilla/5.0 (CyberHealth Security Audit)"})
            resp = conn.getresponse()
            conn.close()
            # Redirection (3xx) vers https://
            if resp.status in (301, 302, 307, 308):
                location = resp.getheader("Location", "")
                return location.lower().startswith("https://")
            # Réponse 200 directement sur HTTP → pas de redirection
            return False
        except Exception:
            return None  # Port 80 fermé ou inaccessible — pas de finding

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
        mx_present = False
        try:
            mx_found = await asyncio.wait_for(
                loop.run_in_executor(None, self._check_mx),
                timeout=SCAN_TIMEOUT_SEC,
            )
            mx_present = mx_found
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

        # MTA-STS — seulement si le domaine a des serveurs mail (MX présents)
        if mx_present:
            try:
                mta_sts_found = await asyncio.wait_for(
                    loop.run_in_executor(None, self._check_mta_sts),
                    timeout=SCAN_TIMEOUT_SEC,
                )
                if not mta_sts_found:
                    findings.append(Finding(
                        category          = "Sécurité Email",
                        severity          = "LOW",
                        title             = self._t("MTA-STS non configuré", "MTA-STS not configured"),
                        technical_detail  = self._t(
                            f"Aucun enregistrement TXT _mta-sts.{self.domain} détecté. "
                            "Le chiffrement TLS des connexions SMTP entrantes n'est pas imposé.",
                            f"No TXT record found for _mta-sts.{self.domain}. "
                            "TLS encryption for incoming SMTP connections is not enforced."
                        ),
                        plain_explanation = self._t(
                            "Sans MTA-STS, les emails envoyés vers votre serveur peuvent transiter "
                            "en clair si un attaquant effectue une attaque de downgrade TLS. "
                            "Vos emails entrants ne sont pas garantis chiffrés bout-en-bout.",
                            "Without MTA-STS, emails sent to your server may travel in plaintext "
                            "if an attacker performs a TLS downgrade attack. "
                            "Your incoming emails are not guaranteed to be encrypted end-to-end."
                        ),
                        penalty           = 2,
                        recommendation    = self._t(
                            "Configurez MTA-STS : créez l'enregistrement TXT _mta-sts.votredomaine.com "
                            "avec 'v=STSv1; id=YYYYMMDD01' et hébergez le fichier de politique sur "
                            "https://mta-sts.votredomaine.com/.well-known/mta-sts.txt.",
                            "Configure MTA-STS: create the TXT record _mta-sts.yourdomain.com "
                            "with 'v=STSv1; id=YYYYMMDD01' and host the policy file at "
                            "https://mta-sts.yourdomain.com/.well-known/mta-sts.txt."
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

    def _check_mta_sts(self) -> bool:
        """Vérifie la présence de l'enregistrement TXT MTA-STS."""
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = DNS_LIFETIME_SEC
            answers = resolver.resolve(f"_mta-sts.{self.domain}", "TXT")
            for r in answers:
                if "v=STSv1" in r.to_text():
                    return True
            return False
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

# ─────────────────────────────────────────────────────────────────────────────
# DomainExpiryAuditor — Expiration du nom de domaine
# ─────────────────────────────────────────────────────────────────────────────

import json as _json
import urllib.request as _urllib_request
import urllib.error as _urllib_error
from datetime import datetime as _datetime, timezone as _timezone

class DomainExpiryAuditor(BaseAuditor):
    """
    Vérifie la date d'expiration du nom de domaine via RDAP (rdap.org).
    Génère un finding CRITICAL si < 14 jours, HIGH si < 30 jours, MEDIUM si < 60 jours.
    """

    CRITICAL_DAYS = 14
    HIGH_DAYS     = 30
    MEDIUM_DAYS   = 60

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._check_expiry),
                timeout=SCAN_TIMEOUT_SEC + 4,
            )
        except (asyncio.TimeoutError, Exception):
            pass
        return self._findings

    def _check_expiry(self) -> None:
        """Interroge l'API RDAP pour obtenir la date d'expiration du domaine."""
        try:
            # Extraire le domaine racine (supprimer sous-domaines) pour la requête RDAP
            parts = self.domain.split(".")
            root_domain = ".".join(parts[-2:]) if len(parts) >= 2 else self.domain

            url = f"https://rdap.org/domain/{root_domain}"
            req = _urllib_request.Request(
                url,
                headers={
                    "Accept": "application/rdap+json",
                    "User-Agent": "CyberHealth-Scanner/1.0 (security audit)",
                },
            )
            with _urllib_request.urlopen(req, timeout=SCAN_TIMEOUT_SEC + 2) as resp:
                data = _json.loads(resp.read())

            # Chercher la date d'expiration dans les events RDAP
            expiry_str: str | None = None
            for event in data.get("events", []):
                if event.get("eventAction") in ("expiration", "registrar expiration"):
                    expiry_str = event.get("eventDate")
                    break

            if not expiry_str:
                self._details["domain_expiry"] = {"status": "unknown"}
                return

            # Parser la date (format ISO 8601 : 2026-12-31T00:00:00Z)
            expiry_dt = _datetime.fromisoformat(
                expiry_str.replace("Z", "+00:00")
            ).replace(tzinfo=_timezone.utc)
            now = _datetime.now(_timezone.utc)
            days_left = (expiry_dt - now).days

            self._details["domain_expiry"] = {
                "status": "ok" if days_left > self.MEDIUM_DAYS else "warning",
                "days_left": days_left,
                "expiry_date": expiry_str[:10],
            }

            if days_left <= 0:
                self._findings.append(Finding(
                    category="Infrastructure",
                    severity="CRITICAL",
                    title=self._t(
                        f"Domaine expiré depuis {abs(days_left)} jours !",
                        f"Domain expired {abs(days_left)} days ago!"
                    ),
                    technical_detail=self._t(
                        f"Le domaine {root_domain} a expiré le {expiry_str[:10]}.",
                        f"Domain {root_domain} expired on {expiry_str[:10]}."
                    ),
                    plain_explanation=self._t(
                        "Votre domaine n'est plus actif. Votre site, vos emails et tous vos services "
                        "sont inaccessibles. Le domaine peut être réenregistré par quelqu'un d'autre.",
                        "Your domain is no longer active. Your website, emails and all services "
                        "are unreachable. The domain may be re-registered by someone else."
                    ),
                    penalty=50,
                    recommendation=self._t(
                        f"Renouvelez immédiatement le domaine {root_domain} via votre bureau d'enregistrement.",
                        f"Immediately renew domain {root_domain} through your registrar."
                    ),
                ))
            elif days_left <= self.CRITICAL_DAYS:
                self._findings.append(Finding(
                    category="Infrastructure",
                    severity="CRITICAL",
                    title=self._t(
                        f"Domaine expire dans {days_left} jours — URGENT",
                        f"Domain expires in {days_left} days — URGENT"
                    ),
                    technical_detail=self._t(
                        f"Le domaine {root_domain} expire le {expiry_str[:10]} "
                        f"({days_left} jours restants).",
                        f"Domain {root_domain} expires on {expiry_str[:10]} "
                        f"({days_left} days remaining)."
                    ),
                    plain_explanation=self._t(
                        "Dans moins de deux semaines, votre domaine expirera et votre site ainsi que "
                        "vos emails seront hors ligne. Un tiers pourrait enregistrer ce domaine.",
                        "In less than two weeks, your domain will expire and your website and "
                        "emails will go offline. A third party could register this domain."
                    ),
                    penalty=30,
                    recommendation=self._t(
                        f"Renouvelez d'urgence le domaine {root_domain} via votre bureau d'enregistrement. "
                        "Activez le renouvellement automatique pour éviter ce risque à l'avenir.",
                        f"Urgently renew domain {root_domain} through your registrar. "
                        "Enable auto-renewal to avoid this risk in the future."
                    ),
                ))
            elif days_left <= self.HIGH_DAYS:
                self._findings.append(Finding(
                    category="Infrastructure",
                    severity="HIGH",
                    title=self._t(
                        f"Domaine expire dans {days_left} jours",
                        f"Domain expires in {days_left} days"
                    ),
                    technical_detail=self._t(
                        f"Le domaine {root_domain} expire le {expiry_str[:10]}.",
                        f"Domain {root_domain} expires on {expiry_str[:10]}."
                    ),
                    plain_explanation=self._t(
                        "Votre domaine expire bientôt. Sans renouvellement rapide, votre site et "
                        "vos emails seront hors ligne dans moins d'un mois.",
                        "Your domain expires soon. Without quick renewal, your website and "
                        "emails will go offline within a month."
                    ),
                    penalty=15,
                    recommendation=self._t(
                        f"Renouvelez le domaine {root_domain} dès maintenant et activez "
                        "le renouvellement automatique chez votre bureau d'enregistrement.",
                        f"Renew domain {root_domain} now and enable "
                        "auto-renewal at your registrar."
                    ),
                ))
            elif days_left <= self.MEDIUM_DAYS:
                self._findings.append(Finding(
                    category="Infrastructure",
                    severity="MEDIUM",
                    title=self._t(
                        f"Domaine expire dans {days_left} jours — à renouveler",
                        f"Domain expires in {days_left} days — renewal needed"
                    ),
                    technical_detail=self._t(
                        f"Le domaine {root_domain} expire le {expiry_str[:10]}.",
                        f"Domain {root_domain} expires on {expiry_str[:10]}."
                    ),
                    plain_explanation=self._t(
                        "Votre domaine expire dans moins de 2 mois. "
                        "Pensez à le renouveler pour garantir la continuité de votre site et vos emails.",
                        "Your domain expires in less than 2 months. "
                        "Remember to renew it to ensure continuity of your website and emails."
                    ),
                    penalty=5,
                    recommendation=self._t(
                        f"Renouvelez le domaine {root_domain} et activez le renouvellement automatique.",
                        f"Renew domain {root_domain} and enable auto-renewal."
                    ),
                ))

        except (_urllib_error.URLError, _urllib_error.HTTPError, Exception):
            self._details["domain_expiry"] = {"status": "error"}
