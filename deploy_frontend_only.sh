#!/bin/bash
# ============================================================
#  deploy_frontend_only.sh — Déploiement frontend uniquement
#  Lance depuis le dossier racine du projet :
#    chmod +x deploy_frontend_only.sh && ./deploy_frontend_only.sh
# ============================================================

set -e

SERVER="jay4pro@100.118.108.112"
FRONTEND_DIR="/var/www/cyberhealth"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}✓${NC} $1"; }
log() { echo -e "${CYAN}▶${NC} $1"; }
err() { echo -e "${RED}✗${NC} $1"; exit 1; }

echo ""
echo "═══════════════════════════════════════════"
echo "  CyberHealth — Deploy Frontend Only"
echo "═══════════════════════════════════════════"

log "Test connexion SSH..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "${SERVER}" "echo ok" >/dev/null 2>&1 \
  || err "SSH impossible vers ${SERVER}"
ok "SSH OK"

log "Build frontend..."
[ -d "frontend" ] || err "Dossier frontend/ introuvable."
(cd frontend && npm install --silent && npm run build) || err "Build frontend échoué."
ok "Build OK"

log "Packaging frontend..."
tar czf /tmp/ch-frontend.tar.gz -C frontend dist/
ok "Archive créée"

log "Upload vers serveur..."
scp -q /tmp/ch-frontend.tar.gz "${SERVER}:/tmp/ch-frontend.tar.gz"
ok "Upload OK"

log "Déploiement sur le serveur..."
ssh -t "${SERVER}" "
  sudo tar xzf /tmp/ch-frontend.tar.gz -C ${FRONTEND_DIR}/ --strip-components=1 --overwrite && \
  sudo chown -R www-data:www-data ${FRONTEND_DIR} 2>/dev/null || sudo chown -R cyberhealth:cyberhealth ${FRONTEND_DIR} && \
  sudo systemctl reload nginx 2>/dev/null || true && \
  rm -f /tmp/ch-frontend.tar.gz && \
  echo 'Frontend déployé ✓'
"

rm -f /tmp/ch-frontend.tar.gz

echo ""
echo "═══════════════════════════════════════════"
echo -e "${GREEN}  ✓ Frontend déployé !${NC}"
echo "  Vérifiez sur https://wezea.net"
echo "═══════════════════════════════════════════"
echo ""
