#!/bin/bash
# ============================================================
#  deploy.sh — CyberHealth Scanner — Mise à jour Production
#
#  Usage (depuis le dossier racine du projet) :
#    chmod +x deploy.sh && ./deploy.sh
#
#  Ce script :
#    1. Build le frontend React (Vite)
#    2. Upload backend + frontend dist vers le serveur
#    3. Génère un script de déploiement côté serveur
#    4. L'exécute via ssh -t (terminal interactif → sudo OK)
#    5. Health check
# ============================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER="jay4pro@100.118.108.112"
APP_USER="cyberhealth"
REMOTE_BACKEND="/home/${APP_USER}/app/backend"
REMOTE_FRONTEND="/var/www/cyberhealth"
SERVICE_NAME="cyberhealth-api"
DOMAIN="scan.wezea.net"

# Couleurs
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}▶${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  🛡️  CyberHealth Scanner — Mise à jour Production${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""

# ── Étape 0 : Vérifications locales ──────────────────────────────────────────
log "Vérifications locales..."

[ -d "frontend" ] || err "Lance ce script depuis la racine du projet (dossier frontend/ introuvable)."
command -v node >/dev/null 2>&1 || err "Node.js non trouvé."
command -v npm  >/dev/null 2>&1 || err "npm non trouvé."
command -v ssh  >/dev/null 2>&1 || err "ssh non trouvé."
command -v scp  >/dev/null 2>&1 || err "scp non trouvé."

log "Test connexion SSH vers ${SERVER}..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "${SERVER}" "echo ok" >/dev/null 2>&1 \
  || err "Connexion SSH impossible. Vérifie ta clé SSH."
ok "Connexion SSH OK"

# ── Étape 1 : Build Frontend ──────────────────────────────────────────────────
echo ""
log "Build du frontend React..."

cd frontend
[ ! -d "node_modules" ] && { log "Installation npm..."; npm install --silent; }

log "Compilation Vite..."
npm run build 2>&1 | grep -v "^$"

[ -d "dist" ] || err "dist/ absent — vérifie les erreurs TypeScript ci-dessus."
ok "Frontend buildé → frontend/dist/"
cd ..

# ── Étape 2 : Packaging ───────────────────────────────────────────────────────
echo ""
log "Packaging..."

tar czf /tmp/cyberhealth-backend.tar.gz \
  --exclude='backend/venv' \
  --exclude='backend/__pycache__' \
  --exclude='backend/app/__pycache__' \
  --exclude='backend/app/services/__pycache__' \
  --exclude='backend/.env' \
  backend/

tar czf /tmp/cyberhealth-frontend.tar.gz -C frontend dist/
ok "Archives créées"

# ── Étape 3 : Génération du script serveur ───────────────────────────────────
#
# On écrit le script dans un fichier local puis on l'uploade.
# Il sera exécuté via ssh -t → le terminal est alloué → sudo peut demander
# le mot de passe normalement.
#
REMOTE_SCRIPT="/tmp/cyberhealth-deploy.sh"
cat > /tmp/cyberhealth-deploy-local.sh << SCRIPT
#!/bin/bash
set -euo pipefail

APP_USER="${APP_USER}"
REMOTE_BACKEND="${REMOTE_BACKEND}"
REMOTE_FRONTEND="${REMOTE_FRONTEND}"
SERVICE_NAME="${SERVICE_NAME}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  \${GREEN}✓\${NC} \$1"; }
warn() { echo -e "  \${YELLOW}⚠\${NC} \$1"; }
err()  { echo -e "  \${RED}✗\${NC} \$1"; exit 1; }

echo ""
echo "  ── Backend ──────────────────────────────────────────────"

sudo mkdir -p "\${REMOTE_BACKEND}"
sudo tar xzf /tmp/cyberhealth-backend.tar.gz \
  -C "/home/\${APP_USER}/app/" \
  --overwrite 2>/dev/null || true
sudo chown -R "\${APP_USER}:\${APP_USER}" "\${REMOTE_BACKEND}"
ok "Fichiers backend déployés"

echo ""
echo "  ── Dépendances Python ───────────────────────────────────"

VENV="/home/\${APP_USER}/app/backend/venv"
if [ ! -f "\${VENV}/bin/python3" ]; then
  warn "Venv absent — création..."
  sudo -u "\${APP_USER}" python3 -m venv "\${VENV}"
fi

sudo -u "\${APP_USER}" "\${VENV}/bin/pip" install \
  --quiet --upgrade pip
sudo -u "\${APP_USER}" "\${VENV}/bin/pip" install \
  --quiet -r "\${REMOTE_BACKEND}/requirements.txt"
ok "Dépendances Python installées"

echo ""
echo "  ── Validation Python ────────────────────────────────────"
sudo -u "\${APP_USER}" "\${VENV}/bin/python3" \
  -m py_compile "\${REMOTE_BACKEND}/app/main.py"
ok "Syntaxe Python OK"

echo ""
echo "  ── Frontend ─────────────────────────────────────────────"
sudo mkdir -p "\${REMOTE_FRONTEND}"
sudo tar xzf /tmp/cyberhealth-frontend.tar.gz \
  -C "\${REMOTE_FRONTEND}/" \
  --strip-components=1 \
  --overwrite
# Propriétaire : www-data si nginx, sinon cyberhealth
if id www-data &>/dev/null; then
  sudo chown -R www-data:www-data "\${REMOTE_FRONTEND}"
else
  sudo chown -R "\${APP_USER}:\${APP_USER}" "\${REMOTE_FRONTEND}"
fi
ok "Frontend déployé → \${REMOTE_FRONTEND}/"

echo ""
echo "  ── Service systemd ──────────────────────────────────────"

# Créer le service s'il n'existe pas encore
if [ ! -f "/etc/systemd/system/\${SERVICE_NAME}.service" ]; then
  warn "Service absent — création..."
  if [ -f "/tmp/cyberhealth-api.service" ]; then
    sudo cp /tmp/cyberhealth-api.service "/etc/systemd/system/\${SERVICE_NAME}.service"
  else
    sudo tee "/etc/systemd/system/\${SERVICE_NAME}.service" > /dev/null << SVCEOF
[Unit]
Description=CyberHealth Scanner API (FastAPI/Uvicorn)
After=network.target

[Service]
User=\${APP_USER}
Group=\${APP_USER}
WorkingDirectory=\${REMOTE_BACKEND}
ExecStart=\${VENV}/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2 --log-level info
Restart=always
RestartSec=5
EnvironmentFile=-\${REMOTE_BACKEND}/.env
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=\${REMOTE_BACKEND}

[Install]
WantedBy=multi-user.target
SVCEOF
  fi
  sudo systemctl daemon-reload
  sudo systemctl enable "\${SERVICE_NAME}"
  ok "Service créé et activé"
fi

# Nginx (1ère fois uniquement)
if [ ! -f "/etc/nginx/sites-available/cyberhealth" ] && command -v nginx &>/dev/null; then
  warn "Config nginx absente — création..."
  if [ -f "/tmp/cyberhealth-nginx.conf" ]; then
    sudo cp /tmp/cyberhealth-nginx.conf /etc/nginx/sites-available/cyberhealth
  else
    sudo tee /etc/nginx/sites-available/cyberhealth > /dev/null << NGXEOF
server {
    listen 80;
    server_name ${DOMAIN};
    root \${REMOTE_FRONTEND};
    index index.html;
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;
    location ~* \\.(js|css|png|jpg|ico|svg|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    location ~ ^/(scan|report|health|generate-pdf|docs|redoc) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \\\$host;
        proxy_set_header X-Real-IP \\\$remote_addr;
        proxy_set_header X-Forwarded-For \\\$remote_addr;
        proxy_read_timeout 120s;
    }
    location / {
        try_files \\\$uri \\\$uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
}
NGXEOF
  fi
  sudo ln -sf /etc/nginx/sites-available/cyberhealth /etc/nginx/sites-enabled/cyberhealth
  sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
  ok "Nginx configuré"
fi

echo ""
echo "  ── Redémarrage ──────────────────────────────────────────"
sudo systemctl restart "\${SERVICE_NAME}"
sleep 3

if command -v nginx &>/dev/null; then
  sudo nginx -t 2>/dev/null && sudo systemctl reload nginx
fi

ok "Services redémarrés"

# Nettoyage /tmp
rm -f /tmp/cyberhealth-backend.tar.gz \
       /tmp/cyberhealth-frontend.tar.gz \
       /tmp/cyberhealth-deploy.sh \
       /tmp/cyberhealth-api.service \
       /tmp/cyberhealth-nginx.conf

echo ""
SCRIPT

# ── Étape 4 : Upload de tout ─────────────────────────────────────────────────
echo ""
log "Upload vers ${SERVER}..."

scp -q /tmp/cyberhealth-backend.tar.gz       "${SERVER}:/tmp/cyberhealth-backend.tar.gz"
scp -q /tmp/cyberhealth-frontend.tar.gz      "${SERVER}:/tmp/cyberhealth-frontend.tar.gz"
scp -q /tmp/cyberhealth-deploy-local.sh      "${SERVER}:${REMOTE_SCRIPT}"

[ -f "infra/nginx.conf" ]              && scp -q "infra/nginx.conf"              "${SERVER}:/tmp/cyberhealth-nginx.conf"
[ -f "infra/cyberhealth-api.service" ] && scp -q "infra/cyberhealth-api.service" "${SERVER}:/tmp/cyberhealth-api.service"

ssh -o BatchMode=yes "${SERVER}" "chmod +x ${REMOTE_SCRIPT}"
ok "Fichiers uploadés"

# ── Étape 5 : Exécution du script sur le serveur (avec TTY → sudo OK) ────────
echo ""
log "Déploiement sur le serveur (sudo peut demander le mot de passe)..."
echo ""

ssh -t "${SERVER}" "bash ${REMOTE_SCRIPT}"

# ── Étape 6 : Health check ────────────────────────────────────────────────────
echo ""
log "Health check..."

STATUS=$(ssh -o BatchMode=yes "${SERVER}" "systemctl is-active ${SERVICE_NAME}" 2>/dev/null || echo "failed")

if [ "${STATUS}" = "active" ]; then
  ok "Service '${SERVICE_NAME}' : ACTIF ✓"
else
  warn "Service status : ${STATUS}"
  echo "Logs :"
  ssh -o BatchMode=yes "${SERVER}" "journalctl -u ${SERVICE_NAME} -n 30 --no-pager" || true
  err "Le service n'a pas démarré correctement."
fi

log "Test API..."
HTTP=$(ssh -o BatchMode=yes "${SERVER}" \
  "curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8000/scan \
   -H 'Content-Type: application/json' \
   -d '{\"domain\":\"wezea.net\"}' --max-time 30" 2>/dev/null || echo "000")

[ "${HTTP}" = "200" ] && ok "API répond HTTP ${HTTP} ✓" || warn "API a répondu HTTP ${HTTP}"

# ── Nettoyage local ───────────────────────────────────────────────────────────
rm -f /tmp/cyberhealth-backend.tar.gz \
      /tmp/cyberhealth-frontend.tar.gz \
      /tmp/cyberhealth-deploy-local.sh

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✓ Mise à jour déployée avec succès !${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  🌐 Site    : http://${DOMAIN}"
echo -e "  ⚙️  API     : http://${DOMAIN}/scan"
echo -e "  📋 Logs    : ssh ${SERVER} 'journalctl -u ${SERVICE_NAME} -f'"
echo -e "  🔄 Restart : ssh ${SERVER} 'sudo systemctl restart ${SERVICE_NAME}'"
echo ""
echo -e "  ${YELLOW}💡 HTTPS (si pas encore fait) :${NC}"
echo -e "     ssh ${SERVER} 'sudo apt install certbot python3-certbot-nginx -y'"
echo -e "     ssh ${SERVER} 'sudo certbot --nginx -d ${DOMAIN}'"
echo ""
