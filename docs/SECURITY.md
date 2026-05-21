# Public Repository Safety

Before pushing this repository publicly, check that it does not contain:

- Real `.env` files.
- Wi-Fi passwords.
- Proxy usernames or passwords.
- Admin password hashes from a real device.
- Session secrets.
- SSH keys.
- TLS certificates or private keys.
- Runtime logs.
- Device backup archives.
- Personal client names or MAC addresses.

Suggested final check:

```bash
rg -n "PASSWORD|SECRET|TOKEN|PRIVATE KEY|BEGIN .*KEY|ssid|psk|proxy" .
```

Some matches are expected because the source code contains variable names and example placeholders. Real values should not appear.

