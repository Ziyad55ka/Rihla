import type { Flights } from '../types/proposal'

export type FlightReview = { state: 'countdown'; dueAt: number; seconds: number } | { state: 'required' | 'unknown'; dueAt: null; seconds: null }

/** A review reminder, never a fare guarantee or an inventory hold. */
export function flightReview(routes: Flights[], minutes: number, now: number): FlightReview {
  if (!routes.length || routes.some(route => route.price_per_person.amount_sar === null || !Number.isFinite(Number(route.price_per_person.amount_sar)) || Number(route.price_per_person.amount_sar) <= 0)) return { state: 'unknown', dueAt: null, seconds: null }
  if (!Number.isFinite(minutes) || minutes <= 0 || minutes > 1440 || !Number.isFinite(now)) return { state: 'required', dueAt: null, seconds: null }
  if (routes.some(route => route.price_per_person.status !== 'Sourced' || !route.schedule_confirmed || route.group_availability !== 'available' || route.trip_type === 'one_way' || !['outbound', 'return'].every(direction => route.legs.some(leg => leg.direction === direction)))) return { state: 'required', dueAt: null, seconds: null }
  const times = routes.map(route => route.priced_at && /(?:Z|[+-]\d{2}:\d{2})$/.test(route.priced_at) ? Date.parse(route.priced_at) : NaN)
  if (times.some(time => !Number.isFinite(time) || time > now)) return { state: 'unknown', dueAt: null, seconds: null }
  const dueAt = Math.min(...times) + minutes * 60000
  const seconds = Math.ceil((dueAt - now) / 1000)
  return seconds > 0 ? { state: 'countdown', dueAt, seconds } : { state: 'required', dueAt: null, seconds: null }
}

export function reviewClock(seconds: number, locale: string): string {
  const number = new Intl.NumberFormat(locale, { minimumIntegerDigits: 2, useGrouping: false })
  const whole = Math.max(0, Math.ceil(seconds))
  const parts = whole >= 3600 ? [Math.floor(whole / 3600), Math.floor(whole % 3600 / 60), whole % 60] : [Math.floor(whole / 60), whole % 60]
  return parts.map(part => number.format(part)).join(':')
}
