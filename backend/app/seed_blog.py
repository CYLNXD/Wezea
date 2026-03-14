"""
Seed 6 blog articles into the database.
Run: python -m app.seed_blog
"""
from datetime import datetime, timezone
from app.database import SessionLocal, engine, Base
from app.models import BlogArticle

ARTICLES = [
    {
        "slug": "configurer-spf-5-minutes",
        "title": "Configurer SPF en 5 minutes",
        "meta_description": "Guide pas-à-pas pour configurer un enregistrement SPF sur votre domaine et protéger vos emails contre l'usurpation d'identité.",
        "category": "dns",
        "reading_time_min": 5,
        "content_md": """## Qu'est-ce que SPF ?

SPF (Sender Policy Framework) est un enregistrement DNS TXT qui indique quels serveurs sont autorisés à envoyer des emails pour votre domaine. Sans SPF, n'importe qui peut envoyer des emails en se faisant passer pour votre organisation.

## Pourquoi c'est important

- **Anti-spoofing** : empêche l'usurpation de votre domaine pour du phishing
- **Délivrabilité** : les serveurs mail vérifient le SPF avant d'accepter un email
- **Conformité NIS2** : l'article 21 impose des mesures de sécurité des communications

## Étape 1 : Identifier vos serveurs d'envoi

Listez tous les services qui envoient des emails pour votre domaine :
- Votre serveur mail (Exchange, Postfix, etc.)
- Services marketing (Brevo, Mailchimp, SendGrid)
- Services transactionnels (Stripe, votre application web)

## Étape 2 : Construire l'enregistrement

La syntaxe de base :

```
v=spf1 include:_spf.google.com include:spf.brevo.com -all
```

- `v=spf1` : version du protocole
- `include:` : autorise les serveurs d'un service tiers
- `-all` : rejette tout email non autorisé (recommandé)
- `~all` : marque comme suspect mais ne rejette pas (soft fail)

## Étape 3 : Ajouter dans votre DNS

1. Connectez-vous à votre gestionnaire DNS (OVH, Cloudflare, Gandi, etc.)
2. Ajoutez un enregistrement TXT sur votre domaine racine
3. Collez votre enregistrement SPF
4. Attendez la propagation DNS (5-30 minutes)

## Étape 4 : Vérifier

Utilisez le scanner Wezea pour vérifier que votre SPF est correctement configuré. Le résultat doit indiquer "SPF valide" avec la politique appropriée.

## Erreurs courantes

| Erreur | Solution |
|--------|----------|
| Trop de lookups DNS (>10) | Réduire les `include:` ou utiliser des IP directes |
| `+all` au lieu de `-all` | Remplacer par `-all` pour rejeter les non-autorisés |
| SPF sur un sous-domaine | Ajouter aussi sur le domaine racine |

## Prochaines étapes

Une fois SPF configuré, passez à DMARC pour une protection complète de vos emails.
""",
    },
    {
        "slug": "dmarc-protegez-domaine-phishing",
        "title": "DMARC : protégez votre domaine du phishing",
        "meta_description": "Comprendre et configurer DMARC pour empêcher les attaquants d'usurper votre domaine dans des campagnes de phishing.",
        "category": "dns",
        "reading_time_min": 7,
        "content_md": """## Qu'est-ce que DMARC ?

DMARC (Domain-based Message Authentication, Reporting and Conformance) est le mécanisme qui orchestre SPF et DKIM pour protéger votre domaine contre le phishing.

## Comment ça fonctionne

1. L'email arrive chez le serveur destinataire
2. Le serveur vérifie SPF (serveur autorisé ?) et DKIM (signature valide ?)
3. DMARC indique quoi faire si les deux échouent : rien, quarantaine ou rejet

## Les 3 politiques DMARC

| Politique | Effet | Recommandation |
|-----------|-------|----------------|
| `p=none` | Aucune action, rapports seulement | Phase de test |
| `p=quarantine` | Mise en spam | Phase de transition |
| `p=reject` | Email rejeté | Production |

## Configuration pas-à-pas

### 1. Commencer par `p=none`

```
v=DMARC1; p=none; rua=mailto:dmarc@votredomaine.com
```

Cela vous envoie des rapports sans bloquer d'emails. Analysez les rapports pendant 2-4 semaines.

### 2. Passer à `p=quarantine`

```
v=DMARC1; p=quarantine; rua=mailto:dmarc@votredomaine.com; pct=50
```

`pct=50` applique la politique à 50% des emails non conformes. Augmentez progressivement.

### 3. Objectif : `p=reject`

```
v=DMARC1; p=reject; rua=mailto:dmarc@votredomaine.com
```

C'est la configuration la plus sécurisée. Elle bloque tout email non authentifié.

## Ajouter l'enregistrement DNS

- Type : TXT
- Nom : `_dmarc.votredomaine.com`
- Valeur : votre enregistrement DMARC

## Lire les rapports

Les rapports DMARC sont en XML. Des services gratuits comme dmarcian ou Postmark DMARC les rendent lisibles. Ils montrent :
- Qui envoie des emails pour votre domaine
- Quels emails passent ou échouent SPF/DKIM
- Les tentatives de spoofing détectées

## Impact sur la conformité

DMARC avec `p=reject` est considéré comme une bonne pratique dans le cadre de NIS2 (article 21, sécurité des communications) et du RGPD (article 32, sécurité du traitement).
""",
    },
    {
        "slug": "certificat-ssl-expire-que-faire",
        "title": "Certificat SSL expiré : que faire ?",
        "meta_description": "Votre certificat SSL a expiré ou va expirer ? Voici comment le renouveler rapidement et éviter que ça se reproduise.",
        "category": "ssl",
        "reading_time_min": 5,
        "content_md": """## Les risques d'un certificat expiré

Un certificat SSL expiré provoque :
- **Avertissement navigateur** : "Votre connexion n'est pas privée" → perte de visiteurs
- **Perte de confiance** : vos clients voient un cadenas rouge
- **Vulnérabilité** : les données transitent potentiellement en clair
- **Impact SEO** : Google pénalise les sites sans HTTPS valide

## Vérifier l'état de votre certificat

Lancez un scan sur Wezea — le rapport SSL vous indique :
- La date d'expiration exacte
- La version TLS utilisée
- La force du chiffrement

## Renouveler avec Let's Encrypt (gratuit)

Si vous utilisez Let's Encrypt (la majorité des sites) :

```bash
# Renouveler manuellement
sudo certbot renew

# Vérifier le renouvellement automatique
sudo systemctl status certbot.timer
```

## Renouveler un certificat commercial

1. Connectez-vous à votre fournisseur (DigiCert, Sectigo, etc.)
2. Générez une nouvelle CSR sur votre serveur
3. Soumettez la CSR pour validation
4. Installez le nouveau certificat

## Automatiser le renouvellement

Pour ne plus jamais avoir ce problème :

### Option 1 : Certbot auto-renew (Let's Encrypt)
```bash
# Vérifier que le timer est actif
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

### Option 2 : Surveillance avec Wezea
Ajoutez votre domaine au monitoring Wezea. Vous recevrez une alerte email quand votre certificat approche de l'expiration.

## Bonnes pratiques SSL/TLS

- Utilisez TLS 1.2 minimum (idéalement TLS 1.3)
- Activez HSTS pour forcer HTTPS
- Vérifiez que la redirection HTTP → HTTPS fonctionne
- Renouvelez au moins 30 jours avant l'expiration
""",
    },
    {
        "slug": "hsts-pourquoi-comment-activer",
        "title": "HSTS : pourquoi et comment l'activer",
        "meta_description": "HSTS force les navigateurs à utiliser HTTPS. Découvrez pourquoi c'est essentiel et comment le configurer sur votre serveur.",
        "category": "headers",
        "reading_time_min": 5,
        "content_md": """## Qu'est-ce que HSTS ?

HSTS (HTTP Strict Transport Security) est un en-tête HTTP qui indique aux navigateurs de toujours utiliser HTTPS pour votre domaine. Une fois reçu, le navigateur refuse automatiquement toute connexion HTTP.

## Pourquoi c'est important

Sans HSTS, un attaquant peut intercepter la première connexion HTTP (avant la redirection vers HTTPS) via une attaque man-in-the-middle. HSTS élimine cette fenêtre de vulnérabilité.

## Configuration

### Nginx

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

### Apache

```apache
Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
```

### Caddy

HSTS est activé par défaut avec Caddy.

## Paramètres expliqués

| Paramètre | Valeur | Signification |
|-----------|--------|---------------|
| `max-age` | 31536000 | Durée en secondes (1 an) |
| `includeSubDomains` | — | Applique HSTS à tous les sous-domaines |
| `preload` | — | Permet l'inscription dans la liste de préchargement Chrome |

## Mise en place progressive

1. **Semaine 1** : `max-age=300` (5 minutes) — testez que tout fonctionne
2. **Semaine 2** : `max-age=86400` (1 jour) — vérifiez les sous-domaines
3. **Production** : `max-age=31536000` (1 an) — configuration finale

## Attention avant d'activer

- Assurez-vous que **tous** vos sous-domaines ont un certificat SSL valide
- Une fois HSTS activé avec `preload`, c'est très difficile à annuler
- Testez d'abord sans `includeSubDomains` si vous avez des sous-domaines HTTP

## Vérification

Utilisez le scanner Wezea pour vérifier que l'en-tête HSTS est correctement configuré. Le rapport affichera un statut vert si la configuration est bonne.
""",
    },
    {
        "slug": "ports-rdp-smb-exposes-risques-pme",
        "title": "Ports RDP/SMB exposés : les risques pour votre PME",
        "meta_description": "Les ports RDP (3389) et SMB (445) exposés sur Internet sont la porte d'entrée favorite des ransomwares. Voici comment les sécuriser.",
        "category": "ports",
        "reading_time_min": 6,
        "content_md": """## Pourquoi RDP et SMB sont dangereux

RDP (Remote Desktop Protocol, port 3389) et SMB (Server Message Block, port 445) sont les deux services les plus ciblés par les attaquants. En 2025, plus de 60% des ransomwares exploitent un accès RDP exposé.

## Les attaques courantes

### Brute-force RDP
L'attaquant teste des milliers de combinaisons utilisateur/mot de passe. Avec un dictionnaire et un accès direct, il peut trouver des identifiants en quelques heures.

### EternalBlue (SMB)
La vulnérabilité EternalBlue (MS17-010) permet l'exécution de code à distance via SMB. C'est l'exploit utilisé par WannaCry et NotPetya.

### Ransomware
Une fois connecté via RDP, l'attaquant installe un ransomware qui chiffre tous vos fichiers et demande une rançon.

## Comment vérifier

Lancez un scan Wezea sur votre domaine ou IP publique. Le rapport indiquera si les ports 3389 (RDP) ou 445 (SMB) sont accessibles depuis Internet.

## Solutions

### 1. Fermer les ports (recommandé)
```bash
# Firewall UFW (Ubuntu)
sudo ufw deny 3389/tcp
sudo ufw deny 445/tcp
```

### 2. VPN obligatoire
Si vous avez besoin d'un accès distant, utilisez un VPN. L'utilisateur se connecte d'abord au VPN, puis accède au RDP en interne.

### 3. Whitelist IP
Si un VPN n'est pas possible, limitez l'accès RDP à des IP spécifiques :
```bash
sudo ufw allow from 203.0.113.10 to any port 3389
```

### 4. Autres mesures
- Activez le NLA (Network Level Authentication) sur RDP
- Utilisez des mots de passe forts (>12 caractères)
- Activez la MFA (authentification multi-facteurs)
- Désactivez SMBv1

## Impact conformité

L'exposition de ports non sécurisés est un manquement direct à l'article 21 de NIS2 qui impose la sécurité des réseaux et systèmes d'information.
""",
    },
    {
        "slug": "nis2-pme-guide-2026",
        "title": "NIS2 : ce que les PME doivent savoir en 2026",
        "meta_description": "La directive NIS2 s'applique à de nombreuses PME depuis 2024. Découvrez vos obligations et comment vous mettre en conformité.",
        "category": "compliance",
        "reading_time_min": 8,
        "content_md": """## NIS2 en bref

La directive NIS2 (Network and Information Security 2) est la réglementation européenne sur la cybersécurité des organisations. Entrée en vigueur en octobre 2024, elle élargit considérablement le périmètre des entreprises concernées.

## Êtes-vous concerné ?

NIS2 s'applique si votre entreprise :
- Opère dans un secteur essentiel ou important (énergie, santé, transport, finance, numérique, alimentation, etc.)
- A plus de 50 employés OU un CA > 10M EUR
- Fournit des services numériques (cloud, DNS, marketplace)

Même si vous êtes une PME, vous pouvez être concerné en tant que sous-traitant d'une entité essentielle.

## Les obligations principales

### Article 21 — Mesures de sécurité

| Mesure | Description |
|--------|-------------|
| Analyse de risques | Évaluation régulière des risques cyber |
| Gestion des incidents | Procédure de détection et réponse |
| Continuité d'activité | Plan de reprise et sauvegardes |
| Sécurité de la chaîne | Vérification des fournisseurs |
| Chiffrement | Protection des données en transit et au repos |
| Contrôle d'accès | Authentification forte, MFA |
| Formation | Sensibilisation des employés |

### Article 23 — Notification des incidents

- **24h** : notification initiale à l'ANSSI (ou équivalent national)
- **72h** : rapport détaillé avec évaluation d'impact
- **1 mois** : rapport final avec mesures correctives

## Les sanctions

- Entités essentielles : jusqu'à 10M EUR ou 2% du CA mondial
- Entités importantes : jusqu'à 7M EUR ou 1,4% du CA mondial
- Responsabilité personnelle des dirigeants possible

## Par où commencer ?

### 1. Diagnostic technique
Utilisez le scanner Wezea pour évaluer votre posture technique. Le rapport de conformité NIS2 vous donne un score et identifie les lacunes.

### 2. Mesures organisationnelles
- Désignez un responsable sécurité
- Rédigez une politique de sécurité
- Mettez en place un plan de réponse aux incidents
- Formez vos employés

### 3. Mesures techniques prioritaires
- Chiffrement des communications (TLS 1.2+, HSTS)
- Authentification forte (MFA sur tous les accès critiques)
- Sauvegardes régulières testées
- Monitoring et détection d'intrusion

### 4. Documentation
Documentez toutes vos mesures. En cas d'audit, vous devrez prouver que vous avez mis en place les contrôles appropriés.

## RGPD et NIS2

Le RGPD (article 32) et NIS2 se complètent. Le RGPD protège les données personnelles, NIS2 protège les systèmes d'information. Les mesures techniques sont souvent les mêmes :
- Chiffrement
- Contrôle d'accès
- Sauvegardes
- Monitoring

Un bon score de conformité Wezea couvre les deux réglementations simultanément.
""",
    },
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for art_data in ARTICLES:
            existing = db.query(BlogArticle).filter(BlogArticle.slug == art_data["slug"]).first()
            if existing:
                print(f"  skip {art_data['slug']} (already exists)")
                continue
            article = BlogArticle(
                slug=art_data["slug"],
                title=art_data["title"],
                meta_description=art_data["meta_description"],
                content_md=art_data["content_md"].strip(),
                category=art_data["category"],
                author="Wezea",
                reading_time_min=art_data["reading_time_min"],
                is_published=True,
                published_at=datetime.now(timezone.utc),
            )
            db.add(article)
            print(f"  + {art_data['slug']}")
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
