"""
CyberHealth Scanner — Moteur d'Audit de Sécurité
=================================================
Auteur  : CyberHealth Team
Version : 1.0.0 (MVP)
Licence : Propriétaire

Architecture :
    AuditManager          → Orchestre les scans en parallèle (asyncio.gather)
    DNSAuditor            → Analyse SPF, DMARC (dnspython)
    SSLAuditor            → Analyse certificat, version TLS (ssl + socket)
    PortAuditor           → Analyse des ports critiques (socket)
    ScoreEngine           → Calcul du SecurityScore & niveau de risque
    ReportBuilder         → Construction du rapport JSON + estimation de pertes

Principes :
    ✓ Scan 100 % passif (lecture seule, pas de brute-force)
    ✓ Modulaire  : ajouter un nouvel auditeur = sous-classer BaseAuditor
    ✓ Thread-safe : chaque auditeur est indépendant, les findings sont agrégés en fin
"""

from __future__ import annotations

import asyncio
import os
import socket
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import dns.exception
import dns.resolver


# ─────────────────────────────────────────────────────────────────────────────
# Configuration — chargée depuis les variables d'environnement
# ─────────────────────────────────────────────────────────────────────────────

SCAN_TIMEOUT_SEC: int = int(os.getenv("SCAN_TIMEOUT_SEC", "5"))
DNS_LIFETIME_SEC: float = float(os.getenv("DNS_LIFETIME_SEC", "8.0"))
SSL_PORT: int = int(os.getenv("SSL_PORT", "443"))

# Ports à scanner avec (service, catégorie_pénalité, niveau_de_risque)
MONITORED_PORTS: dict[int, tuple[str, str | None, str]] = {
    21:    ("FTP",           "ftp_telnet",      "HIGH"),
    22:    ("SSH",           None,              "INFO"),
    23:    ("Telnet",        "ftp_telnet",      "HIGH"),
    25:    ("SMTP",          None,              "INFO"),
    80:    ("HTTP",          None,              "INFO"),
    443:   ("HTTPS",         None,              "INFO"),
    445:   ("SMB",           "rdp_smb",         "CRITICAL"),
    2375:  ("Docker-API",    "exposed_service", "CRITICAL"),
    3306:  ("MySQL",         "database",        "CRITICAL"),
    3389:  ("RDP",           "rdp_smb",         "CRITICAL"),
    5432:  ("PostgreSQL",    "database",        "CRITICAL"),
    6379:  ("Redis",         "exposed_service", "CRITICAL"),
    8080:  ("HTTP-Alt",      None,              "INFO"),
    8443:  ("HTTPS-Alt",     None,              "INFO"),
    9200:  ("Elasticsearch", "exposed_service", "CRITICAL"),
    27017: ("MongoDB",       "exposed_service", "CRITICAL"),
}

# Table des pénalités — modifiable sans toucher à la logique métier
PENALTY_TABLE: dict[str, int] = {
    "spf_missing":              15,
    "spf_misconfigured":        15,
    "dmarc_missing":            20,
    "ssl_invalid":              30,
    "ssl_unreachable":          30,
    "tls_old_version":          10,
    "rdp_smb":                  40,
    "ftp_telnet":               20,
    "database":                 25,
    "exposed_service":          30,
}


# ─────────────────────────────────────────────────────────────────────────────
# Modèles de données
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Finding:
    """
    Représente une vulnérabilité ou un constat de sécurité.
    Chaque finding contient : détail technique + explication vulgarisée PME.
    """
    category:         str   # Ex : "DNS & Mail", "SSL / HTTPS", "Exposition des Ports"
    severity:         str   # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO"
    title:            str   # Titre court du constat
    technical_detail: str   # Détail technique pour un expert
    plain_explanation: str  # Explication compréhensible par un patron de PME
    penalty:          int   # Points déduits du score (0 si INFO)
    recommendation:   str   # Action corrective concrète

    def to_dict(self) -> dict:
        return {
            "category":          self.category,
            "severity":          self.severity,
            "title":             self.title,
            "technical_detail":  self.technical_detail,
            "plain_explanation": self.plain_explanation,
            "penalty":           self.penalty,
            "recommendation":    self.recommendation,
        }


@dataclass
class ScanResult:
    """Rapport complet renvoyé par l'API."""
    domain:         str
    scanned_at:     str
    security_score: int
    risk_level:     str
    findings:       list[Finding]         = field(default_factory=list)
    dns_details:    dict[str, Any]        = field(default_factory=dict)
    ssl_details:    dict[str, Any]        = field(default_factory=dict)
    port_details:   dict[int, dict]       = field(default_factory=dict)
    recommendations: list[str]            = field(default_factory=list)
    scan_duration_ms: int                 = 0
    # Champs premium (Starter / Pro / Dev)
    subdomain_details: dict[str, Any]     = field(default_factory=dict)
    vuln_details:      dict[str, Any]     = field(default_factory=dict)
    breach_details:    dict[str, Any]     = field(default_factory=dict)
    typosquat_details: dict[str, Any]    = field(default_factory=dict)
    ct_details:        dict[str, Any]    = field(default_factory=dict)
    # Conformité réglementaire — tous plans
    compliance:        dict[str, Any]     = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "domain":             self.domain,
            "scanned_at":         self.scanned_at,
            "security_score":     self.security_score,
            "risk_level":         self.risk_level,
            "findings":           [f.to_dict() for f in self.findings],
            "dns_details":        self.dns_details,
            "ssl_details":        self.ssl_details,
            "port_details":       {str(k): v for k, v in self.port_details.items()},
            "recommendations":    self.recommendations,
            "scan_duration_ms":   self.scan_duration_ms,
            "subdomain_details":  self.subdomain_details,
            "vuln_details":       self.vuln_details,
            "breach_details":     self.breach_details,
            "typosquat_details":  self.typosquat_details,
            "ct_details":         self.ct_details,
            "compliance":         self.compliance,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Interface BaseAuditor — étend l'outil facilement
# ─────────────────────────────────────────────────────────────────────────────

class BaseAuditor(ABC):
    """
    Classe abstraite. Pour ajouter un nouveau module de scan :
      1. Sous-classer BaseAuditor
      2. Implémenter `audit() -> list[Finding]` et `get_details() -> dict`
      3. Injecter dans AuditManager.run_all_scans()
    """

    def __init__(self, domain: str, lang: str = "fr") -> None:
        self.domain = domain
        self.lang = lang
        self._findings: list[Finding] = []
        self._details: dict[str, Any] = {}

    def _t(self, fr: str, en: str) -> str:
        """Return the string in the correct language."""
        return en if getattr(self, 'lang', 'fr') == "en" else fr

    @abstractmethod
    async def audit(self) -> list[Finding]:
        """Lance le scan et retourne la liste des findings."""

    def get_details(self) -> dict[str, Any]:
        """Retourne les détails bruts du scan pour le JSON."""
        return self._details


# ─────────────────────────────────────────────────────────────────────────────
# Auditeur DNS (SPF + DMARC)
# ─────────────────────────────────────────────────────────────────────────────

class DNSAuditor(BaseAuditor):
    """Analyse les enregistrements SPF et DMARC du domaine."""

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._check_spf)
        await loop.run_in_executor(None, self._check_dmarc)
        await loop.run_in_executor(None, self._check_dnssec)
        await loop.run_in_executor(None, self._check_caa)
        return self._findings

    # ── SPF ──────────────────────────────────────────────────────────────────

    def _check_spf(self) -> None:
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = DNS_LIFETIME_SEC
            answers = resolver.resolve(self.domain, "TXT")
            spf_records = [
                r.to_text().strip('"')
                for r in answers
                if "v=spf1" in r.to_text()
            ]

            if not spf_records:
                self._findings.append(Finding(
                    category="DNS & Mail",
                    severity="HIGH",
                    title=self._t(
                        "SPF manquant",
                        "SPF record missing"
                    ),
                    technical_detail=self._t(
                        f"Aucun enregistrement TXT contenant 'v=spf1' trouvé pour {self.domain}.",
                        f"No TXT record containing 'v=spf1' found for {self.domain}."
                    ),
                    plain_explanation=self._t(
                        "Sans SPF, n'importe qui peut envoyer des emails en se faisant passer pour votre entreprise. "
                        "Vos clients risquent de recevoir des arnaques semblant provenir de votre adresse officielle.",
                        "Without SPF, anyone can send emails impersonating your company. "
                        "Your customers may receive scam emails that appear to come from your official address."
                    ),
                    penalty=PENALTY_TABLE["spf_missing"],
                    recommendation=self._t(
                        "Ajoutez ce TXT sur votre DNS : \"v=spf1 include:_spf.google.com ~all\" "
                        "(adaptez selon votre hébergeur mail).",
                        "Add this TXT record to your DNS: \"v=spf1 include:_spf.google.com ~all\" "
                        "(adjust based on your email provider)."
                    ),
                ))
                self._details["spf"] = {"status": "missing", "records": []}
                return

            spf = spf_records[0]
            # SPF en +all = tout le monde est autorisé → dangereux
            if "+all" in spf:
                self._findings.append(Finding(
                    category="DNS & Mail",
                    severity="HIGH",
                    title=self._t(
                        "SPF mal configuré (+all permissif)",
                        "SPF misconfigured (+all permissive)"
                    ),
                    technical_detail=self._t(
                        f"Enregistrement SPF trouvé : '{spf}'. "
                        "Le qualificateur '+all' autorise n'importe quel serveur à envoyer.",
                        f"SPF record found: '{spf}'. "
                        "The '+all' qualifier allows any server to send on your behalf."
                    ),
                    plain_explanation=self._t(
                        "Votre protection anti-usurpation par email est configurée comme une porte ouverte : "
                        "tout le monde peut envoyer des emails en votre nom malgré la présence de SPF.",
                        "Your email spoofing protection is configured like an open door: "
                        "anyone can send emails in your name despite SPF being present."
                    ),
                    penalty=PENALTY_TABLE["spf_misconfigured"],
                    recommendation=self._t(
                        "Remplacez '+all' par '~all' (quarantaine) ou '-all' (rejet strict) dans votre enregistrement SPF.",
                        "Replace '+all' with '~all' (quarantine) or '-all' (strict rejection) in your SPF record."
                    ),
                ))
                self._details["spf"] = {"status": "misconfigured", "records": spf_records}
            else:
                self._details["spf"] = {"status": "ok", "records": spf_records}

        except (dns.exception.DNSException, Exception) as exc:
            self._details["spf"] = {"status": "error", "error": str(exc)}

    # ── DMARC ─────────────────────────────────────────────────────────────────

    def _check_dmarc(self) -> None:
        # DMARC vit sur la zone racine — évite les faux positifs sur les sous-domaines
        root = self._root_domain(self.domain)
        dmarc_domain = f"_dmarc.{root}"
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = DNS_LIFETIME_SEC
            answers = resolver.resolve(dmarc_domain, "TXT")
            dmarc_records = [
                r.to_text().strip('"')
                for r in answers
                if "v=DMARC1" in r.to_text()
            ]

            if not dmarc_records:
                self._add_dmarc_missing_finding(root)
                self._details["dmarc"] = {"status": "missing", "records": []}
            else:
                policy = ""
                for rec in dmarc_records:
                    for tag in rec.split(";"):
                        tag = tag.strip()
                        if tag.startswith("p="):
                            policy = tag.split("=", 1)[1].strip()
                if policy == "none":
                    self._findings.append(Finding(
                        category="DNS & Mail",
                        severity="MEDIUM",
                        title=self._t(
                            "DMARC présent mais en mode surveillance (p=none)",
                            "DMARC present but in monitoring mode (p=none)"
                        ),
                        technical_detail=self._t(
                            "Politique DMARC : p=none — les emails frauduleux ne sont pas bloqués, seulement rapportés.",
                            "DMARC policy: p=none — fraudulent emails are not blocked, only reported."
                        ),
                        plain_explanation=self._t(
                            "Votre protection anti-phishing est en mode 'observateur' : "
                            "elle voit les attaques mais ne les bloque pas. "
                            "Les emails usurpant votre identité arrivent quand même chez vos clients.",
                            "Your anti-phishing protection is in 'observer' mode: "
                            "it sees attacks but doesn't block them. "
                            "Emails impersonating your brand still reach your customers."
                        ),
                        penalty=8,
                        recommendation=self._t(
                            "Passez votre politique DMARC à p=quarantine puis p=reject une fois la configuration SPF validée.",
                            "Upgrade your DMARC policy to p=quarantine, then p=reject once your SPF configuration is validated."
                        ),
                    ))
                self._details["dmarc"] = {"status": "ok", "records": dmarc_records, "policy": policy}

        except dns.resolver.NXDOMAIN:
            self._add_dmarc_missing_finding(root)
            self._details["dmarc"] = {"status": "missing", "records": []}
        except Exception as exc:
            self._details["dmarc"] = {"status": "error", "error": str(exc)}

    # ── DNSSEC ────────────────────────────────────────────────────────────────

    @staticmethod
    def _root_domain(domain: str) -> str:
        """Extrait le domaine racine (ex: sub.example.com → example.com).
        Les DNSKEY/CAA/RDAP vivent sur la zone apex, pas sur les sous-domaines."""
        parts = domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain

    def _check_dnssec(self) -> None:
        """Vérifie si DNSSEC est activé sur la zone DNS du domaine (apex)."""
        root = self._root_domain(self.domain)
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = DNS_LIFETIME_SEC
            # Demander les enregistrements DNSKEY sur le domaine racine — DNSSEC vit à l'apex
            answers = resolver.resolve(root, "DNSKEY")
            if answers:
                self._details["dnssec"] = {"status": "ok"}
                return
        except dns.resolver.NoAnswer:
            pass
        except Exception:
            self._details["dnssec"] = {"status": "error"}
            return

        # DNSKEY absent → DNSSEC non configuré
        self._findings.append(Finding(
            category="DNS & Mail",
            severity="LOW",
            title=self._t(
                "DNSSEC non activé",
                "DNSSEC not enabled"
            ),
            technical_detail=self._t(
                f"Aucun enregistrement DNSKEY trouvé pour {root}. "
                "La zone DNS n'est pas signée cryptographiquement.",
                f"No DNSKEY record found for {root}. "
                "The DNS zone is not cryptographically signed."
            ),
            plain_explanation=self._t(
                "Sans DNSSEC, un attaquant peut falsifier les réponses DNS de votre domaine "
                "(cache poisoning) et rediriger vos visiteurs vers de faux sites sans que personne ne s'en aperçoive.",
                "Without DNSSEC, an attacker can forge DNS responses for your domain "
                "(cache poisoning) and redirect your visitors to fake sites without anyone noticing."
            ),
            penalty=3,
            recommendation=self._t(
                "Activez DNSSEC chez votre bureau d'enregistrement de domaine (Infomaniak, OVH, Gandi…). "
                "La procédure prend moins de 5 minutes depuis l'interface d'administration.",
                "Enable DNSSEC at your domain registrar (Infomaniak, OVH, Gandi…). "
                "The process takes less than 5 minutes from the admin interface."
            ),
        ))
        self._details["dnssec"] = {"status": "missing"}

    # ── CAA ───────────────────────────────────────────────────────────────────

    def _check_caa(self) -> None:
        """Vérifie la présence d'un enregistrement CAA sur la zone apex.
        CAA est hérité par les sous-domaines (RFC 6844) — on interroge le domaine racine."""
        root = self._root_domain(self.domain)
        try:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = DNS_LIFETIME_SEC
            answers = resolver.resolve(root, "CAA")
            if answers:
                caa_records = [r.to_text() for r in answers]
                self._details["caa"] = {"status": "ok", "records": caa_records}
                return
        except dns.resolver.NoAnswer:
            pass
        except Exception:
            self._details["caa"] = {"status": "error"}
            return

        self._findings.append(Finding(
            category="DNS & Mail",
            severity="LOW",
            title=self._t(
                "Enregistrement CAA absent",
                "CAA record missing"
            ),
            technical_detail=self._t(
                f"Aucun enregistrement CAA (Certification Authority Authorization) trouvé pour {root}. "
                "N'importe quelle autorité de certification peut émettre un certificat SSL pour ce domaine.",
                f"No CAA (Certification Authority Authorization) record found for {root}. "
                "Any certificate authority can issue an SSL certificate for this domain."
            ),
            plain_explanation=self._t(
                "Sans CAA, une autorité de certification malveillante ou compromise pourrait émettre "
                "un faux certificat SSL pour votre domaine, permettant des attaques de type 'man-in-the-middle'.",
                "Without CAA, a malicious or compromised certificate authority could issue "
                "a fake SSL certificate for your domain, enabling man-in-the-middle attacks."
            ),
            penalty=2,
            recommendation=self._t(
                "Ajoutez un enregistrement CAA : "
                "votredomaine.com. CAA 0 issue \"letsencrypt.org\" "
                "(remplacez par votre AC — Let's Encrypt, DigiCert, Sectigo…).",
                "Add a CAA record: "
                "yourdomain.com. CAA 0 issue \"letsencrypt.org\" "
                "(replace with your CA — Let's Encrypt, DigiCert, Sectigo…)."
            ),
        ))
        self._details["caa"] = {"status": "missing"}

    def _add_dmarc_missing_finding(self, root: str | None = None) -> None:
        checked = root or self.domain
        self._findings.append(Finding(
            category="DNS & Mail",
            severity="HIGH",
            title=self._t(
                "DMARC manquant — Protection anti-phishing absente",
                "DMARC missing — Anti-phishing protection absent"
            ),
            technical_detail=self._t(
                f"Aucun enregistrement TXT DMARC trouvé pour _dmarc.{checked}.",
                f"No DMARC TXT record found for _dmarc.{checked}."
            ),
            plain_explanation=self._t(
                "Sans DMARC, votre domaine est une cible facile pour le phishing. "
                "Des pirates peuvent envoyer des emails semblant venir de vous pour escroquer vos clients, "
                "partenaires ou employés — et vous n'en serez jamais informé.",
                "Without DMARC, your domain is an easy target for phishing. "
                "Attackers can send emails appearing to come from you to scam your customers, "
                "partners, or employees — and you'll never be notified."
            ),
            penalty=PENALTY_TABLE["dmarc_missing"],
            recommendation=self._t(
                "Ajoutez ce TXT : _dmarc.votredomaine.com → "
                "\"v=DMARC1; p=quarantine; rua=mailto:dmarc@votredomaine.com\". "
                "Progressez ensuite vers p=reject pour un blocage total.",
                "Add this TXT record: _dmarc.yourdomain.com → "
                "\"v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com\". "
                "Then upgrade to p=reject for full blocking."
            ),
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Auditeur SSL / HTTPS
# ─────────────────────────────────────────────────────────────────────────────

class SSLAuditor(BaseAuditor):
    """Vérifie la validité du certificat SSL et la version TLS négociée."""

    DEPRECATED_TLS = {"TLSv1", "TLSv1.1", "SSLv2", "SSLv3"}
    EXPIRY_WARNING_DAYS = int(os.getenv("SSL_EXPIRY_WARNING_DAYS", "30"))

    async def audit(self) -> list[Finding]:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._check_ssl)
        # Check ciphers faibles (connexion séparée, silencieuse si OpenSSL ne supporte pas)
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._check_weak_ciphers),
                timeout=SCAN_TIMEOUT_SEC + 2,
            )
        except (asyncio.TimeoutError, Exception):
            pass
        return self._findings

    def _check_ssl(self) -> None:
        ctx = ssl.create_default_context()
        try:
            raw_conn = socket.create_connection(
                (self.domain, SSL_PORT), timeout=SCAN_TIMEOUT_SEC
            )
            with ctx.wrap_socket(raw_conn, server_hostname=self.domain) as tls_sock:
                cert      = tls_sock.getpeercert()
                tls_ver   = tls_sock.version()
                cipher    = tls_sock.cipher()

                # ── Expiration ────────────────────────────────────────────────
                expire_str  = cert.get("notAfter", "")
                expire_dt   = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(
                    tzinfo=timezone.utc
                )
                days_left = (expire_dt - datetime.now(timezone.utc)).days

                self._details = {
                    "status":      "valid",
                    "issuer":      self._flatten_dn(cert.get("issuer", [])),
                    "subject":     self._flatten_dn(cert.get("subject", [])),
                    "expires":     expire_str,
                    "days_left":   days_left,
                    "tls_version": tls_ver,
                    "cipher":      cipher[0] if cipher else None,
                    "bits":        cipher[2] if cipher else None,
                }

                if days_left < 0:
                    self._findings.append(Finding(
                        category="SSL / HTTPS",
                        severity="CRITICAL",
                        title=self._t("Certificat SSL expiré", "SSL certificate expired"),
                        technical_detail=self._t(
                            f"Le certificat a expiré le {expire_str} (il y a {abs(days_left)} jours).",
                            f"The certificate expired on {expire_str} ({abs(days_left)} days ago)."
                        ),
                        plain_explanation=self._t(
                            "Votre certificat de sécurité est périmé. "
                            "Les navigateurs affichent une page d'erreur rouge effrayante à vos visiteurs, "
                            "et les échanges de données ne sont plus chiffrés.",
                            "Your security certificate has expired. "
                            "Browsers display a scary red error page to your visitors, "
                            "and data exchanges are no longer encrypted."
                        ),
                        penalty=PENALTY_TABLE["ssl_invalid"],
                        recommendation=self._t(
                            "Renouvelez immédiatement votre certificat SSL. "
                            "Let's Encrypt (gratuit) avec Certbot renouvelle automatiquement toutes les 60 jours.",
                            "Renew your SSL certificate immediately. "
                            "Let's Encrypt (free) with Certbot renews automatically every 60 days."
                        ),
                    ))
                elif days_left < self.EXPIRY_WARNING_DAYS:
                    self._findings.append(Finding(
                        category="SSL / HTTPS",
                        severity="MEDIUM",
                        title=self._t(
                            f"Certificat SSL expire dans {days_left} jours",
                            f"SSL certificate expires in {days_left} days"
                        ),
                        technical_detail=self._t(
                            f"Date d'expiration : {expire_str}.",
                            f"Expiration date: {expire_str}."
                        ),
                        plain_explanation=self._t(
                            f"Votre certificat de sécurité expire dans {days_left} jours. "
                            "Passé cette date, vos visiteurs verront un avertissement de sécurité et fuiront votre site.",
                            f"Your security certificate expires in {days_left} days. "
                            "After that, visitors will see a security warning and leave your site."
                        ),
                        penalty=0,
                        recommendation=self._t(
                            "Planifiez le renouvellement maintenant. "
                            "Avec Certbot/Let's Encrypt, il s'effectue en une commande.",
                            "Schedule the renewal now. "
                            "With Certbot/Let's Encrypt, it takes just one command."
                        ),
                    ))

                # ── Version TLS ───────────────────────────────────────────────
                if tls_ver in self.DEPRECATED_TLS:
                    self._findings.append(Finding(
                        category="SSL / HTTPS",
                        severity="HIGH",
                        title=self._t(
                            f"Version TLS obsolète : {tls_ver}",
                            f"Deprecated TLS version: {tls_ver}"
                        ),
                        technical_detail=self._t(
                            f"Le serveur a négocié {tls_ver}, une version officiellement dépréciée par la RFC 8996.",
                            f"The server negotiated {tls_ver}, an officially deprecated version per RFC 8996."
                        ),
                        plain_explanation=self._t(
                            "Votre site utilise une technologie de chiffrement obsolète, "
                            "comme une vieille serrure rouillée sur votre coffre-fort. "
                            "Des attaquants peuvent potentiellement intercepter les communications de vos clients.",
                            "Your site uses outdated encryption technology, "
                            "like a rusty old lock on your safe. "
                            "Attackers may be able to intercept your customers' communications."
                        ),
                        penalty=PENALTY_TABLE["tls_old_version"],
                        recommendation=self._t(
                            "Configurez votre serveur web pour accepter uniquement TLS 1.2 et TLS 1.3. "
                            "Ajoutez : SSLProtocol TLSv1.2 TLSv1.3 (Apache) ou ssl_protocols TLSv1.2 TLSv1.3; (Nginx).",
                            "Configure your web server to accept only TLS 1.2 and TLS 1.3. "
                            "Add: SSLProtocol TLSv1.2 TLSv1.3 (Apache) or ssl_protocols TLSv1.2 TLSv1.3; (Nginx)."
                        ),
                    ))

                # ── Perfect Forward Secrecy ───────────────────────────────────
                cipher_name = cipher[0] if cipher else ""
                # TLS 1.3 mandates ECDHE key exchange → always PFS regardless of cipher name
                # TLS 1.2 PFS ciphers start with ECDHE- or DHE-/EDH-
                has_pfs = (tls_ver == "TLSv1.3") or any(
                    cipher_name.upper().startswith(p)
                    for p in ("ECDHE", "DHE", "EDH", "TLS_AES", "TLS_CHACHA20")
                )
                if cipher_name and not has_pfs:
                    self._findings.append(Finding(
                        category="SSL / HTTPS",
                        severity="MEDIUM",
                        title=self._t(
                            f"Confidentialité persistante absente (PFS) — {cipher_name}",
                            f"Perfect Forward Secrecy missing (PFS) — {cipher_name}"
                        ),
                        technical_detail=self._t(
                            f"Cipher négocié : {cipher_name}. "
                            "Ce cipher utilise un échange de clé RSA statique (pas ECDHE/DHE). "
                            "Un attaquant qui capture le trafic et obtient plus tard la clé privée "
                            "peut déchiffrer rétroactivement toutes les communications passées.",
                            f"Negotiated cipher: {cipher_name}. "
                            "This cipher uses a static RSA key exchange (not ECDHE/DHE). "
                            "An attacker who captures traffic and later obtains the private key "
                            "can retroactively decrypt all past communications."
                        ),
                        plain_explanation=self._t(
                            "Sans PFS, si quelqu'un vole un jour votre clé privée SSL, "
                            "il pourra déchiffrer toutes les conversations que vos clients ont eues "
                            "sur votre site depuis des années. PFS génère une clé unique par session "
                            "qui n'est jamais transmise ni stockée.",
                            "Without PFS, if someone ever steals your SSL private key, "
                            "they can decrypt all conversations your customers have had "
                            "on your site for years. PFS generates a unique key per session "
                            "that is never transmitted or stored."
                        ),
                        penalty=8,
                        recommendation=self._t(
                            "Configurez votre serveur pour prioriser les ciphers ECDHE. "
                            "Nginx : ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:...'; "
                            "ssl_prefer_server_ciphers on;",
                            "Configure your server to prioritize ECDHE ciphers. "
                            "Nginx: ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:...'; "
                            "ssl_prefer_server_ciphers on;"
                        ),
                    ))

                # ── Clé de chiffrement trop courte ────────────────────────────
                key_bits = cipher[2] if cipher and len(cipher) > 2 else None
                if key_bits and key_bits < 128:
                    self._findings.append(Finding(
                        category="SSL / HTTPS",
                        severity="HIGH",
                        title=self._t(
                            f"Clé de chiffrement trop faible : {key_bits} bits",
                            f"Cipher key too short: {key_bits} bits"
                        ),
                        technical_detail=self._t(
                            f"Le cipher négocié utilise une clé de seulement {key_bits} bits "
                            f"({cipher_name}). Les standards modernes exigent 128 bits minimum.",
                            f"The negotiated cipher uses only a {key_bits}-bit key "
                            f"({cipher_name}). Modern standards require at least 128 bits."
                        ),
                        plain_explanation=self._t(
                            f"Votre chiffrement SSL utilise une clé de {key_bits} bits, "
                            "considérée comme insuffisante face aux capacités de calcul actuelles. "
                            "Cette configuration peut permettre une attaque par force brute.",
                            f"Your SSL encryption uses a {key_bits}-bit key, "
                            "considered insufficient against modern computing power. "
                            "This configuration may allow a brute-force attack."
                        ),
                        penalty=15,
                        recommendation=self._t(
                            "Désactivez les ciphers < 128 bits et configurez des suites AES-128 ou AES-256. "
                            "Nginx : ssl_ciphers 'HIGH:!aNULL:!MD5:!RC4:!3DES:!EXPORT';",
                            "Disable ciphers < 128 bits and configure AES-128 or AES-256 suites. "
                            "Nginx: ssl_ciphers 'HIGH:!aNULL:!MD5:!RC4:!3DES:!EXPORT';"
                        ),
                    ))

        except ssl.SSLCertVerificationError as exc:
            is_self_signed = "self-signed" in str(exc).lower()
            label_fr = "auto-signé" if is_self_signed else "invalide / non approuvé"
            label_en = "self-signed" if is_self_signed else "invalid / untrusted"
            self._findings.append(Finding(
                category="SSL / HTTPS",
                severity="CRITICAL",
                title=self._t(
                    f"Certificat SSL {label_fr}",
                    f"SSL certificate {label_en}"
                ),
                technical_detail=str(exc),
                plain_explanation=self._t(
                    "Votre site n'a pas de certificat de sécurité reconnu. "
                    "C'est l'équivalent numérique d'ouvrir un magasin sans porte : "
                    "toutes les données échangées peuvent être interceptées par n'importe qui sur le réseau.",
                    "Your site does not have a recognized security certificate. "
                    "It's the digital equivalent of opening a store with no door: "
                    "all exchanged data can be intercepted by anyone on the network."
                ),
                penalty=PENALTY_TABLE["ssl_invalid"],
                recommendation=self._t(
                    "Installez un certificat SSL valide via Let's Encrypt (gratuit) "
                    "ou un fournisseur commercial (DigiCert, Sectigo…).",
                    "Install a valid SSL certificate via Let's Encrypt (free) "
                    "or a commercial provider (DigiCert, Sectigo…)."
                ),
            ))
            self._details = {"status": "invalid_cert", "error": str(exc)}

        except (ssl.SSLError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            self._findings.append(Finding(
                category="SSL / HTTPS",
                severity="CRITICAL",
                title=self._t(
                    "HTTPS inaccessible sur le port 443",
                    "HTTPS unreachable on port 443"
                ),
                technical_detail=self._t(
                    f"Impossible d'établir une connexion TLS vers {self.domain}:{SSL_PORT} — {exc}",
                    f"Unable to establish a TLS connection to {self.domain}:{SSL_PORT} — {exc}"
                ),
                plain_explanation=self._t(
                    "Votre site n'est pas accessible en HTTPS. "
                    "Toutes les données circulant entre vos visiteurs et votre site "
                    "transitent en clair sur internet (comme envoyer une lettre sans enveloppe).",
                    "Your site is not accessible over HTTPS. "
                    "All data between your visitors and your site travels in plaintext "
                    "on the internet (like sending a letter without an envelope)."
                ),
                penalty=PENALTY_TABLE["ssl_unreachable"],
                recommendation=self._t(
                    "Activez HTTPS sur votre serveur web et pointez votre DNS vers le bon serveur. "
                    "Vérifiez que le pare-feu autorise le port 443.",
                    "Enable HTTPS on your web server and point your DNS to the correct server. "
                    "Ensure your firewall allows port 443."
                ),
            ))
            self._details = {"status": "unreachable", "error": str(exc)}

    # Préfixes des familles de ciphers réellement faibles
    _WEAK_CIPHER_PREFIXES = ("DES", "3DES", "RC4", "EXP", "NULL", "ADH", "AECDH")

    def _check_weak_ciphers(self) -> None:
        """
        Tente une connexion TLS 1.2 avec des ciphers faibles connus (3DES/SWEET32/RC4).
        Si le serveur accepte ET que le cipher négocié est réellement faible → finding HIGH.

        Note : `set_ciphers()` ne s'applique qu'à TLS 1.2. Si seul TLS 1.3 est disponible,
        la connexion s'établit avec un cipher TLS 1.3 fort → pas de finding (serveur sécurisé).
        """
        weak_suites = "3DES:DES:RC4:EXPORT:NULL:!aNULL"
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode    = ssl.CERT_NONE
            # Forcer TLS 1.2 max pour que set_ciphers() soit respecté
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            ctx.set_ciphers(weak_suites)
        except (ssl.SSLError, AttributeError):
            # OpenSSL a supprimé ces ciphers, ou TLSv1_2 non supporté → skip
            return

        try:
            conn = socket.create_connection((self.domain, SSL_PORT), timeout=SCAN_TIMEOUT_SEC)
            with ctx.wrap_socket(conn, server_hostname=self.domain) as tls_sock:
                weak_cipher = tls_sock.cipher()[0] if tls_sock.cipher() else ""
        except (ssl.SSLError, ConnectionRefusedError, OSError):
            # Serveur refuse TLS 1.2 ou ces ciphers → bonne pratique → pas de finding
            return
        except Exception:
            return

        # Vérifier que le cipher négocié est réellement dans les familles faibles
        # (évite les faux positifs si TLS 1.3 s'est négocié à la place)
        if not weak_cipher or not any(
            weak_cipher.upper().startswith(p) for p in self._WEAK_CIPHER_PREFIXES
        ):
            return

        # Si on arrive ici → le serveur a accepté un cipher faible TLS 1.2
        self._findings.append(Finding(
            category="SSL / HTTPS",
            severity="HIGH",
            title=self._t(
                f"Cipher faible accepté : {weak_cipher}",
                f"Weak cipher accepted: {weak_cipher}"
            ),
            technical_detail=self._t(
                f"Le serveur accepte le cipher {weak_cipher}, connu comme vulnérable. "
                "3DES est vulnérable à l'attaque SWEET32 (CVE-2016-2183). "
                "RC4 est cassé depuis 2015 (RFC 7465).",
                f"The server accepts cipher {weak_cipher}, known to be vulnerable. "
                "3DES is vulnerable to the SWEET32 attack (CVE-2016-2183). "
                "RC4 has been broken since 2015 (RFC 7465)."
            ),
            plain_explanation=self._t(
                "Votre serveur accepte des algorithmes de chiffrement obsolètes et cassés. "
                "Des attaquants peuvent exploiter ces failles pour déchiffrer vos communications "
                "SSL en capturant suffisamment de trafic.",
                "Your server accepts outdated and broken encryption algorithms. "
                "Attackers can exploit these flaws to decrypt your SSL communications "
                "by capturing enough traffic."
            ),
            penalty=12,
            recommendation=self._t(
                "Désactivez 3DES, RC4 et NULL dans votre configuration SSL. "
                "Nginx : ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
                "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:!3DES:!RC4'; "
                "ssl_prefer_server_ciphers on;",
                "Disable 3DES, RC4 and NULL in your SSL configuration. "
                "Nginx: ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
                "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:!3DES:!RC4'; "
                "ssl_prefer_server_ciphers on;"
            ),
        ))

    @staticmethod
    def _flatten_dn(dn: list) -> dict[str, str]:
        """Aplatit la structure Subject/Issuer du certificat en dict simple."""
        result = {}
        for item in dn:
            if item:
                k, v = item[0]
                result[k] = v
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Détection d'hébergement mutualisé
# ─────────────────────────────────────────────────────────────────────────────

# (nom_partiel_dans_PTR, libellé_hébergeur)
SHARED_HOSTING_PTR_PATTERNS: list[tuple[str, str]] = [
    ("ovh.net",            "OVH"),
    ("ovhcloud.com",       "OVHcloud"),
    ("kimsufi.com",        "Kimsufi"),
    ("so-you-start.com",   "SoYouStart"),
    ("o2switch.net",       "o2switch"),
    ("o2switch.com",       "o2switch"),
    ("1and1.net",          "Ionos"),
    ("1and1.com",          "Ionos"),
    ("ionos.com",          "Ionos"),
    ("hostinger.com",      "Hostinger"),
    ("hostinger.net",      "Hostinger"),
    ("siteground.com",     "SiteGround"),
    ("siteground.net",     "SiteGround"),
    ("bluehost.com",       "Bluehost"),
    ("gandi.net",          "Gandi"),
    ("planethoster.com",   "PlanetHoster"),
    ("planethoster.info",  "PlanetHoster"),
    ("lws.fr",             "LWS"),
    ("ikoula.com",         "Ikoula"),
    ("infomaniak.com",     "Infomaniak"),
    ("infomaniak.net",     "Infomaniak"),
    ("cloudflare.com",     "Cloudflare"),
    ("inmotionhosting.com","InMotion"),
    ("a2hosting.com",      "A2 Hosting"),
    ("dreamhost.com",      "DreamHost"),
    ("namecheap.com",      "Namecheap"),
    ("godaddy.com",        "GoDaddy"),
]


def _detect_shared_hosting(domain: str) -> tuple[bool, str]:
    """
    Détecte si un domaine est hébergé sur une infrastructure mutualisée
    via une résolution PTR de son adresse IP.
    Retourne (is_shared: bool, provider_name: str).
    """
    try:
        ip = socket.gethostbyname(domain)
        try:
            ptr_host = socket.gethostbyaddr(ip)[0].lower()
        except Exception:
            ptr_host = ""
        for pattern, name in SHARED_HOSTING_PTR_PATTERNS:
            if pattern in ptr_host:
                return True, name
    except Exception:
        pass
    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
# Auditeur de Ports
# ─────────────────────────────────────────────────────────────────────────────

class PortAuditor(BaseAuditor):
    """
    Scanne les ports critiques en parallèle.
    Scan passif uniquement : tentative de connexion TCP (SYN), pas de bannière.
    """

    async def audit(self) -> list[Finding]:
        # ── Résolution IP unique ─────────────────────────────────────────────
        # Résoudre le domaine en IP une seule fois AVANT de lancer les checks
        # en parallèle. Sans ça, chaque _tcp_connect fait sa propre résolution
        # DNS (10+ lookups simultanés du même domaine), ce qui consomme une
        # partie du budget timeout de chaque connexion TCP et rend les résultats
        # non déterministes (un port peut sembler fermé alors qu'il est ouvert).
        loop = asyncio.get_event_loop()
        try:
            self._resolved_ip: str = await asyncio.wait_for(
                loop.run_in_executor(None, socket.gethostbyname, self.domain),
                timeout=SCAN_TIMEOUT_SEC,
            )
        except Exception:
            self._resolved_ip = self.domain  # fallback : laisser le socket résoudre

        # Détecter hébergement mutualisé en parallèle du scan des ports
        shared_future = loop.run_in_executor(None, _detect_shared_hosting, self.domain)

        tasks = [
            self._check_port(port, meta)
            for port, meta in MONITORED_PORTS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        is_shared, provider = await shared_future

        port_map: dict[int, dict] = {}
        for res in results:
            if isinstance(res, dict):
                port_map.update(res)

        # Garder self._details avec uniquement les données de ports (clés entières)
        # pour ne pas casser le template PDF qui fait int(key) sur port_details
        self._details = dict(port_map)

        if is_shared:
            self._add_shared_hosting_note(port_map, provider)
        else:
            self._analyze_open_ports(port_map)

        return self._findings

    def _add_shared_hosting_note(self, port_map: dict[int, dict], provider: str) -> None:
        """
        Sur hébergement mutualisé, les ports ouverts appartiennent à l'infrastructure
        du prestataire — l'utilisateur ne peut pas les fermer.
        On génère un finding INFO neutre si des ports critiques semblent ouverts.
        """
        open_critical = [
            p for p, v in port_map.items()
            if v.get("open") and p in (21, 23, 445, 2375, 3306, 3389, 5432, 6379, 9200, 27017)
        ]
        if open_critical:
            self._findings.append(Finding(
                category="Exposition des Ports",
                severity="INFO",
                title=self._t(
                    f"Ports détectés sur infrastructure mutualisée ({provider})",
                    f"Ports detected on shared hosting infrastructure ({provider})"
                ),
                technical_detail=self._t(
                    f"L'adresse IP de {self.domain} appartient à l'infrastructure partagée de {provider}. "
                    f"Les ports {open_critical} détectés sont gérés par l'hébergeur, "
                    "pas par le client final. Ils ne constituent pas une vulnérabilité actionnable.",
                    f"The IP address of {self.domain} belongs to {provider}'s shared infrastructure. "
                    f"Ports {open_critical} are managed by the hosting provider, "
                    "not by the end customer. They do not represent an actionable vulnerability."
                ),
                plain_explanation=self._t(
                    f"Votre site est hébergé chez {provider} sur une infrastructure mutualisée. "
                    "Les ports ouverts détectés sont gérés directement par l'hébergeur — "
                    "vous ne pouvez pas les modifier. "
                    "Pour un contrôle total du firewall, optez pour un VPS ou un serveur dédié.",
                    f"Your site is hosted at {provider} on shared infrastructure. "
                    "The open ports detected are managed directly by the hosting provider — "
                    "you cannot modify them. "
                    "For full firewall control, consider a VPS or dedicated server."
                ),
                penalty=0,
                recommendation=self._t(
                    f"Aucune action requise sur ces ports — ils sont sous contrôle de {provider}. "
                    "Si vous avez besoin de contrôler votre exposition réseau, "
                    "envisagez de migrer vers un VPS ou serveur dédié.",
                    f"No action required on these ports — they are managed by {provider}. "
                    "If you need to control your network exposure, "
                    "consider migrating to a VPS or dedicated server."
                ),
            ))

    async def _check_port(self, port: int, meta: tuple) -> dict:
        """Tente une connexion TCP non bloquante."""
        service, _penalty_key, severity = meta
        loop = asyncio.get_event_loop()
        try:
            future = loop.run_in_executor(None, self._tcp_connect, port)
            is_open = await asyncio.wait_for(future, timeout=SCAN_TIMEOUT_SEC)
        except (asyncio.TimeoutError, Exception):
            is_open = False
        return {port: {"service": service, "open": is_open, "severity": severity}}

    def _tcp_connect(self, port: int) -> bool:
        """Connexion TCP synchrone (exécutée dans un thread).
        Utilise l'IP pré-résolue (_resolved_ip) pour éviter une résolution DNS
        par port et garantir des résultats cohérents entre scans.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SCAN_TIMEOUT_SEC)
        try:
            target = getattr(self, "_resolved_ip", self.domain)
            result = sock.connect_ex((target, port))
            return result == 0
        except Exception:
            return False
        finally:
            sock.close()

    def _analyze_open_ports(self, port_map: dict[int, dict]) -> None:
        """Génère les findings à partir des ports ouverts."""
        open_ports = {p: v for p, v in port_map.items() if v.get("open")}
        open_nums  = set(open_ports.keys())

        # ── RDP / SMB — Risque Ransomware ────────────────────────────────────
        rdp_smb = sorted(open_nums & {3389, 445})
        if rdp_smb:
            self._findings.append(Finding(
                category="Exposition des Ports",
                severity="CRITICAL",
                title=self._t(
                    f"Port(s) RDP/SMB exposés à internet : {rdp_smb}",
                    f"RDP/SMB port(s) exposed to the internet: {rdp_smb}"
                ),
                technical_detail=self._t(
                    f"Ports détectés ouverts : {rdp_smb}. "
                    "Ces ports sont les vecteurs d'attaque #1 des ransomwares (WannaCry, Ryuk, LockBit…).",
                    f"Open ports detected: {rdp_smb}. "
                    "These ports are the #1 attack vector for ransomware (WannaCry, Ryuk, LockBit…)."
                ),
                plain_explanation=self._t(
                    "Porte d'entrée favorite des pirates pour bloquer vos ordinateurs avec un ransomware "
                    "et exiger une rançon en bitcoins. "
                    "90 % des attaques par ransomware débutent par un port RDP ou SMB accessible depuis internet.",
                    "The favorite entry point for attackers to lock your computers with ransomware "
                    "and demand a bitcoin ransom. "
                    "90% of ransomware attacks start through an RDP or SMB port exposed to the internet."
                ),
                penalty=PENALTY_TABLE["rdp_smb"],
                recommendation=self._t(
                    "ACTION IMMÉDIATE : Fermez les ports 3389 (RDP) et 445 (SMB) dans votre pare-feu. "
                    "Pour l'accès distant, utilisez un VPN (WireGuard, OpenVPN) ou une solution Zero-Trust.",
                    "IMMEDIATE ACTION: Close ports 3389 (RDP) and 445 (SMB) in your firewall. "
                    "For remote access, use a VPN (WireGuard, OpenVPN) or a Zero-Trust solution."
                ),
            ))

        # ── FTP / Telnet — Protocoles sans chiffrement ───────────────────────
        ftp_telnet = sorted(open_nums & {21, 23})
        if ftp_telnet:
            self._findings.append(Finding(
                category="Exposition des Ports",
                severity="HIGH",
                title=self._t(
                    f"Protocole(s) obsolète(s) sans chiffrement : {ftp_telnet}",
                    f"Legacy unencrypted protocol(s) exposed: {ftp_telnet}"
                ),
                technical_detail=self._t(
                    f"Ports actifs : {ftp_telnet}. "
                    "FTP (21) et Telnet (23) transmettent identifiants et données en texte clair sur le réseau.",
                    f"Active ports: {ftp_telnet}. "
                    "FTP (21) and Telnet (23) transmit credentials and data in plaintext over the network."
                ),
                plain_explanation=self._t(
                    "Ces protocoles ont été conçus dans les années 70 sans aucune sécurité. "
                    "Utiliser FTP ou Telnet, c'est comme envoyer votre mot de passe sur une carte postale. "
                    "N'importe qui sur le réseau peut intercepter vos identifiants et vos fichiers.",
                    "These protocols were designed in the 1970s with no security. "
                    "Using FTP or Telnet is like sending your password on a postcard. "
                    "Anyone on the network can intercept your credentials and files."
                ),
                penalty=PENALTY_TABLE["ftp_telnet"],
                recommendation=self._t(
                    "Désactivez FTP et Telnet immédiatement. "
                    "Remplacez par : SFTP/SCP pour les transferts de fichiers, SSH (port 22) pour l'administration.",
                    "Disable FTP and Telnet immediately. "
                    "Replace with: SFTP/SCP for file transfers, SSH (port 22) for remote administration."
                ),
            ))

        # ── Bases de données exposées ─────────────────────────────────────────
        databases = sorted(open_nums & {3306, 5432})
        if databases:
            db_labels = {3306: "MySQL", 5432: "PostgreSQL"}
            db_names  = [db_labels[p] for p in databases]
            self._findings.append(Finding(
                category="Exposition des Ports",
                severity="CRITICAL",
                title=self._t(
                    f"Base(s) de données accessibles depuis internet : {db_names}",
                    f"Database(s) accessible from the internet: {db_names}"
                ),
                technical_detail=self._t(
                    f"Ports de base de données ouverts sur IP publique : {databases}. "
                    "Exposés à des tentatives de connexion et d'injection SQL directes.",
                    f"Database ports open on public IP: {databases}. "
                    "Exposed to direct connection attempts and SQL injection."
                ),
                plain_explanation=self._t(
                    "Votre base de données est directement accessible depuis internet. "
                    "C'est comme laisser vos archives confidentielles clients sur le trottoir. "
                    "Un attaquant peut tenter d'extraire toutes vos données en quelques minutes.",
                    "Your database is directly accessible from the internet. "
                    "It's like leaving your confidential customer records on the street. "
                    "An attacker can attempt to extract all your data within minutes."
                ),
                penalty=PENALTY_TABLE["database"],
                recommendation=self._t(
                    f"Bloquez immédiatement les ports {databases} dans votre pare-feu. "
                    "Les bases de données ne doivent JAMAIS être accessibles depuis l'internet public. "
                    "Utilisez un réseau privé (VPC/VLAN) et des connexions via tunnel SSH.",
                    f"Immediately block ports {databases} in your firewall. "
                    "Databases should NEVER be accessible from the public internet. "
                    "Use a private network (VPC/VLAN) and SSH tunnel connections."
                ),
            ))

        # ── Services exposés — Elasticsearch / Redis / MongoDB / Docker API ────
        _svc_labels = {
            6379:  "Redis",
            9200:  "Elasticsearch",
            27017: "MongoDB",
            2375:  "Docker API",
        }
        exposed_svcs = sorted(open_nums & set(_svc_labels))
        for svc_port in exposed_svcs:
            svc_name = _svc_labels[svc_port]
            self._findings.append(Finding(
                category="Exposition des Ports",
                severity="CRITICAL",
                title=self._t(
                    f"{svc_name} accessible depuis internet (port {svc_port})",
                    f"{svc_name} accessible from the internet (port {svc_port})"
                ),
                technical_detail=self._t(
                    f"Le port {svc_port} ({svc_name}) est ouvert sur l'IP publique du domaine. "
                    f"Ce service ne dispose généralement pas d'authentification par défaut.",
                    f"Port {svc_port} ({svc_name}) is open on the domain's public IP. "
                    f"This service typically has no authentication enabled by default."
                ),
                plain_explanation=self._t(
                    f"{svc_name} est une base de données/service interne qui ne devrait jamais être accessible depuis internet. "
                    "Sans protection, un attaquant peut lire, modifier ou supprimer toutes vos données en quelques secondes — sans mot de passe.",
                    f"{svc_name} is an internal database/service that should never be accessible from the internet. "
                    "Without protection, an attacker can read, modify, or delete all your data within seconds — with no password required."
                ),
                penalty=PENALTY_TABLE["exposed_service"],
                recommendation=self._t(
                    f"Bloquez immédiatement le port {svc_port} dans votre pare-feu. "
                    f"{svc_name} doit être accessible uniquement en réseau privé (127.0.0.1 ou VPC). "
                    "Activez l'authentification et le chiffrement TLS sur le service.",
                    f"Immediately block port {svc_port} in your firewall. "
                    f"{svc_name} must only be accessible on a private network (127.0.0.1 or VPC). "
                    "Enable authentication and TLS encryption on the service."
                ),
            ))

        # ── SSH exposé — observation (pas de pénalité) ───────────────────────
        if 22 in open_nums:
            self._findings.append(Finding(
                category="Exposition des Ports",
                severity="INFO",
                title=self._t(
                    "SSH (port 22) exposé — à surveiller",
                    "SSH (port 22) exposed — monitor closely"
                ),
                technical_detail=self._t(
                    "Port 22 (SSH) accessible depuis internet.",
                    "Port 22 (SSH) accessible from the internet."
                ),
                plain_explanation=self._t(
                    "L'accès SSH distant est ouvert. "
                    "Bien que SSH soit chiffré, ce port est constamment scanné par des bots tentant des mots de passe en boucle.",
                    "Remote SSH access is open. "
                    "While SSH is encrypted, this port is constantly scanned by bots trying passwords in a loop."
                ),
                penalty=0,
                recommendation=self._t(
                    "Désactivez l'authentification par mot de passe SSH (utilisez uniquement des clés SSH). "
                    "Envisagez de déplacer SSH sur un port non-standard ou de le protéger avec Fail2Ban.",
                    "Disable SSH password authentication (use only SSH keys). "
                    "Consider moving SSH to a non-standard port or protecting it with Fail2Ban."
                ),
            ))


# ─────────────────────────────────────────────────────────────────────────────
# Moteur de Score
# ─────────────────────────────────────────────────────────────────────────────

class ScoreEngine:
    """Calcule le SecurityScore final et le niveau de risque."""

    BASE_SCORE = 100

    @staticmethod
    def compute(findings: list[Finding]) -> tuple[int, str]:
        total_penalty = sum(f.penalty for f in findings)
        score         = max(0, ScoreEngine.BASE_SCORE - total_penalty)
        risk_level    = ScoreEngine._risk_level(score)
        return score, risk_level

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 80:
            return "LOW"
        elif score >= 60:
            return "MEDIUM"
        elif score >= 40:
            return "HIGH"
        else:
            return "CRITICAL"



# ─────────────────────────────────────────────────────────────────────────────
# Orchestrateur principal — AuditManager
# ─────────────────────────────────────────────────────────────────────────────

class AuditManager:
    """
    Orchestre l'exécution parallèle de tous les auditeurs.
    Point d'entrée unique : await AuditManager(domain, lang).run()
    """

    # Clés de checks supportées (pour checks_config du monitoring)
    CHECK_KEYS = ("dns", "ssl", "ports", "headers", "email", "tech", "reputation")

    def __init__(
        self,
        domain: str,
        lang: str = "fr",
        plan: str = "free",
        checks_config: dict | None = None,
    ) -> None:
        self.domain = domain.lower().strip()
        self.lang   = lang
        self.plan   = plan

        # Import tardif pour éviter les imports circulaires
        from app.extra_checks import (
            HttpHeaderAuditor,
            EmailSecurityAuditor,
            TechExposureAuditor,
            ReputationAuditor,
            DomainExpiryAuditor,
        )

        # Map clé → auditeur
        all_base: list[tuple[str, BaseAuditor]] = [
            ("dns",        DNSAuditor(self.domain, lang)),
            ("ssl",        SSLAuditor(self.domain, lang)),
            ("ports",      PortAuditor(self.domain, lang)),
            ("headers",    HttpHeaderAuditor(self.domain, lang)),
            ("email",      EmailSecurityAuditor(self.domain, lang)),
            ("tech",       TechExposureAuditor(self.domain, lang)),
            ("reputation", ReputationAuditor(self.domain, lang)),
            ("expiry",     DomainExpiryAuditor(self.domain, lang)),
        ]

        # Filtrer selon checks_config si fourni (True = activé par défaut)
        if checks_config:
            self._auditors = [a for (k, a) in all_base if checks_config.get(k, True)]
        else:
            self._auditors = [a for (_, a) in all_base]

        # Auditeurs premium (Starter, Pro et Dev)
        self._premium_auditors: list[BaseAuditor] = []
        if plan in ("starter", "pro", "dev"):
            from app.advanced_checks import SubdomainAuditor, VulnVersionAuditor
            from app.breach_checks import BreachAuditor
            from app.typosquatting_checks import TyposquattingAuditor
            from app.ct_monitor import CertTransparencyAuditor
            self._subdomain_auditor   = SubdomainAuditor(self.domain, lang)
            self._vuln_auditor        = VulnVersionAuditor(self.domain, lang)
            self._breach_auditor      = BreachAuditor(self.domain, lang)
            self._typosquat_auditor   = TyposquattingAuditor(self.domain, lang)
            self._ct_auditor          = CertTransparencyAuditor(self.domain, lang)
            self._premium_auditors    = [
                self._subdomain_auditor, self._vuln_auditor,
                self._breach_auditor, self._typosquat_auditor,
                self._ct_auditor,
            ]
        else:
            self._subdomain_auditor = None
            self._vuln_auditor      = None
            self._breach_auditor    = None
            self._typosquat_auditor = None
            self._ct_auditor        = None

    async def run(self) -> ScanResult:
        """Lance tous les scans en parallèle et agrège les résultats."""
        start_ts = datetime.now(timezone.utc)

        all_auditors = self._auditors + self._premium_auditors
        audit_results = await asyncio.gather(
            *[auditor.audit() for auditor in all_auditors],
            return_exceptions=True,
        )

        all_findings: list[Finding] = []
        for res in audit_results:
            if isinstance(res, list):
                all_findings.extend(res)

        score, risk_level = ScoreEngine.compute(all_findings)

        sorted_findings = sorted(all_findings, key=lambda f: f.penalty, reverse=True)
        recommendations = [
            f.recommendation
            for f in sorted_findings
            if f.penalty > 0
        ]

        elapsed_ms = int(
            (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000
        )

        # Détails premium
        subdomain_details: dict = {}
        vuln_details: dict = {}
        breach_details: dict = {}
        typosquat_details: dict = {}
        ct_details: dict = {}
        if self.plan in ("starter", "pro", "dev") and self._subdomain_auditor:
            subdomain_details = self._subdomain_auditor.get_details()
        if self.plan in ("starter", "pro", "dev") and self._vuln_auditor:
            vuln_details = self._vuln_auditor.get_details()
        if self.plan in ("starter", "pro", "dev") and self._breach_auditor:
            breach_details = self._breach_auditor.get_details()
        if self.plan in ("starter", "pro", "dev") and self._typosquat_auditor:
            typosquat_details = self._typosquat_auditor.get_details()
        if self.plan in ("starter", "pro", "dev") and self._ct_auditor:
            ct_details = self._ct_auditor.get_details()

        # Conformité NIS2 + RGPD — calculée sur TOUS les findings (tous plans)
        from app.compliance_mapper import ComplianceMapper
        compliance = ComplianceMapper().analyze(all_findings).to_dict()

        return ScanResult(
            domain             = self.domain,
            scanned_at         = start_ts.isoformat(),
            security_score     = score,
            risk_level         = risk_level,
            findings           = sorted_findings,
            dns_details        = self._auditors[0].get_details(),  # DNSAuditor
            ssl_details        = self._auditors[1].get_details(),  # SSLAuditor
            port_details       = {
                int(k): v
                for k, v in self._auditors[2].get_details().items()
            },
            recommendations    = recommendations,
            scan_duration_ms   = elapsed_ms,
            subdomain_details  = subdomain_details,
            vuln_details       = vuln_details,
            breach_details     = breach_details,
            typosquat_details  = typosquat_details,
            ct_details         = ct_details,
            compliance         = compliance,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée CLI (tests rapides)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    domain = sys.argv[1] if len(sys.argv) > 1 else "example.com"
    print(f"\n🔍 CyberHealth Scanner — Analyse de : {domain}\n{'─' * 50}")

    async def _main():
        manager = AuditManager(domain)
        result  = await manager.run()
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    asyncio.run(_main())
