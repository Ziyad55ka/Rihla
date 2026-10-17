import { authenticatedRequest } from './http'

export interface Account { id: string; email: string }
export interface Profile { id: string; display_name: string; created_at: string }

export async function accountRequest<T>(
  path: '/api/me' | '/api/profile',
  { signal, displayName }: { signal?: AbortSignal; displayName?: string } = {},
): Promise<T> {
  return authenticatedRequest<T>(path, {
    method: displayName === undefined ? 'GET' : 'PUT',
    ...(displayName === undefined ? {} : { body: { display_name: displayName.trim() } }),
    signal,
  })
}
