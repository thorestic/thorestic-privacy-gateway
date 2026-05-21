from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
from urllib.parse import parse_qs
import subprocess
import html
import hashlib
import secrets
import asyncio
import glob
import csv

from .ui import layout, login_page

APP_DIR = Path("/opt/thorestic-gateway")
CONFIG_FILE = APP_DIR / "configs" / "dashboard.env"
MODE_SCRIPT = str(APP_DIR / "scripts" / "mode-manager.sh")
BLOCK_SCRIPT = str(APP_DIR / "scripts" / "block-manager.sh")
LOG_RETENTION_SCRIPT = str(APP_DIR / "scripts" / "log-retention-manager.sh")
DEVICE_SCRIPT = str(APP_DIR / "scripts" / "device-manager.sh")
PROXY_SCRIPT = str(APP_DIR / "scripts" / "proxy-manager.sh")
ROTATE_PROXY_SCRIPT = str(APP_DIR / "scripts" / "rotate-proxy.sh")
NETWORK_SCRIPT = str(APP_DIR / "scripts" / "auto-hotspot.sh")
LOG_DIR = Path("/var/log/thorestic-gateway")
DEVICE_META_FILE = APP_DIR / "configs" / "device-meta.csv"


def load_config() -> dict:
    config = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(errors="ignore").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


CONFIG = load_config()
ADMIN_USER = CONFIG.get("ADMIN_USER", "admin")
ADMIN_PASSWORD_SHA256 = CONFIG.get("ADMIN_PASSWORD_SHA256", "")
SESSION_SECRET = CONFIG.get("SESSION_SECRET", "change-me-now")

app = FastAPI(title="Thorestic Privacy Gateway")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=60 * 60 * 8,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


def password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def save_dashboard_password(new_password: str) -> None:
    global ADMIN_PASSWORD_SHA256

    new_hash = password_hash(new_password)
    ADMIN_PASSWORD_SHA256 = new_hash

    lines = []
    found_hash = False

    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(errors="ignore").splitlines():
            if line.startswith("ADMIN_PASSWORD_SHA256="):
                lines.append(f"ADMIN_PASSWORD_SHA256={new_hash}")
                found_hash = True
            else:
                lines.append(line)

    if not found_hash:
        lines.append(f"ADMIN_PASSWORD_SHA256={new_hash}")

    CONFIG_FILE.write_text("\n".join(lines) + "\n")


def save_dashboard_config(updates: dict[str, str]) -> None:
    global CONFIG

    lines = []
    seen = set()

    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(errors="ignore").splitlines():
            if "=" in line:
                key, _ = line.split("=", 1)
                key = key.strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                else:
                    lines.append(line)
            else:
                lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")

    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    CONFIG = load_config()


def wifi_qr_escape(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace(":", "\\:")
        .replace('"', '\\"')
    )


def logged_in(request: Request) -> bool:
    return request.session.get("user") == ADMIN_USER


def redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


def run_cmd(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout or ""
        if result.stderr:
            output += "\n" + result.stderr
        return result.returncode, output.strip()
    except Exception as exc:
        return 1, str(exc)


def get_internet_source() -> dict:
    _, out = run_cmd(["ip", "route", "show", "default"], timeout=5)
    device = ""
    gateway = ""
    for line in out.splitlines():
        parts = line.split()
        if "via" in parts:
            gateway = parts[parts.index("via") + 1]
        if "dev" in parts:
            device = parts[parts.index("dev") + 1]
        break

    source_type = "Unknown"
    source_name = device
    if device == "wlan0":
        _, ssid = run_cmd(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], timeout=5)
        for line in ssid.splitlines():
            if line.startswith("yes:"):
                source_name = line.split(":", 1)[1]
                break
        source_type = "Wi-Fi"
    elif device.startswith("usb") or device.startswith("eth1") or device.startswith("enx"):
        source_type = "USB Tethering"
    elif device == "eth0":
        source_type = "Ethernet"
    elif device.startswith("wwan") or device.startswith("ppp"):
        source_type = "Cellular"

    return {"type": source_type, "name": source_name, "device": device, "gateway": gateway}


def get_wifi_status() -> dict:
    status = {
        "device": "wlan0",
        "state": "unknown",
        "connection": "",
        "ssid": "",
        "ip": "",
        "gateway": "",
    }

    _, dev_out = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev", "status"], timeout=5)
    for line in dev_out.splitlines():
        parts = line.split(":", 3)
        if len(parts) >= 4 and parts[0] == "wlan0":
            status["state"] = parts[2]
            status["connection"] = parts[3]
            break

    _, wifi_out = run_cmd(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], timeout=5)
    for line in wifi_out.splitlines():
        if line.startswith("yes:"):
            status["ssid"] = line.split(":", 1)[1]
            break

    _, ip_out = run_cmd(["ip", "-4", "addr", "show", "wlan0"], timeout=5)
    for line in ip_out.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            status["ip"] = line.split()[1].split("/", 1)[0]
            break

    _, route_out = run_cmd(["ip", "route", "show", "default"], timeout=5)
    for line in route_out.splitlines():
        parts = line.split()
        if "dev" in parts and parts[parts.index("dev") + 1] == "wlan0":
            if "via" in parts:
                status["gateway"] = parts[parts.index("via") + 1]
            break

    return status


def parse_wifi_scan(output: str) -> list[dict]:
    networks = {}
    for line in output.splitlines():
        if not line.strip():
            continue

        parts = line.split(":", 2)
        if len(parts) < 2:
            continue

        ssid = parts[0].strip()
        if not ssid:
            continue

        try:
            signal = int(parts[1].strip())
        except Exception:
            signal = 0

        security = parts[2].strip() if len(parts) > 2 else ""
        existing = networks.get(ssid)
        if not existing or signal > existing["signal"]:
            networks[ssid] = {
                "ssid": ssid,
                "signal": signal,
                "security": security or "open",
                "requires_password": bool(security.strip()),
            }

    return sorted(networks.values(), key=lambda item: item["signal"], reverse=True)


def get_status_raw() -> str:
    _, output = run_cmd(["sudo", MODE_SCRIPT, "status"], timeout=10)
    return output or "No status output."


def get_current_mode(status_raw: str) -> str:
    for line in status_raw.splitlines():
        if line.lower().startswith("current mode:"):
            return line.split(":", 1)[1].strip()
    return "unknown"



def ensure_device_meta_file() -> None:
    DEVICE_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DEVICE_META_FILE.exists():
        DEVICE_META_FILE.write_text("mac,name,notes\n")


def load_device_meta() -> dict:
    ensure_device_meta_file()
    data = {}

    with DEVICE_META_FILE.open("r", newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mac = (row.get("mac") or "").strip().lower()
            if not mac:
                continue

            data[mac] = {
                "name": (row.get("name") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }

    return data


def save_device_meta(mac: str, name: str, notes: str) -> None:
    ensure_device_meta_file()
    mac = mac.strip().lower()

    data = load_device_meta()
    data[mac] = {
        "name": name.strip(),
        "notes": notes.strip(),
    }

    with DEVICE_META_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mac", "name", "notes"])
        writer.writeheader()

        for current_mac in sorted(data.keys()):
            writer.writerow({
                "mac": current_mac,
                "name": data[current_mac].get("name", ""),
                "notes": data[current_mac].get("notes", ""),
            })


def client_meta(client: dict) -> dict:
    mac = (client.get("mac") or "").strip().lower()
    if not mac or mac == "-":
        return {"name": "", "notes": ""}

    return load_device_meta().get(mac, {"name": "", "notes": ""})


def client_display_name(client: dict) -> str:
    meta = client_meta(client)
    custom_name = meta.get("name", "").strip()

    if custom_name:
        return custom_name

    hostname = (client.get("hostname") or "").strip()
    if hostname and hostname != "-":
        return hostname

    return client.get("ip", "-")


def parse_leases() -> dict:
    leases = {}
    paths = []
    paths.extend(glob.glob("/var/lib/NetworkManager/dnsmasq-*.leases"))
    paths.extend(glob.glob("/var/lib/misc/dnsmasq.leases"))

    for path in paths:
        try:
            for line in Path(path).read_text(errors="ignore").splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    _, mac, ip, hostname = parts[:4]
                    leases[ip] = {
                        "mac": mac,
                        "hostname": hostname if hostname != "*" else "-",
                    }
        except Exception:
            pass

    return leases



def get_blocked_clients() -> set[str]:
    _, output = run_cmd(["sudo", DEVICE_SCRIPT, "list"], timeout=10)
    return {line.strip() for line in output.splitlines() if line.strip()}


def get_disconnected_clients() -> set[str]:
    _, output = run_cmd(["sudo", DEVICE_SCRIPT, "disconnected"], timeout=10)
    return {line.strip() for line in output.splitlines() if line.strip()}


def client_recent_logs(ip: str, limit: int = 80) -> str:
    log_file = LOG_DIR / "combined.log"
    if not log_file.exists():
        return ""

    lines = log_file.read_text(errors="ignore").splitlines()
    matched = [line for line in lines if ip in line]
    return "\n".join(matched[-limit:])


def get_clients() -> list[dict]:
    leases = parse_leases()
    _, out = run_cmd(["ip", "neigh", "show", "dev", "eth0"], timeout=5)

    clients = {}

    for ip, info in leases.items():
        clients[ip] = {
            "ip": ip,
            "mac": info.get("mac", "-"),
            "hostname": info.get("hostname", "-"),
            "state": "LEASE",
        }

    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue

        ip = parts[0]
        mac = "-"
        state = parts[-1] if len(parts) >= 1 else "-"

        if "lladdr" in parts:
            idx = parts.index("lladdr")
            if idx + 1 < len(parts):
                mac = parts[idx + 1]

        if ip not in clients:
            clients[ip] = {
                "ip": ip,
                "mac": mac,
                "hostname": leases.get(ip, {}).get("hostname", "-"),
                "state": state,
            }
        else:
            if mac != "-":
                clients[ip]["mac"] = mac
            clients[ip]["state"] = state

    return sorted(clients.values(), key=lambda x: x["ip"])


def log_path(kind: str) -> Path:
    allowed = {
        "combined": LOG_DIR / "combined.log",
        "dns": LOG_DIR / "dns.log",
        "connections": LOG_DIR / "connections.log",
    }
    return allowed.get(kind, allowed["combined"])


def tail_file(path: Path, lines: int = 160) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_text(errors="ignore").splitlines()
        return "\n".join(data[-lines:])
    except Exception as exc:
        return f"Could not read log: {exc}"


def get_proxy_status() -> dict:
    _, output = run_cmd(["sudo", PROXY_SCRIPT, "status"], timeout=10)
    data = {
        "PROXY_TYPE": "socks5",
        "PROXY_HOST": "",
        "PROXY_PORT": "",
        "PROXY_USERNAME": "",
        "PROXY_PASSWORD_SET": "no",
        "PROXY_LOCAL_PORT": "12345",
    }

    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

    return data


def get_log_retention_status() -> str:
    _, output = run_cmd(["sudo", LOG_RETENTION_SCRIPT, "status"], timeout=10)
    return output or "No log retention status."




def logs_total_size() -> str:
    total = 0
    for path in LOG_DIR.glob("*.log"):
        try:
            total += path.stat().st_size
        except Exception:
            pass
    if total >= 1024 * 1024:
        return f"{total / (1024 * 1024):.1f} MB"
    if total >= 1024:
        return f"{total / 1024:.0f} KB"
    return f"{total} B"



@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if logged_in(request):
        return RedirectResponse("/", status_code=303)
    return login_page()


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request):
    body = (await request.body()).decode()
    form = parse_qs(body)

    username = form.get("username", [""])[0]
    password = form.get("password", [""])[0]

    ok_user = secrets.compare_digest(username, ADMIN_USER)
    ok_pass = secrets.compare_digest(password_hash(password), ADMIN_PASSWORD_SHA256)

    if ok_user and ok_pass:
        request.session["user"] = ADMIN_USER
        return RedirectResponse("/", status_code=303)

    return login_page("Invalid username or password")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not logged_in(request):
        return redirect_login()

    status_raw = get_status_raw()
    mode = get_current_mode(status_raw).lower()
    clients = get_clients()
    inet = get_internet_source()

    blocked_domains = []
    try:
        blocked_domains = get_blocked_domains()
    except Exception:
        blocked_domains = []

    tor_active = mode == "tor"
    proxy_active = mode == "proxy"
    blocking_active = len(blocked_domains) > 0
    inet_connected = bool(inet["device"])

    inet_line = "diagram-line diagram-line-active" if inet_connected else "diagram-line diagram-line-inactive"

    def ic(on): return "diagram-node-icon active" if on else "diagram-node-icon off"
    def lc(on): return "diagram-node-label active" if on else "diagram-node-label"

    inet_svg = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1"/></svg>"""
    if inet["type"] == "USB Tethering":
        inet_svg = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="7" y="2" width="10" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18.01"/></svg>"""
    elif inet["type"] == "Ethernet":
        inet_svg = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="10" rx="2"/><line x1="6" y1="11" x2="6" y2="13"/><line x1="10" y1="11" x2="10" y2="13"/><line x1="14" y1="11" x2="14" y2="13"/><line x1="18" y1="11" x2="18" y2="13"/></svg>"""

    body = f"""
<div class="net-diagram">
  <div class="diagram-row">
    <div class="diagram-col">
      <div class="diagram-node">
        <div class="{ic(inet_connected)}" style="width:58px;height:58px;">{inet_svg}</div>
        <div class="{lc(inet_connected)}" style="margin-top:8px;font-size:13px;font-weight:800;">{html.escape(inet["type"])}</div>
        <div class="diagram-node-label" style="font-size:11px;">{html.escape(inet["name"])}</div>
      </div>
    </div>
    <div class="{inet_line}"></div>
    <div class="diagram-col diagram-center">
      <div class="diagram-device-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M7 22h10"/><path d="M9 18v4"/><path d="M15 18v4"/><circle cx="12" cy="11" r="3"/><path d="M12 8V6"/><path d="M15 11h2"/><path d="M12 14v2"/><path d="M9 11H7"/></svg>
      </div>
      <div class="diagram-device-label">Thorestic Gateway</div>
      <div class="diagram-device-sub">Raspberry Pi 4 &middot; 192.168.50.1</div>
    </div>
    <div class="diagram-line diagram-line-active"></div>
    <div class="diagram-col">
      <div class="diagram-node">
        <div class="{ic(len(clients)>0)}" style="width:58px;height:58px;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:28px;height:28px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        </div>
        <div class="{lc(len(clients)>0)}" style="margin-top:8px;font-size:13px;font-weight:800;">LAN Clients</div>
        <div class="diagram-node-label" style="font-size:18px;font-weight:900;color:#f1f5f9;">{len(clients)}</div>
      </div>
    </div>
  </div>

  <div class="services-row" aria-label="Service status">
    <div class="svc-toggle service-status" title="Tor: {"Active" if tor_active else "Off"}" aria-label="Tor {"active" if tor_active else "off"}">
      <div class="{ic(tor_active)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg>
      </div>
    </div>

    <div class="svc-toggle service-status" title="VPN: Off" aria-label="VPN off">
      <div class="{ic(False)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      </div>
    </div>

    <div class="svc-toggle service-status" title="Proxy: {"Active" if proxy_active else "Off"}" aria-label="Proxy {"active" if proxy_active else "off"}">
      <div class="{ic(proxy_active)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.66 0 3-4.03 3-9s-1.34-9-3-9m0 18c-1.66 0-3-4.03-3-9s1.34-9 3-9"/></svg>
      </div>
    </div>

    <div class="svc-toggle service-status" title="DNS Block: {"Active" if blocking_active else "Off"}" aria-label="DNS Block {"active" if blocking_active else "off"}">
      <div class="{ic(blocking_active)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
      </div>
    </div>
  </div>
</div>

<div class="info-cards">
  <div class="info-card">
    <div class="info-card-label">Mode</div>
    <div class="info-card-value sm" id="card-mode">{html.escape(mode.upper())}</div>
    <div class="info-card-note">Current routing mode</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Clients</div>
    <div class="info-card-value">{len(clients)}</div>
    <div class="info-card-note">Connected devices</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Blocked</div>
    <div class="info-card-value">{len(blocked_domains)}</div>
    <div class="info-card-note">DNS blocked domains</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Logs</div>
    <div class="info-card-value sm">{logs_total_size()}</div>
    <div class="info-card-note">Total log size</div>
  </div>
</div>

<div class="info-cards" id="sysmon" style="margin-top:0;">
  <div class="info-card">
    <div class="info-card-label">CPU Load</div>
    <div class="info-card-value" id="sys-cpu" style="font-size:24px;">—</div>
    <div class="info-card-note">1-min average</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Memory</div>
    <div class="info-card-value" id="sys-mem" style="font-size:20px;">—</div>
    <div class="info-card-note" id="sys-mem-detail">used / total</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Temperature</div>
    <div class="info-card-value" id="sys-temp" style="font-size:24px;">—</div>
    <div class="info-card-note">SoC thermal</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Uptime</div>
    <div class="info-card-value sm" id="sys-uptime">—</div>
    <div class="info-card-note">Since last boot</div>
  </div>
</div>

<div class="quick-grid">
  <a class="quick-card" href="/tor">
    <div class="quick-card-icon" style="background:linear-gradient(135deg,#7c3aed,#a855f7);"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/></svg></div>
    <div class="quick-card-text"><div class="quick-card-title">Tor</div><div class="quick-card-sub" id="qc-tor">{"Active" if tor_active else "Off"}</div></div>
  </a>
  <a class="quick-card" href="/proxy">
    <div class="quick-card-icon" style="background:linear-gradient(135deg,#059669,#10b981);"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 1-9 9m9-9a9 9 0 0 0-9-9m9 9H3m9 9a9 9 0 0 1-9-9m9 9c1.66 0 3-4.03 3-9s-1.34-9-3-9m0 18c-1.66 0-3-4.03-3-9s1.34-9 3-9"/></svg></div>
    <div class="quick-card-text"><div class="quick-card-title">Proxy</div><div class="quick-card-sub" id="qc-proxy">{"Active" if proxy_active else "Off"}</div></div>
  </a>
  <a class="quick-card" href="/clients">
    <div class="quick-card-icon" style="background:linear-gradient(135deg,#2563eb,#06b6d4);"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></div>
    <div class="quick-card-text"><div class="quick-card-title">Clients</div><div class="quick-card-sub">{len(clients)} devices</div></div>
  </a>
  <a class="quick-card" href="/blocking">
    <div class="quick-card-icon" style="background:linear-gradient(135deg,#dc2626,#f97316);"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg></div>
    <div class="quick-card-text"><div class="quick-card-title">Blocking</div><div class="quick-card-sub">{len(blocked_domains)} domains</div></div>
  </a>
</div>

<script>
async function loadSysmon() {{
  try {{
    const r = await fetch('/api/system');
    const d = await r.json();
    document.getElementById('sys-cpu').textContent = d.cpu_load;
    document.getElementById('sys-mem').textContent = d.mem_pct;
    document.getElementById('sys-mem-detail').textContent = d.mem_used + ' / ' + d.mem_total;
    document.getElementById('sys-temp').textContent = d.temp;
    document.getElementById('sys-uptime').textContent = d.uptime;
  }} catch(e) {{}}
}}
loadSysmon();
setInterval(loadSysmon, 10000);
</script>
"""
    return layout("Dashboard", "dashboard", body)


@app.get("/network", response_class=HTMLResponse)
async def network_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    wifi = get_wifi_status()
    state = html.escape(wifi.get("state", "unknown"))
    ssid = html.escape(wifi.get("ssid") or wifi.get("connection") or "Not connected")
    ip = html.escape(wifi.get("ip") or "-")
    gateway = html.escape(wifi.get("gateway") or "-")

    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">Network</h1>
    <div class="page-sub">Wi-Fi uplink for Raspberry Pi internet access</div>
  </div>
</div>

<div class="info-cards" style="margin-bottom:18px;">
  <div class="info-card">
    <div class="info-card-label">Wi-Fi State</div>
    <div class="info-card-value sm" id="wifi-state">{state}</div>
    <div class="info-card-note">wlan0</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Connected SSID</div>
    <div class="info-card-value sm" id="wifi-ssid">{ssid}</div>
    <div class="info-card-note">Current uplink</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">IP Address</div>
    <div class="info-card-value sm" id="wifi-ip">{ip}</div>
    <div class="info-card-note">Assigned to wlan0</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Gateway</div>
    <div class="info-card-value sm" id="wifi-gateway">{gateway}</div>
    <div class="info-card-note">Default route</div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;direction:ltr;">
      <h2 style="margin:0;text-align:left;">Available Wi-Fi</h2>
      <button class="btn-direct" style="padding:10px 18px;font-size:13px;" onclick="scanNetworks()">Scan</button>
    </div>
    <div id="networkList" style="margin-top:16px;direction:ltr;text-align:left;">
      <div style="color:var(--muted);font-size:13px;">Click Scan to load nearby networks.</div>
    </div>
  </div>

  <div class="card">
    <h2 style="margin-top:0;direction:ltr;text-align:left;">Connect</h2>
    <form onsubmit="return connectNetwork(event)" style="direction:ltr;text-align:left;">
      <label style="display:block;color:var(--muted);margin-bottom:8px;">SSID</label>
      <input id="net-ssid" name="ssid" placeholder="Network name"
        style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;margin-bottom:12px;">

      <label style="display:block;color:var(--muted);margin-bottom:8px;">Password</label>
      <input id="net-password" name="password" type="password" placeholder="Leave empty for open networks"
        style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;margin-bottom:14px;">

      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button class="btn-direct" style="padding:12px 22px;">Connect Raspberry Pi</button>
        <button type="button" class="btn-sm" style="padding:12px 18px;" onclick="disconnectNetwork()">Disconnect Wi-Fi</button>
      </div>
    </form>
    <pre id="networkOutput" style="display:none;margin-top:14px;background:#020617;border:1px solid var(--border);border-radius:10px;padding:12px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--green);max-height:220px;overflow:auto;white-space:pre-wrap;"></pre>
  </div>
</div>

<script>
function escText(text) {{
  const d = document.createElement('div');
  d.textContent = text || '';
  return d.innerHTML;
}}

function signalLabel(signal) {{
  if (signal >= 75) return 'Excellent';
  if (signal >= 50) return 'Good';
  if (signal >= 30) return 'Weak';
  return 'Poor';
}}

function chooseNetwork(ssid) {{
  document.getElementById('net-ssid').value = ssid;
  document.getElementById('net-password').focus();
}}

async function refreshNetworkStatus() {{
  try {{
    const r = await fetch('/api/network/status');
    const d = await r.json();
    document.getElementById('wifi-state').textContent = d.state || 'unknown';
    document.getElementById('wifi-ssid').textContent = d.ssid || d.connection || 'Not connected';
    document.getElementById('wifi-ip').textContent = d.ip || '-';
    document.getElementById('wifi-gateway').textContent = d.gateway || '-';
  }} catch(e) {{}}
}}

async function scanNetworks() {{
  const list = document.getElementById('networkList');
  list.innerHTML = '<div style="color:var(--muted);font-size:13px;">Scanning...</div>';
  try {{
    const r = await fetch('/api/network/scan');
    const d = await r.json();
    if (!d.networks || !d.networks.length) {{
      list.innerHTML = '<div style="color:var(--muted);font-size:13px;">No networks found.</div>';
      return;
    }}
    list.innerHTML = '';
    d.networks.forEach(n => {{
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.style.cssText = 'width:100%;display:flex;justify-content:space-between;align-items:center;gap:12px;text-align:left;margin-bottom:8px;padding:12px 14px;border-radius:12px;border:1px solid var(--border);background:#020617;color:var(--text);cursor:pointer;';
      btn.onclick = () => chooseNetwork(n.ssid || '');

      const left = document.createElement('span');
      left.style.cssText = 'min-width:0;';

      const name = document.createElement('span');
      name.style.cssText = 'display:block;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      name.textContent = n.ssid || '';

      const sec = document.createElement('span');
      sec.style.cssText = 'display:block;color:var(--muted);font-size:12px;margin-top:2px;';
      sec.textContent = n.security || 'open';

      const sig = document.createElement('span');
      sig.style.cssText = 'color:var(--green);font-size:12px;font-weight:800;flex:0 0 auto;';
      sig.textContent = (n.signal || 0) + '% · ' + signalLabel(n.signal || 0);

      left.appendChild(name);
      left.appendChild(sec);
      btn.appendChild(left);
      btn.appendChild(sig);
      list.appendChild(btn);
    }});
  }} catch(e) {{
    list.innerHTML = '<div style="color:var(--red);font-size:13px;">Scan failed.</div>';
  }}
}}

async function connectNetwork(e) {{
  e.preventDefault();
  const out = document.getElementById('networkOutput');
  const body = new URLSearchParams({{
    ssid: document.getElementById('net-ssid').value,
    password: document.getElementById('net-password').value,
  }});
  out.style.display = 'block';
  out.style.color = 'var(--blue)';
  out.textContent = 'Connecting...';
  try {{
    const r = await fetch('/api/network/connect', {{ method: 'POST', body }});
    const d = await r.json();
    out.style.color = d.ok ? 'var(--green)' : 'var(--red)';
    out.textContent = d.output || d.error || 'Done.';
    setTimeout(refreshNetworkStatus, 2500);
  }} catch(err) {{
    out.style.color = 'var(--red)';
    out.textContent = 'Connection request failed.';
  }}
}}

async function disconnectNetwork() {{
  const out = document.getElementById('networkOutput');
  out.style.display = 'block';
  out.style.color = 'var(--blue)';
  out.textContent = 'Disconnecting wlan0...';
  try {{
    const r = await fetch('/api/network/disconnect', {{ method: 'POST' }});
    const d = await r.json();
    out.style.color = d.ok ? 'var(--green)' : 'var(--red)';
    out.textContent = d.output || d.error || 'Done.';
    setTimeout(refreshNetworkStatus, 1500);
  }} catch(err) {{
    out.style.color = 'var(--red)';
    out.textContent = 'Disconnect request failed.';
  }}
}}

refreshNetworkStatus();
</script>
"""
    return layout("Network", "network", body)


@app.get("/tor", response_class=HTMLResponse)
async def tor_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    current_mode = get_current_mode(get_status_raw()).lower()
    active = current_mode == "tor"
    toggle_cls = "svc-toggle on" if active else "svc-toggle"
    status_text = "ACTIVE" if active else "OFF"
    status_cls = "svc-status on" if active else "svc-status"

    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">Tor Network</h1>
    <div class="page-sub">Anonymous routing through The Onion Router</div>
  </div>
</div>

<div class="svc-hero tor-hero">
  <div class="svc-hero-top">
    <div class="svc-hero-icon">
      <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <circle cx="12" cy="12" r="6"/>
        <circle cx="12" cy="12" r="2"/>
      </svg>
    </div>
    <div>
      <h2 class="svc-hero-title">Tor Mode</h2>
      <span class="{status_cls}" id="torStatus">{status_text}</span>
    </div>
    <button class="{toggle_cls}" id="torToggle" onclick="toggleTor()" aria-label="Toggle Tor">
      <span class="svc-toggle-dot"></span>
    </button>
  </div>
  <p class="svc-hero-desc">Routes all connected device traffic through Tor transparent proxy (TransPort 9040, DNSPort 5353). Traffic is anonymized through multiple relay hops.</p>
  <div class="svc-loader" id="torLoader">
    <div class="svc-loader-bar"></div>
    <span class="svc-loader-text" id="torLoaderText">Switching...</span>
  </div>
</div>

<div class="svc-panels">
  <div class="svc-panel" id="torInfoPanel">
    <div class="svc-panel-head">
      <h3>Connection Info</h3>
      <button class="btn-sm" onclick="checkTorStatus()">Refresh</button>
    </div>
    <div class="svc-info-grid" id="torInfoGrid">
      <div class="svc-info-item">
        <div class="svc-info-label">Exit IP</div>
        <div class="svc-info-val" id="torIP">—</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Tor Verified</div>
        <div class="svc-info-val" id="torVerified">—</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Circuit Status</div>
        <div class="svc-info-val" id="torCircuit">—</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Current Mode</div>
        <div class="svc-info-val" id="torMode">{"tor" if active else current_mode}</div>
      </div>
    </div>
    <div class="svc-check-msg" id="torCheckMsg"></div>
  </div>

  <div class="svc-panel">
    <div class="svc-panel-head">
      <h3>Live Logs</h3>
      <button class="btn-sm" onclick="clearTorLog()">Clear</button>
    </div>
    <pre class="svc-log" id="torLog">Waiting for log data...</pre>
  </div>
</div>

<script>
let torActive = {'true' if active else 'false'};
let torSwitching = false;

async function toggleTor() {{
  if (torSwitching) return;
  torSwitching = true;

  const btn = document.getElementById('torToggle');
  const loader = document.getElementById('torLoader');
  const loaderText = document.getElementById('torLoaderText');

  const newMode = torActive ? 'direct' : 'tor';
  loaderText.textContent = torActive ? 'Disconnecting from Tor...' : 'Connecting to Tor network...';
  loader.classList.add('active');
  btn.classList.add('loading');

  try {{
    const resp = await fetch('/api/mode/set', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
      body: 'mode=' + newMode,
    }});
    const data = await resp.json();

    if (data.ok) {{
      torActive = data.tor;
      updateTorUI();
      showSvcToast(torActive ? 'Tor activated' : 'Tor deactivated', true);
      if (torActive) {{
        loaderText.textContent = 'Checking Tor connection...';
        startTorLog();
        await checkTorStatus();
      }} else {{
        if (torLogES) {{ torLogES.close(); torLogES = null; }}
        document.getElementById('torLog').textContent = 'Tor is off — logs will appear when Tor mode is activated.';
      }}
    }} else {{
      showSvcToast('Failed: ' + (data.message || 'unknown error'), false);
    }}
  }} catch(e) {{
    showSvcToast('Network error', false);
  }}

  loader.classList.remove('active');
  btn.classList.remove('loading');
  torSwitching = false;
}}

function updateTorUI() {{
  const btn = document.getElementById('torToggle');
  const st = document.getElementById('torStatus');
  btn.classList.toggle('on', torActive);
  st.textContent = torActive ? 'ACTIVE' : 'OFF';
  st.classList.toggle('on', torActive);
  document.getElementById('torMode').textContent = torActive ? 'tor' : 'direct';
}}

async function checkTorStatus() {{
  const msg = document.getElementById('torCheckMsg');
  const ipEl = document.getElementById('torIP');
  const verEl = document.getElementById('torVerified');
  const circEl = document.getElementById('torCircuit');

  msg.textContent = 'Checking Tor connection...';
  msg.className = 'svc-check-msg checking';
  ipEl.textContent = '...';
  verEl.textContent = '...';

  try {{
    const r = await fetch('/api/tor/check');
    const d = await r.json();

    ipEl.textContent = d.ip || '—';
    verEl.innerHTML = d.using_tor
      ? '<span style="color:var(--green)">&#10003; Yes</span>'
      : '<span style="color:var(--red)">&#10007; No</span>';
    circEl.textContent = d.using_tor ? 'Established' : (torActive ? 'Not verified' : 'Inactive');

    if (d.error) {{
      msg.textContent = d.error;
      msg.className = 'svc-check-msg error';
    }} else if (d.using_tor) {{
      msg.textContent = 'Tor connection verified successfully';
      msg.className = 'svc-check-msg success';
    }} else if (torActive) {{
      msg.textContent = 'Tor is active but check.torproject.org could not confirm';
      msg.className = 'svc-check-msg warn';
    }} else {{
      msg.textContent = '';
      msg.className = 'svc-check-msg';
    }}
  }} catch(e) {{
    msg.textContent = 'Failed to check Tor status';
    msg.className = 'svc-check-msg error';
  }}
}}

function showSvcToast(text, ok) {{
  const existing = document.querySelector('.svc-toast');
  if (existing) existing.remove();
  const t = document.createElement('div');
  t.className = 'svc-toast ' + (ok ? 'ok' : 'fail');
  t.textContent = text;
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => {{ t.classList.remove('show'); setTimeout(() => t.remove(), 300); }}, 3000);
}}

// Live log via SSE
let torLogES = null;
function startTorLog() {{
  if (torLogES) torLogES.close();
  const logEl = document.getElementById('torLog');
  if (!torActive) {{
    logEl.textContent = 'Tor is off — logs will appear when Tor mode is activated.';
    return;
  }}
  logEl.textContent = '';
  torLogES = new EventSource('/stream/logs?kind=connections');
  torLogES.onmessage = function(e) {{
    logEl.textContent += e.data + '\\n';
    if (logEl.childNodes.length > 200) {{
      const lines = logEl.textContent.split('\\n');
      logEl.textContent = lines.slice(-150).join('\\n');
    }}
    logEl.scrollTop = logEl.scrollHeight;
  }};
}}

function clearTorLog() {{
  document.getElementById('torLog').textContent = '';
}}

startTorLog();
if (torActive) checkTorStatus();
</script>
"""
    return layout("Tor", "tor", body)


@app.get("/proxy", response_class=HTMLResponse)
async def proxy_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    current_mode = get_current_mode(get_status_raw()).lower()
    proxy_st = get_proxy_status()
    active = current_mode == "proxy"
    toggle_cls = "svc-toggle on" if active else "svc-toggle"
    status_text = "ACTIVE" if active else "OFF"
    status_cls = "svc-status on" if active else "svc-status"

    p_type = html.escape(proxy_st.get("PROXY_TYPE", "socks5"))
    p_host = html.escape(proxy_st.get("PROXY_HOST", ""))
    p_port = html.escape(proxy_st.get("PROXY_PORT", ""))
    p_user = html.escape(proxy_st.get("PROXY_USERNAME", ""))
    has_pw = proxy_st.get("PROXY_PASSWORD_SET", "no") == "yes" or bool(proxy_st.get("PROXY_PASSWORD", ""))
    pw_hint = "Password is set" if has_pw else "No password configured"

    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">Proxy</h1>
    <div class="page-sub">SOCKS5 / HTTP proxy routing via redsocks</div>
  </div>
</div>

<div class="svc-hero proxy-hero">
  <div class="svc-hero-top">
    <div class="svc-hero-icon">
      <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
        <path d="M2 17l10 5 10-5"/>
        <path d="M2 12l10 5 10-5"/>
      </svg>
    </div>
    <div>
      <h2 class="svc-hero-title">Proxy Mode</h2>
      <span class="{status_cls}" id="proxyStatus">{status_text}</span>
    </div>
    <button class="{toggle_cls}" id="proxyToggle" onclick="toggleProxy()" aria-label="Toggle Proxy">
      <span class="svc-toggle-dot"></span>
    </button>
  </div>
  <p class="svc-hero-desc">Routes all device traffic through a SOCKS5 or HTTP proxy via redsocks (local port 12345). Configure your proxy server below.</p>
  <div class="svc-loader" id="proxyLoader">
    <div class="svc-loader-bar"></div>
    <span class="svc-loader-text" id="proxyLoaderText">Switching...</span>
  </div>

  <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap;">
    <button class="btn-sm" style="padding:8px 16px;font-size:13px;" onclick="document.getElementById('proxySettingsDlg').showModal()">
      Proxy Settings
    </button>
    <span style="font-size:12px;color:var(--muted);align-self:center;">
      {p_type} &middot; {p_host or 'not set'}:{p_port or '—'} &middot; {pw_hint}
    </span>
  </div>
</div>

<div class="svc-panels">
  <div class="svc-panel" id="proxyInfoPanel">
    <div class="svc-panel-head">
      <h3>Connection Info</h3>
      <button class="btn-sm" onclick="checkProxyStatus()">Refresh</button>
    </div>
    <div class="svc-info-grid" id="proxyInfoGrid">
      <div class="svc-info-item">
        <div class="svc-info-label">Exit IP</div>
        <div class="svc-info-val" id="proxyIP">—</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Proxy Type</div>
        <div class="svc-info-val" id="proxyType">{p_type}</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Proxy Server</div>
        <div class="svc-info-val" id="proxyServer" style="font-size:13px;">{p_host}:{p_port}</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Current Mode</div>
        <div class="svc-info-val" id="proxyMode">{"proxy" if active else current_mode}</div>
      </div>
    </div>
    <div class="svc-check-msg" id="proxyCheckMsg"></div>
  </div>

  <div class="svc-panel">
    <div class="svc-panel-head">
      <h3>Live Logs</h3>
      <button class="btn-sm" onclick="clearProxyLog()">Clear</button>
    </div>
    <pre class="svc-log" id="proxyLog">Waiting for log data...</pre>
  </div>
</div>

<dialog id="proxySettingsDlg" class="proxy-modal">
  <div class="proxy-modal-inner">
    <div class="proxy-modal-head">
      <h2>Proxy Settings</h2>
      <button class="btn-sm" onclick="document.getElementById('proxySettingsDlg').close()" style="padding:8px 14px;">Close</button>
    </div>

    <div class="proxy-tabs">
      <button class="proxy-tab active" id="tabManual" onclick="switchProxyTab('manual')">Manual</button>
      <button class="proxy-tab" id="tabFile" onclick="switchProxyTab('file')">Import File</button>
    </div>

    <div id="proxyTabManual">
      <form class="proxy-form-grid" onsubmit="return saveProxyManual(event)">
        <div>
          <label>Type</label>
          <select id="pf-type">
            <option value="socks5" {"selected" if p_type == "socks5" else ""}>SOCKS5</option>
            <option value="http-connect" {"selected" if p_type == "http-connect" else ""}>HTTP-Connect</option>
          </select>
        </div>
        <div>
          <label>Host</label>
          <input id="pf-host" value="{p_host}" placeholder="proxy.example.com">
        </div>
        <div>
          <label>Port</label>
          <input id="pf-port" value="{p_port}" placeholder="1080">
        </div>
        <div>
          <label>Username</label>
          <input id="pf-user" value="{p_user}" placeholder="username">
        </div>
        <div>
          <label>Password</label>
          <input id="pf-pass" type="password" placeholder="Leave empty to keep current">
        </div>
        <div style="grid-column:1/-1;">
          <button class="btn-direct" style="width:100%;padding:12px;">Save Proxy</button>
        </div>
      </form>
    </div>

    <div id="proxyTabFile" style="display:none;">
      <div class="proxy-file-drop" id="proxyFileDrop"
           ondragover="event.preventDefault();this.classList.add('dragover')"
           ondragleave="this.classList.remove('dragover')"
           ondrop="handleProxyFileDrop(event)">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:8px;">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <div>Drop a proxy file here or <label style="color:var(--blue);cursor:pointer;text-decoration:underline;">browse<input type="file" id="proxyFileInput" accept=".txt,.conf,.json,.csv" onchange="handleProxyFile(this.files[0])" style="display:none;"></label></div>
        <div style="font-size:11px;margin-top:6px;color:var(--muted);">Drop a .txt, .csv, or .conf file with proxies (one per line)</div>
        <div style="font-size:10px;margin-top:8px;color:var(--muted);background:rgba(15,23,42,0.5);padding:8px 10px;border-radius:8px;font-family:'JetBrains Mono',monospace;line-height:1.7;">
          <strong style="color:var(--text);">Format examples:</strong><br>
          socks5:host:port:user:pass<br>
          http-connect:host:port:user:pass<br>
          host:port:user:pass<br>
          host:port<br>
          <span style="color:var(--muted);"># Lines starting with # are ignored</span>
        </div>
      </div>
      <pre class="svc-log" id="proxyFilePreview" style="min-height:80px;max-height:160px;margin-top:12px;display:none;"></pre>
      <button class="btn-direct" id="proxyFileApply" style="width:100%;padding:12px;margin-top:12px;display:none;" onclick="applyProxyFile()">Apply First Proxy</button>
    </div>
  </div>
</dialog>

<script>
let proxyActive = {'true' if active else 'false'};
let proxySwitching = false;
let parsedProxies = [];

async function toggleProxy() {{
  if (proxySwitching) return;
  proxySwitching = true;

  const btn = document.getElementById('proxyToggle');
  const loader = document.getElementById('proxyLoader');
  const loaderText = document.getElementById('proxyLoaderText');

  const newMode = proxyActive ? 'direct' : 'proxy';
  loaderText.textContent = proxyActive ? 'Disconnecting proxy...' : 'Connecting via proxy...';
  loader.classList.add('active');
  btn.classList.add('loading');

  try {{
    const resp = await fetch('/api/mode/set', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
      body: 'mode=' + newMode,
    }});
    const data = await resp.json();

    if (data.ok) {{
      proxyActive = data.proxy;
      updateProxyUI();
      showSvcToast(proxyActive ? 'Proxy activated' : 'Proxy deactivated', true);
      if (proxyActive) {{
        loaderText.textContent = 'Checking proxy connection...';
        startProxyLog();
        await checkProxyStatus();
      }} else {{
        stopProxyLog();
      }}
    }} else {{
      showSvcToast('Failed: ' + (data.message || 'unknown error'), false);
    }}
  }} catch(e) {{
    showSvcToast('Network error', false);
  }}

  loader.classList.remove('active');
  btn.classList.remove('loading');
  proxySwitching = false;
}}

function updateProxyUI() {{
  const btn = document.getElementById('proxyToggle');
  const st = document.getElementById('proxyStatus');
  btn.classList.toggle('on', proxyActive);
  st.textContent = proxyActive ? 'ACTIVE' : 'OFF';
  st.classList.toggle('on', proxyActive);
  document.getElementById('proxyMode').textContent = proxyActive ? 'proxy' : 'direct';
}}

async function checkProxyStatus() {{
  const msg = document.getElementById('proxyCheckMsg');
  const ipEl = document.getElementById('proxyIP');

  msg.textContent = 'Checking proxy connection...';
  msg.className = 'svc-check-msg checking';
  ipEl.textContent = '...';

  try {{
    const r = await fetch('/api/proxy/check');
    const d = await r.json();
    ipEl.textContent = d.ip || '—';

    if (d.error) {{
      msg.textContent = d.error;
      msg.className = 'svc-check-msg warn';
    }} else {{
      msg.textContent = 'Proxy connection verified — exit IP: ' + d.ip;
      msg.className = 'svc-check-msg success';
    }}
  }} catch(e) {{
    msg.textContent = 'Failed to check proxy status';
    msg.className = 'svc-check-msg error';
  }}
}}

async function saveProxyManual(e) {{
  e.preventDefault();
  const body = new URLSearchParams({{
    proxy_type: document.getElementById('pf-type').value,
    host: document.getElementById('pf-host').value,
    port: document.getElementById('pf-port').value,
    username: document.getElementById('pf-user').value,
    password: document.getElementById('pf-pass').value,
  }});

  try {{
    const r = await fetch('/settings/proxy', {{ method: 'POST', body }});
    if (r.ok || r.redirected) {{
      showSvcToast('Proxy settings saved', true);
      document.getElementById('proxySettingsDlg').close();
      setTimeout(() => location.reload(), 500);
    }} else {{
      showSvcToast('Failed to save proxy settings', false);
    }}
  }} catch(err) {{
    showSvcToast('Error saving settings', false);
  }}
}}

function switchProxyTab(tab) {{
  document.getElementById('tabManual').classList.toggle('active', tab === 'manual');
  document.getElementById('tabFile').classList.toggle('active', tab === 'file');
  document.getElementById('proxyTabManual').style.display = tab === 'manual' ? '' : 'none';
  document.getElementById('proxyTabFile').style.display = tab === 'file' ? '' : 'none';
}}

function handleProxyFileDrop(e) {{
  e.preventDefault();
  e.currentTarget.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) handleProxyFile(file);
}}

function handleProxyFile(file) {{
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {{
    const text = e.target.result;
    const lines = text.split('\\n').filter(l => l.trim() && !l.trim().startsWith('#'));
    parsedProxies = [];
    const preview = document.getElementById('proxyFilePreview');
    const applyBtn = document.getElementById('proxyFileApply');

    for (const line of lines) {{
      const parts = line.trim().split(':');
      if (parts.length >= 2) {{
        parsedProxies.push(line.trim());
      }}
    }}

    preview.textContent = parsedProxies.length
      ? 'Found ' + parsedProxies.length + ' proxies:\\n' + parsedProxies.slice(0, 10).join('\\n')
      : 'No valid proxies found in file.';
    preview.style.display = '';
    applyBtn.style.display = parsedProxies.length ? '' : 'none';
  }};
  reader.readAsText(file);
}}

async function applyProxyFile() {{
  if (!parsedProxies.length) return;
  const first = parsedProxies[0];
  const parts = first.split(':');

  let type = 'socks5', host = '', port = '', user = '', pass = '';
  if (parts[0].match(/^(socks5|http-connect|http|socks)/i)) {{
    type = parts[0].toLowerCase().replace('http', 'http-connect').replace('socks', 'socks5');
    if (type === 'socks5h') type = 'socks5';
    if (type === 'http-connect-connect') type = 'http-connect';
    host = parts[1] || '';
    port = parts[2] || '';
    user = parts[3] || '';
    pass = parts[4] || '';
  }} else {{
    host = parts[0] || '';
    port = parts[1] || '';
    user = parts[2] || '';
    pass = parts[3] || '';
  }}
  host = host.replace(/\\/\\//g, '');

  const body = new URLSearchParams({{ proxy_type: type, host, port, username: user, password: pass }});
  try {{
    const r = await fetch('/settings/proxy', {{ method: 'POST', body }});
    if (r.ok || r.redirected) {{
      showSvcToast('Proxy imported from file', true);
      document.getElementById('proxySettingsDlg').close();
      setTimeout(() => location.reload(), 500);
    }} else {{
      showSvcToast('Failed to import proxy', false);
    }}
  }} catch(err) {{
    showSvcToast('Error importing', false);
  }}
}}

function showSvcToast(text, ok) {{
  const existing = document.querySelector('.svc-toast');
  if (existing) existing.remove();
  const t = document.createElement('div');
  t.className = 'svc-toast ' + (ok ? 'ok' : 'fail');
  t.textContent = text;
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => {{ t.classList.remove('show'); setTimeout(() => t.remove(), 300); }}, 3000);
}}

// Live log via SSE — only when proxy is active
let proxyLogES = null;
function startProxyLog() {{
  if (proxyLogES) proxyLogES.close();
  const logEl = document.getElementById('proxyLog');
  if (!proxyActive) {{
    logEl.textContent = 'Proxy is off — logs will appear when proxy mode is activated.';
    return;
  }}
  logEl.textContent = '';
  proxyLogES = new EventSource('/stream/logs?kind=connections');
  proxyLogES.onmessage = function(e) {{
    logEl.textContent += e.data + '\\n';
    if (logEl.childNodes.length > 200) {{
      const lines = logEl.textContent.split('\\n');
      logEl.textContent = lines.slice(-150).join('\\n');
    }}
    logEl.scrollTop = logEl.scrollHeight;
  }};
}}

function stopProxyLog() {{
  if (proxyLogES) {{ proxyLogES.close(); proxyLogES = null; }}
  document.getElementById('proxyLog').textContent = 'Proxy is off — logs will appear when proxy mode is activated.';
}}

function clearProxyLog() {{
  document.getElementById('proxyLog').textContent = '';
}}

startProxyLog();
if (proxyActive) checkProxyStatus();

const dlg = document.getElementById('proxySettingsDlg');
dlg.addEventListener('click', function(e) {{ if (e.target === dlg) dlg.close(); }});
</script>
"""
    return layout("Proxy", "proxy", body)


@app.get("/vpn", response_class=HTMLResponse)
async def vpn_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = """
<div class="topline">
  <div>
    <h1 class="page-title">VPN</h1>
    <div class="page-sub">WireGuard / OpenVPN tunneling</div>
  </div>
</div>

<div class="svc-hero" style="border-color:rgba(148,163,184,0.08);">
  <div class="svc-hero-top">
    <div class="svc-hero-icon" style="background:rgba(148,163,184,0.08);color:var(--muted);">
      <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0110 0v4"/>
      </svg>
    </div>
    <div>
      <h2 class="svc-hero-title">VPN Mode</h2>
      <span class="svc-status" style="background:rgba(148,163,184,0.08);color:var(--muted);">COMING SOON</span>
    </div>
    <button class="svc-toggle" disabled style="opacity:0.3;cursor:not-allowed;margin-left:auto;" aria-label="VPN disabled">
      <span class="svc-toggle-dot"></span>
    </button>
  </div>
  <p class="svc-hero-desc">VPN mode is under development. It will support WireGuard config upload, provider profiles (Mullvad, ProtonVPN, etc.), and transparent VPN routing for all connected devices.</p>

  <div style="margin-top:20px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
    <div class="svc-info-item" style="opacity:0.5;">
      <div class="svc-info-label">Protocol</div>
      <div class="svc-info-val" style="font-size:14px;">WireGuard / OpenVPN</div>
    </div>
    <div class="svc-info-item" style="opacity:0.5;">
      <div class="svc-info-label">Status</div>
      <div class="svc-info-val" style="font-size:14px;">Not configured</div>
    </div>
  </div>
</div>
"""
    return layout("VPN", "vpn", body)


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    clients = get_clients()
    blocked = get_blocked_clients()
    disconnected = get_disconnected_clients()

    total = len(clients)
    active_count = sum(1 for c in clients if c["ip"] not in blocked and c["ip"] not in disconnected)
    blocked_count = sum(1 for c in clients if c["ip"] in blocked)
    disc_count = sum(1 for c in clients if c["ip"] in disconnected)

    cards = ""
    for client in clients:
        ip = client["ip"]
        if ip in blocked:
            state = "BLOCKED"
            state_cls = "cl-state blocked"
            dot_cls = "cl-dot blocked"
        elif ip in disconnected:
            state = "DISCONNECTED"
            state_cls = "cl-state disc"
            dot_cls = "cl-dot disc"
        else:
            state = client["state"]
            state_cls = "cl-state active"
            dot_cls = "cl-dot active"

        name = html.escape(client_display_name(client))
        mac = html.escape(client["mac"])

        cards += f"""
<div class="cl-card" onclick="openClient('{html.escape(ip)}')">
  <div class="cl-card-top">
    <div class="{dot_cls}"></div>
    <div class="cl-card-info">
      <div class="cl-card-name">{name}</div>
      <div class="cl-card-ip">{html.escape(ip)}</div>
    </div>
    <span class="{state_cls}">{html.escape(state)}</span>
  </div>
  <div class="cl-card-bottom">
    <span class="cl-card-mac">{mac}</span>
  </div>
</div>
"""

    if not cards:
        cards = '<div style="text-align:center;padding:40px;color:var(--muted);">No clients detected yet. Connect a device to the network.</div>'

    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">Clients</h1>
    <div class="page-sub">Connected devices and access controls</div>
  </div>
</div>

<div class="info-cards" style="margin-bottom:18px;">
  <div class="info-card">
    <div class="info-card-label">Total</div>
    <div class="info-card-value">{total}</div>
    <div class="info-card-note">All devices</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Active</div>
    <div class="info-card-value" style="color:var(--green);">{active_count}</div>
    <div class="info-card-note">Connected</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Blocked</div>
    <div class="info-card-value" style="color:var(--red);">{blocked_count}</div>
    <div class="info-card-note">Firewall blocked</div>
  </div>
  <div class="info-card">
    <div class="info-card-label">Disconnected</div>
    <div class="info-card-value" style="color:var(--yellow);">{disc_count}</div>
    <div class="info-card-note">Temporarily cut</div>
  </div>
</div>

<div class="cl-grid">{cards}</div>

<dialog id="clientModal" class="proxy-modal" style="max-width:560px;">
  <div class="proxy-modal-inner" id="cm-body">Loading...</div>
</dialog>

<script>
const modal = document.getElementById('clientModal');

async function openClient(ip) {{
  modal.showModal();
  document.getElementById('cm-body').innerHTML = '<div style="text-align:center;padding:40px;">Loading...</div>';

  try {{
    const r = await fetch('/api/clients/' + encodeURIComponent(ip));
    const d = await r.json();
    renderClient(d);
  }} catch(e) {{
    document.getElementById('cm-body').innerHTML = '<p style="color:var(--red);">Error loading client</p>';
  }}
}}

function renderClient(d) {{
  const blocked = d.blocked;
  const disc = d.disconnected;
  const stColor = blocked ? 'var(--red)' : (disc ? 'var(--yellow)' : 'var(--green)');

  document.getElementById('cm-body').innerHTML = `
    <div class="proxy-modal-head">
      <h2>${{esc(d.display_name)}}</h2>
      <button class="btn-sm" style="padding:8px 14px;" onclick="modal.close()">Close</button>
    </div>

    <div class="svc-info-grid" style="margin-bottom:20px;">
      <div class="svc-info-item">
        <div class="svc-info-label">IP Address</div>
        <div class="svc-info-val" style="font-size:14px;">${{esc(d.ip)}}</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Status</div>
        <div class="svc-info-val" style="font-size:14px;color:${{stColor}};">${{esc(d.state)}}</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">MAC Address</div>
        <div class="svc-info-val" style="font-size:12px;">${{esc(d.mac)}}</div>
      </div>
      <div class="svc-info-item">
        <div class="svc-info-label">Hostname</div>
        <div class="svc-info-val" style="font-size:12px;">${{esc(d.hostname)}}</div>
      </div>
    </div>

    <div style="margin-bottom:20px;">
      <label style="font-size:12px;color:var(--muted);display:block;margin-bottom:6px;">Device Name</label>
      <form onsubmit="return saveClientMeta(event, '${{esc(d.ip)}}')">
        <input id="cm-name" value="${{esc(d.custom_name)}}" placeholder="Give this device a name..."
          style="width:100%;padding:10px 14px;border-radius:10px;border:1px solid var(--border);background:#020617;color:white;font-size:14px;margin-bottom:8px;">
        <textarea id="cm-notes" placeholder="Notes about this device..." rows="2"
          style="width:100%;padding:10px 14px;border-radius:10px;border:1px solid var(--border);background:#020617;color:white;font-size:13px;resize:vertical;">${{esc(d.notes)}}</textarea>
        <button class="btn-direct" style="margin-top:8px;padding:9px 16px;font-size:13px;">Save</button>
      </form>
    </div>

    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;">
      ${{blocked
        ? `<button class="btn-direct" style="padding:10px 18px;font-size:13px;" onclick="clientAction('${{d.ip}}','unblock')">Unblock</button>`
        : `<button style="padding:10px 18px;font-size:13px;border-radius:10px;border:1px solid rgba(239,68,68,0.3);background:rgba(239,68,68,0.1);color:var(--red);cursor:pointer;" onclick="clientAction('${{d.ip}}','block')">Block</button>`
      }}
      ${{disc
        ? `<button class="btn-direct" style="padding:10px 18px;font-size:13px;" onclick="clientAction('${{d.ip}}','reconnect')">Reconnect</button>`
        : `<button style="padding:10px 18px;font-size:13px;border-radius:10px;border:1px solid rgba(245,158,11,0.3);background:rgba(245,158,11,0.1);color:var(--yellow);cursor:pointer;" onclick="clientAction('${{d.ip}}','disconnect')">Disconnect</button>`
      }}
    </div>

    <div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">Recent Activity</div>
      <pre class="svc-log" style="min-height:80px;max-height:160px;">${{esc(d.logs || 'No logs yet.')}}</pre>
    </div>
  `;
}}

function esc(s) {{
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}}

async function saveClientMeta(e, ip) {{
  e.preventDefault();
  const name = document.getElementById('cm-name').value;
  const notes = document.getElementById('cm-notes').value;
  await fetch('/clients/' + encodeURIComponent(ip) + '/metadata', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
    body: 'name=' + encodeURIComponent(name) + '&notes=' + encodeURIComponent(notes),
  }});
  location.reload();
}}

async function clientAction(ip, action) {{
  await fetch('/clients/' + encodeURIComponent(ip) + '/' + action, {{ method: 'POST' }});
  openClient(ip);
}}

modal.addEventListener('click', function(e) {{
  if (e.target === modal) modal.close();
}});
</script>
"""
    return layout("Clients", "clients", body)


@app.get("/clients/{ip}/edit", response_class=HTMLResponse)
async def client_edit_page(request: Request, ip: str):
    if not logged_in(request):
        return redirect_login()

    clients = get_clients()
    client = next((c for c in clients if c["ip"] == ip), None)

    blocked = ip in get_blocked_clients()
    disconnected = ip in get_disconnected_clients()
    recent_logs = client_recent_logs(ip)

    hostname = client["hostname"] if client else "-"
    mac = client["mac"] if client else "-"
    meta = client_meta(client) if client else {"name": "", "notes": ""}
    display_name = client_display_name(client) if client else ip
    notes = meta.get("notes", "")
    state = "BLOCKED" if blocked else ("DISCONNECTED" if disconnected else (client["state"] if client else "UNKNOWN"))

    block_button = (
        f'<form action="/clients/{html.escape(ip)}/unblock" method="post"><button class="btn-direct">Unblock Internet</button></form>'
        if blocked else
        f'<form action="/clients/{html.escape(ip)}/block" method="post"><button class="btn-danger">Block Internet</button></form>'
    )

    disconnect_button = (
        f'<form action="/clients/{html.escape(ip)}/reconnect" method="post"><button class="btn-direct">Reconnect</button></form>'
        if disconnected else
        f'<form action="/clients/{html.escape(ip)}/disconnect" method="post"><button class="btn-danger">Disconnect</button></form>'
    )

    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">Edit Client</h1>
    <div class="page-sub">{html.escape(ip)}</div>
  </div>
  <a class="button-link btn-direct" href="/clients">Back</a>
</div>

<div class="grid-2">
  <div class="card metric">
    <div class="metric-label">IP</div>
    <div class="metric-value" style="font-size:24px;">{html.escape(ip)}</div>
  </div>

  <div class="card metric">
    <div class="metric-label">State</div>
    <div class="metric-value" style="font-size:24px;">{html.escape(state)}</div>
  </div>
</div>

<div class="card" style="margin-top:18px;direction:ltr;text-align:left;">
  <h2 style="margin-top:0;">Device Info</h2>
  <p><b>Display Name:</b> {html.escape(display_name)}</p>
  <p><b>Hostname:</b> {html.escape(hostname)}</p>
  <p><b>MAC:</b> {html.escape(mac)}</p>
</div>

<div class="card" style="margin-top:18px;direction:ltr;text-align:left;">
  <h2 style="margin-top:0;">Rename / Notes</h2>

  <form action="/clients/{html.escape(ip)}/metadata" method="post">
    <label style="display:block;color:var(--muted);margin-bottom:8px;">Device name</label>
    <input
      name="name"
      value="{html.escape(display_name if display_name != ip else '')}"
      placeholder="Mohammed iPhone"
      style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;"
    >

    <label style="display:block;color:var(--muted);margin:14px 0 8px;">Notes</label>
    <textarea
      name="notes"
      placeholder="Owner, purpose, class demo notes..."
      style="width:100%;min-height:110px;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;"
    >{html.escape(notes)}</textarea>

    <button class="btn-direct" style="margin-top:14px;">Save Device Info</button>
  </form>
</div>

<div class="card" style="margin-top:18px;">
  <h2 style="margin-top:0;direction:ltr;text-align:left;">Controls</h2>
  <div class="btn-row">
    {block_button}
    {disconnect_button}
  </div>
</div>

<div class="card" style="margin-top:18px;">
  <h2 style="margin-top:0;direction:ltr;text-align:left;">Recent Logs</h2>
  <div class="statusbox">{html.escape(recent_logs or "No logs for this client yet.")}</div>
</div>
"""
    return layout("Edit Client", "clients", body)


@app.post("/clients/{ip}/block")
async def client_block(request: Request, ip: str):
    if not logged_in(request):
        return redirect_login()

    run_cmd(["sudo", DEVICE_SCRIPT, "block", ip], timeout=20)
    return RedirectResponse(f"/clients/{ip}/edit", status_code=303)


@app.post("/clients/{ip}/unblock")
async def client_unblock(request: Request, ip: str):
    if not logged_in(request):
        return redirect_login()

    run_cmd(["sudo", DEVICE_SCRIPT, "unblock", ip], timeout=20)
    return RedirectResponse(f"/clients/{ip}/edit", status_code=303)


@app.post("/clients/{ip}/disconnect")
async def client_disconnect(request: Request, ip: str):
    if not logged_in(request):
        return redirect_login()

    run_cmd(["sudo", DEVICE_SCRIPT, "disconnect", ip], timeout=20)
    return RedirectResponse(f"/clients/{ip}/edit", status_code=303)


@app.post("/clients/{ip}/reconnect")
async def client_reconnect(request: Request, ip: str):
    if not logged_in(request):
        return redirect_login()

    run_cmd(["sudo", DEVICE_SCRIPT, "reconnect", ip], timeout=20)
    return RedirectResponse(f"/clients/{ip}/edit", status_code=303)





@app.post("/clients/{ip}/metadata")
async def client_metadata(request: Request, ip: str):
    if not logged_in(request):
        return redirect_login()

    clients = get_clients()
    client = next((c for c in clients if c["ip"] == ip), None)

    if not client:
        return RedirectResponse("/clients", status_code=303)

    mac = client.get("mac", "-")
    if not mac or mac == "-":
        return RedirectResponse(f"/clients/{ip}/edit", status_code=303)

    body = (await request.body()).decode()
    form = parse_qs(body)

    name = form.get("name", [""])[0].strip()
    notes = form.get("notes", [""])[0].strip()

    save_device_meta(mac, name, notes)

    return RedirectResponse(f"/clients/{ip}/edit", status_code=303)


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = """
<div class="topline">
  <div>
    <h1 class="page-title">Logs</h1>
    <div class="page-sub">Live DNS and connection metadata</div>
  </div>
</div>

<div class="card">
  <div class="log-toolbar">
    <button id="btn-combined" class="selected" onclick="switchLog('combined')">All</button>
    <button id="btn-dns" onclick="switchLog('dns')">DNS</button>
    <button id="btn-connections" onclick="switchLog('connections')">Connections</button>
    <button onclick="clearView()">Clear View</button>
  </div>

  <div id="logbox" class="log-box"></div>
</div>

<script>
let currentKind = "combined";
let source = null;

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, function(m) {
    return ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[m];
  });
}

function classify(line) {
  if (line.includes("[DNS]")) return "dns";
  if (line.includes("[CONNECTION]")) return "connection";
  return "other";
}

function label(line) {
  if (line.includes("[DNS]")) return "DNS";
  if (line.includes("[CONNECTION]")) return "CONNECTION";
  return "LOG";
}

function renderLine(line) {
  const cls = classify(line);
  const type = label(line);
  return '<div class="log-entry ' + cls + '">' +
         '<span class="log-type">' + escapeHtml(type) + '</span>' +
         '<span>' + escapeHtml(line) + '</span>' +
         '</div>';
}

function setSelected(kind) {
  ["combined", "dns", "connections"].forEach(k => {
    const btn = document.getElementById("btn-" + k);
    if (btn) btn.classList.toggle("selected", k === kind);
  });
}

function clearView() {
  document.getElementById("logbox").innerHTML = "";
}

function appendLog(line) {
  const box = document.getElementById("logbox");
  box.innerHTML += renderLine(line);

  const entries = box.querySelectorAll(".log-entry");
  if (entries.length > 350) {
    entries[0].remove();
  }

  box.scrollTop = box.scrollHeight;
}

function loadHistory(kind) {
  fetch("/api/logs?kind=" + encodeURIComponent(kind))
    .then(r => r.text())
    .then(text => {
      const box = document.getElementById("logbox");
      box.innerHTML = "";

      text.split("\\n").filter(Boolean).forEach(line => {
        box.innerHTML += renderLine(line);
      });

      box.scrollTop = box.scrollHeight;
    });
}

function switchLog(kind) {
  currentKind = kind;
  setSelected(kind);

  if (source) source.close();

  loadHistory(kind);

  source = new EventSource("/stream/logs?kind=" + encodeURIComponent(kind));
  source.onmessage = function(event) {
    appendLog(event.data);
  };
  source.onerror = function() {
    appendLog("[stream disconnected - retrying]");
  };
}

switchLog("combined");
</script>
"""
    return layout("Logs", "logs", body)



def get_blocked_domains() -> list[str]:
    _, output = run_cmd(["sudo", BLOCK_SCRIPT, "list"], timeout=10)
    domains = []
    for line in output.splitlines():
        domain = line.strip()
        if domain:
            domains.append(domain)
    return domains


@app.get("/blocking", response_class=HTMLResponse)
async def blocking_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    domains = get_blocked_domains()

    domain_tags = ""
    for domain in domains:
        safe = html.escape(domain)
        domain_tags += f"""
<div class="bl-tag">
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
  <span>{safe}</span>
  <form action="/blocking/remove" method="post" style="margin:0;display:inline;">
    <input type="hidden" name="domain" value="{safe}">
    <button class="bl-tag-rm" type="submit" title="Remove">&times;</button>
  </form>
</div>
"""

    if not domain_tags:
        domain_tags = '<div style="text-align:center;padding:30px;color:var(--muted);font-size:13px;">No blocked domains yet. Add one below.</div>'

    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">DNS Blocking</h1>
    <div class="page-sub">Block domains at the DNS level for all connected devices</div>
  </div>
</div>

<div class="svc-hero" style="border-color:rgba(239,68,68,0.15);">
  <div class="svc-hero-top">
    <div class="svc-hero-icon" style="background:rgba(239,68,68,0.12);color:var(--red);">
      <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
    </div>
    <div>
      <h2 class="svc-hero-title">DNS Block</h2>
      <span class="svc-status {"on" if domains else ""}" style="{"background:rgba(239,68,68,0.15);color:var(--red);" if domains else ""}">
        {len(domains)} {"DOMAIN" if len(domains)==1 else "DOMAINS"} BLOCKED
      </span>
    </div>
  </div>
  <p class="svc-hero-desc">Blocked domains are resolved to 0.0.0.0 via dnsmasq for all LAN clients. Changes apply to all devices connected to the gateway.</p>
</div>

<div class="svc-panels" style="grid-template-columns:1fr 340px;">
  <div class="svc-panel">
    <div class="svc-panel-head">
      <h3>Blocked Domains</h3>
      <span style="font-size:12px;color:var(--muted);">{len(domains)} total</span>
    </div>
    <div class="bl-tags-wrap">
      {domain_tags}
    </div>
  </div>

  <div class="svc-panel">
    <div class="svc-panel-head">
      <h3>Add Domain</h3>
    </div>
    <form action="/blocking/add" method="post" style="direction:ltr;">
      <input name="domain" placeholder="example.com" id="bl-input"
        style="width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--border);background:#020617;color:white;font-size:14px;">
      <button class="btn-direct" style="margin-top:12px;width:100%;padding:12px;">Block Domain</button>
    </form>

    <div style="margin-top:18px;padding-top:16px;border-top:1px solid var(--border);">
      <div style="font-size:12px;color:var(--muted);margin-bottom:10px;">Quick Block</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <button class="bl-quick" onclick="quickBlock('facebook.com')">facebook.com</button>
        <button class="bl-quick" onclick="quickBlock('tiktok.com')">tiktok.com</button>
        <button class="bl-quick" onclick="quickBlock('instagram.com')">instagram.com</button>
        <button class="bl-quick" onclick="quickBlock('twitter.com')">twitter.com</button>
        <button class="bl-quick" onclick="quickBlock('youtube.com')">youtube.com</button>
        <button class="bl-quick" onclick="quickBlock('snapchat.com')">snapchat.com</button>
        <button class="bl-quick" onclick="quickBlock('ads.google.com')">ads.google.com</button>
        <button class="bl-quick" onclick="quickBlock('doubleclick.net')">doubleclick.net</button>
      </div>
    </div>
  </div>
</div>

<script>
function quickBlock(domain) {{
  const form = new FormData();
  form.append('domain', domain);
  fetch('/blocking/add', {{ method: 'POST', body: new URLSearchParams(form) }}).then(() => location.reload());
}}
</script>
"""
    return layout("Blocking", "blocking", body)


@app.post("/blocking/add")
async def blocking_add(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = (await request.body()).decode()
    form = parse_qs(body)
    domain = form.get("domain", [""])[0].strip()

    if domain:
        run_cmd(["sudo", BLOCK_SCRIPT, "add", domain], timeout=20)

    return RedirectResponse("/blocking", status_code=303)


@app.post("/blocking/remove")
async def blocking_remove(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = (await request.body()).decode()
    form = parse_qs(body)
    domain = form.get("domain", [""])[0].strip()

    if domain:
        run_cmd(["sudo", BLOCK_SCRIPT, "remove", domain], timeout=20)

    return RedirectResponse("/blocking", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    if not logged_in(request):
        return redirect_login()

    proxy_status = get_proxy_status()
    wifi_qr_ssid = html.escape(CONFIG.get("WIFI_QR_SSID", ""))
    wifi_qr_security = CONFIG.get("WIFI_QR_SECURITY", "WPA")
    wifi_qr_password_set = "yes" if CONFIG.get("WIFI_QR_PASSWORD", "") else "no"
    body = f"""
<div class="topline">
  <div>
    <h1 class="page-title">Settings</h1>
    <div class="page-sub">Gateway configuration and maintenance</div>
  </div>
</div>

<div class="grid-2">
  <div class="card metric">
    <div class="metric-label">Dashboard URL</div>
    <div class="metric-value" style="font-size:24px;">http://192.168.50.1</div>
  </div>

  <div class="card metric">
    <div class="metric-label">Local Domains</div>
    <div class="metric-value" style="font-size:20px;">thorestic.test</div>
    <div class="metric-value" style="font-size:20px;">gateway.thorestic</div>
  </div>
</div>

<div class="card" style="margin-top:18px;">
  <h2 style="margin-top:0;direction:ltr;text-align:left;">Log Retention</h2>

  <form action="/settings/log-retention" method="post" style="direction:ltr;text-align:left;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
      <div>
        <label style="display:block;color:var(--muted);margin-bottom:8px;">Retention days</label>
        <input name="days" value="7" placeholder="7"
          style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;">
      </div>
      <div>
        <label style="display:block;color:var(--muted);margin-bottom:8px;">Max size</label>
        <input name="size" value="10M" placeholder="10M"
          style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;">
      </div>
    </div>
    <button class="btn-direct" style="margin-top:14px;">Apply Retention</button>
  </form>
</div>


<div class="card" style="margin-top:18px;">
  <h2 style="margin-top:0;direction:ltr;text-align:left;">Dashboard Password</h2>

  <form action="/settings/password" method="post" style="direction:ltr;text-align:left;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
      <div>
        <label style="display:block;color:var(--muted);margin-bottom:8px;">Current password</label>
        <input
          name="current_password"
          type="password"
          placeholder="Current password"
          style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;"
        >
      </div>

      <div>
        <label style="display:block;color:var(--muted);margin-bottom:8px;">New password</label>
        <input
          name="new_password"
          type="password"
          placeholder="New password"
          style="width:100%;padding:13px 14px;border-radius:13px;border:1px solid #334155;background:#020617;color:white;font-size:15px;"
        >
      </div>
    </div>

    <button class="btn-direct" style="margin-top:14px;">Change Password</button>
  </form>
</div>

<div class="card" style="margin-top:18px;">
  <h2 style="margin-top:0;direction:ltr;text-align:left;">Proxy Settings</h2>
  <p class="small-note" style="direction:ltr;text-align:left;">Configure proxy from the <a href="/proxy" style="color:var(--blue);">Proxy page</a>.</p>
</div>

<div class="grid-2" style="margin-top:18px;">
  <div class="card">
    <h2 style="margin-top:0;direction:ltr;text-align:left;">Backup / Restore</h2>
    <p style="font-size:13px;color:var(--muted);direction:ltr;text-align:left;margin-bottom:14px;">Export all gateway settings as a file, or restore from a previous backup.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <a href="/api/backup" class="btn-direct" style="padding:10px 18px;font-size:13px;text-decoration:none;display:inline-block;">Download Backup</a>
      <button class="btn-sm" style="padding:10px 18px;font-size:13px;" onclick="document.getElementById('restoreFile').click()">Restore from File</button>
      <input type="file" id="restoreFile" accept=".tar.gz,.tgz" style="display:none;" onchange="restoreBackup(this.files[0])">
    </div>
    <div id="restoreMsg" style="margin-top:10px;font-size:12px;"></div>
  </div>

  <div class="card">
    <h2 style="margin-top:0;direction:ltr;text-align:left;">Wi-Fi QR Code</h2>
    <p style="font-size:13px;color:var(--muted);direction:ltr;text-align:left;margin-bottom:14px;">Save the exact Wi-Fi network you want to share, then generate a clear QR image.</p>
    <form action="/settings/wifi-qr" method="post" style="direction:ltr;text-align:left;">
      <label style="display:block;color:var(--muted);margin-bottom:8px;font-size:12px;">SSID</label>
      <input name="ssid" value="{wifi_qr_ssid}" placeholder="TP-Link Wi-Fi name"
        style="width:100%;padding:11px 12px;border-radius:10px;border:1px solid #334155;background:#020617;color:white;font-size:14px;margin-bottom:10px;">

      <label style="display:block;color:var(--muted);margin-bottom:8px;font-size:12px;">Security</label>
      <select name="security"
        style="width:100%;padding:11px 12px;border-radius:10px;border:1px solid #334155;background:#020617;color:white;font-size:14px;margin-bottom:10px;">
        <option value="WPA" {"selected" if wifi_qr_security == "WPA" else ""}>WPA/WPA2/WPA3</option>
        <option value="WEP" {"selected" if wifi_qr_security == "WEP" else ""}>WEP</option>
        <option value="nopass" {"selected" if wifi_qr_security == "nopass" else ""}>No password</option>
      </select>

      <label style="display:block;color:var(--muted);margin-bottom:8px;font-size:12px;">Password</label>
      <input name="password" type="password" placeholder="{"Password saved - leave empty to keep" if wifi_qr_password_set == "yes" else "Wi-Fi password"}"
        style="width:100%;padding:11px 12px;border-radius:10px;border:1px solid #334155;background:#020617;color:white;font-size:14px;">

      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
        <button class="btn-sm" style="padding:10px 16px;font-size:13px;">Save QR Wi-Fi</button>
        <button type="button" class="btn-direct" style="padding:10px 16px;font-size:13px;" onclick="generateQR()">Generate QR</button>
      </div>
    </form>
    <div style="font-size:11px;color:var(--muted);direction:ltr;text-align:left;margin-top:10px;">Password saved: {wifi_qr_password_set}</div>
    <div id="qrResult" style="margin-top:14px;text-align:center;"></div>
  </div>
</div>

<div class="card" style="margin-top:18px;">
  <h2 style="margin-top:0;direction:ltr;text-align:left;">Auto-Update</h2>
  <p style="font-size:13px;color:var(--muted);direction:ltr;text-align:left;margin-bottom:14px;">Pull the latest version from GitHub. Make sure the repo is configured.</p>
  <button class="btn-direct" style="padding:10px 18px;font-size:13px;" onclick="runUpdate()">Check for Updates</button>
  <pre id="updateOutput" style="display:none;margin-top:12px;background:#020617;border:1px solid var(--border);border-radius:10px;padding:12px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--green);max-height:200px;overflow-y:auto;white-space:pre-wrap;"></pre>
</div>

<div style="margin-top:32px;padding-top:24px;border-top:1px solid var(--border);">
  <a href="/logout" style="display:inline-block;padding:14px 32px;border-radius:14px;background:rgba(239,68,68,0.12);color:var(--red);border:1px solid rgba(239,68,68,0.25);text-decoration:none;font-weight:600;font-size:15px;transition:all 200ms;"
     onmouseover="this.style.background='rgba(239,68,68,0.2)'"
     onmouseout="this.style.background='rgba(239,68,68,0.12)'">
    Logout
  </a>
</div>

<script>
async function restoreBackup(file) {{
  if (!file) return;
  const msg = document.getElementById('restoreMsg');
  msg.textContent = 'Uploading...';
  msg.style.color = 'var(--blue)';
  const fd = new FormData();
  fd.append('file', file);
  try {{
    const r = await fetch('/api/restore', {{ method: 'POST', body: fd }});
    const d = await r.json();
    msg.textContent = d.message || d.error || 'Done.';
    msg.style.color = d.error ? 'var(--red)' : 'var(--green)';
  }} catch(e) {{
    msg.textContent = 'Upload failed.';
    msg.style.color = 'var(--red)';
  }}
}}

async function generateQR() {{
  const el = document.getElementById('qrResult');
  el.innerHTML = '<span style="color:var(--muted);font-size:12px;">Generating...</span>';
  try {{
    const r = await fetch('/api/wifi-qr');
    const d = await r.json();
    if (d.qr_svg) {{
      el.innerHTML = '<div style="display:inline-block;background:white;padding:16px;border-radius:12px;max-width:100%;">' +
        d.qr_svg.replace('<svg ', '<svg style="width:min(320px,76vw);height:auto;display:block;" ') +
        '</div><div style="font-size:12px;color:var(--muted);margin-top:10px;direction:ltr;">SSID: ' + escText(d.ssid || '?') + '</div>';
    }} else {{
      el.innerHTML = '<span style="color:var(--muted);font-size:12px;">' + escText(d.error || 'No Wi-Fi QR settings saved') + '</span>';
    }}
  }} catch(e) {{
    el.innerHTML = '<span style="color:var(--red);font-size:12px;">Error generating QR</span>';
  }}
}}

function escText(text) {{
  const d = document.createElement('div');
  d.textContent = text || '';
  return d.innerHTML;
}}

async function runUpdate() {{
  const el = document.getElementById('updateOutput');
  el.style.display = 'block';
  el.textContent = 'Checking for updates...';
  try {{
    const r = await fetch('/api/update', {{ method: 'POST' }});
    const d = await r.json();
    el.textContent = d.output || d.error || 'Done.';
  }} catch(e) {{
    el.textContent = 'Error: ' + e.message;
  }}
}}
</script>

"""
    return layout("Settings", "settings", body)


@app.post("/settings/log-retention")
async def settings_log_retention(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = (await request.body()).decode()
    form = parse_qs(body)

    days = form.get("days", ["7"])[0].strip()
    size = form.get("size", ["10M"])[0].strip().upper()

    run_cmd(["sudo", LOG_RETENTION_SCRIPT, "set", days, size], timeout=20)

    return RedirectResponse("/settings", status_code=303)


@app.post("/mode/direct")
async def set_direct(request: Request):
    if not logged_in(request):
        return redirect_login()
    run_cmd(["sudo", MODE_SCRIPT, "direct"], timeout=20)
    return RedirectResponse("/", status_code=303)


@app.post("/mode/tor")
async def set_tor(request: Request):
    if not logged_in(request):
        return redirect_login()
    run_cmd(["sudo", MODE_SCRIPT, "tor"], timeout=30)
    return RedirectResponse("/", status_code=303)



@app.post("/mode/proxy")
async def set_proxy(request: Request):
    if not logged_in(request):
        return redirect_login()
    run_cmd(["sudo", MODE_SCRIPT, "proxy"], timeout=30)
    return RedirectResponse("/", status_code=303)


@app.post("/proxy/rotate")
async def rotate_proxy(request: Request):
    if not logged_in(request):
        return redirect_login()
    run_cmd(["sudo", ROTATE_PROXY_SCRIPT], timeout=30)
    return RedirectResponse("/", status_code=303)


@app.post("/settings/password")
async def settings_change_password(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = (await request.body()).decode()
    form = parse_qs(body)

    current_password = form.get("current_password", [""])[0]
    new_password = form.get("new_password", [""])[0]

    current_ok = secrets.compare_digest(password_hash(current_password), ADMIN_PASSWORD_SHA256)

    if current_ok and len(new_password) >= 8:
        save_dashboard_password(new_password)
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/wifi-qr")
async def settings_wifi_qr(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = (await request.body()).decode()
    form = parse_qs(body)

    ssid = form.get("ssid", [""])[0].strip()
    security = form.get("security", ["WPA"])[0].strip()
    password = form.get("password", [""])[0]

    if security not in ("WPA", "WEP", "nopass"):
        security = "WPA"

    updates = {
        "WIFI_QR_SSID": ssid,
        "WIFI_QR_SECURITY": security,
    }

    if security == "nopass":
        updates["WIFI_QR_PASSWORD"] = ""
    elif password:
        updates["WIFI_QR_PASSWORD"] = password

    save_dashboard_config(updates)

    return RedirectResponse("/settings", status_code=303)



@app.post("/settings/proxy")
async def settings_proxy(request: Request):
    if not logged_in(request):
        return redirect_login()

    body = (await request.body()).decode()
    form = parse_qs(body)

    proxy_type = form.get("proxy_type", ["socks5"])[0].strip()
    host = form.get("host", [""])[0].strip()
    port = form.get("port", [""])[0].strip()
    username = form.get("username", [""])[0].strip()
    password = form.get("password", [""])[0]

    if not password:
        password = "__KEEP__"

    run_cmd(["sudo", PROXY_SCRIPT, "set", proxy_type, host, port, username, password], timeout=25)

    return RedirectResponse("/settings", status_code=303)


@app.post("/api/mode/set")
async def api_mode_set(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = (await request.body()).decode()
    form = parse_qs(body)
    mode = form.get("mode", ["direct"])[0].strip().lower()

    if mode not in ("direct", "tor", "proxy"):
        return JSONResponse({"error": "invalid mode"}, status_code=400)

    timeout = 30 if mode in ("tor", "proxy") else 20
    rc, out = run_cmd(["sudo", MODE_SCRIPT, mode], timeout=timeout)

    new_status = get_status_raw()
    new_mode = get_current_mode(new_status)
    tor_active = new_mode == "tor"
    proxy_active = new_mode == "proxy"

    return {
        "ok": rc == 0,
        "mode": new_mode,
        "tor": tor_active,
        "proxy": proxy_active,
        "message": out,
    }


@app.get("/api/clients/{ip}")
async def api_client_detail(request: Request, ip: str):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    clients = get_clients()
    client = next((c for c in clients if c["ip"] == ip), None)
    if not client:
        return JSONResponse({"error": "not found"}, status_code=404)

    blocked = ip in get_blocked_clients()
    disconnected = ip in get_disconnected_clients()
    meta = client_meta(client)
    display = client_display_name(client)
    state = "BLOCKED" if blocked else ("DISCONNECTED" if disconnected else client["state"])
    logs = client_recent_logs(ip, 40)

    return {
        "ip": ip,
        "mac": client.get("mac", "-"),
        "hostname": client.get("hostname", "-"),
        "state": state,
        "blocked": blocked,
        "disconnected": disconnected,
        "display_name": display,
        "custom_name": meta.get("name", ""),
        "notes": meta.get("notes", ""),
        "logs": logs,
    }


@app.get("/api/tor/check")
async def api_tor_check(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    result = {"using_tor": False, "ip": "", "error": ""}

    rc_ip, ip_out = run_cmd(
        ["curl", "-s", "--max-time", "10", "--socks5-hostname", "127.0.0.1:9050", "https://api.ipify.org"],
        timeout=15,
    )
    if rc_ip == 0 and ip_out.strip():
        result["ip"] = ip_out.strip()

    rc_check, check_out = run_cmd(
        ["curl", "-s", "--max-time", "10", "--socks5-hostname", "127.0.0.1:9050", "https://check.torproject.org/api/ip"],
        timeout=15,
    )
    if rc_check == 0 and check_out.strip():
        try:
            import json as _json
            data = _json.loads(check_out.strip())
            result["using_tor"] = data.get("IsTor", False)
            if not result["ip"] and data.get("IP"):
                result["ip"] = data["IP"]
        except Exception:
            pass

    if not result["ip"]:
        rc_fb, fb_out = run_cmd(["curl", "-s", "--max-time", "8", "https://api.ipify.org"], timeout=12)
        if rc_fb == 0 and fb_out.strip():
            result["ip"] = fb_out.strip()
            result["error"] = "Could not reach Tor SOCKS — showing direct IP"

    return result


@app.get("/api/proxy/check")
async def api_proxy_check(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    result = {"ip": "", "error": ""}
    proxy_status = get_proxy_status()
    p_type = proxy_status.get("PROXY_TYPE", "socks5")
    p_host = proxy_status.get("PROXY_HOST", "")
    p_port = proxy_status.get("PROXY_PORT", "")
    p_user = proxy_status.get("PROXY_USERNAME", "")
    p_pass = proxy_status.get("PROXY_PASSWORD", "")

    # Try through local redsocks first (port 12345) — this is what clients actually use
    rc_local, out_local = run_cmd(
        ["curl", "-s", "--max-time", "10", "--socks5", "127.0.0.1:12345", "https://api.ipify.org"],
        timeout=15,
    )
    if rc_local == 0 and out_local.strip() and not out_local.strip().startswith("<"):
        result["ip"] = out_local.strip()
    else:
        # Try direct to remote proxy with auth
        if p_host and p_port:
            if p_type == "socks5":
                if p_user and p_pass:
                    proxy_arg = f"socks5h://{p_user}:{p_pass}@{p_host}:{p_port}"
                else:
                    proxy_arg = f"socks5h://{p_host}:{p_port}"
            else:
                if p_user and p_pass:
                    proxy_arg = f"http://{p_user}:{p_pass}@{p_host}:{p_port}"
                else:
                    proxy_arg = f"http://{p_host}:{p_port}"
            rc, out = run_cmd(
                ["curl", "-s", "--max-time", "10", "--proxy", proxy_arg, "https://api.ipify.org"],
                timeout=15,
            )
            if rc == 0 and out.strip() and not out.strip().startswith("<"):
                result["ip"] = out.strip()
            else:
                result["error"] = "Could not reach external IP via proxy — check proxy credentials and server"
        else:
            result["error"] = "No proxy configured"

    if not result["ip"]:
        rc_fb, fb_out = run_cmd(["curl", "-s", "--max-time", "8", "https://api.ipify.org"], timeout=12)
        if rc_fb == 0 and fb_out.strip():
            result["ip"] = fb_out.strip()
            if not result["error"]:
                result["error"] = "Showing direct IP (proxy not routing traffic)"

    return result


@app.get("/api/system")
async def api_system(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    cpu = "?"
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            cpu = parts[0] if parts else "?"
    except Exception:
        pass

    mem_total, mem_used, mem_pct = "?", "?", "?"
    try:
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                k, v = line.split(":", 1)
                info[k.strip()] = int(v.strip().split()[0])
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", 0)
            used = total - avail
            mem_total = f"{total // 1024}MB"
            mem_used = f"{used // 1024}MB"
            mem_pct = f"{round(used / total * 100)}%" if total else "?"
    except Exception:
        pass

    temp = "?"
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            t = int(f.read().strip())
            temp = f"{t / 1000:.1f}°C"
    except Exception:
        pass

    uptime = "?"
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
            days = secs // 86400
            hours = (secs % 86400) // 3600
            mins = (secs % 3600) // 60
            if days > 0:
                uptime = f"{days}d {hours}h {mins}m"
            elif hours > 0:
                uptime = f"{hours}h {mins}m"
            else:
                uptime = f"{mins}m"
    except Exception:
        pass

    return {"cpu_load": cpu, "mem_used": mem_used, "mem_total": mem_total, "mem_pct": mem_pct, "temp": temp, "uptime": uptime}


@app.get("/api/status")
async def api_status(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    status = get_status_raw()
    return {
        "mode": get_current_mode(status),
        "status": status,
    }


@app.get("/api/network/status")
async def api_network_status(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return get_wifi_status()


@app.get("/api/network/scan")
async def api_network_scan(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    rc, out = run_cmd(["sudo", NETWORK_SCRIPT, "scan"], timeout=20)
    return {
        "ok": rc == 0,
        "networks": parse_wifi_scan(out),
        "output": out,
    }


@app.post("/api/network/connect")
async def api_network_connect(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    body = (await request.body()).decode()
    form = parse_qs(body)

    ssid = form.get("ssid", [""])[0].strip()
    password = form.get("password", [""])[0]

    if not ssid:
        return JSONResponse({"error": "SSID is required"}, status_code=400)

    rc, out = run_cmd(["sudo", NETWORK_SCRIPT, "connect", ssid, password], timeout=45)
    wifi = get_wifi_status()
    return {
        "ok": rc == 0,
        "output": out or ("Connected to " + ssid if rc == 0 else "Connection failed"),
        "status": wifi,
    }


@app.post("/api/network/disconnect")
async def api_network_disconnect(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    rc, out = run_cmd(["sudo", NETWORK_SCRIPT, "disconnect"], timeout=20)
    wifi = get_wifi_status()
    return {
        "ok": rc == 0,
        "output": out or "wlan0 disconnected",
        "status": wifi,
    }


@app.get("/api/clients")
async def api_clients(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return {"clients": get_clients()}


@app.get("/api/logs")
async def api_logs(request: Request, kind: str = "combined"):
    if not logged_in(request):
        return PlainTextResponse("Unauthorized", status_code=401)

    return PlainTextResponse(tail_file(log_path(kind), 180))


@app.get("/stream/logs")
async def stream_logs(request: Request, kind: str = "combined"):
    if not logged_in(request):
        return PlainTextResponse("Unauthorized", status_code=401)

    path = log_path(kind)

    async def event_generator():
        position = 0
        if path.exists():
            position = path.stat().st_size

        while True:
            if await request.is_disconnected():
                break

            if path.exists():
                with path.open("r", encoding="utf-8", errors="ignore") as f:
                    f.seek(position)
                    lines = f.readlines()
                    position = f.tell()

                for line in lines:
                    clean = line.rstrip().replace("\n", " ")
                    if clean:
                        yield f"data: {clean}\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/backup")
async def api_backup(request: Request):
    if not logged_in(request):
        return RedirectResponse("/login", status_code=303)

    import tarfile
    import io
    import time

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        configs_dir = APP_DIR / "configs"
        if configs_dir.exists():
            for f in configs_dir.iterdir():
                if f.is_file() and f.name != "dashboard.env":
                    tar.add(str(f), arcname=f"configs/{f.name}")
        dash_env = configs_dir / "dashboard.env"
        if dash_env.exists():
            tar.add(str(dash_env), arcname="configs/dashboard.env")

    buf.seek(0)
    ts = time.strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename=thorestic-backup-{ts}.tar.gz"},
    )


@app.post("/api/restore")
async def api_restore(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    import tarfile
    import io

    form = await request.form()
    upload = form.get("file")
    if not upload:
        return JSONResponse({"error": "No file uploaded"}, status_code=400)

    content = await upload.read()
    try:
        buf = io.BytesIO(content)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            safe_members = [m for m in tar.getmembers() if not m.name.startswith("/") and ".." not in m.name]
            for member in safe_members:
                if member.isfile() and member.name.startswith("configs/"):
                    tar.extract(member, path=str(APP_DIR))
        return {"message": f"Restored {len(safe_members)} files. Restart the service to apply."}
    except Exception as e:
        return JSONResponse({"error": f"Invalid backup file: {str(e)}"}, status_code=400)


@app.get("/api/wifi-qr")
async def api_wifi_qr(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    ssid = CONFIG.get("WIFI_QR_SSID", "").strip()
    auth = CONFIG.get("WIFI_QR_SECURITY", "WPA").strip()
    password = CONFIG.get("WIFI_QR_PASSWORD", "")

    if not ssid:
        return {
            "qr_svg": "",
            "ssid": "",
            "error": "Save the TP-Link / target Wi-Fi SSID first.",
        }

    if auth not in ("WPA", "WEP", "nopass"):
        auth = "WPA"

    if auth != "nopass" and not password:
        return {
            "qr_svg": "",
            "ssid": ssid,
            "error": "Save the Wi-Fi password first, then generate the QR code.",
        }

    wifi_str = (
        f"WIFI:T:{wifi_qr_escape(auth)};"
        f"S:{wifi_qr_escape(ssid)};"
        f"P:{wifi_qr_escape(password)};"
        ";"
    )

    try:
        rc, qr_out = run_cmd(["qrencode", "-t", "SVG", "-m", "3", wifi_str], timeout=5)
        if rc == 0 and qr_out:
            return {"qr_svg": qr_out, "ssid": ssid, "security": auth}
    except Exception:
        pass

    return {
        "qr_svg": "",
        "ssid": ssid,
        "error": "Could not generate QR SVG. Make sure qrencode is installed.",
    }


@app.post("/api/update")
async def api_update(request: Request):
    if not logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    git_dir = APP_DIR
    if not (git_dir / ".git").exists():
        return {"output": "No git repository found at " + str(git_dir) + "\nInitialize with: cd " + str(git_dir) + " && git init && git remote add origin <your-repo-url>"}

    rc, out = run_cmd(["git", "-C", str(git_dir), "pull", "--rebase"], timeout=30)
    output = out.strip() if out else "No output"
    if rc == 0:
        output += "\n\nUpdate complete. Restart the service to apply:\nsudo systemctl restart thorestic-fastapi"
    else:
        output += "\n\nUpdate failed. Check git remote configuration."

    return {"output": output}


@app.get("/health")
async def health():
    return {"status": "ok"}
