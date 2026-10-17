import { useState, type FormEvent } from 'react'
import { createTrip, invitationToken, joinTrip } from '../lib/trips'
import type { TripDetail } from '../types/trips'

export function CreateTripForm({ onCreated, onBack }: { onCreated: (trip: TripDetail) => void; onBack: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try { onCreated(await createTrip(title, description)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not create your trip.') }
    finally { setBusy(false) }
  }
  return <section className="trip-form-page">
    <button className="trip-back" onClick={onBack} disabled={busy}>← Back to your trips</button>
    <p className="trip-eyebrow">MAKE THE FIRST MOVE</p><h1>Every trip starts<br />with <span>a plan.</span></h1>
    <p className="trip-intro-copy">Give your next adventure a name. Bring your people along next.</p>
    <form className="trip-form" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      <label htmlFor="trip-title">Trip name <span>Required</span></label>
      <input id="trip-title" name="title" required minLength={2} maxLength={100} placeholder="A weekend worth getting away for" value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} />
      <label htmlFor="trip-description">A little about the trip <span>Optional</span></label>
      <textarea id="trip-description" name="description" maxLength={500} rows={4} placeholder="A celebration, a catch-up, or just a change of scenery…" value={description} disabled={busy} onChange={(event) => setDescription(event.target.value)} />
      <p className="trip-field-note">You’ll be the trip administrator and a participating member.</p>
      {error && <p className="trip-feedback trip-feedback--error" role="alert">{error}</p>}
      <div className="trip-form-actions"><button className="trip-primary" disabled={busy || title.trim().length < 2}>{busy ? 'Creating your trip…' : 'Create trip'} <span aria-hidden="true">↗</span></button><button type="button" className="trip-text-button" onClick={onBack} disabled={busy}>Cancel</button></div>
    </form>
  </section>
}

export function JoinTripForm({ initialInvitation, onJoined, onBack }: { initialInvitation: string | null; onJoined: (trip: TripDetail, alreadyMember: boolean) => void; onBack: () => void }) {
  const [input, setInput] = useState(initialInvitation ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const token = invitationToken(input)
    if (!token) { setError('Enter a 6-digit invitation code or paste a complete Rihla invitation link.'); return }
    setBusy(true); setError('')
    try { const result = await joinTrip(token); onJoined(result.trip, result.already_member) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not join this trip.') }
    finally { setBusy(false) }
  }
  return <section className="trip-form-page">
    <button className="trip-back" onClick={onBack} disabled={busy}>← Back to your trips</button>
    <p className="trip-eyebrow">THERE’S A PLACE FOR YOU</p><h1>Good company.<br /><span>You’re invited.</span></h1>
    <p className="trip-intro-copy">Enter the 6-digit code or paste the link your trip administrator shared with you.</p>
    <form className="trip-form" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      <label htmlFor="trip-invitation">Invitation link or code</label>
      <textarea id="trip-invitation" name="invitation" required rows={3} maxLength={2048} autoComplete="off" spellCheck={false} placeholder="6-digit code or invitation link" value={input} disabled={busy} onChange={(event) => setInput(event.target.value)} />
      <p className="trip-field-note">Invitations are valid for 7 days unless the administrator replaces or revokes them. Already a member? Joining again takes you to the same trip.</p>
      {error && <p className="trip-feedback trip-feedback--error" role="alert">{error}</p>}
      <div className="trip-form-actions"><button className="trip-primary" disabled={busy}>{busy ? 'Joining your group…' : 'Join trip'} <span aria-hidden="true">↗</span></button><button type="button" className="trip-text-button" onClick={onBack} disabled={busy}>Cancel</button></div>
    </form>
  </section>
}
