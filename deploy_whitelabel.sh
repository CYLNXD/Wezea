#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_whitelabel.sh — White-branding Pro : PDF + UI Settings
# Modifie : models.py, database.py, auth_router.py, report_service.py,
#           main.py, report_template.html + frontend
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SERVER="jay4pro@100.118.108.112"
REMOTE_APP="/home/cyberhealth/app/backend/app"
DIST_DIR="/var/www/cyberhealth"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PKG_BACK="wezea_wb_backend_${TIMESTAMP}.tar.gz"
PKG_FRONT="wezea_wb_frontend_${TIMESTAMP}.tar.gz"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "▶ Build frontend..."
cd "$SCRIPT_DIR/frontend"
npm run build

echo "▶ Packaging frontend..."
tar -czf "/tmp/$PKG_FRONT" dist/

echo "▶ Packaging backend..."
cd "$SCRIPT_DIR/backend/app"
tar -czf "/tmp/$PKG_BACK" \
  models.py \
  database.py \
  routers/auth_router.py \
  routers/contact_router.py \
  routers/admin_router.py \
  routers/payment_router.py \
  routers/monitoring_router.py \
  routers/scans_router.py \
  routers/public_router.py \
  services/report_service.py \
  services/brevo_service.py \
  scheduler.py \
  main.py \
  templates/report_template.html

echo "▶ Upload vers $SERVER..."
scp "/tmp/$PKG_BACK"  "$SERVER:/tmp/"
scp "/tmp/$PKG_FRONT" "$SERVER:/tmp/"
scp "$SCRIPT_DIR/infra/nginx.conf" "$SERVER:/tmp/wezea_nginx.conf"

echo "▶ Déploiement sur le serveur..."
ssh -t "$SERVER" "
  set -e
  REMOTE_APP=$REMOTE_APP
  DIST_DIR=$DIST_DIR
  PKG_BACK=$PKG_BACK
  PKG_FRONT=$PKG_FRONT
  TIMESTAMP=$TIMESTAMP

  echo '  • Backup backend...'
  sudo cp -r \$REMOTE_APP \${REMOTE_APP}_backup_\$TIMESTAMP 2>/dev/null || true

  echo '  • Déploiement backend...'
  sudo tar -xzf /tmp/\$PKG_BACK -C \$REMOTE_APP --touch

  echo '  • Backup frontend...'
  sudo cp -r \$DIST_DIR \${DIST_DIR}_backup_\$TIMESTAMP 2>/dev/null || true

  echo '  • Déploiement frontend...'
  sudo tar -xzf /tmp/\$PKG_FRONT -C \$DIST_DIR --strip-components=1

  echo '  • Installation dépendances Python...'
  sudo /home/cyberhealth/app/backend/.venv/bin/pip install python-multipart -q

  echo '  • Permissions...'
  sudo chown -R cyberhealth:cyberhealth \$REMOTE_APP \$DIST_DIR
  sudo chmod -R 755 \$DIST_DIR

  echo '  • Mise à jour nginx...'
  sudo cp /tmp/wezea_nginx.conf /etc/nginx/sites-available/cyberhealth
  sudo nginx -t && sudo systemctl reload nginx
  rm -f /tmp/wezea_nginx.conf

  echo '  • Redémarrage du service (migration SQLite auto)...'
  sudo systemctl restart cyberhealth-api

  echo '  • Attente démarrage (8s)...'
  sleep 8

  echo '  • Smoke tests...'
  STATUS=\$(curl -s --max-time 10 --connect-timeout 5 -o /dev/null -w '%{http_code}' http://localhost:8000/health || echo '000')
  if [ \"\$STATUS\" = '200' ]; then
    echo '  ✅ /health OK'
  else
    echo \"  ⚠️  /health retourne \$STATUS (le service démarre peut-être encore)\"
  fi

  WB=\$(curl -s --max-time 10 --connect-timeout 5 -o /dev/null -w '%{http_code}' http://localhost:8000/auth/white-label || echo '000')
  if [ \"\$WB\" = '401' ] || [ \"\$WB\" = '403' ] || [ \"\$WB\" = '200' ]; then
    echo '  ✅ /auth/white-label accessible (réponse auth attendue)'
  else
    echo \"  ⚠️  /auth/white-label retourne \$WB\"
  fi

  echo '  • Nettoyage packages...'
  rm -f /tmp/\$PKG_BACK /tmp/\$PKG_FRONT

  echo ''
  echo '✅ Déploiement white-label terminé !'
"

echo ""
echo "✅ deploy_whitelabel terminé !"
echo "   • Espace client Pro → Settings → Marque blanche"
echo "   • PDF généré avec le nom/logo/couleur de l'agence"
echo "   Vérifiez : https://wezea.net"
