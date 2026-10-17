export type Readiness = 'Ready' | 'Incomplete'
export type MissingField = 'departure_city' | 'max_budget_sar' | 'available_start' | 'available_end'
export type PlanningStatus = {
  own_readiness: { status: Readiness; missing_fields: MissingField[] }
  member_readiness: { user_id: string; status: Readiness }[] | null
  shared_dates:
    | { status: 'pending'; start: null; end: null; duration_days: null }
    | { status: 'conflict'; start: null; end: null; duration_days: null }
    | { status: 'available'; start: string; end: string; duration_days: number }
}
