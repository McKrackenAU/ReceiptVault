import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Disclaimer } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { api } from '@/lib/api'
import { uploadChunked } from '@/lib/upload'

type Doc = { id: string; filename: string; financial_year: string | null; merchant: string | null; total: string | null; currency: string | null; kind: string; media_type: string }

export function DocumentsPage() {
  const [items, setItems] = useState<Doc[]>([])
  const [q, setQ] = useState('')
  const [year, setYear] = useState('')
  const [progress, setProgress] = useState('')
  const [folders, setFolders] = useState<{ path: string; label: string }[]>([])
  const [folder, setFolder] = useState('')

  async function load() {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (year) params.set('financial_year', year)
    if (folder) params.set('folder', folder)
    const r = await api<{ items: Doc[] }>(`/api/v1/documents?${params}`)
    setItems(r.items)
    setFolders((await api<{ items: { path: string; label: string }[] }>('/api/v1/folders')).items)
  }
  useEffect(() => {
    load().catch(() => undefined)
  }, [])

  async function onFile(file: File | undefined) {
    if (!file) return
    if (file.size > 16 * 1024 * 1024) {
      await uploadChunked(file, (p) => setProgress(`${Math.round((p.sent / p.total) * 100)}% · ${(p.speed / 1024 / 1024).toFixed(1)} MiB/s`))
    } else {
      const body = new FormData()
      body.append('file', file)
      await api('/api/v1/documents/upload', { method: 'POST', body })
    }
    setProgress('Uploaded')
    await load()
  }

  async function packageFolder() {
    if (!folder) return
    const r = await api<{ package_id: string }>(`/api/v1/transfers/packages`, {
      method: 'POST',
      body: JSON.stringify({ folder_path: folder }),
    })
    window.location.href = `/api/v1/transfers/packages/${r.package_id}/download`
  }

  return (
    <div>
      <h1 className="font-serif text-4xl text-pine">Documents</h1>
      <Disclaimer />
      <Card className="mb-4 grid gap-3 md:grid-cols-4">
        <div className="md:col-span-2">
          <Label htmlFor="q">Search extracted text and metadata</Label>
          <Input id="q" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="year">Financial year</Label>
          <Input id="year" placeholder="2024-25" value={year} onChange={(e) => setYear(e.target.value)} />
        </div>
        <div className="flex items-end">
          <Button onClick={load}>Apply filters</Button>
        </div>
        <div className="md:col-span-2">
          <Label htmlFor="folder">Virtual folder</Label>
          <select id="folder" className="h-10 w-full rounded-md border bg-white px-2" value={folder} onChange={(e) => setFolder(e.target.value)}>
            <option value="">All</option>
            {folders.map((f) => (
              <option key={f.path} value={f.path}>{f.path}</option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="file">Upload (chunked over 16 MiB)</Label>
          <Input id="file" type="file" onChange={(e) => onFile(e.target.files?.[0])} />
          {progress && <p className="text-sm">{progress}</p>}
        </div>
        <div className="flex items-end">
          <Button variant="outline" onClick={packageFolder}>Download folder package</Button>
        </div>
      </Card>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.length === 0 && <p>No documents yet. Connect an inbox or upload a file.</p>}
        {items.map((d) => (
          <Link key={d.id} to={`/documents/${d.id}`}>
            <Card>
              <p className="font-semibold">{d.filename}</p>
              <p className="text-sm text-slate">{d.merchant || 'Unknown supplier'} · {d.financial_year || 'FY unassigned'}</p>
              <p className="text-sm">{d.total ? `${d.currency} ${d.total}` : 'No total yet'} · {d.kind}</p>
              <p className="mt-1 text-xs text-slate">Open to view the email, PDF, image, or attachment</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
