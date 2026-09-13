import { api, apiBlob } from './api'

export type UploadProgress = {
  sent: number
  total: number
  speed: number
  eta: number
}

export async function uploadChunked(
  file: File,
  onProgress: (p: UploadProgress) => void,
  signal?: { paused: boolean },
) {
  const buffer = await file.arrayBuffer()
  const digest = await sha256Hex(buffer)
  const session = await api<{ session_id: string; chunk_size: number }>('/api/v1/transfers/uploads', {
    method: 'POST',
    body: JSON.stringify({ filename: file.name, size: file.size, mime_hint: file.type, sha256: digest }),
  })
  const chunkSize = session.chunk_size
  const parts = file.size === 0 ? 0 : Math.ceil(file.size / chunkSize)
  const started = Date.now()
  let sent = 0
  for (let index = 0; index < parts; index++) {
    while (signal?.paused) await new Promise((r) => setTimeout(r, 200))
    const start = index * chunkSize
    const chunk = buffer.slice(start, start + chunkSize)
    const chunkHash = await sha256Hex(chunk)
    await retry(async () => {
      const res = await apiBlob(`/api/v1/transfers/uploads/${session.session_id}/chunks/${index}`, {
        method: 'PUT',
        headers: { 'X-Chunk-SHA256': chunkHash, 'Content-Type': 'application/octet-stream' },
        body: new Uint8Array(chunk),
      })
      if (!res.ok) throw new Error(await res.text())
    })
    sent += chunk.byteLength
    const elapsed = (Date.now() - started) / 1000
    const speed = sent / Math.max(elapsed, 0.1)
    onProgress({ sent, total: file.size, speed, eta: (file.size - sent) / speed })
  }
  return api<{ evidence_id: string }>(`/api/v1/transfers/uploads/${session.session_id}/finalize`, { method: 'POST' })
}

export async function downloadResumable(url: string, expectedSize?: number) {
  const chunks: Uint8Array[] = []
  let offset = 0
  while (expectedSize === undefined || offset < expectedSize) {
    const end = expectedSize ? Math.min(offset + 16 * 1024 * 1024 - 1, expectedSize - 1) : offset + 16 * 1024 * 1024 - 1
    const res = await fetch(url, { credentials: 'include', headers: { Range: `bytes=${offset}-${end}` } })
    if (res.status !== 206 && res.status !== 200) throw new Error('download failed')
    const buf = new Uint8Array(await res.arrayBuffer())
    chunks.push(buf)
    offset += buf.byteLength
    const totalHeader = res.headers.get('content-range')
    if (res.status === 200) break
    if (totalHeader) {
      const total = Number(totalHeader.split('/')[1])
      if (offset >= total) break
    } else if (buf.byteLength === 0) break
    if (res.status === 206 && buf.byteLength === 0) break
  }
  const size = chunks.reduce((n, c) => n + c.byteLength, 0)
  const out = new Uint8Array(size)
  let pos = 0
  for (const c of chunks) {
    out.set(c, pos)
    pos += c.byteLength
  }
  return out
}

async function sha256Hex(data: ArrayBuffer) {
  const hash = await crypto.subtle.digest('SHA-256', data)
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function retry(fn: () => Promise<void>, attempts = 4) {
  let last: unknown
  for (let i = 0; i < attempts; i++) {
    try {
      await fn()
      return
    } catch (err) {
      last = err
      await new Promise((r) => setTimeout(r, 400 * 2 ** i))
    }
  }
  throw last
}
