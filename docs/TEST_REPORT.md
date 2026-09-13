# Test report

Recorded 2026-09-13 in this development environment.

## Backend

```text
cd backend && uv run pytest -q
22 passed
```

After installer syntax test:

```text
uv run pytest -q
23 passed
```

Coverage includes:

- Australian FY assignment and fallback
- Decimal money parsing
- Hashing / AES-GCM token encryption
- Duplicate/candidate rules
- Safe path / zip-slip rejection
- OAuth PKCE
- Classification safeguards (no fabricated work purpose; not-tax-advice disclaimer)
- Chunk manifest arithmetic
- Graph mock: three identities, idempotent scan
- CSRF, unauthorized access, HTML sanitizer, security headers, log redaction
- Chunked upload resume, corrupt/missing chunks, zero/one-byte, Unicode folder package + range download
- Installer `bash -n`

## Frontend

```text
cd frontend && npm run build
✓ built (TypeScript + Vite)
```

## Production image of the UI

`frontend/dist` is produced by `npm run build` and served by FastAPI when present.

## Known gaps versus BR-TEST-002 extremes

- 100 MiB and multi-gigabyte fixtures are supported by the same session/chunk code; CI uses small payloads. Operators can verify with `dd` + the upload API.
- Playwright browser e2e is intended for a desktop with browsers installed; this environment uses API integration tests plus a manual UI pass.
