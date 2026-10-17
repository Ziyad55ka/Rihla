import { afterEach, expect, it, vi } from 'vitest'
import { editablePreferences, getPreferences, preferenceError, savePreferences } from './preferences'
import type { SavedPreferences } from '../types/preferences'

const { request } = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('./http', () => ({ authenticatedRequest: request }))
afterEach(() => vi.resetAllMocks())
const saved: SavedPreferences = {
  departure_city: 'Riyadh', max_budget_sar: '4500.50',
  available_start: '2026-11-10', available_end: '2026-11-15',
  destinations: { value: 'Japan', importance: 'Flexible' },
  interests: { value: '', importance: 'Flexible' },
  flights: { value: 'Direct flights', importance: 'Essential' },
  accommodation: { value: '', importance: 'Flexible' },
  currency: 'SAR', updated_at: '2026-10-16T12:00:00Z',
}

it('reads only the current user’s preferences and supports cancellation', async () => {
  const signal = new AbortController().signal
  await getPreferences('trip/id', signal)
  expect(request).toHaveBeenCalledWith('/api/trips/trip%2Fid/preferences', { signal })
})

it('sends editable inputs without response metadata or a target identity', async () => {
  const body = editablePreferences(saved)
  expect(body).not.toHaveProperty('currency')
  expect(body).not.toHaveProperty('updated_at')
  expect(body).not.toHaveProperty('user_id')
  expect(body.flights).not.toBe(saved.flights)
  await savePreferences('trip', body)
  expect(request).toHaveBeenCalledWith('/api/trips/trip/preferences', { method: 'PUT', body })
})

it('accepts incomplete drafts, empty optional fields and same-day availability', () => {
  expect(preferenceError({ ...editablePreferences(saved), departure_city: '', max_budget_sar: null, available_end: null })).toBeNull()
  expect(preferenceError({ ...editablePreferences(saved), available_end: saved.available_start })).toBeNull()
})

it.each(['0', '-1', '1.001', '10000000000', 'NaN', 'Infinity', '1e3'])('rejects invalid SAR amounts: %s', (budget) => {
  expect(preferenceError({ ...editablePreferences(saved), max_budget_sar: budget })).toContain('budget')
})

it('rejects reversed dates instead of silently changing a member’s range', () => {
  expect(preferenceError({ ...editablePreferences(saved), available_end: '2026-11-09' })).toContain('End date')
})
