import { useEffect, useState } from 'react'
import { editablePreferences, getPreferences, preferenceError, savePreferences } from '../lib/preferences'
import type { Importance, MemberPreferences, SavedPreferences } from '../types/preferences'
import '../preferences.css'

const optionalFields = [
  { key: 'destinations', label: 'Destinations', placeholder: 'Cities or countries you would like to visit' },
  { key: 'interests', label: 'Interests', placeholder: 'For example: nature, museums, food or adventure' },
  { key: 'flights', label: 'Flight preferences', placeholder: 'For example: direct flights or a preferred airline' },
  { key: 'accommodation', label: 'Accommodation preferences', placeholder: 'For example: a hotel near the city centre' },
] as const

function PreferencesForm({ tripId, initial, onSaved }: { tripId: string; initial: SavedPreferences; onSaved: () => void }) {
  const [values, setValues] = useState<MemberPreferences>(() => editablePreferences(initial))
  const [savedAt, setSavedAt] = useState(initial.updated_at)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  function change<K extends keyof MemberPreferences>(key: K, value: MemberPreferences[K]) {
    setValues((current) => ({ ...current, [key]: value })); setDirty(true); setNotice(''); setError('')
  }
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const invalid = preferenceError(values)
    if (invalid) { setError(invalid); return }
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await savePreferences(tripId, values)
      setValues(editablePreferences(result)); setSavedAt(result.updated_at); setDirty(false)
      setNotice('Your preferences have been saved. You can edit them throughout planning.')
      onSaved()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save your preferences. Your edits are still here.') }
    finally { setBusy(false) }
  }
  return <form className="trip-form preferences-form" onSubmit={(event) => void submit(event)}>
    <fieldset disabled={busy} className="preferences-fields">
      <legend>Your travel essentials</legend>
      <p className="trip-field-note">Departure city, maximum budget and both dates are required for readiness. You can save a draft with blank fields.</p>
      <div className="preferences-grid">
        <div><label htmlFor="departure-city">Departure city</label><input id="departure-city" autoComplete="address-level2" maxLength={100} value={values.departure_city} placeholder="For example: Riyadh" onChange={(event) => change('departure_city', event.target.value)} /></div>
        <div><label htmlFor="maximum-budget">Maximum budget <span>SAR per person</span></label><input id="maximum-budget" type="number" inputMode="decimal" min="0.01" max="9999999999.99" step="0.01" value={values.max_budget_sar ?? ''} placeholder="Your total travel budget" onChange={(event) => change('max_budget_sar', event.target.value || null)} /></div>
        <div><label htmlFor="available-start">Available from</label><input id="available-start" type="date" min="0001-01-01" max="9999-12-31" value={values.available_start ?? ''} onChange={(event) => change('available_start', event.target.value || null)} /></div>
        <div><label htmlFor="available-end">Available until</label><input id="available-end" type="date" min={values.available_start || '0001-01-01'} max="9999-12-31" value={values.available_end ?? ''} onChange={(event) => change('available_end', event.target.value || null)} /></div>
      </div>
      <p className="trip-field-note">Both dates count as available days. One day is valid when the dates are the same. Your budget and dates are firm limits.</p>
    </fieldset>
    <fieldset disabled={busy} className="preferences-fields preferences-optional">
      <legend>Make it your kind of trip <span>Optional</span></legend>
      <p className="trip-field-note">Essential means it must be respected. Flexible means it may be adjusted, with an explanation when proposals are introduced. Leaving these blank will not block readiness.</p>
      {optionalFields.map(({ key, label, placeholder }) => <div className="preference-choice" key={key}>
        <div><label htmlFor={`preference-${key}`}>{label}</label><textarea id={`preference-${key}`} maxLength={500} rows={2} value={values[key].value} placeholder={placeholder} onChange={(event) => change(key, { ...values[key], value: event.target.value })} /></div>
        <div><label htmlFor={`importance-${key}`}>Importance</label><select id={`importance-${key}`} value={values[key].importance} onChange={(event) => change(key, { ...values[key], importance: event.target.value as Importance })}><option value="Flexible">Flexible</option><option value="Essential">Essential</option></select></div>
      </div>)}
    </fieldset>
    <div className="trip-form-actions"><button type="submit" className="trip-primary" disabled={busy || !dirty}>{busy ? 'Saving…' : 'Save preferences'} <span aria-hidden="true">↗</span></button>
      <span className="preferences-save-status" role="status">{dirty ? 'Unsaved changes' : savedAt ? `Saved ${new Date(savedAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : 'No preferences saved yet'}</span></div>
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{error}</p>}
    {notice && <p className="trip-feedback trip-feedback--success" role="status">{notice}</p>}
  </form>
}

export function PreferencesPanel({ tripId, onSaved }: { tripId: string; onSaved: () => void }) {
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
    <div className="preferences-heading"><div><p className="trip-eyebrow">START WITH WHAT MATTERS TO YOU</p><h2 id="preferences-title">Your trip. Your preferences.</h2></div><span className="preferences-private">Private to you</span></div>
    <p className="trip-intro-copy">Only you can read or change these inputs. Other members, including the administrator, cannot see your budget or detailed preferences.</p>
    {error ? <div className="trip-feedback trip-feedback--error" role="alert">{error}<button type="button" className="trip-text-button" onClick={() => { setError(''); setAttempt((value) => value + 1) }}>Try again</button></div>
      : saved ? <PreferencesForm key={tripId} tripId={tripId} initial={saved} onSaved={onSaved} /> : <p className="trip-loading" role="status">Loading your preferences…</p>}
  </section>
}
