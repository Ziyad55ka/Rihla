import { describe, expect, it } from 'vitest'
import { activityProposalEstimate, isActivitySuitable, selectedActivityCost, validateSelection } from './activities'
import data from '../test-fixtures/activities.json'
import type { Proposal, ProposalSet, ActivitySelections } from '../types/proposal'

const [proposal, other] = (data as ProposalSet).proposals
const activities = proposal.cities[0].activities!

describe('activity selections', () => {
  it('keeps saved selections after reopening, and isolates options and versions', async () => {
    const values = new Map<string, string>()
    const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) } }
    await mockSelectionStore(storage).save(proposal, [activities[0].id])
    const store = mockSelectionStore(storage)
    expect((await store.load(proposal)).activity_ids).toEqual([activities[0].id])
    expect((await store.load(other)).activity_ids).toEqual([])
    expect((await store.load({ ...proposal, version: 2 })).activity_ids).toEqual([])
    await store.save(proposal, [])
    expect((await store.load(proposal)).activity_ids).toEqual([])
  })
  it('rejects foreign ids, duplicates and damaged saved data', async () => {
    expect(() => validateSelection(proposal, ['foreign'])).toThrow()
    expect(() => validateSelection(proposal, [activities[0].id, activities[0].id])).toThrow()
    await expect(mockSelectionStore({ getItem: () => '{}', setItem: () => {} }).load(proposal)).rejects.toThrow()
  })
  it('reports unknown prices separately from free activities and sums exact halalas', () => {
    expect(selectedActivityCost(proposal, activities.map(a => a.id))).toEqual({ amount_sar: '150.50', unknown: 1 })
    expect(selectedActivityCost(proposal, [activities[1].id])).toEqual({ amount_sar: '0.00', unknown: 0 })
    expect(selectedActivityCost(proposal, [])).toEqual({ amount_sar: '0.00', unknown: 0 })
  })
  it('supports legacy proposals without activities and reports blocked storage', async () => {
    const legacy = { ...proposal, cities: proposal.cities.map(city => ({ ...city, activities: undefined })) }
    expect(selectedActivityCost(legacy, [])).toEqual({ amount_sar: '0.00', unknown: 0 })
    const store = mockSelectionStore({ getItem: () => null, setItem: () => { throw new Error('blocked') } })
    await expect(store.save(proposal, [activities[0].id])).rejects.toThrow('blocked')
  })
})

describe('US-12 proposal estimate integration', () => {
  it('adds and removes selected activities from the full proposal total without counting flight legs twice', () => {
    const baseline = activityProposalEstimate(proposal, [])
    expect(baseline.total.known_amount_sar).toBe('3000.00')
    const chosen = activityProposalEstimate(proposal, [activities[0].id, activities[3].id])
    expect(chosen.activities.known_amount_sar).toBe('150.50')
    expect(chosen.total.known_amount_sar).toBe('3150.50')
    expect(activityProposalEstimate(proposal, [activities[3].id]).total.known_amount_sar).toBe('3065.00')
    expect(activityProposalEstimate(proposal, []).total.known_amount_sar).toBe('3000.00')
  })
  it('persists the relevant estimate on explicit save and reload', async () => {
    const values = new Map<string, string>()
    const store = mockSelectionStore({ getItem: key => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value) } })
    expect((await store.load(proposal)).estimate?.total.known_amount_sar).toBe('3000.00')
    await store.save(proposal, [activities[3].id])
    expect((await store.load(proposal)).estimate?.total.known_amount_sar).toBe('3065.00')
    await store.save(proposal, [])
    expect((await store.load(proposal)).estimate?.total.known_amount_sar).toBe('3000.00')
  })
  it('never replaces missing costs with confirmed zero and marks missing return flights', () => {
    const unknown = activityProposalEstimate(proposal, [activities[2].id])
    expect(unknown.activities.missing_items).toBe(1)
    expect(unknown.total.missing_items).toBe(1)
    expect(activityProposalEstimate({ ...proposal, flights: [] }, []).total.missing_items).toBe(1)
    const oneWay = structuredClone(proposal)
    oneWay.flights[0].trip_type = 'one_way'
    expect(activityProposalEstimate(oneWay, []).flights.missing_items).toBe(1)
  })
  it('does not allow an event outside its city stay to be selected', () => {
    const changed = structuredClone(proposal)
    const city = changed.cities[0], event = city.activities![2]
    event.scheduled_date.value = '2027-01-01'
    expect(isActivitySuitable(changed, city, event)).toBe(false)
    expect(() => validateSelection(changed, [event.id])).toThrow()
  })
})

export function mockSelectionStore(storage: Pick<Storage, 'getItem' | 'setItem'>) {
  const key = (p: Proposal) => `rihla.demo.activities:${p.trip_id}:${p.id}:${p.version}`
  const result = (p: Proposal, ids: string[]): ActivitySelections => ({ proposal_id: p.id, version: p.version, activity_ids: ids, estimate: activityProposalEstimate(p, ids) })
  return {
    async load(p: Proposal) {
      const raw = storage.getItem(key(p))
      if (raw === null) return result(p, [])
      const ids: unknown = JSON.parse(raw)
      if (!Array.isArray(ids) || !ids.every(id => typeof id === 'string')) throw new Error('Could not load activity selections.')
      return result(p, validateSelection(p, ids))
    },
    async save(p: Proposal, ids: string[]) {
      validateSelection(p, ids)
      storage.setItem(key(p), JSON.stringify(ids))
      return result(p, ids)
    },
  }
}

