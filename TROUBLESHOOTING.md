# Troubleshooting

## Open the app

On the Proxmox host:

```bash
cd /root/ReceiptVault
git pull
bash deploy/install-receiptvault.sh
```

If `/root/ReceiptVault` is missing:

```bash
git clone --depth 1 https://github.com/McKrackenAU/ReceiptVault.git /root/ReceiptVault
bash /root/ReceiptVault/deploy/install-receiptvault.sh
```

If the site cannot be reached, on the Proxmox host:

```bash
cd /root/ReceiptVault
git pull
bash deploy/reach.sh
```

That forces the CT onto **192.168.13.14/20** and starts the app. Then open **http://192.168.13.14/** (http, not https). Settings must show **1.5.1**.

## App will not start

- `password authentication failed for user "receiptvault"` means the URL in `/etc/receiptvault/receiptvault.env` does not match Postgres. Re-run `fix-from-host.sh`, or inside the CT: `bash /opt/receiptvault/deploy/ensure-db.sh && systemctl restart receiptvault`.
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
- Use **Sign in with Microsoft** (device code). In Entra, enable **Allow public client flows**.
- The LXC must reach the internet via the gateway on the Proxmox bridge (the address the installer suggests).

## Scan stuck or duplicated

- Check Scan jobs. Cancel writes `cancel_requested`; the next page is not lost.
- Re-running a job with the same `idempotency_key` returns the original job.
- Graph 429s wait on `Retry-After` plus jitter.

## Upload 413 through Cloudflare

Chunk size must stay at or below 50 MiB (default 16). Free/Pro request bodies are 100 MB.

## OCR empty

Install `tesseract-ocr` and `ocrmypdf`. The pipeline still extracts embedded PDF text without them.

## Disk filling

Settings → health shows staging bytes. Expired transfer sessions are cleaned by the cleanup job. Soft-deleted originals remain until `RECEIPTVAULT_SOFT_DELETE_DAYS`.
