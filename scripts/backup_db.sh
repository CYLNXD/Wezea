#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# backup_db.sh — Sauvegarde SQLite avec rotation sur 30 jours
#
# Usage  :  ./scripts/backup_db.sh
# Cron   :  0 2 * * * /home/cyberhealth/app/scripts/backup_db.sh >> /home/cyberhealth/app/logs/backup.log 2>&1
#
# Variables d'environnement :
#   DB_PATH       chemin vers cyberhealth.db  (défaut : voir ci-dessous)
#   BACKUP_DIR    répertoire de destination    (défaut : voir ci-dessous)
#   RETENTION     jours de rétention locale    (défaut : 30)
#   S3_BUCKET     bucket S3/S3-compatible      (optionnel — ex. s3://mon-bucket/backups/)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config (surcharger via .env ou variables d'environnement) ─────────────────
DB_PATH="${DB_PATH:-/home/cyberhealth/app/backend/cyberhealth.db}"
BACKUP_DIR="${BACKUP_DIR:-/home/cyberhealth/backups}"
RETENTION="${RETENTION:-30}"
S3_BUCKET="${S3_BUCKET:-}"
DATE=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/cyberhealth_${DATE}.db"

# ── Créer le répertoire si nécessaire ─────────────────────────────────────────
mkdir -p "$BACKUP_DIR"

# ── Vérifier que la DB existe ─────────────────────────────────────────────────
if [ ! -f "$DB_PATH" ]; then
  echo "❌ DB introuvable : $DB_PATH"
  exit 1
fi

# ── Dump atomique via sqlite3 (.backup évite les lectures partielles) ─────────
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Sauvegarde de $DB_PATH → $BACKUP_FILE"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# ── Compresser le dump ────────────────────────────────────────────────────────
gzip -f "$BACKUP_FILE"
BACKUP_GZ="${BACKUP_FILE}.gz"
SIZE=$(du -sh "$BACKUP_GZ" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Backup OK — ${SIZE} → ${BACKUP_GZ}"

# ── Upload S3 (optionnel) ─────────────────────────────────────────────────────
if [ -n "$S3_BUCKET" ]; then
  if command -v aws &>/dev/null; then
    aws s3 cp "$BACKUP_GZ" "${S3_BUCKET}cyberhealth_${DATE}.db.gz" --quiet
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Uploadé sur S3 : ${S3_BUCKET}"
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠  aws CLI absent — upload S3 ignoré"
  fi
fi

# ── Rotation : supprimer les backups de plus de $RETENTION jours ──────────────
DELETED=$(find "$BACKUP_DIR" -name "cyberhealth_*.db.gz" -mtime "+${RETENTION}" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🗑  $DELETED ancien(s) backup(s) supprimé(s) (>${RETENTION}j)"
fi

# ── Vérifier l'espace disque restant ─────────────────────────────────────────
FREE_KB=$(df "$BACKUP_DIR" | awk 'NR==2 {print $4}')
FREE_GB=$(echo "scale=1; $FREE_KB / 1048576" | bc 2>/dev/null || echo "?")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 💾 Espace libre : ${FREE_GB} GB"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Backup terminé."
