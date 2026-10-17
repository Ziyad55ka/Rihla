export type TripRole = 'administrator' | 'member'
export interface TripSummary { id: string; title: string; description: string; created_at: string; role: TripRole; member_count: number }
export interface TripMember { user_id: string; display_name: string; role: TripRole; joined_at: string }
export interface TripDetail extends TripSummary { members: TripMember[] }
export interface InvitationStatus { exists: boolean; expires_at: string | null; revoked: boolean }
export interface InvitationCreated { token: string; code: string; expires_at: string }
export interface JoinResult { trip: TripDetail; already_member: boolean }
