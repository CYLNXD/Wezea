# CLAUDE.md — Mémoire du projet CyberHealth Scanner
> Ce fichier est lu en PREMIER à chaque nouvelle session. Il doit être mis à jour à chaque modification importante.
> Dernière mise à jour : 2026-03-05

---

## 🗂️ Structure du projet

```
cyberhealth-scanner/
├── frontend/          # React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── pages/     # Dashboard, LoginPage, HistoryPage, AdminPage, ContactPage, LegalPage, ClientSpace
│       ├── components/ # PricingModal, etc.
│       └── index.css  # Variables CSS + classes skeuomorphiques globales
├── backend/           # FastAPI + SQLite + SQLAlchemy
│   └── app/
│       ├── main.py
│       ├── models.py
│       ├── database.py
│       ├── extra_checks.py   # Checks supplémentaires (doit être dans git !)
│       └── routers/
│           ├── auth_router.py
│           ├── payment_router.py
│           └── scan_router.py
├── .github/workflows/deploy.yml  # CI/CD GitHub Actions (self-hosted runner)
├── requirements.txt   # Backend Python deps
└── CLAUDE.md          # CE FICHIER
```

---

## 🖥️ Infrastructure & Déploiement

- **Runner CI/CD** : GitHub Actions self-hosted runner sur le serveur
- **Chemin serveur** : `/home/user/cyberhealth-scanner/` (ou similaire)
- **Virtualenv** : `.venv/` (avec le point — NE PAS confondre avec `venv/`)
- **Process manager** : systemd + gunicorn
- **Frontend** : build Vite → servi par nginx
- **Backend** : FastAPI sur gunicorn, port 8000

### Points critiques du deploy.yml
```yaml
rsync --exclude='.venv/' --exclude='venv/' --exclude='*.db' --exclude='*.sqlite'
      --exclude='uploads/' --exclude='logs/'
# IMPORTANT : .venv/ avec le point ! rsync --delete détruirait autrement le venv
pip: utiliser .venv/bin/pip (pas pip global)
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
fastapi
uvicorn
gunicorn==23.0.0      # Requis pour systemd
sqlalchemy
bcrypt==4.0.1         # PINNÉ — 4.2+ incompatible avec passlib 1.7.4
passlib[bcrypt]
python-jose
stripe
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
- Migration ajoutée : `stripe_customer_id TEXT` sur table `users`

### `models.py`
- `User` model : `stripe_customer_id = Column(String(64), nullable=True, index=True)`

### `auth_router.py`
- `UserResponse` contient : `id, email, name, plan, is_admin, created_at`
- `/auth/me` et `/auth/profile` retournent `is_admin=bool(current_user.is_admin)`

### `payment_router.py`
- Résolution user depuis Stripe webhook : `stripe_customer_id` → email → `metadata.user_id`
- Sauvegarde `stripe_customer_id` sur `checkout.session.completed`

---

## 📋 Tâches en attente

- [ ] Rien de bloquant actuellement

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
sudo journalctl -u cyberhealth -n 50 --no-pager

# Redémarrer le service
sudo systemctl restart cyberhealth

# Vérifier état
sudo systemctl status cyberhealth

# DB SQLite (attention, ne pas wiper)
sqlite3 /path/to/prod.db "SELECT email, plan, is_admin FROM users;"
```
