# Setup

This is not a one-click installer yet. These notes explain the setup used for the project and what needs to exist on the Raspberry Pi.

## 1. Download Raspberry Pi OS

Use the official Raspberry Pi tools:

- Raspberry Pi Imager: <https://www.raspberrypi.com/software/>
- Raspberry Pi OS images: <https://www.raspberrypi.com/software/operating-systems/>

For this kind of gateway project, Raspberry Pi OS Lite 64-bit is usually enough because the dashboard is web-based and does not need a desktop UI.

In Raspberry Pi Imager, it is useful to set:

- hostname
- username/password
- SSH enabled
- Wi-Fi if you need first boot network access

Do not publish your real first-boot Wi-Fi password or SSH password.

## 2. Copy Project To The Pi

Expected path:

```bash
/opt/thorestic-gateway
```

Example:

```bash
sudo mkdir -p /opt/thorestic-gateway
sudo chown -R $USER:$USER /opt/thorestic-gateway
git clone https://github.com/thorestic/thorestic-privacy-gateway.git /opt/thorestic-gateway
```

## 3. Install Packages

Packages depend on the exact Raspberry Pi OS version, but the project uses tools like:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx network-manager tcpdump qrencode tor redsocks
```

Some systems may already have NetworkManager. Check before changing the network stack on a remote device.

## 4. Python Environment

```bash
cd /opt/thorestic-gateway
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Run for development:

```bash
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

## 5. Config Files

Use the example files:

```bash
cp configs/dashboard.env.example configs/dashboard.env
cp configs/proxy.env.example configs/proxy.env
```

Then edit the real files on the Pi.

Do not commit the real files.

## 6. systemd Services

Example service files are in:

```text
systemd/
```

Copy and enable them only after checking paths and users:

```bash
sudo cp systemd/thorestic-fastapi.service.example /etc/systemd/system/thorestic-fastapi.service
sudo cp systemd/thorestic-netlogger.service.example /etc/systemd/system/thorestic-netlogger.service
sudo systemctl daemon-reload
sudo systemctl enable --now thorestic-fastapi
sudo systemctl enable --now thorestic-netlogger
```

Check:

```bash
systemctl status thorestic-fastapi
systemctl status thorestic-netlogger
```

## 7. Permissions

The dashboard user needs permission to run specific scripts with `sudo`.

Do not give broad passwordless sudo.

Use a small sudoers rule that allows only the scripts/actions needed by the dashboard.

Always validate sudoers files with:

```bash
sudo visudo -cf /etc/sudoers.d/thorestic-network
```

## 8. Open Dashboard

If nginx is configured as a reverse proxy, open the gateway IP in the browser.

For local uvicorn only:

```text
http://127.0.0.1:8000
```

On the Pi gateway network, the address depends on your setup. In my setup I used the Pi as the gateway IP on the local side.
