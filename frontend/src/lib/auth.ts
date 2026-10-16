/**
 * JWT auth for the SPA.
 *
 * The access token lives in memory (Zustand) and is mirrored to localStorage
 * so a reload keeps the session. Storage can throw (private mode, blocked
 * site data), so every access is wrapped and the app still works in memory.
 *
 * apiFetch() adds `Authorization: Bearer <token>` to every API call,
 * including the streamed story generation, and logs out on a 401 so the
 * route guard sends the user back to /login.
 */
import { create } from 'zustand'

export const API_BASE: string = import.meta.env.VITE_API_BASE_URL || ''

const TOKEN_KEY = 'story-engine.access_token'

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeStoredToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token)
    else window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable: the in-memory token still works for this tab
  }
}

interface AuthState {
  token: string | null
  setToken: (token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: readStoredToken(),
  setToken: (token) => {
    writeStoredToken(token)
    set({ token })
  },
  logout: () => {
    writeStoredToken(null)
    set({ token: null })
  },
}))

/** fetch() against the API with the Bearer token attached; a 401 logs out. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = useAuthStore.getState().token
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const resp = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (resp.status === 401 && token) useAuthStore.getState().logout()
  return resp
}

export interface Credentials {
  email: string
  password: string
  name?: string
}

/** Log in or register; stores the access token on success, throws a readable error otherwise. */
export async function authenticate(mode: 'login' | 'register', creds: Credentials): Promise<void> {
  const body = mode === 'register' ? creds : { email: creds.email, password: creds.password }
  let resp: Response
  try {
    resp = await fetch(`${API_BASE}/api/v1/auth/${mode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error('Could not reach the server')
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail) && data.detail[0]?.msg) detail = data.detail[0].msg
    } catch {
      // keep the status text
    }
    throw new Error(detail)
  }
  const data = await resp.json()
  useAuthStore.getState().setToken(data.access_token)
}
