import type { PlanningStatus } from '../types/planning'

export type TripStage = { key: 'you' | 'members' | 'conflict' | 'ai'; label: string; detail: string }

export function tripStage(status: PlanningStatus): TripStage {
  if (status.shared_dates.status === 'conflict') return {
    key: 'conflict', label: 'Dates do not overlap', detail: 'Update your dates to find a shared travel window.',
  }
  if (status.own_readiness.status === 'Incomplete') return {
    key: 'you', label: 'Waiting for your preferences', detail: 'Add your travel essentials to move the plan forward.',
  }
  if (status.all_members_ready === true && status.shared_dates.status === 'available') return {
    key: 'ai', label: 'Waiting for AI generation', detail: 'Your group is ready. AI planning arrives in Sprint 2.',
  }
  return { key: 'members', label: 'Waiting for members’ preferences', detail: 'Your part is done. Give your people a little time.' }
}
