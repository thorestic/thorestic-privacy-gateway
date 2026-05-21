# Thorestic Privacy Gateway

This is my first Raspberry Pi networking project.

The idea was simple at first: I wanted to make a Raspberry Pi 4 work like a small privacy gateway that I can control from a web page, instead of opening the terminal every time I want to change something.

The project became a dashboard that can manage network modes, Wi-Fi uplink, clients, blocking, proxy/Tor pages, QR code settings, and live logs.

![Dashboard screenshot](docs/images/dashboard-preview.png)

## What The Project Does

Thorestic Gateway runs on a Raspberry Pi. The Pi can sit between a router/client device and the internet.

In my setup, Ethernet is used for the local gateway side, and Wi-Fi can be used as the internet uplink. That means I can connect the Pi to another Wi-Fi network from the dashboard and still keep access to the gateway page.

Main things in the project:

- Web dashboard built with FastAPI.
- Bash scripts for real Linux/network actions.
- Network page to scan and connect to Wi-Fi.
- Dashboard status icons for services.
- Tor, Proxy, VPN, Clients, Logs, Blocking, and Settings pages.
- QR code generator for a selected Wi-Fi network.
- Live DNS and connection logs using `tcpdump`.
- Client blocking and disconnect/reconnect actions.
- Example systemd service files.

## Network Page

This is the page I added so I can connect the Raspberry Pi to Wi-Fi without needing a monitor.

![Network page screenshot](docs/images/network-page.png)

## How It Works

The backend is written in Python with FastAPI.

The website sends requests to API routes, and then FastAPI runs the needed script in the background.

For example, when I click a button to connect to Wi-Fi, the browser does not run the script directly. It calls an API route, and then Python runs something like:

```python
run_cmd(["sudo", NETWORK_SCRIPT, "connect", ssid, password], timeout=45)
```

So the flow is:

```text
Browser button
  -> FastAPI route
  -> Python subprocess
  -> Bash script
  -> Linux / NetworkManager / system service
```

## Project Structure

I split the web files a little so everything is not inside one huge `main.py`.

```text
web/
  main.py                FastAPI routes, APIs, and backend logic
  ui.py                  shared layout and login rendering
  templates/base.html    base HTML page
  static/styles.css      website styling

scripts/
  *.sh                   Raspberry Pi network/service scripts
  net-logger.py          tcpdump log collector

configs/
  *.example              safe example config files only

systemd/
  *.service.example      example service files
```

It is still simple, but now the website style and base layout are not mixed directly with all the Python logic.

## Important Scripts

| Script | What it does |
| --- | --- |
| `auto-hotspot.sh` | Scans Wi-Fi, connects `wlan0`, disconnects Wi-Fi, and can store known hotspots. |
| `mode-manager.sh` | Changes the gateway mode, like direct, Tor, or proxy mode. |
| `force-dns.sh` | Forces client DNS traffic through the gateway rules. |
| `block-manager.sh` | Blocks or unblocks devices/domains depending on the action. |
| `device-manager.sh` | Disconnects, reconnects, or manages client devices. |
| `proxy-manager.sh` | Reads and updates proxy settings. |
| `rotate-proxy.sh` | Rotates between proxy entries. |
| `build-redsocks-config.sh` | Builds redsocks config from proxy settings. |
| `net-logger.py` | Uses `tcpdump` to collect DNS and connection logs. |
| `log-retention-manager.sh` | Handles log cleanup/retention. |
| `healthcheck.sh` | Basic health check script. |
| `setup-https.sh` | HTTPS setup helper. |

## Logs

The logging part uses `tcpdump`.

The idea is to watch traffic metadata from the gateway interface and save useful events for the dashboard.

The main log files on the Raspberry Pi are:

```text
/var/log/thorestic-gateway/dns.log
/var/log/thorestic-gateway/connections.log
/var/log/thorestic-gateway/combined.log
```

The dashboard reads old logs from `/api/logs` and gets live logs from `/stream/logs`.

## Problems I Faced

### Headless setup

I did not have a micro-HDMI screen all the time, so I needed a way to manage the Pi from the website. That is why I added the Network page.

### Wi-Fi connect error

One problem I got was:

```text
802-11-wireless-security.key-mgmt: property is missing
```

The fix was to create a clear NetworkManager profile and set `wifi-sec.key-mgmt wpa-psk` when the network has a password.

### QR code problem

The first QR code was not good enough for phone scanning, and it was also using the wrong network idea. I changed it so the QR is based on the Wi-Fi info I set in Settings, and the output is clearer.

### Dashboard controls

At first the dashboard had too many controls in one place. I changed the service row so it works more like status icons, and the real controls stay in their own pages.

### Public repo safety

I had to make sure I do not upload private files. So this repo does not include real config files, passwords, SSH keys, certificates, proxy credentials, or logs.

## AI Help

I used AI while building this project.

It helped me understand parts of Linux networking, write and fix Bash scripts, connect FastAPI routes to scripts, debug errors, and prepare the project for GitHub.

I still tested the project on the Raspberry Pi and changed things based on what actually happened on the device.

## Not Included In This Public Repo

This repo does not include:

- Real Wi-Fi passwords.
- Real dashboard password hashes.
- Real proxy credentials.
- Logs.
- Certificates.
- SSH keys.
- Device backups.
- Personal network details.

The files in `configs/` are examples only.

## Run Locally For Development

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

On the Raspberry Pi, system-level actions need the right services, permissions, and `sudoers` rules.

This project is still a learning project, but it works as a real Raspberry Pi experiment and helped me understand a lot more about networking and Linux.
