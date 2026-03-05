#!/bin/bash
# ============================================================
#  deploy_quota_daily.sh — Quota /semaine → /jour + double verrou IP
#
#  Fichiers modifiés :
#    backend/app/models.py              → year_week→date_key, per_week→per_day
#    backend/app/main.py               → logique journalière + double verrou IP
#    frontend/src/lib/api.ts           → week_key→day_key, message erreur
#    frontend/src/pages/Dashboard.tsx  → tous les textes semaine→jour
#    frontend/src/components/PricingModal.tsx → "5 scans/semaine"→"5 scans/jour"
#
#  Migration SQL : rename year_week → date_key (table scan_rate_limits)
#
#  Usage :
#    chmod +x deploy_quota_daily.sh && ./deploy_quota_daily.sh
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
echo "  CyberHealth — Deploy Quota Daily"
echo "  • Quota: /semaine → /jour (anonyme + free)"
echo "  • Double verrou: cookie (1/j) + IP (5/j)"
echo "  • Migration SQL: year_week → date_key"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Test SSH ──────────────────────────────────────────────────────────────────
log "Test connexion SSH..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "${SERVER}" "echo ok" >/dev/null 2>&1 \
  || err "SSH impossible vers ${SERVER}"
ok "SSH OK"

# ── Build frontend ────────────────────────────────────────────────────────────
log "Build frontend..."
[ -d "frontend" ] || err "Dossier frontend/ introuvable."
(cd frontend && [ ! -d "node_modules" ] && npm install --silent; npm run build 2>&1 | tail -8)
[ -d "frontend/dist" ] || err "Build frontend échoué."
ok "Frontend buildé"

# ── Packaging ─────────────────────────────────────────────────────────────────
log "Packaging..."
tar czf /tmp/ch-daily-backend.tar.gz \
  backend/app/main.py \
  backend/app/models.py

tar czf /tmp/ch-daily-frontend.tar.gz -C frontend dist/
ok "Archives créées"

# ── Script serveur ────────────────────────────────────────────────────────────
cat > /tmp/ch-daily-server.sh << 'SCRIPT'
#!/bin/bash
set -e
APP_USER="cyberhealth"
BACKEND="/home/${APP_USER}/app/backend"
FRONTEND="/var/www/cyberhealth"
VENV="${BACKEND}/.venv"
[ ! -f "${VENV}/bin/python3" ] && VENV="${BACKEND}/venv"

echo ""
echo "  ── Backend — extraction ─────────────────────────────"
sudo tar xzf /tmp/ch-daily-backend.tar.gz -C "/home/${APP_USER}/app/" --overwrite
sudo chown ${APP_USER}:${APP_USER} \
  ${BACKEND}/app/main.py \
  ${BACKEND}/app/models.py
echo "  ✓ Fichiers extraits"

echo ""
echo "  ── Migration SQL — year_week → date_key ─────────────"
DB_URL=$(sudo -u ${APP_USER} bash -c 'cd /home/'${APP_USER}'/app && source .env 2>/dev/null || true; echo $DATABASE_URL')
if [ -z "${DB_URL}" ]; then
  # Essai via .env direct
  ENV_FILE="/home/${APP_USER}/app/.env"
  if [ -f "${ENV_FILE}" ]; then
    DB_URL=$(grep '^DATABASE_URL=' "${ENV_FILE}" | cut -d= -f2-)
  fi
fi

if [ -z "${DB_URL}" ]; then
  echo "  ⚠ DATABASE_URL introuvable — migration manuelle requise"
  echo "  ⚠ Exécutez manuellement dans psql :"
  echo "    ALTER TABLE scan_rate_limits ADD COLUMN IF NOT EXISTS date_key VARCHAR(10);"
  echo "    UPDATE scan_rate_limits SET date_key = CURRENT_DATE::text WHERE date_key IS NULL;"
  echo "    ALTER TABLE scan_rate_limits ALTER COLUMN date_key SET NOT NULL;"
  echo "    ALTER TABLE scan_rate_limits DROP COLUMN IF EXISTS year_week;"
  echo "    DROP INDEX IF EXISTS ix_client_week;"
  echo "    CREATE UNIQUE INDEX IF NOT EXISTS ix_client_day ON scan_rate_limits (client_id, date_key);"
else
  # Migration automatique via psql
  sudo -u ${APP_USER} psql "${DB_URL}" << 'SQL'
-- Étape 1 : ajouter la nouvelle colonne
ALTER TABLE scan_rate_limits ADD COLUMN IF NOT EXISTS date_key VARCHAR(10);

-- Étape 2 : les données existantes sont des quotas périmés (semaine) — on les invalide
--           en copiant une date arbitrairement ancienne
UPDATE scan_rate_limits SET date_key = '2000-01-01' WHERE date_key IS NULL;

-- Étape 3 : rendre obligatoire
ALTER TABLE scan_rate_limits ALTER COLUMN date_key SET NOT NULL;

-- Étape 4 : supprimer l'ancienne colonne et index
DROP INDEX IF EXISTS ix_client_week;
ALTER TABLE scan_rate_limits DROP COLUMN IF EXISTS year_week;

-- Étape 5 : créer le nouvel index unique
CREATE UNIQUE INDEX IF NOT EXISTS ix_client_day ON scan_rate_limits (client_id, date_key);
SQL
  echo "  ✓ Migration SQL terminée"
fi

echo ""
echo "  ── Validation Python ────────────────────────────────"
sudo -u ${APP_USER} ${VENV}/bin/python3 -m py_compile ${BACKEND}/app/main.py \
  && echo "  ✓ main.py OK" || { echo "  ✗ ERREUR main.py"; exit 1; }
sudo -u ${APP_USER} ${VENV}/bin/python3 -m py_compile ${BACKEND}/app/models.py \
  && echo "  ✓ models.py OK" || { echo "  ✗ ERREUR models.py"; exit 1; }

sudo -u ${APP_USER} ${VENV}/bin/python3 -c "
import sys
sys.path.insert(0, '${BACKEND}')
from app.models import ScanRateLimit
# Vérifier que date_key existe comme attribut SQLAlchemy
cols = [c.name for c in ScanRateLimit.__table__.columns]
assert 'date_key' in cols, f'date_key manquant: {cols}'
assert 'year_week' not in cols, 'year_week encore présent'
print('  ✓ ScanRateLimit.date_key OK')
from app.models import User
u = User()
_ = u.scan_limit_per_day
print('  ✓ User.scan_limit_per_day OK')
" || { echo "  ✗ ERREUR vérification modèle"; exit 1; }

echo ""
echo "  ── Frontend ─────────────────────────────────────────"
sudo tar xzf /tmp/ch-daily-frontend.tar.gz -C ${FRONTEND}/ --strip-components=1 --overwrite
sudo chown -R www-data:www-data ${FRONTEND} 2>/dev/null || sudo chown -R ${APP_USER}:${APP_USER} ${FRONTEND}
echo "  ✓ Frontend déployé"

echo ""
echo "  ── Redémarrage ──────────────────────────────────────"
sudo systemctl restart cyberhealth-api
sleep 3
sudo systemctl reload nginx 2>/dev/null || true

STATUS=$(systemctl is-active cyberhealth-api)
if [ "${STATUS}" = "active" ]; then
  echo "  ✓ Service: ${STATUS}"
else
  echo "  ✗ Service en erreur: ${STATUS}"
  sudo journalctl -u cyberhealth-api -n 30 --no-pager
  exit 1
fi

echo ""
echo "  ── Smoke tests ──────────────────────────────────────"
sleep 1
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
[ "${HTTP}" = "200" ] && echo "  ✓ /health → 200" || echo "  ⚠ /health → ${HTTP}"

# Test /scan/limits — vérifier que day_key est dans la réponse
LIMITS=$(curl -s http://localhost:8000/scan/limits 2>/dev/null || echo "{}")
echo "${LIMITS}" | grep -q "day_key" \
  && echo "  ✓ /scan/limits → day_key présent" \
  || echo "  ✗ /scan/limits → day_key absent (vérifiez)"
echo "${LIMITS}" | grep -q "week_key" \
  && echo "  ✗ /scan/limits → week_key encore présent !" \
  || echo "  ✓ /scan/limits → week_key supprimé"

rm -f /tmp/ch-daily-backend.tar.gz /tmp/ch-daily-frontend.tar.gz /tmp/ch-daily-server.sh
SCRIPT

# ── Upload ────────────────────────────────────────────────────────────────────
log "Upload vers ${SERVER}..."
scp -q /tmp/ch-daily-backend.tar.gz   "${SERVER}:/tmp/ch-daily-backend.tar.gz"
scp -q /tmp/ch-daily-frontend.tar.gz  "${SERVER}:/tmp/ch-daily-frontend.tar.gz"
scp -q /tmp/ch-daily-server.sh        "${SERVER}:/tmp/ch-daily-server.sh"
ssh -o BatchMode=yes "${SERVER}" "chmod +x /tmp/ch-daily-server.sh"
ok "Upload terminé"

# ── Exécution ─────────────────────────────────────────────────────────────────
log "Déploiement + migration sur le serveur..."
echo ""
ssh -t "${SERVER}" "bash /tmp/ch-daily-server.sh"

# ── Cleanup local ─────────────────────────────────────────────────────────────
rm -f /tmp/ch-daily-backend.tar.gz /tmp/ch-daily-frontend.tar.gz /tmp/ch-daily-server.sh

echo ""
echo "═══════════════════════════════════════════════════"
echo -e "${GREEN}  ✓ Déploiement terminé !${NC}"
echo ""
echo "  Ce qui a changé :"
echo "  • Anonyme  : 1 scan/jour par navigateur + 5/jour max par IP"
echo "  • Free     : 5 scans/jour (au lieu de 5/semaine)"
echo "  • Tous les textes du site reflètent ces nouvelles limites"
echo ""
echo "  Logs : ssh ${SERVER} 'journalctl -u cyberhealth-api -n 30'"
echo "═══════════════════════════════════════════════════"
echo ""
