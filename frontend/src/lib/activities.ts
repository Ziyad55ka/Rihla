import type { Activity, ActivityFocus, ActivityProposalEstimate, ActivitySelections, CityStay, EstimateComponent, Proposal, SarPrice } from '../types/proposal'
import { authenticatedRequest } from './http'

const path = (proposal: Proposal) => `/api/trips/${encodeURIComponent(proposal.trip_id)}/proposals/${encodeURIComponent(proposal.id)}/activities/selection` as const

export interface SelectionStore {
  load(proposal: Proposal, signal?: AbortSignal): Promise<ActivitySelections>
  save(proposal: Proposal, ids: string[]): Promise<ActivitySelections>
}

export function validateSelection(proposal: Proposal, ids: string[]): string[] {
  const known = new Set(proposal.cities.flatMap(city => (city.activities ?? []).filter(activity => isActivitySuitable(proposal, city, activity)).map(activity => activity.id)))
  if (new Set(ids).size !== ids.length || ids.some(id => !known.has(id))) throw new Error('Select valid activities from this proposal.')
  return ids
}

export const activityApi: SelectionStore = {
  load: (proposal, signal) => authenticatedRequest<ActivitySelections>(path(proposal), { signal }),
  save: (proposal, ids) => authenticatedRequest<ActivitySelections>(path(proposal), {
    method: 'PUT', body: { version: proposal.version, activity_ids: validateSelection(proposal, ids) },
  }),
}

export function isActivitySuitable(proposal: Proposal, city: CityStay, activity: Activity): boolean {
  const value = activity.scheduled_date.value
  if (value === null) return true
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) return false
  const arrival = new Date(`${proposal.start_date}T00:00:00Z`)
  arrival.setUTCDate(arrival.getUTCDate() + proposal.cities.filter(stay => stay.order < city.order).reduce((sum, stay) => sum + stay.nights, 0))
  const departure = new Date(arrival)
  departure.setUTCDate(departure.getUTCDate() + city.nights)
  const flightArrival = proposal.flights[0]?.legs.find(leg => leg.direction === 'outbound')?.arrival_time?.slice(0, 10)
  const home = proposal.flights[0]?.legs.find(leg => leg.direction === 'return')?.departure_time
  const earlyHome = home?.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):/)
  return parsed >= arrival && parsed <= departure && value <= proposal.end_date && (!flightArrival || value >= flightArrival) && (!earlyHome || Number(earlyHome[2]) >= 12 || value < earlyHome[1])
}

const money = (halalas: bigint) => `${halalas / 100n}.${(halalas % 100n).toString().padStart(2, '0')}`
const halalas = (value: string) => {
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
}

function component(items: { price: SarPrice; quantity: number }[]): EstimateComponent {
  let amount = 0n, missing_items = 0, unconfirmed_items = 0, estimated_items = 0
  for (const { price, quantity } of items) {
    if (!quantity) continue
    if (price.amount_sar === null || !/^\d+(\.\d{1,2})?$/.test(price.amount_sar)) { missing_items++; continue }
    amount += halalas(price.amount_sar) * BigInt(quantity)
    if (price.status === 'Unconfirmed') unconfirmed_items++
    if (price.status === 'Estimated') estimated_items++
  }
  return { known_amount_sar: money(amount), missing_items, unconfirmed_items, estimated_items }
}

function activityComponent(proposal: Proposal, ids: string[]): EstimateComponent {
  // Keep old saved costs readable so an unsuitable selection can be removed.
  // Saving still validates the dates through validateSelection and the API.
  const known = new Set(proposal.cities.flatMap(city => (city.activities ?? []).map(a => a.id)))
  if (new Set(ids).size !== ids.length || ids.some(id => !known.has(id))) throw new Error('Select valid activities from this proposal.')
  const selected = new Set(ids)
  return component(proposal.cities.flatMap(city => (city.activities ?? []).filter(a => selected.has(a.id)).map(a => ({ price: a.price_per_person, quantity: 1 }))))
}

/** Legacy subtotal helper retained for downstream consumers. */
export function selectedActivityCost(proposal: Proposal, ids: string[]) {
  const part = activityComponent(proposal, ids)
  return { amount_sar: part.known_amount_sar, unknown: part.missing_items }
}

export function combineEstimateComponents(parts: EstimateComponent[]): EstimateComponent {
  return {
    known_amount_sar: money(parts.reduce((sum, part) => sum + halalas(part.known_amount_sar), 0n)),
    missing_items: parts.reduce((sum, part) => sum + part.missing_items, 0),
    unconfirmed_items: parts.reduce((sum, part) => sum + part.unconfirmed_items, 0),
    estimated_items: parts.reduce((sum, part) => sum + part.estimated_items, 0),
  }
}

/** US-12-AC03: same per-person calculation as the backend estimate service. */
export function activityProposalEstimate(proposal: Proposal, ids: string[], mealsPerDaySar = '150.00'): ActivityProposalEstimate {
  const flights = component(proposal.flights.length === 1 ? [{ price: proposal.flights[0].price_per_person, quantity: 1 }] : [])
  if (proposal.flights.length !== 1 || proposal.flights[0].trip_type === 'one_way') flights.missing_items++
  const accommodation = component(proposal.cities.map(city => ({ price: city.hotel_price_per_night, quantity: city.nights })))
  const transport = component(proposal.intercity_transport.map(leg => ({ price: leg.price_per_person, quantity: 1 })))
  const activities = activityComponent(proposal, ids)
  const days = Math.round((Date.parse(proposal.end_date) - Date.parse(proposal.start_date)) / 86400000) + 1
  const meals = component([{ price: { amount_sar: mealsPerDaySar, status: 'Unconfirmed', evidence: [] }, quantity: days }])
  // The server supplies its configured allowance in estimate.meals. This helper
  // is for legacy/demo responses without an estimate and accepts that setting.
  const parts = [flights, accommodation, transport, meals, activities]
  const total = combineEstimateComponents(parts)
  return { proposal_id: proposal.id, version: proposal.version, currency: 'SAR', flights, accommodation, transport, meals, activities, total }
}

/** Short labels for the group-interest tags shown on activity cards. */
export const focusLabels: Record<ActivityFocus, string> = {
  landmarks: 'Landmarks',
  museums_history: 'Museums and history',
  culture_arts: 'Culture and arts',
  food: 'Food',
  nature_outdoors: 'Nature',
  beaches_water: 'Beaches and the sea',
  shopping: 'Shopping',
  family_fun: 'Family fun',
  adventure_sports: 'Adventure',
  wellness_spa: 'Wellness',
  events_festivals: 'Festivals and events',
}

export type Mode = 'choose' | 'review' | 'confirmed'
/** Nothing saved: choose. Saved: review the own list. Confirmed: locked list. */
export const modeFor = (savedCount: number, confirmed: boolean, justSaved = false): Mode =>
  justSaved ? 'review' : confirmed ? 'confirmed' : savedCount === 0 ? 'choose' : 'review'

export const selectionFingerprint = (ids: string[]): string => JSON.stringify([...new Set(ids)].sort())

/** Suggestions are listed only with a photo of the place, over HTTPS. */
export function hasActivityPhoto(activity: Activity): boolean {
  const https = (value: string | null | undefined) => { try { return new URL(value ?? '').protocol === 'https:' } catch { return false } }
  return https(activity.image?.url) || https(activity.image_url)
}
