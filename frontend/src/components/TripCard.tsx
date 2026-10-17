import { useEffect, useState } from 'react'
import { getTrip } from '../lib/trips'
import { getPlanningStatus } from '../lib/planning'
import { navigate } from '../lib/navigation'
import { tripStage } from '../lib/trip-stage'
import type { PlanningStatus } from '../types/planning'
import type { TripDetail, TripSummary } from '../types/trips'

export function TripCard({ trip, index, revision }: { trip: TripSummary; index: number; revision: number }) {
  const [detail, setDetail] = useState<TripDetail | null>(null)
  const [planning, setPlanning] = useState<PlanningStatus | null>(null)
  const [namesError, setNamesError] = useState(false)
  const [planningError, setPlanningError] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    void getTrip(trip.id, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setDetail(value); setNamesError(false) } })
      .catch(() => { if (!controller.signal.aborted) setNamesError(true) })
    void getPlanningStatus(trip.id, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setPlanning(value); setPlanningError(false) } })
      .catch(() => { if (!controller.signal.aborted) setPlanningError(true) })
    return () => controller.abort()
  }, [trip.id, revision])
  const stage = planning && !planningError ? tripStage(planning) : null
  return <button type="button" className="trip-card" onClick={() => navigate(`/trips/${trip.id}`)} aria-label={`Open ${trip.title}`}>
    <div className="trip-card-top"><span className="trip-card-number">TRIP / {(index + 1).toString().padStart(2, '0')}</span><span className="trip-role">{trip.role === 'administrator' ? 'Admin' : 'Member'}</span></div>
    <h3>{trip.title}</h3>
    <p className="trip-card-description">{trip.description || 'A new place. Your favourite people.'}</p>
    <div className="trip-card-people"><div className="trip-avatar-stack" aria-hidden="true">{(detail?.members ?? []).slice(0, 3).map((member) => <span key={member.user_id}>{member.display_name.slice(0, 1).toUpperCase()}</span>)}</div>
      <div><span className="trip-card-label">YOUR PEOPLE</span><p>{namesError ? 'Member names could not be refreshed' : detail ? detail.members.map((member) => member.display_name).join(', ') : 'Loading members…'}</p></div></div>
    <div className={`trip-card-stage trip-card-stage--${stage?.key ?? 'loading'}`}><span className="trip-stage-dot" aria-hidden="true" /><span>{planningError ? 'Planning status unavailable' : stage?.label ?? 'Checking your plan…'}</span></div>
    <div className="trip-card-footer"><span>{stage?.detail ?? 'Open the trip for details and a fresh check.'}</span><span className="trip-card-arrow" aria-hidden="true">↗</span></div>
  </button>
}
