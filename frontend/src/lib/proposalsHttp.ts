import { API_BASE_URL } from './api'
import { ApiError } from './http'
import { supabase } from './supabase'

/** For generation and flight checks, which take longer than the 15 seconds in http.ts. */
export async function longRequest<T>(path: `/api/${string}`, { body, timeoutMs }: { body?: unknown; timeoutMs: number }): Promise<T> {
  if (!supabase) throw new Error('Supabase is not configured.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new ApiError('Your session has ended. Please sign in again.', 401)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL.replace(/\/+$/, '')}${path}`, {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: `Bearer ${data.session.access_token}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      cache: 'no-store',
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch {
    throw new ApiError('Could not reach the backend. Check your connection and try again.', 0)
  }
  if (!response.ok) {
    if (response.status === 401) throw new ApiError('Your session is invalid or expired. Sign out and sign in again.', 401)
    const payload: unknown = await response.json().catch(() => null)
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload ? payload.detail : null
    const message = typeof detail === 'string' ? detail
      : typeof detail === 'object' && detail !== null && 'message' in detail && typeof detail.message === 'string' ? detail.message
        : `The request failed (HTTP ${response.status}). Check your input and try again.`
    throw new ApiError(message, response.status, detail)
  }
  return response.json() as Promise<T>
}
