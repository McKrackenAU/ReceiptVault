import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'

type Group = { id: string; kind: string; canonical_evidence_id: string | null; members: { id: string; filename: string; sha256: string; reason: string }[] }

export function DuplicatesPage() {
  const [items, setItems] = useState<Group[]>([])
  async function load() {
    setItems((await api<{ items: Group[] }>('/api/v1/duplicates')).items)
  }
  useEffect(() => {
    load()
  }, [])
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Duplicates</h1>
      <p className="mb-4 text-sm text-slate">Exact (SHA-256) and probable (merchant + number + date + total) matches. Nothing is destroyed automatically — pick a canonical record.</p>
      {items.length === 0 && <p>No duplicate groups.</p>}
      {items.map((g) => (
        <Card key={g.id} className="mb-3">
          <p className="font-semibold">{g.kind} group</p>
          <ul className="mt-2 space-y-1 text-sm">
            {g.members.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>{m.filename} · {m.sha256.slice(0, 12)} · {m.reason}</span>
                <Button variant="outline" onClick={() => api(`/api/v1/duplicates/${g.id}/canonical`, { method: 'POST', body: JSON.stringify({ evidence_id: m.id }) }).then(load)}>
                  {g.canonical_evidence_id === m.id ? 'Canonical' : 'Make canonical'}
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  )
}
