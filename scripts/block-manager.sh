#!/usr/bin/env bash
set -euo pipefail

BLOCK_FILE="/opt/thorestic-gateway/configs/blocked-domains.txt"
DNSMASQ_FILE="/etc/NetworkManager/dnsmasq-shared.d/thorestic-blocklist.conf"

normalize_domain() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's#^https\?://##' \
    | sed 's#/.*$##' \
    | sed 's/^www\.//' \
    | sed 's/[^a-z0-9.-]//g' \
    | sed 's/^\.*//' \
    | sed 's/\.*$//'
}

valid_domain() {
  [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ ]]
}

apply_rules() {
  mkdir -p "$(dirname "$DNSMASQ_FILE")"
  : > "$DNSMASQ_FILE"

  while read -r domain; do
    domain="$(normalize_domain "$domain")"
    [ -z "$domain" ] && continue

    echo "address=/$domain/0.0.0.0" >> "$DNSMASQ_FILE"
    echo "address=/www.$domain/0.0.0.0" >> "$DNSMASQ_FILE"
  done < "$BLOCK_FILE"

  nmcli connection down pi-eth-share >/dev/null 2>&1 || true
  nmcli connection up pi-eth-share >/dev/null 2>&1 || true

  echo "Applied blocking rules"
}

add_domain() {
  domain="$(normalize_domain "$1")"

  if ! valid_domain "$domain"; then
    echo "Invalid domain: $1"
    exit 1
  fi

  touch "$BLOCK_FILE"

  if grep -Fxq "$domain" "$BLOCK_FILE"; then
    echo "$domain already exists"
  else
    echo "$domain" >> "$BLOCK_FILE"
    sort -u "$BLOCK_FILE" -o "$BLOCK_FILE"
    echo "Added $domain"
  fi

  apply_rules
}

remove_domain() {
  domain="$(normalize_domain "$1")"

  if [ -f "$BLOCK_FILE" ]; then
    grep -Fxv "$domain" "$BLOCK_FILE" > "$BLOCK_FILE.tmp" || true
    mv "$BLOCK_FILE.tmp" "$BLOCK_FILE"
  fi

  echo "Removed $domain"
  apply_rules
}

list_domains() {
  if [ -f "$BLOCK_FILE" ]; then
    cat "$BLOCK_FILE"
  fi
}

case "${1:-list}" in
  add)
    add_domain "${2:-}"
    ;;
  remove)
    remove_domain "${2:-}"
    ;;
  apply)
    apply_rules
    ;;
  list)
    list_domains
    ;;
  *)
    echo "Usage: $0 {add domain|remove domain|apply|list}"
    exit 1
    ;;
esac
