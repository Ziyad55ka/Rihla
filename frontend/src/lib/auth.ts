import type { SupabaseClient } from '@supabase/supabase-js'
import { API_BASE_URL } from './api'

export function authErrorMessage(error: unknown): string {
  const code = typeof error === 'object' && error !== null && 'code' in error ? error.code : ''
  switch (code) {
    case 'invalid_credentials': return 'The email or password is incorrect.'
    case 'email_not_confirmed': return 'Confirm your email using the link in your inbox, then sign in.'
    case 'login_locked': return 'Five sign-in attempts failed within 15 minutes. Please wait 15 minutes before trying again.'
    case 'login_in_progress': return 'A sign-in attempt is already in progress. Wait a moment, then try again.'
    case 'backend_unavailable': return 'Could not complete sign-in. Check that the backend is running and try again.'
    case 'over_request_rate_limit':
    case 'over_email_send_rate_limit': return 'Too many attempts. Please wait before trying again.'
    case 'weak_password': return 'Choose a stronger password and try again.'
    case 'user_already_exists': return 'Unable to create this account. Try signing in or use another email.'
    default: return 'The account request could not be completed. Check your connection and try again.'
  }
}

async function backendSignIn(client: SupabaseClient, email: string, password: string) {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL.replace(/\/+$/, '')}/api/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ email, password }), cache: 'no-store', signal: AbortSignal.timeout(15000),
    })
  } catch { throw { code: 'backend_unavailable' } }
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload ? payload.detail : null
    const code = typeof detail === 'object' && detail !== null && 'code' in detail ? detail.code : 'backend_unavailable'
    throw { code }
  }
  if (typeof payload !== 'object' || payload === null || !('access_token' in payload) || typeof payload.access_token !== 'string'
    || !('refresh_token' in payload) || typeof payload.refresh_token !== 'string') throw { code: 'backend_unavailable' }
  // Supabase still owns persistence, refresh and auth state notifications.
  return client.auth.setSession({ access_token: payload.access_token, refresh_token: payload.refresh_token })
}

export async function submitCredentials(
  client: SupabaseClient, mode: 'signin' | 'signup', email: string, password: string,
  redirectOrigin: string,
): Promise<'signed-in' | 'confirmation-required'> {
  const credentials = { email: email.trim(), password }
  const { data, error } = mode === 'signup'
    ? await client.auth.signUp({ ...credentials, options: { emailRedirectTo: redirectOrigin } })
    : await backendSignIn(client, credentials.email, credentials.password)
  if (error) throw error
  return data.session ? 'signed-in' : 'confirmation-required'
}
