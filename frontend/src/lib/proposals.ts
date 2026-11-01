import { authenticatedRequest } from './http'
import type { Language } from './language'
import type { BudgetStatus, GeneratedProposals, GroupConflicts, ConflictCategory, InfoStatus, Proposal, StoredProposals } from '../types/proposal'

// Generation searches and asks the AI several times, so it can take minutes.
const GENERATION_TIMEOUT_MS = 10 * 60 * 1000

const path = (tripId: string, part: string) => `/api/trips/${encodeURIComponent(tripId)}/${part}` as const

export const getConflicts = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<GroupConflicts>(path(tripId, 'conflicts'), { signal })

export const getProposals = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<StoredProposals>(path(tripId, 'proposals'), { signal })

export const generateProposals = (tripId: string, regenerate: boolean) =>
  authenticatedRequest<GeneratedProposals>(path(tripId, 'proposals'), {
    method: 'POST', body: { regenerate }, timeoutMs: GENERATION_TIMEOUT_MS,
  })

// Category messages only. The API never says which member or value caused a conflict.
export const conflictMessages: Record<ConflictCategory, string> = {
  readiness: 'Generation is waiting for all members to be ready.',
  dates: 'The group’s dates do not allow a trip yet.',
  destinations: 'The group’s required destinations conflict.',
  flights: 'The group’s flight requirements cannot be met together.',
  accommodation: 'The group’s accommodation requirements cannot be met.',
  budget: 'The group’s budget is too low for these requirements and dates.',
}

export const reviewMessages: Partial<Record<ConflictCategory, string>> = {
  destinations: 'You have a required destination. Please review it in your preferences.',
}

export const budgetStatusLabels: Record<BudgetStatus, string> = {
  within_group_budget: 'Within the group budget',
  includes_unconfirmed: 'Within budget, with unconfirmed prices',
  over_group_budget: 'Over the group budget',
}

export const statusLabels: Record<InfoStatus, string> = {
  Sourced: 'Confirmed by the seller',
  Estimated: 'Estimated',
  Unconfirmed: 'Unconfirmed · Check before booking',
  'Not available': 'Not available',
}

/** A flight's source is an internal fare note, so people never see it. */
export function isInternalSource(source: { title: string; kind?: string | null }): boolean {
  return source.kind === 'flight' || /^Ignav\b/.test(source.title)
}

export function proposalTitle(proposal: Proposal, language: Language): string {
  return (language === 'ar' ? proposal.title_ar : proposal.title_en) ?? proposal.title
}

// Saved data comes from outside services, so only web addresses become links.
export function safeLink(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

function addDays(day: string, count: number): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + count)
  return date.toISOString().slice(0, 10)
}

/** Each stay's check-in and check-out, counted from the trip's first day. */
export function stayDates(proposal: Proposal): { start: string; end: string }[] {
  let start = proposal.start_date
  return proposal.cities.map((stay) => {
    const end = addDays(start, stay.nights)
    const dates = { start, end }
    start = end
    return dates
  })
}

export type BookLeg = 'outbound' | 'inbound' | 'round_trip'
export type FlightFallback = 'not_available' | 'limit' | 'demo'

export interface BookFlightResult {
  url: string
  fallback: FlightFallback | null
  seller: string | null
  exact_flight: boolean
  price_sar: string | null
  previous_price_sar: string | null
}

export interface RefreshFlightsResult {
  updated: boolean
  fallback: FlightFallback | null
  url: string | null
  now_over_budget: boolean
  next_refresh_seconds: number
}

export const bookFlight = (tripId: string, proposalId: string, leg: BookLeg) =>
  authenticatedRequest<BookFlightResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/book-flight?leg=${leg}`, { timeoutMs: 60000 })

export const refreshFlights = (tripId: string, proposalId: string) =>
  authenticatedRequest<RefreshFlightsResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/refresh-flights`, { method: 'POST', timeoutMs: 60000 })

export interface PriceAgeLimits {
  freshHours: number
  staleHours: number
  /** For older proposals with no price time: when the proposals were generated. */
  fallback?: string | null
}

export function priceAge(pricedAt: string | null, now: number, limits: PriceAgeLimits): { level: 'fresh' | 'recent' | 'old'; unit: 'minutes' | 'hours'; count: number } | null {
  if (!pricedAt) return null
  const minutes = Math.max(0, Math.floor((now - new Date(pricedAt).getTime()) / 60000))
  if (Number.isNaN(minutes)) return null
  const hours = Math.floor(minutes / 60)
  if (hours >= limits.staleHours) return { level: 'old', unit: 'hours', count: hours }
  if (hours >= limits.freshHours) return { level: 'recent', unit: 'hours', count: hours }
  return minutes < 60 ? { level: 'fresh', unit: 'minutes', count: minutes } : { level: 'fresh', unit: 'hours', count: hours }
}

/** Minutes left before another update, counted from when the price was last checked. */
export function refreshWaitMinutes(pricedAt: string | null | undefined, cooldownMinutes: number, now: number): number {
  if (!pricedAt) return 0
  const left = new Date(pricedAt).getTime() + cooldownMinutes * 60000 - now
  return left > 0 ? Math.ceil(left / 60000) : 0
}

export function canPressGenerate(conflicts: GroupConflicts | null, generating: boolean): boolean {
  return conflicts?.can_generate === true && !generating
}
