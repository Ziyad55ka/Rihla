import { authenticatedRequest } from './http'

export type DateCheck = { status: 'available' | 'conflict' | 'pending' }

export function checkTravelDates(tripId: string, start: string, end: string, signal?: AbortSignal) {
  return authenticatedRequest<DateCheck>(`/api/trips/${encodeURIComponent(tripId)}/date-check`, {
    method: 'POST', body: { available_start: start, available_end: end }, signal,
  })
}
