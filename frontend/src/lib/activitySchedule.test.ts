import { describe, expect, it } from 'vitest'
import { buildActivitySchedule, suggestDailyPlan } from './activitySchedule'
import { selectedActivityCost } from './activities'
import data from '../test-fixtures/activities.json'
import type { ProposalSet } from '../types/proposal'

const [proposal, multi] = (data as ProposalSet).proposals

describe('one visit per activity', () => {
  it('distributes choices once across days and leaves the actual event on its date', () => {
    const ids = proposal.cities[0].activities!.map(a => a.id)
    const plan = buildActivitySchedule(proposal, [...ids, ids[0]])
    const visits = plan.days.flatMap(day => day.visits)
    expect(visits.map(v => v.activity.id).sort()).toEqual([...ids].sort())
    expect(plan.days.find(day => day.date === '2026-11-21')!.visits.some(v => v.activity.scheduled_date.value === '2026-11-21')).toBe(true)
    expect(plan.days).toHaveLength(5)
    expect(plan.unscheduled).toBe(0)
    // Visiting on five days never multiplies four single admissions by five.
    expect(selectedActivityCost(proposal, visits.map(v => v.activity.id))).toEqual(selectedActivityCost(proposal, ids))
  })
  it('never puts a visit before its city arrival or repeats it on a transfer day', () => {
    const ids = multi.cities.flatMap(c => c.activities!.map(a => a.id))
    const plan = buildActivitySchedule(multi, ids)
    expect(plan.days.flatMap(day => day.visits)).toHaveLength(ids.length)
    expect(plan.days.filter(day => day.date < '2026-11-23').flatMap(day => day.visits).every(v => v.city.city !== 'Batumi')).toBe(true)
    expect(plan.unscheduled).toBe(0)
  })
  it('rejects an out-of-stay event from the proposed calendar instead of moving its date', () => {
    const p = structuredClone(proposal)
    const event = p.cities[0].activities![2]
    event.scheduled_date.value = '2027-01-01'
    const plan = buildActivitySchedule(p, [event.id])
    expect(plan.unscheduled).toBe(1)
    expect(plan.days.flatMap(day => day.visits)).toHaveLength(0)
  })
  it('handles one-day trips and leap days without timezone shifts', () => {
    const p = structuredClone(proposal)
    p.start_date = p.end_date = '2028-02-29'
    p.cities[0].nights = 0
    const id = p.cities[0].activities![0].id
    const plan = buildActivitySchedule(p, [id])
    expect(plan.days.map(day => day.date)).toEqual(['2028-02-29'])
    expect(plan.days[0].visits.map(v => v.activity.id)).toEqual([id])
    expect(plan.unscheduled).toBe(0)
  })
  it('keeps the overnight flight day and an early return free of flexible visits', () => {
    const p = structuredClone(proposal)
    p.flights[0].legs[0].arrival_time = '2026-11-21T10:50:00'
    p.flights[0].legs[1].departure_time = '2026-11-24T01:15:00'
    const id = p.cities[0].activities![0].id
    const plan = buildActivitySchedule(p, [id])
    expect(plan.days[0].visits).toHaveLength(0)
    expect(plan.days[0].travel).toBe(true)
    expect(plan.days.at(-1)!.visits).toHaveLength(0)
    expect(plan.days.at(-1)!.travel).toBe(true)
    expect(plan.days.find(day => day.date === '2026-11-21')!.visits[0].activity.id).toBe(id)
  })
})

describe('suggestDailyPlan', () => {
  it('fills each visiting day once, keeps own choices and skips photo-less suggestions', () => {
    const proposal = structuredClone((data as unknown as ProposalSet).proposals[0])
    const all = proposal.cities.flatMap(city => city.activities ?? [])
    const noPhoto = all.find(a => !a.scheduled_date.value)!
    const ids = suggestDailyPlan(proposal, [], a => a.id !== noPhoto.id)
    expect(ids.length).toBeGreaterThan(0)
    expect(ids).not.toContain(noPhoto.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.every(id => !all.find(a => a.id === id)!.scheduled_date.value)).toBe(true)
    expect(buildActivitySchedule(proposal, ids).unscheduled).toBe(0)
    // The member's own choice stays.
    expect(suggestDailyPlan(proposal, [noPhoto.id], () => false)).toEqual([noPhoto.id])
  })
})
