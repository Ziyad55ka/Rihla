import { authenticatedRequest } from './http'
import type { BudgetStatus, GeneratedProposals, GroupConflicts, ConflictCategory, StoredProposals } from '../types/proposal'

// Generation searches and asks the AI several times, so it can take minutes.
const GENERATION_TIMEOUT_MS = 10 * 60 * 1000

const path = (tripId: string, part: string) => `/api/trips/${encodeURIComponent(tripId)}/${part}` as const

export const getConflicts = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<GroupConflicts>(path(tripId, 'conflicts'), { signal })

export const getProposals = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<StoredProposals>(path(tripId, 'proposals'), { signal })

export const generateProposals = (tripId: string, regenerate: boolean) =>
  authenticatedRequest<GeneratedProposals>(path(tripId, 'proposals'), {
    method: 'POST', body: { regenerate }, timeoutMs: GENERATION_TIMEOUT_MS,
  })

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
  includes_unconfirmed: 'Within budget, with unconfirmed prices',
  over_group_budget: 'Over the group budget',
}

export function canPressGenerate(conflicts: GroupConflicts | null, generating: boolean): boolean {
  return conflicts?.can_generate === true && !generating
}
