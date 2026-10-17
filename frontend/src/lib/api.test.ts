import { afterEach, describe, expect, it, vi } from 'vitest'
import { getBackendHealth } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('backend health check', () => {
  it('uses the configured API prefix and validates the Rihla response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ status: 'ok', service: 'rihla-api' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getBackendHealth({ baseUrl: 'http://localhost:8000/api/' })).resolves.toEqual({
      status: 'ok', service: 'rihla-api',
    })
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/health', expect.objectContaining({
      method: 'GET', cache: 'no-store', signal: expect.any(AbortSignal),
    }))
  })

  it.each([
    { status: 'error', service: 'rihla-api' },
    { status: 'ok', service: 'another-app' },
    { status: 'ok' },
    null,
  ])('does not report success for an unrelated or unhealthy response: %j', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(body)))
    await expect(getBackendHealth()).rejects.toThrow('did not identify a healthy Rihla backend')
  })

  it('rejects an HTTP failure even when its body looks healthy', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'ok', service: 'rihla-api' }, { status: 503 })))
    await expect(getBackendHealth()).rejects.toThrow('HTTP 503')
  })

  it('rejects a successful HTML response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Another service</html>')))
    await expect(getBackendHealth()).rejects.toThrow('valid Rihla health response')
  })

  it('rejects malformed configuration without making a request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(getBackendHealth({ baseUrl: 'localhost:8000' })).rejects.toThrow('VITE_API_BASE_URL')
    await expect(getBackendHealth({ baseUrl: 'https://user:password@example.test' })).rejects.toThrow('VITE_API_BASE_URL')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('times out an unresponsive request', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const result = expect(getBackendHealth({ timeoutMs: 1000 })).rejects.toThrow('within 1 seconds')
    await vi.advanceTimersByTimeAsync(1000)
    await result
    expect(vi.getTimerCount()).toBe(0)
  })

  it('forwards cancellation so an unmounted page can stop its request', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })))
    const result = expect(getBackendHealth({ signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await result
  })
})
