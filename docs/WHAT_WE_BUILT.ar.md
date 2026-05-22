# شو عملنا بالمشروع

هذا الملف ملخص مباشر للأشياء اللي انعملت بالمشروع.

## الفكرة الأساسية

المشروع بحول Raspberry Pi 4 إلى gateway صغير للشبكة، وفيه dashboard من المتصفح.

بدل ما كل شيء يكون من التيرمنال، الموقع يرسل الطلب إلى FastAPI، و FastAPI يشغل السكربت المناسب على الراسبري.

## تعديلات الداشبورد

الأشياء اللي تغيرت بالداشبورد:

- شلنا قسم Tools من الواجهة ومن routes.
- أضفنا صفحة Network عشان تفحص شبكات Wi-Fi وتشبك الراسبري على شبكة محددة.
- أضفنا زر Disconnect Wi-Fi عشان نقدر نجرب الوصول للـ gateway بدون إنترنت upstream.
- خلينا Tor و VPN و Proxy و Blocking في الداشبورد كأيقونات حالة فقط.
- خلينا التحكم الحقيقي داخل الصفحات الخاصة من الـ sidebar.
- أضفنا إعدادات Wi-Fi QR عشان الـ QR يستخدم شبكة نحددها، مش الشبكة اللي الراسبري شابك عليها.
- حسنّا إخراج QR Code عشان التلفون يقدر يعمل scan بسهولة.

## ترتيب الكود

في البداية كان أغلب تطبيق الويب داخل `main.py`.

قسمناه تقسيم خفيف:

```text
web/main.py
web/ui.py
web/templates/base.html
web/static/styles.css
```

الفكرة مش إننا نكبر المشروع زيادة. بس صار أسهل للقراءة:

- backend في `main.py`
- layout مشترك في `ui.py`
- HTML الأساسي في `templates/base.html`
- CSS في `static/styles.css`

## شغل الشبكة

سكربت Wi-Fi صار يقدر:

- يعمل scan للشبكات باستخدام `nmcli`
- يشبك على شبكة عليها password
- ينشئ NetworkManager profile واضح
- يضيف `wifi-sec.key-mgmt wpa-psk`
- يفصل `wlan0`

هذا حل الخطأ:

```text
802-11-wireless-security.key-mgmt: property is missing
```

## تجهيز GitHub Public

نظفنا الريبو عشان ما يحتوي:

- ملفات `.env` حقيقية
- passwords
- أسماء أو كلمات مرور Wi-Fi حقيقية
- SSH keys
- certificates
- logs
- proxy credentials
- backups من الجهاز

بدلها، الريبو يحتوي ملفات example آمنة.

## الصور

الريبو يستخدم screenshots حقيقية من واجهة الموقع:

- `docs/images/dashboard-preview.png`
- `docs/images/network-page.png`
