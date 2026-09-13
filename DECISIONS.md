# ReceiptVault Design Decisions

Decisions below are not prescribed by `CURSOR_BUILD_REQUIREMENTS.md`. They exist so operators and later contributors can see why the implementation looks this way.

| ID | Decision | Rationale | Date |
| --- | --- | --- | --- |
| D-001 | Background queue is **Dramatiq + Redis** | Lighter than Celery for a single-owner monolith, has retries/acks, and maps cleanly to systemd (`receiptvault-worker`). | 2026-09-13 |
| D-002 | **No Caddy.** FastAPI binds `:80` | Debian Caddy's default site stole port 80 (welcome page). The app listens on `:80` itself. HTTPS is Cloudflare Tunnel when wanted. | 2026-09-13 |
| D-003 | ORM is **SQLAlchemy 2.0 (sync)** with Alembic | Sync sessions are simpler to share between FastAPI request handlers and Dramatiq workers than mixed async/sync engines. | 2026-09-13 |
| D-004 | Frontend is **Vite + React + TypeScript + Tailwind CSS + shadcn/ui** | Requirements specified React + TypeScript; shadcn covers accessible primitives without a second component library. | 2026-09-13 |
| D-005 | Microsoft authority defaults to `https://login.microsoftonline.com/common` | Required to support personal Hotmail/Outlook and work/school tenants with one registration. Documented in the Entra walkthrough. | 2026-09-13 |
| D-006 | Graph access uses **delegated `Mail.Read` only** (plus OIDC + `offline_access`) | Least privilege for read-only ingestion. No `Mail.ReadWrite` or `Mail.Send`. Consulted Microsoft Graph permissions reference (retrieved 2026-09-13). | 2026-09-13 |
| D-007 | Optional `GRAPH_MOCK=true` provider | Enables concurrent connection of three mocked Microsoft identities and all scan/e2e tests without live credentials. Disabled by default. Never used as a production mailbox. | 2026-09-13 |
| D-008 | Token encryption is **AES-256-GCM** via the `cryptography` library | Authenticated encryption for refresh tokens. Master key lives in a root-readable env file, never in PostgreSQL. | 2026-09-13 |
| D-009 | HTML sanitizer is **nh3** (Ammonia) | Strict allow-list sanitization for email HTML. Remote images and active content stripped before display or PDF snapshot. | 2026-09-13 |
| D-010 | Body-only receipt PDF uses **Playwright Chromium** when installed, ReportLab fallback | Requirements ask for a local headless browser. ReportLab produces a text/layout snapshot if Chromium is absent so the app still starts. | 2026-09-13 |
| D-011 | File-type detection uses **libmagic**, then content sniffing | Extensions and client MIME headers are never trusted alone. | 2026-09-13 |
| D-012 | Default display timezone is `Australia/Melbourne` | Matches the ATO-oriented operator. All stored timestamps remain UTC. | 2026-09-13 |
| D-013 | Money is `Numeric(19, 4)` + ISO-4217 currency | Never float. Four decimal places cover GST fractions without binary rounding. | 2026-09-13 |
| D-014 | Classification v1 is **rule-based**; pluggable model providers stay disabled | The app must start without an external AI API. Suggestions are labelled review aids, never tax advice. | 2026-09-13 |
| D-015 | Folder packages are **ZIP64 written to disk** then served via the same range/chunk download API | Avoids building multi-gigabyte archives in RAM (Cloudflare Free/Pro request body limit is 100 MB as of 2026-09-05). | 2026-09-13 |
| D-016 | SPA CSRF uses a **session-bound token** exposed at `GET /api/v1/auth/csrf` and required as `X-CSRF-Token` | HttpOnly session cookie cannot be read by JS; the CSRF cookie/header pair covers state-changing browser calls. | 2026-09-13 |
| D-017 | Sessions are stored hashed in PostgreSQL | Allows “log out all sessions” and survives restart without a separate session store. | 2026-09-13 |
| D-018 | Local/dev bind is `0.0.0.0:8473` (API) and `0.0.0.0:18473` (Vite) | Avoids well-known ports. Production FastAPI listens on `:80`. | 2026-09-13 |
| D-019 | Python packaging via **uv** + `pyproject.toml` | Fast, lockable installs for Debian and this development environment. | 2026-09-13 |
| D-020 | First-run wizard covers owner, timezone, storage check, Entra credentials, three inboxes, audit years, first scan | Satisfies the handover requirement that production must not need source edits. | 2026-09-13 |
| D-021 | Cloudflare request sizing | Consulted Cloudflare Workers/platform limits (updated 2026-09-05): Free/Pro request body 100 MB. Default chunk 16 MiB stays well under that with protocol overhead. | 2026-09-13 |
| D-022 | ATO Help links | Official record-keeping page retrieved 2026-09-13 (ATO last updated 2026-06-08). Help quotes eligibility/evidence rules and does not invent deductions. | 2026-09-13 |
| D-023 | Updates use a **GitHub tarball**, never `git pull` in the LXC | The installer copies the tree without `.git`. Host command `receiptvault-update` clones on the Proxmox host; Settings and `receiptvault update` unpack `main.tar.gz` inside the CT. | 2026-09-13 |

## Ambiguities considered and not changed

- “Hotmail / Outlook / Microsoft 365” is implemented as three independent Graph connections, not three hardcoded product SKUs.
- Soft-delete retention default is **30 days** (configurable).
- Incremental scan default is **15 minutes** as specified.
- Unprivileged LXC is the installer default; nesting/keyctl are offered only when bind-mount/NFS requires them.
