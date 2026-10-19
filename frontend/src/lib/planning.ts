import { authenticatedRequest } from './http'
import type { MissingField, PlanningStatus } from '../types/planning'

export const getPlanningStatus = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<PlanningStatus>(`/api/trips/${encodeURIComponent(tripId)}/planning`, { signal })

export const missingFieldLabels: Record<MissingField, string> = {
  departure_city: 'Departure city', max_budget_sar: 'Maximum budget in SAR',
  available_start: 'Available from date', available_end: 'Available until date',
}

// These are calendar dates. Local midnight preserves the date in every time zone.
export function calendarDate(value: string, locale?: string): string {
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(0)
  date.setFullYear(year, month - 1, day); date.setHours(0, 0, 0, 0)
  return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
}
