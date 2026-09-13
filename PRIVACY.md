# Privacy

ReceiptVault is local-first. Receipt documents, OCR text, metadata, OAuth tokens, and classifications stay on the LXC or its bind-mounted evidence volume.

- No public SaaS telemetry unless `RECEIPTVAULT_TELEMETRY_OPT_IN=true` (default false; v1 collects nothing).
- No training on your documents.
- Email HTML is sanitized before display; remote images are blocked.
- Audit events store minimal non-sensitive metadata.
- Disconnecting a mailbox removes local tokens and stops jobs. Previously imported evidence remains until you explicitly soft-delete it.

If you expose the app through Cloudflare Tunnel, Cloudflare terminates TLS at the edge. Application login remains mandatory. Optional Cloudflare Access is an extra gate, not a replacement.
