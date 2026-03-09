# CLAUDE.md — Mémoire du projet CyberHealth Scanner
> Ce fichier est lu en PREMIER à chaque nouvelle session. Il doit être mis à jour à chaque modification importante.
> Dernière mise à jour : 2026-03-09 (session 33)

---

## 🗂️ Structure du projet

```
cyberhealth-scanner/
├── frontend/          # React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── pages/     # Dashboard, LoginPage, HistoryPage, AdminPage, ContactPage, LegalPage, ClientSpace, PublicScanPage
│       ├── components/ # PricingModal, etc.
│       └── index.css  # Variables CSS + classes skeuomorphiques globales
├── backend/           # FastAPI + SQLite + SQLAlchemy
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── auth.py            # JWT + argon2/bcrypt dual-context
│   │   ├── extra_checks.py    # Checks supplémentaires (doit être dans git !)
│   │   ├── app_checks.py      # AppAuditor — Application Scanning (8 catégories, lecture seule)
│   │   └── routers/
│   │       ├── auth_router.py
│   │       ├── payment_router.py
│   │       ├── scans_router.py
│   │       ├── monitoring_router.py
│   │       ├── webhook_router.py
│   │       ├── public_router.py
│   │       ├── admin_router.py
│   │       └── app_router.py        # Application Scanning CRUD + verify + scan
│   └── tests/         # Tests pytest (conftest, test_auth, test_scan_validation, test_rate_limit)
├── scripts/
│   └── backup_db.sh   # Script de sauvegarde SQLite avec rotation 30j
├── infra/
│   ├── cyberhealth-api.service  # Service systemd (uvicorn --workers 2)
│   └── cron-backup.example      # Exemple cron pour backup DB quotidien
├── .github/workflows/deploy.yml  # CI/CD GitHub Actions (self-hosted runner)
├── requirements.txt   # Backend Python deps
└── CLAUDE.md          # CE FICHIER
```

---

## 🖥️ Infrastructure & Déploiement

- **Hébergeur** : Infomaniak VPS Lite (migré 2026-03-07, ancien : self-hosted)
- **OS** : Ubuntu 24.04 LTS — Python **3.12** (pas 3.11 — non disponible par défaut sur 24.04)
- **IP publique** : `83.228.217.154`
- **Runner CI/CD** : GitHub Actions self-hosted runner (`/home/cyberhealth/actions-runner/`)
- **Chemin serveur** : `/home/cyberhealth/app/`
- **Virtualenv** : `.venv/` (avec le point) — utilisé à la fois par le CI/CD (`pip install`) ET par le service systemd
  - ⚠️ Ancienne confusion : le service référençait `venv/` (sans le point) → packages manquants en prod → **corrigé le 2026-03-08**
- **Process manager** : systemd + uvicorn (`--workers 2` — optimal pour 2 vCPU + SQLite)
- **Frontend** : build Vite → servi par nginx (`/home/cyberhealth/app/frontend/dist/`)
- **Backend** : FastAPI sur uvicorn, port 8000

### Domaines & DNS
| Domaine | Rôle | Pointe vers |
|---------|------|-------------|
| `wezea.net` | Frontend | `83.228.217.154` |
| `www.wezea.net` | Frontend (redirect) | `83.228.217.154` |
| `scan.wezea.net` | API backend | `83.228.217.154` |

### Variables d'environnement — `.env` backend
Fichier : `/home/cyberhealth/app/backend/.env`, propriétaire `cyberhealth`
⚠️ Le service systemd lit **`backend/.env`** (EnvironmentFile dans cyberhealth-api.service) — ne pas éditer `/home/cyberhealth/app/.env` qui n'est PAS lu par le service.
```bash
API_ENV=production
SECRET_KEY=<secrets.token_hex(32)>
RATE_LIMIT=20/minute
CORS_ORIGINS=https://wezea.net,https://scan.wezea.net,http://localhost:3000
SCAN_TIMEOUT_SEC=8
SSL_EXPIRY_WARNING_DAYS=30

# Email — Brevo
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=<depuis Brevo SMTP settings — onglet "SMTP & API">
SMTP_PASS=<depuis Brevo SMTP settings — onglet "SMTP & API">
FROM_NAME=CyberHealth Scanner
FROM_EMAIL=contact@wezea.net
BREVO_API_KEY=<depuis Brevo API Keys>

# Auth
GOOGLE_CLIENT_ID=307486238342-aagbmcb5ia7f8mod8ltmlogd916lgkrc.apps.googleusercontent.com
JWT_SECRET_KEY=<openssl rand -hex 32>   # STABLE — ne pas changer, déconnecte tous les users

# Stripe
STRIPE_SECRET_KEY=<depuis Stripe Developers → API keys>
STRIPE_PUBLISHABLE_KEY=<depuis Stripe Developers → API keys>
STRIPE_WEBHOOK_SECRET=<depuis Stripe Developers → Webhooks → Signing secret>
STRIPE_STARTER_PRICE_ID=price_1T7BaSKOrtMvErGvXlh4JA44
STRIPE_PRO_PRICE_ID=price_1T7BaVKOrtMvErGv17gX79zw
STRIPE_DEV_PRICE_ID=price_1T8MpWKOrtMvErGv0iXhORaP

# Frontend
FRONTEND_URL=https://wezea.net
```

### Variables d'environnement — `.env.production` frontend
Fichier : `/home/cyberhealth/app/frontend/.env.production` (NON dans git — à recréer à chaque migration)
```bash
VITE_API_URL=https://scan.wezea.net
VITE_GOOGLE_CLIENT_ID=307486238342-aagbmcb5ia7f8mod8ltmlogd916lgkrc.apps.googleusercontent.com
```
**⚠️ Après toute modification de ce fichier, rebuilder le frontend :**
```bash
sudo -u cyberhealth bash -c "cd /home/cyberhealth/app/frontend && npm run build"
```

### Nginx — Content-Security-Policy complète
Fichier : `/etc/nginx/sites-available/wezea.net`
La CSP complète à utiliser dans le bloc `wezea.net` (frontend) :
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://us-assets.i.posthog.com https://internal-j.posthog.com https://f.wezea.net https://accounts.google.com https://ssl.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com https://f.wezea.net; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://f.wezea.net https://lh3.googleusercontent.com; connect-src 'self' https://scan.wezea.net https://f.wezea.net https://accounts.google.com https://us.posthog.com https://internal-j.posthog.com https://us-assets.i.posthog.com; frame-src https://accounts.google.com; worker-src blob:;" always;
```

### sudoers — permissions cyberhealth
Le runner CI/CD et le déploiement ont besoin de sudo limité :
```
cyberhealth ALL=(ALL) NOPASSWD: /bin/systemctl restart cyberhealth-api, /bin/systemctl reload nginx
```

### Points critiques du deploy.yml
```yaml
rsync --exclude='.venv/' --exclude='venv/' --exclude='*.db' --exclude='*.sqlite'
      --exclude='uploads/' --exclude='logs/'
# IMPORTANT : .venv/ avec le point ! rsync --delete détruirait autrement le venv
pip: utiliser .venv/bin/pip (pas pip global)
# Les tests backend s'exécutent AVANT le déploiement (étape 4)
```

### GitHub Actions Runner
- **Emplacement** : `/home/cyberhealth/actions-runner/`
- **Service** : `actions.runner.CYLNXD-Wezea.ov-ac0014.service`
- **Commandes** :
```bash
sudo systemctl status actions.runner.CYLNXD-Wezea.ov-ac0014
sudo systemctl restart actions.runner.CYLNXD-Wezea.ov-ac0014
# Réinstaller si besoin (nouveau token depuis github.com/CYLNXD/Wezea/settings/actions/runners/new) :
cd /home/cyberhealth/actions-runner && sudo ./svc.sh uninstall
# Puis reconfigurer avec ./config.sh --url ... --token ...
sudo ./svc.sh install cyberhealth && sudo ./svc.sh start
```

### Backup de la DB
```bash
# Installé sur le serveur (cron cyberhealth) :
# 0 2 * * * /home/cyberhealth/app/scripts/backup_db.sh >> /home/cyberhealth/app/logs/backup.log 2>&1

# Variables d'env optionnelles :
# BACKUP_DIR=/home/cyberhealth/backups  (défaut)
# RETENTION=30                          (jours de rétention)
# S3_BUCKET=s3://mon-bucket/backups/    (optionnel)
```

### Opérations DB courantes
```bash
# Accéder à la DB (toujours en tant que cyberhealth) :
sudo -u cyberhealth sqlite3 /home/cyberhealth/app/backend/cyberhealth.db

# ⚠️ Nom correct de la table rate limit : scan_rate_limits (PLURIEL)
# Vider les quotas anonymes du jour (utile pour les tests) :
sudo -u cyberhealth sqlite3 /home/cyberhealth/app/backend/cyberhealth.db \
  "DELETE FROM scan_rate_limits WHERE date_key = date('now');"

# Voir les tables :
sudo -u cyberhealth sqlite3 /home/cyberhealth/app/backend/cyberhealth.db ".tables"

# Voir les migrations :
sudo -u cyberhealth sqlite3 /home/cyberhealth/app/backend/cyberhealth.db \
  "SELECT * FROM db_migrations ORDER BY id;"
```

---

## 👤 Comptes importants

| Email | Rôle | Plan | Notes |
|-------|------|------|-------|
| `ceylan.top@gmail.com` | Propriétaire | Starter | Lié à Stripe, restauré après wipe DB |
| `wezea.app@gmail.com` | Admin | Pro | `is_admin=1, plan='pro'` en DB |

---

## 🎨 Système de design — Skeuomorphique

Toutes les pages doivent utiliser ces classes CSS définies dans `index.css` :

| Classe | Usage |
|--------|-------|
| `.sku-panel` | Panneaux principaux (fond sombre avec bordure subtile) |
| `.sku-card` | Cartes de contenu |
| `.sku-inset` | Inputs, textareas, selects (aspect enfoncé) |
| `.sku-stat` | Blocs statistiques |
| `.sku-btn-primary` | Bouton principal cyan/bleu |
| `.sku-btn-ghost` | Bouton secondaire transparent |

**IMPORTANT** : Ne pas mettre de `backgroundColor` solide sur les wrappers de pages — cela cache les radial-gradients du `body` définis dans `index.css`.

**IMPORTANT** : Le body a `background-attachment: fixed` — les gradients sont fixés au viewport. Ne pas retirer cette propriété, sinon les gradients deviennent invisibles sur les pages longues.

### 🔲 Pattern SkuIcon — boîte d'icône skeuomorphique

**TOUJOURS utiliser ce pattern** pour toute icône non-inline (en-têtes de section, notices, paywalls, cards). Reproduire l'implémentation ci-dessous à chaque nouvel usage.

```tsx
// Composant SkuIcon — à copier dans chaque fichier qui en a besoin
// color : hex de la couleur thématique (voir palette ci-dessous)
function SkuIcon({ children, color, size = 36 }: { children: ReactNode; color: string; size?: number }) {
  const r = Math.round(size * 0.28);
  return (
    <div className="shrink-0 flex items-center justify-center relative overflow-hidden"
      style={{
        width: size, height: size, borderRadius: r,
        background: `linear-gradient(150deg, ${color}30 0%, ${color}0d 100%)`,
        border: `1px solid ${color}40`,
        boxShadow: `0 4px 16px ${color}22, 0 1px 3px rgba(0,0,0,0.4), inset 0 1px 0 ${color}30, inset 0 -1px 0 rgba(0,0,0,0.3)`,
      }}
    >
      {/* Reflet supérieur — NE PAS OMETTRE */}
      <div className="absolute inset-0 pointer-events-none"
        style={{ borderRadius: r, background: 'linear-gradient(180deg,rgba(255,255,255,0.07) 0%,transparent 50%)' }} />
      {children}
    </div>
  );
}
```

**Palette de couleurs thématiques :**

| Contexte | Couleur hex | Classe Lucide |
|----------|-------------|---------------|
| Info / compte / cyan | `#22d3ee` | `text-cyan-300` |
| Sécurité / auth | `#818cf8` | `text-indigo-300` |
| API / intégration | `#a78bfa` | `text-violet-300` |
| Danger / suppression | `#f87171` | `text-red-300` |
| Succès / validation | `#4ade80` | `text-green-300` |
| Avertissement | `#fbbf24` | `text-amber-300` |
| Pro / premium | `#a78bfa` | `text-violet-300` |
| Scan / analyse | `#22d3ee` | `text-cyan-300` |

**Tailles recommandées :**
- `size={32}` — notices inline, petites cards
- `size={36}` — en-têtes de section (usage principal)
- `size={44}` — paywalls, éléments hero d'une section
- `size={52}` — éléments centraux (ex : paywall sans header au-dessus)

**Règle** : les icônes dans les **boutons** (Save, Lock, Trash2…) restent sans SkuIcon — elles font partie du bouton lui-même. Seules les icônes **standalone** (section headers, notices, cards, paywalls) utilisent SkuIcon.

### Pages stylisées (skeuomorphique ✅)
- `Dashboard.tsx` ✅
- `LoginPage.tsx` ✅
- `HistoryPage.tsx` ✅
- `AdminPage.tsx` ✅
- `ContactPage.tsx` ✅
- `LegalPage.tsx` ✅
- `ClientSpace.tsx` ✅
- `PricingModal.tsx` ✅
- `ProfileModal.tsx` ✅ (SkuIcon dans tous les en-têtes de section + notices)
- `PublicScanPage.tsx` ✅ (page publique /r/{uuid}, pas de skeu — style épuré)

---

## 🔧 Bugs résolus (historique)

### CI/CD
- **Service 203/EXEC** : rsync `--delete` supprimait `.venv/` → ajout `--exclude='.venv/'`
- **`pip: command not found`** : idem + gunicorn manquant → ajouté `gunicorn==23.0.0` dans requirements.txt
- **`No module named 'app.extra_checks'`** : fichier était dans `.gitignore` → retiré du gitignore
- **DB wipée à chaque deploy** : `*.db` non exclus du rsync → ajout `--exclude='*.db'`

### Backend
- **Rate limit 429 global** : uvicorn derrière nginx sans `--proxy-headers` → `request.client.host = 127.0.0.1` pour tous → compteur IP partagé entre tous les anonymes → bloqué après 5 scans au total. Fix : `_get_real_ip()` dans `main.py` lit `X-Real-IP` puis `X-Forwarded-For`, + `--proxy-headers --forwarded-allow-ips=127.0.0.1` dans `cyberhealth-api.service`
- **bcrypt/passlib incompatible** : bcrypt 4.x+ refuse passwords > 72 bytes → `bcrypt==4.0.1`
- **`is_admin` absent après reload** : `UserResponse` Pydantic n'avait pas le champ → ajouté
- **Stripe résilience** : après wipe DB, `metadata.user_id` devenait invalide → résolution par `stripe_customer_id` > email > metadata
- **login_failures dict non partagé entre workers** : remplacé par table `login_attempts` en DB (2026-03-06)
- **`None` crash dans `_derive_checks_overview`** : `data.get("dns_details", {})` retourne `None` quand la clé existe mais vaut `None` → ajouté `or {}` : `dns_det = data.get("dns_details", {}) or {}`
- **`None` crash dans `_build_context` (report_service.py ligne 307)** : `dict(data.get("dns_details", {}))` idem — clé existante mais valeur `None` → `TypeError: 'NoneType' object is not iterable` → ajouté `or {}` pour dns_det, ssl_det, port_det
- **Plan `dev` sans auditors premium** : `scanner.py` avait `plan in ("starter", "pro")` pour instancier SubdomainAuditor et VulnVersionAuditor — `dev` exclu → les utilisateurs Dev n'avaient aucun résultat de sous-domaines ou versions vulnérables. Fix : `("starter", "pro", "dev")` aux 2 endroits concernés.

### Frontend
- **Scan anonyme → page d'accueil au lieu des résultats** : double cause : (1) `AuthContext.fetchMe` appelait `logout()` sur catch → `window.location.href = '/'` en cas de token expiré. (2) Sur erreur 429, `useScanner` attendait 4800ms de simulation inutile + aucun `scrollIntoView` sur status `'error'` → le ScanConsole qui disparaît réduisait la page et remontait l'utilisateur sur le hero. Fix : retrait du redirect dans fetchMe + fast-fail 800ms sur erreur + scroll sur `'error'` comme sur `'success'`
- **"Créer un compte" ouvrait onglet "Connexion"** : `onGoRegister?.() ?? onGoLogin?.()` — les fonctions void retournent `undefined`, le `??` déclenchait toujours le fallback → remplacé par `if (onGoRegister) { onGoRegister(); } else { onGoLogin?.(); }`
- **Build TS** : `<select>` dans ContactPage avait deux attributs `style` → fusionnés
- **"hebdomadaire" → "journalière"** : message de limite quota corrigé
- **Gradients invisibles sur pages longues** : positions `0%`/`100%` hors viewport en scroll → `background-attachment: fixed` + positions `15%`/`85%` dans `index.css`
- **⚠️ Grille cyber sur pages secondaires** : NE PAS RETENTER — impossible à faire via CSS global (stacking contexts) ou App.tsx (fixed piégé). Seul endroit qui fonctionne : inside hero section du Dashboard (absolute dans relative overflow-hidden).

---

## 📦 Dépendances clés

### Backend (`requirements.txt`)
```
fastapi==0.115.5
uvicorn[standard]==0.32.1
gunicorn==23.0.0          # Requis pour systemd
sqlalchemy==2.0.36
bcrypt==4.0.1             # PINNÉ — 4.2+ incompatible passlib 1.7.4
passlib[bcrypt]==1.7.4
argon2-cffi==23.1.0       # Migration transparente bcrypt → argon2 (rehash au prochain login)
python-jose
stripe
apscheduler==3.10.4
sentry-sdk[fastapi]
pytest + pytest-asyncio   # Tests backend (lancés avant chaque déploiement CI)
```

### Frontend
- React + TypeScript + Vite
- Tailwind CSS
- Framer Motion
- Lucide React

---

## 🏗️ Architecture Backend — Points importants

### `database.py`
- Utilise `_add_column_if_missing()` pour les migrations SQLite (pas d'Alembic)
- **Migrations versionnées** : table `db_migrations(version, applied_at)` — chaque migration ne s'applique qu'une seule fois
- Migrations actuelles : 001 à 008 (voir database.py)

### `models.py`
- `User` model : `stripe_customer_id`, `wb_*` (white-branding), `api_key`
- `ScanHistory` : `public_share BOOLEAN` → active le lien /r/{uuid}
- `LoginAttempt` : remplace le dict in-memory `_login_failures` → partagé entre workers
- `MonitoredDomain` : `scan_frequency`, `email_report`, surveillance élargie

### `auth.py`
- `CryptContext(schemes=["argon2", "bcrypt"], deprecated=["bcrypt"])`
- Nouveaux mots de passe → argon2
- Anciens hashes bcrypt → vérifiés et rehashés en argon2 au prochain login
- `needs_rehash(hash)` → appelé dans `auth_router.login()` après login réussi
- JWT : `JWT_SECRET_KEY` doit être défini dans `.env` (≥32 chars). Si absent, warning stderr + secret temporaire généré.

### `auth_router.py`
- Login lockout → table `login_attempts` en DB (fenêtre 15 min, max 5 échecs)
- `_check_lockout(ip, db)`, `_record_failure(ip, db)`, `_clear_failures(ip, db)` prennent maintenant la session DB
- Rehash argon2 transparent après login bcrypt réussi

### `payment_router.py`
- Résolution user depuis Stripe webhook : `stripe_customer_id` → email → `metadata.user_id`
- Sauvegarde `stripe_customer_id` sur `checkout.session.completed`

### `scans_router.py`
- `GET /scans/history/{uuid}/export?format=json|csv` → export des scans (Starter + Pro)
- `PATCH /scans/history/{uuid}/share` → toggle `public_share`
- `GET /scans/history` retourne maintenant `public_share: bool` par scan

### `public_router.py`
- `GET /public/scan/{uuid}` → rapport public si `public_share=True` (sans auth)
- `GET /public/badge/{domain}` → badge SVG dynamique
- `GET /public/stats` → stats anonymisées + `industry_avg` (moyenne réelle si ≥ 50 scans, sinon baseline 70) + `avg_source` ("real" | "baseline")

### `main.py` — `_get_real_ip(request)`
- Lit `X-Real-IP` (nginx) puis `X-Forwarded-For` avant de tomber sur `request.client.host`
- **Critique** : sans ça, tous les anonymes partagent le bucket IP `127.0.0.1`
- Remplace les anciens appels `get_remote_address(request)` dans `/scan` et `/scan/limits`

---

## 🧪 Tests

```bash
cd backend
.venv/bin/pytest tests/ -v --tb=short

# Variables d'env requises :
# JWT_SECRET_KEY=test-secret-key-for-ci-only-32chars
# CORS_ORIGINS=http://testserver
```

Fichiers : `tests/conftest.py`, `test_auth.py`, `test_scan_validation.py`, `test_rate_limit.py`, `test_report_service.py`, `test_monitoring.py`

### `test_report_service.py` — formats de données importants
```python
# SSL : utiliser status/tls_version/days_left (PAS valid/protocols)
"ssl_details": {"status": "valid", "tls_version": "TLSv1.3", "days_left": 90}
# Ports : dict par numéro de port (PAS open_ports list)
"port_details": {"443": {"open": True}, "3389": {"open": False}}
# DNS : status + champ spécifique (policy pour DMARC, records pour SPF)
"dns_details": {"spf": {"status": "ok"}, "dmarc": {"status": "ok", "policy": "reject"}}
```

---

## 🔒 Opérations serveur — Post-déploiement

### Installer le cron de backup DB (une seule fois)
```bash
sudo crontab -u cyberhealth -e
# Ajouter :
0 2 * * * /home/cyberhealth/app/scripts/backup_db.sh >> /home/cyberhealth/app/logs/backup.log 2>&1
```

### Vérifier les backups
```bash
ls -lh /home/cyberhealth/backups/
```

---

## 🆕 Fonctionnalités récentes (2026-03-06, session 3)

### Auth — Mot de passe oublié / Réinitialisation
- **Backend** : `POST /auth/forgot-password` + `POST /auth/reset-password`
  - Migration DB 009 : colonnes `password_reset_token`, `password_reset_expires` sur `users`
  - Token `secrets.token_urlsafe(32)`, durée 1h, usage unique, timezone-safe (SQLite)
  - Anti-énumération : retourne toujours 200 (même si l'email est inconnu)
  - Comptes Google exclus (`!google:` hash → pas de mot de passe local)
  - Email envoyé via `send_password_reset_email()` dans `brevo_service.py`
  - Reset URL : `{FRONTEND_URL}/?reset_token={token}`
- **Frontend** :
  - `App.tsx` : détecte `?reset_token=xxx` → ouvre LoginPage en mode reset + nettoie l'URL
  - `LoginPage.tsx` : 4 sous-vues animées (`AnimatePresence`) :
    - `forgot` : formulaire email → POST /auth/forgot-password
    - `forgot-sent` : confirmation (mention vérifier les spams)
    - `reset` : formulaire nouveau mdp + confirmation → POST /auth/reset-password
    - `reset-done` : succès + bouton "Se connecter"
  - Lien "Mot de passe oublié ?" discret sous le formulaire login (mode `isLogin` uniquement)
- **Tests** : 8 nouveaux tests (73 total), fixture `db_user` pour éviter le rate limit `/register`

## 🆕 Migration VPS Infomaniak (2026-03-07, session 28)

### Migration self-hosted → Infomaniak VPS Lite

#### Étapes réalisées
1. Création VPS (Ubuntu 24.04, 2 vCPU, IP `83.228.217.154`)
2. `sudo apt install python3.12 python3.12-venv nodejs npm nginx certbot python3-certbot-nginx`
3. Création user `cyberhealth` + clone repo dans `/home/cyberhealth/app/`
4. Création venv `.venv` + `pip install -r requirements.txt`
5. Création `/home/cyberhealth/app/.env` (JWT, Google, Stripe, Brevo…)
6. Création `/home/cyberhealth/app/frontend/.env.production` (VITE_API_URL + VITE_GOOGLE_CLIENT_ID)
7. Installation service systemd `cyberhealth-api`
8. Build frontend (`npm run build`)
9. Config nginx avec CSP complète + SSL Let's Encrypt (3 domaines)
10. Migration DB : SCP de l'ancien serveur → Mac → nouveau VPS
11. GitHub Actions runner → `/home/cyberhealth/actions-runner/` (service systemd)
12. Cron backup DB + JWT stable + sudoers cyberhealth

#### Bugs découverts pendant la migration

- **`python3.11` absent sur Ubuntu 24.04** : utiliser `python3.12` et `python3.12-venv`
- **Permission denied nginx sur `/home/cyberhealth/dist/`** : `sudo chmod o+x /home/cyberhealth /home/cyberhealth/app /home/cyberhealth/app/frontend /home/cyberhealth/app/frontend/dist`
- **Certbot timeout** : firewall Infomaniak bloquait ports 80/443 → ajouter règles TCP 80+443 dans le panneau VPS Infomaniak
- **nginx `conflicting server name scan.wezea.net`** : certbot ajoutait un bloc dans `/etc/nginx/sites-enabled/default` → `sudo rm /etc/nginx/sites-enabled/default`
- **Frontend appelait `localhost:8000`** : `.env.production` absent du repo → créer manuellement sur le serveur après chaque migration, puis rebuilder
- **CSP incomplète** : la CSP doit inclure PostHog (`f.wezea.net`, `us.posthog.com`, `us-assets.i.posthog.com`, `internal-j.posthog.com`), Google Fonts, Google Sign-In (`accounts.google.com`, `ssl.gstatic.com`) — voir section nginx ci-dessus
- **`scan_rate_limits` (PLURIEL)** : le nom de la table SQLite est `scan_rate_limits` et non `scan_rate_limit` — erreur fréquente dans les requêtes manuelles
- **sqlite3 nécessite `sudo -u cyberhealth`** : la DB est en lecture seule pour `ubuntu` — toujours utiliser `sudo -u cyberhealth sqlite3 ...`
- **GitHub Actions runner dans `/home/ubuntu/`** : le service tourne en tant que `cyberhealth` qui n'a pas accès à `/home/ubuntu/` → déplacer dans `/home/cyberhealth/actions-runner/` + `chown -R cyberhealth:cyberhealth`
- **`VITE_GOOGLE_CLIENT_ID` manquant** : le bouton Google Sign-In n'apparaît pas si cette variable est absente de `.env.production` → à recréer à chaque migration
- **Mauvais fichier `.env`** : le service lit `/home/cyberhealth/app/backend/.env` (défini dans `EnvironmentFile` du service systemd), PAS `/home/cyberhealth/app/.env` — toujours éditer `backend/.env`

---

## 🆕 Fonctionnalités récentes (2026-03-09, session 32)

### Rapport PDF — 3 améliorations

#### 1. Couverture dynamique selon le niveau de risque
- **`report_service.py`** : `_build_context` ajoute `cover_gradient` au contexte :
  - CRITICAL → rouge foncé `#0f172a → #7f1d1d → #450a0a`
  - HIGH → orange foncé `#0f172a → #7c2d12 → #431407`
  - MEDIUM → bleu (inchangé) `#0f172a → #1e3a8a → #312e81`
  - LOW → vert foncé `#0f172a → #14532d → #052e16`
- **`report_template.html`** : `.cover` background appliqué via `style="{{ cover_gradient }}"`, bande `cover-risk-stripe` au bas en `risk_color`

#### 2. One-pager dirigeant (page 2 visuelle)
- Nouvelle page `@page onepager` insérée entre la couverture et la Synthèse
- Score géant (88pt) + niveau de risque pill colorée
- Grille 2 colonnes : Top 5 risques CRITICAL/HIGH (gauche) / Top 5 actions prioritaires (droite)
- KPIs en bas : Critiques / Élevées / Modérées / Checks OK / Score / Moy. PME

#### 3. Nouveaux checks dans le plan d'action
- **`report_service.py`** — 16 nouvelles entrées `FINDING_ACTIONS` :
  - DNSSEC, CAA → optimize
  - PFS manquant, cipher faible, clé courte → important
  - HTTP→HTTPS absent, domaine expiré/expire → urgent
  - MTA-STS, Permissions-Policy → optimize

#### Tests (+17 tests)
- `TestBuildActionPlan` : 12 tests pour nouveaux checks
- `TestBuildContext` : 6 tests pour `cover_gradient` (LOW/CRITICAL/HIGH/MEDIUM/UNKNOWN/présence)

---

## 🆕 Fonctionnalités récentes (2026-03-09, session 33)

### Feature — Dashboard Monitoring Enrichi (alertes configurables + digest hebdomadaire)

#### 1. Seuil SSL configurable par domaine
- **`backend/app/models.py`** : colonne `ssl_alert_days = Column(Integer, default=30)` sur `MonitoredDomain`
- **`backend/app/database.py`** : migration `012_monitoring_alert_config` — `ALTER TABLE monitored_domains ADD COLUMN ssl_alert_days INTEGER DEFAULT 30`
- **`backend/app/scheduler.py`** : `ssl_threshold = monitored.ssl_alert_days or 30` remplace le hardcode 30j — alerte urgente si ≤7j, alerte warning si ≤ssl_threshold
- **`frontend/src/pages/ClientSpace.tsx`** : select avec options 7/14/30/60 jours → appel PATCH `/monitoring/domains/{d}`

#### 2. Préférences d'alertes par type
- **`backend/app/models.py`** : colonne `alert_config = Column(Text, nullable=True)` + `DEFAULT_ALERT_CONFIG` dict + `get_alert_config()` méthode avec fallback
- **`backend/app/routers/monitoring_router.py`** : `UpdateDomainRequest.alert_config: Optional[dict]` — sanitisation des clés autorisées uniquement ; `DomainResponse.alert_config_parsed` (dict décodé) retourné dans GET
- **`backend/app/scheduler.py`** : `alert_cfg = monitored.get_alert_config()` — chaque type d'alerte (score_drop, critical_findings, ssl_expiry, port_changes, tech_changes) contrôlé individuellement
- **`frontend/src/pages/ClientSpace.tsx`** : section `<details>` expandable avec 5 checkboxes dans la ligne de config de chaque domaine

#### 3. Résumé hebdomadaire par email (digest lundi 07:30 UTC)
- **`backend/app/services/brevo_service.py`** : `send_weekly_monitoring_digest(email, first_name, domains)` — email sombre avec tableau Domaine/Score/Risque/SSL/Dernier scan, tri par priorité (CRITICAL/HIGH en premier), compteur "X domaine(s) nécessitent votre attention"
- **`backend/app/scheduler.py`** : `run_weekly_digest()` + `_async_weekly_digest()` — récupère tous les users avec domaines actifs, agrège les données, envoie le digest
- **Planification** : `CronTrigger(day_of_week="mon", hour=7, minute=30)` enregistré dans `start_scheduler()`

#### Tests (inclus dans 1095 tests, 0 échec)
- `test_monitoring.py` : `test_patch_ssl_alert_days`, `test_patch_ssl_alert_days_clamped`, `test_patch_alert_config`, `test_patch_alert_config_sanitizes_unknown_keys`
- `test_scheduler.py` : `TestWeeklyDigest` (5 tests) : domaines agrégés, données correctes, error silencieux, run_weekly_digest
- `test_brevo_service.py` : `TestSendWeeklyMonitoringDigest` (5 tests) : tri priorité, HTML contenu, no API key → False
- `test_database.py` : `012_monitoring_alert_config` dans la liste des migrations

---

## 🆕 Fonctionnalités récentes (2026-03-09, session 31)

### Feature — Onboarding wizard post-inscription

#### Architecture
- **`frontend/src/components/OnboardingWizard.tsx`** (nouveau) — Modal overlay plein-écran affiché une seule fois après la première connexion
  - 3 étapes animées (Framer Motion, `mode="wait"`) : Bienvenue → Scanner votre domaine → Prochaines étapes
  - Détection "nouveau compte" : `localStorage.getItem(`wezea_onboarding_done_${user.id}`)` — vide au 1er login
  - Fermeture : `localStorage.setItem(key, '1')` → ne réapparaît jamais pour cet userId
  - Style skeuomorphique : `.sku-panel`, `SkuIcon`, `.sku-btn-primary`, `.sku-inset`
  - StepDots indicator en haut du modal

- **Étape 1 — Bienvenue** :
  - Icône Shield cyan, salutation personnalisée (prénom ou partie email avant @)
  - 3 feature cards : Analyse complète / Surveillance continue / Rapport PDF
  - CTA "Commencer — scanner mon domaine"

- **Étape 2 — Scanner votre domaine** :
  - Input domain avec validation regex + nettoyage du protocole/www
  - Bouton "Lancer l'analyse" → ferme le wizard + lance le scan sur le Dashboard
  - Exemples cliquables (`exemple.fr`, `mon-shop.com`, `startup.io`)
  - Lien "Explorer les fonctionnalités →" pour passer à l'étape 3

- **Étape 3 — Prochaines étapes** :
  - 3 boutons : Dashboard (ferme) / Surveillance (→ ClientSpace tab monitoring) / Plans (→ ClientSpace tab billing)

- **`frontend/src/pages/Dashboard.tsx`** — Modifications :
  - Import `OnboardingWizard`
  - State `onboardingOpen`
  - `useEffect` sur `user?.id` → vérifie le flag localStorage → `setOnboardingOpen(true)`
  - `closeOnboarding()` → setItem + setState
  - `handleOnboardingScan(domain)` — défini **après** `handleSubmit` (évite TDZ) → ferme wizard + lance scan
  - `<AnimatePresence>` + `<OnboardingWizard ...>` en bas du JSX (avant `</div>` final)

#### Comportement
- Affiché uniquement si `user !== null && !localStorage[key]` (après login/register)
- Clique sur l'overlay ferme le wizard
- Bouton X (coin haut-droit) ferme le wizard
- "Passer l'introduction" lien discret sur l'étape 1
- Scan depuis le wizard : ferme le modal + pré-remplit le champ + lance `scanner.startScan()`

#### Build
- TypeScript build : ✅ 0 erreur
- Bundle : 442 kB JS (+0 — composant inclus dans le bundle principal)

---

## 🆕 Fonctionnalités récentes (2026-03-09, session 30)

### Nouveaux checks de sécurité — scanner.py + extra_checks.py

#### 8 nouvelles catégories de vérifications

**`scanner.py` — Ports dangereux + DNS avancé + TLS avancé**

- **Ports exposés critiques** : ajout de Docker-API (2375), Redis (6379), Elasticsearch (9200), MongoDB (27017) dans `MONITORED_PORTS` — chacun génère un finding CRITICAL p=30 indépendant (vs grouped penalty précédent)
  - `PENALTY_TABLE["exposed_service"] = 30`
  - Block `_analyze_open_ports` : findings individuels avec titre et explication spécifique par service

- **DNSSEC** (`DNSAuditor._check_dnssec()`) : requête DNSKEY — LOW p=3 si absent
- **CAA** (`DNSAuditor._check_caa()`) : requête CAA — LOW p=2 si absent

- **TLS — Perfect Forward Secrecy** (dans `_check_ssl()`) :
  - TLS 1.3 → always PFS (mandaté par la spec)
  - TLS 1.2 : vérifie que le cipher name commence par ECDHE/DHE/EDH → MEDIUM p=8 si absent
  - Fix critique : `has_pfs = (tls_ver == "TLSv1.3") or any(...)` — TLS 1.3 ciphers comme `AES256-GCM-SHA384` n'ont pas le préfixe ECDHE dans le nom mais utilisent ECDHE en interne

- **TLS — Bits de clé faibles** (dans `_check_ssl()`) : `cipher[2] < 128` → HIGH p=15

- **TLS — Ciphers faibles** (`SSLAuditor._check_weak_ciphers()`) :
  - Tente une connexion SSL avec `3DES:DES:RC4:EXPORT:NULL:!aNULL`
  - HIGH p=12 si le serveur accepte
  - Silencieux si OpenSSL local ne supporte pas ces ciphers

**`extra_checks.py` — Headers + HTTP→HTTPS + MTA-STS + Domain Expiry**

- **Permissions-Policy** (dans `HttpHeaderAuditor._get_security_headers()`) : LOW p=2 si absent
- **HTTP→HTTPS redirect** (`HttpHeaderAuditor._check_http_redirect()`) : connexion port 80 → HIGH p=10 si pas de redirect 3xx vers https://
- **MTA-STS** (`EmailSecurityAuditor._check_mta_sts()`) : query TXT `_mta-sts.{domain}` → LOW p=2 si absent (et seulement si MX présent)
- **DomainExpiryAuditor** (nouvelle classe) : requête RDAP `https://rdap.org/domain/{root}` — CRITICAL p=50 si expiré, CRITICAL p=30 si <14j, HIGH p=15 si <30j, MEDIUM p=5 si <60j
  - Ajouté à `AuditManager.all_base` → disponible tous plans
  - Extrait le root domain (`parts[-2:]`) pour éviter les requêtes sur sous-domaines

#### Mise à jour tests (1070 tests → 1078, 0 échec)
- `_all_auditor_patches()` : ajout `DomainExpiryAuditor` mock, compteur 7→8
- `_ALL_SECURE_HEADERS` fixture : ajout `Permissions-Policy`
- `TestSSLAuditor::test_valid_cert_no_findings` : mock `("AES256-GCM-SHA384", "TLSv1.3", 256)` — fix PFS TLS 1.3

### Fix — Faux positifs sur tous les checks existants

#### Corrections appliquées
- **DMARC sur sous-domaine** : `_check_dmarc` utilise maintenant `_dmarc.{root_domain}` — même fix que DNSSEC/CAA
  - `_add_dmarc_missing_finding(root)` accepte un param optionnel pour afficher le vrai domaine dans le détail
- **WordPress substring trop large** : patterns spécifiques uniquement (`/wp-content/`, `/wp-json/`, `wordpress.org`, `content=['"]wordpress`, `wp-login.php`)
- **Drupal substring trop large** : patterns spécifiques (`drupal.js`, `/sites/default/files/`, `data-drupal`, `content=['"]drupal`, `X-Drupal-*` headers)
- **`_check_http_redirect` en CI** : mock `_check_http_redirect` ajouté dans le helper `_audit` des tests `TestHttpHeaderAuditor`
- **Ciphers faibles faux positif (TLS 1.3)** : `ctx.maximum_version = TLSv1_2` + vérification du préfixe du cipher négocié
- **DNSSEC/CAA sur sous-domaines** : méthode `_root_domain()` extraite et réutilisée par `_check_dnssec`, `_check_caa`, `_check_dmarc`

#### Tests ajoutés (session 30)
- `TestAdminReset2FA` (4 tests dans test_admin.py) : succès, user introuvable, 2FA non activée, non-admin
- `TestGoogleAuth2FA` (2 tests dans test_auth.py) : Google login + 2FA → `mfa_required`, flux complet Google → confirm-login
- `test_wordpress_text_mention_no_false_positive` + `test_drupal_text_mention_no_false_positive`

### Fix — Navbar Dashboard
- Suppression du bouton "Mon espace" de la top navbar (présent en doublon : navbar + dropdown)
- Remplacé par "Historique" pour tous les utilisateurs connectés (commit `d3bdaa7`)

### Fix — CORS sur `/auth/google`
- `response_model=TokenResponse` sur `@router.post("/google")` causait un `ResponseValidationError` (500) quand le 2FA était requis (`{"mfa_required": True, ...}` ≠ `TokenResponse`)
- Fix : retrait de `response_model=TokenResponse` (commit `526cb6d`)

---

## 🆕 Fonctionnalités récentes (2026-03-07, session 27)

### Bug fixes — pipeline de scan principal

#### `scanner.py` — Plan `dev` sans auditors premium
- **Symptôme** : les utilisateurs Dev (29,90€) n'obtenaient pas les résultats SubdomainAuditor ni VulnVersionAuditor dans leurs scans
- **Cause** : deux conditions `plan in ("starter", "pro")` excluaient `"dev"` lors de l'instanciation des auditors premium
- **Fix** : `("starter", "pro", "dev")` aux lignes 947, 987 et 989
- **Test ajouté** : `test_dev_plan_has_premium_auditors` dans `TestAuditManagerInit`

#### `report_service.py` — `dict(None)` crash ligne 307
- **Symptôme** : génération PDF crash avec `TypeError: 'NoneType' object is not iterable` quand `dns_details`, `ssl_details` ou `port_details` existent en DB mais valent `None`
- **Cause** : `dict(data.get("dns_details", {}))` — le fallback `{}` ne s'applique que si la clé est absente ; si la clé est présente avec valeur `None`, `dict(None)` crash
- **Fix** : ajout `or {}` : `dict(data.get("dns_details", {}) or {})` pour dns_det, ssl_det, port_det (même pattern déjà appliqué à la ligne 643)

#### Vérification consistance des catégories
- Toutes les catégories des auditors standard (`scanner.py`, `extra_checks.py`, `advanced_checks.py`) sont dans `known_cats` de `report_service.py` ✅
- Les catégories de `app_checks.py` (Application Scanning) sont volontairement absentes car ce module est indépendant du pipeline PDF ✅

**1003 tests, 0 échec** ✅

---

## 🆕 Fonctionnalités récentes (2026-03-07, session 26)

### Feature — Plan DEV (29,90 €/mois)

#### Architecture plan DEV
- **Hiérarchie** : `free (0€) → starter (9,90€) → pro (19,90€) → dev (29,90€)`
- **Plan DEV = tout Pro + API key + Application Scanning**
- API key (`wsk_`) déplacée de Pro → Dev exclusivement
- Application Scanning réservé à Dev exclusivement

#### Backend — Fichiers modifiés
- **`payment_router.py`** : `STRIPE_DEV_PRICE_ID = "price_1T8MpWKOrtMvErGv0iXhORaP"`, `_PLAN_AMOUNTS["dev"] = 2990`, `_PRICE_TO_PLAN[STRIPE_DEV_PRICE_ID] = "dev"`, `_price_id_for_plan("dev")`, rank downgrade `{"free":0,"starter":1,"pro":2,"dev":3}`, `is_paid` inclut "dev", portail/cancel incluent "dev"
- **`auth_router.py`** : API key auth (`get_current_user` + `get_optional_user`) : `("pro",)` → `("dev",)` ; White-label (`wb_enabled`, `wb_logo`) : `("pro",)` → `("pro","dev")`
- **`main.py`** : 2 occurrences API key wsk_ dans `/scan/limits` et `/scan` : `("pro",)` → `("dev",)` ; White-label PDF : `("pro",)` → `("pro","dev")`
- **`monitoring_router.py`** : `DOMAIN_LIMITS["dev"] = None` (illimité)
- **`webhook_router.py`** : `_require_pro` : `("pro",)` → `("pro","dev")`
- **`admin_router.py`** : `PLAN_PRICES["dev"] = 2990`, plan breakdown inclut "dev", validation plans inclut "dev"
- **`models.py`** : `scan_limit_per_day["dev"] = None`
- **`app_router.py`** : `APP_LIMITS = {"dev": None}`, `_require_plan` → "dev" uniquement

#### Frontend — Fichiers modifiés
- **`AuthContext.tsx`** : `plan` type inclut `'dev'`, `upgradeToPlan` accepte `'dev'`
- **`PricingModal.tsx`** : 4ème carte DEV violet (29,90€), `max-w-5xl`, grid 4 colonnes, `isPaid = plan !== 'free'`, `isDev`, `DEV_FEATURES` (tout Pro + API key + Application Scanning)
- **`ClientSpace.tsx`** : `isPremium` inclut 'dev', Developer tab visible pour pro+dev, White-label tab visible pour pro+dev, apps tab uniquement pour dev, `fetchApps` guard dev-only, plan colors (dev=violet), billing description dev, plan comparison grid 4 colonnes avec carte Dev
- **`analytics.ts`** : `captureUpgradePlanClicked(plan: 'starter' | 'pro' | 'dev')`

#### Tests
- `test_auth.py` : `_make_pro_with_api_key` → plan "dev", `test_api_key_pro_user_authenticated` → plan "dev", `test_wsk_pro_key_returns_user` → plan "dev"
- `test_main_helpers.py` : `test_wsk_pro_key_in_scan_limits` et `test_wsk_pro_key_scan` → plan "dev"
- `test_payment.py` : `_PLAN_AMOUNTS["dev"] == 2990` ajouté
- **910 tests, 0 échec** ✅

#### Variable d'env Stripe à définir sur le serveur
```bash
STRIPE_DEV_PRICE_ID=price_1T8MpWKOrtMvErGv0iXhORaP
```
(Déjà codée en dur comme fallback dans `payment_router.py`)

---

## 🆕 Fonctionnalités récentes (2026-03-07, session 25)

### Feature — Application Scanning (nouveau service)

#### Architecture
- **`app/app_checks.py`** (nouveau) — `AppAuditor(BaseAuditor)` : 8 catégories de checks passifs sur applications web
  - Fichiers sensibles exposés : `.env`, `.git/HEAD`, dumps SQL, `.htpasswd`, backups (CRITICAL/HIGH)
  - Panneaux admin : phpMyAdmin, Adminer, `/admin`, `/administrator` (CRITICAL/HIGH)
  - Endpoints API : Swagger, OpenAPI, Spring Actuator, phpinfo (MEDIUM/HIGH)
  - CORS wildcard `*` → HIGH p=10
  - Cookies sans flags `Secure` / `HttpOnly` → MEDIUM p=5 chacun
  - Listing de répertoires → MEDIUM p=8
  - Mode debug / stack traces → HIGH p=12
  - `robots.txt` révélant des chemins sensibles → LOW p=3
  - Zéro test d'injection actif (lecture seule)

- **`app/models.py`** — nouveau modèle `VerifiedApp`
  - Colonnes : `name`, `url`, `domain`, `verification_method` (dns|file), `verification_token`, `is_verified`, `verified_at`, `last_scan_at`, `last_score`, `last_risk_level`, `last_findings_json`, `last_details_json`
  - Contrainte unique `(user_id, url)` — index `ix_user_app_url`

- **`app/database.py`** — migration `010_verified_apps` (table gérée par ORM)

- **`app/routers/app_router.py`** (nouveau) — `APIRouter(prefix="/apps")`
  - `POST   /apps`                      → enregistrer une app (Starter+)
  - `GET    /apps`                      → lister les apps de l'user
  - `DELETE /apps/{id}`                 → supprimer une app
  - `GET    /apps/{id}/verify-info`     → instructions de vérification (DNS ou fichier)
  - `POST   /apps/{id}/verify`          → déclencher la vérification d'ownership
  - `POST   /apps/{id}/scan`            → lancer un scan applicatif (rate limit 3/hour)
  - `GET    /apps/{id}/results`         → derniers résultats
  - Validation URL anti-SSRF (FQDN regex + plages IP privées bloquées)
  - Limites plan : Starter=3 apps, Pro=illimité

- **`app/main.py`** — enregistrement de `app_router`

- **`frontend/src/pages/ClientSpace.tsx`** — nouvel onglet "Applications"
  - Formulaire d'ajout : nom, URL, choix méthode de vérification (DNS TXT / fichier .well-known)
  - Liste des apps avec badge VÉRIFIÉ / EN ATTENTE
  - Instructions de vérification inline (expandable)
  - Bouton "Vérifier" → appel `/apps/{id}/verify`
  - Bouton "Scanner" → appel `/apps/{id}/scan` + affichage findings expandable
  - Score badge + findings avec couleurs par sévérité

#### Vérification d'ownership
- **DNS TXT** : `_cyberhealth-verify.{domain}` → valeur `cyberhealth-verify={token}`
- **Fichier** : `{url}/.well-known/cyberhealth-verify.txt` → contenu `cyberhealth-verify={token}`
- Token : `secrets.token_urlsafe(24)` — unique par app
- Résilience : fallback HTTP si HTTPS échoue pour la vérification fichier

#### Tests
- `tests/test_database.py::test_apply_migrations_records_all_versions` : mis à jour pour `010_verified_apps`
- **910 tests, 0 échec** ✅

---

## 🆕 Fonctionnalités récentes (2026-03-07, session 24)

### Bug fix — Rate limit 429 global (nginx + IP réelle)
- **Symptôme** : tous les utilisateurs anonymes partageaient le même bucket `ip:127.0.0.1` → le premier utilisateur à scanner épuisait le quota pour tout le monde
- **Cause** : uvicorn derrière nginx sans `--proxy-headers` → `request.client.host` retournait `127.0.0.1` pour toutes les connexions
- **Fix backend** (`main.py`) : ajout de `_get_real_ip(request)` — lit `X-Real-IP` puis `X-Forwarded-For`, fallback `request.client.host`
  ```python
  def _get_real_ip(request: Request) -> str:
      real_ip = request.headers.get("X-Real-IP", "").strip()
      if real_ip:
          return real_ip
      forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
      if forwarded_for:
          return forwarded_for.split(",")[0].strip()
      return request.client.host if request.client else "127.0.0.1"
  ```
  - Remplace 2 appels `get_remote_address(request)` par `_get_real_ip(request)` dans `/scan` et `/scan/limits`
- **Fix infra** (`infra/cyberhealth-api.service`) : ajout `--proxy-headers --forwarded-allow-ips=127.0.0.1` à l'ExecStart uvicorn
- **Fix frontend** (`useScanner.ts`) : fast-fail sur erreur — max 800ms d'attente au lieu de 4800ms quand l'API retourne une erreur immédiatement (ex: 429)
  ```typescript
  const waitMs = apiError ? Math.min(remaining, 800) : remaining;
  ```

### Bug fix — Scan anonyme → retour à la page d'accueil (pas de scroll sur erreur)
- **Symptôme** : après un scan en erreur, la ScanConsole disparaissait et l'utilisateur se retrouvait sur le hero section
- **Fix** (`Dashboard.tsx`) : scroll vers `resultsRef` également sur `scanner.status === 'error'` (pas seulement sur `'success'`)

### Feature — Section "Ce qu'un pirate voit" dans le rapport PDF (Section 4)
- **`report_service.py`** : nouvelle fonction `_hacker_scenarios(findings, lang)` — 8 scénarios d'attaque mappés depuis les findings CRITICAL/HIGH par mots-clés (titre/catégorie)
  - RDP/SMB → ransomware (exploit_time: "< 2 heures")
  - Base de données exposée → exfiltration SQL
  - FTP/Telnet → sniffing man-in-the-middle
  - SSL/TLS invalide → interception HTTPS
  - SPF/DMARC manquant → phishing domain spoofing
  - WordPress → brute-force /wp-admin
  - Version vulnérable → RCE (CVE associés)
  - Réputation/blacklist → spam/phishing
  - Déduplication : SPF+DMARC → 1 carte phishing uniquement
- **`report_template.html`** :
  - CSS : `.hacker-card`, `.hacker-card-header`, `.hacker-diagram-*`, `.hacker-time-value`
  - Section 4 ajoutée (conditionnelle `{% if hacker_scenarios %}`) — cartes sombres, header navy, temps d'exploitation en rouge, schéma ASCII de l'attaque (🔴 Attaquant → 🌐 Internet → 🖥 Cible)
  - Renumérotation des sections : Plan d'Action 3→5/4, Annexes 4→6/5, CTA 5→7/6
- **`main.py`** : injection de `industry_avg` dans `audit_data` avant `generate_pdf()` (requête SQL + fallback 70)

### Feature — Widget maturité de sécurité (Dashboard + rapport PDF)
- **`public_router.py`** : `/public/stats` retourne maintenant `industry_avg` et `avg_source`
  - `avg_source = "real"` si ≥50 scans en DB (moyenne réelle calculée)
  - `avg_source = "baseline"` sinon → valeur fixe 70
  - Constante `INDUSTRY_BASELINE = 70`, `MIN_SCANS_FOR_REAL = 50`
- **`Dashboard.tsx`** : widget maturité entre le panneau score et les onglets
  - 2 barres animées : score utilisateur vs moyenne industrie
  - Message psychologique avec percentile estimé (`gap × 1.5`)
  - CTA "Obtenir le rapport complet" pour les anonymes sous la moyenne
  - Couleur violet `#a78bfa`, icône `TrendingUp`
- **`report_template.html`** (Section 1) : bloc benchmark PDF avec 2 barres horizontales + message danger/ok
- **`analytics.ts`** : `'maturity_widget'` ajouté à `RegisterCtaSource`

---

## 🆕 Fonctionnalités récentes (2026-03-06, session 23)

### CRM Brevo — Lead Gen `/report/request` (910 tests, 100% coverage)

#### `brevo_service.py` — 2 nouvelles fonctions
- **`add_lead_contact(email, domain)`** : ajoute le lead dans la liste Brevo dédiée (`LEADS_LIST_ID = 4`) avec attributs `DOMAIN` et `LEAD_SOURCE = "landing_report"`, `updateEnabled=True` (idempotent)
- **`send_lead_report_email(email, domain, pdf_bytes, score, risk_level)`** : envoie le rapport PDF expert par email (template distinct du rapport hebdomadaire monitoring) — couleur de risque dynamique, CTA vers l'inscription, mention consultation 30 min offerte

#### `main.py` — background task `_deliver_lead_report`
- Remplace le TODO ligne 693 par `asyncio.create_task(_deliver_lead_report(body.email, body.domain, lead_id))`
- Pipeline (erreurs silencieuses, non bloquant) :
  1. `brevo_service.add_lead_contact()` → CRM
  2. `AuditManager(domain, plan="pro").run()` → scan complet
  3. `report_service.generate_pdf(scan_data, lang="fr")` → PDF
  4. `brevo_service.send_lead_report_email()` → envoi
- L'endpoint retourne toujours 202 immédiatement

#### Tests (+12 tests)
- `TestAddLeadContact` (4) : délègue à `_contacts_request`, attribut DOMAIN, LEAD_SOURCE, `updateEnabled`
- `TestSendLeadReportEmail` (5) : délègue à `_send`, PDF base64, destinataire, couleur CRITICAL, fallback couleur inconnue
- `TestDeliverLeadReport` (3) : pipeline complet appelé, args `send_lead_report_email` corrects, exception silencieuse

**Variable d'env à créer dans Brevo** : liste "Leads Landing" (id=4) avec attributs contact `DOMAIN` (text) et `LEAD_SOURCE` (text)

---

## 🆕 Fonctionnalités récentes (2026-03-06, session 22)

### Tests — scanner.py __main__ block (+2 tests) → 898 tests, **100% coverage** 🏆

#### TestScannerMainEntrypoint (nouveau, 2 tests dans test_scanner.py)
- `test_main_with_explicit_domain` : `sys.argv[1]` fourni → `AuditManager("test.com")` créé et `run()` attendu (line 1019 branch True)
- `test_main_default_domain` : aucun argv[1] → domaine par défaut `"example.com"` (line 1019 branch False)

**Technique** : `runpy.run_path(scanner_path, run_name="__main__")` + interception de `asyncio.run` via `patch.object` avec injection du mock `AuditManager` dans `coro.cr_frame.f_globals` avant délégation à l'`asyncio.run` original. Permet de couvrir le bloc `if __name__ == "__main__":` sans réseau réel.

**Couverture globale : 100%** (898 tests, 0 échec) 🎯
**100% sur TOUS les fichiers** — plus aucun gap dans l'ensemble du codebase.

---

## 🆕 Fonctionnalités récentes (2026-03-06, session 21)

### Tests — main.py + database.py + quickwins (+75 tests) → 896 tests, 99%

#### test_main_helpers.py (nouveau, 44 tests)
- `TestScanRequestValidateLang` (4) : lang fr/en valides, lang invalide → fallback "fr", lang vide → "fr" (line 199)
- `TestReportRequestValidateEmail` (4) : email valid, lowercase normalisé, sans @, sans point → 422 (lines 237-240)
- `TestHealthCheck` (1) : GET /health → 200 + status/version/timestamp (lines 294-296)
- `TestCheckAnonRateLimit` (4) : sous limite, cookie limite 429, IP limite 429, pas de record = 0 (lines 329-364)
- `TestIncrementAnonCount` (2) : incrémente existants, crée nouveaux (lines 384-407)
- `TestCheckUserRateLimit` (3) : illimité, sous limite, dépassé → 429 (lines 412-421)
- `TestClientId` (2) : GET /client-id nouveau cookie, cookie existant (lines 448-461)
- `TestReportRequest` (3) : POST /report/request valide → 202, _build_report_structure, email invalide → 422 (lines 691-701, 729)
- `TestRunInExecutor` (1) : fn synchrone → résultat correct (lines 894-895)
- `TestScanLimits` (3) : Pro illimité, Free limité, wsk_ Pro key (lines 489-492)
- `TestScanEndpoint` (6) : anonyme, authentifié + history, wsk_, timeout 504, exception 500, debug mode (lines 554-655)
- `TestGeneratePdfEndpoint` (6) : succès, RuntimeError 503, Exception 500, white-label, debug RuntimeError, debug Exception (lines 844-880)
- `TestLifespanSchedulerStarted` (1) : scheduler_started=True → stop_scheduler appelé (lines 108, 113)
- `TestSentryInit` (1) : SENTRY_DSN défini → sentry_sdk.init() appelé (lines 129-147)
- `TestGlobalExceptionHandler` (2) : exception → 500, debug mode → détail exposé (lines 905-909)
- **main.py : 61% → 100%** 🎯

#### test_database.py (nouveau, 8 tests)
- `TestGetDb` (1) : get_db() yield session + close (lines 23-27)
- `TestAddColumnIfMissing` (2) : ajoute si absente, skip si existante (lines 133-138)
- `TestApplyMigrations` (4) : table créée, 9 migrations enregistrées, idempotent, legacy table → ALTER TABLE
- `TestInitDb` (1) : create_all + migrations appliquées
- **database.py : 47% → 100%** 🎯

#### Corrections de tests existants
- `test_brevo_service.py::TestAddNewsletterContactFallback` : mock `put` remplacé par `side_effect=[400, 200]` sur `post` (la fn utilise post pour les 2 appels, pas put) → **brevo_service.py 100%**
- `test_report_service.py::TestGeneratePdf` : ajout `test_generate_pdf_success_returns_bytes` → chemin nominal (line 228) → **report_service.py 100%**
- `test_auth_utils.py::TestJwtSecretKeyFallback` (+2) : reload auth.py avec JWT_SECRET_KEY absent/trop court → warning stderr → **auth.py 100%**
- `test_auth.py::TestGetOptionalUserWithBearer` : refactorisé de HTTP vers appel direct `get_optional_user()` → élimine 3 appels POST /contact qui épuisaient le rate limit (5/hour) → fix de 2 tests qui failaient en suite complète
- `test_contact_newsletter.py::TestNewsletterClientIp` : refactorisé de HTTP vers appel direct `_get_ip(mock_request)` → élimine call POST /newsletter qui épuisait le rate limit → **newsletter_router.py 100%**

**Couverture globale : 99%** (896 tests, 0 échec)
**100% sur** : tous les routers + auth + database + main + scheduler + brevo + report + models + advanced_checks + extra_checks + limiter
**Seul gap** : `scanner.py` lines 1016-1027 (`if __name__ == "__main__":` block, non coverable par pytest)

## 🆕 Fonctionnalités récentes (2026-03-06, session 20)

### Tests — payment_router + scanner + advanced_checks + extra_checks + monitoring_router (+56 tests) → 821 tests, 93%

#### test_payment.py (+21 tests)
- `TestUserFromSubscriptionCacheUpdate` (2) : uid_meta fallback → stripe_customer_id mis en cache, pas d'écrasement si déjà défini
- `TestEnsureAndDowngradeAdminGuard` (4) : admin guard bloque `_ensure_plan` et `_downgrade`, exceptions silencieuses
- `TestCreateCheckoutStripeError` (1) : appel direct de `create_checkout()` (bypass rate limiter 5/hour) → 502 sur StripeError
- `TestWebhookEdgeCases` (5) : Customer.retrieve fallback (patch `app.routers.payment_router.stripe`), exception silencieuse, asyncio.create_task RuntimeError silencieux, invoice.payment_failed → downgrade appelé, no sub_id → no-op
- `TestCustomerPortalEdgeCases` (4) : cache depuis checkout.Session, Session.retrieve StripeError → fallback Customer.list, Customer.list → cache + portal, Customer.list StripeError → 404
- `TestCancelSubscriptionStripeErrors` (3) : Subscription.list StripeError, Session.retrieve StripeError, Subscription.modify StripeError → tous silencieux, status=cancelling quand même
- `TestWebhookConstructEventException` (1) : Exception générique dans construct_event → 400 (lines 246-248)
- `TestCancelViaSessionRetrieve` (1) : sub_id depuis Session.retrieve quand Subscription.list vide (line 455)
- **payment_router.py : 87% → 100%**

#### test_scanner.py (+22 tests)
- `TestFindingToDict` (1) : `Finding.to_dict()` retourne tous les champs (line 94)
- `TestScanResultToDict` (1) : `ScanResult.to_dict()` sérialise findings + port_details int→str (lines 122-123)
- `TestBaseAuditorGetDetails` (1) : `BaseAuditor.get_details()` retourne `_details` (lines 166-167)
- `TestDNSAuditorAuditMethod` (2) : appel `audit()` complet → appelle `_check_spf` + `_check_dmarc` (lines 177-182)
- `TestSSLAuditorAuditMethod` (2) : appel `audit()` complet → appelle `_check_ssl` (lines 361-364)
- `TestDetectSharedHosting` (4) : `_detect_shared_hosting()` : OVH PTR → True, inconnu → False, PTR exception → False, DNS exception → False (lines 589-601)
- `TestPortAuditorLowLevel` (6) : `_check_port` TimeoutError → closed (line 709-711), Exception → closed, `_tcp_connect` success/refused/exception/resolved_ip (lines 718-728)
- **scanner.py : 85% → 97%** (seul __main__ block non couvert)

#### test_advanced_checks.py (+13 tests)
- `TestVulnVersionAuditorMissingPaths` (5+1) : `audit()` success (line 138-139), `get_details()` (143-144), ASP.NET headers (198-201), aspnetmvc header, version non-parseable → continue (212-213)
- `TestVulnVersionAuditorNoVersionContinue` (1) : x-aspnet-version avec valeur garbage → `_parse_version` None → continue (line 213)
- `TestSubdomainAuditorAudit` (3) : success/timeout/exception paths (lines 278-289)
- `TestExtraChecksMissingPaths` (3) : `_fetch_headers_sync` success (207-209), DKIM TimeoutError → silencieux (256-257), `TechExposureAuditor.audit()` success (324)
- **advanced_checks.py : 93% → 100%**, **extra_checks.py : 96% → 100%**

#### test_monitoring.py (+7 tests)
- `TestMonitoringMissingPaths` (7) : JSON invalide dans `open_ports`/`technologies` → None silencieux (149-150, 155-156), PATCH `is_active=False` (301), PATCH `checks_config` (303), scan_now avec JSON invalide (362-363, 368-369)
- **monitoring_router.py : 94% → 100%**

**Couverture globale : 93%** (821 tests, 0 échec)
**100% sur** : payment_router, monitoring_router, scans_router, webhook_router, admin_router, advanced_checks, extra_checks, limiter

---

## 🆕 Fonctionnalités récentes (2026-03-06, session 19)

### Tests — auth_router Google OAuth + report_service Jinja2/PDF (+22 tests) → 700 tests, 86%

#### test_auth.py (+10 tests)
- `TestGoogleAuth` (6) : token invalide → 401, email non vérifié → 401, nouvel user auto-créé, user existant connecté, rattachement compte existant, `GOOGLE_CLIENT_ID` manquant → 400
- `TestGoogleUserGuards` (2) : `change-password` + `change-email` bloqués pour comptes Google (`password_hash` préfixé `!google:`)
- `TestOptionalUserApiKey` (2) : clé Pro `wsk_` → 200 sur `/auth/me`, clé Starter → 401
- **Pattern** : `google_id_token` importé localement dans la fonction → patcher `google.oauth2.id_token.verify_oauth2_token` directement (pas `app.routers.auth_router.google_id_token`)
- `auth_router.py` 84% → 95%

#### test_report_service.py (+12 tests)
- `TestBuildJinjaEnv` (9) : filtre `format_eur` (int, float, None, non-numérique), filtre `risk_class` (CRITICAL/HIGH/MEDIUM/LOW/unknown → classes CSS)
- `TestGeneratePdf` (3) : `WeasyPrint` ImportError → RuntimeError, erreur Jinja2 render → RuntimeError, `write_pdf` error → RuntimeError
- **Fix** : `from unittest.mock import patch, MagicMock` ajouté au niveau module (les 2 premiers tests importaient `patch` localement, le 3ème non → NameError)
- `report_service.py` 83% → **99%**

**Couverture globale : 86%** (700 tests, 0 échec)

## 🆕 Fonctionnalités récentes (2026-03-06, session 18)

### Tests — AuditManager (14) + _async_monitoring (4) + fix test flaky JWT → 652 tests, 80%
- **18 nouveaux tests**, total **652 tests, 0 échec**, couverture 80%

#### test_scanner.py — TestAuditManagerInit + TestAuditManagerRun (14 tests)
- Orchstrateur central enfin couvert : `scanner.py` 73% → 85%
- `TestAuditManagerInit` (6) : plan free (0 premium), starter/pro (2 premium), domain lowercased+stripped, checks_config filtre auditors, sans config = 7 auditeurs
- `TestAuditManagerRun` (8) : ScanResult avec tous les champs, agrégation findings multi-auditeurs, tri par pénalité, exception dans un auditeur ignorée via `gather(return_exceptions=True)`, détails premium vides pour free / remplis pour starter, score calculé depuis findings
- **Pattern** : `ExitStack` + `_all_auditor_patches()` pour patcher les 7+2 classes auditeurs — chaque classe patchée retourne un `_mock_auditor(findings, details)`
- **Bug trouvé** : `Finding` est un `@dataclass` avec 7 champs positionnels (`category, severity, title, technical_detail, plain_explanation, penalty, recommendation`) — toujours utiliser les kwargs

#### test_scheduler.py — TestAsyncMonitoring (4 tests)
- `_async_monitoring` : `scheduler.py` 64% → 71%
- Tests : `_scan_and_alert` appelé pour chaque domaine actif, skip si `_should_scan_now=False`, exception sur un domaine n'arrête pas la boucle, domaines `is_active=False` ignorés
- **Import local** : `SessionLocal` importé dans `_async_monitoring` → patch à `app.database.SessionLocal` (pas `app.scheduler.SessionLocal`)
- `MagicMock` ajouté aux imports de test_scheduler.py

#### test_auth_utils.py — fix test_tampered_signature (flaky)
- **Root cause** : dernier char base64url peut être un "filler" (bits nuls de padding) → le changer ne modifie pas les bytes décodés → vérification HMAC réussit quand même
- **Fix** : modifier un char au milieu de la signature (chars toujours significatifs)

## 🆕 Fonctionnalités récentes (2026-03-06, session 17)

### Tests — brevo_service.py (test_brevo_service.py) + scheduler._scan_and_alert (test_scan_and_alert.py)
- **37 + 12 = 49 nouveaux tests**, total **634 tests, 0 échec**

#### test_brevo_service.py (37 tests)
- Couvre toutes les fonctions d'envoi email et gestion contacts de `brevo_service.py`
- **Pattern critique** : conftest patche les fonctions à scope session → sauvegarder les vraies références au niveau module *avant* que conftest s'exécute :
  ```python
  import app.services.brevo_service as _svc
  _real_send_welcome = _svc.send_welcome_email
  _real_send_reset   = _svc.send_password_reset_email
  # etc.
  ```
- `add_newsletter_contact` / `remove_newsletter_contact` utilisent httpx directement (pas `_contacts_request`) → mockées via `patch("httpx.AsyncClient")`
- `_mock_http_client(response)` helper construit un context manager AsyncClient mock
- Tests : pas de clé API → False, 200/201/204 → True, 400/500 → False, exception réseau → False, champs user HTML-escapés, méthodes HTTP correctes (POST/PUT/DELETE), liste ID 2 pour utilisateurs inscrits, attribut PLAN défini

#### test_scan_and_alert.py (12 tests)
- Couvre `scheduler._scan_and_alert` — logique centrale de monitoring
- **Import local** : `AuditManager` importé dans la fonction → patch à `app.scanner.AuditManager`
- **Import local** : `fire_webhooks` importé dans la fonction → patch à `app.routers.webhook_router.fire_webhooks`
- `_audit_mock(result)` : wraps un MagicMock avec `run = AsyncMock(return_value=result)`
- Tests : user inactif skippé, score/risk/SSL/ports mis à jour en DB, alerte sur drop ≥ seuil, alerte sur finding CRITICAL, pas d'alerte premier scan (no prev_score), alerte SSL ≤7 jours, alerte nouveau port ouvert, rapport PDF envoyé/non-envoyé selon `email_report`

## 🆕 Fonctionnalités récentes (2026-03-06, session 16)

### Tests — auth.py + brevo_service._esc (test_auth_utils.py)
- 35 nouveaux tests, total **585 tests, 0 échec**
- Nouveau fichier `tests/test_auth_utils.py` — zéro DB, zéro réseau (fonctions pures)
- 7 classes : `TestHashPassword`, `TestVerifyPassword`, `TestNeedsRehash`, `TestCreateAccessToken`, `TestDecodeToken`, `TestGenerateApiKey`, `TestBrEsc`
- `TestHashPassword` (4 tests) : type str, préfixe $argon2, salt aléatoire, non-plaintext
- `TestVerifyPassword` (6 tests) : correct True, mauvais False, hash invalide False sans exception, sensible casse
- `TestNeedsRehash` (3 tests) : argon2 frais → False, hash invalide → False
- `TestCreateAccessToken` (6 tests) : format JWT 3 segments, payload sub/email/plan/exp, sub est string (JWT spec)
- `TestDecodeToken` (5 tests) : valid → payload, invalid/vide/tampered → None
- `TestGenerateApiKey` (4 tests) : préfixe wsk_, longueur ≥40, unicité sur 10 appels, chars URL-safe
- `TestBrEsc` (7 tests) : plain inchangé, <>&" → entités HTML, non-string → str, XSS neutralisé

## 🆕 Fonctionnalités récentes (2026-03-06, session 16)

### Tests — auth_router.py (test_auth.py)
- 32 nouveaux tests, total **550 tests, 0 échec**
- Endpoints couverts : `PATCH /auth/profile`, `DELETE /auth/account`, `POST /auth/change-password`, `POST /auth/change-email`, `GET/PATCH /auth/white-label`, `POST/DELETE /auth/white-label/logo`
- Helper `_make_user(db_session, plan)` ajouté au fichier (évite les appels HTTP, même pattern que test_monitoring.py)
- Vérifie : update partiel profile (prénom seul), suppression effective de l'user en DB, login fonctionnel après changement de mot de passe, isolation email (409 si doublon), guard 403 sur tous les endpoints white-label pour plan free, upload PNG + taille + type MIME + plan, delete logo cycle upload→delete
- **Bug fix** : `conftest.py` — `import app.models` ajouté avant `Base.metadata.create_all()` dans `test_engine` → corrige le 500 sur `test_register_success` en isolation

## 🆕 Fonctionnalités récentes (2026-03-06, session 14)

### Tests — report_service.py (test_report_service.py)
- 68 nouveaux tests, total **518 tests, 0 échec**
- 5 nouvelles classes : `TestScoreColor`, `TestRiskColor`, `TestRiskLabel`, `TestBuildActionPlan`, `TestBuildContext`
- `TestScoreColor` (9 tests) : boundaries exactes 70/69/40/39, limites 0 et 100
- `TestRiskColor` (6 tests) : CRITICAL/HIGH/MEDIUM/LOW + unknown/vide → gris par défaut
- `TestRiskLabel` (10 tests) : fr (Critique/Élevé/Modéré/Faible) + en (Critical/High/Moderate/Low) + niveau inconnu → retourné tel quel + lang inconnue → fallback fr
- `TestBuildActionPlan` (12 tests) : phases vides, SPF→urgent, DKIM→important, SSH→optimize, déduplication (2 findings identiques → 1 action), lang=en, multi-phase, plafond 5 en optimize, DMARC→urgent, SSL expiré→urgent
- `TestBuildContext` (31 tests) : domain/scan_id/score, score_color/risk_color/risk_label calculés, groupes par catégorie, compteurs severity, checks_context, actions, is_premium, format date fr/en + fallback, white-label (enabled/disabled/company/color)

## 🆕 Fonctionnalités récentes (2026-03-06, session 13)

### Tests — SubdomainAuditor (test_advanced_checks.py)
- 23 nouveaux tests, total **450 tests, 0 échec**
- 2 nouvelles classes : `TestSubdomainAuditorSync`, `TestSubdomainAuditorFetch`
- `TestSubdomainAuditorSync` (17 tests) : via `patch.object` sur `_fetch_crtsh`, `_resolve_subdomain`, `_check_cert`
  - Aucun subdomain → [], actifs valides → INFO p=0, orphelins → MEDIUM p=count×3 (plafonné 15)
  - Cert expiré → HIGH p=15, cert expirant <30j → MEDIUM p=8
  - Mixte orphelins + expiré → MEDIUM + HIGH (2 findings)
  - Expiring soon empêche le finding INFO
  - `_details` dict : total_found, subdomains avec IP, orphaned list
- `TestSubdomainAuditorFetch` (6 tests) : `urllib.request.urlopen` mocké
  - JSON valide → sous-domaines filtrés, wildcards exclus, hors-scope exclus, déduplication, erreur réseau → [], plafond MAX_SUBDOMAINS=50
- **Stratégie** : `_run()` helper avec `patch.object` sur les 3 sous-méthodes — zéro appel réseau réel

## 🆕 Fonctionnalités récentes (2026-03-06, session 12)

### Tests — TechExposureAuditor + ReputationAuditor (test_advanced_checks.py)
- 23 nouveaux tests, total **427 tests, 0 échec**
- 2 nouvelles classes : `TestTechExposureAuditor`, `TestReputationAuditor`
- `TechExposureAuditor` : `_detect_tech_sync` — body vide → [], WordPress (wp-content, wp-json, literal) → MEDIUM p=5, /wp-admin 200/302 → +HIGH p=10, /wp-admin 404 → MEDIUM seul, Drupal → MEDIUM p=4, PHP/7.4.33 → LOW p=4, PHP sans version → pas de finding, fallback HTTP quand HTTPS échoue
- `ReputationAuditor` : IP clean → INFO p=0, blacklisté tous DNSBL → CRITICAL p=20, 1 seul DNSBL → CRITICAL, DNS failure → [], `_resolve_ip` sync direct, `_check_dnsbl` vérifie inversion octets IP, serveurs matchés retournés
- **Stratégie mock TechExposure** : `side_effect=[conn_main, conn_wp_admin]` pour isoler les deux appels HTTPSConnection (main page vs /wp-admin) — `_run()` helper injecte une 2ème conn qui raise pour éviter le HIGH parasite
- **Stratégie mock Reputation** : `patch("app.extra_checks.socket.gethostbyname")` + `patch("app.extra_checks.dns.resolver.Resolver")`

## 🆕 Fonctionnalités récentes (2026-03-06, session 11)

### Tests — advanced_checks.py + extra_checks.py (test_advanced_checks.py)
- 44 nouveaux tests, total **404 tests, 0 échec**
- Couvre : `_parse_version`, `_version_in_range`, `VulnVersionAuditor`, `HttpHeaderAuditor`, `EmailSecurityAuditor`
- 5 classes : `TestParseVersion`, `TestVersionInRange`, `TestVulnVersionAuditor`, `TestHttpHeaderAuditor`, `TestEmailSecurityAuditor`
- `_parse_version` / `_version_in_range` : logique pure — 9+10 cas dont boundaries exactes et edge cases
- `VulnVersionAuditor` : PHP 7.x (CRITICAL), PHP 8.0 (HIGH), PHP 8.2 (ok), Apache 2.4.49 CVE-2021-41773 (CRITICAL), nginx 1.20.0 (HIGH), IIS 8.5 (HIGH), no headers → [], connexion échouée → []
- `HttpHeaderAuditor` : tous headers présents → 0 finding, HSTS manquant (HIGH p=10), CSP manquant (MEDIUM p=8), Server avec version (LOW), X-Powered-By (LOW p=3), hôte injoignable → []
- `EmailSecurityAuditor` : DKIM trouvé (ok), DKIM absent (MEDIUM p=8), MX présent (ok), MX absent (INFO p=0), `_check_dkim`/`_check_mx` directs

## 🆕 Fonctionnalités récentes (2026-03-06, session 10)

### Tests — scanner.py (test_scanner.py) + bug fix dns.exception.NXDOMAIN
- 45 nouveaux tests, total **360 tests, 0 échec**
- Couvre : `ScoreEngine`, `DNSAuditor` (SPF + DMARC), `SSLAuditor`, `PortAuditor`
- **Bug corrigé** : `dns.exception.NXDOMAIN` inexistant → `dns.resolver.NXDOMAIN` (scanner.py)
  - Impact réel : domaines sans enregistrement DMARC retournaient `status:"error"` au lieu de `status:"missing"` + finding HIGH — le finding DMARC manquant n'était donc JAMAIS généré sur NXDOMAIN
- `ScoreEngine` : 12 cas limites dont boundaries 40/60/80, clampage à 0
- `DNSAuditorSPF` : +all permissif, ~all valide, -all strict, manquant, erreur DNS
- `DNSAuditorDMARC` : NXDOMAIN, p=none, p=quarantine, p=reject, erreur générique, TXT sans v=DMARC1
- `SSLAuditor` : valide, expiré, expire <30j (pénalité 0), TLSv1.1 déprécié, TLSv1.0, auto-signé, connexion refusée, timeout, détails complets
- `PortAuditor` : RDP/SMB groupés, MySQL, PostgreSQL, FTP, SSH (INFO 0 penalty), HTTP/HTTPS (sans pénalité), hébergement mutualisé (INFO only, 0 penalty), détails tous ports présents

## 🆕 Fonctionnalités récentes (2026-03-06, session 9)

### Tests — scheduler (test_scheduler.py)
- 34 nouveaux tests, total **279 tests, 0 échec**
- Couvre : `_should_scan_now` (toutes fréquences + cas limites) + séquence onboarding complète
- 7 classes : `TestShouldScanNow`, `TestOnboardingJ1`, `TestOnboardingJ3`, `TestOnboardingJ7`, `TestOnboardingJ14`, `TestOnboardingIsolation`
- `_should_scan_now` testé avec `SimpleNamespace` (zéro DB) — rapide et isolé
- Onboarding testé avec users créés en DB à `created_at` contrôlé, brevo_service entièrement mocké
- Vérifie : fenêtres temporelles exactes (J+1: 20-28h, J+3: 68-76h, J+7: 164-172h, J+14: 332-340h), conditions par plan (free uniquement), condition scan (J+1: 0 scans, J+7: ≥1 scan), users inactifs exclus, scan_count transmis correctement à J+7, non-chevauchement des fenêtres

## 🆕 Fonctionnalités récentes (2026-03-06, session 9)

### Tests — payment_router (test_payment.py)
- 36 nouveaux tests, total **315 tests, 0 échec**
- Couvre : `GET /payment/status`, `POST /payment/create-checkout`, `POST /payment/webhook`, `POST /payment/cancel`
- 5 classes : `TestPaymentStatus`, `TestCreateCheckout`, `TestWebhookGuard`, `TestWebhookCheckoutCompleted`, `TestWebhookSubscriptionEvents`, `TestCancelSubscription`
- Stripe API mockée : `stripe.Webhook.construct_event`, `stripe.checkout.Session.create`, `stripe.Subscription.list/modify`
- `_user_from_subscription` et `_plan_from_subscription` mockés directement pour les events subscription (évite appels Stripe réels)
- Vérifie la sécurité clé : admin ne peut JAMAIS voir son plan modifié par un webhook Stripe
- Rate limit `5/hour` sur create-checkout → 2 tests remplacés par assertions Python directes (`_PLAN_AMOUNTS`, `inspect.getsource`)
- **100% de couverture routers atteinte** : tous les routers FastAPI ont désormais des tests

## 🆕 Fonctionnalités récentes (2026-03-06, session 8)

### Tests — webhook_router (test_webhook.py)
- 32 nouveaux tests, total **245 tests, 0 échec**
- Couvre : `GET /webhooks`, `POST /webhooks`, `DELETE /webhooks/{id}`, `POST /webhooks/{id}/test`
- 5 classes : `TestWebhookGuard`, `TestListWebhooks`, `TestCreateWebhook`, `TestDeleteWebhook`, `TestTestWebhook`
- Livraison HTTP mockée via `patch("httpx.AsyncClient")` — 200, 500, exception réseau → status=0
- Vérifie : guard Pro (401/403 free/starter), isolation inter-users, secret retourné une seule fois (absent du GET list), soft-delete (is_active=False en DB), limite 5 webhooks/compte, tous les événements valides acceptés

## 🆕 Fonctionnalités récentes (2026-03-06, session 7)

### Tests — contact_router + newsletter_router (test_contact_newsletter.py)
- 27 nouveaux tests, total **213 tests, 0 échec**
- Couvre : `GET /contact/subjects`, `POST /contact`, `POST /newsletter/subscribe`, `GET /newsletter/confirm/{token}`, `POST /newsletter/unsubscribe`
- Tous les appels Brevo mockés via `autouse` fixture
- Bug corrigé au passage : `POST /newsletter/subscribe` retournait 200 au lieu de 202 (`JSONResponse` ignorait le `status_code` du décorateur) → ajout de `status_code=202` sur les 4 `JSONResponse` de l'endpoint
- Stratégie rate limit : validation Pydantic directe pour le test des sujets (les 422 consomment aussi le compteur SlowAPI)

## 🆕 Fonctionnalités récentes (2026-03-06, session 6)

### Tests — admin_router (test_admin.py)
- 32 nouveaux tests, total **186 tests, 0 échec**
- Couvre : `GET /admin/users`, `PATCH /admin/users/{id}`, `DELETE /admin/users/{id}`, `GET /admin/stats`, `GET /admin/metrics`
- 6 classes : `TestAdminGuard`, `TestAdminListUsers`, `TestAdminUpdateUser`, `TestAdminDeleteUser`, `TestAdminStats`, `TestAdminMetrics`
- Vérifie : guard `require_admin` (401/403 pour non-admin), auto-protection (admin ne peut ni modifier ni supprimer son propre compte), plan invalide → 400, MRR calculé correctement sur subscriptions actives, conversion_rate dans [0,100], séries temporelles (signups/scans) bien formées

## 🆕 Fonctionnalités récentes (2026-03-06, session 5)

### Tests — scans_router + public_router (test_scans_history.py)
- 38 nouveaux tests, total **154 tests, 0 échec**
- Couvre : `GET/DELETE/PATCH /scans/history` + `GET /scans/history/{uuid}/export` + `GET /public/badge`, `/public/scan`, `/public/stats`
- 8 classes de tests : `TestScanHistoryList`, `TestScanDetail`, `TestExportScan`, `TestToggleShare`, `TestDeleteScan`, `TestPublicBadge`, `TestPublicScan`, `TestPublicStats`
- Export PDF mocké via `patch("app.services.report_service.generate_pdf")`
- Vérifie : isolation entre users, toggle share on/off/double, cycle share→public access, 403 si scan non partagé, badge SVG www-stripping + header X-Score

## 🆕 Fonctionnalités récentes (2026-03-06, session 4 suite)

### Monitoring — scan immédiat
- **Backend** : `POST /monitoring/domains/{domain}/scan`
  - Rate limit 3/hour par user
  - Requiert plan Starter ou Pro (403 sinon)
  - 404 si le domaine n'est pas sous surveillance ou est inactif
  - Réutilise `_scan_and_alert()` du scheduler → met à jour `last_score`, `last_risk_level`, `last_scan_at`, `last_ssl_expiry_days`, `last_open_ports`, `last_technologies` en DB
  - **Ne renvoie pas d'alerte email** (scan de diagnostic uniquement)
  - Retourne les nouvelles valeurs + message de confirmation
- **Frontend** (`ClientSpace.tsx`) :
  - Bouton `RefreshCw` dans la colonne Actions de chaque ligne du tableau monitoring
  - Spinner pendant le scan → check vert 3s après succès
  - Désactivé quand un autre scan est en cours (prevent double-click)
  - Reload automatique des domaines + historique après scan réussi
  - Visible au hover avec le bouton Supprimer (groupe `opacity-0 → opacity-100`)

## 🆕 Fonctionnalités récentes (2026-03-06, session 4)

### Tests — monitoring CRUD (test_monitoring.py)
- 31 nouveaux tests, total **104 tests, 0 échec**
- Couvre : `GET/POST/DELETE/PATCH /monitoring/domains` + `GET /monitoring/status`
- 5 classes de tests : `TestFreeUserBlocked`, `TestListDomains`, `TestAddDomain`, `TestDeleteDomain`, `TestUpdateDomain`, `TestMonitoringStatus`
- **Stratégie anti-rate-limit** : tokens générés directement via `create_access_token()`, users créés en DB via `_make_user(db_session, plan)` — aucun appel `/auth/register` ou `/auth/login`
- Vérifie : isolation entre users, soft delete, clamping seuil [1–50], fréquence invalide ignorée, limites par plan (starter=1, pro=illimité)

## 🆕 Fonctionnalités récentes (2026-03-06, session 2)

### Rapport PDF — numérotation des sections
- Sections renumérotées : ①②③④⑤⑥ (Plan d'Action était ③, Annexes ④, CTA ⑤ → décalés +1)
- Contexte enrichi : `passed_checks_count`, `warn_checks_count`, `fail_checks_count` via `_checks_context()`

### Dashboard — onglet Recommandations
- 4ème onglet `reco` ajouté : Résumé / Vulnérabilités / **Recommandations** / Avancé
- Dot indicateur orange sur l'onglet quand des recommandations existent
- Affichage numéroté avec badge de priorité (HIGH=rouge, MEDIUM=amber, LOW=gris)

### HistoryPage — export PDF + partage public
- Migré `fetch()` → `apiClient` (Axios)
- Bouton Export PDF : `GET /scans/history/{uuid}/export?format=pdf&lang={lang}` → blob download
- Bouton Share : `PATCH /scans/history/{uuid}/share` → toggle `public_share`, copie le lien dans le presse-papiers
- Badge "public" affiché sur les scans partagés, feedback ✓ 2.5s après copie

### ClientSpace — monitoring enrichi
- Colonne "Tendance" ajoutée dans le tableau de surveillance (sparkline SVG des derniers scores)
- Limit historique augmentée 20→100 pour alimenter les sparklines
- Label hardcodé corrigé → dynamique

---

## 🧪 Load Testing — Locust

Script : `load_tests/locustfile.py`

```bash
# Installation (dev uniquement)
pip install locust==2.32.3

# UI interactive (recommandé pour la première fois)
cd load_tests
locust -f locustfile.py --host=https://scan.wezea.net
# → http://localhost:8089 | Users: 50 | Spawn: 5/s | Duration: 2min

# Headless (CI / comparaison avant/après)
locust -f locustfile.py \
  --host=https://scan.wezea.net \
  --users=50 --spawn-rate=5 --run-time=2m \
  --headless --csv=load_tests/results/run_$(date +%Y%m%d_%H%M)
```

**Prérequis** : créer un compte `loadtest@example.com` / `LoadTest2026!` sur wezea.net avant de lancer.

**Objectifs** : p95 < 200ms sur les GET légers, p95 < 8s sur /scan, 0% erreur (hors 429 rate limit).

---

## 📋 Tâches en attente

- [ ] Surveiller les premières migrations argon2 dans les logs (rehash au prochain login de chaque user)
- [ ] Vérifier que `wezea.net` est bien dans les **Authorized JavaScript origins** du client OAuth Google (Google Cloud Console → APIs & Services → Credentials)
- [ ] Migration Google Sign-In vers FedCM (avertissement Chrome — pas urgent, non obligatoire aujourd'hui)

## 💡 Features en attente de trafic suffisant

### Feature Partenaires (à revoir quand ~centaines de scans/semaine)
- **Concept** : les professionnels IT/cybersécurité s'inscrivent comme partenaires (49€/mois standard, 99€/mois premium). Après chaque scan, l'utilisateur voit une liste d'experts dans sa région pouvant résoudre les vulnérabilités détectées.
- **Matching** : spécialités partenaire ↔ catégories de findings du scan (SSL, DNS, Ports, etc.)
- **Géolocalisation** : demander la ville au moment du clic "Voir les experts" (pas d'IP geolocation)
- **MVP suggéré** : annuaire statique `/partenaires` + formulaire d'intérêt avant de coder le matching
- **Modèle `Partner`** : `company_name`, `contact_email`, `region`, `city`, `specialties` (JSON), `description`, `website`, `logo_url`, `plan` (standard|premium), `is_verified`, `impressions_count`, `stripe_customer_id`
- **Pourquoi attendre** : sans trafic, les partenaires ne voient pas de leads → désabonnement ; les utilisateurs ne voient pas d'experts → feature invisible

---

## 🔄 Procédure de reprise de session

1. **Lire ce fichier en premier**
2. `git log --oneline -10` pour voir les derniers commits
3. `git status` pour voir les changements non commités
4. Vérifier si le CI/CD est vert sur GitHub Actions

---

## 📡 Commandes utiles serveur

```bash
# Voir logs du service
sudo journalctl -u cyberhealth-api -n 50 --no-pager

# Redémarrer le service
sudo systemctl restart cyberhealth-api

# Vérifier état
sudo systemctl status cyberhealth-api

# DB SQLite (attention, ne pas wiper)
sqlite3 /home/cyberhealth/app/backend/cyberhealth.db "SELECT email, plan, is_admin FROM users;"

# Voir les migrations appliquées
sqlite3 /home/cyberhealth/app/backend/cyberhealth.db "SELECT * FROM db_migrations ORDER BY id;"

# Voir les tentatives de login (brute-force monitoring)
sqlite3 /home/cyberhealth/app/backend/cyberhealth.db \
  "SELECT ip, COUNT(*) as attempts, MAX(failed_at) as last_attempt FROM login_attempts GROUP BY ip ORDER BY attempts DESC LIMIT 10;"
```
