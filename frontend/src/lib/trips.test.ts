import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTrip, invitationToken, issueInvitation, joinTrip, listTrips, readPendingInvitation, rememberInvitation, revokeInvitation } from './trips'

const { request } = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('./http', () => ({ authenticatedRequest: request }))
afterEach(() => { vi.resetAllMocks(); vi.unstubAllGlobals() })
const token = 'ab'.repeat(32)

describe('trip requests', () => {
  it('sends trip fields without a client-controlled owner or role', async () => {
    request.mockResolvedValue({ id: 'trip' })
    await createTrip('  Our trip  ', '  Together  ')
    expect(request).toHaveBeenCalledWith('/api/trips', { method: 'POST', body: { title: 'Our trip', description: 'Together' } })
  })
  it('keeps invitation tokens in a POST body rather than a URL', async () => {
    await joinTrip(token)
    expect(request).toHaveBeenCalledWith('/api/trips/join', { method: 'POST', body: { token } })
  })
  it('uses separate administrator endpoints for creation and revocation', async () => {
    await issueInvitation('trip'); await revokeInvitation('trip')
    expect(request).toHaveBeenNthCalledWith(1, '/api/trips/trip/invitation', { method: 'POST' })
    expect(request).toHaveBeenNthCalledWith(2, '/api/trips/trip/invitation', { method: 'DELETE' })
  })
  it('passes cancellation to trip listing', async () => {
    const signal = new AbortController().signal
    await listTrips(signal)
    expect(request).toHaveBeenCalledWith('/api/trips', { signal })
  })
})

describe('invitation handoff across sign-in', () => {
  function environment(hash: string, remembered = '') {
    const storage = { getItem: vi.fn().mockReturnValue(remembered), setItem: vi.fn(), removeItem: vi.fn() }
    const replaceState = vi.fn()
    vi.stubGlobal('sessionStorage', storage)
    vi.stubGlobal('window', { location: { hash, pathname: '/', search: '' }, history: { replaceState } })
    return { storage, replaceState }
  }
  it('keeps the token through authentication and removes it from the address bar', () => {
    const { storage, replaceState } = environment(`#invite=${token}`)
    expect(readPendingInvitation()).toBe(token)
    rememberInvitation(token)
    expect(storage.setItem).toHaveBeenCalledWith('rihla.pendingInvitation', token)
    expect(replaceState).toHaveBeenCalledWith(null, '', '/')
  })
  it('restores an invitation after returning from authentication', () => {
    environment('', token)
    expect(readPendingInvitation()).toBe(token)
  })
  it('does not substitute an old invitation for a malformed new link', () => {
    environment('#invite=invalid', token)
    expect(readPendingInvitation()).toBeNull()
  })
  it('leaves Supabase authentication callback fragments alone', () => {
    const { replaceState } = environment('#access_token=fictional&refresh_token=fictional', token)
    expect(readPendingInvitation()).toBe(token)
    rememberInvitation(token)
    expect(replaceState).not.toHaveBeenCalled()
  })
  it('clears the pending invitation after a join or cancellation', () => {
    const { storage } = environment('', token)
    rememberInvitation(null)
    expect(storage.removeItem).toHaveBeenCalledWith('rihla.pendingInvitation')
  })
})

describe('invitation input', () => {
  it('accepts a valid raw token or complete fragment link', () => {
    expect(invitationToken(` ${token} `)).toBe(token)
    expect(invitationToken(`http://localhost:5173/#invite=${token}`)).toBe(token)
    expect(invitationToken(`https://rihla.example/#invite=${token}`)).toBe(token)
  })
  it.each(['', 'wrong', 'a'.repeat(63), `javascript:alert(1)#invite=${token}`, `https://rihla.example/?invite=${token}`])('rejects invalid or unsafe invitation input: %s', (input) => {
    expect(invitationToken(input)).toBeNull()
  })
})
