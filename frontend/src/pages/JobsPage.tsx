import { useEffect, useState } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'

type Job = { id: string; kind: string; status: string; progress: number; message: string | null; created_at: string }

export function JobsPage() {
  const [items, setItems] = useState<Job[]>([])
  async function refresh() {
    setItems((await api<{ items: Job[] }>('/api/v1/mail/jobs')).items)
  }
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [])
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Scan jobs</h1>
      <p className="mb-4 text-sm text-slate">Jobs continue after the browser closes. Pause/cancel writes a durable flag and the next page checkpoint is kept.</p>
      <div className="space-y-3">
        {items.length === 0 && <p>No jobs yet.</p>}
        {items.map((j) => (
          <Card key={j.id} className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-semibold">{j.kind}</p>
              <p className="text-sm text-slate">{j.status} · {j.progress}% · {new Date(j.created_at).toLocaleString()}</p>
              {j.message && <p className="text-sm">{j.message}</p>}
            </div>
            <Button variant="outline" onClick={() => api(`/api/v1/mail/scans/${j.id}/cancel`, { method: 'POST' }).then(refresh)}>
              Cancel / pause
            </Button>
          </Card>
        ))}
      </div>
    </div>
  )
}
