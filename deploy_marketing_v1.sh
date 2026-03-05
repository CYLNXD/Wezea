#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_marketing_v1.sh — Landing page : pricing + agences/MSP + fixes branding
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SERVER="jay4pro@100.118.108.112"
REMOTE_FRONT="/home/cyberhealth/app/frontend"
DIST_DIR="/var/www/cyberhealth"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE="wezea_marketing_v1_${TIMESTAMP}.tar.gz"

echo "▶ Build frontend..."
cd "$(dirname "$0")/frontend"
npm run build

echo "▶ Packaging dist..."
tar -czf "/tmp/$PACKAGE" dist/

echo "▶ Upload vers $SERVER..."
scp "/tmp/$PACKAGE" "$SERVER:/tmp/"

echo "▶ Déploiement sur le serveur (sudo requis — entrez le mot de passe si demandé)..."
ssh -t "$SERVER" "
  set -e
  echo '  • Backup...'
  sudo cp -r $DIST_DIR ${DIST_DIR}_backup_${TIMESTAMP} 2>/dev/null || true

  echo '  • Extraction...'
  sudo tar -xzf /tmp/$PACKAGE -C $DIST_DIR --strip-components=1

  echo '  • Permissions...'
  sudo chown -R cyberhealth:cyberhealth $DIST_DIR

  echo '  • Nettoyage...'
  rm -f /tmp/$PACKAGE

  echo '  • Smoke test branding...'
  if sudo grep -r 'CyberHealth' $DIST_DIR --include='*.js' -ql 2>/dev/null; then
    echo '  ❌ CyberHealth encore présent dans le bundle'
  else
    echo '  ✅ CyberHealth absent du bundle'
  fi

  if sudo grep -r '9,90' $DIST_DIR --include='*.js' -ql 2>/dev/null; then
    echo '  ✅ Section tarifs trouvée dans le bundle'
  else
    echo '  ⚠️  Section tarifs NON trouvée'
  fi

  echo ''
  echo '✅ Déploiement terminé !'
"

echo ""
echo "Vérifiez : https://wezea.net"
echo "  • Section agences/MSP visible"
echo "  • Section tarifs (Free / Starter 9,90€ / Pro 19,90€)"
echo "  • Testimonial : 'Sans Wezea je l'aurais raté'"
echo "  • Hero : 'en moins de 60 secondes'"
