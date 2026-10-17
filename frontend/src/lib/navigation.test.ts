import { afterEach, expect, it, vi } from 'vitest'
import { isWorkspaceRoute, readReturnPath, readRoute, rememberReturnPath } from './navigation'

afterEach(() => vi.unstubAllGlobals())
it('gives preferences their own refreshable protected URL', () => {
  const id = '12345678-abcd-1234-abcd-123456789012'
  expect(readRoute(`/trips/${id}/preferences`)).toEqual({ page: 'preferences', tripId: id })
  expect(isWorkspaceRoute(readRoute('/trips/new'))).toBe(true)
  expect(readRoute('/trips/not-an-id')).toEqual({ page: 'not-found' })
})
it('preserves only known internal destinations through authentication', () => {
  const entries = new Map<string, string>()
  vi.stubGlobal('sessionStorage', { getItem: (key: string) => entries.get(key) ?? null, setItem: (key: string, value: string) => entries.set(key, value), removeItem: (key: string) => entries.delete(key) })
  rememberReturnPath('/trips/new')
  expect(readReturnPath()).toBe('/trips/new')
  rememberReturnPath('https://example.com')
  expect(readReturnPath()).toBeNull()
  entries.set('rihla.afterSignIn', '//example.com')
  expect(readReturnPath()).toBeNull()
})
it('works when browser session storage is restricted', () => {
  vi.stubGlobal('sessionStorage', { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') }, removeItem: () => { throw new Error('blocked') } })
  expect(() => rememberReturnPath('/trips/join')).not.toThrow()
  expect(readReturnPath()).toBeNull()
})
