"""
CyberHealth Scanner — Extra Security Checks
============================================
Adds 4 new check categories:
  1. HTTP Security Headers  (CSP, HSTS, X-Frame-Options, X-Content-Type-Options…)
  2. SPF / DKIM / DMARC     (email authentication records)
  3. Technology Exposure    (Server, X-Powered-By, CMS fingerprinting)
  4. Domain Reputation      (DNSBL / public blacklists)

Drop this file in:  /home/cyberhealth/app/backend/app/services/extra_checks.py
Then call:          run_extra_checks(domain)  → list[dict]

Each finding dict matches the existing schema:
  {
    "category":       str,   # e.g. "En-têtes HTTP"
    "severity":       str,   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    "message":        str,
    "recommendation": str,
  }
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Optional

import httpx

# dnspython — installed with:  pip install dnspython
try:
    import dns.resolver
    import dns.exception
    _DNS_OK = True
except ImportError:
    _DNS_OK = False

# ─── constants ───────────────────────────────────────────────────────────────

TIMEOUT_HTTP  = 10   # seconds
TIMEOUT_DNS   = 5    # seconds

SECURITY_HEADERS = {
    "strict-transport-security":       ("HSTS",                    "HIGH"),
    "content-security-policy":         ("Content-Security-Policy", "HIGH"),
    "x-frame-options":                 ("X-Frame-Options",         "MEDIUM"),
    "x-content-type-options":          ("X-Content-Type-Options",  "MEDIUM"),
    "referrer-policy":                 ("Referrer-Policy",         "LOW"),
    "permissions-policy":              ("Permissions-Policy",      "LOW"),
    "x-xss-protection":                ("X-XSS-Protection",        "LOW"),
}

# Common DKIM selectors to probe
DKIM_SELECTORS = [
    "default", "google", "mail", "k1", "k2",
    "selector1", "selector2", "dkim", "email",
    "s1", "s2", "mandrill", "brevo", "sendgrid",
]

# Public DNSBL zones
DNSBL_ZONES = [
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "dnsbl.sorbs.net",
    "b.barracudacentral.org",
    "dnsbl-1.uceprotect.net",
]

# Headers that leak technology info
TECH_HEADERS = [
    "server",
    "x-powered-by",
    "x-aspnet-version",
    "x-aspnetmvc-version",
    "x-generator",
    "x-drupal-cache",
    "x-wp-total",
    "x-wc-store-id",
]

# ─── 1. HTTP Security Headers ────────────────────────────────────────────────

async def check_http_headers(domain: str) -> list[dict]:
    findings: list[dict] = []
    url = f"https://{domain}"

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT_HTTP,
            follow_redirects=True,
            verify=False,          # SSL errors handled elsewhere
        ) as client:
            r = await client.get(url)
            headers_lower = {k.lower(): v for k, v in r.headers.items()}
    except Exception:
        # Try HTTP fallback
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_HTTP,
                follow_redirects=True,
            ) as client:
                r = await client.get(f"http://{domain}")
                headers_lower = {k.lower(): v for k, v in r.headers.items()}
        except Exception:
            return findings

    for header_name, (label, default_severity) in SECURITY_HEADERS.items():
        if header_name not in headers_lower:
            # Missing header
            severity = default_severity
            recommendation = _header_recommendation(header_name)
            findings.append({
                "category":       "En-têtes HTTP",
                "severity":       severity,
                "message":        f"En-tête {label} manquant",
                "recommendation": recommendation,
            })
        else:
            # Present — check for weak values
            val = headers_lower[header_name]
            weak = _check_header_value(header_name, val)
            if weak:
                findings.append({
                    "category":       "En-têtes HTTP",
                    "severity":       "MEDIUM",
                    "message":        f"{label} présent mais mal configuré : {weak}",
                    "recommendation": _header_recommendation(header_name),
                })

    # Check HSTS max-age if present
    hsts = headers_lower.get("strict-transport-security", "")
    if hsts:
        m = re.search(r"max-age=(\d+)", hsts)
        if m:
            age = int(m.group(1))
            if age < 15_552_000:   # < 180 days
                findings.append({
                    "category":       "En-têtes HTTP",
                    "severity":       "MEDIUM",
                    "message":        f"HSTS max-age trop court ({age}s < 180 jours)",
                    "recommendation": "Définir max-age=31536000 (1 an) avec includeSubDomains.",
                })

    return findings


def _header_recommendation(header_name: str) -> str:
    recs = {
        "strict-transport-security":
            "Ajouter : Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
        "content-security-policy":
            "Définir une CSP restrictive. Ex : default-src 'self'; script-src 'self'",
        "x-frame-options":
            "Ajouter : X-Frame-Options: DENY pour bloquer le clickjacking.",
        "x-content-type-options":
            "Ajouter : X-Content-Type-Options: nosniff",
        "referrer-policy":
            "Ajouter : Referrer-Policy: strict-origin-when-cross-origin",
        "permissions-policy":
            "Ajouter : Permissions-Policy: geolocation=(), camera=(), microphone=()",
        "x-xss-protection":
            "Ajouter : X-XSS-Protection: 1; mode=block (en complément d'une CSP).",
    }
    return recs.get(header_name, "Configurer cet en-tête de sécurité.")


def _check_header_value(header_name: str, value: str) -> Optional[str]:
    """Return a weakness description or None if value looks fine."""
    v = value.lower()
    if header_name == "content-security-policy":
        if "unsafe-inline" in v:
            return "unsafe-inline autorisé (XSS possible)"
        if "unsafe-eval" in v:
            return "unsafe-eval autorisé (XSS possible)"
        if "*" in v and "default-src" in v:
            return "wildcard (*) dans default-src"
    if header_name == "x-frame-options":
        if v not in ("deny", "sameorigin"):
            return f"valeur non standard : {value}"
    if header_name == "x-xss-protection":
        if v == "0":
            return "XSS Protection désactivée (valeur 0)"
    return None


# ─── 2. SPF / DKIM / DMARC ───────────────────────────────────────────────────

async def check_email_security(domain: str) -> list[dict]:
    findings: list[dict] = []

    if not _DNS_OK:
        return findings

    loop = asyncio.get_event_loop()

    # SPF
    spf = await loop.run_in_executor(None, _lookup_spf, domain)
    if spf is None:
        findings.append({
            "category":       "Sécurité Email",
            "severity":       "HIGH",
            "message":        "Aucun enregistrement SPF trouvé",
            "recommendation": "Créer un TXT record : v=spf1 include:_spf.yourmailprovider.com ~all",
        })
    else:
        weak = _analyze_spf(spf)
        if weak:
            findings.append({
                "category":       "Sécurité Email",
                "severity":       "MEDIUM",
                "message":        f"SPF présent mais faible : {weak}",
                "recommendation": "Remplacer ~all (softfail) par -all (reject) pour bloquer les expéditeurs non autorisés.",
            })

    # DMARC
    dmarc = await loop.run_in_executor(None, _lookup_dmarc, domain)
    if dmarc is None:
        findings.append({
            "category":       "Sécurité Email",
            "severity":       "HIGH",
            "message":        "Aucun enregistrement DMARC trouvé",
            "recommendation": "Créer un TXT record _dmarc.{domain} : v=DMARC1; p=reject; rua=mailto:dmarc@yourdomain.com",
        })
    else:
        weak = _analyze_dmarc(dmarc)
        if weak:
            findings.append({
                "category":       "Sécurité Email",
                "severity":       "MEDIUM",
                "message":        f"DMARC présent mais politique faible : {weak}",
                "recommendation": "Passer la politique DMARC à p=reject pour bloquer les emails frauduleux.",
            })

    # DKIM — probe common selectors
    dkim_found = await loop.run_in_executor(None, _probe_dkim, domain)
    if not dkim_found:
        findings.append({
            "category":       "Sécurité Email",
            "severity":       "MEDIUM",
            "message":        "Aucun enregistrement DKIM détecté (sélecteurs courants testés)",
            "recommendation": "Configurer DKIM via votre fournisseur de messagerie et publier la clé publique en DNS.",
        })

    return findings


def _lookup_txt(name: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=TIMEOUT_DNS)
        return ["".join(r.strings[j].decode() for j in range(len(r.strings))) for r in answers]
    except Exception:
        return []


def _lookup_spf(domain: str) -> Optional[str]:
    records = _lookup_txt(domain)
    for r in records:
        if r.startswith("v=spf1"):
            return r
    return None


def _analyze_spf(spf: str) -> Optional[str]:
    if spf.strip().endswith("+all"):
        return "+all autorisé (tout le monde peut envoyer en votre nom !)"
    if spf.strip().endswith("?all"):
        return "?all (neutral — aucune protection réelle)"
    if spf.strip().endswith("~all"):
        return "~all (softfail — les spams ne sont pas bloqués)"
    return None


def _lookup_dmarc(domain: str) -> Optional[str]:
    records = _lookup_txt(f"_dmarc.{domain}")
    for r in records:
        if r.startswith("v=DMARC1"):
            return r
    return None


def _analyze_dmarc(dmarc: str) -> Optional[str]:
    m = re.search(r"p=(\w+)", dmarc)
    if not m:
        return "pas de politique p= définie"
    policy = m.group(1).lower()
    if policy == "none":
        return "p=none (monitoring uniquement, aucune protection)"
    if policy == "quarantine":
        return "p=quarantine (recommandé : passer à p=reject)"
    return None


def _probe_dkim(domain: str) -> bool:
    for selector in DKIM_SELECTORS:
        records = _lookup_txt(f"{selector}._domainkey.{domain}")
        if any("v=DKIM1" in r or "k=rsa" in r for r in records):
            return True
    return False


# ─── 3. Technology Exposure ───────────────────────────────────────────────────

async def check_technology_exposure(domain: str) -> list[dict]:
    findings: list[dict] = []
    url = f"https://{domain}"

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT_HTTP,
            follow_redirects=True,
            verify=False,
        ) as client:
            r = await client.get(url)
            headers_lower = {k.lower(): v for k, v in r.headers.items()}
            body = r.text
    except Exception:
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_HTTP,
                follow_redirects=True,
            ) as client:
                r = await client.get(f"http://{domain}")
                headers_lower = {k.lower(): v for k, v in r.headers.items()}
                body = r.text
        except Exception:
            return findings

    # Check verbose headers
    for h in TECH_HEADERS:
        if h in headers_lower:
            val = headers_lower[h]
            if h == "server":
                if _is_verbose_server(val):
                    findings.append({
                        "category":       "Exposition Technologique",
                        "severity":       "MEDIUM",
                        "message":        f"En-tête Server expose la version : {val}",
                        "recommendation": "Masquer la version du serveur (ex: Apache, Nginx → 'Server: nginx' sans version).",
                    })
            elif h == "x-powered-by":
                findings.append({
                    "category":       "Exposition Technologique",
                    "severity":       "MEDIUM",
                    "message":        f"X-Powered-By expose la technologie : {val}",
                    "recommendation": "Supprimer l'en-tête X-Powered-By (Header unset X-Powered-By dans Apache/Nginx).",
                })
            else:
                findings.append({
                    "category":       "Exposition Technologique",
                    "severity":       "LOW",
                    "message":        f"En-tête {h} expose des informations : {val[:80]}",
                    "recommendation": "Supprimer ou masquer cet en-tête pour réduire l'exposition.",
                })

    # CMS/Framework detection via HTML
    cms = _detect_cms(body, headers_lower)
    if cms:
        findings.append({
            "category":       "Exposition Technologique",
            "severity":       "LOW",
            "message":        f"CMS/Framework détecté : {cms}",
            "recommendation": "Masquer les traces du CMS (retirer meta generator, supprimer /wp-login.php, etc.).",
        })

    # WordPress specific — check /wp-json/ exposed
    if "wordpress" in (cms or "").lower() or "/wp-content/" in body:
        wp_api = await _check_url_accessible(client if hasattr(client, 'get') else None,
                                             f"https://{domain}/wp-json/")
        if wp_api:
            findings.append({
                "category":       "Exposition Technologique",
                "severity":       "MEDIUM",
                "message":        "API REST WordPress (/wp-json/) accessible publiquement",
                "recommendation": "Restreindre l'accès à l'API REST WordPress si non nécessaire.",
            })

    return findings


def _is_verbose_server(val: str) -> bool:
    """Return True if Server header contains a version number."""
    return bool(re.search(r"[\d.]+", val)) and "/" in val


def _detect_cms(body: str, headers: dict) -> Optional[str]:
    signatures = {
        "WordPress":    ["/wp-content/", "/wp-includes/", 'name="generator" content="WordPress'],
        "Drupal":       ["/sites/default/files/", "Drupal.settings", "X-Generator: Drupal"],
        "Joomla":       ["/components/com_", "/templates/system/", "Joomla!"],
        "Shopify":      ["cdn.shopify.com", "Shopify.theme"],
        "Wix":          ["static.wixstatic.com", "wix-bolt"],
        "Squarespace":  ["squarespace.com", "squarespace-cdn"],
        "PrestaShop":   ["/modules/ps_", "prestashop"],
        "Magento":      ["Magento", "mage/cookies"],
        "Laravel":      ["laravel_session", "XSRF-TOKEN"],
        "Django":       ["csrfmiddlewaretoken", "django"],
        "Ruby on Rails":["_rails-", "rack.session"],
        "Next.js":      ["__NEXT_DATA__", "_next/static"],
        "Nuxt.js":      ["__nuxt", "_nuxt/"],
    }
    body_lower = body.lower()
    for cms, sigs in signatures.items():
        for sig in sigs:
            if sig.lower() in body_lower or sig.lower() in str(headers).lower():
                return cms
    return None


async def _check_url_accessible(client, url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5, verify=False) as c:
            r = await c.get(url)
            return r.status_code == 200
    except Exception:
        return False


# ─── 4. Domain Reputation (DNSBL) ────────────────────────────────────────────

async def check_domain_reputation(domain: str) -> list[dict]:
    findings: list[dict] = []

    if not _DNS_OK:
        return findings

    loop = asyncio.get_event_loop()

    # Resolve domain IP(s)
    ips = await loop.run_in_executor(None, _resolve_ips, domain)

    if not ips:
        return findings

    blacklisted_on: list[str] = []
    for ip in ips[:2]:  # Check up to 2 IPs
        hits = await loop.run_in_executor(None, _check_dnsbl, ip)
        blacklisted_on.extend(hits)

    if blacklisted_on:
        unique = list(dict.fromkeys(blacklisted_on))
        findings.append({
            "category":       "Réputation du Domaine",
            "severity":       "CRITICAL" if len(unique) >= 2 else "HIGH",
            "message":        f"Adresse IP listée sur {len(unique)} liste(s) noire(s) : {', '.join(unique[:3])}",
            "recommendation": "Demandez la suppression (delisting) sur chaque liste noire. Vérifiez si le serveur a été compromis.",
        })
    else:
        # Good finding (informational)
        findings.append({
            "category":       "Réputation du Domaine",
            "severity":       "INFO",
            "message":        f"Domaine non listé sur les listes noires principales ({len(DNSBL_ZONES)} vérifiées)",
            "recommendation": "Continuer à surveiller régulièrement la réputation du domaine.",
        })

    return findings


def _resolve_ips(domain: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(domain, None)
        ips = list({info[4][0] for info in infos
                    if not ipaddress.ip_address(info[4][0]).is_private})
        return ips
    except Exception:
        return []


def _check_dnsbl(ip: str) -> list[str]:
    """Return list of DNSBL zones where this IP is listed."""
    try:
        parts = ip.split(".")
        reversed_ip = ".".join(reversed(parts))
    except Exception:
        return []

    hits: list[str] = []
    for zone in DNSBL_ZONES:
        lookup = f"{reversed_ip}.{zone}"
        try:
            dns.resolver.resolve(lookup, "A", lifetime=TIMEOUT_DNS)
            hits.append(zone)
        except Exception:
            pass

    return hits


# ─── Main entry point ─────────────────────────────────────────────────────────

async def run_extra_checks(domain: str) -> list[dict]:
    """
    Run all 4 extra check categories concurrently.
    Returns a flat list of finding dicts merged with existing findings.
    """
    results = await asyncio.gather(
        check_http_headers(domain),
        check_email_security(domain),
        check_technology_exposure(domain),
        check_domain_reputation(domain),
        return_exceptions=True,
    )

    all_findings: list[dict] = []
    for result in results:
        if isinstance(result, list):
            all_findings.extend(result)

    return all_findings
