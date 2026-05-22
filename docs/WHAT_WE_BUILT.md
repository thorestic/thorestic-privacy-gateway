# What We Built

This file is a direct summary of what was done in the project.

## Main Idea

The project turns a Raspberry Pi 4 into a small network gateway with a browser dashboard.

Instead of controlling everything from terminal commands, the dashboard calls FastAPI routes, and FastAPI runs local scripts on the Pi.

## Dashboard Changes

What was changed in the dashboard:

- Removed the old Tools section from the UI and routes.
- Added a Network page to scan Wi-Fi networks and connect the Raspberry Pi to a selected network.
- Added a Disconnect Wi-Fi action for testing gateway access without upstream internet.
- Changed Tor/VPN/Proxy/Blocking controls on the dashboard into status icons only.
- Kept the real controls inside their own sidebar pages.
- Added Wi-Fi QR settings so the QR code uses a selected network, not whatever network the Pi is connected to.
- Improved QR output so phones can scan it more easily.

## Code Organization

The web app was first mostly inside one large `main.py`.

It was split lightly:

```text
web/main.py
web/ui.py
web/templates/base.html
web/static/styles.css
```

The goal was not to over-engineer the project. It just makes the repo easier to read:

- Python backend in `main.py`
- shared UI rendering in `ui.py`
- base HTML in `templates/base.html`
- CSS in `static/styles.css`

## Network Work

The Wi-Fi script was updated so it can:

- scan available Wi-Fi networks with `nmcli`
- connect to a secured network
- create an explicit NetworkManager profile
- set `wifi-sec.key-mgmt wpa-psk`
- disconnect `wlan0`

This fixed the NetworkManager error:

```text
802-11-wireless-security.key-mgmt: property is missing
```

## Public GitHub Work

The public repo was cleaned so it does not include:

- real `.env` files
- passwords
- real Wi-Fi names/passwords
- SSH keys
- certificates
- logs
- proxy credentials
- device backups

The repo includes example config files instead.

## Screenshots

The repo uses real screenshots from the local dashboard UI:

- `docs/images/dashboard-preview.png`
- `docs/images/network-page.png`

They were taken from a safe local preview, not from private Raspberry Pi data.
