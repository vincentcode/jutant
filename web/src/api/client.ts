// One fetch wrapper: sends the session cookie, parses errors, and sends the user to /login when
// the session has ended.

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `API error ${status}`)
    this.status = status
    this.detail = detail
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  // A file upload (FormData) sets its own multipart content type.
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...init, headers })
  if (response.status === 401 && window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : body
    throw new ApiError(response.status, detail)
  }
  return response
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init)
  return (await response.json()) as T
}
