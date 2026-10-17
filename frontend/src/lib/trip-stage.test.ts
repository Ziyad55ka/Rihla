import { expect, it } from 'vitest'
import { tripStage } from './trip-stage'
import type { PlanningStatus } from '../types/planning'

const status: PlanningStatus = {
  all_members_ready: true,
  own_readiness: { status: 'Ready', missing_fields: [], has_saved_preferences: true },
  member_readiness: null,
  shared_dates: { status: 'available', start: '2026-11-10', end: '2026-11-15', duration_days: 6 },
}
it('only shows the future AI stage when everyone is ready and dates overlap', () => {
  expect(tripStage(status).key).toBe('ai')
  expect(tripStage({ ...status, all_members_ready: false }).key).toBe('members')
  expect(tripStage({ ...status, shared_dates: { status: 'pending', start: null, end: null, duration_days: null } }).key).toBe('members')
})
it('asks the current user for essentials without reading other members’ private inputs', () => {
  expect(tripStage({ ...status, all_members_ready: false, own_readiness: { status: 'Incomplete', missing_fields: ['departure_city'], has_saved_preferences: true } }).key).toBe('you')
})
it('keeps date conflicts visible even when everyone is individually Ready', () => {
  expect(tripStage({ ...status, shared_dates: { status: 'conflict', start: null, end: null, duration_days: null } }).key).toBe('conflict')
})
