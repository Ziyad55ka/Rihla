import { authenticatedRequest } from './http'
import type { Language } from './language'
import type { BudgetStatus, GeneratedProposals, GroupConflicts, ConflictCategory, InfoStatus, Proposal, StoredProposals } from '../types/proposal'

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

export const statusLabels: Record<InfoStatus, string> = {
  Sourced: 'From a source',
  Estimated: 'Estimated',
  Unconfirmed: 'Unconfirmed · Check before booking',
  'Not available': 'Not available',
}

export function proposalTitle(proposal: Proposal, language: Language): string {
  return (language === 'ar' ? proposal.title_ar : proposal.title_en) ?? proposal.title
}

// Saved data comes from outside services, so only web addresses become links.
export function safeLink(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

function addDays(day: string, count: number): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + count)
  return date.toISOString().slice(0, 10)
}

/** Each stay's check-in and check-out, counted from the trip's first day. */
export function stayDates(proposal: Proposal): { start: string; end: string }[] {
  let start = proposal.start_date
  return proposal.cities.map((stay) => {
    const end = addDays(start, stay.nights)
    const dates = { start, end }
    start = end
    return dates
  })
}

export function canPressGenerate(conflicts: GroupConflicts | null, generating: boolean): boolean {
  return conflicts?.can_generate === true && !generating
}
