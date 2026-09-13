import { useEffect, useState } from 'react'
import { Disclaimer } from '@/components/Layout'
import { Badge, Card } from '@/components/ui/card'
import { api } from '@/lib/api'

type Dash = {
  financial_year: string | null
  accounts: { label: string; masked_address: string; scan_status: string; emails_examined: number; candidates_found: number; documents_imported: number; failures: number }[]
  active_jobs: { id: string; kind: string; status: string; progress: number }[]
  receipts_found: number
  status_counts: Record<string, number>
  unresolved_reviews: number
  totals_by_year: Record<string, number>
  disclaimer: string
}

export function DashboardPage() {
  const [data, setData] = useState<Dash | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api<Dash>('/api/v1/dashboard').then(setData).catch((e) => setError(e.message))
  }, [])
  if (error) return <p role="alert">{error}</p>
  if (!data) return <p>Loading dashboard…</p>
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Audit workspace</h1>
      <Disclaimer />
      <p className="mb-4 text-sm text-slate">{data.disclaimer}</p>
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <p className="text-sm text-slate">Receipts / invoices found</p>
          <p className="font-serif text-3xl">{data.receipts_found}</p>
        </Card>
        <Card>
          <p className="text-sm text-slate">Unresolved reviews</p>
          <p className="font-serif text-3xl">{data.unresolved_reviews}</p>
        </Card>
        <Card>
          <p className="text-sm text-slate">Active jobs</p>
          <p className="font-serif text-3xl">{data.active_jobs.length}</p>
        </Card>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Card>
          <h2 className="font-serif text-xl">Inbox health</h2>
          {data.accounts.length === 0 && <p className="mt-2 text-sm">No mailboxes connected yet.</p>}
          <ul className="mt-3 space-y-2">
            {data.accounts.map((a) => (
              <li key={a.label} className="flex justify-between gap-2 text-sm">
                <span>
                  {a.label} · {a.masked_address}
                </span>
                <Badge tone={a.scan_status === 'idle' ? 'moss' : 'amber'}>{a.scan_status}</Badge>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <h2 className="font-serif text-xl">Review labels (not deductions)</h2>
          <ul className="mt-3 space-y-1 text-sm">
            <li>Potentially claimable: {data.status_counts.potentially_claimable || 0}</li>
            <li>Needs review: {data.status_counts.needs_review || 0}</li>
            <li>Likely private: {data.status_counts.likely_private || 0}</li>
          </ul>
          <h3 className="mt-4 font-semibold">Extracted totals by FY</h3>
          <ul className="text-sm">
            {Object.entries(data.totals_by_year).map(([year, total]) => (
              <li key={year}>
                {year}: {total.toFixed(2)} (review total, not a deduction)
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
