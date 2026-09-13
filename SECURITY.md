# Security

## Authentication

- First launch creates the single owner. Registration routes then refuse new users.
- Passwords: Argon2id, minimum 12 characters.
- Optional TOTP with hashed recovery codes.
- New session ID after login. HttpOnly `SameSite=Lax` cookies; `Secure` when `RECEIPTVAULT_COOKIE_SECURE=true`.
- CSRF: session-bound token from `GET /api/v1/auth/csrf` or `/me`, required as `X-CSRF-Token` on state-changing requests.
- Login rate-limited. “Log out all sessions” revokes every row.
- Recovery: `receiptvault reset-password` / `disable-totp` on the host console.

## Secrets

- Microsoft refresh tokens encrypted at rest (AES-256-GCM).
- Master key lives in `/etc/receiptvault/receiptvault.env` (root-readable, mode 0600), never in PostgreSQL.
- Structured logs redact tokens, cookies, Authorization, passwords, email bodies, and document content.

## Uploads and paths

- libmagic + signature sniffing; extensions are not trusted.
- Executables are preserved labelled and never previewed.
- `safe_relpath` rejects `..`, absolute paths, and symlink escape.
- ZIP packaging uses sanitized relative names (zip-slip tests in CI).

## Headers and proxies

- CSP, `X-Frame-Options: DENY`, `nosniff`, restrictive referrer policy.
- `X-Forwarded-For` is used only when `RECEIPTVAULT_TRUSTED_PROXIES` is set.

## Mail

- Delegated `Mail.Read` only. The Graph client never sends, deletes, moves, or marks messages.

## CI

GitHub Actions (or equivalent) runs `ruff`, `bandit`, and `pytest`.
