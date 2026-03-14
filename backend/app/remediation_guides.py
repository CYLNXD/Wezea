"""
CyberHealth Scanner — Guides de remédiation pas-à-pas
=====================================================
Module statique de guides de correction pour les findings de sécurité.
Même pattern que FINDING_ACTIONS dans report_service.py.

Chaque guide est lié à une clé de FINDING_ACTIONS et fournit des étapes
concrètes : quoi faire, où le faire, et comment vérifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RemediationStep:
    order: int
    action_fr: str
    action_en: str
    where_fr: str = ""
    where_en: str = ""
    verify_fr: str = ""
    verify_en: str = ""


@dataclass
class RemediationGuide:
    key: str
    title_fr: str
    title_en: str
    difficulty: str        # "easy" | "medium" | "advanced"
    estimated_time_min: int
    steps: list[RemediationStep] = field(default_factory=list)
    is_premium: bool = False


# ── 15 guides prioritaires ────────────────────────────────────────────────────

REMEDIATION_GUIDES: dict[str, RemediationGuide] = {
    # ── 1. SPF manquant ──────────────────────────────────────────────────────
    "SPF manquant": RemediationGuide(
        key="SPF manquant",
        title_fr="Ajouter un enregistrement SPF",
        title_en="Add an SPF record",
        difficulty="easy",
        estimated_time_min=10,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Identifiez votre registrar de domaine (OVH, Gandi, Cloudflare, Namecheap…)",
                action_en="Identify your domain registrar (OVH, Gandi, Cloudflare, Namecheap…)",
                where_fr="Votre email de confirmation d'achat du domaine",
                where_en="Your domain purchase confirmation email",
            ),
            RemediationStep(
                order=2,
                action_fr="Connectez-vous au panneau de gestion DNS de votre registrar",
                action_en="Log in to your registrar's DNS management panel",
                where_fr="OVH : Manager > Domaines > Zone DNS | Gandi : DNS Records | Cloudflare : DNS",
                where_en="OVH: Manager > Domains > DNS Zone | Gandi: DNS Records | Cloudflare: DNS",
            ),
            RemediationStep(
                order=3,
                action_fr="Ajoutez un enregistrement TXT avec la valeur : v=spf1 include:_spf.google.com ~all (adaptez selon votre fournisseur email)",
                action_en="Add a TXT record with the value: v=spf1 include:_spf.google.com ~all (adapt for your email provider)",
                where_fr="Zone DNS > Ajouter une entrée > Type : TXT > Nom : @ (ou vide)",
                where_en="DNS Zone > Add record > Type: TXT > Name: @ (or empty)",
            ),
            RemediationStep(
                order=4,
                action_fr="Attendez la propagation DNS (jusqu'à 24h, généralement 15-30 min)",
                action_en="Wait for DNS propagation (up to 24h, usually 15-30 min)",
            ),
            RemediationStep(
                order=5,
                action_fr="Vérifiez que l'enregistrement est actif",
                action_en="Verify the record is active",
                verify_fr="dig TXT votre-domaine.com +short | grep spf",
                verify_en="dig TXT your-domain.com +short | grep spf",
            ),
        ],
    ),

    # ── 2. DMARC manquant ────────────────────────────────────────────────────
    "DMARC manquant": RemediationGuide(
        key="DMARC manquant",
        title_fr="Créer un enregistrement DMARC",
        title_en="Create a DMARC record",
        difficulty="easy",
        estimated_time_min=10,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Accédez à la zone DNS de votre domaine",
                action_en="Access your domain's DNS zone",
                where_fr="Panneau de gestion de votre registrar (OVH, Gandi, Cloudflare…)",
                where_en="Your registrar's management panel (OVH, Gandi, Cloudflare…)",
            ),
            RemediationStep(
                order=2,
                action_fr="Ajoutez un enregistrement TXT pour _dmarc.votre-domaine.com avec la valeur : v=DMARC1; p=quarantine; rua=mailto:dmarc@votre-domaine.com",
                action_en="Add a TXT record for _dmarc.your-domain.com with value: v=DMARC1; p=quarantine; rua=mailto:dmarc@your-domain.com",
                where_fr="Zone DNS > Ajouter > Type : TXT > Nom : _dmarc",
                where_en="DNS Zone > Add > Type: TXT > Name: _dmarc",
            ),
            RemediationStep(
                order=3,
                action_fr="Surveillez les rapports DMARC pendant 2-4 semaines, puis passez à p=reject",
                action_en="Monitor DMARC reports for 2-4 weeks, then upgrade to p=reject",
            ),
            RemediationStep(
                order=4,
                action_fr="Vérifiez l'enregistrement",
                action_en="Verify the record",
                verify_fr="dig TXT _dmarc.votre-domaine.com +short",
                verify_en="dig TXT _dmarc.your-domain.com +short",
            ),
        ],
    ),

    # ── 3. DKIM non détecté ──────────────────────────────────────────────────
    "DKIM non détecté": RemediationGuide(
        key="DKIM non détecté",
        title_fr="Configurer la signature DKIM",
        title_en="Configure DKIM signing",
        difficulty="medium",
        estimated_time_min=20,
        is_premium=True,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Identifiez votre fournisseur d'email (Google Workspace, Microsoft 365, OVH…)",
                action_en="Identify your email provider (Google Workspace, Microsoft 365, OVH…)",
            ),
            RemediationStep(
                order=2,
                action_fr="Générez la clé DKIM depuis votre fournisseur d'email",
                action_en="Generate the DKIM key from your email provider",
                where_fr="Google : Admin > Apps > Gmail > Authentifier les e-mails | M365 : Exchange Admin > DKIM",
                where_en="Google: Admin > Apps > Gmail > Authenticate emails | M365: Exchange Admin > DKIM",
            ),
            RemediationStep(
                order=3,
                action_fr="Copiez l'enregistrement CNAME ou TXT fourni et ajoutez-le dans votre zone DNS",
                action_en="Copy the provided CNAME or TXT record and add it to your DNS zone",
                where_fr="Zone DNS > Ajouter > Type : CNAME ou TXT > Nom : google._domainkey (ou selon le fournisseur)",
                where_en="DNS Zone > Add > Type: CNAME or TXT > Name: google._domainkey (or per provider)",
            ),
            RemediationStep(
                order=4,
                action_fr="Activez la signature DKIM dans le panneau de votre fournisseur email",
                action_en="Enable DKIM signing in your email provider's panel",
            ),
            RemediationStep(
                order=5,
                action_fr="Vérifiez en envoyant un email de test",
                action_en="Verify by sending a test email",
                verify_fr="Envoyez un email à check-auth@verifier.port25.com et vérifiez le résultat DKIM=pass",
                verify_en="Send an email to check-auth@verifier.port25.com and check for DKIM=pass",
            ),
        ],
    ),

    # ── 4. Certificat SSL expiré ─────────────────────────────────────────────
    "Certificat SSL expiré": RemediationGuide(
        key="Certificat SSL expiré",
        title_fr="Renouveler le certificat SSL",
        title_en="Renew the SSL certificate",
        difficulty="easy",
        estimated_time_min=15,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Connectez-vous à votre serveur ou panneau d'hébergement",
                action_en="Log in to your server or hosting panel",
                where_fr="cPanel, Plesk, ou terminal SSH",
                where_en="cPanel, Plesk, or SSH terminal",
            ),
            RemediationStep(
                order=2,
                action_fr="Si Let's Encrypt : exécutez la commande de renouvellement",
                action_en="If Let's Encrypt: run the renewal command",
                verify_fr="sudo certbot renew --dry-run",
                verify_en="sudo certbot renew --dry-run",
            ),
            RemediationStep(
                order=3,
                action_fr="Si certificat commercial : renouvelez depuis votre fournisseur SSL et réinstallez",
                action_en="If commercial cert: renew from your SSL provider and reinstall",
                where_fr="Votre fournisseur SSL (DigiCert, Sectigo, GlobalSign…)",
                where_en="Your SSL provider (DigiCert, Sectigo, GlobalSign…)",
            ),
            RemediationStep(
                order=4,
                action_fr="Configurez le renouvellement automatique pour éviter les expirations futures",
                action_en="Set up automatic renewal to avoid future expirations",
                verify_fr="sudo certbot certificates  # vérifiez la date d'expiration",
                verify_en="sudo certbot certificates  # check expiration date",
            ),
        ],
    ),

    # ── 5. Version TLS obsolète ──────────────────────────────────────────────
    "Version TLS obsolète": RemediationGuide(
        key="Version TLS obsolète",
        title_fr="Désactiver TLS 1.0/1.1",
        title_en="Disable TLS 1.0/1.1",
        difficulty="medium",
        estimated_time_min=30,
        is_premium=True,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Identifiez votre serveur web (nginx, Apache, IIS)",
                action_en="Identify your web server (nginx, Apache, IIS)",
                verify_fr="nginx -v  # ou  httpd -v  # ou via le panneau d'hébergement",
                verify_en="nginx -v  # or  httpd -v  # or via hosting panel",
            ),
            RemediationStep(
                order=2,
                action_fr="Modifiez la configuration TLS pour n'autoriser que TLS 1.2 et 1.3",
                action_en="Update TLS config to allow only TLS 1.2 and 1.3",
                where_fr="nginx : ssl_protocols TLSv1.2 TLSv1.3; dans le bloc server | Apache : SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1",
                where_en="nginx: ssl_protocols TLSv1.2 TLSv1.3; in server block | Apache: SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1",
            ),
            RemediationStep(
                order=3,
                action_fr="Redémarrez le serveur web",
                action_en="Restart the web server",
                verify_fr="sudo systemctl restart nginx  # ou apache2",
                verify_en="sudo systemctl restart nginx  # or apache2",
            ),
            RemediationStep(
                order=4,
                action_fr="Vérifiez la configuration",
                action_en="Verify the configuration",
                verify_fr="nmap --script ssl-enum-ciphers -p 443 votre-domaine.com",
                verify_en="nmap --script ssl-enum-ciphers -p 443 your-domain.com",
            ),
        ],
    ),

    # ── 6. Port RDP/SMB exposé ───────────────────────────────────────────────
    "Port(s) RDP/SMB": RemediationGuide(
        key="Port(s) RDP/SMB",
        title_fr="Fermer les ports RDP et SMB",
        title_en="Close RDP and SMB ports",
        difficulty="medium",
        estimated_time_min=20,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Accédez au firewall de votre serveur ou panneau d'hébergement",
                action_en="Access your server firewall or hosting panel",
                where_fr="iptables, ufw, panneau cloud (AWS Security Groups, OVH Firewall…)",
                where_en="iptables, ufw, cloud panel (AWS Security Groups, OVH Firewall…)",
            ),
            RemediationStep(
                order=2,
                action_fr="Bloquez les ports 3389 (RDP) et 445 (SMB) pour le trafic entrant depuis internet",
                action_en="Block ports 3389 (RDP) and 445 (SMB) for incoming traffic from the internet",
                verify_fr="sudo ufw deny 3389 && sudo ufw deny 445",
                verify_en="sudo ufw deny 3389 && sudo ufw deny 445",
            ),
            RemediationStep(
                order=3,
                action_fr="Si vous avez besoin d'un accès distant, configurez un VPN (WireGuard, OpenVPN)",
                action_en="If you need remote access, set up a VPN (WireGuard, OpenVPN)",
            ),
            RemediationStep(
                order=4,
                action_fr="Vérifiez que les ports sont fermés",
                action_en="Verify ports are closed",
                verify_fr="nmap -p 3389,445 votre-ip-publique",
                verify_en="nmap -p 3389,445 your-public-ip",
            ),
        ],
    ),

    # ── 7. Base de données exposée ───────────────────────────────────────────
    "Base(s) de données": RemediationGuide(
        key="Base(s) de données",
        title_fr="Bloquer l'accès public aux bases de données",
        title_en="Block public access to databases",
        difficulty="medium",
        estimated_time_min=20,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Identifiez le port exposé (3306=MySQL, 5432=PostgreSQL, 6379=Redis, 27017=MongoDB)",
                action_en="Identify the exposed port (3306=MySQL, 5432=PostgreSQL, 6379=Redis, 27017=MongoDB)",
            ),
            RemediationStep(
                order=2,
                action_fr="Configurez le firewall pour bloquer le port depuis internet",
                action_en="Configure the firewall to block the port from the internet",
                verify_fr="sudo ufw deny 3306  # adaptez le port",
                verify_en="sudo ufw deny 3306  # adapt the port",
            ),
            RemediationStep(
                order=3,
                action_fr="Configurez la base de données pour n'écouter que sur localhost",
                action_en="Configure the database to listen only on localhost",
                where_fr="MySQL : bind-address = 127.0.0.1 dans my.cnf | PostgreSQL : listen_addresses = 'localhost' dans postgresql.conf",
                where_en="MySQL: bind-address = 127.0.0.1 in my.cnf | PostgreSQL: listen_addresses = 'localhost' in postgresql.conf",
            ),
            RemediationStep(
                order=4,
                action_fr="Redémarrez le service de base de données et vérifiez",
                action_en="Restart the database service and verify",
                verify_fr="sudo systemctl restart mysql && nmap -p 3306 votre-ip",
                verify_en="sudo systemctl restart mysql && nmap -p 3306 your-ip",
            ),
        ],
    ),

    # ── 8. HSTS manquant ─────────────────────────────────────────────────────
    "HSTS manquant": RemediationGuide(
        key="HSTS manquant",
        title_fr="Activer l'en-tête HSTS",
        title_en="Enable the HSTS header",
        difficulty="easy",
        estimated_time_min=5,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Ajoutez l'en-tête Strict-Transport-Security dans la configuration de votre serveur web",
                action_en="Add the Strict-Transport-Security header in your web server config",
                where_fr="nginx : add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always; | Apache : Header always set Strict-Transport-Security \"max-age=31536000; includeSubDomains\"",
                where_en="nginx: add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains\" always; | Apache: Header always set Strict-Transport-Security \"max-age=31536000; includeSubDomains\"",
            ),
            RemediationStep(
                order=2,
                action_fr="Redémarrez le serveur web et vérifiez",
                action_en="Restart the web server and verify",
                verify_fr="curl -sI https://votre-domaine.com | grep -i strict",
                verify_en="curl -sI https://your-domain.com | grep -i strict",
            ),
        ],
    ),

    # ── 9. CSP manquant ──────────────────────────────────────────────────────
    "CSP manquant": RemediationGuide(
        key="CSP manquant",
        title_fr="Ajouter une Content-Security-Policy",
        title_en="Add a Content-Security-Policy",
        difficulty="medium",
        estimated_time_min=30,
        is_premium=True,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Commencez par une CSP en mode Report-Only pour identifier les ressources bloquées",
                action_en="Start with a Report-Only CSP to identify blocked resources",
                where_fr="nginx : add_header Content-Security-Policy-Report-Only \"default-src 'self'; script-src 'self'\" always;",
                where_en="nginx: add_header Content-Security-Policy-Report-Only \"default-src 'self'; script-src 'self'\" always;",
            ),
            RemediationStep(
                order=2,
                action_fr="Analysez les violations dans la console navigateur (F12 > Console) pendant quelques jours",
                action_en="Analyze violations in the browser console (F12 > Console) for a few days",
            ),
            RemediationStep(
                order=3,
                action_fr="Ajustez la politique pour autoriser vos sources légitimes (CDN, analytics, fonts…)",
                action_en="Adjust the policy to allow your legitimate sources (CDN, analytics, fonts…)",
            ),
            RemediationStep(
                order=4,
                action_fr="Passez de Report-Only à Content-Security-Policy une fois la politique stable",
                action_en="Switch from Report-Only to Content-Security-Policy once the policy is stable",
                verify_fr="curl -sI https://votre-domaine.com | grep -i content-security",
                verify_en="curl -sI https://your-domain.com | grep -i content-security",
            ),
        ],
    ),

    # ── 10. HTTP→HTTPS redirect manquant ─────────────────────────────────────
    "Pas de redirection HTTP": RemediationGuide(
        key="Pas de redirection HTTP",
        title_fr="Configurer la redirection HTTP vers HTTPS",
        title_en="Set up HTTP to HTTPS redirect",
        difficulty="easy",
        estimated_time_min=10,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Ajoutez un bloc server pour le port 80 qui redirige vers HTTPS",
                action_en="Add a server block for port 80 that redirects to HTTPS",
                where_fr="nginx : server { listen 80; return 301 https://$host$request_uri; } | Apache : RewriteEngine On / RewriteRule ^(.*)$ https://%{HTTP_HOST}/$1 [R=301,L]",
                where_en="nginx: server { listen 80; return 301 https://$host$request_uri; } | Apache: RewriteEngine On / RewriteRule ^(.*)$ https://%{HTTP_HOST}/$1 [R=301,L]",
            ),
            RemediationStep(
                order=2,
                action_fr="Redémarrez le serveur web et vérifiez",
                action_en="Restart the web server and verify",
                verify_fr="curl -sI http://votre-domaine.com | head -3  # doit montrer 301 + Location: https://",
                verify_en="curl -sI http://your-domain.com | head -3  # should show 301 + Location: https://",
            ),
        ],
    ),

    # ── 11. WordPress wp-admin exposé ────────────────────────────────────────
    "WordPress détecté": RemediationGuide(
        key="WordPress détecté",
        title_fr="Sécuriser WordPress",
        title_en="Secure WordPress",
        difficulty="medium",
        estimated_time_min=15,
        is_premium=True,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Restreignez l'accès à /wp-admin par IP dans votre serveur web",
                action_en="Restrict /wp-admin access by IP in your web server",
                where_fr="nginx : location /wp-admin { allow VOTRE_IP; deny all; } | .htaccess pour Apache",
                where_en="nginx: location /wp-admin { allow YOUR_IP; deny all; } | .htaccess for Apache",
            ),
            RemediationStep(
                order=2,
                action_fr="Installez un plugin de sécurité (Wordfence ou Sucuri) et activez le 2FA",
                action_en="Install a security plugin (Wordfence or Sucuri) and enable 2FA",
                where_fr="WordPress : Extensions > Ajouter > Rechercher 'Wordfence'",
                where_en="WordPress: Plugins > Add New > Search 'Wordfence'",
            ),
            RemediationStep(
                order=3,
                action_fr="Désactivez l'éditeur de fichiers intégré",
                action_en="Disable the built-in file editor",
                where_fr="wp-config.php : define('DISALLOW_FILE_EDIT', true);",
                where_en="wp-config.php: define('DISALLOW_FILE_EDIT', true);",
            ),
            RemediationStep(
                order=4,
                action_fr="Mettez à jour WordPress, les thèmes et les plugins",
                action_en="Update WordPress, themes and plugins",
                where_fr="WordPress : Tableau de bord > Mises à jour",
                where_en="WordPress: Dashboard > Updates",
            ),
        ],
    ),

    # ── 12. Server header version exposé ─────────────────────────────────────
    "En-tête Server expose": RemediationGuide(
        key="En-tête Server expose",
        title_fr="Masquer la version du serveur",
        title_en="Hide server version",
        difficulty="easy",
        estimated_time_min=5,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Masquez la version dans la configuration du serveur web",
                action_en="Hide the version in your web server config",
                where_fr="nginx : server_tokens off; | Apache : ServerTokens Prod / ServerSignature Off",
                where_en="nginx: server_tokens off; | Apache: ServerTokens Prod / ServerSignature Off",
            ),
            RemediationStep(
                order=2,
                action_fr="Redémarrez et vérifiez",
                action_en="Restart and verify",
                verify_fr="curl -sI https://votre-domaine.com | grep -i server",
                verify_en="curl -sI https://your-domain.com | grep -i server",
            ),
        ],
    ),

    # ── 13. DNSSEC non activé ────────────────────────────────────────────────
    "DNSSEC non activé": RemediationGuide(
        key="DNSSEC non activé",
        title_fr="Activer DNSSEC",
        title_en="Enable DNSSEC",
        difficulty="easy",
        estimated_time_min=10,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Connectez-vous au panneau de votre registrar",
                action_en="Log in to your registrar's panel",
                where_fr="OVH : Manager > Domaine > DNSSEC | Gandi : Domaine > DNSSEC | Cloudflare : DNS > activer DNSSEC",
                where_en="OVH: Manager > Domain > DNSSEC | Gandi: Domain > DNSSEC | Cloudflare: DNS > enable DNSSEC",
            ),
            RemediationStep(
                order=2,
                action_fr="Activez DNSSEC (bouton ou toggle selon le registrar)",
                action_en="Enable DNSSEC (button or toggle depending on registrar)",
            ),
            RemediationStep(
                order=3,
                action_fr="Vérifiez l'activation",
                action_en="Verify activation",
                verify_fr="dig DNSKEY votre-domaine.com +short  # doit retourner des clés",
                verify_en="dig DNSKEY your-domain.com +short  # should return keys",
            ),
        ],
    ),

    # ── 14. Domaine expire bientôt ───────────────────────────────────────────
    "Domaine expire dans": RemediationGuide(
        key="Domaine expire dans",
        title_fr="Renouveler le nom de domaine",
        title_en="Renew the domain name",
        difficulty="easy",
        estimated_time_min=5,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Connectez-vous au panneau de votre registrar",
                action_en="Log in to your registrar's panel",
                where_fr="OVH, Gandi, Namecheap, Cloudflare, Google Domains…",
                where_en="OVH, Gandi, Namecheap, Cloudflare, Google Domains…",
            ),
            RemediationStep(
                order=2,
                action_fr="Renouvelez le domaine et activez le renouvellement automatique",
                action_en="Renew the domain and enable automatic renewal",
                where_fr="Section Domaines > Votre domaine > Renouveler / Auto-renew",
                where_en="Domains section > Your domain > Renew / Auto-renew",
            ),
            RemediationStep(
                order=3,
                action_fr="Vérifiez la nouvelle date d'expiration",
                action_en="Verify the new expiration date",
                verify_fr="whois votre-domaine.com | grep -i expir",
                verify_en="whois your-domain.com | grep -i expir",
            ),
        ],
    ),

    # ── 15. Permissions-Policy absent ────────────────────────────────────────
    "Permissions-Policy absent": RemediationGuide(
        key="Permissions-Policy absent",
        title_fr="Ajouter l'en-tête Permissions-Policy",
        title_en="Add the Permissions-Policy header",
        difficulty="easy",
        estimated_time_min=5,
        steps=[
            RemediationStep(
                order=1,
                action_fr="Ajoutez l'en-tête dans la configuration de votre serveur web",
                action_en="Add the header in your web server configuration",
                where_fr="nginx : add_header Permissions-Policy \"camera=(), microphone=(), geolocation=()\" always; | Apache : Header always set Permissions-Policy \"camera=(), microphone=(), geolocation=()\"",
                where_en="nginx: add_header Permissions-Policy \"camera=(), microphone=(), geolocation=()\" always; | Apache: Header always set Permissions-Policy \"camera=(), microphone=(), geolocation=()\"",
            ),
            RemediationStep(
                order=2,
                action_fr="Redémarrez le serveur web et vérifiez",
                action_en="Restart the web server and verify",
                verify_fr="curl -sI https://votre-domaine.com | grep -i permissions-policy",
                verify_en="curl -sI https://your-domain.com | grep -i permissions-policy",
            ),
        ],
    ),
}


def get_guide_for_finding(title: str) -> RemediationGuide | None:
    """Retourne le guide correspondant au titre du finding (matching par substring, case-insensitive)."""
    title_lower = title.lower()
    for key, guide in REMEDIATION_GUIDES.items():
        if key.lower() in title_lower:
            return guide
    return None


def get_guides_for_findings(titles: list[str]) -> dict[str, RemediationGuide | None]:
    """Retourne les guides pour une liste de titres (batch)."""
    return {title: get_guide_for_finding(title) for title in titles}
