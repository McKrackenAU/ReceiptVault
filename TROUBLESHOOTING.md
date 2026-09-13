# Troubleshooting

## Open the app

The installer asks for the LXC IPv4 and the router/gateway. After that you open:

**http://&lt;the-ip-you-typed&gt;/**

Typical values: LXC `192.168.13.13`, router `192.168.1.1` → **http://192.168.13.13/**

If that is not working, or Settings still says **1.0.0**, paste this **one line** on the Proxmox host:

```bash
echo UPDATE && wget -4 --timeout=25 --tries=2 -nv -O /root/fix-receiptvault.sh https://raw.githubusercontent.com/McKrackenAU/ReceiptVault/main/deploy/fix-from-host.sh && bash /root/fix-receiptvault.sh
```

You must see `UPDATE` immediately. If the prompt is `>` instead of `#`, the paste broke — press Ctrl+C and try again. If `UPDATE` appears then nothing, wget cannot reach GitHub; wait 25 seconds for the timeout error.

The first line after download must say `ReceiptVault 1.4.0`. That script downloads the new app on the host (the LXC has no git repo), unpacks it, purges Caddy, and binds port 80. Hard-refresh the browser (Ctrl+Shift+R). Settings must then show **1.4.0**.

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
- The LXC must reach the internet via the gateway you entered (typically **192.168.1.1**).

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
