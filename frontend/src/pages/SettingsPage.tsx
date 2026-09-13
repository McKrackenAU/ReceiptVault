import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Disclaimer } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Textarea } from '@/components/ui/input'
import { api } from '@/lib/api'

type Settings = {
  timezone: string
  public_url: string
  graph_mock: boolean
  oauth_redirect: string
  chunk_size_mib: number
  evidence_root: string
  evidence_free_bytes: number
  staging_bytes: number
  selected_financial_year?: string
  app_version: string
  latest_bundle_version?: string
  update_available?: boolean
  can_self_update?: boolean
  ms_client_configured: boolean
}

type Health = {
  database: string
  queue: string
  storage_free_bytes: number
  staging_bytes: number
  pending_jobs: number
  failed_jobs: number
  mail: { label: string; status: string }[]
}

export function SettingsPage() {
  const [params] = useSearchParams()
  const wizard = params.get('wizard') === '1'
  const [settings, setSettings] = useState<Settings | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [year, setYear] = useState('2024-25')
  const [notes, setNotes] = useState('')
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [msg, setMsg] = useState('')
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    api<Settings>('/api/v1/settings').then((s) => {
      setSettings(s)
      if (s.selected_financial_year) setYear(s.selected_financial_year)
    })
    api<Health>('/api/v1/health').then(setHealth)
    api<{ adviser_notes: string | null }>('/api/v1/profile').then((p) => setNotes(p.adviser_notes || ''))
  }, [])

  if (!settings) return <p>Loading settings…</p>
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">{wizard ? 'First-run checklist' : 'Settings and health'}</h1>
      <Disclaimer />
      {wizard && (
        <Card className="mb-4">
          <ol className="list-decimal space-y-2 pl-5 text-sm">
            <li>Owner account created.</li>
            <li>Confirm timezone (default Australia/Melbourne) and evidence path below.</li>
            <li>Register a Microsoft Entra app (any org + personal accounts). Paste the client ID and secret below. Callback: {settings.oauth_redirect}</li>
            <li>Connect Hotmail / Outlook on Inbox accounts — you sign in at Microsoft, not on this page.</li>
            <li>Select audit years and start the first historical scan.</li>
          </ol>
        </Card>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="font-serif text-xl">Workspace</h2>
          <Label>Selected audit year</Label>
          <Input value={year} onChange={(e) => setYear(e.target.value)} />
          <Button className="mt-3" onClick={() => api('/api/v1/settings', { method: 'PUT', body: JSON.stringify({ selected_financial_year: year }) }).then(() => setMsg('Saved')).catch((err: Error) => setMsg(err.message))}>
            Save
          </Button>
          <Label className="mt-4">Adviser notes</Label>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Button className="mt-2" variant="outline" onClick={() => api('/api/v1/profile', { method: 'PUT', body: JSON.stringify({ adviser_notes: notes, common_equipment: [], audit_years: [year], periods: [] }) }).then(() => setMsg('Profile saved')).catch((err: Error) => setMsg(err.message))}>
            Save taxpayer profile
          </Button>
        </Card>
        <Card>
          <h2 className="font-serif text-xl">Microsoft app (required for real Hotmail)</h2>
          <p className="mb-3 text-sm text-slate">
            Create the app at{' '}
            <a className="underline" href="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade">
              entra.microsoft.com
            </a>
            . Supported accounts: any organisational directory <em>and</em> personal Microsoft accounts. Redirect URI (Web):
          </p>
          <p className="mb-3 break-all rounded-md bg-black/5 px-2 py-1 font-mono text-xs">{settings.oauth_redirect}</p>
          <p className="mb-3 text-sm text-slate">
            Delegated permissions only: openid, profile, email, offline_access, Mail.Read. Turn on{' '}
            <strong>Allow public client flows</strong> in the Entra app. Sign-in uses a short Microsoft device code so it
            works on http://192.168.13.13/. This box never asks for your Hotmail password.
          </p>
          <Label>Application (client) ID</Label>
          <Input value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder={settings.ms_client_configured ? 'Already saved — paste to replace' : 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'} />
          <Label className="mt-3">Client secret</Label>
          <Input type="password" autoComplete="new-password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder={settings.ms_client_configured ? 'Leave blank to keep the current secret' : 'Paste the secret value'} />
          <Button
            className="mt-3"
            onClick={() =>
              api('/api/v1/settings', {
                method: 'PUT',
                body: JSON.stringify({
                  ms_client_id: clientId || undefined,
                  ms_client_secret: clientSecret || undefined,
                }),
              }).then(() => {
                setClientSecret('')
                setMsg('Microsoft app saved. Open Inbox accounts and choose Sign in with Microsoft.')
                return api<Settings>('/api/v1/settings').then(setSettings)
              })
            }
          >
            Save Microsoft app
          </Button>
          <p className="mt-2 text-sm">Configured: {settings.ms_client_configured ? 'yes' : 'no'}</p>
        </Card>
        <Card>
          <h2 className="font-serif text-xl">Storage and security</h2>
          <p className="text-sm">Evidence root: {settings.evidence_root}</p>
          <p className="text-sm">Free: {(settings.evidence_free_bytes / 1024 / 1024).toFixed(0)} MiB</p>
          <p className="text-sm">Staging: {(settings.staging_bytes / 1024 / 1024).toFixed(1)} MiB</p>
          <p className="text-sm">Chunk size: {settings.chunk_size_mib} MiB</p>
          <p className="text-sm">Public URL: {settings.public_url}</p>
          <p className="text-sm">Microsoft app configured: {settings.ms_client_configured ? 'yes' : 'no'} (mock={String(settings.graph_mock)})</p>
          <p className="text-sm">Version {settings.app_version}</p>
          {settings.latest_bundle_version && settings.latest_bundle_version !== settings.app_version && (
            <p className="text-sm">Bundle on this build: {settings.latest_bundle_version}</p>
          )}
          <Button
            className="mt-3"
            disabled={updating}
            onClick={() => {
              setUpdating(true)
              setMsg('Downloading the latest ReceiptVault from GitHub. Keep this tab open…')
              api<{ version: string }>('/api/v1/ops/update', { method: 'POST', body: JSON.stringify({}) })
                .then((r) => {
                  setMsg(`Updated to ${r.version}. The app is restarting — wait 10 seconds, then hard-refresh (Ctrl+Shift+R).`)
                })
                .catch((err: Error) => {
                  setMsg(err.message || 'Update failed')
                })
                .finally(() => setUpdating(false))
            }}
          >
            {updating ? 'Updating…' : 'Update from GitHub'}
          </Button>
          <p className="mt-2 text-sm text-slate">
            This downloads the app tarball. It does not use git. After the first host update you can also type{' '}
            <code>receiptvault-update</code> on the Proxmox host.
          </p>
        </Card>
        <Card>
          <h2 className="font-serif text-xl">System health</h2>
          {health ? (
            <ul className="text-sm">
              <li>Database: {health.database}</li>
              <li>Queue: {health.queue}</li>
              <li>Pending jobs: {health.pending_jobs}</li>
              <li>Failed jobs: {health.failed_jobs}</li>
              <li>Staging bytes: {health.staging_bytes}</li>
              {health.mail.map((m) => (
                <li key={m.label}>{m.label}: {m.status}</li>
              ))}
            </ul>
          ) : (
            <p>Loading health…</p>
          )}
        </Card>
        <Card>
          <h2 className="font-serif text-xl">Backup</h2>
          <Button onClick={() => api('/api/v1/ops/backup', { method: 'POST', body: JSON.stringify({ include_evidence: true }) }).then((r) => setMsg(JSON.stringify(r)))}>
            Create backup now
          </Button>
          <p className="mt-2 text-sm">CLI: <code>receiptvault backup</code> and <code>receiptvault restore PATH --dry-run</code></p>
        </Card>
      </div>
      {msg && <p className="mt-3 text-sm">{msg}</p>}
    </div>
  )
}
