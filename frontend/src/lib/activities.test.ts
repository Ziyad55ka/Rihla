import { describe, expect, it } from 'vitest'
import { mockSelectionStore, selectedActivityCost, validateSelection } from './activities'
import data from '../data/activities.mock.json'
import type { ProposalSet } from '../types/proposal'

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
    expect(selectedActivityCost(proposal, activities.map(a => a.id))).toEqual({ amount_sar: '85.50', unknown: 1 })
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
