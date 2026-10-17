import { authenticatedRequest } from './http'
import type { InvitationCreated, InvitationStatus, JoinResult, TripDetail, TripSummary } from '../types/trips'

export const listTrips = (signal?: AbortSignal) => authenticatedRequest<TripSummary[]>('/api/trips', { signal })
export const getTrip = (id: string, signal?: AbortSignal) => authenticatedRequest<TripDetail>(`/api/trips/${encodeURIComponent(id)}`, { signal })
export const createTrip = (title: string, description: string) => authenticatedRequest<TripDetail>('/api/trips', { method: 'POST', body: { title: title.trim(), description: description.trim() } })
export const joinTrip = (token: string) => authenticatedRequest<JoinResult>('/api/trips/join', { method: 'POST', body: { token } })
export const getInvitation = (id: string, signal?: AbortSignal) => authenticatedRequest<InvitationStatus>(`/api/trips/${encodeURIComponent(id)}/invitation`, { signal })
export const issueInvitation = (id: string) => authenticatedRequest<InvitationCreated>(`/api/trips/${encodeURIComponent(id)}/invitation`, { method: 'POST' })
export const revokeInvitation = (id: string) => authenticatedRequest<InvitationStatus>(`/api/trips/${encodeURIComponent(id)}/invitation`, { method: 'DELETE' })

export function invitationToken(input: string): string | null {
  const value = input.trim()
  if (/^[0-9a-f]{64}$/.test(value)) return value
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol)) return null
    const token = new URLSearchParams(url.hash.slice(1)).get('invite')
    return token && /^[0-9a-f]{64}$/.test(token) ? token : null
  } catch { return null }
}

export function invitationUrl(token: string): string { return `${window.location.origin}/#invite=${token}` }

const PENDING_KEY = 'rihla.pendingInvitation'
export function readPendingInvitation(): string | null {
  const params = new URLSearchParams(window.location.hash.slice(1))
  const token = params.get('invite')
  if (params.has('invite')) return token && /^[0-9a-f]{64}$/.test(token) ? token : null
  try { return invitationToken(sessionStorage.getItem(PENDING_KEY) ?? '') } catch { return null }
}
export function rememberInvitation(token: string | null) {
  try { if (token) sessionStorage.setItem(PENDING_KEY, token); else sessionStorage.removeItem(PENDING_KEY) } catch { /* Joining manually still works with restricted storage. */ }
  // Fragments avoid token exposure in server access logs. Consume ours only;
  // Supabase still owns authentication callback fragments.
  if (new URLSearchParams(window.location.hash.slice(1)).has('invite')) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
}
