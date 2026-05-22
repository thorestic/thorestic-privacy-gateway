# حماية الريبو public

قبل ما ترفع الريبو على GitHub، تأكد إنه ما يحتوي:

- ملفات `.env` حقيقية
- كلمات مرور Wi-Fi
- usernames أو passwords للـ proxy
- password hashes حقيقية من الجهاز
- session secrets
- SSH keys
- TLS certificates أو private keys
- runtime logs
- backup archives
- أسماء أجهزة شخصية أو MAC addresses

فحص سريع:

```bash
rg -n "PASSWORD|SECRET|TOKEN|PRIVATE KEY|BEGIN .*KEY|ssid|psk|proxy" .
```

ممكن تظهر نتائج طبيعية لأن الكود فيه أسماء متغيرات و placeholders. المهم ما تظهر قيم حقيقية.

