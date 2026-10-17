import { afterEach, expect, it, vi } from 'vitest'
import { calendarDate, getPlanningStatus } from './planning'

const { request } = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('./http', () => ({ authenticatedRequest: request }))
afterEach(() => vi.resetAllMocks())

it('requests only the selected trip’s planning status with cancellation', async () => {
  const signal = new AbortController().signal
  await getPlanningStatus('trip/id', signal)
  expect(request).toHaveBeenCalledWith('/api/trips/trip%2Fid/planning', { signal })
})

it('formats calendar dates without turning them into UTC instants', () => {
  expect(calendarDate('2028-02-29')).toBe(new Date(2028, 1, 29).toLocaleDateString([], { year:'numeric', month:'short', day:'numeric' }))
})
