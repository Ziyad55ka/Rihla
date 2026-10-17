import { API_BASE_URL } from './api'
import { supabase } from './supabase'

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError' }
}

export async function authenticatedRequest<T>(
  path: `/api/${string}`,
  { method = 'GET', body, signal }: { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  if (!supabase) throw new Error('Supabase is not configured.')
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) throw new ApiError('Your session has ended. Please sign in again.', 401)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL.replace(/\/+$/, '')}${path}`, {
      method,
      headers: { Accept: 'application/json', Authorization: `Bearer ${data.session.access_token}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      cache: 'no-store',
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
    })
  } catch (err) {
    if (signal?.aborted) throw err
    throw new ApiError('Could not reach the backend. Check your connection and try again.', 0)
  }
  if (!response.ok) {
    if (response.status === 401) throw new ApiError('Your session is invalid or expired. Sign out and sign in again.', 401)
    const payload: unknown = await response.json().catch(() => null)
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload ? payload.detail : null
    throw new ApiError(typeof detail === 'string' ? detail : `The request failed (HTTP ${response.status}). Check your input and try again.`, response.status)
  }
  return response.json() as Promise<T>
}
