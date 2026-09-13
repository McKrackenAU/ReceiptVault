export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super((body as { detail?: string })?.detail || 'Request failed')
    this.status = status
    this.body = body
  }
}

let csrf = ''

export function setCsrf(token: string) {
  csrf = token
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof Uint8Array) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (csrf && init.method && !['GET', 'HEAD'].includes(init.method.toUpperCase())) {
    headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(path, { ...init, headers, credentials: 'include' })
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) throw new ApiError(response.status, data)
  return data as T
}

export async function apiBlob(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (csrf && init.method && !['GET', 'HEAD'].includes(init.method.toUpperCase())) {
    headers.set('X-CSRF-Token', csrf)
  }
  return fetch(path, { ...init, headers, credentials: 'include' })
}
