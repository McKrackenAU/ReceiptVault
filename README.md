# ReceiptVault

Private, self-hosted evidence locker for receipts and invoices. It connects read-only Microsoft inboxes (Hotmail / Outlook / Microsoft 365), preserves original emails and attachments, extracts line items, and helps you review likely Australian work-related expenses for an ATO audit pack.

ReceiptVault is **not tax advice**. Suggestions are labelled Potentially claimable, Needs review, or Likely private/non-claimable. You or your adviser make the claim decision.

## What you get

- Single-owner first-run setup (no public registration)
- Three independent Microsoft Graph connections (`Mail.Read` only)
- Immutable, content-addressed originals
- OCR + correction UI with PDF.js preview
- Australian financial-year virtual folders
- Cloudflare-safe 16 MiB chunked uploads/downloads and ZIP64 folder packages
- Backup/restore CLI and UI
- Proxmox helper-script installer for an unprivileged Debian 13 LXC

## Local development

Requirements: Python 3.12+, Node 20+, PostgreSQL 16, Redis, Tesseract/OCRmyPDF optional.

```bash
sudo apt install postgresql postgresql-contrib redis-server tesseract-ocr libmagic1
sudo pg_ctlcluster 16 main start
sudo redis-server --daemonize yes
sudo -u postgres psql -c "CREATE USER receiptvault LOGIN PASSWORD 'receiptvault_dev';"
sudo -u postgres createdb -O receiptvault receiptvault

cp .env.example .env
# set RECEIPTVAULT_MASTER_KEY and, for demo scans, RECEIPTVAULT_GRAPH_MOCK=true

chmod +x scripts/dev.sh
./scripts/dev.sh
```

- UI: http://127.0.0.1:18473
- API / OpenAPI: http://127.0.0.1:8473/api/docs
- Live probe: http://127.0.0.1:8473/health/live

Default local ports avoid 3000/5173/8080.

## Tests

```bash
cd backend && uv sync --extra dev && uv run pytest -q
cd ../frontend && npm test || true
```

## Production (Proxmox)

On the Proxmox host:

```bash
cd /root/ReceiptVault
git pull
bash deploy/install-receiptvault.sh
```

First time: `git clone --depth 1 https://github.com/McKrackenAU/ReceiptVault.git /root/ReceiptVault` then the same `bash deploy/install-receiptvault.sh`.

Choose **Default install** for a new CT. Accept `192.168.13.14` and the suggested gateway. The prefix is **/20**.

If the CT already exists and the browser cannot reach it:

```bash
cd /root/ReceiptVault
git pull
bash deploy/reach.sh
```

Then open **http://192.168.13.14/** (http, not https). Create the owner, save the Microsoft app in Settings, connect Hotmail, start the historical scan.

## Operator commands

```bash
receiptvault reset-password OWNER_USERNAME 'new-long-password'
receiptvault disable-totp OWNER_USERNAME
receiptvault update
receiptvault backup --include-evidence
receiptvault restore /path/to/backup.tar --dry-run
```

These log the action and never print existing passwords or mailbox tokens.

## Documentation

- `ARCHITECTURE.md` — process layout and data flow
- `SECURITY.md` — auth, CSRF, headers, encryption
- `PRIVACY.md` — what stays on the LXC
- `BACKUP_RESTORE.md` — backup/restore contract
- `TROUBLESHOOTING.md` — common failures
- `docs/MICROSOFT_APP_REGISTRATION.md`
- `docs/CLOUDFLARE_TUNNEL.md`
- `docs/REFERENCES.md` — upstream docs consulted
- `DECISIONS.md` — implementation choices
- `IMPLEMENTATION_PLAN.md` — requirement traceability
