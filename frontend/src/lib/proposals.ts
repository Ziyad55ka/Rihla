import { authenticatedRequest } from './http'
import { longRequest } from './proposalsHttp'
import type { Language } from './language'
import type { AirlineFareNote, BudgetStatus, GeneratedProposals, GenerationIssue, GenerationProgress, GroupConflicts, ConflictCategory, InfoStatus, IntercityTransfer, Proposal, ProposalSource, StoredProposals } from '../types/proposal'

// Generation searches and asks the AI several times, so it can take minutes.
const GENERATION_TIMEOUT_MS = 10 * 60 * 1000

const path = (tripId: string, part: string) => `/api/trips/${encodeURIComponent(tripId)}/${part}` as const

export const getConflicts = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<GroupConflicts>(path(tripId, 'conflicts'), { signal })

export const getProposals = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<StoredProposals>(path(tripId, 'proposals'), { signal })

/** `tripDays` is the administrator's chosen length; leave it out to let the AI choose. */
export const generateProposals = (tripId: string, regenerate: boolean, tripDays?: number | null) =>
  longRequest<GeneratedProposals>(path(tripId, 'proposals'), { body: tripDays ? { regenerate, trip_days: tripDays } : { regenerate }, timeoutMs: GENERATION_TIMEOUT_MS })

export const getGenerationProgress = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<GenerationProgress | null>(path(tripId, 'proposals/progress'), { signal })

/** How often the page asks for progress while generating. */
export const PROGRESS_POLL_MS = 2000

/** The structured reason from a failed generation, when the backend sent one. */
export function generationIssue(detail: unknown): GenerationIssue | null {
  if (typeof detail !== 'object' || detail === null) return null
  const value = detail as Partial<GenerationIssue>
  if (typeof value.code !== 'string' || typeof value.message !== 'string' || !Array.isArray(value.suggestions)) return null
  return {
    code: value.code,
    message: value.message,
    places: Array.isArray(value.places) ? value.places.filter((item): item is string => typeof item === 'string') : [],
    causes: Array.isArray(value.causes) ? value.causes.filter((item) => typeof item === 'object' && item !== null && typeof item.kind === 'string' && typeof item.text === 'string') : [],
    suggestions: value.suggestions.filter((item) => typeof item === 'object' && item !== null && typeof item.action === 'string' && typeof item.kind === 'string')
      .map((item) => ({ ...item, params: item.params ?? {} })),
  }
}

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
  includes_unconfirmed: 'Budget not confirmed: some prices are estimates or missing',
  over_group_budget: 'Over the group budget',
}

export const statusLabels: Record<InfoStatus, string> = {
  Sourced: 'Source-backed',
  Estimated: 'Estimated',
  Unconfirmed: 'Rough estimate',
  'Not available': 'Not available',
}

export function proposalTitle(proposal: Proposal, language: Language): string {
  return (language === 'ar' ? proposal.title_ar : proposal.title_en) ?? proposal.title
}

// Saved data comes from outside services, so only web addresses become links.
export function safeLink(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

/** Old saved hotel results may contain an ad click instead of a hotel page. */
export function hotelLink(url: string | null): string | null {
  if (!url) return null
  try {
    const link = new URL(url)
    if (link.protocol !== 'https:' || link.username || link.password) return null
    if (['google.com', 'www.google.com'].includes(link.hostname) && ['/aclk', '/url'].includes(link.pathname)) return null
    return link.toString()
  } catch { return null }
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

interface FlightSummary {
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

interface FlightAlternative extends FlightFacts {
  /** gone: already saved in place of the old flight. The others are suggestions. */
  reason: 'gone' | 'no_link' | 'cheaper' | 'agent'
  within_budget: boolean | null
}

export interface FlightCheckResult extends FlightFacts {
  updated: boolean
  /** Set means url, if any, is a Google Flights search. */
  fallback: FlightFallback | null
  alternative: FlightAlternative | null
  /** Google Flights with both chosen flights selected for the group, or null. */
  itinerary_url?: string | null
  /** With fallback "limit": when a new check is allowed again (ISO time). */
  retry_at?: string | null
  now_over_budget: boolean
  checked_at: string | null
  link_valid_minutes: number
  next_refresh_seconds: number
}

export const bookFlight = (tripId: string, proposalId: string, leg: BookLeg) =>
  longRequest<FlightCheckResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/book-flight?leg=${leg}`, { timeoutMs: 60000 })

export const refreshFlights = (tripId: string, proposalId: string) =>
  longRequest<FlightCheckResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/refresh-flights`, { timeoutMs: 60000 })

/** The member opened the seller and this flight was not offered: find another. */
export const reportFlightNotOffered = (tripId: string, proposalId: string) =>
  longRequest<FlightCheckResult>(`/api/trips/${encodeURIComponent(tripId)}/proposals/${encodeURIComponent(proposalId)}/flight-not-offered`, { timeoutMs: 60000 })

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

/** A time in the page's digits. */
export function localTime(time: string, locale: string): string {
  const format = new Intl.NumberFormat(locale, { minimumIntegerDigits: 2, useGrouping: false })
  return time.split(':').map((part) => format.format(Number(part))).join(':')
}

/** "1h 20m" in the page's language. Other wording stays as the source wrote it. */
export function durationLabel(text: string | null, language: Language, locale: string): string | null {
  if (!text) return null
  const found = /^\s*(?:(\d+)\s*h(?:ours?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*$/i.exec(text)
  if (!found || (!found[1] && !found[2])) return text
  const number = (value: string) => Number(value).toLocaleString(locale)
  const hours = found[1] ? `${number(found[1])}${language === 'ar' ? ' س' : 'h'}` : ''
  const minutes = found[2] ? `${number(found[2])}${language === 'ar' ? ' د' : 'm'}` : ''
  return [hours, minutes].filter(Boolean).join(' ')
}

export type ModeKind = 'train' | 'bus' | 'flight' | 'car' | 'ferry' | 'other'

export function modeKind(mode: string | null): ModeKind {
  const text = mode ?? ''
  if (/train|rail|tgv|قطار/i.test(text)) return 'train'
  if (/bus|coach|باص|حافلة/i.test(text)) return 'bus'
  if (/flight|fly|plane|air|طيران|طائرة/i.test(text)) return 'flight'
  if (/ferry|boat|عبّارة|عبارة/i.test(text)) return 'ferry'
  if (/car|taxi|drive|سيارة|تاكسي/i.test(text)) return 'car'
  return 'other'
}

/** Where a transfer's link goes: the page its price, mode or duration was read from,
 * otherwise Rome2rio's page for the route, which lists operators. Never a web search. */
export function transferLink(transfer: IntercityTransfer, sources: ProposalSource[]): { url: string; kind: 'source' | 'planner' } {
  const cited = [transfer.price_per_person, transfer.mode, transfer.duration].flatMap((field) => field.evidence.map((item) => item.source_id))
  const page = cited.map((id) => sources.find((source) => source.id === id)).find((source) => source?.url.startsWith('https://'))
  if (page) return { url: page.url, kind: 'source' }
  const place = (name: string) => encodeURIComponent(name.trim().replace(/\s+/g, '-'))
  return { url: `https://www.rome2rio.com/map/${place(transfer.from_city)}/${place(transfer.to_city)}`, kind: 'planner' }
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

/** How much of the link's time is left, from 1 down to 0, for the ring. */
/** One room for each person, as the budget check assumes, even on older saved links. */
export function bookingLink(url: string | null): string | null {
  const safe = safeLink(url)
  if (!safe) return null
  try {
    const link = new URL(safe)
    const adults = link.searchParams.get('group_adults')
    if (adults) link.searchParams.set('no_rooms', adults)
    return link.toString()
  } catch { return safe }
}

export function linkFractionLeft(checkedAt: string | null, validMinutes: number, now: number): number {
  if (!checkedAt) return 0
  const left = new Date(checkedAt).getTime() + validMinutes * 60000 - now
  return Math.min(Math.max(left / (validMinutes * 60000), 0), 1)
}

export function priceChange(price: string | null, previous: string | null): { price: number; previous: number; difference: number } | null {
  if (!price || !previous) return null
  const difference = Math.round((Number(price) - Number(previous)) * 100) / 100
  return difference === 0 ? null : { price: Number(price), previous: Number(previous), difference }
}


export function canPressGenerate(conflicts: GroupConflicts | null, generating: boolean): boolean {
  return conflicts?.can_generate === true && !generating
}
