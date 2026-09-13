# Microsoft Entra app registration

Consulted 2026-09-13:

- https://learn.microsoft.com/en-us/graph/permissions-reference (`Mail.Read` delegated is valid for personal and work/school accounts)
- https://learn.microsoft.com/en-us/graph/permissions-overview
- https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc (`offline_access` must be requested explicitly on the v2 endpoint to receive refresh tokens)

## Steps

1. Entra admin centre → App registrations → New registration.
2. Name: `ReceiptVault`.
3. Supported account types: **Accounts in any organisational directory and personal Microsoft accounts**.
4. Authentication → **Allow public client flows** = Yes. ReceiptVault uses the device-code flow so Hotmail works on `http://192.168.x.x` (Microsoft often rejects that as a Web redirect).
5. Optional Web redirect (only needed for HTTPS): Settings → OAuth callback.
6. Certificates & secrets → New client secret. Store it only in `/etc/receiptvault/receiptvault.env` as `RECEIPTVAULT_MS_CLIENT_SECRET`.
7. API permissions → Microsoft Graph → Delegated:
   - `openid`
   - `profile`
   - `email`
   - `offline_access`
   - `Mail.Read`
8. Do **not** add `Mail.ReadWrite`, `Mail.Send`, or application (app-only) mail permissions.
9. Set `RECEIPTVAULT_MS_CLIENT_ID` and `RECEIPTVAULT_MS_TENANT=common`.

The app uses authorization-code flow with PKCE (`S256`).
