import { useEffect, useState } from 'react'
import { useLanguage } from '../lib/language'
import { activityApi, activityProposalEstimate, focusLabels, isActivitySuitable, selectedActivityCost, type SelectionStore } from '../lib/activities'
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
const sectionLabels: Record<ActivityCategory, string> = { attraction: 'Top sights', activity: 'Things to do', restaurant: 'Where to eat' }
const sectionOrder: ActivityCategory[] = ['attraction', 'activity', 'restaurant']
type Filter = 'all' | 'picked' | ActivityCategory
const matches = (activity: Activity) => (activity.fits?.length ?? 0) > 0
// Suggestions that match the group's interests come first within each section.
const byFit = (a: Activity, b: Activity) => (b.fits?.length ?? 0) - (a.fits?.length ?? 0)

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

/** A price with no source is Gemini's usual price, so it reads as a rough guide. */
function ActivityPriceLine({ activity, proposal }: { activity: Activity; proposal: Proposal }) {
  const { t, locale } = useLanguage()
  const price = activity.price_per_person
  const amount = price.amount_sar === null ? null : Number(price.amount_sar)
  if (amount !== null && price.status === 'Unconfirmed') return <div className="activity-info"><dt>{t('Price per person')}</dt><dd>
    {amount === 0 ? t('Usually free') : t('About {price}', { price: amount.toLocaleString(locale, { style: 'currency', currency: 'SAR', maximumFractionDigits: 0 }) })} <small>{t('Rough estimate · may change with the season')}</small>
  </dd></div>
  return <ActivityInfo label="Price per person" field={{ value: amount === null ? null : amount.toLocaleString(locale, { style: 'currency', currency: 'SAR' }), status: price.status, evidence: price.evidence }} proposal={proposal} />
}

function ActivityCard({ activity, index, city, proposal, selected, disabled, onToggle }: { activity: Activity; index: number; city: CityStay; proposal: Proposal; selected: boolean; disabled: boolean; onToggle: () => void }) {
  const { t } = useLanguage()
  const booking = safeUrl(activity.booking_url), image = safeUrl(activity.image_url)
  const suitable = isActivitySuitable(proposal, city, activity)
  const name = activity.name.value ?? ''
  return <article className={`planning-member-card activity-card${selected ? ' activity-card--selected' : ''}`}>
    {activity.image ? <PlacePhoto image={activity.image} place={name} /> : image ? <ActivityImage url={image} name={name} /> : <div className={`activity-card-art activity-card-art--${index % 3}`}>
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
      <ActivityPriceLine activity={activity} proposal={proposal} />
    </dl>
    {!suitable && <p className="activity-unsuitable" role="status">{t('Outside this city stay — unsuitable for this proposal.')}</p>}
    {booking ? <a href={booking} target="_blank" rel="noreferrer">{t('Booking link')}</a> : <p>{t('Booking link')}: {t('Not available')}</p>}
    <label className="activity-choice"><input type="checkbox" aria-label={t('Select {name}', { name: activity.name.value ?? t('Not available') })} checked={selected} disabled={disabled || !suitable} onChange={onToggle} />{t('Select activity')}</label>
  </article>
}

export function ActivitiesPanel({ proposal, store = activityApi, onSaved, showEstimate = true }: { proposal: Proposal; store?: SelectionStore; onSaved?: () => void; showEstimate?: boolean }) {
  const { t, locale } = useLanguage()
  const [ids, setIds] = useState<string[]>([])
  const [saved, setSaved] = useState<string[]>([])
  const [estimate, setEstimate] = useState<ActivityProposalEstimate | null>(null)
  const [category, setCategory] = useState<Filter>('all')
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
      {(['all', 'picked', 'attraction', 'activity', 'restaurant'] as const).map(value => <button type="button" key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{t(value === 'all' ? 'All suggestions' : value === 'picked' ? 'Picked for your group' : sectionLabels[value])}</button>)}
    </div>
    {loading && <p role="status">{t('Loading activity selections…')}</p>}
    {error && <p role="alert">{t(error)} {loadFailed && <button type="button" onClick={() => setAttempt(value => value + 1)}>{t('Try again')}</button>}</p>}
    {notice && <p role="status">{t(notice)}</p>}
    {proposal.cities.map(city => {
      const all = city.activities ?? []
      const shown = all.filter(activity => category === 'all' || (category === 'picked' ? matches(activity) : (activity.category ?? 'activity') === category))
      const sections = sectionOrder.map(kind => ({ kind, items: shown.filter(activity => (activity.category ?? 'activity') === kind).sort(byFit) })).filter(section => section.items.length > 0)
      return <section key={city.order} className="activities-city">
        <h5>{city.city}</h5>
        {all.length === 0 && <p>{t('No activities available for this city.')}</p>}
        {all.length > 0 && shown.length === 0 && <p>{t('No suggestions in this category for this city.')}</p>}
        {sections.map(section => <div key={section.kind} className="activities-group">
          {sections.length > 1 || category === 'all' || category === 'picked' ? <h6 className="activities-group-title">{t(sectionLabels[section.kind])}</h6> : null}
          <div className="activities-grid">{section.items.map((activity, index) => <ActivityCard key={activity.id} activity={activity} index={index} city={city} proposal={proposal}
            selected={ids.includes(activity.id)} disabled={loading || busy || loadFailed}
            onToggle={() => { setNotice(''); setIds(current => current.includes(activity.id) ? current.filter(id => id !== activity.id) : [...current, activity.id]) }} />)}</div>
        </div>)}
      </section>
    })}
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
