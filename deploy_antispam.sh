#!/bin/bash
# ============================================================
#  deploy_antispam.sh — Déploiement des fixes anti-spam
#
#  Fichiers modifiés :
#    backend/app/main.py               → /client-id endpoint, cookie wezea_cid
#    backend/app/routers/auth_router.py → rate limit login/register + lockout
#    backend/app/routers/contact_router.py → rate limit contact 5/h
#    frontend/src/lib/api.ts           → withCredentials, initClientId
#    frontend/src/App.tsx              → appel initClientId au démarrage
#
#  Usage :
#    chmod +x deploy_antispam.sh && ./deploy_antispam.sh
# ============================================================

set -e

SERVER="jay4pro@100.118.108.112"
APP_USER="cyberhealth"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
log()  { echo -e "${CYAN}▶${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo "═══════════════════════════════════════════════════"
echo "  CyberHealth — Deploy Anti-Spam Fixes"
echo "  • Rate limiting auth (login/register)"
echo "  • Rate limiting contact (5/h)"
echo "  • Cookie HttpOnly wezea_cid (Option B)"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Test SSH ──────────────────────────────────────────────────────────────────
log "Test connexion SSH..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "${SERVER}" "echo ok" >/dev/null 2>&1 \
  || err "SSH impossible vers ${SERVER}. Vérifiez votre connexion."
ok "SSH OK"

# ── Build frontend ────────────────────────────────────────────────────────────
log "Build frontend (api.ts + App.tsx modifiés)..."
[ -d "frontend" ] || err "Dossier frontend/ introuvable (lancez le script depuis la racine du projet)."
(cd frontend && [ ! -d "node_modules" ] && npm install --silent; npm run build 2>&1 | tail -8)
[ -d "frontend/dist" ] || err "Build frontend échoué — dossier dist/ absent."
ok "Frontend buildé"

# ── Packaging ─────────────────────────────────────────────────────────────────
log "Packaging des fichiers modifiés..."

# Backend : uniquement les 3 fichiers modifiés
tar czf /tmp/ch-antispam-backend.tar.gz \
  backend/app/main.py \
  backend/app/routers/auth_router.py \
  backend/app/routers/contact_router.py

# Frontend : tout le dist (build complet)
tar czf /tmp/ch-antispam-frontend.tar.gz -C frontend dist/

ok "Archives créées"

# ── Script serveur ────────────────────────────────────────────────────────────
cat > /tmp/ch-antispam-server.sh << SCRIPT
#!/bin/bash
set -e
APP_USER="${APP_USER}"
BACKEND="/home/\${APP_USER}/app/backend"
FRONTEND="/var/www/cyberhealth"
VENV="\${BACKEND}/.venv"
[ ! -f "\${VENV}/bin/python3" ] && VENV="\${BACKEND}/venv"

echo ""
echo "  ── Backend — extraction des fichiers modifiés ───────"
sudo tar xzf /tmp/ch-antispam-backend.tar.gz -C "/home/\${APP_USER}/app/" --overwrite
sudo chown -R \${APP_USER}:\${APP_USER} \${BACKEND}/app/main.py
sudo chown -R \${APP_USER}:\${APP_USER} \${BACKEND}/app/routers/auth_router.py
sudo chown -R \${APP_USER}:\${APP_USER} \${BACKEND}/app/routers/contact_router.py
echo "  ✓ Fichiers extraits"

echo ""
echo "  ── Validation syntaxe Python ────────────────────────"
sudo -u \${APP_USER} \${VENV}/bin/python3 -m py_compile \${BACKEND}/app/main.py \
  && echo "  ✓ main.py OK" || { echo "  ✗ ERREUR main.py"; exit 1; }
sudo -u \${APP_USER} \${VENV}/bin/python3 -m py_compile \${BACKEND}/app/routers/auth_router.py \
  && echo "  ✓ auth_router.py OK" || { echo "  ✗ ERREUR auth_router.py"; exit 1; }
sudo -u \${APP_USER} \${VENV}/bin/python3 -m py_compile \${BACKEND}/app/routers/contact_router.py \
  && echo "  ✓ contact_router.py OK" || { echo "  ✗ ERREUR contact_router.py"; exit 1; }

echo ""
echo "  ── Vérification imports (slowapi + time) ────────────"
sudo -u \${APP_USER} \${VENV}/bin/python3 -c "
import sys
sys.path.insert(0, '\${BACKEND}')
from app.limiter import limiter
from app.routers.auth_router import router as auth_router, _check_lockout, _record_failure
from app.routers.contact_router import router as contact_router
print('  ✓ Limiter OK')
print('  ✓ Auth lockout functions OK')
print('  ✓ Contact router OK')
" || { echo "  ✗ ERREUR imports"; exit 1; }

echo ""
echo "  ── Frontend ─────────────────────────────────────────"
sudo tar xzf /tmp/ch-antispam-frontend.tar.gz -C \${FRONTEND}/ --strip-components=1 --overwrite
sudo chown -R www-data:www-data \${FRONTEND} 2>/dev/null || sudo chown -R \${APP_USER}:\${APP_USER} \${FRONTEND}
echo "  ✓ Frontend déployé"

echo ""
echo "  ── Redémarrage ──────────────────────────────────────"
sudo systemctl restart cyberhealth-api
sleep 3
sudo systemctl reload nginx 2>/dev/null || true
STATUS=\$(systemctl is-active cyberhealth-api)
if [ "\${STATUS}" = "active" ]; then
  echo "  ✓ Service: \${STATUS}"
else
  echo "  ✗ Service en erreur : \${STATUS}"
  sudo journalctl -u cyberhealth-api -n 20 --no-pager
  exit 1
fi

echo ""
echo "  ── Smoke tests ──────────────────────────────────────"
sleep 1
HTTP=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
[ "\${HTTP}" = "200" ] && echo "  ✓ /health → 200" || echo "  ⚠ /health → \${HTTP} (check logs)"

HTTP=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/client-id 2>/dev/null || echo "000")
[ "\${HTTP}" = "200" ] && echo "  ✓ /client-id → 200" || echo "  ✗ /client-id → \${HTTP} (ERREUR)"

rm -f /tmp/ch-antispam-backend.tar.gz /tmp/ch-antispam-frontend.tar.gz /tmp/ch-antispam-server.sh
SCRIPT

# ── Upload ────────────────────────────────────────────────────────────────────
log "Upload vers ${SERVER}..."
scp -q /tmp/ch-antispam-backend.tar.gz   "${SERVER}:/tmp/ch-antispam-backend.tar.gz"
scp -q /tmp/ch-antispam-frontend.tar.gz  "${SERVER}:/tmp/ch-antispam-frontend.tar.gz"
scp -q /tmp/ch-antispam-server.sh        "${SERVER}:/tmp/ch-antispam-server.sh"
ssh -o BatchMode=yes "${SERVER}" "chmod +x /tmp/ch-antispam-server.sh"
ok "Upload terminé"

# ── Exécution sur le serveur ──────────────────────────────────────────────────
log "Déploiement sur le serveur (sudo peut demander le mot de passe)..."
echo ""
ssh -t "${SERVER}" "bash /tmp/ch-antispam-server.sh"

# ── Cleanup local ─────────────────────────────────────────────────────────────
rm -f /tmp/ch-antispam-backend.tar.gz /tmp/ch-antispam-frontend.tar.gz /tmp/ch-antispam-server.sh

echo ""
echo "═══════════════════════════════════════════════════"
echo -e "${GREEN}  ✓ Anti-spam fixes déployés !${NC}"
echo ""
echo "  Vérifications manuelles recommandées :"
echo "  • Login brute-force : 6+ tentatives → 429 attendu"
echo "  • Contact form : 6+ soumissions/h → 429 attendu"
echo "  • Cookie : curl -I https://scan.wezea.net/client-id"
echo "             → Set-Cookie: wezea_cid=... HttpOnly; Secure"
echo ""
echo "  Logs : ssh ${SERVER} 'journalctl -u cyberhealth-api -n 30'"
echo "═══════════════════════════════════════════════════"
echo ""
