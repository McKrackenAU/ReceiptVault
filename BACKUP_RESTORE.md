# Backup and restore

## What a backup contains

- PostgreSQL dump (`database.sql`)
- Application configuration snapshot
- Encrypted token ciphertext as stored in the database (still wrapped by the master key)
- Original evidence and derived files **or** `EVIDENCE_EXCLUDED.txt` if you opted out

A sidecar `.sha256` is written next to the archive. Encrypted archives use a user-supplied passphrase (AES-256-GCM).

The API and CLI **do not** report success if you asked to include evidence and the evidence root was missing.

## Backup

```bash
receiptvault backup
receiptvault backup --passphrase 'only-on-console' --include-evidence
```

UI: Settings → Create backup now.

## Restore

```bash
receiptvault restore /var/lib/receiptvault/backups/receiptvault-….tar --dry-run
receiptvault restore /var/lib/receiptvault/backups/receiptvault-….tar --no-dry-run --confirm
```

Dry-run checks the sidecar hash, archive members, and path safety (no zip/tar slip). Confirm is required for a live restore. After restore, `/health` and an evidence hash comparison should be run before opening the app to users.

Keep `/etc/receiptvault/receiptvault.env` (master key) in a separate, offline copy. Restoring the database without the original master key leaves mailbox tokens unreadable — reconnect the inboxes.
