#!/usr/bin/env bash
set -euo pipefail

BLOCK_FILE="/opt/thorestic-gateway/configs/blocked-clients.txt"
DISCONNECT_FILE="/opt/thorestic-gateway/configs/disconnected-clients.txt"
CHAIN="TGW_CLIENT_CONTROL"
LAN_IF="eth0"

valid_ip() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

ensure_files() {
  touch "$BLOCK_FILE" "$DISCONNECT_FILE"
  chmod 600 "$BLOCK_FILE" "$DISCONNECT_FILE"
  chown root:root "$BLOCK_FILE" "$DISCONNECT_FILE"
}

ensure_chain() {
  iptables -N "$CHAIN" 2>/dev/null || true

  # Keep our chain at the very top of FORWARD.
  while iptables -D FORWARD -j "$CHAIN" 2>/dev/null; do true; done
  iptables -I FORWARD 1 -j "$CHAIN"
}

kill_sessions() {
  local ip="$1"

  conntrack -D -s "$ip" 2>/dev/null || true
  conntrack -D -d "$ip" 2>/dev/null || true
  ip neigh flush to "$ip" dev "$LAN_IF" 2>/dev/null || true
}

apply_rules() {
  ensure_files
  ensure_chain

  iptables -F "$CHAIN"

  # Permanent blocks.
  while read -r ip; do
    ip="$(echo "$ip" | tr -d '[:space:]')"
    [ -z "$ip" ] && continue

    if valid_ip "$ip"; then
      iptables -A "$CHAIN" -s "$ip" -j DROP
      iptables -A "$CHAIN" -d "$ip" -j DROP
    fi
  done < "$BLOCK_FILE"

  # Temporary disconnects.
  while read -r ip; do
    ip="$(echo "$ip" | tr -d '[:space:]')"
    [ -z "$ip" ] && continue

    if valid_ip "$ip"; then
      iptables -A "$CHAIN" -s "$ip" -j DROP
      iptables -A "$CHAIN" -d "$ip" -j DROP
    fi
  done < "$DISCONNECT_FILE"

  echo "Applied client control rules"
}

block_ip() {
  local ip="${1:-}"

  if ! valid_ip "$ip"; then
    echo "Invalid IP: $ip"
    exit 1
  fi

  ensure_files

  if grep -Fxq "$ip" "$BLOCK_FILE"; then
    echo "$ip already blocked"
  else
    echo "$ip" >> "$BLOCK_FILE"
    sort -u "$BLOCK_FILE" -o "$BLOCK_FILE"
    echo "Blocked $ip"
  fi

  kill_sessions "$ip"
  apply_rules
}

unblock_ip() {
  local ip="${1:-}"

  if ! valid_ip "$ip"; then
    echo "Invalid IP: $ip"
    exit 1
  fi

  ensure_files

  grep -Fxv "$ip" "$BLOCK_FILE" > "$BLOCK_FILE.tmp" || true
  mv "$BLOCK_FILE.tmp" "$BLOCK_FILE"

  echo "Unblocked $ip"
  apply_rules
}

disconnect_ip() {
  local ip="${1:-}"

  if ! valid_ip "$ip"; then
    echo "Invalid IP: $ip"
    exit 1
  fi

  ensure_files

  if grep -Fxq "$ip" "$DISCONNECT_FILE"; then
    echo "$ip already disconnected"
  else
    echo "$ip" >> "$DISCONNECT_FILE"
    sort -u "$DISCONNECT_FILE" -o "$DISCONNECT_FILE"
    echo "Disconnected $ip"
  fi

  kill_sessions "$ip"
  apply_rules
}

reconnect_ip() {
  local ip="${1:-}"

  if ! valid_ip "$ip"; then
    echo "Invalid IP: $ip"
    exit 1
  fi

  ensure_files

  grep -Fxv "$ip" "$DISCONNECT_FILE" > "$DISCONNECT_FILE.tmp" || true
  mv "$DISCONNECT_FILE.tmp" "$DISCONNECT_FILE"

  echo "Reconnected $ip"
  apply_rules
}

list_blocked() {
  ensure_files
  cat "$BLOCK_FILE"
}

list_disconnected() {
  ensure_files
  cat "$DISCONNECT_FILE"
}

status_rules() {
  ensure_files

  echo "Blocked clients:"
  cat "$BLOCK_FILE"
  echo

  echo "Disconnected clients:"
  cat "$DISCONNECT_FILE"
  echo

  echo "iptables chain:"
  iptables -L "$CHAIN" -n -v --line-numbers 2>/dev/null || echo "No chain yet"
}

case "${1:-status}" in
  block)
    block_ip "${2:-}"
    ;;
  unblock)
    unblock_ip "${2:-}"
    ;;
  disconnect)
    disconnect_ip "${2:-}"
    ;;
  reconnect)
    reconnect_ip "${2:-}"
    ;;
  apply)
    apply_rules
    ;;
  list)
    list_blocked
    ;;
  disconnected)
    list_disconnected
    ;;
  status)
    status_rules
    ;;
  *)
    echo "Usage: $0 {block IP|unblock IP|disconnect IP|reconnect IP|apply|list|disconnected|status}"
    exit 1
    ;;
esac
