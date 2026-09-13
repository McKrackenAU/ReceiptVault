import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

export function PdfPreview({ url }: { url: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [scale, setScale] = useState(1.1)
  const [rotation, setRotation] = useState(0)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('Loading PDF…')

  useEffect(() => {
    let cancelled = false
    async function draw() {
      const pdfjs = await import('pdfjs-dist')
      pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()
      const pdf = await pdfjs.getDocument({ url, withCredentials: true }).promise
      if (cancelled) return
      setPages(pdf.numPages)
      const pg = await pdf.getPage(page)
      const viewport = pg.getViewport({ scale, rotation })
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      canvas.width = viewport.width
      canvas.height = viewport.height
      await pg.render({ canvasContext: ctx, viewport, canvas }).promise
      if (query) {
        const content = await pg.getTextContent()
        const hits = content.items.filter((item) => 'str' in item && String(item.str).toLowerCase().includes(query.toLowerCase()))
        setStatus(hits.length ? `${hits.length} hits on this page` : 'No hits on this page')
      } else {
        setStatus(`Page ${page} of ${pdf.numPages}`)
      }
    }
    draw().catch((e) => setStatus(e.message || 'PDF preview failed'))
    return () => {
      cancelled = true
    }
  }, [url, page, scale, rotation, query])

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setPage((p) => Math.max(1, p - 1))} aria-label="Previous page">Prev</Button>
        <Button variant="outline" onClick={() => setPage((p) => Math.min(pages, p + 1))} aria-label="Next page">Next</Button>
        <Button variant="outline" onClick={() => setScale((s) => s + 0.2)} aria-label="Zoom in">Zoom +</Button>
        <Button variant="outline" onClick={() => setScale((s) => Math.max(0.4, s - 0.2))} aria-label="Zoom out">Zoom −</Button>
        <Button variant="outline" onClick={() => setRotation((r) => (r + 90) % 360)} aria-label="Rotate">Rotate</Button>
        <Button variant="outline" onClick={() => window.print()}>Print</Button>
        <input className="h-10 rounded-md border px-2 text-sm" placeholder="Find in page" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search PDF text" />
      </div>
      <p className="mb-2 text-sm text-slate" aria-live="polite">{status}</p>
      <div className="overflow-auto rounded-md border bg-white">
        <canvas ref={canvasRef} className="max-w-full" />
      </div>
    </div>
  )
}
