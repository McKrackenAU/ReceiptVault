import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { PdfPreview } from '@/components/PdfPreview'
import { api } from '@/lib/api'

type RelatedItem = {
  id: string
  filename: string
  media_type: string
  kind: string
  bytes: number
  viewer: string
}

type Preview = {
  id: string
  filename: string
  media_type: string
  viewer: string
  related: { parent: RelatedItem | null; attachments: RelatedItem[] }
  email: {
    from: string
    to: string
    cc: string
    subject: string
    date: string
    html: string
    text: string
    eml_parts: { filename: string; media_type: string; bytes: number }[]
  } | null
  text: string | null
}

export function EvidenceViewer({ evidenceId }: { evidenceId: string }) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [activeId, setActiveId] = useState(evidenceId)
  const [siblings, setSiblings] = useState<RelatedItem[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    setActiveId(evidenceId)
  }, [evidenceId])

  useEffect(() => {
    setError('')
    api<Preview>(`/api/v1/documents/${activeId}/preview`)
      .then((p) => {
        setPreview(p)
        if (p.related.attachments.length) {
          setSiblings(p.related.attachments)
        } else if (p.related.parent) {
          api<Preview>(`/api/v1/documents/${p.related.parent.id}/preview`)
            .then((parent) => setSiblings(parent.related.attachments))
            .catch(() => undefined)
        }
      })
      .catch((e) => setError(e.message || 'Preview failed'))
  }, [activeId])

  if (error) {
    return (
      <div>
        <p className="text-sm text-slate">{error}</p>
        <OriginalLinks id={activeId} />
      </div>
    )
  }
  if (!preview) return <p>Loading viewer…</p>

  const contentUrl = `/api/v1/documents/${preview.id}/content`
  const htmlUrl = `/api/v1/documents/${preview.id}/html`
  const parent = preview.related.parent
  const emailId = parent?.id || (preview.viewer === 'email' ? preview.id : evidenceId)
  const attachments = siblings.length ? siblings : preview.related.attachments

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {parent && (
          <Button variant="outline" onClick={() => setActiveId(parent.id)}>
            Back to email
          </Button>
        )}
        {parent && (
          <Link className="text-sm underline" to={`/documents/${parent.id}`}>
            Open email record
          </Link>
        )}
      </div>
      {attachments.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-sm font-semibold">Attachments</p>
          <div className="flex flex-wrap gap-2">
            <Button variant={activeId === emailId ? undefined : 'outline'} onClick={() => setActiveId(emailId)}>
              Email body
            </Button>
            {attachments.map((att) => (
              <Button key={att.id} variant={activeId === att.id ? undefined : 'outline'} onClick={() => setActiveId(att.id)}>
                {att.filename}
              </Button>
            ))}
          </div>
        </div>
      )}
      {preview.email && preview.viewer === 'email' && (
        <dl className="mb-3 grid gap-1 text-sm">
          <div>
            <span className="text-slate">From </span>
            {preview.email.from || '—'}
          </div>
          <div>
            <span className="text-slate">To </span>
            {preview.email.to || '—'}
          </div>
          {preview.email.cc ? (
            <div>
              <span className="text-slate">Cc </span>
              {preview.email.cc}
            </div>
          ) : null}
          <div>
            <span className="text-slate">Date </span>
            {preview.email.date || '—'}
          </div>
          <div className="font-semibold">{preview.email.subject || '(no subject)'}</div>
        </dl>
      )}
      <ViewerBody preview={preview} contentUrl={contentUrl} htmlUrl={htmlUrl} />
      <OriginalLinks id={preview.id} filename={preview.filename} />
    </div>
  )
}

function ViewerBody({
  preview,
  contentUrl,
  htmlUrl,
}: {
  preview: Preview
  contentUrl: string
  htmlUrl: string
}) {
  if (preview.viewer === 'pdf') {
    return <PdfPreview url={contentUrl} />
  }
  if (preview.viewer === 'image') {
    return <img src={contentUrl} alt={preview.filename} className="max-h-[70vh] w-full object-contain" />
  }
  if (preview.viewer === 'email' || preview.viewer === 'html') {
    return (
      <iframe
        title={preview.filename}
        src={htmlUrl}
        sandbox="allow-same-origin"
        referrerPolicy="no-referrer"
        className="min-h-[480px] w-full rounded-md border bg-white"
      />
    )
  }
  if (preview.viewer === 'text' && preview.text) {
    return <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-md border bg-white p-3 text-sm">{preview.text}</pre>
  }
  return (
    <p className="text-sm text-slate">
      This file type ({preview.media_type}) cannot be shown in the browser. Use Open original or Download.
    </p>
  )
}

function OriginalLinks({ id, filename }: { id: string; filename?: string }) {
  const url = `/api/v1/documents/${id}/content`
  return (
    <div className="mt-3 flex flex-wrap gap-3 text-sm">
      <a className="underline" href={url} target="_blank" rel="noreferrer">
        Open original{filename ? ` (${filename})` : ''}
      </a>
      <a className="underline" href={`${url}?disposition=attachment`}>
        Download
      </a>
    </div>
  )
}
