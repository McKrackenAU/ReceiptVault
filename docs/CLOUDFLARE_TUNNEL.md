# Cloudflare Tunnel

ReceiptVault is designed to sit behind an existing tunnel or an optional in-LXC `cloudflared` connector.

## Existing tunnel

Point the public hostname to the LXC origin:

```text
http://<lxc-lan-ip>:8080
```

Point the tunnel origin at `http://<lxc-ip>/` (ReceiptVault listens on port 80). App request bodies stay at 16 MiB chunks.

Cloudflare Free/Pro proxied uploads are **100 MB per request** (platform limits updated 2026-09-05). This application never relies on a single oversized POST.

## Managed connector

The installer can install `cloudflared` and accept a tunnel token in a password box. The token is written to `/etc/cloudflared/token` (mode 0600) and is not appended to the install log.

## Access

Cloudflare Access in front of the hostname is recommended as a second factor for the operator. It does **not** replace ReceiptVault login.
