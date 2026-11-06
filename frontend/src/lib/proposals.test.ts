import { afterEach, expect, it, vi } from 'vitest'
import { canPressGenerate, conflictMessages, generateProposals, getConflicts, getProposals, hotelLink } from './proposals'

const { request } = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('./http', () => ({ authenticatedRequest: request }))
vi.mock('./proposalsHttp', () => ({ longRequest: request }))
afterEach(() => vi.resetAllMocks())

it('reads conflicts and proposals for the selected trip', async () => {
  const signal = new AbortController().signal
  await getConflicts('trip/id', signal)
  await getProposals('trip/id', signal)
  expect(request).toHaveBeenCalledWith('/api/trips/trip%2Fid/conflicts', { signal })
  expect(request).toHaveBeenCalledWith('/api/trips/trip%2Fid/proposals', { signal })
})

it('asks for regeneration explicitly and allows a long wait', async () => {
  await generateProposals('t', true)
  expect(request).toHaveBeenCalledWith('/api/trips/t/proposals', { body: { regenerate: true }, timeoutMs: 600000 })
})

it('allows generating only with no conflicts and no running generation', () => {
  const clear = { conflicts: [], own_review: [], can_generate: true }
  expect(canPressGenerate(clear, false)).toBe(true)
  expect(canPressGenerate(clear, true)).toBe(false)
  expect(canPressGenerate({ conflicts: ['budget'], own_review: [], can_generate: false }, false)).toBe(false)
  expect(canPressGenerate(null, false)).toBe(false)
})

it('conflict messages hold no figure', () => {
  for (const message of Object.values(conflictMessages)) expect(message).not.toMatch(/\d/)
})

it.each(['https://www.google.com/aclk?adurl', 'https://google.com/url?q=hotel', 'http://booking.com/hotel/test', 'https://user:secret@booking.com/hotel/test', 'not-a-url'])('does not offer an unusable saved hotel link: %s', url => {
  expect(hotelLink(url)).toBeNull()
})

it('keeps a real hotel page and a dated price comparison intact', () => {
  for (const url of ['https://booking.com/hotel/test?checkin=2027-01-10', 'https://www.google.com/travel/hotels/entity/test?dates=2027-01-10']) expect(hotelLink(url)).toBe(url)
})
