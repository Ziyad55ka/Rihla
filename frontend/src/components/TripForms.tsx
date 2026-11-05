import { useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from 'react'
import { createTrip, invitationToken, joinTrip } from '../lib/trips'
import type { TripDetail } from '../types/trips'
import { useLanguage } from '../lib/language'

export function CreateTripForm({ onCreated, onBack }: { onCreated: (trip: TripDetail) => void; onBack: () => void }) {
  const { t } = useLanguage()
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
    <button className="trip-back" onClick={onBack} disabled={busy}>{t("← Back to your trips")}</button>
    <p className="trip-eyebrow">{t('MAKE THE FIRST MOVE')}</p><h1>{t('Every trip starts')}<br />{t('with a plan.')}</h1>
    <p className="trip-intro-copy">{t("Give your next adventure a name. Bring your people along next.")}</p>
    <form className="trip-form" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      <label htmlFor="trip-title">{t('Trip name')} <span>{t('Required')}</span></label>
      <input id="trip-title" name="title" required minLength={2} maxLength={100} placeholder={t("A weekend worth getting away for")} value={title} disabled={busy} onChange={(event) => setTitle(event.target.value)} />
      <label htmlFor="trip-description">{t('A little about the trip')} <span>{t('Optional')}</span></label>
      <textarea id="trip-description" name="description" maxLength={500} rows={4} placeholder={t("A celebration, a catch-up, or just a change of scenery…")} value={description} disabled={busy} onChange={(event) => setDescription(event.target.value)} />
      <p className="trip-field-note">{t("You’ll be the trip administrator and a participating member.")}</p>
      {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
      <div className="trip-form-actions"><button className="trip-primary" disabled={busy || title.trim().length < 2}>{t(busy ? 'Creating your trip…' : 'Create trip')} <span aria-hidden="true">↗</span></button><button type="button" className="trip-text-button" onClick={onBack} disabled={busy}>{t('Cancel')}</button></div>
    </form>
  </section>
}

const CODE_LENGTH = 6

/** Six boxes for the code: typing moves on, Backspace moves back, and pasting a
 * code fills every box. Pasting a link switches to the link field. */
function CodeBoxes({ value, disabled, onChange, onLink }: { value: string; disabled: boolean; onChange: (code: string) => void; onLink: (link: string) => void }) {
  const { t } = useLanguage()
  const boxes = useRef<(HTMLInputElement | null)[]>([])
  const focus = (index: number) => boxes.current[Math.max(0, Math.min(CODE_LENGTH - 1, index))]?.focus()
  function type(index: number, typed: string) {
    const digits = typed.replace(/\D/g, '')
    if (!digits) return
    const next = (value.slice(0, index) + digits).slice(0, CODE_LENGTH)
    onChange(next)
    focus(next.length)
  }
  function key(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Backspace') {
      event.preventDefault()
      const at = value[index] ? index : index - 1
      if (at < 0) return
      onChange(value.slice(0, at))
      focus(at)
    } else if (event.key === 'ArrowLeft') focus(index - 1)
    else if (event.key === 'ArrowRight') focus(index + 1)
  }
  function paste(event: ClipboardEvent<HTMLInputElement>) {
    const text = event.clipboardData.getData('text').trim()
    event.preventDefault()
    if (/^\d[\d\s-]*$/.test(text)) { const code = text.replace(/\D/g, '').slice(0, CODE_LENGTH); onChange(code); focus(code.length) }
    else if (text) onLink(text)
  }
  return <div className="trip-code" role="group" aria-labelledby="trip-code-label" dir="ltr">
    {Array.from({ length: CODE_LENGTH }, (_, index) => <input
      key={index} ref={(element) => { boxes.current[index] = element }}
      className="trip-code-box" inputMode="numeric" autoComplete={index === 0 ? 'one-time-code' : 'off'}
      aria-label={t('Digit {number} of 6', { number: index + 1 })} maxLength={CODE_LENGTH}
      value={value[index] ?? ''} disabled={disabled} autoFocus={index === 0}
      onFocus={() => { if (index > value.length) focus(value.length) }}
      onChange={(event) => type(index, event.target.value)} onKeyDown={(event) => key(index, event)} onPaste={paste} />)}
  </div>
}

export function JoinTripForm({ initialInvitation, onJoined, onBack }: { initialInvitation: string | null; onJoined: (trip: TripDetail, alreadyMember: boolean) => void; onBack: () => void }) {
  const { t } = useLanguage()
  const startsWithLink = Boolean(initialInvitation && !/^\d{6}$/.test(initialInvitation.trim()))
  const [mode, setMode] = useState<'code' | 'link'>(startsWithLink ? 'link' : 'code')
  const [code, setCode] = useState(startsWithLink ? '' : (initialInvitation ?? '').trim())
  const [link, setLink] = useState(startsWithLink ? initialInvitation ?? '' : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const token = invitationToken(mode === 'code' ? code : link)
    if (!token) {
      setError(mode === 'code' ? 'Enter all 6 digits of the code your trip administrator shared.' : 'This is not a complete Rihla invitation link. Copy the whole link again, or use the 6-digit code instead.')
      return
    }
    setBusy(true); setError('')
    try { const result = await joinTrip(token); onJoined(result.trip, result.already_member) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not join this trip.') }
    finally { setBusy(false) }
  }
  const switchTo = (next: 'code' | 'link') => { setMode(next); setError('') }
  const ready = mode === 'code' ? code.length === CODE_LENGTH : link.trim().length > 0
  return <section className="trip-form-page">
    <button className="trip-back" onClick={onBack} disabled={busy}>{t("← Back to your trips")}</button>
    <p className="trip-eyebrow">{t('THERE’S A PLACE FOR YOU')}</p><h1>{t('Good company.')}<br /><span>{t('You’re invited.')}</span></h1>
    <p className="trip-intro-copy">{t("Enter the 6-digit code or paste the link your trip administrator shared with you.")}</p>
    <form className="trip-form" onSubmit={(event) => void submit(event)} aria-busy={busy}>
      {mode === 'code' ? <>
        <label id="trip-code-label">{t('Invitation code')}</label>
        <CodeBoxes value={code} disabled={busy} onChange={(next) => { setCode(next); setError('') }} onLink={(pasted) => { setLink(pasted); switchTo('link') }} />
        <button type="button" className="trip-text-button trip-code-switch" onClick={() => switchTo('link')} disabled={busy}>{t('Have a link instead? Paste it')}</button>
      </> : <>
        <label htmlFor="trip-invitation">{t('Invitation link')}</label>
        <input id="trip-invitation" name="invitation" type="url" maxLength={2048} autoComplete="off" spellCheck={false} placeholder={t('Paste the invitation link')} value={link} disabled={busy} autoFocus onChange={(event) => { setLink(event.target.value); setError('') }} />
        <button type="button" className="trip-text-button trip-code-switch" onClick={() => switchTo('code')} disabled={busy}>{t('Use the 6-digit code instead')}</button>
      </>}
      <p className="trip-field-note">{t("Invitations are valid for 7 days unless the administrator replaces or revokes them. Already a member? Joining again takes you to the same trip.")}</p>
      {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
      <div className="trip-form-actions"><button className="trip-primary" disabled={busy || !ready}>{t(busy ? 'Joining your group…' : 'Join trip')} <span aria-hidden="true">↗</span></button><button type="button" className="trip-text-button" onClick={onBack} disabled={busy}>{t('Cancel')}</button></div>
    </form>
  </section>
}
