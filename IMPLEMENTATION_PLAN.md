# ReceiptVault Implementation Plan

Every requirement ID maps to one or more tasks. Status is updated at the end of each phase.

Legend: `todo` · `doing` · `done`

## Phase 1 — Repository, database, owner authentication, base UI

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| Planning docs, `.env.example`, operator docs skeleton | §1, §20 | done |
| Python package, FastAPI app, Alembic, settings | BR-INFRA-002, §13 | done |
| Users, sessions, recovery codes, Argon2id, CSRF, cookies | BR-AUTH-001, BR-SEC-001 | done |
| First-run owner setup; public registration disabled after | BR-AUTH-001 | done |
| TOTP + recovery codes; session regeneration | BR-AUTH-001 | done |
| Login rate limit; logout-all | BR-AUTH-001 | done |
| CLI: reset owner password / disable TOTP | BR-AUTH-002 | done |
| Audit log table + writer | BR-AUDIT-001 | done |
| React shell, routing, all required pages (real, not stubs) | BR-UI-001, BR-UI-006 | done |
| Login + setup screens | BR-UI-001 | done |

## Phase 2 — Evidence storage and manual ingestion

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| Content-addressed store, path safety, type detection | BR-DOC-001, BR-DOC-002, BR-SEC-001 | done |
| Manual upload ingest (small files via API; large via Phase 8) | BR-DOC-001 | done |
| Soft delete + confirmation + retention | BR-DOC-002 | done |
| Evidence metadata, parent/child, hashes | BR-DOC-002, §13 | done |

## Phase 3 — Preview, OCR, parsing, correction UI

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| PDF.js preview, image preview, email HTML (sanitized) | BR-UI-004, BR-SEC-001, BR-DOC-001 | done |
| Extraction pipeline: magic → text → OCR fallback | BR-OCR-001 | done |
| Receipt fields + line items + confidence | BR-OCR-002 | done |
| Arithmetic validation | BR-OCR-003 | done |
| Side-by-side correction; raw extraction preserved | BR-OCR-002, BR-UI-004 | done |
| Body-only HTML → sanitized PDF snapshot | BR-DOC-003 | done |

## Phase 4–5 — Microsoft Graph, jobs, multi-account, dedup

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| Entra OAuth authorization-code + PKCE | BR-MAIL-001 | done |
| Three independent accounts + connection UI | BR-MAIL-001, BR-MAIL-002 | done |
| Read-only Graph client; MIME + attachments; hashes | BR-MAIL-003, BR-MAIL-005 | done |
| Candidate detection (false-negative conservative) | BR-MAIL-004 | done |
| Durable checkpoints, throttle/Retry-After, resume | BR-MAIL-003 | done |
| Incremental schedule (default 15 min) | BR-MAIL-003 | done |
| Mock Graph identities for tests/demo | BR-TEST-003 | done |
| Exact + probable duplicate groups | BR-DOC-004 | done |

## Phase 6–7 — ATO review, search, folders, dashboard, audit UI

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| Australian FY assignment + fallback marking | BR-ATO-001 | done |
| Virtual folders/tags | BR-ATO-001, BR-UI-005 | done |
| Taxpayer/work profile | BR-ATO-002 | done |
| Line-item classification + user decisions | BR-ATO-003 | done |
| Explainability + not-tax-advice disclaimer | BR-ATO-004 | done |
| Dashboard totals (not labelled deductions) | BR-UI-002 | done |
| Search/filter | BR-UI-003 | done |
| Audit log UI + CSV export | BR-AUDIT-001 | done |

## Phase 8 — Chunked transfers and folder packaging

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| Upload sessions, chunk SHA-256, resume, finalize | BR-XFER-001, BR-XFER-002 | done |
| Range + download-session API | BR-XFER-003 | done |
| Streaming ZIP64 folder packages | BR-XFER-004, BR-UI-005 | done |
| Authz, cleanup, health counters | BR-XFER-005 | done |

## Phase 9 — Exports, backup/restore, health

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| FY/selection exports + manifest | BR-ATO-005 | done |
| Backup CLI/UI (DB, secrets, config, evidence) | BR-OPS-001 | done |
| Restore dry-run + integrity | BR-OPS-002 | done |
| Authenticated health + `/health/live` | BR-OPS-003 | done |

## Phase 10 — Proxmox installer

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| `install-receiptvault.sh` helper-script GUI | BR-INSTALL-001 … 005 | done |
| systemd units, Caddy, Debian packaging notes | BR-INFRA-001, BR-INFRA-002 | done |
| Update/rollback/repair/uninstall | BR-INSTALL-003, BR-INSTALL-004 | done |

## Phase 11 — Hardening, tests, docs, release

| Tasks | Requirement IDs | Status |
| --- | --- | --- |
| Security headers, CSP, log redaction, CI checks | BR-SEC-001 | done |
| Unit / integration / e2e / transfer / security tests | BR-TEST-001, BR-TEST-002 | done |
| Operator docs + OpenAPI + release archive | §20, BR-TEST-003 | done |

## Commands run at phase gates

Recorded in `docs/TEST_REPORT.md` as tests are executed.
