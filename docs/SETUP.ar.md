# تشغيل وتجهيز المشروع

هذا مش installer جاهز بضغطة زر. الملف هذا يشرح setup المشروع والأشياء اللي لازم تكون موجودة على Raspberry Pi.

## 1. تحميل Raspberry Pi OS

استخدم الأدوات الرسمية:

- Raspberry Pi Imager: <https://www.raspberrypi.com/software/>
- Raspberry Pi OS images: <https://www.raspberrypi.com/software/operating-systems/>

لهذا النوع من المشاريع، Raspberry Pi OS Lite 64-bit غالبا بكفي، لأنه الداشبورد web وما يحتاج desktop UI.

من Raspberry Pi Imager، مفيد تضبط:

- hostname
- username/password
- تفعيل SSH
- Wi-Fi لو بدك أول boot يكون عنده اتصال

لا تنشر كلمة مرور Wi-Fi أو SSH الحقيقية.

## 2. نسخ المشروع على الراسبري

المسار المتوقع:

```bash
/opt/thorestic-gateway
```

مثال:

```bash
sudo mkdir -p /opt/thorestic-gateway
sudo chown -R $USER:$USER /opt/thorestic-gateway
git clone https://github.com/thorestic/thorestic-privacy-gateway.git /opt/thorestic-gateway
```

## 3. تثبيت البرامج المطلوبة

الحزم ممكن تختلف حسب نسخة Raspberry Pi OS، لكن المشروع يستخدم أدوات مثل:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx network-manager tcpdump qrencode tor redsocks
```

بعض الأنظمة يكون فيها NetworkManager جاهز. انتبه قبل ما تغير network stack وأنت داخل على الجهاز عن بعد.

## 4. Python Environment

```bash
cd /opt/thorestic-gateway
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

تشغيل للتطوير:

```bash
./venv/bin/uvicorn web.main:app --host 127.0.0.1 --port 8000
```

## 5. ملفات الإعدادات

استخدم ملفات المثال:

```bash
cp configs/dashboard.env.example configs/dashboard.env
cp configs/proxy.env.example configs/proxy.env
```

بعدها عدل الملفات الحقيقية على الراسبري.

لا تعمل commit للملفات الحقيقية.

## 6. systemd services

أمثلة الخدمات موجودة في:

```text
systemd/
```

انسخها وفعلها بعد ما تراجع المسارات والـ users:

```bash
sudo cp systemd/thorestic-fastapi.service.example /etc/systemd/system/thorestic-fastapi.service
sudo cp systemd/thorestic-netlogger.service.example /etc/systemd/system/thorestic-netlogger.service
sudo systemctl daemon-reload
sudo systemctl enable --now thorestic-fastapi
sudo systemctl enable --now thorestic-netlogger
```

افحص:

```bash
systemctl status thorestic-fastapi
systemctl status thorestic-netlogger
```

## 7. الصلاحيات

مستخدم الداشبورد يحتاج صلاحية يشغل سكربتات محددة بـ `sudo`.

لا تعطي sudo مفتوح بدون كلمة مرور.

استخدم sudoers rule صغير يسمح فقط بالسكريبتات والأوامر اللي يحتاجها الداشبورد.

دائما افحص sudoers:

```bash
sudo visudo -cf /etc/sudoers.d/thorestic-network
```

## 8. فتح الداشبورد

لو nginx مضبوط كـ reverse proxy، افتح IP الراسبري من المتصفح.

لو مشغل uvicorn محلي:

```text
http://127.0.0.1:8000
```

على شبكة الراسبري نفسها، العنوان يعتمد على إعدادك. في setup تبعي كنت أستخدم الراسبري كـ gateway IP من جهة الشبكة الداخلية.

