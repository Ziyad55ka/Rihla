import { describe, expect, it } from 'vitest'
import { formatAccommodation, parseAccommodation, toggleHotelClass } from './accommodation'

describe('hotel preferences', () => {
  it('preserves legacy notes and whitespace', () => {
    const value = 'Near metro\nstep free '
    expect(formatAccommodation(parseAccommodation(value))).toBe(value)
  })
  it('only accepts lower classes explicitly selected by the member', () => {
    const value = formatAccommodation({ stars: 5, lower: [3, 4, 4, 5], notes: 'quiet\n' })
    expect(value).toBe('stay:stars=5;lower=3,4;notes:quiet\n')
    expect(parseAccommodation(value)).toEqual({ stars: 5, lower: [3, 4], notes: 'quiet\n' })
  })
  it('lets each class be chosen once while keeping the existing wire format', () => {
    const base = { stars: 5 as const, lower: [], notes: 'quiet' }
    const both = toggleHotelClass(base, 3)
    expect(formatAccommodation(both)).toBe('stay:stars=5;lower=3;notes:quiet')
    expect(toggleHotelClass(both, 5)).toEqual({ stars: 3, lower: [], notes: 'quiet' })
    expect(toggleHotelClass(toggleHotelClass(both, 5), 3)).toEqual({ stars: null, lower: [], notes: 'quiet' })
  })
})
