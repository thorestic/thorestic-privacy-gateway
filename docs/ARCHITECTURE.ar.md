# كيف المشروع مبني

المشروع فيه ثلاث طبقات رئيسية:

```text
Browser dashboard
  -> FastAPI backend
  -> Bash/Python scripts
  -> Linux services and network tools
```

## المتصفح

المتصفح يفتح الداشبورد ويرسل الأوامر إلى FastAPI.

أمثلة:

- تضغط Scan في صفحة Network
- تضغط Connect Raspberry Pi
- تغير mode من صفحة Tor أو Proxy
- تشوف logs
- تعمل block أو reconnect لجهاز

المتصفح ما يشغل أوامر Linux مباشرة.

## FastAPI

FastAPI هو backend المكتوب بـ Python داخل `web/main.py`.

مسؤول عن:

- عرض الصفحات
- login/session
- API routes
- قراءة config files
- قراءة log files
- تشغيل السكربتات باستخدام `subprocess.run`
- إرجاع JSON للواجهة
- بث logs مباشرة باستخدام server-sent events

النمط المستخدم مثل:

```python
rc, out = run_cmd(["sudo", NETWORK_SCRIPT, "connect", ssid, password], timeout=45)
```

يعني:

```text
زر في الموقع -> API route -> run_cmd() -> script -> Linux tool
```

## السكربتات

السكربتات موجودة داخل `scripts/`.

أغلبها Bash لأن الشغل نفسه شغل Linux/network.

أمثلة:

- `auto-hotspot.sh` يستخدم `nmcli`
- `mode-manager.sh` يغير modes
- `force-dns.sh` يدير قواعد DNS
- `block-manager.sh` يعمل block
- `proxy-manager.sh` يدير إعدادات proxy
- `net-logger.py` يشغل `tcpdump` ويكتب logs

## الخدمات

على Raspberry Pi، المشروع عادة يشتغل عن طريق systemd services.

أمثلة الخدمات موجودة في:

```text
systemd/
```

الخدمات الأساسية:

- خدمة FastAPI dashboard
- خدمة network logger
- سكربتات يتم تشغيلها بصلاحيات محددة عن طريق sudo

## اللوقات

الـ logger يراقب metadata من حركة الشبكة ويكتب ملفات داخل:

```text
/var/log/thorestic-gateway/
```

أهم الملفات:

```text
dns.log
connections.log
combined.log
```

الداشبورد يقرأ اللوقات القديمة من:

```text
/api/logs
```

واللوقات المباشرة من:

```text
/stream/logs
```

## شكل الشبكة

الفكرة العامة:

```text
Client/router side -> Raspberry Pi eth0 -> Raspberry Pi gateway logic -> wlan0/upstream internet
```

في setup الجهاز:

- `eth0` جهة الشبكة الداخلية.
- `wlan0` جهة Wi-Fi للإنترنت.
- الداشبورد ينفتح من جهة الشبكة الداخلية.

## ليش التقسيم بسيط؟

المشروع لسه learning project. ما قسمته إلى ملفات كثيرة عشان ما يصير أصعب للقراءة.

التقسيم الحالي كافي:

- backend logic: `web/main.py`
- layout: `web/ui.py`
- base HTML: `web/templates/base.html`
- CSS: `web/static/styles.css`

