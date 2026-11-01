import type { ActivitySelections, Proposal } from '../types/proposal'
import { authenticatedRequest } from './http'

const path = (proposal: Proposal) => `/api/trips/${encodeURIComponent(proposal.trip_id)}/proposals/${encodeURIComponent(proposal.id)}/activities/selection` as const

export interface SelectionStore {
  load(proposal: Proposal, signal?: AbortSignal): Promise<ActivitySelections>
  save(proposal: Proposal, ids: string[]): Promise<ActivitySelections>
}

export function validateSelection(proposal: Proposal, ids: string[]): string[] {
  const known = new Set(proposal.cities.flatMap(city => (city.activities ?? []).map(activity => activity.id)))
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
  const result = (p: Proposal, ids: string[]): ActivitySelections => ({ proposal_id: p.id, version: p.version, activity_ids: ids })
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

/** Integer halalas avoid decimal rounding. Missing prices never become free. */
export function selectedActivityCost(proposal: Proposal, ids: string[]) {
  validateSelection(proposal, ids)
  const selected = new Set(ids)
  let halalas = 0, unknown = 0
  for (const activity of proposal.cities.flatMap(city => city.activities ?? [])) {
    if (!selected.has(activity.id)) continue
    const raw = activity.price_per_person.amount_sar
    if (raw === null) { unknown++; continue }
    if (!/^\d+(\.\d{1,2})?$/.test(raw)) { unknown++; continue }
    const [whole, fraction = ''] = raw.split('.')
    halalas += Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  }
  return { amount_sar: (halalas / 100).toFixed(2), unknown }
}
