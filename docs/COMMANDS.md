# Commands

These are useful commands from the project work. They use placeholders, not private values.

## SSH To The Pi

```bash
ssh USERNAME@PI_IP
```

With a key:

```bash
ssh -i ./your_key USERNAME@PI_IP
```

## Check Services

```bash
systemctl status thorestic-fastapi
systemctl status thorestic-netlogger
systemctl is-active thorestic-fastapi
```

Restart:

```bash
sudo systemctl restart thorestic-fastapi
sudo systemctl restart thorestic-netlogger
```

Logs:

```bash
journalctl -u thorestic-fastapi -n 100 --no-pager
journalctl -u thorestic-netlogger -n 100 --no-pager
```

## Test Python

```bash
python3 -m py_compile web/main.py web/ui.py
```

Run locally:

```bash
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

## NetworkManager

Show devices:

```bash
nmcli dev status
```

Scan Wi-Fi:

```bash
nmcli -t -f ssid,signal,security dev wifi list --rescan yes
```

Connect to Wi-Fi:

```bash
sudo nmcli dev wifi connect "SSID_NAME" password "WIFI_PASSWORD"
```

Disconnect Wi-Fi:

```bash
sudo nmcli dev disconnect wlan0
```

## Project Network Script

Scan:

```bash
sudo /opt/thorestic-gateway/scripts/auto-hotspot.sh scan
```

Connect:

```bash
sudo /opt/thorestic-gateway/scripts/auto-hotspot.sh connect "SSID_NAME" "WIFI_PASSWORD"
```

Disconnect:

```bash
sudo /opt/thorestic-gateway/scripts/auto-hotspot.sh disconnect
```

Syntax check:

```bash
bash -n /opt/thorestic-gateway/scripts/auto-hotspot.sh
```

## tcpdump

DNS traffic:

```bash
sudo tcpdump -i eth0 -n port 53
```

TCP connection attempts:

```bash
sudo tcpdump -i eth0 -n 'tcp[tcpflags] & tcp-syn != 0'
```

## Logs

```bash
sudo tail -f /var/log/thorestic-gateway/combined.log
sudo tail -f /var/log/thorestic-gateway/dns.log
sudo tail -f /var/log/thorestic-gateway/connections.log
```
