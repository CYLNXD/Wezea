# Plan de remédiation sécurité — wezea.net
> Basé sur le rapport d'audit du 09/03/2026 · Score : 41/100 · Objectif : 85+/100
> Mis à jour le 09/03/2026 après vérification DNS manuelle

---

## ✅ Corrections déjà appliquées ou confirmées

| # | Finding | Statut | Détail |
|---|---------|--------|--------|
| 3 | DKIM non détecté (-8 pts) | ✅ DÉJÀ CONFIGURÉ | Délégation NS `_domainkey → nsany1.infomaniak.com` — Infomaniak gère les sélecteurs |
| 2 | DMARC p=none (-8 pts) | ✅ DÉJÀ CORRIGÉ | `p=reject; adkim=s; aspf=s; fo=1; pct=100` |
| 4 | Sous-domaines orphelins (-6 pts) | ✅ FAUX POSITIF | `crm.wezea.net` et `intranet.wezea.net` absents du DNS — détectés via crt.sh (certificats historiques) uniquement |
| 7 | Enregistrement CAA absent (-2 pts) | ✅ DÉJÀ CONFIGURÉ | `CAA 0 issue "letsencrypt.org"` + `CAA 0 issuewild ";"` présents |
| 6 | Version serveur exposée (-3 pts) | ✅ CORRIGÉ dans ce repo | `server_tokens off;` ajouté dans `nginx-wezea.conf` et `nginx-scan.conf` |
| 8 | MTA-STS non configuré (-2 pts) | ✅ CONFIG CRÉÉE | `nginx-mta-sts.conf` prêt avec MX corrigé (`mta-gw.infomaniak.ch`) |

> **Note DKIM** : Le scanner attendait un enregistrement TXT sur `_domainkey.wezea.net` (sans sélecteur spécifique).
> Infomaniak utilise une délégation NS : `_domainkey.wezea.net. IN NS nsany1.infomaniak.com.`
> Ce mécanisme est valide — les sélecteurs DKIM (ex: `default._domainkey.wezea.net`) sont gérés par Infomaniak directement.
> Vérification : `dig TXT default._domainkey.wezea.net` ou `dig TXT s1._domainkey.wezea.net`

> **Note sous-domaines orphelins** : Le scanner a trouvé `crm.wezea.net` et `intranet.wezea.net` dans les logs
> Certificate Transparency (crt.sh) — ces sous-domaines ont eu des certificats SSL par le passé mais n'ont
> JAMAIS eu d'enregistrements DNS A/CNAME actifs (ou ont été supprimés). Pas d'action requise.

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

---

## 🟠 MEDIUM — Action immédiate

### #5 — Domaine expire dans 57 jours (2026-05-06) (-5 pts)

**Action immédiate chez Infomaniak :**

1. [Manager Infomaniak](https://manager.infomaniak.com) → **Domaines** → `wezea.net`
2. Cliquer **Renouveler maintenant** → payer 1 ou 2 ans
3. Activer le **renouvellement automatique** pour ne plus avoir ce risque

⚠️ Si le domaine expire, le site et les emails s'arrêtent instantanément.

---

## 🟡 LOW — Déploiements serveur

### #6 — Version nginx exposée (-3 pts) ✅ CORRIGÉ dans ce repo

`server_tokens off;` ajouté dans `nginx-wezea.conf` et `nginx-scan.conf`.

**Déploiement sur le serveur :**
```bash
sudo cp infra/nginx-wezea.conf /etc/nginx/sites-available/wezea.net
sudo cp infra/nginx-scan.conf /etc/nginx/sites-available/scan.wezea.net
sudo nginx -t && sudo systemctl reload nginx
```

---

### #8 — MTA-STS non configuré (-2 pts) ✅ CONFIG CRÉÉE

Le fichier `infra/nginx-mta-sts.conf` est prêt.
MX configuré correctement : `mta-gw.infomaniak.ch` (vérifié via `dig MX wezea.net`).

**Étape 1 — Ajouter les DNS chez Infomaniak :**

| Type | Nom | Valeur |
|------|-----|--------|
| A | `mta-sts.wezea.net` | `83.228.217.154` |
| TXT | `_mta-sts.wezea.net` | `v=STSv1; id=20260309000001` |

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
# Doit afficher : version: STSv1 / mode: enforce / mx: mta-gw.infomaniak.ch ...
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

| Action | Gain | Statut |
|--------|------|--------|
| DMARC p=reject | +8 pts | ✅ DÉJÀ FAIT |
| DKIM configuré | +8 pts | ✅ DÉJÀ FAIT (NS delegation) |
| Sous-domaines orphelins | +6 pts | ✅ FAUX POSITIF |
| Domaine renouvelé | +5 pts | ⏳ À FAIRE |
| Serveur header masqué | +3 pts | ✅ DÉJÀ CORRIGÉ (à déployer) |
| CAA ajouté | +2 pts | ✅ DÉJÀ FAIT |
| MTA-STS configuré | +2 pts | ✅ CONFIG PRÊTE (à déployer) |
| **Total estimé** | **41 + 34 = 75 pts** | |

> Le typosquatting (-25 pts) est détecté mais hors de contrôle direct —
> enregistrer les TLDs principaux reste fortement recommandé pour la protection de marque.

> **Remarque** : Le score passera probablement à 75+ dès le prochain audit car DKIM/DMARC/CAA
> sont confirmés configurés — le scanner ne les avait pas détectés correctement.

---

## 🔢 Ordre de priorité résumé

1. **URGENT (cette semaine)** : Renouveler le domaine wezea.net · Acheter wezea.com
2. **DÉPLOIEMENT (1-2 jours)** : Copier nginx configs sur le serveur (server_tokens) · Déployer MTA-STS
3. **OPTIMISATION (3 mois)** : SSH clé uniquement · Fail2Ban
