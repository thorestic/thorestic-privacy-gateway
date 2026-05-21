#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="/opt/thorestic-gateway/certs"
CERT_FILE="$CERT_DIR/thorestic.crt"
KEY_FILE="$CERT_DIR/thorestic.key"
NGINX_CONF="/etc/nginx/sites-available/thorestic-gateway"

mkdir -p "$CERT_DIR"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
  echo "Certificates already exist at $CERT_DIR"
  echo "To regenerate, delete them first:"
  echo "  rm $CERT_FILE $KEY_FILE"
  echo "  then re-run this script"
else
  echo "Generating self-signed certificate..."
  openssl req -x509 -nodes -days 3650 \
    -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/CN=thorestic-gateway/O=Thorestic/C=JO" \
    -addext "subjectAltName=IP:192.168.50.1,DNS:thorestic.test,DNS:gateway.thorestic"

  chmod 600 "$KEY_FILE"
  chmod 644 "$CERT_FILE"
  echo "Certificate generated at $CERT_DIR"
fi

if [ -f "$NGINX_CONF" ]; then
  if grep -q "ssl_certificate" "$NGINX_CONF"; then
    echo "Nginx already configured for SSL."
  else
    echo "Updating Nginx config for HTTPS..."
    cat > "$NGINX_CONF" <<'NGINX'
server {
    listen 80;
    server_name 192.168.50.1 thorestic.test gateway.thorestic;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name 192.168.50.1 thorestic.test gateway.thorestic;

    ssl_certificate /opt/thorestic-gateway/certs/thorestic.crt;
    ssl_certificate_key /opt/thorestic-gateway/certs/thorestic.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    location /stream/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        chunked_transfer_encoding off;
        proxy_cache off;
    }
}
NGINX
    echo "Nginx config updated."
  fi
else
  echo "Nginx config not found at $NGINX_CONF"
  echo "You may need to create the Nginx site config manually."
fi

echo ""
echo "To apply changes:"
echo "  sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "Then access the dashboard at:"
echo "  https://192.168.50.1"
echo ""
echo "Note: Your browser will show a security warning since it's self-signed."
echo "      Click 'Advanced' > 'Proceed' to accept."
