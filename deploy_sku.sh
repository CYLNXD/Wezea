#!/bin/bash
# ─── Déploiement thème Skeuomorphique ─────────────────────────────────────────
set -e

SERVER="jay4pro@100.118.108.112"
LOCAL_DIST="$(dirname "$0")/dist_sku"

echo "🚀 Transfert du build vers le serveur..."
ssh "$SERVER" "mkdir -p /tmp/cyberhealth-dist-sku"
scp -r "$LOCAL_DIST"/* "$SERVER:/tmp/cyberhealth-dist-sku/"

echo "🔧 Création du script distant..."
cat > /tmp/install_sku.sh << 'REMOTE'
#!/bin/bash
set -e
sudo rm -rf /var/www/cyberhealth
sudo mkdir -p /var/www/cyberhealth
sudo cp -r /tmp/cyberhealth-dist-sku/* /var/www/cyberhealth/
sudo chown -R www-data:www-data /var/www/cyberhealth
echo "✓ Frontend déployé dans /var/www/cyberhealth"
sudo systemctl reload nginx
echo "✓ Nginx rechargé"
echo ""
echo "✅ Déploiement terminé — https://wezea.net"
REMOTE

scp /tmp/install_sku.sh "$SERVER:/tmp/install_sku.sh"
echo "📦 Installation..."
ssh -t "$SERVER" "bash /tmp/install_sku.sh"
