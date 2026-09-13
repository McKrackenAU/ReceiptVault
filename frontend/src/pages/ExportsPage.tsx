import { useEffect, useState } from 'react'
import { Disclaimer } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { api } from '@/lib/api'

type Exp = { id: string; financial_year: string | null; created_at: string; package_id: string | null; status: string; sha256: string | null }

export function ExportsPage() {
  const [year, setYear] = useState('2024-25')
  const [items, setItems] = useState<Exp[]>([])
  async function load() {
    setItems((await api<{ items: Exp[] }>('/api/v1/exports')).items)
  }
  useEffect(() => {
    load()
  }, [])
  async function create() {
    await api('/api/v1/exports', { method: 'POST', body: JSON.stringify({ financial_year: year, idempotency_key: `exp-${year}-${Date.now()}` }) })
    await load()
  }
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Exports</h1>
      <Disclaimer />
      <Card className="mb-4">
        <Label htmlFor="fy">Financial year</Label>
        <Input id="fy" value={year} onChange={(e) => setYear(e.target.value)} />
        <Button className="mt-3" onClick={create}>Create export package</Button>
      </Card>
      {items.map((item) => (
        <Card key={item.id} className="mb-2">
          <p>{item.financial_year} · {item.status} · {new Date(item.created_at).toLocaleString()}</p>
          <p className="text-xs break-all">SHA-256 {item.sha256}</p>
          {item.package_id && (
            <a className="mt-2 inline-block underline" href={`/api/v1/transfers/packages/${item.package_id}/download`}>
              Download ZIP (originals + registers + manifest)
            </a>
          )}
        </Card>
      ))}
    </div>
  )
}
