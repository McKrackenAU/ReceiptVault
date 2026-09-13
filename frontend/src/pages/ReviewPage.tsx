import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Disclaimer } from '@/components/Layout'
import { Badge, Card } from '@/components/ui/card'
import { api } from '@/lib/api'

type Item = { line_id: string; evidence_id: string | null; filename: string | null; description: string; suggested_status: string; decision: string }

export function ReviewPage() {
  const [items, setItems] = useState<Item[]>([])
  useEffect(() => {
    api<{ items: Item[] }>('/api/v1/review/queue').then((r) => setItems(r.items))
  }, [])
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Needs review</h1>
      <Disclaimer />
      <p className="mb-4 text-sm">Open a document and use j/k to move through the queue. Suggestions never invent a work purpose.</p>
      <div className="space-y-3">
        {items.length === 0 && <p>Review queue is empty.</p>}
        {items.map((item) => (
          <Link key={item.line_id} to={item.evidence_id ? `/documents/${item.evidence_id}` : '/documents'}>
            <Card className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{item.description}</p>
                <p className="text-sm text-slate">{item.filename}</p>
              </div>
              <Badge tone="amber">{item.suggested_status.replaceAll('_', ' ')}</Badge>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
