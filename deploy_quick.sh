#!/bin/bash
# ============================================================
#  deploy_quick.sh — Déploiement rapide backend + frontend
#  Lance depuis le dossier racine du projet :
#    chmod +x deploy_quick.sh && ./deploy_quick.sh
# ============================================================

set -e

SERVER="jay4pro@100.118.108.112"
APP_USER="cyberhealth"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()  { echo -e "${GREEN}✓${NC} $1"; }
log() { echo -e "${CYAN}▶${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo "═══════════════════════════════════════════"
echo "  CyberHealth — Deploy rapide"
echo "═══════════════════════════════════════════"

# ── Test SSH ──────────────────────────────────────────────────────────────────
log "Test connexion SSH..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "${SERVER}" "echo ok" >/dev/null 2>&1 \
  || err "SSH impossible."
ok "SSH OK"

# ── Build frontend ────────────────────────────────────────────────────────────
log "Build frontend..."
cd frontend
[ ! -d "node_modules" ] && npm install --silent
npm run build 2>&1 | tail -5
[ -d "dist" ] || err "Build frontend échoué."
ok "Frontend buildé"
cd ..

# ── Package ───────────────────────────────────────────────────────────────────
log "Packaging..."
tar czf /tmp/ch-backend.tar.gz \
  --exclude='backend/venv' --exclude='backend/.venv' \
  --exclude='backend/__pycache__' \
  --exclude='backend/app/__pycache__' \
  --exclude='backend/app/services/__pycache__' \
  --exclude='backend/app/routers/__pycache__' \
  --exclude='backend/.env' \
  backend/
tar czf /tmp/ch-frontend.tar.gz -C frontend dist/
ok "Archives créées"

# ── Générer le script serveur ─────────────────────────────────────────────────
cat > /tmp/ch-deploy-server.sh << SCRIPT
#!/bin/bash
set -e
APP_USER="${APP_USER}"
BACKEND="/home/\${APP_USER}/app/backend"
FRONTEND="/var/www/cyberhealth"

echo ""
echo "  ── Backend ──────────────────────────────────────────"
sudo tar xzf /tmp/ch-backend.tar.gz -C "/home/\${APP_USER}/app/" --overwrite
sudo chown -R \${APP_USER}:\${APP_USER} \${BACKEND}

# Vérifier que extra_checks.py est au bon endroit
if [ -f "\${BACKEND}/app/extra_checks.py" ]; then
  echo "  ✓ extra_checks.py : \${BACKEND}/app/extra_checks.py"
else
  echo "  ✗ ERREUR : extra_checks.py introuvable !"
  exit 1
fi

# Supprimer l'ancienne version dans services/ si elle existe (mauvais chemin)
[ -f "\${BACKEND}/app/services/extra_checks.py" ] && sudo rm "\${BACKEND}/app/services/extra_checks.py" && echo "  ✓ Ancienne version services/ supprimée"

# Validation syntaxe Python
VENV="\${BACKEND}/.venv"
[ ! -f "\${VENV}/bin/python3" ] && VENV="\${BACKEND}/venv"
sudo -u \${APP_USER} \${VENV}/bin/python3 -m py_compile \${BACKEND}/app/scanner.py && echo "  ✓ scanner.py OK"
sudo -u \${APP_USER} \${VENV}/bin/python3 -m py_compile \${BACKEND}/app/extra_checks.py && echo "  ✓ extra_checks.py OK"
sudo -u \${APP_USER} \${VENV}/bin/python3 -m py_compile \${BACKEND}/app/main.py && echo "  ✓ main.py OK"

# Test import
sudo -u \${APP_USER} \${VENV}/bin/python3 -c "
import sys
sys.path.insert(0, '\${BACKEND}')
from app.extra_checks import HttpHeaderAuditor, EmailSecurityAuditor, TechExposureAuditor, ReputationAuditor
h = HttpHeaderAuditor('test.com', 'en')
print('  ✓ Imports OK — EN:', h._t('FR','EN'), '| FR:', HttpHeaderAuditor('test.com','fr')._t('FR','EN'))
"

echo ""
echo "  ── Frontend ─────────────────────────────────────────"
sudo tar xzf /tmp/ch-frontend.tar.gz -C \${FRONTEND}/ --strip-components=1 --overwrite
sudo chown -R www-data:www-data \${FRONTEND} 2>/dev/null || sudo chown -R \${APP_USER}:\${APP_USER} \${FRONTEND}
echo "  ✓ Frontend déployé"

echo ""
echo "  ── Redémarrage ──────────────────────────────────────"
sudo systemctl restart cyberhealth-api
sleep 3
sudo systemctl reload nginx 2>/dev/null || true
STATUS=\$(systemctl is-active cyberhealth-api)
echo "  ✓ Service: \${STATUS}"

rm -f /tmp/ch-backend.tar.gz /tmp/ch-frontend.tar.gz /tmp/ch-deploy-server.sh
SCRIPT

# ── Upload ────────────────────────────────────────────────────────────────────
log "Upload..."
scp -q /tmp/ch-backend.tar.gz      "${SERVER}:/tmp/ch-backend.tar.gz"
scp -q /tmp/ch-frontend.tar.gz     "${SERVER}:/tmp/ch-frontend.tar.gz"
scp -q /tmp/ch-deploy-server.sh    "${SERVER}:/tmp/ch-deploy-server.sh"
ssh -o BatchMode=yes "${SERVER}" "chmod +x /tmp/ch-deploy-server.sh"
ok "Upload terminé"

# ── Exécution sur le serveur avec TTY (sudo OK) ───────────────────────────────
log "Déploiement sur le serveur (sudo va demander le mot de passe)..."
echo ""
ssh -t "${SERVER}" "bash /tmp/ch-deploy-server.sh"

ok "Déploiement terminé !"

# ── Cleanup local ─────────────────────────────────────────────────────────────
rm -f /tmp/ch-backend.tar.gz /tmp/ch-frontend.tar.gz /tmp/ch-deploy-server.sh

echo ""
echo "═══════════════════════════════════════════"
echo -e "${GREEN}  ✓ Tout déployé !${NC}"
echo "  Logs : ssh ${SERVER} 'journalctl -u cyberhealth-api -n 30'"
echo "═══════════════════════════════════════════"
echo ""
