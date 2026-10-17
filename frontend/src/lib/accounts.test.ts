import { afterEach, describe, expect, it, vi } from 'vitest'
import { accountRequest } from './accounts'

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }))
vi.mock('./supabase', () => ({ supabase: { auth: { getSession } } }))

afterEach(() => { vi.unstubAllGlobals(); vi.resetAllMocks() })

describe('authenticated application requests', () => {
  it('uses the SDK current token and never sends the refresh token', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'current-access', refresh_token: 'private-refresh' } }, error: null })
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ id: 'user' }))
    vi.stubGlobal('fetch', fetchMock)
    await accountRequest('/api/me')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/me$/), expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer current-access' }),
    }))
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain('private-refresh')
  })
  it('sends only the display name when saving, with no client-controlled owner', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'token' } }, error: null })
    const fetchMock = vi.fn().mockResolvedValue(Response.json({}))
    vi.stubGlobal('fetch', fetchMock)
    await accountRequest('/api/profile', { displayName: ' Alice ' })
    expect(fetchMock).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ method: 'PUT', body: '{"display_name":"Alice"}' }))
  })
  it('does not send an anonymous request after the session ends', async () => {
    getSession.mockResolvedValue({ data: { session: null }, error: null })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(accountRequest('/api/me')).rejects.toThrow('session has ended')
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('explains an expired or rejected token', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'token' } }, error: null })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })))
    await expect(accountRequest('/api/me')).rejects.toThrow('invalid or expired')
  })
  it('shows an actionable backend configuration error', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'token' } }, error: null })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'Supabase is not configured on the backend.' }, { status: 503 })))
    await expect(accountRequest('/api/me')).rejects.toThrow('not configured on the backend')
  })
})
