#!/usr/bin/env bash
set -euo pipefail

LAN_IF="eth0"
LAN_DNS="192.168.50.1"
CHAIN="TGW_FORCE_DNS"

enable_force_dns() {
  iptables -t nat -N "$CHAIN" 2>/dev/null || true
  iptables -t nat -F "$CHAIN"

  iptables -t nat -C PREROUTING -i "$LAN_IF" -p udp --dport 53 -j "$CHAIN" 2>/dev/null || \
    iptables -t nat -I PREROUTING 1 -i "$LAN_IF" -p udp --dport 53 -j "$CHAIN"

  iptables -t nat -C PREROUTING -i "$LAN_IF" -p tcp --dport 53 -j "$CHAIN" 2>/dev/null || \
    iptables -t nat -I PREROUTING 1 -i "$LAN_IF" -p tcp --dport 53 -j "$CHAIN"

  iptables -t nat -A "$CHAIN" -d "$LAN_DNS" -j RETURN
  iptables -t nat -A "$CHAIN" -p udp --dport 53 -j DNAT --to-destination "$LAN_DNS"
  iptables -t nat -A "$CHAIN" -p tcp --dport 53 -j DNAT --to-destination "$LAN_DNS"

  echo "Force DNS enabled on $LAN_IF -> $LAN_DNS"
}

disable_force_dns() {
  iptables -t nat -D PREROUTING -i "$LAN_IF" -p udp --dport 53 -j "$CHAIN" 2>/dev/null || true
  iptables -t nat -D PREROUTING -i "$LAN_IF" -p tcp --dport 53 -j "$CHAIN" 2>/dev/null || true
  iptables -t nat -F "$CHAIN" 2>/dev/null || true
  iptables -t nat -X "$CHAIN" 2>/dev/null || true

  echo "Force DNS disabled"
}

status_force_dns() {
  iptables -t nat -L "$CHAIN" -n -v --line-numbers 2>/dev/null || echo "Force DNS chain not found"
}

case "${1:-enable}" in
  enable)
    enable_force_dns
    ;;
  disable)
    disable_force_dns
    ;;
  status)
    status_force_dns
    ;;
  *)
    echo "Usage: $0 {enable|disable|status}"
    exit 1
    ;;
esac
