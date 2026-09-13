import { useEffect, useState } from 'react'
import { Card } from '@/components/ui/card'
import { api } from '@/lib/api'

type Ev = { id: string; created_at: string; username: string | null; event_type: string; target_id: string | null; success: boolean; ip: string | null }

export function AuditPage() {
  const [items, setItems] = useState<Ev[]>([])
  useEffect(() => {
    api<{ items: Ev[] }>('/api/v1/audit').then((r) => setItems(r.items))
  }, [])
  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Audit log</h1>
      <p className="mb-3 text-sm">Append-only from the web UI. <a className="underline" href="/api/v1/audit.csv">Download CSV</a></p>
      <Card className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th>Time (UTC)</th>
              <th>User</th>
              <th>Event</th>
              <th>Target</th>
              <th>Result</th>
              <th>IP</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id} className="border-t">
                <td>{new Date(e.created_at).toISOString()}</td>
                <td>{e.username}</td>
                <td>{e.event_type}</td>
                <td>{e.target_id}</td>
                <td>{e.success ? 'success' : 'failure'}</td>
                <td>{e.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
