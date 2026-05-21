#!/usr/bin/env bash
set -euo pipefail

ETH_IF="eth0"
LAN_IP="192.168.50.1"
LAN_NET="192.168.50.0/24"

TOR_TRANS_PORT="9040"
TOR_DNS_PORT="5353"

PROXY_LOCAL_PORT="12345"

MODE_FILE="/opt/thorestic-gateway/configs/current-mode"
FORCE_DNS_SCRIPT="/opt/thorestic-gateway/scripts/force-dns.sh"

ensure_chains() {
  iptables -t nat -N TGW_MODE_PREROUTING 2>/dev/null || true
  iptables -N TGW_MODE_FORWARD 2>/dev/null || true

  iptables -t nat -C PREROUTING -i "$ETH_IF" -j TGW_MODE_PREROUTING 2>/dev/null || \
    iptables -t nat -I PREROUTING 1 -i "$ETH_IF" -j TGW_MODE_PREROUTING

  iptables -C FORWARD -i "$ETH_IF" -j TGW_MODE_FORWARD 2>/dev/null || \
    iptables -I FORWARD 1 -i "$ETH_IF" -j TGW_MODE_FORWARD
}

clear_rules() {
  iptables -t nat -F TGW_MODE_PREROUTING 2>/dev/null || true
  iptables -F TGW_MODE_FORWARD 2>/dev/null || true
}

mode_direct() {
  ensure_chains
  clear_rules

  systemctl stop tor 2>/dev/null || true
  systemctl stop thorestic-redsocks 2>/dev/null || true

  echo "direct" > "$MODE_FILE"
  $FORCE_DNS_SCRIPT enable >/dev/null 2>&1 || true
  echo "Mode changed to DIRECT"
}

mode_tor() {
  systemctl stop thorestic-redsocks 2>/dev/null || true
  systemctl start tor
  sleep 2

  ensure_chains
  clear_rules

  # Keep dashboard and local LAN reachable
  iptables -t nat -A TGW_MODE_PREROUTING -d "$LAN_NET" -j RETURN

  # DNS from clients -> Tor DNSPort
  iptables -t nat -A TGW_MODE_PREROUTING -p udp --dport 53 -j REDIRECT --to-ports "$TOR_DNS_PORT"
  iptables -t nat -A TGW_MODE_PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports "$TOR_DNS_PORT"

  # TCP from clients -> Tor TransPort
  iptables -t nat -A TGW_MODE_PREROUTING -p tcp --syn -j REDIRECT --to-ports "$TOR_TRANS_PORT"

  # Block forwarding leaks
  iptables -A TGW_MODE_FORWARD -j REJECT

  echo "tor" > "$MODE_FILE"
  echo "Mode changed to TOR"
}

mode_proxy() {
  systemctl stop tor 2>/dev/null || true
  systemctl restart thorestic-redsocks
  sleep 2

  ensure_chains
  clear_rules

  # Keep dashboard and same LAN reachable
  iptables -t nat -A TGW_MODE_PREROUTING -d "$LAN_NET" -j RETURN

  # Force DNS to local gateway DNS
  iptables -t nat -A TGW_MODE_PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 53
  iptables -t nat -A TGW_MODE_PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 53

  # Redirect TCP browsing/apps to redsocks
  iptables -t nat -A TGW_MODE_PREROUTING -p tcp --syn -j REDIRECT --to-ports "$PROXY_LOCAL_PORT"

  # Block non-proxied forwarding leaks
  iptables -A TGW_MODE_FORWARD -j REJECT

  echo "proxy" > "$MODE_FILE"
  $FORCE_DNS_SCRIPT enable >/dev/null 2>&1 || true
  echo "Mode changed to PROXY"
}

mode_status() {
  echo "Current mode: $(cat "$MODE_FILE" 2>/dev/null || echo direct)"
  echo

  echo "Network devices:"
  nmcli device status
  echo

  echo "IP addresses:"
  ip -br addr
  echo

  echo "Routes:"
  ip route
  echo

  echo "Tor service:"
  systemctl is-active tor || true
  echo

  echo "Proxy service:"
  systemctl is-active thorestic-redsocks || true
}

mode_restore() {
  current="$(cat "$MODE_FILE" 2>/dev/null || echo direct)"

  case "$current" in
    tor)
      mode_tor
      ;;
    proxy)
      mode_proxy
      ;;
    direct|*)
      mode_direct
      ;;
  esac
}

case "${1:-status}" in
  direct)
    mode_direct
    ;;
  tor)
    mode_tor
    ;;
  proxy)
    mode_proxy
    ;;
  status)
    mode_status
    ;;
  restore)
    mode_restore
    ;;
  *)
    echo "Usage: $0 {direct|tor|proxy|status|restore}"
    exit 1
    ;;
esac
