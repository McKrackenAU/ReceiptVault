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

## Production (Debian / Proxmox LXC)

See `deploy/install-receiptvault.sh`. Safer sequence:

1. Copy the script to the Proxmox host
2. Read it
3. `bash install-receiptvault.sh` as root

Do not put mailbox passwords or tunnel tokens on the curl command line. The installer can accept a Cloudflare token interactively.

After install, open the LAN URL, create the owner, set timezone, confirm evidence storage, add Entra credentials (or keep mock off in production), connect three inboxes, choose audit years, and start the first historical scan. No source edits are required.

## Operator commands

```bash
receiptvault reset-password OWNER_USERNAME 'new-long-password'
receiptvault disable-totp OWNER_USERNAME
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
