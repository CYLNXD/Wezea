# CLAUDE.md — Mémoire du projet CyberHealth Scanner
> Ce fichier est lu en PREMIER à chaque nouvelle session. Il doit être mis à jour à chaque modification importante.
> Dernière mise à jour : 2026-03-06 (session 2)

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
│   │   └── routers/
│   │       ├── auth_router.py
│   │       ├── payment_router.py
│   │       ├── scans_router.py
│   │       ├── monitoring_router.py
│   │       ├── webhook_router.py
│   │       ├── public_router.py
│   │       └── admin_router.py
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

- **Runner CI/CD** : GitHub Actions self-hosted runner sur le serveur
- **Chemin serveur** : `/home/cyberhealth/app/`
- **Virtualenv deploy** : `.venv/` (avec le point — NE PAS confondre avec `venv/`)
- **Virtualenv service** : `venv/` (sans le point — tel que configuré dans cyberhealth-api.service)
- **Process manager** : systemd + uvicorn (`--workers 2` — optimal pour 2 vCPU + SQLite)
- **Frontend** : build Vite → servi par nginx
- **Backend** : FastAPI sur uvicorn, port 8000

### Points critiques du deploy.yml
```yaml
rsync --exclude='.venv/' --exclude='venv/' --exclude='*.db' --exclude='*.sqlite'
      --exclude='uploads/' --exclude='logs/'
# IMPORTANT : .venv/ avec le point ! rsync --delete détruirait autrement le venv
pip: utiliser .venv/bin/pip (pas pip global)
# Les tests backend s'exécutent AVANT le déploiement (étape 4)
```

### Backup de la DB
```bash
# Installation une fois (sur le serveur) :
sudo crontab -u cyberhealth -e
# Ajouter : 0 2 * * * /home/cyberhealth/app/scripts/backup_db.sh >> /home/cyberhealth/app/logs/backup.log 2>&1

# Variables d'env optionnelles :
# BACKUP_DIR=/home/cyberhealth/backups  (défaut)
# RETENTION=30                          (jours de rétention)
# S3_BUCKET=s3://mon-bucket/backups/    (optionnel)
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

### Pages stylisées (skeuomorphique ✅)
- `Dashboard.tsx` ✅
- `LoginPage.tsx` ✅
- `HistoryPage.tsx` ✅
- `AdminPage.tsx` ✅
- `ContactPage.tsx` ✅
- `LegalPage.tsx` ✅
- `ClientSpace.tsx` ✅
- `PricingModal.tsx` ✅
- `PublicScanPage.tsx` ✅ (page publique /r/{uuid}, pas de skeu — style épuré)

---

## 🔧 Bugs résolus (historique)

### CI/CD
- **Service 203/EXEC** : rsync `--delete` supprimait `.venv/` → ajout `--exclude='.venv/'`
- **`pip: command not found`** : idem + gunicorn manquant → ajouté `gunicorn==23.0.0` dans requirements.txt
- **`No module named 'app.extra_checks'`** : fichier était dans `.gitignore` → retiré du gitignore
- **DB wipée à chaque deploy** : `*.db` non exclus du rsync → ajout `--exclude='*.db'`

### Backend
- **bcrypt/passlib incompatible** : bcrypt 4.x+ refuse passwords > 72 bytes → `bcrypt==4.0.1`
- **`is_admin` absent après reload** : `UserResponse` Pydantic n'avait pas le champ → ajouté
- **Stripe résilience** : après wipe DB, `metadata.user_id` devenait invalide → résolution par `stripe_customer_id` > email > metadata
- **login_failures dict non partagé entre workers** : remplacé par table `login_attempts` en DB (2026-03-06)
- **`None` crash dans `_derive_checks_overview`** : `data.get("dns_details", {})` retourne `None` quand la clé existe mais vaut `None` → ajouté `or {}` : `dns_det = data.get("dns_details", {}) or {}`

### Frontend
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
- `GET /public/stats` → stats anonymisées landing page

---

## 🧪 Tests

```bash
cd backend
.venv/bin/pytest tests/ -v --tb=short

# Variables d'env requises :
# JWT_SECRET_KEY=test-secret-key-for-ci-only-32chars
# CORS_ORIGINS=http://testserver
```

Fichiers : `tests/conftest.py`, `test_auth.py`, `test_scan_validation.py`, `test_rate_limit.py`, `test_report_service.py`

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

## 🆕 Fonctionnalités récentes (2026-03-06)

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

## 📋 Tâches en attente

- [ ] Configurer `JWT_SECRET_KEY` stable dans `.env` serveur (`openssl rand -hex 32`)
- [ ] Installer le cron de backup DB sur le serveur (voir ci-dessus)
- [ ] Surveiller les premières migrations argon2 dans les logs (rehash au prochain login de chaque user)

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
