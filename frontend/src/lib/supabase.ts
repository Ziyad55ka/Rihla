import { createClient, type SupabaseClient } from '@supabase/supabase-js'

interface SupabaseEnvironment {
  url?: string
  publishableKey?: string
}

export type SupabaseConfiguration =
  | { state: 'not-configured'; message: string }
  | { state: 'invalid'; message: string }
  | { state: 'configured'; url: string; publishableKey: string; message: string }

function isLegacyAnonKey(key: string): boolean {
  try {
    const parts = key.split('.')
    if (parts.length !== 3) return false
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const decoded: unknown = JSON.parse(atob(payload))
    return typeof decoded === 'object' && decoded !== null && 'role' in decoded && decoded.role === 'anon'
  } catch {
    return false
  }
}

export function readSupabaseConfiguration({ url, publishableKey }: SupabaseEnvironment): SupabaseConfiguration {
  const projectUrl = url?.trim() || ''
  const key = publishableKey?.trim() || ''
  if (!projectUrl && !key) {
    return {
      state: 'not-configured',
      message: 'Add the project URL and publishable key to frontend/.env.local when your Supabase project is ready.',
    }
  }
  if (!projectUrl || !key) {
    return { state: 'invalid', message: 'Both the Supabase project URL and publishable key are required.' }
  }
  try {
    const parsedUrl = new URL(projectUrl)
    const isLocal = ['localhost', '127.0.0.1', '[::1]'].includes(parsedUrl.hostname)
    if (
      (parsedUrl.protocol !== 'https:' && !(parsedUrl.protocol === 'http:' && isLocal)) ||
      parsedUrl.username || parsedUrl.password || parsedUrl.search || parsedUrl.hash || parsedUrl.pathname !== '/'
    ) throw new Error('Invalid project URL')
  } catch {
    return { state: 'invalid', message: 'Use your Supabase project URL, such as https://your-project.supabase.co.' }
  }
  // Browser clients accept public keys only. Never display the supplied key in errors.
  if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(key) && !isLegacyAnonKey(key)) {
    return {
      state: 'invalid',
      message: 'Use a publishable key (or legacy anon key). Secret and service_role keys cannot be used in the browser.',
    }
  }
  return {
    state: 'configured',
    url: projectUrl,
    publishableKey: key,
    message: 'Configuration is present. Sign in above to check your identity and profile database access separately.',
  }
}

export const supabaseConfiguration = readSupabaseConfiguration({
  url: import.meta.env.VITE_SUPABASE_URL,
  publishableKey: import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
})

// Creating the client does not prove that a project/key exists or that RLS allows access.
// Auth owns session storage/refresh. FastAPI verifies identity independently.
export const supabase: SupabaseClient | null = supabaseConfiguration.state === 'configured'
  ? createClient(supabaseConfiguration.url, supabaseConfiguration.publishableKey)
  : null
