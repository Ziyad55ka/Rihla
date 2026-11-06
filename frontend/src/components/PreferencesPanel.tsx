import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { BedDouble, Check, CheckCircle2, ChevronDown, LockKeyhole, MapPin, Mountain, Palmtree, Landmark, Tickets, Utensils, Trees, Users, ShieldCheck, CircleAlert, Minus, Plus } from 'lucide-react'
import { editablePreferences, formatInterestPreference, getPreferences, INTEREST_FOCUS, parseInterestPreference, preferenceError, preferencesForForm, savePreferences, type InterestFocus } from '../lib/preferences'
import { checkTravelDates } from '../lib/date-check'
import type { DateCheck } from '../lib/date-check'
import type { Importance, MemberPreferences, SavedPreferences } from '../types/preferences'
import { useLanguage } from '../lib/language'
import '../preferences.css'
import { DestinationDiscovery } from './DestinationDiscovery'
import { formatAccommodation, parseAccommodation, toggleHotelClass } from '../lib/accommodation'
import { stepBudget } from '../lib/budget'
import { FlyIcon } from './FlightIcons'

const interestLabels: Record<InterestFocus, string> = {
  adventure_sports: 'Adventure',
  beaches_water: 'Beaches & water',
  landmarks: 'Sightseeing',
  museums_history: 'Heritage & museums',
  events_festivals: 'Events & festivals',
  food: 'Food experiences',
  nature_outdoors: 'Nature & outdoors',
  family_fun: 'Family activities',
}

const interestIcons = { adventure_sports: Mountain, beaches_water: Palmtree, landmarks: MapPin, museums_history: Landmark, events_festivals: Tickets, food: Utensils, nature_outdoors: Trees, family_fun: Users }

function jumpToSection(event: MouseEvent<HTMLAnchorElement>, id: string) {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
  event.preventDefault()
  const section = document.getElementById(id)
  section?.focus({ preventScroll: true })
  section?.scrollIntoView({ block: 'start', behavior: 'instant' })
}

function PreferenceImportance({ id, value, onChange }: { id: string; value: Importance; onChange: (value: Importance) => void }) {
  const { t } = useLanguage()
  return <fieldset className="preference-importance" id={id}>
    <legend>{t('Importance')}</legend>
    <div className="importance-options">
      {(['Flexible', 'Essential'] as const).map(option => <button key={option} type="button" aria-pressed={value === option} onClick={() => onChange(option)}>{value === option && <Check size={14} aria-hidden="true" />}{t(option)}</button>)}
    </div>
    <small>{t(value === 'Essential' ? 'Must be respected.' : 'Can adapt to the group.')}</small>
  </fieldset>
}

export function PreferencesForm({ tripId, initial, onSaved }: { tripId: string; initial: SavedPreferences; onSaved: () => void }) {
  const { t, locale } = useLanguage()
  const [values, setValues] = useState<MemberPreferences>(() => preferencesForForm(initial))
  const [savedAt, setSavedAt] = useState(initial.updated_at)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dateCheck, setDateCheck] = useState<{ range: string; state: DateCheck['status'] | 'checking' | 'error' } | null>(null)
  const [checkAttempt, setCheckAttempt] = useState(0)
  const feedback = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (error) feedback.current?.focus() }, [error])
  const interests = parseInterestPreference(values.interests.value)
  const hotel = parseAccommodation(values.accommodation.value)
  function changeHotel(next: typeof hotel) {
    const encoded = formatAccommodation(next)
    if (encoded.length > 500) { setError('Shorten your hotel notes before changing hotel class.'); return }
    change('accommodation', { ...values.accommodation, value: encoded })
  }
  const range = `${values.available_start ?? ''}/${values.available_end ?? ''}`
  useEffect(() => {
    const start = values.available_start
    const end = values.available_end
    if (!start || !end || start > end) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setDateCheck({ range, state: 'checking' })
      checkTravelDates(tripId, start, end, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setDateCheck({ range, state: result.status }) })
        .catch(() => { if (!controller.signal.aborted) setDateCheck({ range, state: 'error' }) })
    }, 400)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [tripId, values.available_start, values.available_end, range, checkAttempt])
  const currentDateCheck = dateCheck?.range === range && values.available_start && values.available_end && values.available_start <= values.available_end ? dateCheck.state : null
  function change<K extends keyof MemberPreferences>(key: K, value: MemberPreferences[K]) {
    setValues((current) => ({ ...current, [key]: value })); setDirty(true); setNotice(''); setError('')
  }
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const invalid = preferenceError(values)
    if (invalid) { setError(invalid); return }
    setBusy(true); setError(''); setNotice('')
    setCheckAttempt((current) => current + 1)
    try {
      const result = await savePreferences(tripId, {
        ...values,
        destinations: { ...values.destinations, importance: 'Flexible' },
        flights: { ...values.flights, importance: 'Flexible' },
      })
      setValues(editablePreferences(result)); setSavedAt(result.updated_at); setDirty(false)
      setNotice('Your preferences have been saved. You can edit them throughout planning.')
      onSaved()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save your preferences. Your edits are still here.') }
    finally { setBusy(false) }
  }
  function applyDiscovery(focus: InterestFocus[], notes: string) {
    const nextNotes = interests.notes.includes(notes) ? interests.notes : `${interests.notes}\n${notes}`.trim()
    const nextValue = formatInterestPreference([...new Set([...interests.focus, ...focus])], nextNotes)
    if (nextValue.length > 500) { setError('Your interest notes are too long to add these answers. Shorten them and try again.'); return }
    change('interests', { ...values.interests, value: nextValue })
  }
  return <form className="trip-form preferences-form" onSubmit={(event) => void submit(event)}>
    <fieldset disabled={busy} tabIndex={-1} className="preferences-fields preferences-destination" id="preferences-destination">
      <legend><span className="preferences-section-number">01</span><span>{t('Where would you like to go?')}</span><span className="preferences-optional-label">{t('Optional')}</span></legend>
      <label htmlFor="preference-destinations">{t('Destinations')}<span aria-hidden="true">{values.destinations.value.length}/500</span></label>
      <input type="text" id="preference-destinations" maxLength={500} autoComplete="off" value={values.destinations.value} placeholder={t('For example: Paris, Japan, or a beach destination')} aria-describedby="destinations-help" onChange={event => change('destinations', { ...values.destinations, value: event.target.value })} />
      <div className="destination-help-row"><p id="destinations-help">{t('Add cities or countries. We’ll combine the group’s wishes.')}</p><DestinationDiscovery onChoose={applyDiscovery} /></div>
    </fieldset>
    <fieldset disabled={busy} tabIndex={-1} className="preferences-fields" id="preferences-essentials">
      <legend><span className="preferences-section-number">02</span><span>{t('Your travel essentials')}</span><span className="preferences-required-label">{t('Required')}</span></legend>
      <div className="preferences-grid">
        <div><label htmlFor="departure-city">{t('Departure city')}</label><input id="departure-city" required pattern=".*\S.*" autoComplete="address-level2" maxLength={100} value={values.departure_city} placeholder={t('City or airport code, e.g. Riyadh or RUH')} onChange={(event) => change('departure_city', event.target.value)} /></div>
        <div><label htmlFor="maximum-budget">{t("Maximum budget")} <span>{t("SAR per person")}</span></label>
          <div className="budget-control" dir="ltr">
            <button type="button" className="budget-step" aria-label={t('Decrease budget by 1,000 SAR')} disabled={stepBudget(values.max_budget_sar, -1) === values.max_budget_sar} onClick={() => change('max_budget_sar', stepBudget(values.max_budget_sar, -1))}><Minus size={18} aria-hidden="true" /></button>
            <input id="maximum-budget" required type="text" inputMode="decimal" maxLength={13} value={values.max_budget_sar ?? ''} placeholder={t("Your total travel budget")} aria-describedby="budget-step-help" onKeyDown={event => {
              if (event.key === 'ArrowUp' || event.key === 'ArrowDown') { event.preventDefault(); change('max_budget_sar', stepBudget(values.max_budget_sar, event.key === 'ArrowUp' ? 1 : -1)) }
            }} onChange={(event) => change('max_budget_sar', event.target.value || null)} />
            <button type="button" className="budget-step" aria-label={t('Increase budget by 1,000 SAR')} disabled={stepBudget(values.max_budget_sar, 1) === values.max_budget_sar} onClick={() => change('max_budget_sar', stepBudget(values.max_budget_sar, 1))}><Plus size={18} aria-hidden="true" /></button>
          </div><small id="budget-step-help" className="trip-field-note">{t('Use + and − to change by 1,000 SAR, or enter your own amount.')}</small>
        </div>
        <div><label htmlFor="available-start">{t('Available from')}</label><input id="available-start" required type="date" min="0001-01-01" max="9999-12-31" value={values.available_start ?? ''} onChange={(event) => change('available_start', event.target.value || null)} /></div>
        <div><label htmlFor="available-end">{t('Available until')}</label><input id="available-end" required type="date" min={values.available_start || '0001-01-01'} max="9999-12-31" value={values.available_end ?? ''} onChange={(event) => change('available_end', event.target.value || null)} /></div>
      </div>
      {currentDateCheck && <p className={`preferences-date-check preferences-date-check--${currentDateCheck}`} role={currentDateCheck === 'conflict' ? 'alert' : 'status'}>
        {currentDateCheck === 'available' ? <CheckCircle2 size={18} aria-hidden="true" /> : <CircleAlert size={18} aria-hidden="true" />}
        {currentDateCheck === 'conflict' ? t("Your dates do not overlap with the dates entered by other trip members. Try another range. You can still save your preferences.")
          : currentDateCheck === 'available' ? t("Your dates overlap with the group’s entered availability.")
            : currentDateCheck === 'pending' ? t("Waiting for other members to add their dates before confirming the group’s shared window.")
              : currentDateCheck === 'error' ? t("We couldn’t check your dates against the group. You can still save; we’ll check again when you do.") : t("Checking your dates with the group…")}
      </p>}
      <p className="preferences-limit-note"><ShieldCheck size={16} aria-hidden="true" />{t('Your budget and dates are firm limits. Both dates count as available days.')}</p>
    </fieldset>
    <fieldset disabled={busy} tabIndex={-1} className="preferences-fields preferences-optional" id="preferences-style">
      <legend><span className="preferences-section-number">03</span><span>{t('Make it your kind of trip')}</span><span className="preferences-optional-label">{t('Optional')}</span></legend>
      <div className="preference-choice preference-interests">
        <div>
          <div className="preference-interests-header"><div><label id="interest-focus-label">{t('What would you like to do?')}</label><p className="trip-field-note">{t('Choose as many as you like.')}</p></div><PreferenceImportance id="importance-interests" value={values.interests.importance} onChange={importance => change('interests', { ...values.interests, importance })} /></div>
          <div className="interest-focus-grid" role="group" aria-labelledby="interest-focus-label">
            {INTEREST_FOCUS.map((focus) => {
              const selected = interests.focus.includes(focus)
              const Icon = interestIcons[focus]
              return <button key={focus} type="button" className={`interest-focus${selected ? ' interest-focus--selected' : ''}`} aria-pressed={selected} onClick={() => {
                const next = selected ? interests.focus.filter((item) => item !== focus) : [...interests.focus, focus]
                const encoded = formatInterestPreference(next, interests.notes)
                if (encoded.length > 500) { setError('Shorten your interest notes before adding more categories.'); return }
                change('interests', { ...values.interests, value: encoded })
              }}><Icon size={20} aria-hidden="true" /><span>{t(interestLabels[focus])}</span><span className="interest-selection-mark" aria-hidden="true">{selected && <Check size={14} />}</span></button>
            })}
          </div>
          <label htmlFor="interest-notes">{t('Other interests')}</label>
          <textarea id="interest-notes" maxLength={Math.max(interests.notes.length, 500 - formatInterestPreference(interests.focus, '').length)} rows={2} value={interests.notes} placeholder={t('For example: quiet local experiences or accessible activities')} onChange={(event) => change('interests', { ...values.interests, value: formatInterestPreference(interests.focus, event.target.value) })} />
        </div>
      </div>
      <div className="preference-choice preference-accommodation">
        <div><label id="hotel-class-label"><BedDouble size={19} aria-hidden="true" />{t('Your hotel')}</label>
          <p className="trip-field-note">{t('Higher star ratings can leave less of your budget for activities.')}</p>
          <p id="hotel-class-help" className="trip-field-note">{t('Select every hotel class you would be happy to book.')}</p>
          <div className="hotel-class-options" role="group" aria-labelledby="hotel-class-label" aria-describedby="hotel-class-help">
            {([null, 3, 4, 5] as const).map(stars => <button key={stars ?? 'any'} type="button" aria-pressed={stars === null ? hotel.stars === null : hotel.stars === stars || hotel.lower.includes(stars)} onClick={() => changeHotel(stars === null ? { ...hotel, stars: null, lower: [] } : toggleHotelClass(hotel, stars))}>{stars === null ? t('No preference') : t('{stars} stars', { stars })}</button>)}
          </div>
          <label htmlFor="preference-accommodation">{t('Other hotel needs')}</label><textarea id="preference-accommodation" maxLength={Math.max(hotel.notes.length,500-formatAccommodation({...hotel,notes:''}).length)} rows={2} value={hotel.notes} placeholder={t('For example: a hotel near the city centre')} onChange={event => changeHotel({ ...hotel, notes: event.target.value })} />
        </div>
        <PreferenceImportance id="importance-accommodation" value={values.accommodation.importance} onChange={importance => change('accommodation', { ...values.accommodation, importance })} />
      </div>
    </fieldset>
    {error && <p ref={feedback} tabIndex={-1} className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {notice && <p className="trip-feedback trip-feedback--success" role="status">{t(notice)}</p>}
    <div className={`trip-form-actions preferences-actions${dirty ? ' preferences-actions--dirty' : ''}`}><button type="submit" className="trip-primary" disabled={busy || !dirty}>{busy ? t("Saving…") : t("Save preferences")} <span aria-hidden="true"><FlyIcon /></span></button>
      <span className="preferences-save-status" role="status">{dirty ? t("Unsaved changes") : savedAt ? t('Saved {date}', { date: new Date(savedAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) }) : t("No preferences saved yet")}</span></div>
  </form>
}

export function PreferencesPanel({ tripId, onSaved }: { tripId: string; onSaved: () => void }) {
  const { t } = useLanguage()
  const [saved, setSaved] = useState<SavedPreferences | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getPreferences(tripId, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setSaved(result); setError('') } })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load your preferences.') })
    return () => controller.abort()
  }, [tripId, attempt])
  return <section className="preferences-panel" aria-labelledby="preferences-title">
    <div className="preferences-heading"><div><h1 id="preferences-title">{t('Your travel preferences')}</h1><p>{t('A few details. A trip that fits you.')}</p></div><details className="preferences-privacy"><summary><LockKeyhole size={15} aria-hidden="true" />{t('Who can see this?')}<ChevronDown size={14} aria-hidden="true" /></summary><p>{t('Your travel dates are visible to your trip members. Your budget and other preferences stay private; only you can edit your inputs.')}</p></details></div>
    <nav className="preferences-section-nav" aria-label={t('Preference sections')}><a href="#preferences-destination" onClick={event => jumpToSection(event, 'preferences-destination')}>{t('Destination')}</a><a href="#preferences-essentials" onClick={event => jumpToSection(event, 'preferences-essentials')}>{t('Dates & budget')}</a><a href="#preferences-style" onClick={event => jumpToSection(event, 'preferences-style')}>{t('Travel style')}</a></nav>
    {error ? <div className="trip-feedback trip-feedback--error" role="alert">{t(error)}<button type="button" className="trip-text-button" onClick={() => { setError(''); setAttempt((value) => value + 1) }}>{t("Try again")}</button></div>
      : saved ? <PreferencesForm key={tripId} tripId={tripId} initial={saved} onSaved={onSaved} /> : <p className="trip-loading" role="status">{t("Loading your preferences…")}</p>}
  </section>
}
