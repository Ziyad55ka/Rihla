import { authenticatedRequest } from './http'
import type { Language } from './language'
import type { AirlineFareNote, BudgetStatus, CityStay, GeneratedProposals, GroupConflicts, ConflictCategory, InfoStatus, Proposal, ProposalSource, StoredProposals } from '../types/proposal'

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
export type FlightFallback = 'not_available' | 'limit' | 'demo' | 'check_failed' | 'no_link'

export interface FlightSummary {
  direction: 'outbound' | 'return'
  airline: string | null
  flight_number: string | null
  departure_time: string | null
  arrival_time: string | null
}

export interface FlightFacts {
  url: string | null
  seller: string | null
  seller_type: string | null
  provider: string | null
  exact_flight: boolean
  price_sar: string | null
  /** Set only when the price differs from the one saved. */
  previous_price_sar: string | null
  cabin_class: string | null
  fare_name: string | null
  checked_bags: number | null
  carry_on_bags: number | null
  flights: FlightSummary[]
  airline_fares: AirlineFareNote[]
}

export interface FlightAlternative extends FlightFacts {
  /** gone: already saved in place of the old flight. The others are suggestions. */
  reason: 'gone' | 'no_link' | 'cheaper'
  within_budget: boolean | null
}

export interface FlightCheckResult extends FlightFacts {
  updated: boolean
  /** Set means url, if any, is a Google Flights search. */
  fallback: FlightFallback | null
  alternative: FlightAlternative | null
  now_over_budget: boolean
  checked_at: string | null
  link_valid_minutes: number
  next_refresh_seconds: number
}

export const bookFlight = (tripId: string, proposalId: string, leg: BookLeg) =>
  authenticatedRequest<FlightCheckResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/book-flight?leg=${leg}`, { method: 'POST', timeoutMs: 60000 })

export const refreshFlights = (tripId: string, proposalId: string) =>
  authenticatedRequest<FlightCheckResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/refresh-flights`, { method: 'POST', timeoutMs: 60000 })

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

/** Who gave a flight's price, in plain words. Trip.com must always be named. */
export function sourceLabel(facts: { provider?: string | null; seller_type?: string | null; price_source?: string | null }): string {
  if (facts.provider === 'tripcom') return 'Price from Trip.com'
  if (facts.seller_type === 'airline' && facts.price_source !== 'search') return 'Price directly from the seller'
  if (facts.price_source === 'seller') return 'Price from a travel agent'
  return 'Price from flight search results'
}

/** Reloads the page's proposals after a check saved something, so it shows the new price. */
export async function checkAndReload(check: () => Promise<FlightCheckResult>, reload: () => void): Promise<FlightCheckResult> {
  const result = await check()
  if (result.updated) reload()
  return result
}

/** Minutes a checked link should still work. 0 means expired, null means no timer. */
export function linkMinutesLeft(checkedAt: string | null, validMinutes: number, now: number): number | null {
  if (!checkedAt) return null
  const left = new Date(checkedAt).getTime() + validMinutes * 60000 - now
  return left > 0 ? Math.ceil(left / 60000) : 0
}

export function priceChange(price: string | null, previous: string | null): { price: number; previous: number; difference: number } | null {
  if (!price || !previous) return null
  const difference = Math.round((Number(price) - Number(previous)) * 100) / 100
  return difference === 0 ? null : { price: Number(price), previous: Number(previous), difference }
}

/** Who gave a stay's name and price: a live source, or the booking site it was read from. */
export function staySource(stay: CityStay, sources: ProposalSource[]): string | null {
  if (stay.hotel_source) return stay.hotel_source
  const cited = [...stay.hotel_price_per_night.evidence, ...stay.hotel_name.evidence][0]
  const source = cited && sources.find((item) => item.id === cited.source_id)
  if (!source) return null
  try { return new URL(source.url).hostname.replace(/^www\./, '') } catch { return null }
}

export function canPressGenerate(conflicts: GroupConflicts | null, generating: boolean): boolean {
  return conflicts?.can_generate === true && !generating
}
