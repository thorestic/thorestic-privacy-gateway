#!/usr/bin/env bash
set -euo pipefail

PROXIES_FILE="/opt/thorestic-gateway/configs/proxies.csv"
PROXY_ENV="/opt/thorestic-gateway/configs/proxy.env"
STATE_FILE="/opt/thorestic-gateway/configs/proxy-state.env"
MODE_FILE="/opt/thorestic-gateway/configs/current-mode"

if [ ! -f "$PROXIES_FILE" ]; then
  echo "Missing $PROXIES_FILE"
  exit 1
fi

mapfile -t PROXIES < <(tail -n +2 "$PROXIES_FILE" | sed '/^\s*$/d')

if [ "${#PROXIES[@]}" -eq 0 ]; then
  echo "No proxies found in $PROXIES_FILE"
  exit 1
fi

CURRENT_INDEX=-1
if [ -f "$STATE_FILE" ]; then
  source "$STATE_FILE" || true
  CURRENT_INDEX="${CURRENT_INDEX:--1}"
fi

NEXT_INDEX=$((CURRENT_INDEX + 1))
if [ "$NEXT_INDEX" -ge "${#PROXIES[@]}" ]; then
  NEXT_INDEX=0
fi

IFS=',' read -r NAME TYPE HOST PORT USERNAME PASSWORD <<< "${PROXIES[$NEXT_INDEX]}"

cat > "$PROXY_ENV" <<CONF
PROXY_TYPE=$TYPE
PROXY_HOST=$HOST
PROXY_PORT=$PORT
PROXY_USERNAME=$USERNAME
PROXY_PASSWORD=$PASSWORD
PROXY_LOCAL_PORT=12345
CONF

chmod 600 "$PROXY_ENV"
chown root:root "$PROXY_ENV"

cat > "$STATE_FILE" <<CONF
CURRENT_INDEX=$NEXT_INDEX
CURRENT_NAME=$NAME
CURRENT_TYPE=$TYPE
CURRENT_HOST=$HOST
CURRENT_PORT=$PORT
CONF

chmod 600 "$STATE_FILE"
chown root:root "$STATE_FILE"

systemctl restart thorestic-redsocks

CURRENT_MODE="$(cat "$MODE_FILE" 2>/dev/null || echo direct)"
if [ "$CURRENT_MODE" = "proxy" ]; then
  /opt/thorestic-gateway/scripts/mode-manager.sh proxy >/dev/null 2>&1 || true
fi

echo "Rotated to $NAME ($HOST:$PORT, $TYPE)"
