export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    const problem = body as { detail?: string; title?: string }
    super(problem?.detail || problem?.title || 'Request failed')
    this.status = status
    this.body = body
  }
}

let csrf = ''

export function setCsrf(token: string) {
  csrf = token
}

function mutating(method?: string) {
  return Boolean(method && !['GET', 'HEAD'].includes(method.toUpperCase()))
}

async function ensureCsrf() {
  if (csrf) return
  const response = await fetch('/api/v1/auth/csrf', { credentials: 'include' })
  if (!response.ok) return
  const data = await response.json()
  if (data.csrf) csrf = data.csrf
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (mutating(init.method)) await ensureCsrf()
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof Uint8Array) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (csrf && mutating(init.method)) headers.set('X-CSRF-Token', csrf)
  const response = await fetch(path, { ...init, headers, credentials: 'include' })
  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = { detail: text || `Request failed (${response.status})` }
  }
  if (!response.ok) throw new ApiError(response.status, data)
  return data as T
}

export async function apiBlob(path: string, init: RequestInit = {}): Promise<Response> {
  if (mutating(init.method)) await ensureCsrf()
  const headers = new Headers(init.headers)
  if (csrf && mutating(init.method)) headers.set('X-CSRF-Token', csrf)
  return fetch(path, { ...init, headers, credentials: 'include' })
}
