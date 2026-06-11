/**
 * Cliente HTTP del portal.
 *
 * - Rutas relativas `/api/v1/...` (proxy de Vite en dev). Si está definida
 *   `VITE_API_BASE_URL` se usa como base absoluta.
 * - Agrega `Authorization: Bearer <access_token>`.
 * - Ante 401: intenta UNA vez `POST /auth/refresh` (single-flight) y reintenta;
 *   si el refresh falla, dispara el logout global y redirige a /login.
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
const API_V1 = `${API_BASE}/api/v1`

const ACCESS_KEY = 'koala.access_token'
const REFRESH_KEY = 'koala.refresh_token'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/** Lo registra el AuthProvider para reaccionar a sesiones expiradas. */
let onSessionExpired: (() => void) | null = null
export function registerSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn
}

export type QueryParams = Record<string, string | number | boolean | undefined | null>

function buildUrl(path: string, params?: QueryParams): string {
  const url = `${API_V1}${path}`
  if (!params) return url
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    qs.set(key, String(value))
  }
  const s = qs.toString()
  return s ? `${url}?${s}` : url
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `Error ${res.status}`
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') detail = body.detail
    else if (Array.isArray(body?.detail) && body.detail[0]?.msg) detail = String(body.detail[0].msg)
  } catch {
    /* cuerpo no JSON */
  }
  return new ApiError(res.status, detail)
}

// Refresh single-flight: si varias requests reciben 401 a la vez, un solo refresh.
let refreshPromise: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = tokenStore.refresh
      if (!refresh) return false
      try {
        const res = await fetch(`${API_V1}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refresh }),
        })
        if (!res.ok) return false
        const data = await res.json()
        tokenStore.set(data.access_token, data.refresh_token)
        return true
      } catch {
        return false
      }
    })().finally(() => {
      setTimeout(() => {
        refreshPromise = null
      }, 0)
    })
  }
  return refreshPromise
}

interface RequestOptions {
  method?: string
  body?: unknown
  params?: QueryParams
  /** No agrega Authorization ni intenta refresh (login). */
  skipAuth?: boolean
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, params, skipAuth = false } = options

  const doFetch = () => {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (!skipAuth && tokenStore.access) headers['Authorization'] = `Bearer ${tokenStore.access}`
    return fetch(buildUrl(path, params), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  }

  let res = await doFetch()

  if (res.status === 401 && !skipAuth) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      res = await doFetch()
    }
    if (res.status === 401) {
      tokenStore.clear()
      onSessionExpired?.()
      throw await parseError(res)
    }
  }

  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
