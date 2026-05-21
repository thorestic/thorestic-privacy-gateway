from pathlib import Path
import html


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
BASE_TEMPLATE = (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


def nav_html(active: str) -> str:
    items = [
        ("dashboard", "/", "Dashboard"),
        ("network", "/network", "Network"),
        ("tor", "/tor", "Tor"),
        ("proxy", "/proxy", "Proxy"),
        ("vpn", "/vpn", "VPN"),
        ("clients", "/clients", "Clients"),
        ("logs", "/logs", "Logs"),
        ("blocking", "/blocking", "Blocking"),
        ("settings", "/settings", "Settings"),
    ]

    links = ""
    for key, href, label in items:
        cls = "active" if active == key else ""
        links += f'<a class="{cls}" href="{href}">{html.escape(label)}</a>'

    return links


def layout(title: str, active: str, body: str) -> str:
    shell = f"""
<div class="mobile-topbar">
  <button class="hamburger" onclick="document.querySelector('aside').classList.add('open');document.getElementById('sideOverlay').classList.add('open');">&#9776;</button>
  <div class="brand-title" style="font-size:16px;">Thorestic Gateway</div>
</div>
<div class="sidebar-overlay" id="sideOverlay" onclick="document.querySelector('aside').classList.remove('open');this.classList.remove('open');"></div>
<div class="layout">
  <aside>
    <div class="brand">
      <div class="brand-logo">TG</div>
      <div class="brand-copy">
        <div class="brand-title">Thorestic Gateway</div>
        <div class="brand-sub">Private Network Router</div>
      </div>
    </div>
    <nav>
      {nav_html(active)}
    </nav>

    <div class="sidebar-footer">
      <div>Built by Thorestic</div>
      <div>&copy; 2026 Privacy Gateway</div>
    </div>
  </aside>
  <section class="content">
    <div class="app-topbar">
      <div class="topbar-left">
        <div class="topbar-title">Network Control Center</div>
        <div class="topbar-sub">Direct &middot; Tor &middot; Proxy Gateway</div>
      </div>
      <div class="topbar-badge">Gateway Online</div>
    </div>
    {body}
  </section>
</div>
"""
    return BASE_TEMPLATE.replace("%%TITLE%%", html.escape(title)).replace("%%BODY%%", shell)


def login_page(error: str = "") -> str:
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""
<div class="login-page">
  <form class="login-card" method="post" action="/login">
    <h1>Thorestic Gateway</h1>
    <div class="sub">Admin Login</div>
    {error_html}
    <label>Username</label>
    <input name="username" autocomplete="username" autofocus>
    <label>Password</label>
    <input name="password" type="password" autocomplete="current-password">
    <button type="submit">Login</button>
  </form>
</div>
"""
    return BASE_TEMPLATE.replace("%%TITLE%%", "Login").replace("%%BODY%%", body)

