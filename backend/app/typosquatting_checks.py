"""
CyberHealth Scanner — Typosquatting Detection
=============================================
Détecte les domaines sosies enregistrés par des tiers :
variantes de TLD, fautes de frappe, homoglyphes ASCII, transpositions.

Méthode : résolution DNS (gethostbyname) — un domaine qui répond
          est considéré enregistré et actif.

Zéro API externe — lecture seule.
Plans : Starter / Pro / Dev.
"""

from __future__ import annotations

import asyncio
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from app.scanner import BaseAuditor, Finding, SCAN_TIMEOUT_SEC


# ── Constantes ────────────────────────────────────────────────────────────────

MAX_VARIANTS   = 50   # limite de performance
MAX_WORKERS    = 20   # parallélisme DNS
DNS_TIMEOUT    = 2.0  # secondes par lookup individuel

# TLDs à tester en priorité (remplacent le TLD actuel)
COMMON_TLDS = [
    ".com", ".fr", ".net", ".org", ".io", ".co", ".eu",
    ".biz", ".info", ".uk", ".de", ".es", ".be",
]

# Homoglyphes ASCII uniquement (pas d'IDN/unicode → compatible gethostbyname)
HOMOGLYPHS: dict[str, list[str]] = {
    "a": ["4"],
    "e": ["3"],
    "i": ["1", "l"],
    "l": ["1", "i"],
    "o": ["0"],
    "s": ["5"],
    "t": ["7"],
}

# Touches voisines sur un clavier AZERTY/QWERTY
KEYBOARD_NEIGHBORS: dict[str, str] = {
    "a": "qzsw",  "b": "vghn",  "c": "xdfv",  "d": "serfcx",
    "e": "wrsxd", "f": "drtgvc","g": "ftyhbv", "h": "gyujnb",
    "i": "uojkp", "j": "huikm", "k": "jiol",   "l": "kop",
    "m": "njk",   "n": "bhjm",  "o": "iklp",   "p": "ol",
    "q": "wa",    "r": "etdf",  "s": "awedxz", "t": "ryfg",
    "u": "yijho", "v": "cfgb",  "w": "qeasz",  "x": "zsdc",
    "y": "tughi", "z": "asx",
}


# ── Dataclass résultat ────────────────────────────────────────────────────────

@dataclass
class TyposquatHit:
    domain:       str
    variant_type: str   # "tld" | "missing" | "double" | "transposition" | "homoglyph" | "keyboard"
    ip:           str

    def to_dict(self) -> dict:
        return {
            "domain":       self.domain,
            "variant_type": self.variant_type,
            "ip":           self.ip,
        }


# ── Génération de variantes ───────────────────────────────────────────────────

def _generate_variants(domain: str) -> list[tuple[str, str]]:
    """
    Génère jusqu'à MAX_VARIANTS variantes typosquat du domaine.
    Retourne une liste de (domaine_variante, type_de_variante).
    """
    if "." not in domain:
        return []

    last_dot = domain.rfind(".")
    name = domain[:last_dot]
    tld  = domain[last_dot:]   # inclut le point

    if not name or len(name) < 2:
        return []

    seen: set[str] = {domain}
    result: list[tuple[str, str]] = []

    def add(variant: str, vtype: str) -> None:
        # Filtre : alphanumérique + tirets uniquement (compatible DNS)
        clean = variant.replace(".", "").replace("-", "")
        if variant not in seen and clean.isalnum() and len(clean) >= 3:
            seen.add(variant)
            result.append((variant, vtype))

    # 1. Variations de TLD (remplacement du TLD actuel)
    for alt_tld in COMMON_TLDS:
        if alt_tld != tld:
            add(f"{name}{alt_tld}", "tld")

    # 2. Lettre manquante (chaque lettre retirée une fois)
    for i in range(len(name)):
        v = name[:i] + name[i + 1:]
        if len(v) >= 3:
            add(f"{v}{tld}", "missing")

    # 3. Lettre doublée (chaque lettre répétée une fois)
    for i in range(len(name)):
        v = name[:i] + name[i] + name[i:]
        add(f"{v}{tld}", "double")

    # 4. Transposition de deux lettres adjacentes
    for i in range(len(name) - 1):
        if name[i] != name[i + 1]:  # évite les no-ops
            v = name[:i] + name[i + 1] + name[i] + name[i + 2:]
            add(f"{v}{tld}", "transposition")

    # 5. Homoglyphes ASCII (0→o, 1→i, 3→e…)
    for i, char in enumerate(name.lower()):
        if char in HOMOGLYPHS:
            for repl in HOMOGLYPHS[char]:
                v = name[:i] + repl + name[i + 1:]
                add(f"{v}{tld}", "homoglyph")

    # 6. Touches voisines (limitées aux 6 premiers chars pour la perf)
    for i in range(min(len(name), 6)):
        char = name[i].lower()
        if char in KEYBOARD_NEIGHBORS:
            for neighbor in KEYBOARD_NEIGHBORS[char][:2]:
                v = name[:i] + neighbor + name[i + 1:]
                add(f"{v}{tld}", "keyboard")

    return result[:MAX_VARIANTS]


# ── Auditeur principal ────────────────────────────────────────────────────────

class TyposquattingAuditor(BaseAuditor):
    """
    Détecte les domaines typosquat enregistrés via résolution DNS.
    Disponible sur les plans Starter, Pro et Dev.
    """

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._check_typosquatting)
        return self._findings

    # ── Logique principale ────────────────────────────────────────────────────

    def _check_typosquatting(self) -> None:
        root   = self._root_domain()
        variants = _generate_variants(root)
        hits   = self._check_variants_parallel(variants)

        self._details = {
            "status":    "squatted" if hits else "clean",
            "checked":   len(variants),
            "hit_count": len(hits),
            "hits":      [h.to_dict() for h in hits],
        }

        if not hits:
            return

        count = len(hits)

        if count >= 5:
            severity, penalty = "CRITICAL", 25
        elif count >= 3:
            severity, penalty = "HIGH", 15
        else:
            severity, penalty = "MEDIUM", 8

        fr_s  = "s" if count > 1 else ""
        en_es = "es" if count > 1 else ""
        examples = ", ".join(h.domain for h in hits[:3])
        if count > 3:
            examples += "…"

        self._findings.append(Finding(
            category = "Typosquatting",
            severity = severity,
            title    = self._t(
                f"{count} domaine{fr_s} sosie{fr_s} enregistré{fr_s}",
                f"{count} lookalike domain{en_es} registered",
            ),
            technical_detail = (
                f"Domaines actifs détectés : {examples}"
                if self.lang == "fr" else
                f"Active lookalike domains: {examples}"
            ),
            plain_explanation = self._t(
                f"Des tiers ont enregistré {count} domaine{fr_s} ressemblant au vôtre "
                f"({examples}). Ces domaines peuvent être utilisés pour du phishing "
                "ciblant vos clients, de l'usurpation de marque ou des attaques "
                "man-in-the-middle.",
                f"Third parties have registered {count} domain{en_es} similar to yours "
                f"({examples}). These can be used for phishing targeting your customers, "
                "brand impersonation, or man-in-the-middle attacks.",
            ),
            penalty       = penalty,
            recommendation = self._t(
                "Enregistrez les TLDs principaux de votre domaine (.com, .fr, .org) "
                "pour bloquer l'usurpation. Signalez les domaines actifs à votre "
                "registrar. Activez DMARC (p=reject) pour protéger votre marque contre "
                "le phishing par email.",
                "Register the main TLDs of your domain (.com, .fr, .org) to block "
                "impersonation. Report active domains to your registrar. Enable DMARC "
                "(p=reject) to protect your brand against email phishing.",
            ),
        ))

    # ── Résolution DNS parallèle ──────────────────────────────────────────────

    def _check_variants_parallel(
        self, variants: list[tuple[str, str]]
    ) -> list[TyposquatHit]:
        """Lance les lookups DNS en parallèle avec un pool de threads."""
        if not variants:
            return []

        hits: list[TyposquatHit] = []
        timeout = max(SCAN_TIMEOUT_SEC - 1, 3)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._dns_lookup, domain, vtype): (domain, vtype)
                for domain, vtype in variants
            }
            try:
                for future in as_completed(futures, timeout=timeout):
                    result = future.result()
                    if result is not None:
                        hits.append(result)
            except Exception:
                pass  # timeout global — on travaille avec ce qu'on a

        return sorted(hits, key=lambda h: h.domain)

    def _dns_lookup(self, domain: str, vtype: str) -> TyposquatHit | None:
        """Tentative de résolution DNS. Retourne un TyposquatHit si le domaine répond."""
        old_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(DNS_TIMEOUT)
            ip = socket.gethostbyname(domain)
            return TyposquatHit(domain=domain, variant_type=vtype, ip=ip)
        except (socket.gaierror, OSError):
            return None
        except Exception:
            return None
        finally:
            socket.setdefaulttimeout(old_timeout)

    # ── Utilitaire ────────────────────────────────────────────────────────────

    def _root_domain(self) -> str:
        """Extrait le domaine racine (sub.example.com → example.com)."""
        parts = self.domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else self.domain
