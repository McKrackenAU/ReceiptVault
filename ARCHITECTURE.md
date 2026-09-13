# Architecture

ReceiptVault is a maintainable monolith: one FastAPI process serves `/api/v1` and the built React UI, plus a Dramatiq worker for long-running jobs.

```text
Browser ──► Caddy :8080 ──► FastAPI :8473
                               │
                    PostgreSQL 16     Redis
                               │
                         Dramatiq worker
                               │
              evidence/  derived/  staging/  backups/
```

## Processes

| Unit | Role |
| --- | --- |
| `receiptvault.service` | FastAPI / UI |
| `receiptvault-worker.service` | Dramatiq consumer (scan, package, export, cleanup) |
| `postgresql` | System of record |
| `redis-server` | Queue broker |
| `caddy` | LAN :8080 reverse proxy |
| optional `cloudflared` | Tunnel connector |

## Data flow

1. Owner authenticates (Argon2id, optional TOTP). Sessions are hashed in PostgreSQL.
2. Mailboxes connect via OAuth 2.0 + PKCE. Refresh tokens are AES-256-GCM encrypted with `RECEIPTVAULT_MASTER_KEY`.
3. Scans page Graph messages, write a checkpoint after every page, detect receipt candidates conservatively, and store `.eml` plus byte-for-byte attachments under `evidence/{aa}/{bb}/{sha256}-name`.
4. OCR/parse runs in the worker. User edits write field history; raw extraction is immutable.
5. Virtual folders (`ATO Audit/2024-25/Needs Review/…`) are tags, not copies of bytes.
6. Large transfers use upload/download sessions with per-chunk SHA-256 and HTTP ranges.

## API

Versioned under `/api/v1`. OpenAPI at `/api/v1/openapi.json`. Errors use problem-details (`title`, `status`, `detail`). Job-creating POSTs accept `idempotency_key`.
