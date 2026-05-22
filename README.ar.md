# Thorestic Privacy Gateway

هذا أول مشروع شبكات كامل أعمله على Raspberry Pi.

الفكرة بدأت من إني بدي أخلي Raspberry Pi 4 يشتغل كأنه privacy gateway صغير، وأقدر أتحكم فيه من موقع بدل ما أضل أكتب أوامر من التيرمنال كل مرة.

[English README](README.md)

## شو هو المشروع؟

المشروع عبارة عن Raspberry Pi gateway فيه:

- Dashboard مبني بـ FastAPI.
- سكربتات Bash بتنفذ أوامر الشبكة على لينكس.
- صفحة Network عشان أفحص الشبكات وأشبك الراسبري على Wi-Fi من الموقع.
- صفحات Tor و Proxy و VPN و Clients و Logs و Settings.
- QR Code لشبكة Wi-Fi يتم تحديدها من الإعدادات.
- Logs مباشرة من `tcpdump`.
- تحكم بالأجهزة المتصلة مثل block و disconnect و reconnect.
- ملفات config examples آمنة للنشر.

في setup المشروع، `eth0` هو جهة الشبكة الداخلية أو الراوتر، و `wlan0` ممكن يكون جهة الإنترنت.

## صور من الموقع

Dashboard:

![صورة الداشبورد](docs/images/dashboard-preview.png)

Network page:

![صورة صفحة الشبكة](docs/images/network-page.png)

## ملفات التوثيق

| عربي | English | شو فيه |
| --- | --- | --- |
| [WHAT_WE_BUILT.ar.md](docs/WHAT_WE_BUILT.ar.md) | [WHAT_WE_BUILT.md](docs/WHAT_WE_BUILT.md) | شو عملنا وعدلنا بالمشروع. |
| [ARCHITECTURE.ar.md](docs/ARCHITECTURE.ar.md) | [ARCHITECTURE.md](docs/ARCHITECTURE.md) | كيف الموقع والـ Python والسكريبتات والخدمات واللوقات مربوطين ببعض. |
| [SETUP.ar.md](docs/SETUP.ar.md) | [SETUP.md](docs/SETUP.md) | كيف تجهز الراسبري وتشغل المشروع. |
| [COMMANDS.ar.md](docs/COMMANDS.ar.md) | [COMMANDS.md](docs/COMMANDS.md) | أهم الأوامر اللي استخدمناها. |
| [TROUBLESHOOTING.ar.md](docs/TROUBLESHOOTING.ar.md) | [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | المشاكل اللي ظهرت وكيف انحلت. |
| [AI_ASSISTANCE.ar.md](docs/AI_ASSISTANCE.ar.md) | [AI_ASSISTANCE.md](docs/AI_ASSISTANCE.md) | كيف الذكاء الاصطناعي ساعد بالمشروع. |
| [SECURITY.ar.md](docs/SECURITY.ar.md) | [SECURITY.md](docs/SECURITY.md) | شو الأشياء اللي ما لازم تنرفع على GitHub. |

## تقسيم المشروع

```text
web/
  main.py                FastAPI routes والـ backend logic
  ui.py                  layout و login rendering
  templates/base.html    شكل HTML الأساسي
  static/styles.css      CSS تبع الموقع

scripts/
  *.sh                   سكربتات الشبكة والخدمات
  net-logger.py          سكربت اللوقات المبني على tcpdump

configs/
  *.example              أمثلة فقط بدون أسرار

systemd/
  *.service.example      أمثلة systemd services
```

كان أغلب الموقع بالبداية داخل `main.py`. بعدين قسمته تقسيم خفيف: خليت Python للـ backend، وخليت ملفات الموقع لحالها، بدون ما أكبر المشروع زيادة.

## تشغيل سريع للتطوير

هذا يشغل الموقع فقط. أوامر الشبكة الحقيقية تحتاج Raspberry Pi وإعدادات وصلاحيات مناسبة.

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

افتح:

```text
http://127.0.0.1:8000
```

## ملاحظة خصوصية

هذا الريبو public، لذلك ما رفعت عليه أي باسوردات حقيقية، Wi-Fi credentials، proxy credentials، logs، certificates، SSH keys، أو backups من الجهاز.

ملفات `configs/` هي أمثلة فقط.

## استخدام AI

استخدمت الذكاء الاصطناعي كمساعد أثناء بناء المشروع.

ساعدني أفهم أجزاء من Linux networking، أكتب وأعدل سكربتات Bash، أربط FastAPI بالسكريبتات، debug الأخطاء.

لكن التجربة والتعديل النهائي كانوا على Raspberry Pi حقيقي حسب المشاكل اللي ظهرت فعليًا.
