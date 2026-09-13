# Cloudflare Tunnel

ReceiptVault is designed to sit behind an existing tunnel or an optional in-LXC `cloudflared` connector.

## Existing tunnel

Point the public hostname to the LXC origin:

```text
http://<lxc-lan-ip>:8080
```

Caddy listens on 8080 and proxies to FastAPI on 127.0.0.1:8473. Request body limit in Caddy is 60 MB so a 16 MiB app chunk plus overhead still fits.

Cloudflare Free/Pro proxied uploads are **100 MB per request** (platform limits updated 2026-09-05). This application never relies on a single oversized POST.

## Managed connector

The installer can install `cloudflared` and accept a tunnel token in a password box. The token is written to `/etc/cloudflared/token` (mode 0600) and is not appended to the install log.

## Access

Cloudflare Access in front of the hostname is recommended as a second factor for the operator. It does **not** replace ReceiptVault login.
