export type Importance = 'Essential' | 'Flexible'
export type OptionalPreference = { value: string; importance: Importance }
export type MemberPreferences = {
  departure_city: string
  max_budget_sar: string | null
  available_start: string | null
  available_end: string | null
  destinations: OptionalPreference
  interests: OptionalPreference
  flights: OptionalPreference
  accommodation: OptionalPreference
}
export type SavedPreferences = MemberPreferences & { currency: 'SAR'; updated_at: string | null }
