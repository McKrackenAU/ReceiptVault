import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Disclaimer } from '@/components/Layout'
import { Button } from '@/components/ui/button'
import { Badge, Card } from '@/components/ui/card'
import { Input, Label, Textarea } from '@/components/ui/input'
import { api } from '@/lib/api'
import { PdfPreview } from '@/components/PdfPreview'

type Detail = {
  id: string
  filename: string
  sha256: string
  bytes: number
  media_type: string
  financial_year: string | null
  fy_source: string | null
  processing_history: unknown[]
  extracted: { raw_text: string | null; validation_flags: string[]; total: string | null; disclaimer: string; engine_version: string | null } | null
  fields: { id: string; name: string; raw: string | null; current: string | null; confidence: string | null }[]
  line_items: {
    id: string
    raw_description: string
    suggested_status: string
    suggested_category: string | null
    explanation: { why?: string; missing_facts?: string[]; disclaimer?: string }
    paid_personally: string
    reimbursed: string
    work_related: string
    work_use_percent: number
    work_purpose: string | null
    decision: string
    adviser_note: string | null
    line_total: string | null
  }[]
}

export function DocumentDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [doc, setDoc] = useState<Detail | null>(null)
  const [confirm, setConfirm] = useState('')
  const [queue, setQueue] = useState<string[]>([])

  async function load() {
    const data = await api<Detail>(`/api/v1/documents/${id}`)
    setDoc(data)
    const q = await api<{ items: { evidence_id: string }[] }>('/api/v1/review/queue')
    setQueue(q.items.map((i) => i.evidence_id).filter(Boolean) as string[])
  }
  useEffect(() => {
    load()
  }, [id])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!id || queue.length === 0) return
      const idx = queue.indexOf(id)
      if (e.key === 'j' && idx < queue.length - 1) navigate(`/documents/${queue[idx + 1]}`)
      if (e.key === 'k' && idx > 0) navigate(`/documents/${queue[idx - 1]}`)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [id, queue, navigate])

  if (!doc) return <p>Loading document…</p>
  const previewUrl = `/api/v1/documents/${doc.id}/content`

  return (
    <div>
      <h1 className="font-serif text-3xl text-pine">{doc.filename}</h1>
      <Disclaimer />
      <p className="mb-3 text-sm text-slate">FY {doc.financial_year || 'unassigned'} ({doc.fy_source || 'none'}) · SHA-256 {doc.sha256} · {doc.bytes} bytes · keys j/k move the review queue</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="min-h-[480px]">
          {doc.media_type === 'application/pdf' ? (
            <PdfPreview url={previewUrl} />
          ) : doc.media_type.startsWith('image/') ? (
            <img src={previewUrl} alt={doc.filename} className="max-h-[70vh] w-full object-contain" />
          ) : (
            <iframe title="Sanitized email" srcDoc="" className="hidden" />
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <a className="underline" href={previewUrl}>Open original</a>
            <a className="underline" href={`${previewUrl}?disposition=attachment`}>Download original</a>
          </div>
        </Card>
        <div className="space-y-4">
          <Card>
            <h2 className="font-serif text-xl">Extracted fields</h2>
            <p className="text-xs text-slate">Edits never overwrite the raw extraction.</p>
            {doc.fields.map((f) => (
              <div key={f.id} className="mt-2">
                <Label htmlFor={f.id}>{f.name} (raw: {f.raw || '—'})</Label>
                <Input
                  id={f.id}
                  defaultValue={f.current || ''}
                  onBlur={(e) => {
                    if (e.target.value !== (f.current || '')) {
                      api(`/api/v1/documents/${doc.id}/fields/${f.id}`, { method: 'PATCH', body: JSON.stringify({ value: e.target.value }) })
                    }
                  }}
                />
              </div>
            ))}
            {doc.extracted && (
              <p className="mt-3 text-sm">Flags: {doc.extracted.validation_flags.join(', ') || 'none'} · engine {doc.extracted.engine_version}</p>
            )}
          </Card>
          {doc.line_items.map((line) => (
            <Card key={line.id}>
              <div className="flex justify-between gap-2">
                <h3 className="font-semibold">{line.raw_description}</h3>
                <StatusBadge status={line.suggested_status} />
              </div>
              <p className="text-sm">Suggested category: {line.suggested_category} · {line.line_total}</p>
              <p className="mt-2 text-sm">{line.explanation.why}</p>
              <p className="text-xs text-slate">Missing facts: {(line.explanation.missing_facts || []).join(', ') || 'none'}</p>
              <p className="disclaimer mt-2">{line.explanation.disclaimer}</p>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <SelectField label="Paid personally" value={line.paid_personally} options={['yes', 'no', 'unknown']} onChange={(v) => patchLine(line.id, { paid_personally: v })} />
                <SelectField label="Reimbursed" value={line.reimbursed} options={['yes', 'no', 'unknown']} onChange={(v) => patchLine(line.id, { reimbursed: v })} />
                <SelectField label="Work related" value={line.work_related} options={['yes', 'no', 'partial', 'unknown']} onChange={(v) => patchLine(line.id, { work_related: v })} />
                <SelectField label="Decision" value={line.decision} options={['include', 'exclude', 'undecided']} onChange={(v) => patchLine(line.id, { decision: v })} />
              </div>
              <Label className="mt-2">Work-use % (0–100)</Label>
              <Input type="number" min={0} max={100} defaultValue={line.work_use_percent} onBlur={(e) => patchLine(line.id, { work_use_percent: Number(e.target.value) })} />
              <Label className="mt-2">Work purpose (you must enter this — the app will not invent it)</Label>
              <Textarea defaultValue={line.work_purpose || ''} onBlur={(e) => patchLine(line.id, { work_purpose: e.target.value })} />
              <Label className="mt-2">Accountant / adviser note</Label>
              <Textarea defaultValue={line.adviser_note || ''} onBlur={(e) => patchLine(line.id, { adviser_note: e.target.value })} />
            </Card>
          ))}
          <Card>
            <h2 className="font-serif text-xl">Soft-delete original</h2>
            <p className="text-sm">Type the exact filename {doc.filename} to confirm. Retention applies before permanent purge.</p>
            <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            <Button className="mt-2" variant="danger" onClick={() => api(`/api/v1/documents/${doc.id}/delete`, { method: 'POST', body: JSON.stringify({ confirmation: confirm }) }).then(() => navigate('/documents'))}>
              Delete evidence
            </Button>
          </Card>
        </div>
      </div>
    </div>
  )
}

function patchLine(id: string, body: object) {
  return api(`/api/v1/review/lines/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <div>
      <Label>{label}</Label>
      <select className="h-10 w-full rounded-md border bg-white px-2" defaultValue={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === 'potentially_claimable' ? 'moss' : status === 'likely_private' ? 'slate' : 'amber'
  const label = status.replaceAll('_', ' ')
  const icon = status === 'potentially_claimable' ? '✓' : status === 'likely_private' ? '✕' : '?'
  return <Badge tone={tone}>{icon} {label}</Badge>
}
