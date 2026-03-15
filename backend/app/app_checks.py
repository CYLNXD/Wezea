"""
CyberHealth Scanner — Application Scanning
==========================================
AppAuditor : vérifie les vulnérabilités courantes d'applications web custom.

Checks couverts :
  1.  Fichiers sensibles exposés  (.env, .git, dumps SQL, backups…)
  2.  Panneaux d'administration   (phpMyAdmin, Adminer, /admin…)
  3.  Endpoints API non protégés  (Swagger, Actuator, phpinfo…)
  4.  Configuration CORS          (Access-Control-Allow-Origin: *)
  5.  Flags de sécurité des cookies (HttpOnly, Secure, SameSite)
  6.  Listing de répertoires
  7.  Mode debug / stack traces visibles
  8.  robots.txt révélant des chemins sensibles
  9.  Mixed content (formulaires/ressources HTTP sur page HTTPS)
  10. Bibliothèques JavaScript front obsolètes (jQuery, Angular 1.x…)

N'effectue aucun test d'injection actif — lecture seule (DAST passif).
"""

from __future__ import annotations

import asyncio
import http.client
import re
import ssl
from typing import Any

from app.scanner import BaseAuditor, Finding, SCAN_TIMEOUT_SEC


# ─────────────────────────────────────────────────────────────────────────────
# Chemins à tester  (path, titre, sévérité, pénalité)
# ─────────────────────────────────────────────────────────────────────────────

_SENSITIVE_FILES: list[tuple[str, str, str, int]] = [
    ("/.env",               "Fichier .env exposé",               "CRITICAL", 25),
    ("/.env.local",         "Fichier .env.local exposé",         "CRITICAL", 25),
    ("/.env.production",    "Fichier .env.production exposé",    "CRITICAL", 25),
    ("/.git/HEAD",          "Dépôt Git exposé (.git/HEAD)",      "CRITICAL", 20),
    ("/.git/config",        "Config Git exposée (.git/config)",  "CRITICAL", 20),
    ("/backup.sql",         "Dump SQL accessible",               "CRITICAL", 20),
    ("/dump.sql",           "Dump SQL accessible",               "CRITICAL", 20),
    ("/database.sql",       "Dump SQL accessible",               "CRITICAL", 20),
    ("/config.php.bak",     "Backup config PHP exposé",          "HIGH",     15),
    ("/wp-config.php.bak",  "Backup wp-config exposé",           "HIGH",     15),
    ("/.htpasswd",          "Fichier .htpasswd accessible",      "CRITICAL", 20),
    ("/composer.json",      "composer.json accessible",          "LOW",       3),
    ("/package.json",       "package.json accessible",           "LOW",       3),
]

_ADMIN_PATHS: list[tuple[str, str, str, int]] = [
    ("/phpmyadmin",         "phpMyAdmin accessible",             "CRITICAL", 20),
    ("/phpmyadmin/",        "phpMyAdmin accessible",             "CRITICAL", 20),
    ("/adminer.php",        "Adminer exposé",                    "CRITICAL", 20),
    ("/admin",              "Interface admin exposée (/admin)",  "HIGH",     10),
    ("/administrator",      "Interface admin Joomla exposée",    "HIGH",     10),
]

_API_PATHS: list[tuple[str, str, str, int]] = [
    ("/swagger",            "Documentation Swagger accessible",  "MEDIUM",    5),
    ("/swagger-ui.html",    "Documentation Swagger accessible",  "MEDIUM",    5),
    ("/api/docs",           "Documentation API accessible",      "MEDIUM",    5),
    ("/openapi.json",       "Schéma OpenAPI exposé",             "MEDIUM",    5),
    ("/v1/docs",            "Documentation API v1 accessible",   "MEDIUM",    5),
    ("/actuator",           "Spring Boot Actuator exposé",       "HIGH",     15),
    ("/actuator/env",       "Spring Actuator /env exposé",       "CRITICAL", 20),
    ("/phpinfo.php",        "phpinfo() accessible",              "HIGH",     12),
    ("/info.php",           "phpinfo() accessible",              "HIGH",     12),
    ("/server-status",      "Apache server-status accessible",   "MEDIUM",    8),
]

_ROBOTS_SENSITIVE_KEYWORDS = [
    "/admin", "/backup", "/config", "/private", "/secret",
    "/api/", "/internal", "/.env", "/.git", "/phpmyadmin",
    "/database", "/logs", "/tmp", "/staging",
]

_DEBUG_PATTERNS = [
    "traceback (most recent call last)",
    "exception in thread",
    "whoops!",
    "xdebug",
    "stack trace:",
    "symfony exception",
    "laravel.log",
    "rails.application",
    "activerecord::base",
]

# Bibliothèques JS front vulnérables connues
# (regex_pattern, lib_name, max_safe_version_tuple, severity, penalty, cve_ref)
_VULNERABLE_JS_LIBS: list[tuple[str, str, tuple[int, ...], str, int, str]] = [
    (r"jquery[.\-/](\d+\.\d+\.\d+)", "jQuery", (3, 5, 0),
     "HIGH", 10, "CVE-2020-11022 / CVE-2020-11023 (XSS)"),
    (r"angular[.\-/](\d+\.\d+\.\d+)", "AngularJS", (2, 0, 0),
     "HIGH", 10, "Multiple XSS — AngularJS 1.x EOL"),
    (r"bootstrap[.\-/](\d+\.\d+\.\d+)", "Bootstrap", (4, 6, 0),
     "MEDIUM", 5, "CVE-2024-6484 / CVE-2019-8331 (XSS)"),
    (r"lodash[.\-/](\d+\.\d+\.\d+)", "Lodash", (4, 17, 21),
     "MEDIUM", 5, "CVE-2021-23337 (Prototype Pollution)"),
]

_RE_FORM_HTTP = re.compile(r"<form[^>]+action\s*=\s*[\"']http://", re.IGNORECASE)
_RE_RESOURCE_HTTP = re.compile(
    r"<(?:script|link|img)[^>]+(?:src|href)\s*=\s*[\"']http://", re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────────────
# AppAuditor
# ─────────────────────────────────────────────────────────────────────────────

class AppAuditor(BaseAuditor):
    """
    Scan de vulnérabilités applicatives web (Application Scanning).

    Utilise le même protocole que BaseAuditor mais cible spécifiquement
    les erreurs de configuration d'applications web custom.
    """

    async def audit(self) -> list[Finding]:
        await asyncio.gather(
            self._check_sensitive_files(),
            self._check_admin_paths(),
            self._check_api_paths(),
            self._check_main_response(),
            self._check_robots_txt(),
            return_exceptions=True,
        )
        return self._findings

    # ── Fichiers sensibles ────────────────────────────────────────────────────

    # Patterns de validation du body pour les fichiers sensibles critiques.
    # Si le body ne contient pas au moins un de ces patterns, c'est probablement
    # une page 200 générique (SPA, custom 404, etc.) → faux positif.
    _BODY_VALIDATORS: dict[str, list[str]] = {
        "/.env":            ["=", "DB_", "APP_", "SECRET", "KEY", "PASSWORD"],
        "/.env.local":      ["=", "DB_", "APP_", "SECRET", "KEY", "PASSWORD"],
        "/.env.production": ["=", "DB_", "APP_", "SECRET", "KEY", "PASSWORD"],
        "/.git/HEAD":       ["ref: refs/"],
        "/.git/config":     ["[core]", "[remote"],
    }

    async def _check_sensitive_files(self) -> None:
        loop = asyncio.get_running_loop()
        seen_titles: set[str] = set()
        for path, title, severity, penalty in _SENSITIVE_FILES:
            if title in seen_titles:
                continue
            try:
                validators = self._BODY_VALIDATORS.get(path)
                if validators:
                    # GET + validation du body pour éviter les faux positifs
                    code, body = await loop.run_in_executor(
                        None, lambda p=path: self._get_status_and_body(p)
                    )
                    if code != 200 or not any(v in body for v in validators):
                        continue
                else:
                    code = await loop.run_in_executor(None, lambda p=path: self._head_or_get(p))
                    if code not in (200, 301, 302):
                        continue
                seen_titles.add(title)
                self._findings.append(Finding(
                    category="Fichiers sensibles",
                    severity=severity,
                    title=title,
                    technical_detail=f"HTTP {code} — {self.domain}{path}",
                    plain_explanation=(
                        f"Le fichier {path} est accessible publiquement. "
                        "Il peut contenir des clés API, mots de passe, tokens de base de données "
                        "ou la structure interne de l'application."
                    ),
                    penalty=penalty,
                    recommendation=(
                        f"Bloquer l'accès à {path} dans la configuration serveur. "
                        "nginx : `location ~ /\\.env {{ deny all; }}` — "
                        "Apache : `<Files .env> Require all denied </Files>`"
                    ),
                ))
                self._details.setdefault("exposed_files", []).append(path)
            except Exception:
                pass

    # ── Panneaux admin ────────────────────────────────────────────────────────

    async def _check_admin_paths(self) -> None:
        loop = asyncio.get_running_loop()
        seen: set[str] = set()
        for path, title, severity, penalty in _ADMIN_PATHS:
            if title in seen:
                continue
            try:
                code = await loop.run_in_executor(None, lambda p=path: self._get_status(p))
                # 302 est typiquement un redirect vers login → ne pas signaler
                if code == 200:
                    seen.add(title)
                    self._findings.append(Finding(
                        category="Exposition admin",
                        severity=severity,
                        title=title,
                        technical_detail=f"HTTP {code} — {self.domain}{path}",
                        plain_explanation=(
                            f"Le panneau d'administration {path} est accessible depuis internet "
                            "sans restriction d'IP. Un attaquant peut tenter des attaques par "
                            "force brute sur les identifiants."
                        ),
                        penalty=penalty,
                        recommendation=(
                            f"Restreindre l'accès à {path} aux IP de confiance uniquement "
                            "(VPN, IP de bureau), ou déplacer l'interface admin sur un port "
                            "non standard non exposé publiquement."
                        ),
                    ))
                    self._details.setdefault("exposed_admin", []).append(path)
            except Exception:
                pass

    # ── Endpoints API ─────────────────────────────────────────────────────────

    async def _check_api_paths(self) -> None:
        loop = asyncio.get_running_loop()
        seen: set[str] = set()
        for path, title, severity, penalty in _API_PATHS:
            if title in seen:
                continue
            try:
                code = await loop.run_in_executor(None, lambda p=path: self._get_status(p))
                if code == 200:
                    seen.add(title)
                    self._findings.append(Finding(
                        category="Exposition API",
                        severity=severity,
                        title=title,
                        technical_detail=f"HTTP {code} — {self.domain}{path}",
                        plain_explanation=(
                            f"L'endpoint {path} est accessible publiquement. "
                            "Il peut révéler la structure interne, les endpoints disponibles "
                            "et les paramètres attendus — informations précieuses pour un attaquant."
                        ),
                        penalty=penalty,
                        recommendation=(
                            f"Désactiver {path} en production ou le protéger par authentification. "
                            "Flask/FastAPI : utiliser des variables d'environnement pour activer "
                            "la documentation uniquement en développement."
                        ),
                    ))
                    self._details.setdefault("exposed_api", []).append(path)
            except Exception:
                pass

    # ── Réponse principale : CORS, cookies, debug, directory listing ──────────

    async def _check_main_response(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            headers, body, status_code = await loop.run_in_executor(
                None, self._fetch_main
            )
            self._details["http_status"] = status_code

            # ── CORS wildcard ─────────────────────────────────────────────────
            acao = headers.get("access-control-allow-origin", "")
            if acao.strip() == "*":
                self._findings.append(Finding(
                    category="Configuration CORS",
                    severity="HIGH",
                    title="CORS wildcard (*) configuré",
                    technical_detail="Access-Control-Allow-Origin: *",
                    plain_explanation=(
                        "Toute origine externe peut effectuer des requêtes cross-origin "
                        "vers votre application. Cela facilite les attaques CSRF avancées "
                        "et la lecture de données privées depuis n'importe quel site malveillant."
                    ),
                    penalty=10,
                    recommendation=(
                        "Remplacer `*` par une liste blanche explicite des origines autorisées. "
                        "Ex : `Access-Control-Allow-Origin: https://monapp.fr`"
                    ),
                ))
                self._details["cors"] = "wildcard"

            # ── Cookies sans flags ────────────────────────────────────────────
            # http.client.HTTPMessage.get_all() n'existe pas — on parse manuellement
            raw_headers = str(headers)
            cookies_raw = [
                line.split(":", 1)[1].strip()
                for line in raw_headers.splitlines()
                if line.lower().startswith("set-cookie:")
            ]
            missing_secure: list[str] = []
            missing_httponly: list[str] = []
            missing_samesite: list[str] = []
            for cookie in cookies_raw:
                name = cookie.split("=")[0].strip()
                cl = cookie.lower()
                if "secure" not in cl:
                    missing_secure.append(name)
                if "httponly" not in cl:
                    missing_httponly.append(name)
                if "samesite=" not in cl:
                    missing_samesite.append(name)

            if missing_secure:
                self._findings.append(Finding(
                    category="Cookies",
                    severity="MEDIUM",
                    title="Cookies sans flag Secure",
                    technical_detail=f"Cookies concernés : {', '.join(missing_secure[:5])}",
                    plain_explanation=(
                        "Ces cookies peuvent être transmis sur des connexions HTTP non chiffrées, "
                        "permettant leur interception par un attaquant (man-in-the-middle)."
                    ),
                    penalty=5,
                    recommendation=(
                        "Ajouter le flag `Secure` à tous les cookies de session : "
                        "`Set-Cookie: session=...; Secure; HttpOnly; SameSite=Strict`"
                    ),
                ))
            if missing_httponly:
                self._findings.append(Finding(
                    category="Cookies",
                    severity="MEDIUM",
                    title="Cookies sans flag HttpOnly",
                    technical_detail=f"Cookies concernés : {', '.join(missing_httponly[:5])}",
                    plain_explanation=(
                        "Ces cookies sont accessibles via JavaScript. "
                        "En cas d'attaque XSS, ils peuvent être volés et utilisés "
                        "pour usurper l'identité de l'utilisateur."
                    ),
                    penalty=5,
                    recommendation=(
                        "Ajouter le flag `HttpOnly` à tous les cookies de session. "
                        "Django : `SESSION_COOKIE_HTTPONLY = True` — "
                        "Express : `app.use(session({ cookie: { httpOnly: true } }))`"
                    ),
                ))
            if missing_samesite:
                self._findings.append(Finding(
                    category="Cookies",
                    severity="LOW",
                    title="Cookies sans attribut SameSite",
                    technical_detail=f"Cookies concernés : {', '.join(missing_samesite[:5])}",
                    plain_explanation=(
                        "Sans l'attribut SameSite, ces cookies sont envoyés avec les requêtes "
                        "cross-site, ce qui facilite les attaques CSRF (Cross-Site Request Forgery)."
                    ),
                    penalty=3,
                    recommendation=(
                        "Ajouter `SameSite=Lax` (ou `Strict`) à tous les cookies de session. "
                        "Django : `SESSION_COOKIE_SAMESITE = 'Lax'` — "
                        "Express : `app.use(session({ cookie: { sameSite: 'lax' } }))`"
                    ),
                ))

            # ── Directory listing ─────────────────────────────────────────────
            body_lower = body.lower()
            if "index of /" in body_lower or "directory listing" in body_lower:
                self._findings.append(Finding(
                    category="Configuration serveur",
                    severity="MEDIUM",
                    title="Listing de répertoires activé",
                    technical_detail="La réponse principale contient 'Index of /' ou 'Directory Listing'",
                    plain_explanation=(
                        "Le serveur expose la liste des fichiers de l'application. "
                        "Un attaquant peut explorer l'arborescence complète et télécharger "
                        "des fichiers sensibles."
                    ),
                    penalty=8,
                    recommendation=(
                        "Désactiver le directory listing. "
                        "nginx : `autoindex off;` — Apache : `Options -Indexes`"
                    ),
                ))

            # ── Mode debug / stack traces ─────────────────────────────────────
            body_excerpt = body[:6000].lower()
            for pattern in _DEBUG_PATTERNS:
                if pattern in body_excerpt:
                    self._findings.append(Finding(
                        category="Mode debug",
                        severity="HIGH",
                        title="Mode debug / stack trace visible",
                        technical_detail=f"Pattern détecté dans la réponse : '{pattern}'",
                        plain_explanation=(
                            "L'application affiche des informations techniques internes "
                            "(chemins de fichiers, noms de variables, requêtes SQL). "
                            "Ces données facilitent des attaques ciblées."
                        ),
                        penalty=12,
                        recommendation=(
                            "Désactiver le mode debug en production. "
                            "Django : `DEBUG = False` — "
                            "Laravel : `APP_DEBUG=false` dans `.env` — "
                            "Configurer un handler d'erreurs personnalisé sans détails techniques."
                        ),
                    ))
                    break

            # ── Mixed content ────────────────────────────────────────────────
            self._check_mixed_content(body)

            # ── Bibliothèques JS obsolètes ───────────────────────────────────
            self._check_outdated_js(body)

        except Exception:
            pass

    # ── Mixed content ────────────────────────────────────────────────────────

    def _check_mixed_content(self, body: str) -> None:
        """Détecte les formulaires et ressources chargées en HTTP sur une page HTTPS."""
        if not body:
            return

        # Formulaires POST vers HTTP (risque de fuite de données)
        http_forms = _RE_FORM_HTTP.findall(body)
        if http_forms:
            self._findings.append(Finding(
                category="Mixed Content",
                severity="MEDIUM",
                title="Formulaire soumis vers HTTP (non chiffré)",
                technical_detail=(
                    f"{len(http_forms)} formulaire(s) avec action='http://…' détecté(s)"
                ),
                plain_explanation=(
                    "Un ou plusieurs formulaires envoient les données utilisateur "
                    "(identifiants, données personnelles) vers une URL non chiffrée (HTTP). "
                    "Un attaquant sur le réseau peut intercepter ces données."
                ),
                penalty=8,
                recommendation=(
                    "Remplacer toutes les URLs `http://` dans les attributs `action` des "
                    "formulaires par `https://`, ou utiliser des chemins relatifs (`/submit`)."
                ),
            ))

        # Ressources externes chargées en HTTP (scripts, CSS, images)
        http_resources = _RE_RESOURCE_HTTP.findall(body)
        if http_resources:
            self._findings.append(Finding(
                category="Mixed Content",
                severity="MEDIUM",
                title="Ressources chargées en HTTP (mixed content)",
                technical_detail=(
                    f"{len(http_resources)} ressource(s) <script>/<link>/<img> en http:// détectée(s)"
                ),
                plain_explanation=(
                    "Des scripts, feuilles de style ou images sont chargés via HTTP non chiffré. "
                    "Un attaquant peut modifier ces ressources en transit et injecter du code "
                    "malveillant dans la page (attaque man-in-the-middle)."
                ),
                penalty=5,
                recommendation=(
                    "Charger toutes les ressources externes via HTTPS. "
                    "Ajouter l'en-tête `Content-Security-Policy: upgrade-insecure-requests` "
                    "pour forcer la migration automatique."
                ),
            ))

    # ── Bibliothèques JS obsolètes ─────────────────────────────────────────

    @staticmethod
    def _parse_semver(version_str: str) -> tuple[int, ...] | None:
        """Parse '3.5.1' → (3, 5, 1). Retourne None si invalide."""
        try:
            return tuple(int(x) for x in version_str.split("."))
        except (ValueError, AttributeError):
            return None

    def _check_outdated_js(self, body: str) -> None:
        """Détecte les bibliothèques JS front obsolètes/vulnérables dans le HTML."""
        if not body:
            return

        detected: list[str] = []
        for pattern, lib_name, max_safe, severity, penalty, cve_ref in _VULNERABLE_JS_LIBS:
            match = re.search(pattern, body, re.IGNORECASE)
            if not match:
                continue
            version = self._parse_semver(match.group(1))
            if version is None:
                continue
            if version < max_safe:
                detected.append(f"{lib_name} {match.group(1)}")
                self._findings.append(Finding(
                    category="Bibliothèques obsolètes",
                    severity=severity,
                    title=f"{lib_name} {match.group(1)} — version vulnérable",
                    technical_detail=f"{lib_name} {match.group(1)} < {'.'.join(str(x) for x in max_safe)} — {cve_ref}",
                    plain_explanation=(
                        f"La bibliothèque {lib_name} version {match.group(1)} contient des "
                        "vulnérabilités connues (XSS, injection de code). Un attaquant peut les "
                        "exploiter pour voler des données utilisateur ou prendre le contrôle de sessions."
                    ),
                    penalty=penalty,
                    recommendation=(
                        f"Mettre à jour {lib_name} vers la dernière version stable. "
                        f"Version minimale sécurisée : {'.'.join(str(x) for x in max_safe)}."
                    ),
                ))

        if detected:
            self._details["outdated_js"] = detected

    # ── robots.txt ────────────────────────────────────────────────────────────

    async def _check_robots_txt(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            body = await loop.run_in_executor(None, lambda: self._fetch_text("/robots.txt"))
            if not body:
                return
            found: list[str] = []
            for line in body.splitlines():
                line_lower = line.lower().strip()
                if line_lower.startswith("disallow:"):
                    path = line_lower.replace("disallow:", "").strip()
                    if any(kw in path for kw in _ROBOTS_SENSITIVE_KEYWORDS):
                        found.append(path)
            if found:
                self._findings.append(Finding(
                    category="Divulgation d'information",
                    severity="LOW",
                    title="robots.txt révèle des chemins sensibles",
                    technical_detail=f"Chemins Disallow déclarés : {', '.join(found[:8])}",
                    plain_explanation=(
                        "Le fichier robots.txt liste des répertoires sensibles. "
                        "Bien que destiné aux robots indexeurs, ce fichier est public "
                        "et guide les attaquants vers des zones d'intérêt."
                    ),
                    penalty=3,
                    recommendation=(
                        "Ne pas lister de chemins sensibles dans robots.txt. "
                        "Protéger ces zones par authentification — l'obscurcissement n'est pas "
                        "une mesure de sécurité."
                    ),
                ))
                self._details["robots_sensitive_paths"] = found[:8]
        except Exception:
            pass

    # ── Utilitaires réseau synchrones ─────────────────────────────────────────

    def _ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _get_conn(self) -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(
            self.domain, timeout=SCAN_TIMEOUT_SEC, context=self._ssl_context()
        )

    def _head_or_get(self, path: str) -> int:
        """HEAD avec fallback GET si le serveur ne supporte pas HEAD."""
        conn = self._get_conn()
        try:
            conn.request("HEAD", path, headers={"User-Agent": "Mozilla/5.0 CyberHealth-Scanner/1.0"})
            r = conn.getresponse()
            return r.status
        except Exception:
            pass
        finally:
            conn.close()
        conn = self._get_conn()
        try:
            conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 CyberHealth-Scanner/1.0"})
            r = conn.getresponse()
            return r.status
        finally:
            conn.close()

    def _get_status(self, path: str) -> int:
        conn = self._get_conn()
        try:
            conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 CyberHealth-Scanner/1.0"})
            r = conn.getresponse()
            return r.status
        finally:
            conn.close()

    def _get_status_and_body(self, path: str) -> tuple[int, str]:
        """GET request returning (status_code, body_excerpt)."""
        conn = self._get_conn()
        try:
            conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 CyberHealth-Scanner/1.0"})
            r = conn.getresponse()
            body = r.read(2048).decode("utf-8", errors="replace") if r.status == 200 else ""
            return r.status, body
        finally:
            conn.close()

    def _fetch_main(self) -> tuple[Any, str, int]:
        """Fetch la racine — retourne (headers, body_excerpt, status)."""
        conn = self._get_conn()
        try:
            conn.request("GET", "/", headers={
                "User-Agent": "Mozilla/5.0 CyberHealth-Scanner/1.0",
                "Accept": "text/html,*/*",
            })
            r = conn.getresponse()
            body = r.read(8192).decode("utf-8", errors="replace")
            return r.headers, body, r.status
        finally:
            conn.close()

    def _fetch_text(self, path: str) -> str:
        conn = self._get_conn()
        try:
            conn.request("GET", path, headers={"User-Agent": "Mozilla/5.0 CyberHealth-Scanner/1.0"})
            r = conn.getresponse()
            if r.status == 200:
                return r.read(4096).decode("utf-8", errors="replace")
            return ""
        finally:
            conn.close()
