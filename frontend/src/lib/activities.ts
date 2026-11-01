import type { Activity, ActivityProposalEstimate, ActivitySelections, CityStay, EstimateComponent, Proposal, SarPrice } from '../types/proposal'
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

// Demo-only browser storage. No real users, tokens, AI calls or database writes.
export function mockSelectionStore(storage: Pick<Storage, 'getItem' | 'setItem'>): SelectionStore {
  const key = (p: Proposal) => `rihla.demo.activities:${p.trip_id}:${p.id}:${p.version}`
  const result = (p: Proposal, ids: string[]): ActivitySelections => ({ proposal_id: p.id, version: p.version, activity_ids: ids, estimate: activityProposalEstimate(p, ids) })
  return {
    async load(p) {
      const raw = storage.getItem(key(p))
      if (raw === null) return result(p, [])
      const ids: unknown = JSON.parse(raw)
      if (!Array.isArray(ids) || !ids.every(id => typeof id === 'string')) throw new Error('Could not load activity selections.')
      return result(p, validateSelection(p, ids))
    },
    async save(p, ids) {
      validateSelection(p, ids)
      storage.setItem(key(p), JSON.stringify(ids))
      return result(p, ids)
    },
  }
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
  return parsed >= arrival && parsed <= departure && value <= proposal.end_date
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
  validateSelection(proposal, ids)
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
export function activityProposalEstimate(proposal: Proposal, ids: string[]): ActivityProposalEstimate {
  const flights = component(proposal.flights.length === 1 ? [{ price: proposal.flights[0].price_per_person, quantity: 1 }] : [])
  if (proposal.flights.length !== 1 || proposal.flights[0].trip_type === 'one_way') flights.missing_items++
  const accommodation = component(proposal.cities.map(city => ({ price: city.hotel_price_per_night, quantity: city.nights })))
  const transport = component(proposal.intercity_transport.map(leg => ({ price: leg.price_per_person, quantity: 1 })))
  const activities = activityComponent(proposal, ids)
  const parts = [flights, accommodation, transport, activities]
  const total = combineEstimateComponents(parts)
  return { proposal_id: proposal.id, version: proposal.version, currency: 'SAR', flights, accommodation, transport, activities, total }
}
