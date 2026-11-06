import { authenticatedRequest } from './http'
import type { MemberPreferences, SavedPreferences } from '../types/preferences'

export const INTEREST_FOCUS = [
  'adventure_sports',
  'beaches_water',
  'landmarks',
  'museums_history',
  'events_festivals',
  'food',
  'nature_outdoors',
  'family_fun',
] as const

export type InterestFocus = typeof INTEREST_FOCUS[number]

const INTEREST_PREFIX = 'focus:'
const NOTES_SEPARATOR = '; ' + 'notes:'

/** Keep the existing private preference column while giving the backend stable tags. */
export function parseInterestPreference(value: string): { focus: InterestFocus[]; notes: string } {
  if (!value.startsWith(INTEREST_PREFIX)) return { focus: [], notes: value }
  const body = value.slice(INTEREST_PREFIX.length)
  const separator = body.indexOf(NOTES_SEPARATOR)
  const encodedFocus = separator < 0 ? body : body.slice(0, separator)
  const notes = separator < 0 ? '' : body.slice(separator + NOTES_SEPARATOR.length)
  const allowed = new Set<string>(INTEREST_FOCUS)
  const focus = encodedFocus.split(',').filter((item): item is InterestFocus => allowed.has(item))
  return { focus: [...new Set(focus)], notes }
}

export function formatInterestPreference(focus: InterestFocus[], notes: string): string {
  const unique = INTEREST_FOCUS.filter((item) => focus.includes(item))
  // Preserve spaces/newlines during controlled-input editing. Trimming on each
  // keystroke made it impossible to type a space at the end of a word.
  if (unique.length === 0) return notes
  return `${INTEREST_PREFIX}${unique.join(',')}${NOTES_SEPARATOR}${notes}`
}

export const getPreferences = (tripId: string, signal?: AbortSignal) =>
  authenticatedRequest<SavedPreferences>(`/api/trips/${encodeURIComponent(tripId)}/preferences`, { signal })

export const savePreferences = (tripId: string, preferences: MemberPreferences) =>
  authenticatedRequest<SavedPreferences>(`/api/trips/${encodeURIComponent(tripId)}/preferences`, { method: 'PUT', body: preferences })

// Build the editable payload explicitly: response metadata/identity must not be submitted.
export function editablePreferences(saved: SavedPreferences): MemberPreferences {
  return {
    departure_city: saved.departure_city, max_budget_sar: saved.max_budget_sar,
    available_start: saved.available_start, available_end: saved.available_end,
    destinations: { ...saved.destinations }, interests: { ...saved.interests },
    flights: { ...saved.flights }, accommodation: { ...saved.accommodation },
  }
}

export function preferencesForForm(saved: SavedPreferences): MemberPreferences {
  const preferences = editablePreferences(saved)
  if (saved.updated_at) return preferences
  return {
    ...preferences,
    destinations: { ...preferences.destinations, importance: 'Essential' },
    interests: { ...preferences.interests, importance: 'Essential' },
    flights: { ...preferences.flights, importance: 'Essential' },
    accommodation: { ...preferences.accommodation, importance: 'Essential' },
  }
}

export function preferenceError(values: MemberPreferences): string | null {
  if (!values.departure_city.trim() || !values.max_budget_sar?.trim() || !values.available_start || !values.available_end) {
    return 'Fill in departure city, maximum budget and both travel dates before saving.'
  }
  if (values.max_budget_sar !== null && (!/^\d+(\.\d{1,2})?$/.test(values.max_budget_sar) || Number(values.max_budget_sar) <= 0 || Number(values.max_budget_sar) >= 10000000000)) {
    return 'Enter a budget greater than 0 and below 10,000,000,000 SAR, with up to 2 decimal places.'
  }
  if (values.available_start && values.available_end && values.available_start > values.available_end) {
    return 'End date must be on or after start date.'
  }
  return null
}
