import { useEffect, useState } from 'react'
import { Disclaimer } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Badge, Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { api } from '@/lib/api'

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

export function AccountsPage() {
  const [items, setItems] = useState<Account[]>([])
  const [label, setLabel] = useState('Hotmail personal')
  const [identity, setIdentity] = useState('hotmail-one')
  const [message, setMessage] = useState('')

  async function refresh() {
    const r = await api<{ items: Account[] }>('/api/v1/mail/accounts')
    setItems(r.items)
  }
  useEffect(() => {
    refresh().catch((e) => setMessage(e.message))
  }, [])

  async function connect() {
    const r = await api<{ authorize_url: string }>('/api/v1/mail/connect', {
      method: 'POST',
      body: JSON.stringify({ label, mock_identity: identity }),
    })
    window.location.href = r.authorize_url
  }

  async function act(id: string, path: string, extra: object = {}) {
    await api(`/api/v1/mail/accounts/${id}${path}`, { method: 'POST', body: JSON.stringify(extra) })
    await refresh()
  }

  async function scan(id: string, dry = false) {
    const r = await api<{ status?: string; estimated_messages?: number }>(`/api/v1/mail/scans`, {
      method: 'POST',
      body: JSON.stringify({ account_id: id, folders: ['inbox'], dry_run: dry, idempotency_key: dry ? undefined : `scan-${id}-${Date.now()}` }),
    })
    setMessage(dry ? `Estimate: ${r.estimated_messages} messages` : `Scan ${r.status}`)
    await refresh()
  }

  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Inbox accounts</h1>
      <Disclaimer />
      <Card className="mb-6">
        <h2 className="font-serif text-xl">Connect a Microsoft inbox</h2>
        <p className="mt-1 text-sm text-slate">Read-only Mail.Read via OAuth. Mailbox passwords are never collected.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div>
            <Label htmlFor="label">Label</Label>
            <Input id="label" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="identity">Mock identity (local/demo)</Label>
            <select id="identity" className="h-10 w-full rounded-md border border-pine/20 bg-white px-2" value={identity} onChange={(e) => setIdentity(e.target.value)}>
              <option value="hotmail-one">hotmail-one</option>
              <option value="hotmail-two">hotmail-two</option>
              <option value="outlook-work">outlook-work</option>
            </select>
          </div>
        </div>
        <div className="mt-3">
          <Button onClick={connect}>Connect account</Button>
        </div>
        {message && <p className="mt-2 text-sm">{message}</p>}
      </Card>
      <div className="grid gap-4">
        {items.length === 0 && <p>No accounts connected.</p>}
        {items.map((a) => (
          <Card key={a.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-serif text-2xl">{a.label}</h2>
                <p className="text-sm text-slate">{a.masked_address} · {a.provider_type}</p>
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
              <Button variant="outline" onClick={() => act(a.id, '/test')}>Test connection</Button>
              <Button variant="outline" onClick={() => scan(a.id, true)}>Dry-run estimate</Button>
              <Button onClick={() => scan(a.id)}>Start historical scan</Button>
              <Button variant="outline" onClick={() => scan(a.id)}>Scan now</Button>
              <Button variant="danger" onClick={() => act(a.id, '/disconnect')}>Disconnect</Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
