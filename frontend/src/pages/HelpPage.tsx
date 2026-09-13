import { Disclaimer } from '@/components/Layout'
import { Card } from '@/components/ui/card'

export function HelpPage() {
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Help and setup</h1>
      <Disclaimer />
      <Card className="mb-4">
        <h2 className="font-serif text-2xl">What this app does</h2>
        <p className="mt-2 text-sm">
          ReceiptVault keeps original emails and attachments, extracts receipt fields, and helps you review line items for an ATO audit
          pack. It never files a tax return, never writes to your mailbox, and never decides that an expense is legally deductible.
        </p>
      </Card>
      <Card className="mb-4">
        <h2 className="font-serif text-2xl">ATO records you still need</h2>
        <p className="mt-2 text-sm">
          Official guidance (ATO, last updated 8 June 2026) says a work-related deduction generally needs written evidence showing
          cost, supplier name, nature of the expense, date of purchase/payment, and how the expense relates to earning your income,
          including work versus private use. A bank statement alone is not written evidence from the supplier. Keep records for five
          years from lodgement unless a longer rule applies.
        </p>
        <p className="mt-2 text-sm">
          Source:{' '}
          <a className="underline" href="https://www.ato.gov.au/individuals-and-families/income-deductions-offsets-and-records/records-you-need-to-keep">
            Records you need to keep (ATO)
          </a>
        </p>
      </Card>
      <Card className="mb-4">
        <h2 className="font-serif text-2xl">Connect Hotmail or Outlook</h2>
        <p className="mt-2 text-sm">
          ReceiptVault never asks for your mailbox password. You register a free Microsoft Entra app (your own), paste the ID and
          secret under Settings, then click Sign in with Microsoft. Microsoft shows the Hotmail login. After you approve Mail.Read,
          you return here with the inbox connected.
        </p>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
          <li>Open entra.microsoft.com → App registrations → New registration. Name it ReceiptVault.</li>
          <li>Supported account types: accounts in any organisational directory <em>and</em> personal Microsoft accounts.</li>
          <li>Redirect URI (Web): copy the exact callback from Settings (it looks like http://192.168.13.13/api/v1/mail/oauth/callback).</li>
          <li>Certificates &amp; secrets → New client secret. Copy the secret value once.</li>
          <li>API permissions → Microsoft Graph → Delegated: openid, profile, email, offline_access, Mail.Read. No Mail.ReadWrite or Mail.Send.</li>
          <li>Settings → paste Application (client) ID and the secret → Save Microsoft app.</li>
          <li>Inbox accounts → Sign in with Microsoft → log into Hotmail on Microsoft&apos;s page.</li>
        </ol>
      </Card>
      <Card>
        <h2 className="font-serif text-2xl">Cloudflare Tunnel</h2>
        <p className="mt-2 text-sm">
          Point an existing tunnel at the LXC origin (Caddy on port 8080). Free/Pro proxied uploads are capped at 100 MB per request
          (Cloudflare docs, 5 Sep 2026) — this app therefore uses 16 MiB application-level chunks. Optional Cloudflare Access is a
          second gate, not a substitute for ReceiptVault login.
        </p>
      </Card>
    </div>
  )
}
