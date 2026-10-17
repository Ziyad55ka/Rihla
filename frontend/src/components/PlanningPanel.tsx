import { useEffect, useState } from 'react'
import { calendarDate, getPlanningStatus, missingFieldLabels } from '../lib/planning'
import type { PlanningStatus } from '../types/planning'
import type { TripDetail } from '../types/trips'
import '../planning.css'

export function PlanningPanel({ trip, revision, onRefresh }: { trip: TripDetail; revision: number; onRefresh: () => void }) {
  const [status, setStatus] = useState<PlanningStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    setBusy(true)
    getPlanningStatus(trip.id, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setStatus(result); setError('') } })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not check planning status.') })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [trip.id, revision])
  return <section className="planning-panel" aria-labelledby="planning-title">
    <div className="planning-heading"><div><p className="trip-eyebrow">ONE STEP CLOSER TO GOING</p><h2 id="planning-title">Find your common ground.</h2></div><button type="button" className="trip-text-button" disabled={busy} onClick={onRefresh}>{busy ? 'Checking…' : 'Refresh planning'}</button></div>
    <p className="trip-field-note">Based on saved preferences. Updates after saving and checks for group changes every 15 seconds while this page is visible.</p>
    {error ? <p className="trip-feedback trip-feedback--error" role="alert">{error} Last results could not be refreshed. Try Refresh planning.</p>
      : !status ? <p className="trip-loading" role="status">Checking readiness and shared dates…</p>
      : <><div className="planning-cards">
        <section className="planning-card" aria-labelledby="own-readiness-title"><p className="trip-eyebrow">YOUR SAVED INPUTS</p><h3 id="own-readiness-title">Your readiness</h3><span className={`planning-badge planning-badge--${status.own_readiness.status.toLowerCase()}`}>{status.own_readiness.status}</span>
          {status.own_readiness.status === 'Ready' ? <p>Your required information is complete. You can keep editing your preferences.</p> : <><p>Complete these fields in your preferences:</p><ul>{status.own_readiness.missing_fields.map((field) => <li key={field}>{missingFieldLabels[field]}</li>)}</ul></>}
          <p className="trip-field-note">Optional preferences do not affect readiness.</p></section>
        <section className="planning-card" aria-labelledby="shared-dates-title"><p className="trip-eyebrow">THE WHOLE GROUP, INCLUDING THE ADMINISTRATOR</p><h3 id="shared-dates-title">Shared travel dates</h3>
          {status.shared_dates.status === 'pending' ? <><span className="planning-badge">Waiting for dates</span><p>Everyone needs to save both availability dates before we can find your shared travel period.</p></>
            : status.shared_dates.status === 'conflict' ? <><span className="planning-badge planning-badge--conflict">No shared dates</span><p>Everyone has saved dates, but the ranges do not overlap. Discuss alternatives and update your own dates.</p><p className="trip-field-note">Members can be Ready even when their dates conflict.</p></>
              : <><span className="planning-badge planning-badge--ready">Shared dates found</span><p className="planning-date-range">{calendarDate(status.shared_dates.start)} <span>to</span> {calendarDate(status.shared_dates.end)}</p><p><strong>{status.shared_dates.duration_days} {status.shared_dates.duration_days === 1 ? 'day' : 'days'}</strong>, counting both dates.</p><p className="trip-field-note">This is the overlap of everyone’s saved availability.</p></>}
        </section></div>
        {trip.role === 'administrator' && status.member_readiness && <section className="planning-admin" aria-labelledby="group-readiness-title"><div className="trip-panel-title"><h3 id="group-readiness-title">Group readiness</h3><span>{status.member_readiness.filter((member) => member.status === 'Ready').length} of {status.member_readiness.length} Ready</span></div><p className="trip-field-note">As administrator, you can see status only. Everyone’s detailed inputs and missing fields stay private.</p><ul>{status.member_readiness.map((member) => <li key={member.user_id}><span>{trip.members.find((person) => person.user_id === member.user_id)?.display_name ?? 'Trip member'}</span><span className={`planning-badge planning-badge--${member.status.toLowerCase()}`}>{member.status}</span></li>)}</ul></section>}
      </>}
  </section>
}
