#!/bin/bash
# ============================================================
# deploy_extra_checks.sh
# Deploy the 4 new security scan checks to the CyberHealth server
#
# Run from your LOCAL machine:
#   chmod +x deploy_extra_checks.sh && ./deploy_extra_checks.sh
# ============================================================

set -e

SERVER="jay4pro@100.118.108.112"
REMOTE_APP="/home/cyberhealth/app/backend/app"
REMOTE_SVC="/home/cyberhealth/app/backend/app/services"

echo "======================================================"
echo "  CyberHealth — Deploy Extra Security Checks"
echo "======================================================"

# ── 1. Upload fichiers vers /tmp (accessible par jay4pro) ─
echo ""
echo "▶ Uploading files to /tmp …"
scp extra_checks.py "${SERVER}:/tmp/extra_checks.py"
scp patch_integrate_extra_checks.py "${SERVER}:/tmp/patch_integrate_extra_checks.py"
echo "  ✓ Files uploaded to /tmp"

# ── 2. Copie vers le bon dossier avec sudo ────────────────
echo ""
echo "▶ Moving extra_checks.py to services folder (sudo) …"
ssh "${SERVER}" "
  sudo cp /tmp/extra_checks.py ${REMOTE_SVC}/extra_checks.py
  sudo chown cyberhealth:cyberhealth ${REMOTE_SVC}/extra_checks.py
  sudo chmod 644 ${REMOTE_SVC}/extra_checks.py
"
echo "  ✓ extra_checks.py installed"

# ── 3. Install dependencies dans le venv cyberhealth ─────
echo ""
echo "▶ Installing Python dependencies (dnspython, httpx) …"
ssh "${SERVER}" "
  sudo -u cyberhealth /home/cyberhealth/app/backend/venv/bin/pip install --quiet dnspython httpx 2>&1 | tail -5
"
echo "  ✓ Dependencies installed"

# ── 4. Run patch script (en tant que cyberhealth) ─────────
echo ""
echo "▶ Running patch script on server …"
ssh "${SERVER}" "
  sudo cp /tmp/patch_integrate_extra_checks.py /tmp/patch_integrate_extra_checks.py
  sudo -u cyberhealth /home/cyberhealth/app/backend/venv/bin/python3 /tmp/patch_integrate_extra_checks.py
"

# ── 5. Validate Python syntax ────────────────────────────
echo ""
echo "▶ Validating Python syntax …"
ssh "${SERVER}" "
  sudo -u cyberhealth /home/cyberhealth/app/backend/venv/bin/python3 -m py_compile /home/cyberhealth/app/backend/app/main.py && echo '  ✓ main.py syntax OK'
  sudo -u cyberhealth /home/cyberhealth/app/backend/venv/bin/python3 -m py_compile /home/cyberhealth/app/backend/app/services/extra_checks.py && echo '  ✓ extra_checks.py syntax OK'
"

# ── 6. Restart service ────────────────────────────────────
echo ""
echo "▶ Restarting cyberhealth-api service …"
ssh "${SERVER}" "sudo systemctl restart cyberhealth-api"
sleep 3

# ── 7. Health check ───────────────────────────────────────
echo ""
echo "▶ Health check …"
STATUS=$(ssh "${SERVER}" "sudo systemctl is-active cyberhealth-api")
if [ "$STATUS" = "active" ]; then
    echo "  ✓ Service is running (active)"
else
    echo "  ✗ Service status: ${STATUS}"
    echo "  Showing last 30 log lines:"
    ssh "${SERVER}" "journalctl -u cyberhealth-api -n 30 --no-pager"
    exit 1
fi

# ── 8. Quick API test ─────────────────────────────────────
echo ""
echo "▶ Quick API test (scan wezea.net) …"
ssh "${SERVER}" "curl -s -X POST http://localhost:8000/scan \
  -H 'Content-Type: application/json' \
  -d '{\"domain\": \"wezea.net\"}' | python3 -m json.tool | head -60" || true

echo ""
echo "======================================================"
echo "  ✓ Deployment complete!"
echo "  New checks active:"
echo "    • En-têtes HTTP (CSP, HSTS, X-Frame-Options…)"
echo "    • Sécurité Email (SPF, DKIM, DMARC)"
echo "    • Exposition Technologique (Server, CMS, frameworks)"
echo "    • Réputation du Domaine (DNSBL)"
echo "======================================================"
