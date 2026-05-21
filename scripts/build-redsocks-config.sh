#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/thorestic-gateway/configs/proxy.env"
OUT_FILE="/etc/redsocks-thorestic.conf"
LOG_FILE="/var/log/thorestic-gateway/redsocks.log"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${PROXY_TYPE:?Missing PROXY_TYPE}"
: "${PROXY_HOST:?Missing PROXY_HOST}"
: "${PROXY_PORT:?Missing PROXY_PORT}"
: "${PROXY_LOCAL_PORT:=12345}"

esc() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

PROXY_IP="$(getent ahostsv4 "$PROXY_HOST" | awk '{print $1; exit}')"
if [ -z "$PROXY_IP" ]; then
  PROXY_IP="$PROXY_HOST"
fi

LOGIN_LINE=""
PASSWORD_LINE=""

if [ "${PROXY_USERNAME:-}" != "" ]; then
  LOGIN_LINE="    login = \"$(esc "$PROXY_USERNAME")\";"
fi

if [ "${PROXY_PASSWORD:-}" != "" ]; then
  PASSWORD_LINE="    password = \"$(esc "$PROXY_PASSWORD")\";"
fi

cat > "$OUT_FILE" <<CONF
base {
    log_debug = on;
    log_info = on;
    log = "file:$LOG_FILE";
    daemon = off;
    redirector = iptables;
}

redsocks {
    local_ip = 0.0.0.0;
    local_port = $PROXY_LOCAL_PORT;

    ip = $PROXY_IP;
    port = $PROXY_PORT;
    type = $PROXY_TYPE;
$LOGIN_LINE
$PASSWORD_LINE
}
CONF

chmod 600 "$OUT_FILE"
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

echo "Generated $OUT_FILE using proxy $PROXY_HOST:$PROXY_PORT ($PROXY_TYPE)"
