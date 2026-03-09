"""
ct_monitor.py — Certificate Transparency Log Monitor

Surveille les logs CT via l'API gratuite crt.sh pour détecter :
- Certificats émis récemment (7j / 30j) pour le domaine et ses sous-domaines
- Certificats wildcard (*.domain.com) potentiellement suspects
- Émetteurs inhabituels (CA inconnue ou inattendue)
- Volume élevé de certificats (signal de reconnaissance active)

Plan : Starter, Pro, Dev (premium)
API : https://crt.sh/?q=%.{domain}&output=json (gratuit, pas d'auth)
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from app.scanner import BaseAuditor, Finding, SCAN_TIMEOUT_SEC

# ── Constantes ────────────────────────────────────────────────────────────────

CT_BASE_URL = "https://crt.sh/?q=%25.{domain}&output=json"
CT_TIMEOUT  = min(8, SCAN_TIMEOUT_SEC - 1)
MAX_CERTS   = 300       # plafond de traitement (crt.sh peut retourner des milliers)

RECENT_URGENT_DAYS = 7
RECENT_WARN_DAYS   = 30

# Mots-clés caractéristiques des CA reconnues (minuscules)
_KNOWN_CA_KEYWORDS = {
    "let's encrypt", "letsencrypt", "digicert", "comodo", "sectigo",
    "globalsign", "godaddy", "amazon", "google trust services",
    "entrust", "certum", "swisssign", "isrg", "microsoft", "ssl.com",
    "identrust", "actalis", "harica", "buypass", "trustcor", "zerossl",
    "e1", "r3", "r10", "r11",  # Let's Encrypt intermediaires
}


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class CertRecord:
    common_name: str
    name_value:  str
    issuer:      str
    logged_at:   str   # "YYYY-MM-DD"
    not_before:  str   # "YYYY-MM-DD"
    not_after:   str   # "YYYY-MM-DD"

    def to_dict(self) -> dict:
        return {
            "common_name": self.common_name,
            "name_value":  self.name_value,
            "issuer":      self.issuer,
            "logged_at":   self.logged_at,
            "not_before":  self.not_before,
            "not_after":   self.not_after,
        }


# ── Auditeur principal ────────────────────────────────────────────────────────

class CertTransparencyAuditor(BaseAuditor):
    """Analyse les logs Certificate Transparency via crt.sh."""

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._check_ct_logs),
                timeout=CT_TIMEOUT,
            )
        except (asyncio.TimeoutError, Exception):
            pass
        return self._findings

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def _root_domain(self) -> str:
        parts = self.domain.split(".")
        if len(parts) > 2:
            return ".".join(parts[-2:])
        return self.domain

    @staticmethod
    def _parse_issuer(issuer_name: str) -> str:
        """Extrait un nom court depuis le DN de l'émetteur."""
        for part in issuer_name.split(","):
            part = part.strip()
            if part.startswith("O="):
                return part[2:].strip().strip('"')
            if part.startswith("CN="):
                return part[3:].strip().strip('"')
        return issuer_name[:60] if issuer_name else ""

    @staticmethod
    def _parse_date(date_str: str) -> datetime | None:
        """Parse 'YYYY-MM-DDTHH:MM:SS' ou 'YYYY-MM-DD HH:MM:SS' → datetime UTC."""
        if not date_str:
            return None
        try:
            clean = date_str.replace("T", " ").split(".")[0]
            return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return None

    @staticmethod
    def _is_known_ca(issuer_short: str) -> bool:
        low = issuer_short.lower()
        return any(kw in low for kw in _KNOWN_CA_KEYWORDS)

    def _fetch_certs(self, root: str) -> list[dict]:
        """Interroge crt.sh et retourne la liste brute des certificats."""
        url = CT_BASE_URL.format(domain=root)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CyberHealth-Scanner/1.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=CT_TIMEOUT) as resp:
                raw = resp.read()
            return json.loads(raw) or []
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            return []

    # ── Logique principale ────────────────────────────────────────────────────

    def _check_ct_logs(self) -> None:
        root = self._root_domain()
        raw_certs = self._fetch_certs(root)

        if not raw_certs:
            self._details = {
                "status":      "no_data",
                "total_found": 0,
                "recent_7days":  0,
                "recent_30days": 0,
                "wildcard_count": 0,
                "issuers":     [],
                "recent_certs":  [],
                "wildcard_certs": [],
            }
            return

        now = datetime.now(timezone.utc)
        recent_7:  list[CertRecord] = []
        recent_30: list[CertRecord] = []
        wildcards: list[CertRecord] = []
        issuers_set: set[str] = set()
        unknown_issuer_recent: list[CertRecord] = []

        for raw in raw_certs[:MAX_CERTS]:
            issuer_dn    = raw.get("issuer_name", "") or ""
            common_name  = (raw.get("common_name", "") or "").strip()
            name_value   = (raw.get("name_value",  "") or "").strip()
            logged_str   = raw.get("logged_at",  "") or ""
            not_bef_str  = raw.get("not_before", "") or ""
            not_aft_str  = raw.get("not_after",  "") or ""

            issuer_short = self._parse_issuer(issuer_dn)
            if issuer_short:
                issuers_set.add(issuer_short)

            logged_at = self._parse_date(logged_str)

            record = CertRecord(
                common_name = common_name,
                name_value  = name_value,
                issuer      = issuer_short or issuer_dn[:60],
                logged_at   = logged_str[:10] if logged_str else "",
                not_before  = not_bef_str[:10] if not_bef_str else "",
                not_after   = not_aft_str[:10] if not_aft_str else "",
            )

            # Recency
            if logged_at:
                age_days = (now - logged_at).days
                if age_days <= RECENT_URGENT_DAYS:
                    recent_7.append(record)
                    if not self._is_known_ca(record.issuer):
                        unknown_issuer_recent.append(record)
                if age_days <= RECENT_WARN_DAYS:
                    recent_30.append(record)

            # Wildcards
            if "*." in common_name or "*." in name_value:
                wildcards.append(record)

        # ── Stocker les détails ────────────────────────────────────────────────
        self._details = {
            "status":         "certs_found",
            "total_found":    len(raw_certs),
            "recent_7days":   len(recent_7),
            "recent_30days":  len(recent_30),
            "wildcard_count": len(wildcards),
            "issuers":        sorted(issuers_set),
            "recent_certs":   [r.to_dict() for r in recent_7[:10]],
            "wildcard_certs": [r.to_dict() for r in wildcards[:5]],
        }

        # ── Générer les findings ───────────────────────────────────────────────

        # 1. Certificats récents (≤ 7j) d'un émetteur inhabituel → MEDIUM
        if unknown_issuer_recent:
            examples = ", ".join(r.common_name for r in unknown_issuer_recent[:3])
            issuers_ex = ", ".join({r.issuer for r in unknown_issuer_recent})
            self._findings.append(Finding(
                category         = "Certificate Transparency",
                severity         = "MEDIUM",
                title            = self._t(
                    f"{len(unknown_issuer_recent)} certificat(s) récent(s) émis par un CA inattendu",
                    f"{len(unknown_issuer_recent)} recent certificate(s) issued by an unexpected CA",
                ),
                technical_detail = self._t(
                    f"Certificats émis dans les 7 derniers jours pour {root} par : {issuers_ex}. "
                    f"Domaines concernés : {examples}",
                    f"Certificates issued within the last 7 days for {root} by: {issuers_ex}. "
                    f"Affected names: {examples}",
                ),
                plain_explanation = self._t(
                    "Un ou plusieurs certificats TLS récents ont été émis par une autorité de certification "
                    "non reconnue. Cela peut indiquer une prise de contrôle de sous-domaine ou une "
                    "émission non autorisée.",
                    "One or more recent TLS certificates were issued by an unrecognized CA. "
                    "This may indicate a subdomain takeover or unauthorized certificate issuance.",
                ),
                penalty          = 8,
                recommendation   = self._t(
                    "Vérifiez l'origine de ces certificats. Ajoutez des enregistrements CAA DNS "
                    "(`CAA 0 issue \"letsencrypt.org\"`) pour restreindre les CA autorisées.",
                    "Verify the origin of these certificates. Add CAA DNS records "
                    "(`CAA 0 issue \"letsencrypt.org\"`) to restrict which CAs can issue certificates.",
                ),
            ))

        # 2. Wildcard certs récents (≤ 30j) d'un émetteur inhabituel → HIGH
        unexpected_wildcards = [
            r for r in wildcards
            if not self._is_known_ca(r.issuer)
            and r.logged_at >= (now - timedelta(days=RECENT_WARN_DAYS)).strftime("%Y-%m-%d")
        ]
        if unexpected_wildcards:
            ex = unexpected_wildcards[0]
            self._findings.append(Finding(
                category         = "Certificate Transparency",
                severity         = "HIGH",
                title            = self._t(
                    "Certificat wildcard émis par un CA non reconnu",
                    "Wildcard certificate issued by an unrecognized CA",
                ),
                technical_detail = self._t(
                    f"Certificat wildcard `{ex.common_name}` émis par `{ex.issuer}` "
                    f"le {ex.logged_at}.",
                    f"Wildcard certificate `{ex.common_name}` issued by `{ex.issuer}` "
                    f"on {ex.logged_at}.",
                ),
                plain_explanation = self._t(
                    "Un certificat wildcard couvre tous les sous-domaines (*.domain.com). "
                    "Émis par un CA inconnu, il constitue un signal fort de compromission potentielle.",
                    "A wildcard certificate covers all subdomains (*.domain.com). "
                    "Issued by an unknown CA, it is a strong indicator of potential compromise.",
                ),
                penalty          = 12,
                recommendation   = self._t(
                    "Révoquez le certificat si vous n'en êtes pas à l'origine. "
                    "Utilisez les enregistrements CAA pour interdire l'émission de wildcards : "
                    "`CAA 0 issuewild \";\"` (zéro CA autorisée pour les wildcards).",
                    "Revoke the certificate if you didn't authorize it. "
                    "Use CAA records to prohibit wildcard issuance: "
                    "`CAA 0 issuewild \";\"` (no CA allowed for wildcards).",
                ),
            ))

        # 3. Volume très élevé de certificats connus → INFO (signal de recon)
        elif len(raw_certs) > 100 and not self._findings:
            self._findings.append(Finding(
                category         = "Certificate Transparency",
                severity         = "INFO",
                title            = self._t(
                    f"Volume élevé de certificats CT ({len(raw_certs)} enregistrements)",
                    f"High CT certificate volume ({len(raw_certs)} records)",
                ),
                technical_detail = self._t(
                    f"{len(raw_certs)} certificats trouvés dans les logs CT pour {root}. "
                    f"Émetteurs : {', '.join(sorted(issuers_set)[:5])}.",
                    f"{len(raw_certs)} certificates found in CT logs for {root}. "
                    f"Issuers: {', '.join(sorted(issuers_set)[:5])}.",
                ),
                plain_explanation = self._t(
                    "Un nombre élevé de certificats peut indiquer une infrastructure active "
                    "avec de nombreux sous-domaines, ou une reconnaissance passive de votre domaine.",
                    "A high number of certificates may indicate active infrastructure with many "
                    "subdomains, or passive reconnaissance of your domain.",
                ),
                penalty          = 0,
                recommendation   = self._t(
                    "Auditez régulièrement les certificats émis via https://crt.sh/?q=%.{root} "
                    "et activez la surveillance des logs CT.",
                    "Regularly audit issued certificates via https://crt.sh/?q=%.{root} "
                    "and enable CT log monitoring.",
                ).format(root=root),
            ))

        # 4. Certificats récents (≤ 7j) de CA connues → INFO (pour information)
        elif recent_7 and not self._findings:
            examples = ", ".join({r.issuer for r in recent_7[:3]})
            self._findings.append(Finding(
                category         = "Certificate Transparency",
                severity         = "INFO",
                title            = self._t(
                    f"{len(recent_7)} certificat(s) émis dans les 7 derniers jours",
                    f"{len(recent_7)} certificate(s) issued in the last 7 days",
                ),
                technical_detail = self._t(
                    f"Certificats récents pour {root} par : {examples}.",
                    f"Recent certificates for {root} by: {examples}.",
                ),
                plain_explanation = self._t(
                    "Des certificats ont été émis récemment pour votre domaine par des CA reconnues. "
                    "C'est normal si vous avez renouvelé ou déployé des certificats récemment.",
                    "Certificates were recently issued for your domain by recognized CAs. "
                    "This is normal if you recently renewed or deployed certificates.",
                ),
                penalty          = 0,
                recommendation   = self._t(
                    "Vérifiez que ces certificats correspondent à vos renouvellements prévus. "
                    "Activez les alertes CT (ex : Facebook CT Monitor, crt.sh RSS) pour être "
                    "notifié en temps réel.",
                    "Verify these certificates match your planned renewals. "
                    "Enable CT alerts (e.g., Facebook CT Monitor, crt.sh RSS) "
                    "to be notified in real time.",
                ),
            ))
