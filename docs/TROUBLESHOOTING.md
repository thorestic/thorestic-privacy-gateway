# Troubleshooting

These are real problems that came up while working on the project.

## Wi-Fi Connect Error

Error:

```text
802-11-wireless-security.key-mgmt: property is missing
```

Cause:

NetworkManager needed a clear Wi-Fi security setting for the connection profile.

Fix:

The script creates a NetworkManager profile and sets:

```bash
wifi-sec.key-mgmt wpa-psk
```

when the network has a password.

## Wi-Fi Scan Shows No Networks

Things to check:

```bash
nmcli radio wifi
nmcli dev status
nmcli -t -f ssid,signal,security dev wifi list --rescan yes
```

Possible causes:

- Wi-Fi radio is disabled.
- `wlan0` is blocked.
- NetworkManager does not control the interface.
- The dashboard user does not have permission to run the scan script.
- The Pi is too far from the access point.

## No Screen Or micro-HDMI

Problem:

If the Pi loses Wi-Fi, it is hard to fix without a screen.

Fix used in this project:

- Keep the Ethernet/gateway side available.
- Add a Network page in the dashboard.
- Add a Disconnect Wi-Fi button for testing.
- Make sure the Pi can still be reached from the local gateway network.

## QR Code Not Scanning

Problem:

The first QR code was too small/compressed and phones could not scan it reliably.

Fix:

- Generate SVG QR output.
- Render it larger in the UI.
- Use a specific SSID/password from Settings, not the currently connected upstream Wi-Fi.

## Dashboard Had Too Many Controls

Problem:

The dashboard service row had too many buttons and controls.

Fix:

The dashboard now shows status icons only. Real controls live in the sidebar pages.

## Logs Not Showing

Check if logger service is active:

```bash
systemctl status thorestic-netlogger
```

Check files:

```bash
ls -lah /var/log/thorestic-gateway/
```

Check live output:

```bash
sudo tail -f /var/log/thorestic-gateway/combined.log
```

Possible causes:

- `tcpdump` is not installed.
- service is not running as root.
- wrong interface name.
- log directory does not exist or has wrong permissions.

## FastAPI Not Running

Check:

```bash
systemctl status thorestic-fastapi
journalctl -u thorestic-fastapi -n 100 --no-pager
```

Test Python syntax:

```bash
python3 -m py_compile web/main.py web/ui.py
```

Run manually:

```bash
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```
