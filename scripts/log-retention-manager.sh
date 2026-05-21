#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/thorestic-gateway/configs/log-retention.env"
LOGROTATE_FILE="/etc/logrotate.d/thorestic-gateway"

if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<CONF
RETENTION_DAYS=7
MAX_SIZE=10M
CONF
  chmod 600 "$ENV_FILE"
  chown root:root "$ENV_FILE"
fi

set -a
source "$ENV_FILE"
set +a

RETENTION_DAYS="${RETENTION_DAYS:-7}"
MAX_SIZE="${MAX_SIZE:-10M}"

validate() {
  if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    echo "RETENTION_DAYS must be a number"
    exit 1
  fi

  if ! [[ "$MAX_SIZE" =~ ^[0-9]+[KMG]?$ ]]; then
    echo "MAX_SIZE must look like 10M, 500K, or 1G"
    exit 1
  fi
}

apply_config() {
  validate

  cat > "$LOGROTATE_FILE" <<CONF
/var/log/thorestic-gateway/*.log {
    daily
    rotate $RETENTION_DAYS
    maxsize $MAX_SIZE
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
    create 0644 root root
}
CONF

  chmod 644 "$LOGROTATE_FILE"

  echo "Applied log retention:"
  echo "RETENTION_DAYS=$RETENTION_DAYS"
  echo "MAX_SIZE=$MAX_SIZE"
  echo "Config: $LOGROTATE_FILE"
}

set_config() {
  local days="${1:-}"
  local size="${2:-}"

  if [ -z "$days" ] || [ -z "$size" ]; then
    echo "Usage: $0 set DAYS SIZE"
    echo "Example: $0 set 7 10M"
    exit 1
  fi

  cat > "$ENV_FILE" <<CONF
RETENTION_DAYS=$days
MAX_SIZE=$size
CONF

  chmod 600 "$ENV_FILE"
  chown root:root "$ENV_FILE"

  RETENTION_DAYS="$days"
  MAX_SIZE="$size"

  apply_config
}

status_config() {
  echo "Current retention settings:"
  cat "$ENV_FILE"
  echo
  echo "Log files:"
  ls -lh /var/log/thorestic-gateway/*.log 2>/dev/null || true
  echo
  echo "Logrotate config:"
  cat "$LOGROTATE_FILE" 2>/dev/null || echo "No logrotate config yet"
}

test_config() {
  apply_config
  logrotate -d "$LOGROTATE_FILE"
}

case "${1:-status}" in
  apply)
    apply_config
    ;;
  set)
    set_config "${2:-}" "${3:-}"
    ;;
  status)
    status_config
    ;;
  test)
    test_config
    ;;
  *)
    echo "Usage: $0 {apply|set DAYS SIZE|status|test}"
    exit 1
    ;;
esac
