import { useEffect, useRef, useState } from 'react'
import { useLanguage } from '../lib/language'
import { buildActivitySchedule, suggestDailyPlan } from '../lib/activitySchedule'
import { calendarDate } from '../lib/planning'
import { placeName } from '../lib/places'
import { activityApi, activityProposalEstimate, focusLabels, hasActivityPhoto, isActivitySuitable, type Mode, modeFor, selectedActivityCost, selectionFingerprint, type SelectionStore } from '../lib/activities'
import type { Activity, ActivityCategory, ActivityProposalEstimate, CityStay, InfoField, Proposal } from '../types/proposal'
import { PlacePhoto } from './proposal-details/PlacePhoto'
import { ActivityEstimate } from './ActivityEstimate'
import '../activities.css'
import '../planning.css'

const safeUrl = (value: string | null) => {
  try { const url = new URL(value ?? ''); return url.protocol === 'https:' ? url.href : null } catch { return null }
}

const categoryLabels: Record<ActivityCategory, string> = { activity: 'Activities', attraction: 'Attractions', restaurant: 'Restaurants' }
// Sections a visitor scans for: the sights, the things to do, then where to eat.
const sectionOrder: ActivityCategory[] = ['attraction', 'activity', 'restaurant']
const steps = ['Top sights', 'Activities and events', 'Where to eat', 'Your daily plan'] as const
// Suggestions that match the group's interests come first within each section.
const byFit = (a: Activity, b: Activity) => (b.fits?.length ?? 0) - (a.fits?.length ?? 0)

function ActivityImage({ url, name, onUnavailable }: { url: string; name: string; onUnavailable?: () => void }) {
  const { t } = useLanguage()
  const [failed, setFailed] = useState(false)
  return failed ? <div className="activity-image-unavailable">{t('Image not available')}</div>
    : <img src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => { setFailed(true); onUnavailable?.() }} />
}

function ActivityInfo({ label, field }: { label: string; field: InfoField }) {
  const { t } = useLanguage()
  return <div className="activity-info"><dt>{t(label)}</dt><dd>{field.value ?? t('Not available')}</dd></div>
}

/** A price with no source is Gemini's usual price, so it reads as a rough guide. */
function ActivityPriceLine({ activity }: { activity: Activity }) {
  const { t, locale } = useLanguage()
  const price = activity.price_per_person
  const amount = price.amount_sar === null ? null : Number(price.amount_sar)
  if (amount !== null && price.status === 'Unconfirmed') return <div className="activity-info"><dt>{t('Price per person')}</dt><dd>
    {amount === 0 ? t('Usually free') : t('About {price}', { price: amount.toLocaleString(locale, { style: 'currency', currency: 'SAR', maximumFractionDigits: 0 }) })} <small>{t('Rough estimate · may change with the season')}</small>
  </dd></div>
  return <div className="activity-info activity-price"><dt>{t('Price per person')}</dt><dd>{amount === null ? t('Not available') : amount.toLocaleString(locale, { style: 'currency', currency: 'SAR' })}{amount !== null && <small>{t('Estimated · check final fees and availability')}</small>}</dd></div>
}

export function ActivityCard({ activity, index, city, proposal, selected, disabled, onToggle, readOnly = false }: { activity: Activity; index: number; city: CityStay; proposal: Proposal; selected: boolean; disabled: boolean; onToggle: () => void; readOnly?: boolean }) {
  const { t, language } = useLanguage()
  const booking = safeUrl(activity.booking_url), image = safeUrl(activity.image_url)
  const suitable = isActivitySuitable(proposal, city, activity)
  const name = (language === 'ar' ? activity.name_ar : activity.name_en) || activity.name.value || ''
  const description = (language === 'ar' ? activity.description_ar : activity.description_en) || (language === 'en' ? activity.description.value : null)
  const [expanded, setExpanded] = useState(false)
  const [photoFailed, setPhotoFailed] = useState(false)
  const shownDescription = description && !expanded && description.length > 320 ? `${description.slice(0,320)}…` : description
  const evidence = [...activity.name.evidence,...activity.description.evidence,...activity.price_per_person.evidence]
  const links = [...new Set([...evidence.map(item => proposal.sources.find(source => source.id === item.source_id)?.url),...(activity.content_urls ?? [])])].filter((url): url is string => !!safeUrl(url ?? null))
  // A suggestion is shown only with a photo of it. A saved choice stays visible.
  if (!selected && (photoFailed || !hasActivityPhoto(activity))) return null
  return <article className={`planning-member-card activity-card${selected ? ' activity-card--selected' : ''}`}>
    {activity.image ? <PlacePhoto key={activity.image.url} image={activity.image} place={name} onUnavailable={() => setPhotoFailed(true)} /> : image ? <ActivityImage key={image} url={image} name={name} onUnavailable={() => setPhotoFailed(true)} /> : <div className={`activity-card-art activity-card-art--${index % 3}`}>
      <span>{String(index + 1).padStart(2, '0')}</span>
      <svg viewBox="0 0 140 100" fill="none" aria-hidden="true">
        {index % 3 === 0 ? <g><path d="m29 36 41-21 41 21H29Zm5 48h72M39 41v37m20-37v37m22-37v37m20-37v37M26 90h88" /><circle cx="70" cy="28" r="3" /></g> : index % 3 === 1 ? <g><path d="M20 80c20 0 18-24 38-24s22-25 42-25h20" strokeDasharray="4 5" /><path d="m36 54 8-22 8 22m-8-11v19m53-7 8-22 8 22m-8-11v19" /><circle cx="20" cy="80" r="4" /><circle cx="120" cy="31" r="4" /></g> : <g><path d="M70 15c1 28 9 35 34 35-25 1-33 8-34 35-1-27-9-34-34-35 25 0 33-7 34-35Z" /><path d="m108 14 2 8 8 2-8 2-2 8-2-8-8-2 8-2 2-8Z" /><circle cx="32" cy="76" r="3" /></g>}
      </svg><span>{t('Image not available')}</span>
    </div>}
    <p className="activity-category-label">{t(categoryLabels[activity.category ?? 'activity'])}</p>
    <h6><bdi>{name || t('Not available')}</bdi></h6>
    {activity.fits && activity.fits.length > 0 && <p className="activity-fits">{t('Matches the group’s interests:')} {activity.fits.map((tag) => <span key={tag} className="activity-fit">{t(focusLabels[tag])}</span>)}</p>}
    <dl>
      <div className="activity-info activity-description"><dt>{t('Description')}</dt><dd>{shownDescription || t(language === 'ar' ? 'Arabic description is not available yet.' : 'Not available')}{description && description.length > 320 && <button type="button" className="trip-text-button" onClick={() => setExpanded(value => !value)}>{t(expanded ? 'Show less' : 'Read more')}</button>}</dd></div>
      {activity.location.value && <ActivityInfo label="Location" field={activity.location} />}
      {activity.duration.value && <ActivityInfo label="Duration" field={activity.duration} />}
      {activity.scheduled_date.value !== null && <ActivityInfo label="Event date" field={activity.scheduled_date} />}
      <ActivityPriceLine activity={activity} />
    </dl>
    {!suitable && <p className="activity-unsuitable" role="status">{t('Outside this city stay — unsuitable for this proposal.')}</p>}
    {booking && <a className="activity-availability-link" href={booking} target="_blank" rel="noreferrer">{t('Check availability and tickets')}</a>}
    {links.length > 0 && <details className="activity-references"><summary>{t('Information and credits')}</summary>{links.map((url,index) => <a key={url} href={url} target="_blank" rel="noreferrer">{t('Reference {number}', {number:index+1})}</a>)}</details>}
    {!readOnly && <label className="activity-choice"><input type="checkbox" aria-label={t('Select {name}', { name: name || t('Not available') })} checked={selected} disabled={disabled || (!suitable && !selected)} onChange={onToggle} />{t('Select activity')}</label>}
  </article>
}

// Confirmation is kept in this browser; storage can be off, so it never throws.
const confirmKey = (proposal: Proposal) => `rihla-activities-confirmed:${proposal.id}:${proposal.version}`
function readConfirmed(proposal: Proposal, ids: string[]): boolean {
  try { return localStorage.getItem(confirmKey(proposal)) === selectionFingerprint(ids) } catch { return false }
}
function writeConfirmed(proposal: Proposal, ids: string[] | null) {
  try { if (ids !== null) localStorage.setItem(confirmKey(proposal), selectionFingerprint(ids)); else localStorage.removeItem(confirmKey(proposal)) } catch { /* storage unavailable */ }
}

export function ActivitiesPanel({ proposal, store = activityApi, onSaved, showEstimate = true }: { proposal: Proposal; store?: SelectionStore; onSaved?: () => void; showEstimate?: boolean }) {
  const { t, locale, language } = useLanguage()
  const [ids, setIds] = useState<string[]>([])
  const [saved, setSaved] = useState<string[]>([])
  const [estimate, setEstimate] = useState<ActivityProposalEstimate | null>(null)
  const [step, setStep] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousStep = useRef(0)
  useEffect(() => {
    if (previousStep.current !== step) { heading.current?.focus(); heading.current?.scrollIntoView({ block: 'start' }); previousStep.current = step }
  }, [step])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [mode, setMode] = useState<Mode>('choose')
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setNotice(''); setIds([]); setSaved([]); setEstimate(null)
    store.load(proposal, controller.signal).then(result => {
      if (!controller.signal.aborted) {
        setIds(result.activity_ids); setSaved(result.activity_ids); setEstimate(result.estimate ?? activityProposalEstimate(proposal, result.activity_ids)); setLoading(false)
        // A saved choice opens as the member's own list, not the full catalogue.
        setMode(modeFor(result.activity_ids.length, readConfirmed(proposal, result.activity_ids)))
      }
    }).catch(() => { if (!controller.signal.aborted) { setError('Could not load activity selections.'); setLoading(false) } })
    return () => controller.abort()
    // The parent keys this component by proposal id/version. Polling must not erase drafts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal.id, proposal.version, store, attempt])
  const total = selectedActivityCost(proposal, ids)
  const dirty = JSON.stringify([...ids].sort()) !== JSON.stringify([...saved].sort())
  const scheduleConflict = buildActivitySchedule(proposal, ids).unscheduled > 0
  async function save() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await store.save(proposal, ids)
      setSaved(result.activity_ids); setIds(result.activity_ids); setEstimate(result.estimate ?? activityProposalEstimate(proposal, result.activity_ids)); setNotice('Activity selections saved.')
      writeConfirmed(proposal, null)
      setMode(modeFor(result.activity_ids.length, false, true))
      onSaved?.()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save activity selections.') }
    finally { setBusy(false) }
  }
  const loadFailed = error === 'Could not load activity selections.'
  const listing = mode === 'choose'
  function confirm() { writeConfirmed(proposal, saved); setNotice(''); setMode('confirmed') }
  function edit() { writeConfirmed(proposal, null); setNotice(''); setStep(0); setMode('choose') }
  return <section id="activities-options" tabIndex={-1} className="activities-panel" aria-label={t('Activities')}>
    <div className="activity-wizard-heading">
      <div><p className="trip-eyebrow">{t('Make each day yours')}</p><h4 ref={heading} tabIndex={-1}>{t(listing ? steps[step] : 'Your daily plan')}</h4></div>
      <p>{t('Each activity is one visit, counted once.')}</p>
    </div>
    {listing && <nav className="activity-stepper" aria-label={t('Activity selection steps')}><ol>
      {steps.map((label, index) => <li key={label}><button type="button" aria-current={step === index ? 'step' : undefined} onClick={() => setStep(index)}>
        <span className="activity-step-number">{(index + 1).toLocaleString(locale)}</span><span>{t(label)}</span>
        {index < 3 && <small>{ids.filter(id => proposal.cities.some(city => city.activities?.some(a => a.id === id && (a.category ?? 'activity') === sectionOrder[index]))).length.toLocaleString(locale)}</small>}
      </button></li>)}
    </ol></nav>}
    {mode === 'review' && <p className="activity-selection-note">{t('These are the activities you saved. Confirm them, or edit your choice.')}</p>}
    {mode === 'confirmed' && <p className="activity-confirmed" role="status">{t('Your activities are confirmed and counted in your costs.')}</p>}
    {listing && <div className="activity-autoplan">
      <div><strong>{t('Want us to plan your activities day by day?')}</strong><p>{t('We pick the best matches for your group for each day. You can change any of them before saving.')}</p></div>
      <button type="button" className="trip-secondary" disabled={loading || busy || loadFailed} onClick={() => { setNotice(''); setIds(current => suggestDailyPlan(proposal, current, hasActivityPhoto)); setStep(3) }}>{t('Yes, plan my days')}</button>
    </div>}
    {listing && step < 3 && <p className="activity-selection-note">{t('Choose what appeals to you. Skip this step if you prefer.')}</p>}
    {loading && <p role="status">{t('Loading activity selections…')}</p>}
    {error && <p role="alert">{t(error)} {loadFailed && <button type="button" onClick={() => setAttempt(value => value + 1)}>{t('Try again')}</button>}</p>}
    {notice && <p role="status">{t(notice)}</p>}
    {listing && step < 3 ? proposal.cities.map(city => {
      const all = city.activities ?? []
      const shown = all.filter(activity => (activity.category ?? 'activity') === sectionOrder[step] && (hasActivityPhoto(activity) || ids.includes(activity.id))).sort(byFit)
      return <section key={city.order} className="activities-city">
        <h5>{placeName(city.city, language, city.city_ar)}</h5>
        {shown.length === 0 && <p className="activity-empty-step">{t('No suggestions in this category for this city.')}</p>}
        <div className="activities-grid">{shown.map((activity, index) => <ActivityCard key={activity.id} activity={activity} index={index} city={city} proposal={proposal}
          selected={ids.includes(activity.id)} disabled={loading || busy || loadFailed}
          onToggle={() => { setNotice(''); setIds(current => current.includes(activity.id) ? current.filter(id => id !== activity.id) : [...current, activity.id]) }} />)}</div>
      </section>
    }) : <DailyActivityPlan proposal={proposal} ids={listing ? ids : saved} />}
    {listing && <div className="activity-wizard-navigation">
      {step > 0 && <button type="button" className="trip-secondary" onClick={() => setStep(value => value - 1)}>{t('Previous step')}</button>}
      {step < 3 && <button type="button" className="trip-primary" onClick={() => setStep(value => value + 1)}>{t('Next: {step}', { step: t(steps[step + 1]) })}</button>}
    </div>}
    <div className="activities-summary">
      <p>{t('Selected activities: {count}', { count: ids.length })}</p>
      <p>{t('Known activity cost per person')}: {total.unknown > 0 && Number(total.amount_sar) === 0 ? t('Not available') : Number(total.amount_sar).toLocaleString(locale, { style: 'currency', currency: 'SAR' })}</p>
      {total.unknown > 0 && <p role="status">{t('{count} selected activities have unavailable prices.', { count: total.unknown })}</p>}
      {listing && dirty && <p>{t('You have unsaved activity changes.')}</p>}
      {listing && step === 3 && <button type="button" className="trip-primary" disabled={loading || busy || loadFailed || scheduleConflict || (!dirty && saved.length > 0)} onClick={() => void save()}>{t(busy ? 'Saving activities…' : 'Save activities')}</button>}
      {mode === 'review' && <div className="activities-actions">
        <button type="button" className="trip-secondary" onClick={edit}>{t('Edit activities')}</button>
        <button type="button" className="trip-primary" disabled={scheduleConflict} onClick={confirm}>{t('Confirm activities')}</button>
      </div>}
    </div>
    {showEstimate && estimate && <ActivityEstimate estimate={estimate} dirty={dirty} />}
  </section>
}


export function DailyActivityPlan({ proposal, ids }: { proposal: Proposal; ids: string[] }) {
  const { t, language, locale } = useLanguage()
  const schedule = buildActivitySchedule(proposal, ids)
  return <div className="activity-daily-plan">
    <p className="activity-selection-note">{t('Suggested days, not reservations. Dated events keep their actual date; check opening hours before visiting.')}</p>
    {schedule.unscheduled > 0 && <p role="alert">{t('Some selected activities no longer fit these dates. Edit your choices before confirming.')}</p>}
    <ol>{schedule.days.map((day, index) => <li className="activity-day" key={day.date}>
      <header><span>{t('Day {number}', { number: (index + 1).toLocaleString(locale) })}</span><h5>{calendarDate(day.date, locale)}</h5><small>{t('{count} visits', { count: day.visits.length.toLocaleString(locale) })}</small></header>
      {day.visits.length === 0 ? <p className="activity-free-time">{t(day.travel ? 'Travel day — no activities scheduled.' : 'Free time')}</p> : <ul>{day.visits.map(({ activity, city }) => {
        const name = (language === 'ar' ? activity.name_ar : activity.name_en) || activity.name.value || ''
        return <li key={activity.id} className="activity-day-visit">
          {activity.image && <PlacePhoto image={activity.image} place={name} />}
          <div><p className="activity-day-city">{placeName(city.city, language, city.city_ar)} · {t(categoryLabels[activity.category ?? 'activity'])}</p><h6><bdi>{name}</bdi></h6>
            {activity.scheduled_date.value && <p className="activity-fixed-date">{t('Dated event')}</p>}
            <dl><ActivityPriceLine activity={activity} /></dl>
          </div>
        </li>
      })}</ul>}
    </li>)}</ol>
  </div>
}
