#!/usr/bin/env python3
"""
Seed script — Blog links keyword mapping
=========================================
Ce script peuple la table `blog_links` avec les correspondances
keyword ↔ article pour toutes les catégories de findings du scanner.

Usage (à exécuter depuis le répertoire backend/) :
    .venv/bin/python seed_blog_links.py

Le script est idempotent : il vide la table avant de réinsérer.
Il peut donc être relancé sans risque.
"""

import sys, os

# Ajouter le répertoire backend au path Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, engine, Base
from app.models import BlogLink

# ── Mappings complets ──────────────────────────────────────────────────────────
#
# Structure : (match_keyword, article_title, article_url)
#
# match_keyword : mots-clés séparés par des virgules.
#   Chaque mot-clé est cherché (insensible à la casse) dans le texte
#   de recommandation affiché dans l'onglet Recommandations du Dashboard.
#   La première correspondance gagne → les entrées sont ordonnées du
#   plus spécifique au plus générique.
#
# Les recommandations viennent de f.recommendation dans chaque auditor :
#   scanner.py, extra_checks.py, advanced_checks.py, breach_checks.py, …
#   ainsi que des DEFAULT_OPTIMIZE_ACTIONS (fr/en) du report_service.

BLOG_LINKS = [

    # ── 1. Certificat SSL expiré / renouvelé ──────────────────────────────────
    # Matches : SSL expired (certbot, let's encrypt), SSL expiring soon
    (
        "votre certificat ssl,certbot,let's encrypt,install a valid ssl,renew your ssl,renouveler les certificats",
        "Que faire quand votre certificat SSL est expiré ?",
        "/blog/certificat-ssl-expire/",
    ),

    # ── 2. Configuration SPF / DKIM / DMARC ───────────────────────────────────
    # Matches : SPF manquant ("v=spf1"), SPF +all ("~all"), DMARC manquant ("_dmarc."),
    #           DKIM non détecté ("dkim chez votre")
    (
        "v=spf1,_dmarc.votredomaine,dkim chez votre,dkim with your hosting,~all',ajoutez ce txt",
        "Guide complet : configurer SPF, DKIM et DMARC",
        "/blog/configurer-spf-dkim-dmarc/",
    ),

    # ── 3. Analyse des rapports DMARC ─────────────────────────────────────────
    # Matches : DMARC en mode p=none → montée à p=quarantine/reject
    (
        "p=quarantine puis p=reject,quarantine, then p=reject,politique dmarc",
        "Analyser les rapports DMARC pour protéger votre domaine",
        "/blog/dmarc-rapports-analyse/",
    ),

    # ── 4. Ports réseau dangereux ─────────────────────────────────────────────
    # Matches : FTP/Telnet ouverts, SSH password auth, services DB/Docker/Redis exposés
    (
        "ftp et telnet,disable ftp,clés ssh,ssh keys,réseau privé (vpc,private network (vpc",
        "Les ports réseau dangereux à fermer absolument",
        "/blog/ports-reseau-dangereux/",
    ),

    # ── 5. Ransomware — prévention ────────────────────────────────────────────
    # Matches : RDP/SMB ouverts (le vecteur ransomware par excellence)
    #           La recommandation mentionne WireGuard/OpenVPN
    (
        "wireguard,openvpn,ports 3389 (rdp,close ports 3389",
        "Ransomware : comment protéger votre PME",
        "/blog/ransomware-pme-prevention/",
    ),

    # ── 6. DNS Hijacking ──────────────────────────────────────────────────────
    # Matches : CAA record manquant (empêche l'émission de certifs non autorisés)
    (
        "enregistrement caa,caa 0 issue,add a caa,ajoutez un enregistrement caa",
        "DNS Hijacking : comment protéger vos enregistrements DNS",
        "/blog/dns-hijacking/",
    ),

    # ── 7. DNSSEC ─────────────────────────────────────────────────────────────
    # Matches : DNSSEC non activé
    (
        "activez dnssec,enable dnssec,bureau d'enregistrement de domaine (infomaniak",
        "DNSSEC : sécuriser vos enregistrements DNS contre la falsification",
        "/blog/dnssec-securiser-dns/",
    ),

    # ── 8. Headers HTTP de sécurité ───────────────────────────────────────────
    # Matches : HSTS, CSP, X-Frame-Options, X-Content-Type-Options,
    #           Referrer-Policy, Permissions-Policy, redirection HTTP→HTTPS
    (
        "strict-transport-security,content-security-policy,x-frame-options,x-content-type-options,referrer-policy,permissions-policy,redirection 301,x-powered-by",
        "Les headers HTTP de sécurité essentiels à configurer",
        "/blog/headers-http-securite/",
    ),

    # ── 9. Sécurité WordPress ─────────────────────────────────────────────────
    # Matches : WordPress détecté, /wp-admin exposé
    # ⚠️  Mis AVANT MFA car la recommendation WordPress contient aussi "double authentification"
    (
        "wordpress,/wp-admin",
        "Sécurité WordPress : la checklist complète",
        "/blog/securite-wordpress-checklist/",
    ),

    # ── 10. MFA / Double authentification ─────────────────────────────────────
    # Matches : breach finding (2FA), DEFAULT_OPTIMIZE (gestionnaire de mots de passe)
    # Note : "double authentification" seul retiré pour ne pas interférer avec WordPress
    (
        "authentification à deux facteurs (2fa),gestionnaire de mots de passe,enterprise password manager,two-factor authentication on all",
        "MFA et double authentification : protéger vos comptes",
        "/blog/mfa-authentification-double-facteur/",
    ),

    # ── 10. Expiration du nom de domaine ──────────────────────────────────────
    # Matches : toutes les variantes de "renouveler le domaine {root} via bureau d'enregistrement"
    (
        "via votre bureau d'enregistrement,auto-renewal to avoid,renouvellement automatique chez votre bureau",
        "Expiration de nom de domaine : risques et comment l'éviter",
        "/blog/expiration-nom-domaine/",
    ),

    # ── 11. Liste noire email ─────────────────────────────────────────────────
    # Matches : domaine/IP blacklisté dans les DNSBL
    (
        "opérateurs des blacklists,blacklist operators,serveur a été compromis,server has been compromised",
        "Votre domaine est-il sur liste noire ? Comment le vérifier et en sortir",
        "/blog/liste-noire-email-domaine/",
    ),

    # ── 12. Réputation IP et délivrabilité email ──────────────────────────────
    # Matches : domaine avec bonne réputation (finding INFO avec recommandation de maintien)
    (
        "préserver cette réputation,good email sending practices,bonnes pratiques d'envoi email",
        "Réputation IP et délivrabilité email : tout comprendre",
        "/blog/reputation-ip-delivrabilite-email/",
    ),

    # ── 13. Protection phishing domaine ───────────────────────────────────────
    # Matches : DEFAULT_OPTIMIZE_ACTIONS anti-phishing
    (
        "sensibilisation anti-phishing,anti-phishing awareness programme",
        "Phishing et usurpation de domaine : comment protéger votre marque",
        "/blog/protection-phishing-domaine/",
    ),

    # ── 14. Usurpation de domaine / email ─────────────────────────────────────
    # Matches : domaine sans MX ni SPF/DMARC → recommandation de compléter la politique
    (
        "politique spf/dmarc complète,spf/dmarc policy",
        "Comment protéger son domaine contre l'usurpation d'email",
        "/blog/usurpation-domaine-email/",
    ),

    # ── 16. Sous-domaines et risques sécurité ─────────────────────────────────
    # Matches : CT monitor finding (surveiller sous-domaines et certificats)
    (
        "surveiller régulièrement les sous-domaines,regularly monitor subdomains,logs ct sont immuables",
        "Sous-domaines et sécurité : les risques souvent négligés",
        "/blog/sous-domaines-risques-securite/",
    ),

    # ── 17. Vulnérabilités CVE / versions logicielles ─────────────────────────
    # Matches : PHP vulnérable, Apache, nginx, IIS — VulnVersionAuditor
    (
        "migrer vers php,mettre à jour apache,mettre à jour nginx,migrer vers iis,update apache immediately,update nginx",
        "Vulnérabilités CVE : pourquoi mettre à jour vos logiciels serveur",
        "/blog/vulnerabilites-cve-logiciels/",
    ),

    # ── 18. Score de sécurité de domaine ──────────────────────────────────────
    # Matches : DEFAULT_OPTIMIZE — surveillance IDS/IPS, SIEM
    (
        "ids/ips,siem,journalisation des événements",
        "Comprendre le score de sécurité de votre domaine",
        "/blog/score-securite-domaine/",
    ),

    # ── 19. Audit de sécurité de domaine ──────────────────────────────────────
    # Matches : DEFAULT_OPTIMIZE — pentest annuel
    (
        "pentest,penetration test,test d'intrusion",
        "Comment réaliser un audit de sécurité de votre domaine",
        "/blog/audit-securite-domaine/",
    ),

]


def seed():
    db = SessionLocal()
    try:
        # Vider la table pour garantir l'idempotence
        deleted = db.query(BlogLink).delete()
        db.commit()
        if deleted:
            print(f"🗑  {deleted} entrée(s) existante(s) supprimée(s).")

        # Insérer les nouvelles entrées
        inserted = 0
        for match_keyword, article_title, article_url in BLOG_LINKS:
            link = BlogLink(
                match_keyword = match_keyword,
                article_title = article_title,
                article_url   = article_url,
            )
            db.add(link)
            inserted += 1

        db.commit()
        print(f"✅  {inserted} blog link(s) insérés avec succès.\n")

        # Afficher le résumé
        all_links = db.query(BlogLink).all()
        for l in all_links:
            kw_preview = l.match_keyword[:60] + "…" if len(l.match_keyword) > 60 else l.match_keyword
            print(f"  [{l.id:2d}] {l.article_url}\n       Keywords: {kw_preview}")

    except Exception as e:
        db.rollback()
        print(f"❌  Erreur : {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("🔗  Seeding blog_links table…\n")
    seed()
    print("\n✓  Terminé.")
