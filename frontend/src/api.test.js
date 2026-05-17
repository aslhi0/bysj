import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  apiFetch,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from './api'

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('api token storage', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('stores, reads and clears access and refresh tokens', () => {
    setTokens({ access: 'access-token', refresh: 'refresh-token' })

    expect(sessionStorage.getItem(ACCESS_TOKEN_KEY)).toBe('access-token')
    expect(sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-token')
    expect(getAccessToken()).toBe('access-token')
    expect(getRefreshToken()).toBe('refresh-token')

    clearTokens()

    expect(getAccessToken()).toBe('')
    expect(getRefreshToken()).toBe('')
  })
})

describe('apiFetch authentication flow', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.restoreAllMocks()
  })

  it('adds the bearer token to authenticated requests', async () => {
    setTokens({ access: 'access-token' })
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await apiFetch('/api/projects/')

    expect(res.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers.get('Authorization')).toBe('Bearer access-token')
  })

  it('refreshes an expired access token and retries the original request once', async () => {
    setTokens({ access: 'expired-token', refresh: 'refresh-token' })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ access: 'new-access-token' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await apiFetch('/api/cases/')

    expect(res.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/token/refresh/')
    expect(getAccessToken()).toBe('new-access-token')
    expect(fetchMock.mock.calls[2][1].headers.get('Authorization')).toBe('Bearer new-access-token')
  })

  it('returns the original 401 response when refresh is unavailable', async () => {
    setTokens({ access: 'expired-token' })
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'expired' }, { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    const res = await apiFetch('/api/cases/')

    expect(res.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
