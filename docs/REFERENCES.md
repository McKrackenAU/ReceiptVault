# Reference sources consulted

Recorded as required by section 19 of the build requirements. Retrieved **2026-09-13**.

| Source | URL | Version / date noted | How it was used |
| --- | --- | --- | --- |
| Microsoft Graph permissions reference | https://learn.microsoft.com/en-us/graph/permissions-reference | Live docs, retrieved 2026-09-13 | Confirmed delegated `Mail.Read` is valid for personal Microsoft accounts and work/school accounts. Did **not** request `Mail.ReadWrite` or `Mail.Send`. |
| Microsoft Graph permissions overview | https://learn.microsoft.com/en-us/graph/permissions-overview | Live docs, retrieved 2026-09-13 | Least-privilege delegated permissions; admin-restricted vs user-consent. |
| Microsoft identity scopes / `offline_access` | https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc | Live docs, retrieved 2026-09-13 | Explicit `openid`, `profile`, `email`, `offline_access` on the v2 endpoint so refresh tokens are issued. |
| Cloudflare Workers / platform limits | https://developers.cloudflare.com/workers/platform/limits/ | Updated 2026-09-05; retrieved 2026-09-13 | Free/Pro request body **100 MB**. Default transfer chunk is 16 MiB. |
| Cloudflare 413 / upload size | https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/ | Retrieved 2026-09-13 | Confirms proxied/Tunnel uploads share the plan upload cap. Chunking is the supported approach. |
| ATO records you need to keep | https://www.ato.gov.au/individuals-and-families/income-deductions-offsets-and-records/records-you-need-to-keep | ATO last updated 8 June 2026; retrieved 2026-09-13 | Help page, evidence-field mapping, and the “not tax advice” disclaimer. |

If a provider changes behaviour, record the conflict here and keep the safest compatible implementation.
