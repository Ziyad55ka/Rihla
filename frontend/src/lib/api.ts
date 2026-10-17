import type { HealthResponse } from '../types/api'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://localhost:8001'

interface HealthOptions {
  baseUrl?: string
  signal?: AbortSignal
  timeoutMs?: number
}

function healthUrl(baseUrl: string): string {
  let url: URL
  try {
    url = new URL(baseUrl)
  } catch {
    throw new Error('Check VITE_API_BASE_URL: it must be a complete http or https URL.')
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Check VITE_API_BASE_URL: use an http or https URL without credentials, a query, or a fragment.')
  }
  return `${url.toString().replace(/\/+$/, '')}/health`
}

export async function getBackendHealth({
  baseUrl = API_BASE_URL,
  signal,
  timeoutMs = 5000,
}: HealthOptions = {}): Promise<HealthResponse> {
  const url = healthUrl(baseUrl)
  const controller = new AbortController()
  let timedOut = false
  const onAbort = () => controller.abort(signal?.reason)
  if (signal?.aborted) onAbort()
  else signal?.addEventListener('abort', onAbort, { once: true })

  const timeout = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(`The backend returned HTTP ${response.status}.`)

    let data: unknown
    try {
      data = await response.json()
    } catch {
      throw new Error('The backend did not return a valid Rihla health response.')
    }
    if (
      typeof data !== 'object' ||
      data === null ||
      !('status' in data) ||
      data.status !== 'ok' ||
      !('service' in data) ||
      data.service !== 'rihla-api'
    ) {
      throw new Error('The response did not identify a healthy Rihla backend.')
    }
    return { status: data.status, service: data.service }
  } catch (error) {
    if (timedOut) throw new Error(`The backend did not respond within ${timeoutMs / 1000} seconds.`, { cause: error })
    throw error
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', onAbort)
  }
}
