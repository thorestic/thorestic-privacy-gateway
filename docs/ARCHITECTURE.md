# Architecture

This project has three main parts:

```text
Browser dashboard
  -> FastAPI backend
  -> Bash/Python scripts
  -> Linux services and network tools
```

## Browser

The browser opens the dashboard and sends actions to FastAPI routes.

Examples:

- click Scan on the Network page
- click Connect Raspberry Pi
- switch a mode page
- view logs
- block or reconnect a client

The browser does not run Linux commands directly.

## FastAPI

FastAPI is the Python backend in `web/main.py`.

It does things like:

- render pages
- check login/session
- expose API routes
- read config files
- read log files
- call scripts using `subprocess.run`
- return JSON to the frontend
- stream logs with server-sent events

Example pattern:

```python
rc, out = run_cmd(["sudo", NETWORK_SCRIPT, "connect", ssid, password], timeout=45)
```

That means:

```text
frontend button -> API route -> run_cmd() -> script -> Linux tool
```

## Scripts

The scripts live in `scripts/`.

Most of them are Bash scripts because the actions are Linux/network actions.

Examples:

- `auto-hotspot.sh` uses `nmcli`
- `mode-manager.sh` changes routing modes
- `force-dns.sh` manages DNS rules
- `block-manager.sh` blocks clients/domains
- `proxy-manager.sh` stores proxy settings
- `net-logger.py` runs `tcpdump` and writes logs

## Services

On the Raspberry Pi, the project is normally run with systemd services.

Example service files are in:

```text
systemd/
```

The common services are:

- FastAPI dashboard service
- network logger service
- mode/service scripts called through sudo

## Logs

The logger watches network traffic metadata and writes files under:

```text
/var/log/thorestic-gateway/
```

Main log files:

```text
dns.log
connections.log
combined.log
```

The dashboard reads logs from:

```text
/api/logs
```

Live logs come from:

```text
/stream/logs
```

## Network Layout

The expected idea is:

```text
Client/router side -> Raspberry Pi eth0 -> Raspberry Pi gateway logic -> wlan0/upstream internet
```

In the real device setup:

- `eth0` is the local gateway side.
- `wlan0` is used for upstream Wi-Fi.
- the dashboard can be reached from the local gateway side.

## Why The Split Is Small

This is still a learning project. I did not split it into many modules because that would make it harder to follow.

The current split is enough:

- backend logic: `web/main.py`
- layout: `web/ui.py`
- base HTML: `web/templates/base.html`
- CSS: `web/static/styles.css`
