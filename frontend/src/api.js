export const ACCESS_TOKEN_KEY = 'autotest_access_token'
export const REFRESH_TOKEN_KEY = 'autotest_refresh_token'

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || ''
}

export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem(ACCESS_TOKEN_KEY, access)
  if (refresh) localStorage.setItem(REFRESH_TOKEN_KEY, refresh)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY) || ''
}

let refreshing = null

async function refreshAccessToken() {
  if (refreshing) return refreshing
  const refresh = getRefreshToken()
  if (!refresh) return null
  refreshing = (async () => {
    const res = await fetch('/api/auth/token/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) return null
    if (data.access) setTokens({ access: data.access })
    return data.access || null
  })()
  try {
    return await refreshing
  } finally {
    refreshing = null
  }
}

export async function apiFetch(input, init = {}) {
  const token = getAccessToken()
  const apiKey = import.meta.env.VITE_API_KEY
  const headers = new Headers(init.headers || {})
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (apiKey) headers.set('X-API-Key', apiKey)
  const res = await fetch(input, { ...init, headers })
  if (res.status !== 401) return res
  const newAccess = await refreshAccessToken()
  if (!newAccess) return res
  const headers2 = new Headers(init.headers || {})
  headers2.set('Authorization', `Bearer ${newAccess}`)
  if (apiKey) headers2.set('X-API-Key', apiKey)
  return fetch(input, { ...init, headers: headers2 })
}
