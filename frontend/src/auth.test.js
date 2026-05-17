import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './api'
import { isAdminUser, loadCurrentUser, resetCurrentUserCache } from './auth'

vi.mock('./api', () => ({
  apiFetch: vi.fn(),
}))

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('current user cache', () => {
  beforeEach(() => {
    apiFetch.mockReset()
    resetCurrentUserCache()
  })

  it('loads the current user once and reuses the cached value', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ username: 'admin', is_staff: true }))

    const first = await loadCurrentUser()
    const second = await loadCurrentUser()

    expect(first).toEqual({ username: 'admin', is_staff: true })
    expect(second).toBe(first)
    expect(isAdminUser.value).toBe(true)
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith('/api/auth/me/')
  })

  it('supports a forced reload when permissions may have changed', async () => {
    apiFetch
      .mockResolvedValueOnce(jsonResponse({ username: 'tester', is_staff: false }))
      .mockResolvedValueOnce(jsonResponse({ username: 'tester', is_staff: true }))

    await loadCurrentUser()
    const reloaded = await loadCurrentUser(true)

    expect(reloaded).toEqual({ username: 'tester', is_staff: true })
    expect(isAdminUser.value).toBe(true)
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  it('returns null and clears admin status when the user endpoint fails', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, { status: 401 }))

    const user = await loadCurrentUser()

    expect(user).toBeNull()
    expect(isAdminUser.value).toBe(false)
  })
})
