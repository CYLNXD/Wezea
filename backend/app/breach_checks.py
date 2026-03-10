"""
CyberHealth Scanner — Breach Detection via HaveIBeenPwned
=========================================================
Vérifie si le domaine scanné apparaît dans des fuites de données connues.

API utilisée (clé optionnelle) :
  GET https://haveibeenpwned.com/api/v3/breacheddomain/{domain}
  → Retourne {BreachName: [email1, ...], ...} ou 404 si domaine propre
  → Requiert une clé API HIBP (hibp-api-key header) — ≈ 3,50 $/mois

Variable d'environnement : HIBP_API_KEY (optionnelle)
  - Si absente → status "no_api_key" (aucune pénalité)
  - Si présente → check complet

Lecture seule — aucune donnée envoyée, uniquement le nom de domaine racine.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import urllib.error
import urllib.request

from app.scanner import BaseAuditor, Finding, SCAN_TIMEOUT_SEC


HIBP_DOMAIN_URL = "https://haveibeenpwned.com/api/v3/breacheddomain/{domain}"


class BreachAuditor(BaseAuditor):
    """
    Détecte les fuites de données associées au domaine via HaveIBeenPwned.
    Disponible sur les plans Starter, Pro et Dev.
    """

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._check_breaches)
        return self._findings

    # ── Utilitaire ────────────────────────────────────────────────────────────

    def _root_domain(self) -> str:
        """Extrait le domaine racine (ex: sub.example.com → example.com)."""
        parts = self.domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else self.domain

    # ── Check principal ───────────────────────────────────────────────────────

    def _check_breaches(self) -> None:
        api_key = os.environ.get("HIBP_API_KEY", "").strip()

        # Clé absente → on signale mais sans pénalité
        if not api_key:
            self._details = {"status": "no_api_key"}
            return

        root = self._root_domain()
        url = HIBP_DOMAIN_URL.format(domain=root)

        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "CyberHealth-Scanner/1.0",
                    "hibp-api-key": api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=SCAN_TIMEOUT_SEC, context=ctx) as resp:
                data: dict = json.loads(resp.read(1_048_576))  # 1 MB max

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Domaine propre — aucune fuite connue
                self._details = {"status": "clean", "breach_count": 0, "breach_names": []}
            elif e.code == 401:
                # Clé invalide ou expirée
                self._details = {"status": "no_api_key"}
            # Toute autre erreur HTTP → silencieux (ne pas pénaliser)
            return

        except Exception:
            # Timeout, réseau indisponible, etc. → silencieux
            return

        if not data:
            self._details = {"status": "clean", "breach_count": 0, "breach_names": []}
            return

        # ── Analyse des résultats ─────────────────────────────────────────────

        breach_names = list(data.keys())
        count = len(breach_names)

        # Sévérité selon le nombre de fuites distinctes
        if count >= 3:
            severity, penalty = "CRITICAL", 30
        else:
            severity, penalty = "HIGH", 20

        self._details = {
            "status": "breached",
            "breach_count": count,
            "breach_names": breach_names[:10],  # Max 10 noms stockés
        }

        # Pluriel
        fr_s = "s" if count > 1 else ""
        en_es = "es" if count > 1 else ""

        self._findings.append(Finding(
            category="Fuites de données",
            severity=severity,
            title=self._t(
                f"Domaine trouvé dans {count} fuite{fr_s} de données",
                f"Domain found in {count} data breach{en_es}",
            ),
            technical_detail=(
                f"Sources HIBP : {', '.join(breach_names[:5])}"
                f"{'…' if count > 5 else ''}"
            ),
            plain_explanation=self._t(
                f"Des identifiants liés à votre domaine ont été retrouvés dans {count} "
                f"base{fr_s} de données piratée{fr_s}. Ces credentials peuvent être utilisés "
                "pour des attaques de credential stuffing ou du phishing ciblé contre "
                "vos collaborateurs.",
                f"Credentials linked to your domain were found in {count} breached "
                f"database{en_es}. These can be used for credential stuffing or targeted "
                "phishing attacks against your team.",
            ),
            penalty=penalty,
            recommendation=self._t(
                "Demandez à vos équipes de changer leurs mots de passe sur les services "
                "concernés. Activez l'authentification à deux facteurs (2FA) sur tous les "
                "comptes professionnels. Vérifiez les accès suspects dans vos logs.",
                "Ask your team to change their passwords on affected services. Enable "
                "two-factor authentication (2FA) on all business accounts. Review your "
                "access logs for suspicious activity.",
            ),
        ))
