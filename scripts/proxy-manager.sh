#!/usr/bin/env bash
set -euo pipefail

PROXY_ENV="/opt/thorestic-gateway/configs/proxy.env"
MODE_FILE="/opt/thorestic-gateway/configs/current-mode"

load_current() {
  if [ -f "$PROXY_ENV" ]; then
    set -a
    source "$PROXY_ENV"
    set +a
  fi

  PROXY_TYPE="${PROXY_TYPE:-socks5}"
  PROXY_HOST="${PROXY_HOST:-}"
  PROXY_PORT="${PROXY_PORT:-}"
  PROXY_USERNAME="${PROXY_USERNAME:-}"
  PROXY_PASSWORD="${PROXY_PASSWORD:-}"
  PROXY_LOCAL_PORT="${PROXY_LOCAL_PORT:-12345}"
}

status_proxy() {
  load_current

  echo "PROXY_TYPE=$PROXY_TYPE"
  echo "PROXY_HOST=$PROXY_HOST"
  echo "PROXY_PORT=$PROXY_PORT"
  echo "PROXY_USERNAME=$PROXY_USERNAME"
  echo "PROXY_PASSWORD_SET=$([ -n "$PROXY_PASSWORD" ] && echo yes || echo no)"
  echo "PROXY_LOCAL_PORT=$PROXY_LOCAL_PORT"
  echo
  echo "Proxy service:"
  systemctl is-active thorestic-redsocks || true
}

set_proxy() {
  local type="${1:-}"
  local host="${2:-}"
  local port="${3:-}"
  local username="${4:-}"
  local password="${5:-__KEEP__}"

  load_current

  if [ "$type" != "socks5" ] && [ "$type" != "http-connect" ]; then
    echo "Invalid proxy type: $type"
    exit 1
  fi

  if [ -z "$host" ] || [ -z "$port" ] || [ -z "$username" ]; then
    echo "Missing proxy host/port/username"
    exit 1
  fi

  if [ "$password" = "__KEEP__" ] || [ -z "$password" ]; then
    password="$PROXY_PASSWORD"
  fi

  cat > "$PROXY_ENV" <<CONF
PROXY_TYPE=$type
PROXY_HOST=$host
PROXY_PORT=$port
PROXY_USERNAME=$username
PROXY_PASSWORD=$password
PROXY_LOCAL_PORT=12345
CONF

  chmod 600 "$PROXY_ENV"
  chown root:root "$PROXY_ENV"

  /opt/thorestic-gateway/scripts/build-redsocks-config.sh

  current_mode="$(cat "$MODE_FILE" 2>/dev/null || echo direct)"

  if [ "$current_mode" = "proxy" ]; then
    systemctl restart thorestic-redsocks
    /opt/thorestic-gateway/scripts/mode-manager.sh proxy >/dev/null 2>&1 || true
  fi

  echo "Proxy settings updated"
}

case "${1:-status}" in
  status)
    status_proxy
    ;;
  set)
    set_proxy "${2:-}" "${3:-}" "${4:-}" "${5:-}" "${6:-__KEEP__}"
    ;;
  *)
    echo "Usage: $0 {status|set TYPE HOST PORT USERNAME PASSWORD}"
    exit 1
    ;;
esac
