# الأوامر

هذه أهم الأوامر اللي استخدمناها أثناء بناء وتجربة المشروع. الأوامر فيها placeholders، مش بيانات خاصة.

## الدخول على الراسبري SSH

```bash
ssh USERNAME@PI_IP
```

باستخدام key:

```bash
ssh -i ./your_key USERNAME@PI_IP
```

## فحص الخدمات

```bash
systemctl status thorestic-fastapi
systemctl status thorestic-netlogger
systemctl is-active thorestic-fastapi
```

إعادة تشغيل:

```bash
sudo systemctl restart thorestic-fastapi
sudo systemctl restart thorestic-netlogger
```

لوقات الخدمات:

```bash
journalctl -u thorestic-fastapi -n 100 --no-pager
journalctl -u thorestic-netlogger -n 100 --no-pager
```

## فحص Python

```bash
python3 -m py_compile web/main.py web/ui.py
```

تشغيل محلي:

```bash
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

## NetworkManager

عرض الأجهزة:

```bash
nmcli dev status
```

فحص شبكات Wi-Fi:

```bash
nmcli -t -f ssid,signal,security dev wifi list --rescan yes
```

الاتصال بشبكة:

```bash
sudo nmcli dev wifi connect "SSID_NAME" password "WIFI_PASSWORD"
```

فصل Wi-Fi:

```bash
sudo nmcli dev disconnect wlan0
```

## سكربت الشبكة في المشروع

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

فحص syntax:

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

## اللوقات

```bash
sudo tail -f /var/log/thorestic-gateway/combined.log
sudo tail -f /var/log/thorestic-gateway/dns.log
sudo tail -f /var/log/thorestic-gateway/connections.log
```
