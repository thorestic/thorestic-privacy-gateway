# المشاكل والحلول

هذه مشاكل حقيقية ظهرت أثناء الشغل على المشروع.

## خطأ الاتصال بالـ Wi-Fi

الخطأ:

```text
802-11-wireless-security.key-mgmt: property is missing
```

السبب:

NetworkManager كان يحتاج إعداد واضح لنوع حماية الشبكة داخل connection profile.

الحل:

السكريبت صار ينشئ NetworkManager profile ويضيف:

```bash
wifi-sec.key-mgmt wpa-psk
```

لما تكون الشبكة عليها password.

## Scan ما يطلع شبكات

أوامر تفحصها:

```bash
nmcli radio wifi
nmcli dev status
nmcli -t -f ssid,signal,security dev wifi list --rescan yes
```

أسباب ممكنة:

- Wi-Fi radio مطفي.
- `wlan0` معمول له block.
- NetworkManager لا يتحكم بالواجهة.
- مستخدم الداشبورد ما عنده صلاحية يشغل scan script.
- الراسبري بعيد عن الراوتر.

## ما عندي شاشة أو micro-HDMI

المشكلة:

لو الراسبري خسر اتصال Wi-Fi، ممكن يصير صعب تصلحه بدون شاشة.

الحل في المشروع:

- خلي جهة Ethernet/gateway متاحة.
- أضف صفحة Network في الداشبورد.
- أضف زر Disconnect Wi-Fi للتجربة.
- تأكد إنك تقدر تدخل على الراسبري من الشبكة الداخلية.

## QR Code ما ينقرأ

المشكلة:

أول QR Code كان صغير أو مضغوط، والتلفون ما كان يقرأه بسهولة.

الحل:

- توليد QR بصيغة SVG.
- عرضه بحجم أوضح في الواجهة.
- استخدام SSID/password من Settings، مش الشبكة اللي الراسبري متصل فيها.

## الداشبورد فيه أزرار كثيرة

المشكلة:

صف الخدمات في الداشبورد كان فيه controls كثيرة.

الحل:

صار الداشبورد يعرض status icons فقط. التحكم الحقيقي موجود في صفحات الـ sidebar.

## اللوقات ما تظهر

افحص خدمة logger:

```bash
systemctl status thorestic-netlogger
```

افحص الملفات:

```bash
ls -lah /var/log/thorestic-gateway/
```

راقب مباشر:

```bash
sudo tail -f /var/log/thorestic-gateway/combined.log
```

أسباب ممكنة:

- `tcpdump` غير مثبت.
- الخدمة لا تعمل كـ root.
- اسم interface غلط.
- مجلد اللوقات غير موجود أو صلاحياته غلط.

## FastAPI لا يعمل

افحص:

```bash
systemctl status thorestic-fastapi
journalctl -u thorestic-fastapi -n 100 --no-pager
```

افحص Python syntax:

```bash
python3 -m py_compile web/main.py web/ui.py
```

شغله يدوي:

```bash
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

## GitHub رفض الـ push

الخطأ:

```text
non-fast-forward
fatal: refusing to merge unrelated histories
```

اللي صار:

الريبو المحلي و GitHub كان عندهم first commits مختلفين.

الحل اللي استخدمناه:

```bash
git push --force-with-lease origin main
```

كان مناسب هنا لأن GitHub كان عليه نسخة أقدم من نفس المشروع.

## حماية الريبو public

قبل أي push:

```bash
rg -n -e "PASSWORD" -e "SECRET" -e "PRIVATE KEY" -e "BEGIN .*KEY" .
```

مش كل نتيجة معناها مشكلة، لأن الكود فيه أسماء متغيرات مثل `PROXY_PASSWORD`. المهم ما يكون فيه قيم حقيقية.

