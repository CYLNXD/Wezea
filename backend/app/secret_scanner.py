"""
backend/app/secret_scanner.py

Détection de secrets/API keys exposés dans les bundles JS publics d'une app vérifiée.
Pattern-matching sur les formats connus : AWS, Stripe, GitHub, Google, Slack, etc.

Lecture seule — aucun appel destructif.
"""
from __future__ import annotations

import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# ─── Configuration ─────────────────────────────────────────────────────────────

SECRET_TIMEOUT   = 8          # secondes par requête HTTP
MAX_SCRIPTS      = 5          # max de fichiers JS à fetcher et analyser
MAX_SCRIPT_SIZE  = 500_000    # octets — ignorer les bundles trop volumineux

# ─── Patterns de secrets connus ────────────────────────────────────────────────

@dataclass
class SecretPattern:
    name:        str
    regex:       re.Pattern
    severity:    str
    penalty:     int
    description: str
    recommendation: str


_PATTERNS: list[SecretPattern] = [
    SecretPattern(
        name        = "AWS Access Key ID",
        regex       = re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
        severity    = "CRITICAL",
        penalty     = 30,
        description = (
            "Une clé d'accès AWS (AKIA…) est exposée dans le bundle JS public. "
            "Elle permet d'accéder aux ressources cloud AWS et peut entraîner "
            "des coûts importants ou une exfiltration de données."
        ),
        recommendation = (
            "Révoquer immédiatement la clé dans AWS IAM → Security credentials. "
            "Déplacer tous les credentials AWS dans des variables d'environnement "
            "serveur uniquement — jamais dans le code front-end."
        ),
    ),
    SecretPattern(
        name        = "Stripe Live Secret Key",
        regex       = re.compile(r'\bsk_live_[0-9a-zA-Z]{24,}'),
        severity    = "CRITICAL",
        penalty     = 30,
        description = (
            "Une clé secrète Stripe Live (sk_live_…) est visible côté client. "
            "Elle permet de déclencher des paiements, rembourser des transactions "
            "et d'accéder à l'intégralité des données de votre compte Stripe."
        ),
        recommendation = (
            "Révoquer la clé immédiatement dans Stripe Dashboard → Developers → API keys. "
            "Les clés secrètes (sk_) ne doivent exister que côté serveur. "
            "Seule la clé publiable (pk_) peut être exposée côté client."
        ),
    ),
    SecretPattern(
        name        = "GitHub Personal Access Token",
        regex       = re.compile(r'\bghp_[A-Za-z0-9]{36}\b'),
        severity    = "CRITICAL",
        penalty     = 25,
        description = (
            "Un token GitHub (ghp_…) est exposé dans le bundle public. "
            "Il donne accès en lecture/écriture aux repositories associés "
            "et peut être utilisé pour exfiltrer votre code source."
        ),
        recommendation = (
            "Révoquer le token dans GitHub → Settings → Developer settings → "
            "Personal access tokens. Utiliser des variables d'environnement CI/CD "
            "plutôt que d'inclure des tokens dans le bundle front-end."
        ),
    ),
    SecretPattern(
        name        = "GitHub Fine-Grained Token",
        regex       = re.compile(r'\bgithub_pat_[A-Za-z0-9_]{82}\b'),
        severity    = "CRITICAL",
        penalty     = 25,
        description = (
            "Un token GitHub fine-grained (github_pat_…) est exposé dans le bundle public."
        ),
        recommendation = (
            "Révoquer le token dans GitHub → Settings → Developer settings → "
            "Fine-grained personal access tokens."
        ),
    ),
    SecretPattern(
        name        = "PEM Private Key",
        regex       = re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
        severity    = "CRITICAL",
        penalty     = 30,
        description = (
            "Une clé privée cryptographique (format PEM) est présente dans le bundle JS. "
            "Elle peut être utilisée pour usurper l'identité du serveur, "
            "déchiffrer des communications TLS ou signer des artefacts malveillants."
        ),
        recommendation = (
            "Supprimer immédiatement la clé privée du code front-end. "
            "Révoquer et régénérer le certificat/la clé associée. "
            "Les clés privées ne doivent jamais quitter le serveur."
        ),
    ),
    SecretPattern(
        name        = "Stripe Test Secret Key",
        regex       = re.compile(r'\bsk_test_[0-9a-zA-Z]{24,}'),
        severity    = "HIGH",
        penalty     = 15,
        description = (
            "Une clé secrète Stripe de test (sk_test_…) est exposée côté client. "
            "Elle révèle l'implémentation Stripe et peut permettre des abus "
            "sur votre environnement de test."
        ),
        recommendation = (
            "Déplacer la clé Stripe test dans les variables d'environnement serveur. "
            "Même en environnement de test, les clés secrètes (sk_) doivent rester "
            "exclusivement côté serveur."
        ),
    ),
    SecretPattern(
        name        = "SendGrid API Key",
        regex       = re.compile(r'\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b'),
        severity    = "HIGH",
        penalty     = 20,
        description = (
            "Une clé API SendGrid (SG.…) est exposée dans le bundle public. "
            "Elle permet d'envoyer des emails depuis votre compte, "
            "d'accéder aux statistiques et éventuellement à la liste de contacts."
        ),
        recommendation = (
            "Révoquer la clé dans SendGrid → Settings → API Keys. "
            "L'envoi d'emails doit toujours passer par votre backend, "
            "jamais directement depuis le navigateur."
        ),
    ),
    SecretPattern(
        name        = "Slack Bot/OAuth Token",
        regex       = re.compile(r'\bxox[baprs]-[0-9A-Za-z\-]{10,}'),
        severity    = "HIGH",
        penalty     = 20,
        description = (
            "Un token Slack (xox…) est exposé dans le bundle public. "
            "Il peut permettre de lire des messages privés, poster des messages "
            "ou accéder aux données de votre workspace Slack."
        ),
        recommendation = (
            "Révoquer le token dans Slack → Your Apps → OAuth & Permissions. "
            "Les tokens Slack doivent être stockés uniquement côté serveur "
            "dans des variables d'environnement."
        ),
    ),
    SecretPattern(
        name        = "Google API Key",
        regex       = re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'),
        severity    = "HIGH",
        penalty     = 18,
        description = (
            "Une clé API Google (AIza…) est exposée. Selon les APIs activées, "
            "elle peut permettre d'effectuer des requêtes facturées sur votre compte "
            "ou d'accéder à des données protégées (Maps, Vision, Translate, etc.)."
        ),
        recommendation = (
            "Restreindre la clé dans Google Cloud Console → APIs & Services → Credentials "
            "(restrictions par domaine HTTP referrer ou adresse IP). "
            "Idéalement, utiliser des clés distinctes par service avec les permissions minimales."
        ),
    ),
    SecretPattern(
        name        = "Firebase Server Key",
        regex       = re.compile(r'\bAAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140}\b'),
        severity    = "HIGH",
        penalty     = 20,
        description = (
            "Une clé serveur Firebase est exposée dans le bundle public. "
            "Elle permet d'envoyer des notifications push à tous les utilisateurs "
            "de votre application sans authentification."
        ),
        recommendation = (
            "Révoquer la clé dans Firebase Console → Project Settings → Cloud Messaging. "
            "Les clés serveur Firebase ne doivent jamais être exposées côté client — "
            "utiliser les clés de configuration publiques (apiKey) à la place."
        ),
    ),
    SecretPattern(
        name        = "Twilio Account SID + Auth Token",
        regex       = re.compile(r'\bAC[0-9a-f]{32}\b'),
        severity    = "HIGH",
        penalty     = 18,
        description = (
            "Un Account SID Twilio (AC…) est exposé. Combiné à un Auth Token, "
            "il permet d'envoyer des SMS/appels facturés sur votre compte Twilio."
        ),
        recommendation = (
            "Vérifier qu'aucun Auth Token Twilio n'est exposé à proximité. "
            "Les appels Twilio doivent passer par votre backend uniquement. "
            "Révoquer et régénérer dans Twilio Console → Account → API Keys & Tokens."
        ),
    ),
    SecretPattern(
        name        = "Brevo (Sendinblue) API Key",
        regex       = re.compile(r'\bxkeysib-[0-9a-f]{64}-[0-9A-Za-z]{12}\b'),
        severity    = "HIGH",
        penalty     = 18,
        description = (
            "Une clé API Brevo/Sendinblue est exposée dans le bundle public. "
            "Elle permet d'envoyer des emails, d'accéder aux contacts et campagnes."
        ),
        recommendation = (
            "Révoquer la clé dans Brevo → SMTP & API → API Keys. "
            "Les appels aux APIs d'emailing doivent toujours passer par votre backend."
        ),
    ),
    SecretPattern(
        name        = "Mailchimp API Key",
        regex       = re.compile(r'\b[0-9a-f]{32}-us[0-9]{1,2}\b'),
        severity    = "MEDIUM",
        penalty     = 12,
        description = (
            "Une clé API Mailchimp est exposée (format {32hexchars}-usNN). "
            "Elle permet d'accéder aux listes de contacts et d'envoyer des campagnes."
        ),
        recommendation = (
            "Révoquer la clé dans Mailchimp → Account → Extras → API keys. "
            "Les appels Mailchimp doivent passer exclusivement par votre backend."
        ),
    ),
]

# ─── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SecretFinding:
    pattern_name:  str
    severity:      str
    penalty:       int
    description:   str
    recommendation: str
    matched_value: str    # masqué : sk_live_AbCd***…***Xy
    source_url:    str    # URL du bundle JS source
    context:       str    # ~40 caractères autour du match

    def to_dict(self) -> dict:
        return {
            "pattern_name":   self.pattern_name,
            "severity":       self.severity,
            "penalty":        self.penalty,
            "description":    self.description,
            "recommendation": self.recommendation,
            "matched_value":  self.matched_value,
            "source_url":     self.source_url,
            "context":        self.context,
        }


@dataclass
class SecretScanResult:
    findings:        list[SecretFinding] = field(default_factory=list)
    scripts_found:   int = 0
    scripts_scanned: int = 0
    error:           Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "findings":        [f.to_dict() for f in self.findings],
            "scripts_found":   self.scripts_found,
            "scripts_scanned": self.scripts_scanned,
            "error":           self.error,
        }


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _mask(value: str) -> str:
    """Masque un secret — conserve les 6 premiers et 2 derniers caractères."""
    if len(value) <= 10:
        return value[:4] + "***"
    return value[:6] + "***…***" + value[-2:]


def _context(text: str, start: int, end: int, window: int = 40) -> str:
    """Extrait le contexte autour d'un match (sans les newlines)."""
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    snippet = text[lo:hi]
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    return snippet


def _make_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    return ctx


def _fetch(url: str, timeout: int = SECRET_TIMEOUT) -> bytes:
    """Fetch l'URL et retourne les bytes (max MAX_SCRIPT_SIZE+1)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "CyberHealthScanner/1.0 (security-audit; read-only)"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_make_ssl_ctx()) as resp:
        return resp.read(MAX_SCRIPT_SIZE + 1)


def _extract_script_urls(html: str, base_url: str) -> list[str]:
    """Extrait les URLs des fichiers JS externes (<script src="...">)."""
    pattern = re.compile(r'<script[^>]+\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
    base_host = urllib.parse.urlparse(base_url).hostname or ""
    urls: list[str] = []
    for m in pattern.finditer(html):
        src = m.group(1).strip()
        if not src or src.startswith("data:"):
            continue
        full = urllib.parse.urljoin(base_url, src)
        script_host = urllib.parse.urlparse(full).hostname or ""
        # Analyser uniquement les scripts du même domaine
        if script_host == base_host or not script_host:
            urls.append(full)
    return urls


def _scan_content(content: str, source_url: str) -> list[SecretFinding]:
    """Analyse un bloc de texte avec tous les patterns, retourne les findings."""
    findings: list[SecretFinding] = []
    seen: set[tuple[str, str]] = set()  # (pattern_name, masked)

    for pat in _PATTERNS:
        for m in pat.regex.finditer(content):
            masked = _mask(m.group(0))
            key    = (pat.name, masked)
            if key in seen:
                continue
            seen.add(key)
            findings.append(SecretFinding(
                pattern_name   = pat.name,
                severity       = pat.severity,
                penalty        = pat.penalty,
                description    = pat.description,
                recommendation = pat.recommendation,
                matched_value  = masked,
                source_url     = source_url,
                context        = _context(content, m.start(), m.end()),
            ))
    return findings


# ─── Scanner principal ─────────────────────────────────────────────────────────

class SecretScanner:
    """Fetch les bundles JS publics d'une app et détecte les secrets exposés."""

    def __init__(self, base_url: str) -> None:
        url = base_url.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.base_url = url

    def run(self) -> SecretScanResult:
        result = SecretScanResult()
        all_findings: list[SecretFinding] = []

        try:
            # ── 1. Fetch la page principale ────────────────────────────────
            html_bytes = _fetch(self.base_url)
            html       = html_bytes.decode("utf-8", errors="replace")

            # ── 2. Scanner les blocs <script> inline ───────────────────────
            inline_re = re.compile(
                r'<script(?![^>]+\bsrc=)[^>]*>(.*?)</script>',
                re.DOTALL | re.IGNORECASE,
            )
            for m in inline_re.finditer(html):
                all_findings.extend(
                    _scan_content(m.group(1), self.base_url + " (inline)")
                )

            # ── 3. Trouver les scripts externes ────────────────────────────
            script_urls = _extract_script_urls(html, self.base_url)
            result.scripts_found = len(script_urls)

            # ── 4. Fetch + scanner chaque bundle (max MAX_SCRIPTS) ─────────
            for url in script_urls[:MAX_SCRIPTS]:
                try:
                    js_bytes = _fetch(url)
                    if len(js_bytes) > MAX_SCRIPT_SIZE:
                        continue   # Bundle trop volumineux — ignorer
                    js_text = js_bytes.decode("utf-8", errors="replace")
                    all_findings.extend(_scan_content(js_text, url))
                    result.scripts_scanned += 1
                except Exception:
                    pass  # Erreur réseau sur un script individuel — non-fatal

        except Exception as exc:
            result.error = str(exc)

        # ── Dédupliquer sur l'ensemble (même pattern + même valeur masquée) ──
        seen: set[tuple[str, str]] = set()
        deduped: list[SecretFinding] = []
        for f in all_findings:
            key = (f.pattern_name, f.matched_value)
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        # Trier par pénalité décroissante
        result.findings = sorted(deduped, key=lambda f: -f.penalty)
        return result
