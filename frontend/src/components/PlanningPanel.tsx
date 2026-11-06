import { useEffect, useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { FlyIcon } from './FlightIcons'
import { calendarDate, getPlanningStatus, missingFieldLabels } from '../lib/planning'
import { tripStage } from '../lib/trip-stage'
import type { PlanningStatus } from '../types/planning'
import type { TripDetail } from '../types/trips'
import { InviteMembersControl } from './InviteMembersControl'
import { ProposalsPanel } from './ProposalsPanel'
import { useLanguage } from '../lib/language'
import '../planning.css'

function planningStage(status: PlanningStatus) {
  if (status.all_members_ready === undefined && status.own_readiness.status === 'Ready' && status.shared_dates.status !== 'conflict') return { title: 'Your part of the plan is ready.', label: 'Group readiness unavailable', copy: 'Your preferences are complete. Group readiness will appear when the latest planning update is available.' }
  const stage = tripStage(status)
  const titles = { you: 'Add your travel essentials', members: 'Waiting for your group', conflict: 'Choose dates that overlap', ai: 'Ready to plan together' }
  return { title: titles[stage.key], label: stage.label, copy: stage.key === 'ai' ? 'Compare the trip options below, or update your preferences.' : stage.detail }
}

export function PlanningPanel({ trip, revision, onRefresh, onPreferences }: { trip: TripDetail; revision: number; onRefresh: () => void; onPreferences: () => void }) {
  const { t, locale } = useLanguage()
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
  return <section className="planning-panel" aria-label={t('Trip planning')}>
    <section className="planning-overview" aria-labelledby="trip-overview-title">
      <div className="planning-overview-top">
        <div className="planning-overview-title"><h1 id="trip-overview-title">{trip.title}</h1>{trip.description && <p>{trip.description}</p>}</div>
        <div className="planning-overview-actions"><span className="trip-role">{t(trip.role === 'administrator' ? 'You’re the administrator' : 'You’re a member')}</span><button className="planning-preferences-button" type="button" onClick={onPreferences}><SlidersHorizontal size={17} aria-hidden="true" />{hasSaved === true ? t('Edit preferences') : hasSaved === false ? t('Enter preferences') : t('Your preferences')}<FlyIcon /></button></div>
      </div>
      <div className="planning-overview-details">
        <div className="planning-people-summary">
          <div className="planning-avatar-stack" aria-hidden="true">{trip.members.slice(0, 4).map((member, index) => <span className={`planning-member-avatar--${index % 3}`} key={member.user_id}>{member.display_name.slice(0, 1).toUpperCase()}</span>)}</div>
          <div><p className="trip-eyebrow">{t('YOUR PEOPLE')}</p><p>{trip.members.map((member) => member.display_name).join(', ')}</p></div>
        </div>
        <div className="planning-status-summary">
          <p className="trip-eyebrow">{t('TRIP STATUS')}</p>
          <span className="planning-stage-label">{t(stage?.label ?? (error ? 'Planning status unavailable' : 'Checking your group'))}</span>
          <h2>{t(stage?.title ?? 'A little closer to somewhere new.')}</h2>
          <p>{t(stage?.copy ?? (error ? 'Refresh to see the latest planning status.' : 'Checking your saved preferences and the group’s shared travel dates…'))}</p>
        </div>
        <div className="planning-date-summary" aria-labelledby="shared-dates-title">
          <p className="trip-eyebrow" id="shared-dates-title">{t('SHARED TRAVEL DATES')}</p>
          {!current ? <p>{error ? t("Dates unavailable") : t("Finding common dates…")}</p>
            : current.shared_dates.status === 'pending' ? <><span className="planning-badge">{t("Waiting for dates")}</span><p>{t("Waiting for everyone’s availability.")}</p></>
              : current.shared_dates.status === 'conflict' ? <><span className="planning-badge planning-badge--conflict">{t("No shared dates")}</span><p>{t("Update your dates to find an overlap.")}</p></>
                : <><span className="planning-badge planning-badge--ready">{current.shared_dates.duration_days === 1 ? t('1 day together') : t('{count} days together', { count: current.shared_dates.duration_days.toLocaleString(locale) })}</span><p className="planning-date-range">{calendarDate(current.shared_dates.start, locale)}<span>{t("to")}</span>{calendarDate(current.shared_dates.end, locale)}</p></>}
        </div>
      </div>
      <button type="button" className="planning-refresh" disabled={busy} onClick={onRefresh}>{busy ? t("Checking…") : t("Refresh trip information")} <span aria-hidden="true">↻</span></button>
    </section>
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)} {t("Try Refresh planning.")}</p>}
    <ProposalsPanel tripId={trip.id} isAdmin={trip.role === 'administrator'} revision={revision} sharedDays={current?.shared_dates.status === 'available' ? current.shared_dates.duration_days : null} />
    <section className="planning-members" aria-labelledby="members-title">
      <div className="planning-members-heading"><div><h2 id="members-title">{t('Your travel group')}</h2><p>{trip.member_count === 1 ? t('1 person making the plan together.') : t('{count} people making the plan together.', { count: trip.member_count.toLocaleString(locale) })}</p></div>
        <div className="planning-members-actions">{trip.role === 'administrator' && <InviteMembersControl tripId={trip.id} />}</div>
      </div>
      {current?.own_readiness.status === 'Incomplete' && <p className="planning-own-note">{t("For your readiness, add:")} {current.own_readiness.missing_fields.map((field) => t(missingFieldLabels[field])).join('، ')}{t('. Complete all required fields before saving.')}</p>}
      <ul className="planning-member-grid">{trip.members.map((member, index) => {
        const readiness = trip.role === 'administrator' ? current?.member_readiness?.find((value) => value.user_id === member.user_id)?.status : undefined
        const dates = current?.member_dates.find((value) => value.user_id === member.user_id)
        return <li className="planning-member-card" key={member.user_id}>
          <div className="planning-member-card-top"><span className={`planning-member-avatar planning-member-avatar--${index % 3}`} aria-hidden="true">{member.display_name.slice(0, 1).toUpperCase()}</span><span className="planning-member-number" aria-hidden="true">{(index + 1).toString().padStart(2, '0')}</span></div>
          <h3>{member.display_name}</h3><p>{member.role === 'administrator' ? t("Trip administrator") : t("Trip member")}</p>
          <div className="planning-member-dates"><span>{t('Travel dates')}</span>
            {!dates ? <p>{current ? t('Dates unavailable') : busy ? t('Loading travel dates…') : t('Dates unavailable')}</p>
              : !dates.available_start && !dates.available_end ? <p>{t('Dates not entered yet')}</p>
                : <p>{t('Available from')}: {dates.available_start ? <time dateTime={dates.available_start}>{calendarDate(dates.available_start, locale)}</time> : t('Not entered')}<br />{t('Available until')}: {dates.available_end ? <time dateTime={dates.available_end}>{calendarDate(dates.available_end, locale)}</time> : t('Not entered')}</p>}
          </div>
          {trip.role === 'administrator' && <div className="planning-member-readiness"><span>{t("Preferences")}</span><span className={`planning-badge${readiness ? ` planning-badge--${readiness.toLowerCase()}` : ''}`}>{t(readiness ?? 'Unavailable')}</span></div>}
        </li>
      })}</ul>
      <p className="planning-privacy-note"><span aria-hidden="true">◇</span> {t('Travel dates are shared with trip members. Budgets and other preferences stay private. Only the administrator sees individual readiness.')}</p>
    </section>
  </section>
}
