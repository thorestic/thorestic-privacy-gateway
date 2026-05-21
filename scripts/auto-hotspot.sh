#!/usr/bin/env bash
set -euo pipefail

KNOWN_FILE="/opt/thorestic-gateway/configs/known-hotspots.txt"

usage() {
  echo "Usage: $0 {scan|connect SSID [PASSWORD]|disconnect|add SSID PASSWORD|remove SSID|list|auto}"
  exit 1
}

ensure_file() {
  if [ ! -f "$KNOWN_FILE" ]; then
    mkdir -p "$(dirname "$KNOWN_FILE")"
    touch "$KNOWN_FILE"
    chmod 600 "$KNOWN_FILE"
  fi
}

scan_wifi() {
  nmcli -t -f ssid,signal,security dev wifi list --rescan yes 2>/dev/null | head -20
}

add_hotspot() {
  local ssid="${1:-}"
  local pass="${2:-}"
  if [ -z "$ssid" ] || [ -z "$pass" ]; then
    echo "Usage: $0 add SSID PASSWORD"
    exit 1
  fi
  ensure_file
  # Remove existing entry for this SSID
  grep -v "^${ssid}:" "$KNOWN_FILE" > "${KNOWN_FILE}.tmp" 2>/dev/null || true
  echo "${ssid}:${pass}" >> "${KNOWN_FILE}.tmp"
  mv "${KNOWN_FILE}.tmp" "$KNOWN_FILE"
  chmod 600 "$KNOWN_FILE"
  echo "Added hotspot: $ssid"
}

remove_hotspot() {
  local ssid="${1:-}"
  if [ -z "$ssid" ]; then
    echo "Usage: $0 remove SSID"
    exit 1
  fi
  ensure_file
  grep -v "^${ssid}:" "$KNOWN_FILE" > "${KNOWN_FILE}.tmp" 2>/dev/null || true
  mv "${KNOWN_FILE}.tmp" "$KNOWN_FILE"
  echo "Removed: $ssid"
}

list_hotspots() {
  ensure_file
  if [ ! -s "$KNOWN_FILE" ]; then
    echo "No saved hotspots."
    return
  fi
  echo "Saved hotspots:"
  while IFS=: read -r ssid _pass; do
    echo "  - $ssid"
  done < "$KNOWN_FILE"
}

connect_to() {
  local ssid="${1:-}"
  local pass="${2:-}"
  if [ -z "$ssid" ]; then
    echo "Usage: $0 connect SSID [PASSWORD]"
    exit 1
  fi

  local security
  security=$(nmcli -t -f ssid,security dev wifi list --rescan yes 2>/dev/null | awk -F: -v target="$ssid" '$1 == target {print $2; exit}')
  if [ -n "$security" ] && [ -z "$pass" ]; then
    echo "Password required for secured network: $ssid ($security)"
    exit 2
  fi

  local con_name
  con_name="thorestic-wifi-$(printf '%s' "$ssid" | tr -c 'A-Za-z0-9_.-' '-')"

  echo "Connecting to: $ssid"
  nmcli connection delete "$con_name" >/dev/null 2>&1 || true
  nmcli connection add type wifi ifname wlan0 con-name "$con_name" ssid "$ssid" >/dev/null

  if [ -n "$pass" ]; then
    nmcli connection modify "$con_name" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$pass"
  fi

  nmcli connection modify "$con_name" connection.autoconnect yes connection.autoconnect-priority 50 ipv4.method auto ipv6.method auto
  nmcli connection up "$con_name" ifname wlan0 2>&1
}

disconnect_wifi() {
  echo "Disconnecting wlan0 from Wi-Fi uplink"
  nmcli dev disconnect wlan0 2>&1 || true
  echo "wlan0 disconnected"
}

auto_connect() {
  ensure_file
  if [ ! -s "$KNOWN_FILE" ]; then
    echo "No saved hotspots. Add one with: $0 add SSID PASSWORD"
    exit 0
  fi

  local available
  available=$(nmcli -t -f ssid dev wifi list --rescan yes 2>/dev/null)

  while IFS=: read -r ssid pass; do
    [ -z "$ssid" ] && continue
    if echo "$available" | grep -qF "$ssid"; then
      echo "Found known hotspot: $ssid"
      connect_to "$ssid" "$pass"
      return
    fi
  done < "$KNOWN_FILE"

  echo "No known hotspots in range."
}

case "${1:-}" in
  scan)    scan_wifi ;;
  connect) connect_to "${2:-}" "${3:-}" ;;
  disconnect) disconnect_wifi ;;
  add)     add_hotspot "${2:-}" "${3:-}" ;;
  remove)  remove_hotspot "${2:-}" ;;
  list)    list_hotspots ;;
  auto)    auto_connect ;;
  *)       usage ;;
esac
