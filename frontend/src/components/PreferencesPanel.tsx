import { useEffect, useState } from 'react'
import { editablePreferences, getPreferences, preferenceError, preferencesForForm, savePreferences } from '../lib/preferences'
import { checkTravelDates } from '../lib/date-check'
import type { DateCheck } from '../lib/date-check'
import type { Importance, MemberPreferences, SavedPreferences } from '../types/preferences'
import { useLanguage } from '../lib/language'
import '../preferences.css'

// Places and flight wishes have no importance: Rihla combines everyone's into
// one plan, so they are always saved as Flexible.
const optionalFields = [
  { key: 'destinations', label: 'Destinations', placeholder: 'Cities or countries you would like to visit', wish: true },
  { key: 'interests', label: 'Interests', placeholder: 'For example: nature, museums, food or adventure', wish: false },
  { key: 'flights', label: 'Flight preferences', placeholder: 'For example: direct flights or a preferred airline', wish: true },
  { key: 'accommodation', label: 'Accommodation preferences', placeholder: 'For example: a hotel near the city centre', wish: false },
] as const

function PreferencesForm({ tripId, initial, onSaved }: { tripId: string; initial: SavedPreferences; onSaved: () => void }) {
  const { t, locale } = useLanguage()
  const [values, setValues] = useState<MemberPreferences>(() => preferencesForForm(initial))
  const [savedAt, setSavedAt] = useState(initial.updated_at)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dateCheck, setDateCheck] = useState<{ range: string; state: DateCheck['status'] | 'checking' | 'error' } | null>(null)
  const [checkAttempt, setCheckAttempt] = useState(0)
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
  return <form className="trip-form preferences-form" onSubmit={(event) => void submit(event)}>
    <fieldset disabled={busy} className="preferences-fields">
      <legend><span className="preferences-section-number">01</span> {t('Your travel essentials')}</legend>
      <p className="trip-field-note">{t('Departure city, maximum budget and both dates are required before saving.')}</p>
      <div className="preferences-grid">
        <div><label htmlFor="departure-city">{t('Departure city')}</label><input id="departure-city" required pattern=".*\S.*" autoComplete="address-level2" maxLength={100} value={values.departure_city} placeholder={t('For example: Riyadh')} onChange={(event) => change('departure_city', event.target.value)} /></div>
        <div><label htmlFor="maximum-budget">{t("Maximum budget")} <span>{t("SAR per person")}</span></label><input id="maximum-budget" required type="number" inputMode="decimal" min="0.01" max="9999999999.99" step="0.01" value={values.max_budget_sar ?? ''} placeholder={t("Your total travel budget")} onChange={(event) => change('max_budget_sar', event.target.value || null)} /></div>
        <div><label htmlFor="available-start">{t('Available from')}</label><input id="available-start" required type="date" min="0001-01-01" max="9999-12-31" value={values.available_start ?? ''} onChange={(event) => change('available_start', event.target.value || null)} /></div>
        <div><label htmlFor="available-end">{t('Available until')}</label><input id="available-end" required type="date" min={values.available_start || '0001-01-01'} max="9999-12-31" value={values.available_end ?? ''} onChange={(event) => change('available_end', event.target.value || null)} /></div>
      </div>
      {currentDateCheck && <p className={`preferences-date-check preferences-date-check--${currentDateCheck}`} role={currentDateCheck === 'conflict' ? 'alert' : 'status'}>
        <span aria-hidden="true">{currentDateCheck === 'conflict' ? '↔' : currentDateCheck === 'available' ? '✓' : '◇'}</span>
        {currentDateCheck === 'conflict' ? t("Your dates do not overlap with the dates entered by other trip members. Try another range. You can still save your preferences.")
          : currentDateCheck === 'available' ? t("Your dates overlap with the group’s entered availability.")
            : currentDateCheck === 'pending' ? t("Waiting for other members to add their dates before confirming the group’s shared window.")
              : currentDateCheck === 'error' ? t("We couldn’t check your dates against the group. You can still save; we’ll check again when you do.") : t("Checking your dates with the group…")}
      </p>}
      <p className="trip-field-note">{t("Both dates count as available days. One day is valid when the dates are the same. Your budget and dates are firm limits.")}</p>
    </fieldset>
    <fieldset disabled={busy} className="preferences-fields preferences-optional">
      <legend><span className="preferences-section-number">02</span> {t('The little things that matter')} <span className="preferences-optional-label">{t('Optional')}</span></legend>
      <p className="trip-field-note">{t("List as many places as you like. Rihla combines everyone’s places into trips that suit the whole group. For interests and accommodation, Essential means it must be respected and Flexible means it may be adjusted, with an explanation. Leaving these blank will not block readiness.")}</p>
      {optionalFields.map(({ key, label, placeholder, wish }) => {
        const essential = values[key].importance === 'Essential'
        const nextImportance: Importance = essential ? 'Flexible' : 'Essential'
        return <div className={`preference-choice${wish ? ' preference-choice--wish' : ''}`} key={key}>
          <div><label htmlFor={`preference-${key}`}>{t(label)}</label><textarea id={`preference-${key}`} maxLength={500} rows={2} value={values[key].value} placeholder={t(placeholder)} onChange={(event) => change(key, { ...values[key], value: event.target.value })} /></div>
          {!wish && <div className="importance-control"><label htmlFor={`importance-${key}`}>{t('Importance')}</label><button id={`importance-${key}`} type="button" className={`importance-toggle importance-toggle--${essential ? 'essential' : 'flexible'}`} aria-pressed={essential} onClick={() => change(key, { ...values[key], importance: nextImportance })}>{t(values[key].importance)}</button></div>}
        </div>
      })}
    </fieldset>
    <div className="trip-form-actions preferences-actions"><button type="submit" className="trip-primary" disabled={busy || !dirty}>{busy ? t("Saving…") : t("Save preferences")} <span aria-hidden="true">↗</span></button>
      <span className="preferences-save-status" role="status">{dirty ? t("Unsaved changes") : savedAt ? t('Saved {date}', { date: new Date(savedAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) }) : t("No preferences saved yet")}</span></div>
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {notice && <p className="trip-feedback trip-feedback--success" role="status">{t(notice)}</p>}
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
    <div className="preferences-heading"><div><p className="trip-eyebrow">{t('A SPACE FOR YOUR INPUT')}</p><h2 id="preferences-title">{t('Your travel preferences')}</h2></div><span className="preferences-private"><span aria-hidden="true">◇</span> {t('Private to you')}</span></div>
    <p className="trip-intro-copy">{t('Your travel dates are visible to your trip members. Your budget and other preferences stay private; only you can edit your inputs.')}</p>
    {error ? <div className="trip-feedback trip-feedback--error" role="alert">{t(error)}<button type="button" className="trip-text-button" onClick={() => { setError(''); setAttempt((value) => value + 1) }}>{t("Try again")}</button></div>
      : saved ? <PreferencesForm key={tripId} tripId={tripId} initial={saved} onSaved={onSaved} /> : <p className="trip-loading" role="status">{t("Loading your preferences…")}</p>}
  </section>
}
