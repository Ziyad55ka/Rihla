import { useEffect, useState } from 'react'
import { useLanguage } from '../lib/language'
import { activityApi, activityProposalEstimate, focusLabels, isActivitySuitable, selectedActivityCost, type SelectionStore } from '../lib/activities'
import type { ActivityCategory, ActivityProposalEstimate, InfoField, Proposal } from '../types/proposal'
import { ActivityEstimate } from './ActivityEstimate'
import '../activities.css'
import '../planning.css'

const safeUrl = (value: string | null) => {
  try { const url = new URL(value ?? ''); return url.protocol === 'https:' ? url.href : null } catch { return null }
}

const categoryLabels: Record<ActivityCategory, string> = { activity: 'Activities', attraction: 'Attractions', restaurant: 'Restaurants' }

function ActivityImage({ url, name }: { url: string; name: string }) {
  const { t } = useLanguage()
  const [failed, setFailed] = useState(false)
  return failed ? <div className="activity-image-unavailable">{t('Image not available')}</div>
    : <img src={url} alt={name} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
}

function ActivityInfo({ label, field, proposal }: { label: string; field: InfoField; proposal: Proposal }) {
  const { t } = useLanguage()
  return <div className="activity-info"><dt>{t(label)}</dt><dd>{field.value ?? t('Not available')} {field.value !== null && <small>{t(field.status)}</small>}
    {field.evidence.map((evidence, index) => {
      const source = proposal.sources.find(item => item.id === evidence.source_id)
      const url = safeUrl(source?.url ?? null)
      return source && url ? <a key={index} href={url} target="_blank" rel="noreferrer" title={evidence.quote}>{source.title}</a> : null
    })}
  </dd></div>
}

export function ActivitiesPanel({ proposal, store = activityApi, onSaved, showEstimate = true }: { proposal: Proposal; store?: SelectionStore; onSaved?: () => void; showEstimate?: boolean }) {
  const { t, locale } = useLanguage()
  const [ids, setIds] = useState<string[]>([])
  const [saved, setSaved] = useState<string[]>([])
  const [estimate, setEstimate] = useState<ActivityProposalEstimate | null>(null)
  const [category, setCategory] = useState<'all' | ActivityCategory>('all')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setNotice(''); setIds([]); setSaved([]); setEstimate(null)
    store.load(proposal, controller.signal).then(result => {
      if (!controller.signal.aborted) { setIds(result.activity_ids); setSaved(result.activity_ids); setEstimate(result.estimate ?? activityProposalEstimate(proposal, result.activity_ids)); setLoading(false) }
    }).catch(() => { if (!controller.signal.aborted) { setError('Could not load activity selections.'); setLoading(false) } })
    return () => controller.abort()
    // The parent keys this component by proposal id/version. Polling must not erase drafts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal.id, proposal.version, store, attempt])
  const total = selectedActivityCost(proposal, ids)
  const dirty = JSON.stringify([...ids].sort()) !== JSON.stringify([...saved].sort())
  async function save() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await store.save(proposal, ids)
      setSaved(result.activity_ids); setIds(result.activity_ids); setEstimate(result.estimate ?? activityProposalEstimate(proposal, result.activity_ids)); setNotice('Activity selections saved.')
      onSaved?.()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save activity selections.') }
    finally { setBusy(false) }
  }
  const loadFailed = error === 'Could not load activity selections.'
  return <section id="activities-options" className="activities-panel" aria-label={t('Activities')}>
    <h4>{t('Activities and places')}</h4>
    <p className="activity-selection-note">{t('Choose freely. You do not need to assign a day or time.')}</p>
    <div className="activity-filters" role="group" aria-label={t('Suggestion categories')}>
      {(['all', 'activity', 'attraction', 'restaurant'] as const).map(value => <button type="button" key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{t(value === 'all' ? 'All suggestions' : categoryLabels[value])}</button>)}
    </div>
    {loading && <p role="status">{t('Loading activity selections…')}</p>}
    {error && <p role="alert">{t(error)} {loadFailed && <button type="button" onClick={() => setAttempt(value => value + 1)}>{t('Try again')}</button>}</p>}
    {notice && <p role="status">{t(notice)}</p>}
    {proposal.cities.map(city => <section key={city.order} className="activities-city">
      <h5>{city.city}</h5>
      {!(city.activities?.length) && <p>{t('No activities available for this city.')}</p>}
      {city.activities?.length && !city.activities.some(a => category === 'all' || (a.category ?? 'activity') === category) ? <p>{t('No suggestions in this category for this city.')}</p> : null}
      <div className="activities-grid">{city.activities?.filter(activity => category === 'all' || (activity.category ?? 'activity') === category).map((activity, index) => {
        const booking = safeUrl(activity.booking_url), image = safeUrl(activity.image_url)
        const suitable = isActivitySuitable(proposal, city, activity)
        return <article key={activity.id} className={`planning-member-card activity-card${ids.includes(activity.id) ? ' activity-card--selected' : ''}`}>
          {image ? <ActivityImage url={image} name={activity.name.value ?? ''} /> : <div className={`activity-card-art activity-card-art--${index % 3}`}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <svg viewBox="0 0 140 100" fill="none" aria-hidden="true">
              {index % 3 === 0 ? <g><path d="m29 36 41-21 41 21H29Zm5 48h72M39 41v37m20-37v37m22-37v37m20-37v37M26 90h88" /><circle cx="70" cy="28" r="3" /></g> : index % 3 === 1 ? <g><path d="M20 80c20 0 18-24 38-24s22-25 42-25h20" strokeDasharray="4 5" /><path d="m36 54 8-22 8 22m-8-11v19m53-7 8-22 8 22m-8-11v19" /><circle cx="20" cy="80" r="4" /><circle cx="120" cy="31" r="4" /></g> : <g><path d="M70 15c1 28 9 35 34 35-25 1-33 8-34 35-1-27-9-34-34-35 25 0 33-7 34-35Z" /><path d="m108 14 2 8 8 2-8 2-2 8-2-8-8-2 8-2 2-8Z" /><circle cx="32" cy="76" r="3" /></g>}
            </svg><span>{t('Image not available')}</span>
          </div>}
          <p className="activity-category-label">{t(categoryLabels[activity.category ?? 'activity'])}</p>
          <h6>{activity.name.value ?? t('Not available')} <small>{t(activity.name.status)}</small></h6>
          {activity.fits && activity.fits.length > 0 && <p className="activity-fits">{t('Matches the group’s interests:')} {activity.fits.map((tag) => <span key={tag} className="activity-fit">{t(focusLabels[tag])}</span>)}</p>}
          <dl>
            <ActivityInfo label="Description" field={activity.description} proposal={proposal} />
            <ActivityInfo label="Location" field={activity.location} proposal={proposal} />
            <ActivityInfo label="Duration" field={activity.duration} proposal={proposal} />
            <ActivityInfo label="Event date" field={activity.scheduled_date} proposal={proposal} />
            <ActivityInfo label="Price per person" field={{ value: activity.price_per_person.amount_sar === null ? null : `${Number(activity.price_per_person.amount_sar).toLocaleString(locale, { style: 'currency', currency: 'SAR' })}`, status: activity.price_per_person.status, evidence: activity.price_per_person.evidence }} proposal={proposal} />
          </dl>
          {!suitable && <p className="activity-unsuitable" role="status">{t('Outside this city stay — unsuitable for this proposal.')}</p>}
          {booking ? <a href={booking} target="_blank" rel="noreferrer">{t('Booking link')}</a> : <p>{t('Booking link')}: {t('Not available')}</p>}
          <label className="activity-choice"><input type="checkbox" aria-label={t('Select {name}', { name: activity.name.value ?? t('Not available') })} checked={ids.includes(activity.id)} disabled={loading || busy || loadFailed || !suitable} onChange={() => { setNotice(''); setIds(current => current.includes(activity.id) ? current.filter(id => id !== activity.id) : [...current, activity.id]) }} />{t('Select activity')}</label>
        </article>
      })}</div>
    </section>)}
    <div className="activities-summary">
      <p>{t('Selected activities: {count}', { count: ids.length })}</p>
      <p>{t('Known activity cost per person')}: {Number(total.amount_sar).toLocaleString(locale, { style: 'currency', currency: 'SAR' })}</p>
      {total.unknown > 0 && <p role="status">{t('{count} selected activities have unavailable prices.', { count: total.unknown })}</p>}
      {dirty && <p>{t('You have unsaved activity changes.')}</p>}
      <button type="button" className="trip-primary" disabled={loading || busy || loadFailed || !dirty} onClick={() => void save()}>{t(busy ? 'Saving activities…' : 'Save activities')}</button>
    </div>
    {showEstimate && estimate && <ActivityEstimate estimate={estimate} dirty={dirty} />}
  </section>
}
