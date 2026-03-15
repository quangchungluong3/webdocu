#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   🏪  WEBDOCU — CÀI ĐẶT VPS              ║"
echo "╚══════════════════════════════════════════╝"

apt update -y && apt upgrade -y
apt install -y python3 python3-pip nginx certbot python3-certbot-nginx git ufw

pip3 install fastapi uvicorn python-multipart aiofiles

mkdir -p /var/www/webdocu/static
mkdir -p /var/www/webdocu/uploads

cat > /etc/systemd/system/webdocu.service << 'SERVICE'
[Unit]
Description=Webdocu FastAPI
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/webdocu
Environment="ADMIN_USERNAME=admin"
Environment="ADMIN_PASSWORD=chodocus123"
Environment="PORT=8000"
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable webdocu

cat > /etc/nginx/sites-available/webdocu << 'NGINX'
server {
    listen 80;
    server_name YOUR_DOMAIN.COM;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/webdocu /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

ufw allow ssh
ufw allow 'Nginx Full'
ufw --force enable

echo ""
echo "✅ Xong! Bước tiếp theo:"
echo "1. cp -r ~/webdocu/* /var/www/webdocu/"
echo "2. nano /etc/nginx/sites-available/webdocu"
echo "   → Thay YOUR_DOMAIN.COM"
echo "3. nano /etc/systemd/system/webdocu.service"
echo "   → Thay ADMIN_PASSWORD"
echo "4. systemctl start webdocu && systemctl reload nginx"
echo "5. certbot --nginx -d YOUR_DOMAIN.COM"
