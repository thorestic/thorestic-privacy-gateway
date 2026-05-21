#!/usr/bin/env bash

echo "===== BASIC INFO ====="
date
whoami
hostname
hostname -I
echo

echo "===== OS INFO ====="
cat /etc/os-release | head -n 5
echo

echo "===== NETWORK DEVICES ====="
nmcli device status
echo

echo "===== ACTIVE CONNECTIONS ====="
nmcli connection show --active
echo

echo "===== IP ADDRESSES ====="
ip -br addr
echo

echo "===== ROUTES ====="
ip route
echo

echo "===== DNS TEST ====="
ping -c 2 1.1.1.1
ping -c 2 google.com
echo

echo "===== DISK ====="
df -h /
echo

echo "===== MEMORY ====="
free -h
echo

echo "===== SERVICES ====="
systemctl is-active ssh || true
systemctl is-active nginx || true
echo

echo "===== RASPBERRY TEMP / THROTTLE ====="
if command -v vcgencmd >/dev/null; then
  vcgencmd measure_temp || true
  vcgencmd get_throttled || true
else
  echo "vcgencmd not installed"
fi
