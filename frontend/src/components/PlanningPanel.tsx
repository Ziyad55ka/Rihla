import { useEffect, useState } from 'react'
import { calendarDate, getPlanningStatus, missingFieldLabels } from '../lib/planning'
import { tripStage } from '../lib/trip-stage'
import type { PlanningStatus } from '../types/planning'
import type { TripDetail } from '../types/trips'
import { InviteMembersControl } from './InviteMembersControl'
import '../planning.css'

function planningStage(status: PlanningStatus) {
  if (status.all_members_ready === undefined && status.own_readiness.status === 'Ready' && status.shared_dates.status !== 'conflict') return { title: 'Your part of the plan is ready.', label: 'Group readiness unavailable', copy: 'Your preferences are complete. Group readiness will appear when the latest planning update is available.' }
  const stage = tripStage(status)
  const titles = { you: 'Your preferences come first.', members: 'Good things take a little planning.', conflict: 'Let’s find dates that fit.', ai: 'Everyone’s on the same page.' }
  return { title: titles[stage.key], label: stage.label, copy: stage.detail }
}

export function PlanningPanel({ trip, revision, onRefresh, onPreferences }: { trip: TripDetail; revision: number; onRefresh: () => void; onPreferences: () => void }) {
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
  const current = !error ? status : null
  const stage = current ? planningStage(current) : null
  const hasSaved = current?.own_readiness.has_saved_preferences
  return <section className="planning-panel" aria-label="Trip planning">
    <section className="planning-overview" aria-labelledby="trip-overview-title">
      <div className="planning-overview-top">
        <div className="planning-overview-title"><p className="trip-eyebrow">YOUR NEXT ADVENTURE</p><h1 id="trip-overview-title">{trip.title}</h1>{trip.description && <p>{trip.description}</p>}</div>
        <span className="trip-role">{trip.role === 'administrator' ? 'You’re the administrator' : 'You’re a member'}</span>
      </div>
      <div className="planning-overview-details">
        <div className="planning-people-summary">
          <div className="planning-avatar-stack" aria-hidden="true">{trip.members.slice(0, 4).map((member, index) => <span className={`planning-member-avatar--${index % 3}`} key={member.user_id}>{member.display_name.slice(0, 1).toUpperCase()}</span>)}</div>
          <div><p className="trip-eyebrow">YOUR PEOPLE</p><p>{trip.members.map((member) => member.display_name).join(', ')}</p></div>
        </div>
        <div className="planning-status-summary">
          <p className="trip-eyebrow">TRIP STATUS</p>
          <span className="planning-stage-label">{stage?.label ?? (error ? 'Planning status unavailable' : 'Checking your group')}</span>
          <h2>{stage?.title ?? 'A little closer to somewhere new.'}</h2>
          <p>{stage?.copy ?? (error ? 'Refresh to see the latest planning status.' : 'Checking your saved preferences and the group’s shared travel dates…')}</p>
        </div>
        <div className="planning-date-summary" aria-labelledby="shared-dates-title">
          <p className="trip-eyebrow" id="shared-dates-title">SHARED TRAVEL DATES</p>
          {!current ? <p>{error ? 'Dates unavailable' : 'Finding common dates…'}</p>
            : current.shared_dates.status === 'pending' ? <><span className="planning-badge">Waiting for dates</span><p>Waiting for everyone’s availability.</p></>
              : current.shared_dates.status === 'conflict' ? <><span className="planning-badge planning-badge--conflict">No shared dates</span><p>Update your dates to find an overlap.</p></>
                : <><span className="planning-badge planning-badge--ready">{current.shared_dates.duration_days} {current.shared_dates.duration_days === 1 ? 'day' : 'days'} together</span><p className="planning-date-range">{calendarDate(current.shared_dates.start)}<span>to</span>{calendarDate(current.shared_dates.end)}</p></>}
        </div>
      </div>
      <button type="button" className="planning-refresh" disabled={busy} onClick={onRefresh}>{busy ? 'Checking…' : 'Refresh trip information'} <span aria-hidden="true">↻</span></button>
    </section>
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{error} Try Refresh planning.</p>}
    <section className="planning-members" aria-labelledby="members-title">
      <div className="planning-members-heading"><div><p className="trip-eyebrow">YOUR TRAVEL CIRCLE</p><h2 id="members-title">Different people. One adventure.</h2><p>{trip.member_count} {trip.member_count === 1 ? 'person' : 'people'} making the plan together.</p></div>
        <div className="planning-members-actions"><button className="planning-preferences-button" type="button" onClick={onPreferences}>{hasSaved === true ? 'Edit preferences' : hasSaved === false ? 'Enter preferences' : 'Your preferences'} <span aria-hidden="true">↗</span></button>{trip.role === 'administrator' && <InviteMembersControl tripId={trip.id} />}</div>
      </div>
      {current?.own_readiness.status === 'Incomplete' && <p className="planning-own-note">For your readiness, add: {current.own_readiness.missing_fields.map((field) => missingFieldLabels[field]).join(', ')}. You can save your progress at any time.</p>}
      <ul className="planning-member-grid">{trip.members.map((member, index) => {
        const readiness = trip.role === 'administrator' ? current?.member_readiness?.find((value) => value.user_id === member.user_id)?.status : undefined
        return <li className="planning-member-card" key={member.user_id}>
          <div className="planning-member-card-top"><span className={`planning-member-avatar planning-member-avatar--${index % 3}`} aria-hidden="true">{member.display_name.slice(0, 1).toUpperCase()}</span><span className="planning-member-number" aria-hidden="true">{(index + 1).toString().padStart(2, '0')}</span></div>
          <h3>{member.display_name}</h3><p>{member.role === 'administrator' ? 'Trip administrator' : 'Trip member'}</p>
          {trip.role === 'administrator' && <div className="planning-member-readiness"><span>Preferences</span><span className={`planning-badge${readiness ? ` planning-badge--${readiness.toLowerCase()}` : ''}`}>{readiness ?? 'Unavailable'}</span></div>}
        </li>
      })}</ul>
      <p className="planning-privacy-note"><span aria-hidden="true">◇</span> Your preferences stay private. {trip.role === 'administrator' ? 'You can see each member’s readiness only.' : 'Your administrator can see readiness only.'}</p>
    </section>
  </section>
}
