# CLAUDE.md — Mémoire du projet CyberHealth Scanner
> Ce fichier est lu en PREMIER à chaque nouvelle session. Il doit être mis à jour à chaque modification importante.
> Dernière mise à jour : 2026-03-06 (session 15)

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

## 🆕 Fonctionnalités récentes (2026-03-06, session 15)

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

## 📋 Tâches en attente

- [ ] Configurer `JWT_SECRET_KEY` stable dans `.env` serveur (`openssl rand -hex 32`)
- [ ] Installer le cron de backup DB sur le serveur (voir ci-dessus)
- [ ] Surveiller les premières migrations argon2 dans les logs (rehash au prochain login de chaque user)
- [ ] Ajouter `FRONTEND_URL=https://wezea.net` dans `.env` serveur (utilisé par les emails de reset mot de passe)

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
