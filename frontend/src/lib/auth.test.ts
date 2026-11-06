import type { SupabaseClient } from '@supabase/supabase-js'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { authErrorMessage, submitCredentials } from './auth'

function fakeClient(result: object) {
  const auth = { signUp: vi.fn().mockResolvedValue(result), signInWithPassword: vi.fn(), setSession: vi.fn().mockResolvedValue(result) }
  return { client: { auth } as unknown as SupabaseClient, auth }
}
afterEach(() => vi.unstubAllGlobals())

describe('account authentication', () => {
  it('handles email confirmation without pretending the user is signed in', async () => {
    const { client, auth } = fakeClient({ data: { session: null }, error: null })
    await expect(submitCredentials(client, 'signup', ' user@example.test ', 'private-password', 'http://localhost:5173')).resolves.toBe('confirmation-required')
    expect(auth.signUp).toHaveBeenCalledWith({ email: 'user@example.test', password: 'private-password', options: { emailRedirectTo: 'http://localhost:5173' } })
    expect(auth.signInWithPassword).not.toHaveBeenCalled()
  })
  it('recognizes a real session returned by password sign-in', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: 'token', refresh_token: 'refresh' })))
    vi.stubGlobal('fetch', request)
    const { client, auth } = fakeClient({ data: { session: { access_token: 'token' } }, error: null })
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'password', 'http://localhost:5173')).resolves.toBe('signed-in')
    expect(auth.signUp).not.toHaveBeenCalled()
    expect(auth.signInWithPassword).not.toHaveBeenCalled()
    expect(auth.setSession).toHaveBeenCalledWith({ access_token: 'token', refresh_token: 'refresh' })
    expect(request.mock.calls[0][0]).toMatch(/\/api\/auth\/login$/)
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ email: 'user@example.test', password: 'password' })
  })
  it('propagates rejected credentials', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'invalid_credentials' } }), { status: 401 })))
    const { client } = fakeClient({ data: { session: null }, error: { code: 'invalid_credentials' } })
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'wrong', 'http://localhost:5173')).rejects.toMatchObject({ code: 'invalid_credentials' })
  })
  it('does not bypass the login limit if the backend refuses sign-in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'login_locked' } }), { status: 429 })))
    const { client, auth } = fakeClient({ data: { session: null }, error: null })
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'wrong', 'http://localhost:5173')).rejects.toMatchObject({ code: 'login_locked' })
    expect(auth.signInWithPassword).not.toHaveBeenCalled()
    expect(auth.setSession).not.toHaveBeenCalled()
  })
  it('does not report a malformed session response as successful authentication', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
    const { client, auth } = fakeClient({ data: { session: null }, error: null })
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'password', 'http://localhost:5173')).rejects.toMatchObject({ code: 'service_unavailable' })
    expect(auth.setSession).not.toHaveBeenCalled()
  })
  it.each(['invalid_credentials', 'email_not_confirmed', 'over_request_rate_limit', 'over_email_send_rate_limit', 'weak_password', 'login_locked', 'login_in_progress', 'backend_unavailable', 'service_unavailable', 'invalid_email'])('gives a useful message for %s', (code) => {
    expect(authErrorMessage({ code })).not.toContain('could not be completed')
  })
  it('tells a wrong password apart from an unreachable or failing server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const { client } = fakeClient({ data: { session: null }, error: null })
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'pw', 'http://x')).rejects.toMatchObject({ code: 'backend_unavailable' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"x"}', { status: 503 })))
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'pw', 'http://x')).rejects.toMatchObject({ code: 'service_unavailable' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":[]}', { status: 422 })))
    await expect(submitCredentials(client, 'signin', 'user@example.test', 'pw', 'http://x')).rejects.toMatchObject({ code: 'invalid_email' })
    expect(authErrorMessage({ code: 'invalid_credentials' })).toBe('The email or password is incorrect.')
  })
  it('does not expose arbitrary upstream error details', () => {
    expect(authErrorMessage(new Error('sensitive details'))).not.toContain('sensitive details')
  })
})
