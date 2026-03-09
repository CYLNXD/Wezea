# Plan de remédiation sécurité — wezea.net
> Basé sur le rapport d'audit du 09/03/2026 · Score : 41/100 · Objectif : 85+/100

---

## ✅ Corrections déjà appliquées dans ce repo

| # | Finding | Action | Fichier modifié |
|---|---------|--------|-----------------|
| 6 | Version serveur exposée (LOW -3pts) | `server_tokens off;` ajouté | `nginx-wezea.conf`, `nginx-scan.conf` |
| 8 | MTA-STS non configuré (LOW -2pts) | Config nginx + politique créées | `nginx-mta-sts.conf` (nouveau) |

---

## 🔴 CRITICAL — À faire en urgence (avant J+7)

### #1 — 6 domaines sosies enregistrés (Typosquatting · -25 pts)

**Risque** : Des tiers ont enregistré `ezea.net`, `weea.net`, `wesea.net`… pouvant servir au phishing.

**Actions manuelles chez votre registrar (Infomaniak) :**

1. Aller sur [Infomaniak Domains](https://www.infomaniak.com/fr/domaines) → acheter :
   - `wezea.com` (priorité max — le .com est le plus crédible pour le phishing)
   - `wezea.fr` (audience française)
   - `wezea.org`
2. Configurer les domaines achetés en **redirection 301** vers `wezea.net`
3. Signaler les domaines actifs malveillants (`ezea.net`, `weea.net`) :
   - Via [ICANN WHOIS](https://lookup.icann.org/) → trouver le registrar → déposer plainte
   - Ou via [Nominet abuse](https://www.nominet.uk/report-abuse/) pour les .net

**Protection DMARC liée :** appliquer #2 ci-dessous simultanément.

---

## 🟠 MEDIUM — À corriger sous 30 jours

### #2 — DMARC en mode surveillance p=none (-8 pts)

**Risque** : N'importe qui peut envoyer des emails en se faisant passer pour `@wezea.net`.

**Enregistrement DNS actuel :**
```
v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com
```

**Procédure (Infomaniak → Hébergement → Domaines → DNS) :**

Étape 1 — Passer à `p=quarantine` (les emails frauduleux vont en spam) :
```
v=DMARC1; p=quarantine; rua=mailto:rua@dmarc.brevo.com; pct=100
```

Étape 2 — Attendre 2 semaines, analyser les rapports reçus sur `rua@dmarc.brevo.com`.
Si aucun email légitime ne part en spam, passer à `p=reject` :
```
v=DMARC1; p=reject; rua=mailto:rua@dmarc.brevo.com; pct=100
```

⚠️ Ne passer à `p=reject` qu'après avoir configuré DKIM (#3) et vérifié les rapports.

---

### #3 — DKIM non détecté (-8 pts)

**Risque** : Sans DKIM, les emails peuvent être falsifiés sans détection.

**Configuration DKIM chez Infomaniak :**

1. Se connecter à [Infomaniak Manager](https://manager.infomaniak.com)
2. Menu → **Emails** → votre domaine `wezea.net`
3. Onglet **Sécurité** → activer **DKIM**
4. Infomaniak génère automatiquement la clé et ajoute l'enregistrement DNS

**Vérification :** (après 15 min de propagation DNS)
```bash
dig TXT default._domainkey.wezea.net
# Doit retourner : v=DKIM1; k=rsa; p=...
```

---

### #4 — 2 sous-domaines orphelins (-6 pts)

**Risque** : `crm.wezea.net` et `intranet.wezea.net` n'ont plus de serveur — vulnérables au *subdomain takeover*.

**Action chez Infomaniak → DNS :**

Supprimer les enregistrements DNS suivants :
- `crm.wezea.net` (type A ou CNAME — n'a plus d'IP)
- `intranet.wezea.net` (type A ou CNAME — n'a plus d'IP)

**Vérification :**
```bash
dig A crm.wezea.net      # doit retourner NXDOMAIN
dig A intranet.wezea.net  # doit retourner NXDOMAIN
```

---

### #5 — Domaine expire dans 57 jours (2026-05-06) (-5 pts)

**Action immédiate chez Infomaniak :**

1. [Manager Infomaniak](https://manager.infomaniak.com) → **Domaines** → `wezea.net`
2. Cliquer **Renouveler maintenant** → payer 1 ou 2 ans
3. Activer le **renouvellement automatique** pour ne plus avoir ce risque

⚠️ Si le domaine expire, le site et les emails s'arrêtent instantanément.

---

## 🟡 LOW — Optimisations (sous 90 jours)

### #6 — Version nginx exposée (-3 pts) ✅ DÉJÀ CORRIGÉ

`server_tokens off;` ajouté dans `nginx-wezea.conf` et `nginx-scan.conf`.

**Déploiement sur le serveur :**
```bash
sudo cp infra/nginx-wezea.conf /etc/nginx/sites-available/wezea.net
sudo cp infra/nginx-scan.conf /etc/nginx/sites-available/scan.wezea.net
sudo nginx -t && sudo systemctl reload nginx
```

---

### #7 — Enregistrement CAA absent (-2 pts)

**Risque** : N'importe quelle autorité de certification peut émettre un certificat SSL pour votre domaine.

**Enregistrement DNS à ajouter chez Infomaniak :**

| Type | Nom | Valeur |
|------|-----|--------|
| CAA | `wezea.net` | `0 issue "letsencrypt.org"` |
| CAA | `wezea.net` | `0 issuewild ";"` (bloque les wildcards) |

**Vérification :**
```bash
dig CAA wezea.net
# doit retourner : wezea.net. 3600 IN CAA 0 issue "letsencrypt.org"
```

---

### #8 — MTA-STS non configuré (-2 pts) ✅ CONFIG CRÉÉE

Le fichier `infra/nginx-mta-sts.conf` est prêt. Déploiement en 3 étapes :

**Étape 1 — Ajouter les DNS chez Infomaniak :**

| Type | Nom | Valeur |
|------|-----|--------|
| A | `mta-sts.wezea.net` | `83.228.217.154` |
| TXT | `_mta-sts.wezea.net` | `v=STSv1; id=20260309000000` |

> ⚠️ Vérifier d'abord les vrais serveurs MX : `dig MX wezea.net`
> Adapter les lignes `mx:` dans `nginx-mta-sts.conf` si nécessaire.

**Étape 2 — Déployer nginx et obtenir le certificat SSL :**
```bash
# Sur le serveur :
sudo cp infra/nginx-mta-sts.conf /etc/nginx/sites-available/mta-sts.wezea.net
sudo ln -sf /etc/nginx/sites-available/mta-sts.wezea.net \
            /etc/nginx/sites-enabled/mta-sts.wezea.net
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d mta-sts.wezea.net
sudo systemctl reload nginx
```

**Étape 3 — Vérification :**
```bash
curl https://mta-sts.wezea.net/.well-known/mta-sts.txt
# Doit afficher : version: STSv1 / mode: enforce / mx: mail.infomaniak.com ...
```

---

## ℹ️ INFO — Sécurité SSH (port 22 ouvert)

**Pas de pénalité sur le score, mais bonne pratique à appliquer.**

**Sur le serveur, éditer `/etc/ssh/sshd_config` :**
```bash
sudo nano /etc/ssh/sshd_config
```

Modifier ou ajouter ces lignes :
```
PasswordAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
```

Redémarrer SSH :
```bash
sudo systemctl restart ssh
```

⚠️ **AVANT de désactiver les mots de passe** : s'assurer que votre clé SSH publique est bien dans `~/.ssh/authorized_keys` sur le serveur et que vous pouvez vous connecter avec.

**Optionnel — Fail2Ban (protection brute-force) :**
```bash
sudo apt install fail2ban
# Configuration par défaut protège SSH automatiquement
```

---

## 📊 Score estimé après toutes les corrections

| Action | Gain |
|--------|------|
| DMARC p=reject | +8 pts |
| DKIM configuré | +8 pts |
| Sous-domaines orphelins supprimés | +6 pts |
| Domaine renouvelé | +5 pts |
| Serveur header masqué ✅ | +3 pts |
| CAA ajouté | +2 pts |
| MTA-STS configuré ✅ | +2 pts |
| **Total estimé** | **41 + 34 = 75 pts** |

> Le typosquatting (-25 pts) est détecté mais hors de contrôle direct —
> enregistrer les TLDs principaux reste fortement recommandé pour la protection de marque.

---

## 🔢 Ordre de priorité résumé

1. **URGENT (cette semaine)** : Renouveler le domaine wezea.net · Acheter wezea.com
2. **IMPORTANT (2 semaines)** : DMARC p=quarantine → surveiller → p=reject · Configurer DKIM
3. **IMPORTANT (1 mois)** : Supprimer DNS orphelins · Déployer nginx server_tokens + MTA-STS
4. **OPTIMISATION (3 mois)** : Ajouter CAA · SSH clé uniquement · Fail2Ban
