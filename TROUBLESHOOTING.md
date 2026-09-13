# Troubleshooting

## Installer locale warnings (perl / apt-listchanges)

A red bar at about 78% is the progress gauge starting the in-container bootstrap, not a crash. Lines like `Cannot set LC_ALL to default locale` on a fresh Debian LXC are warnings. Current installer sets `C.UTF-8` before apt. If an older run stopped, check:

```bash
tail -n 80 /var/tmp/receiptvault-install.log
pct exec <CTID> -- tail -n 80 /var/log/receiptvault-bootstrap.log
```

Then re-run the helper and choose **Repair** or **Update**.

## Static IP not reachable

Your Proxmox host (for example `https://192.168.14.1:8006`) and the container must be on the **same subnet**. `192.168.13.13` is a different network from `192.168.14.1/24`. Use `192.168.14.13/24` with gateway `192.168.14.1` unless you really have a `192.168.13.0/24` router.

Fix an already-installed CT without reinstalling: re-download the helper and choose **Fix / change LAN IP**. Or on the host:

```bash
pct set <CTID> --net0 name=eth0,bridge=vmbr0,firewall=0,ip=192.168.14.13/24,gw=192.168.14.1
pct exec <CTID> -- env RV_CIDR=192.168.14.13/24 RV_GATEWAY=192.168.14.1 bash /opt/receiptvault/deploy/guest-network.sh
pct exec <CTID> -- systemctl restart caddy
```

Then open `http://192.168.14.13/` (port 80) or `http://192.168.14.13:8080`.

## Cannot open the app / still see Caddy

Run this **on the Proxmox host** (the shell where `pct` works), not inside the LXC:

```bash
wget -O /root/fix-receiptvault.sh \
  https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/fix-from-host.sh
bash /root/fix-receiptvault.sh
```

It finds the container, puts it on the **same subnet as vmbr0** (if Proxmox is `192.168.14.1`, the app becomes `192.168.14.13`), stops Caddy, binds ReceiptVault on port **8082**, and curls the page from the host. Open the URL it prints, for example `http://192.168.14.13:8082/`.

`192.168.13.13` is a different network from `192.168.14.1`. A laptop that loads `https://192.168.14.1:8006` will not reach `.13.13` without a router.

## App will not start

- `pg_isready` and `redis-cli ping` should succeed.
- `RECEIPTVAULT_DATABASE_URL` must use the `postgresql+psycopg://` scheme.
- `journalctl -u receiptvault -u receiptvault-worker` on production.

## First-run setup already claimed

Setup is one-time. Reset the owner with `receiptvault reset-password` rather than re-opening `/setup`.

## Microsoft connect fails

- Confirm the Entra redirect URI equals Settings → OAuth callback.
- Personal Hotmail/Outlook need the `common` authority.
- Tenant policy may block unverified apps; an admin may need to allow `Mail.Read`.
- For local tests set `RECEIPTVAULT_GRAPH_MOCK=true` and use the three mock identities.

## Scan stuck or duplicated

- Check Scan jobs. Cancel writes `cancel_requested`; the next page is not lost.
- Re-running a job with the same `idempotency_key` returns the original job.
- Graph 429s wait on `Retry-After` plus jitter.

## Upload 413 through Cloudflare

Chunk size must stay at or below 50 MiB (default 16). Free/Pro request bodies are 100 MB. Do not raise Caddy/`client_max_body_size` as a substitute for chunking.

## OCR empty

Install `tesseract-ocr` and `ocrmypdf`. The pipeline still extracts embedded PDF text without them.

## Disk filling

Settings → health shows staging bytes. Expired transfer sessions are cleaned by the cleanup job. Soft-deleted originals remain until `RECEIPTVAULT_SOFT_DELETE_DAYS`.
