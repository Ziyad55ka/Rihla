export type Readiness = 'Ready' | 'Incomplete'
export type MissingField = 'departure_city' | 'max_budget_sar' | 'available_start' | 'available_end'
export type PlanningStatus = {
  all_members_ready: boolean
  own_readiness: { status: Readiness; missing_fields: MissingField[]; has_saved_preferences: boolean }
  member_readiness: { user_id: string; status: Readiness }[] | null
  member_dates: { user_id: string; available_start: string | null; available_end: string | null }[]
  shared_dates:
    | { status: 'pending'; start: null; end: null; duration_days: null }
    | { status: 'conflict'; start: null; end: null; duration_days: null }
    | { status: 'available'; start: string; end: string; duration_days: number }
}
