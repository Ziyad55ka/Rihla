import { expect, it } from 'vitest'
import { discoveryInterests } from './discovery'

it('turns answers into interests and soft wishes without inventing bookable destinations', () => {
  const result = discoveryInterests({ experience: 'beach', pace: 'relaxed', reach: 'nearby' })
  expect(result.focus).toEqual(['beaches_water', 'nature_outdoors'])
  expect(result.notes.join(' ')).toContain('when feasible')
  expect(result).not.toHaveProperty('price')
  expect(result).not.toHaveProperty('destination')
})

it('keeps surprise answers open to the group planner', () => {
  expect(discoveryInterests({ experience: 'surprise', pace: 'balanced', reach: 'anywhere' }).focus).toEqual([])
})
