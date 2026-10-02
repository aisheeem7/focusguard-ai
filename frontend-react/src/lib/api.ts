/**
 * Thin wrapper around the backend's REST API - a TypeScript port of
 * frontend/js/api.js. Kept byte-for-byte compatible with it: same
 * endpoints, same request/response shapes, same localStorage keys
 * (fg_token/fg_user_id/fg_username), so a session started here is
 * recognized by the existing plain-HTML dashboard (app.html) and vice
 * versa. The backend itself is untouched.
 */

const BACKEND_URL =
  (window as { FOCUS_GROVE_BACKEND_URL?: string }).FOCUS_GROVE_BACKEND_URL ??
  'http://127.0.0.1:8000'

interface Session {
  api_token: string
  user_id: number
  username?: string
}

export const Auth = {
  getToken(): string | null {
    return localStorage.getItem('fg_token')
  },
  getUserId(): number | null {
    const id = localStorage.getItem('fg_user_id')
    return id ? parseInt(id, 10) : null
  },
  getUsername(): string | null {
    return localStorage.getItem('fg_username')
  },
  getAvatarUrl(): string | null {
    return localStorage.getItem('fg_avatar_url')
  },
  setSession({ api_token, user_id, username }: Session) {
    localStorage.setItem('fg_token', api_token)
    localStorage.setItem('fg_user_id', String(user_id))
    if (username) localStorage.setItem('fg_username', username)
  },
  setProfile({ username, avatar_url }: { username: string; avatar_url: string | null }) {
    localStorage.setItem('fg_username', username)
    if (avatar_url) localStorage.setItem('fg_avatar_url', avatar_url)
    else localStorage.removeItem('fg_avatar_url')
  },
  clearSession() {
    localStorage.removeItem('fg_token')
    localStorage.removeItem('fg_user_id')
    localStorage.removeItem('fg_username')
    localStorage.removeItem('fg_avatar_url')
  },
  isLoggedIn(): boolean {
    return !!this.getToken()
  },
}

class ApiError extends Error {
  status?: number
}

async function apiRequest<T>(
  path: string,
  { method = 'GET', body = null, auth = true }: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = Auth.getToken()
    if (!token) throw new Error('Not logged in')
    headers.Authorization = `Bearer ${token}`
  }
  const resp = await fetch(`${BACKEND_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const errBody = await resp.json()
      if (errBody.detail) detail = errBody.detail
    } catch {
      /* response wasn't JSON */
    }
    const err = new ApiError(detail)
    err.status = resp.status
    throw err
  }
  return resp.json()
}

interface Profile {
  id: number
  username: string
  avatar_url: string | null
  break_interval_minutes: number
}

export const Api = {
  async register(username: string, password: string) {
    const data = await apiRequest<Session>('/users/register', {
      method: 'POST',
      body: { username, password },
      auth: false,
    })
    Auth.setSession(data)
    return data
  },
  async login(username: string, password: string) {
    const data = await apiRequest<Session>('/users/login', {
      method: 'POST',
      body: { username, password },
      auth: false,
    })
    Auth.setSession(data)
    return data
  },
  async getMe() {
    const data = await apiRequest<Profile>('/users/me')
    Auth.setProfile(data)
    return data
  },
  async updateUsername(username: string) {
    const data = await apiRequest<Profile>('/users/me', { method: 'PATCH', body: { username } })
    Auth.setProfile(data)
    return data
  },
  async updateBreakInterval(minutes: number) {
    const data = await apiRequest<Profile>('/users/me', {
      method: 'PATCH',
      body: { break_interval_minutes: minutes },
    })
    Auth.setProfile(data)
    return data
  },
  async uploadAvatar(file: File) {
    const token = Auth.getToken()
    if (!token) throw new Error('Not logged in')
    const form = new FormData()
    form.append('file', file)
    const resp = await fetch(`${BACKEND_URL}/users/me/avatar`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    })
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`
      try {
        const errBody = await resp.json()
        if (errBody.detail) detail = errBody.detail
      } catch {
        /* response wasn't JSON */
      }
      const err = new ApiError(detail)
      err.status = resp.status
      throw err
    }
    const data: Profile = await resp.json()
    Auth.setProfile(data)
    return data
  },
}

export { BACKEND_URL }
