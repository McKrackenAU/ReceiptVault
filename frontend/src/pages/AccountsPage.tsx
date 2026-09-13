import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Disclaimer } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Badge, Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { ApiError, api } from '@/lib/api'

type Account = {
  id: string
  label: string
  masked_address: string
  provider_type: string
  connected_at: string
  last_token_refresh_at: string | null
  last_scan_at: string | null
  scan_status: string
  emails_examined: number
  candidates_found: number
  documents_imported: number
  duplicates_skipped: number
  failures: number
}

type AppSettings = {
  graph_mock: boolean
  oauth_redirect: string
  ms_client_configured: boolean
}

export function AccountsPage() {
  const [params] = useSearchParams()
  const [items, setItems] = useState<Account[]>([])
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [label, setLabel] = useState('Hotmail personal')
  const [hint, setHint] = useState('')
  const [identity, setIdentity] = useState('hotmail-one')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [device, setDevice] = useState<{
    state: string
    user_code: string
    verification_uri: string
    interval: number
    message: string
  } | null>(null)

  async function refresh() {
    const r = await api<{ items: Account[] }>('/api/v1/mail/accounts')
    setItems(r.items)
  }
  useEffect(() => {
    refresh().catch((e) => setMessage(e.message))
    api<AppSettings>('/api/v1/settings')
      .then(setSettings)
      .catch((e) => setMessage(e.message))
    if (params.get('connected') === '1') {
      setMessage('Microsoft sign-in finished. If the account is not listed, the callback may have failed — try Connect again.')
    }
    if (params.get('ms_error')) {
      setMessage(`Microsoft rejected the browser redirect (${params.get('ms_error')}). Use the device code on this page instead — HTTP LAN addresses are often blocked.`)
    }
  }, [params])

  async function connect() {
    setBusy(true)
    setMessage('')
    setDevice(null)
    try {
      const body: Record<string, string> = { label }
      if (settings?.graph_mock) body.mock_identity = identity
      const r = await api<{
        state: string
        user_code: string
        verification_uri: string
        interval: number
        message: string
        mock?: boolean
      }>('/api/v1/mail/connect/device', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      setDevice({
        state: r.state,
        user_code: r.user_code,
        verification_uri: r.verification_uri,
        interval: r.interval || 5,
        message: r.message,
      })
      setMessage(r.message)
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not start Microsoft sign-in')
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!device) return
    let stop = false
    async function poll() {
      while (!stop) {
        await new Promise((ok) => setTimeout(ok, Math.max(device.interval, 3) * 1000))
        if (stop) return
        try {
          const r = await api<{ status: string }>('/api/v1/mail/connect/device/poll', {
            method: 'POST',
            body: JSON.stringify({ state: device.state }),
          })
          if (r.status === 'connected') {
            setDevice(null)
            setBusy(false)
            setMessage('Hotmail is connected.')
            await refresh()
            return
          }
        } catch (err) {
          setDevice(null)
          setBusy(false)
          setMessage(err instanceof ApiError ? err.message : 'Microsoft sign-in failed')
          return
        }
      }
    }
    poll()
    return () => {
      stop = true
    }
  }, [device])

  async function act(id: string, path: string, extra: object = {}) {
    try {
      await api(`/api/v1/mail/accounts/${id}${path}`, { method: 'POST', body: JSON.stringify(extra) })
      await refresh()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Action failed')
    }
  }

  async function scan(id: string, dry = false) {
    try {
      const r = await api<{ status?: string; estimated_messages?: number }>(`/api/v1/mail/scans`, {
        method: 'POST',
        body: JSON.stringify({ account_id: id, folders: ['inbox'], dry_run: dry, idempotency_key: dry ? undefined : `scan-${id}-${Date.now()}` }),
      })
      setMessage(dry ? `Estimate: ${r.estimated_messages} messages` : `Scan ${r.status}`)
      await refresh()
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Scan failed')
    }
  }

  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Inbox accounts</h1>
      <Disclaimer />
      <Card className="mb-6">
        <h2 className="font-serif text-xl">Connect a Hotmail or Outlook inbox</h2>
        <p className="mt-2 text-sm text-slate">
          You do not type your mailbox password here. ReceiptVault sends you to Microsoft. You sign in there; this app only
          receives a read-only Mail.Read token.
        </p>
        {settings && !settings.graph_mock && !settings.ms_client_configured && (
          <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm">
            Microsoft sign-in is not configured yet. Open{' '}
            <Link className="underline" to="/settings">
              Settings
            </Link>{' '}
            and paste the Application (client) ID and client secret from your Entra app. The redirect URI to add in Azure is{' '}
            <code className="break-all">{settings.oauth_redirect}</code>
          </p>
        )}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div>
            <Label htmlFor="label">Label in ReceiptVault</Label>
            <Input id="label" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          {settings?.graph_mock ? (
            <div>
              <Label htmlFor="identity">Demo inbox</Label>
              <select
                id="identity"
                className="h-10 w-full rounded-md border border-pine/20 bg-white px-2"
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
              >
                <option value="hotmail-one">hotmail-one</option>
                <option value="hotmail-two">hotmail-two</option>
                <option value="outlook-work">outlook-work</option>
              </select>
            </div>
          ) : (
            <div>
              <Label htmlFor="hint">Your Hotmail / Outlook address (optional)</Label>
              <Input
                id="hint"
                type="email"
                placeholder="name@hotmail.com"
                value={hint}
                onChange={(e) => setHint(e.target.value)}
              />
            </div>
          )}
        </div>
        <div className="mt-3">
          <Button onClick={connect} disabled={busy || (settings !== null && !settings.graph_mock && !settings.ms_client_configured)}>
            {settings?.graph_mock ? 'Connect demo inbox' : 'Sign in with Microsoft'}
          </Button>
        </div>
        {device && (
          <div className="mt-4 rounded-md border border-pine/20 bg-black/5 p-4">
            <p className="text-sm">On your phone or this computer, open Microsoft and enter this code:</p>
            <p className="mt-2 font-mono text-3xl tracking-widest">{device.user_code}</p>
            <p className="mt-3 text-sm">
              <a className="underline" href={device.verification_uri} target="_blank" rel="noreferrer">
                {device.verification_uri}
              </a>
            </p>
            <p className="mt-2 text-sm text-slate">Waiting for you to finish sign-in at Microsoft…</p>
          </div>
        )}
        {message && <p className="mt-2 text-sm">{message}</p>}
      </Card>
      <div className="grid gap-4">
        {items.length === 0 && <p>No accounts connected.</p>}
        {items.map((a) => (
          <Card key={a.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-serif text-2xl">{a.label}</h2>
                <p className="text-sm text-slate">
                  {a.masked_address} · {a.provider_type}
                </p>
              </div>
              <Badge tone={a.scan_status === 'idle' ? 'moss' : 'amber'}>{a.scan_status}</Badge>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
              <div>Connected {new Date(a.connected_at).toLocaleString()}</div>
              <div>Token refresh {a.last_token_refresh_at ? new Date(a.last_token_refresh_at).toLocaleString() : '—'}</div>
              <div>Last scan {a.last_scan_at ? new Date(a.last_scan_at).toLocaleString() : '—'}</div>
              <div>Examined {a.emails_examined}</div>
              <div>Candidates {a.candidates_found}</div>
              <div>Imported {a.documents_imported}</div>
              <div>Duplicates {a.duplicates_skipped}</div>
              <div>Failures {a.failures}</div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => act(a.id, '/test')}>
                Test connection
              </Button>
              <Button variant="outline" onClick={() => scan(a.id, true)}>
                Dry-run estimate
              </Button>
              <Button onClick={() => scan(a.id)}>Start historical scan</Button>
              <Button variant="outline" onClick={() => scan(a.id)}>
                Scan now
              </Button>
              <Button variant="danger" onClick={() => act(a.id, '/disconnect')}>
                Disconnect
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
