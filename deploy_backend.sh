#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_backend.sh — Déploiement backend CyberHealth (1 seule connexion SSH)
#
# Usage :
#   ./deploy_backend.sh                             → déploie tous les fichiers
#   ./deploy_backend.sh backend/app/main.py         → déploie un fichier précis
#   ./deploy_backend.sh backend/app/main.py backend/app/scanner.py  → plusieurs
# ─────────────────────────────────────────────────────────────────────────────

set -e

SERVER="jay4pro@100.118.108.112"
REMOTE_APP="/home/cyberhealth/app/backend/app"
LOCAL_APP="backend/app"
OWNER="cyberhealth:cyberhealth"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

# ── Liste des fichiers à déployer ──────────────────────────────────────────

if [ $# -gt 0 ]; then
  FILES=("$@")
else
  FILES=(
    "backend/app/main.py"
    "backend/app/auth.py"
    "backend/app/limiter.py"
    "backend/app/database.py"
    "backend/app/scanner.py"
    "backend/app/extra_checks.py"
    "backend/app/advanced_checks.py"
    "backend/app/models.py"
    "backend/app/scheduler.py"
    "backend/app/routers/auth_router.py"
    "backend/app/routers/payment_router.py"
    "backend/app/routers/scans_router.py"
    "backend/app/routers/admin_router.py"
    "backend/app/routers/monitoring_router.py"
    "backend/app/routers/contact_router.py"
    "backend/app/services/brevo_service.py"
    "backend/app/services/report_service.py"
    "backend/app/templates/report_template.html"
  )
fi

echo -e "\n${YELLOW}=== Déploiement Backend CyberHealth ===${NC}\n"

# ── Étape 1 : SCP de tous les fichiers vers /tmp (sans sudo) ───────────────

TO_DEPLOY=()
REMOTE_CMDS=""

for f in "${FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo -e "${YELLOW}⚠ Ignoré (introuvable) : ${f}${NC}"
    continue
  fi

  filename=$(basename "$f")
  remote_subdir=$(dirname "$f" | sed "s|^${LOCAL_APP}||")
  remote_dir="${REMOTE_APP}${remote_subdir}"
  tmp_path="/tmp/deploy_${filename}"

  echo -e "${YELLOW}→ SCP ${filename}...${NC}"
  scp "$f" "${SERVER}:${tmp_path}" || {
    echo -e "${RED}✗ Échec SCP pour ${filename}${NC}"; exit 1
  }

  TO_DEPLOY+=("$filename")
  # Construire la commande distante pour ce fichier
  REMOTE_CMDS+="sudo mkdir -p '${remote_dir}' && sudo mv '${tmp_path}' '${remote_dir}/${filename}' && sudo chown ${OWNER} '${remote_dir}/${filename}' && sudo chmod 644 '${remote_dir}/${filename}' && echo '✓ ${filename}' && "
done

if [ ${#TO_DEPLOY[@]} -eq 0 ]; then
  echo -e "${RED}Aucun fichier à déployer.${NC}"; exit 1
fi

# ── Étape 2 : Une seule connexion SSH pour mv + chown + restart ────────────

echo -e "\n${YELLOW}→ Application sur le serveur (1 mot de passe)...${NC}"
REMOTE_CMDS+="sudo systemctl restart cyberhealth-api && sleep 2 && sudo systemctl status cyberhealth-api | grep Active"

ssh -t "$SERVER" "$REMOTE_CMDS" || {
  echo -e "${RED}✗ Échec sur le serveur${NC}"; exit 1
}

echo -e "\n${GREEN}=== Déploiement terminé ✓ (${#TO_DEPLOY[@]} fichier(s)) ===${NC}\n"
