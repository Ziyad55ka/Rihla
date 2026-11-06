import { describe, expect, it } from 'vitest'
import { flightReview, reviewClock } from './flightReview'
import data from '../test-fixtures/activities.json'
import type { Flights, ProposalSet } from '../types/proposal'

const now = Date.parse('2026-11-06T09:00:00Z')
function route(changes: Partial<Flights> = {}): Flights {
  const item = structuredClone((data as ProposalSet).proposals[0].flights[0])
  item.price_per_person.status = 'Sourced'
  return { ...item, schedule_confirmed: true, group_availability: 'available', priced_at: '2026-11-06T09:00:00Z', ...changes }
}

describe('flight price review reminder', () => {
  it('counts from the quote check, not from page opening or generation', () => {
    expect(flightReview([route()], 15, now + 1000)).toMatchObject({ state: 'countdown', seconds: 899 })
    expect(flightReview([route()], 15, now + 15 * 60000).state).toBe('required')
  })
  it('uses the oldest route and understands explicit time zones', () => {
    const routes = [route(), route({ priced_at: '2026-11-06T12:02:00+03:00' })]
    expect(flightReview(routes, 15, now + 10 * 60000)).toMatchObject({ state: 'countdown', seconds: 300 })
  })
  it.each([null, 'not-a-date', '2026-11-06T09:00:00', '2026-11-06T09:01:00Z'])('does not invent a check time for %s', priced_at => {
    expect(flightReview([route({ priced_at })], 15, now).state).toBe('unknown')
  })
  it('requires checking incomplete, unconfirmed or unavailable party flights', () => {
    for (const changes of [{ schedule_confirmed: false }, { group_availability: 'not_found' as const }, { trip_type: 'one_way' as const }, { legs: [] }]) expect(flightReview([route(changes)], 15, now).state).toBe('required')
  })
  it('never presents missing or invalid flight prices as a fresh offer', () => {
    expect(flightReview([], 15, now).state).toBe('unknown')
    for (const amount_sar of [null, 'NaN', '0', '-1']) {
      const item = route()
      item.price_per_person.amount_sar = amount_sar
      expect(flightReview([item], 15, now).state).toBe('unknown')
    }
  })
  it('requires checking estimated prices even when the schedule is confirmed', () => {
    const item = route()
    item.price_per_person.status = 'Estimated'
    expect(flightReview([item], 15, now).state).toBe('required')
  })
  it.each([0, -1, NaN, Infinity, 1441])('rejects an invalid review interval %s', minutes => {
    expect(flightReview([route()], minutes, now).state).toBe('required')
  })
  it('formats a stable, localized countdown including longer windows', () => {
    expect(reviewClock(61, 'en-US')).toBe('01:01')
    expect(reviewClock(3661, 'en-US')).toBe('01:01:01')
    expect(reviewClock(0, 'en-US')).toBe('00:00')
    expect(reviewClock(61, 'ar-SA')).toBe('٠١:٠١')
  })
})
