import { useEffect, useState } from 'react'
import { PreferencesPanel } from '../components/PreferencesPanel'
import { PlanningPanel } from '../components/PlanningPanel'
import { getInvitation, getTrip, invitationUrl, issueInvitation, revokeInvitation } from '../lib/trips'
import type { InvitationStatus, TripDetail } from '../types/trips'

function date(value: string) { return new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) }

function InvitationPanel({ tripId }: { tripId: string }) {
  const [status, setStatus] = useState<InvitationStatus | null>(null)
  const [link, setLink] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(true)
  const [copied, setCopied] = useState(false)
  const [confirm, setConfirm] = useState<'replace' | 'revoke' | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setBusy(true); setError('')
    getInvitation(tripId, controller.signal).then((value) => { if (!controller.signal.aborted) setStatus(value) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not check the invitation.') })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [tripId, attempt])

  async function issue() {
    setBusy(true); setError(''); setConfirm(null)
    try {
      const invitation = await issueInvitation(tripId)
      setLink(invitationUrl(invitation.token)); setCopied(false)
      setStatus({ exists: true, expires_at: invitation.expires_at, revoked: false })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not create the invitation.') }
    finally { setBusy(false) }
  }
  async function revoke() {
    setBusy(true); setError(''); setConfirm(null)
    try { setStatus(await revokeInvitation(tripId)); setLink(''); setCopied(false) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not revoke the invitation.') }
    finally { setBusy(false) }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); setError('') }
    catch { setError('Clipboard access is unavailable. Select the link and copy it manually.') }
  }
  const active = !!status?.exists && !status.revoked && !!status.expires_at && new Date(status.expires_at).getTime() > Date.now()
  return <section className="trip-invite-panel" aria-labelledby="invite-title">
    <p className="trip-eyebrow">BETTER WITH YOUR PEOPLE</p><h2 id="invite-title">Bring them along.</h2>
    <p>Share one invitation with your group. Each new link is valid for 7 days.</p>
    <div className="trip-invite-status" role="status">{busy ? 'Checking invitation…' : !status ? 'Invitation unavailable' : !status.exists ? 'No invitation created yet' : status.revoked ? 'Invitation revoked' : active ? 'Invitation active' : 'Invitation expired'}
      {status?.exists && status.expires_at && !status.revoked && <span>{active ? 'Expires' : 'Expired'} {date(status.expires_at)}</span>}</div>
    {link && active && <div className="trip-copy-link"><label htmlFor="share-invitation">Your invitation link</label><div><input id="share-invitation" readOnly value={link} onFocus={(event) => event.currentTarget.select()} /><button type="button" className="trip-secondary" onClick={() => void copy()}>{copied ? 'Copied ✓' : 'Copy'}</button></div></div>}
    {!link && active && <p className="trip-field-note">Links are shown when created. Replace the invitation to get a new link to copy.</p>}
    {confirm ? <div className="trip-confirm-action"><p>{confirm === 'replace' ? 'The previous link will stop working. Share the new link with anyone who hasn’t joined yet.' : 'This link will stop accepting new members. People who already joined will stay in the trip.'}</p>
      <div className="trip-button-row"><button type="button" className="trip-primary" disabled={busy} onClick={() => void (confirm === 'replace' ? issue() : revoke())}>{confirm === 'replace' ? 'Replace invitation' : 'Revoke invitation'}</button><button type="button" className="trip-text-button" onClick={() => setConfirm(null)}>Cancel</button></div></div>
      : <div className="trip-button-row"><button type="button" className="trip-primary" disabled={busy || !status} onClick={() => status?.exists ? setConfirm('replace') : void issue()}>{status?.exists ? 'Create a new link' : 'Create invitation'} <span aria-hidden="true">↗</span></button>
        {active && <button type="button" className="trip-text-button trip-danger" disabled={busy} onClick={() => setConfirm('revoke')}>Revoke link</button>}</div>}
    {error && <div className="trip-feedback trip-feedback--error" role="alert">{error} <button className="trip-text-button" type="button" disabled={busy} onClick={() => setAttempt((value) => value + 1)}>Check again</button></div>}
  </section>
}

export function TripDetailPage({ tripId, notice, onBack }: { tripId: string; notice: string; onBack: () => void }) {
  const [trip, setTrip] = useState<TripDetail | null>(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [savedRevision, setSavedRevision] = useState(0)
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') setAttempt((value) => value + 1) }
    const timer = window.setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setChecking(true); setError('')
    getTrip(tripId, controller.signal).then((value) => { if (!controller.signal.aborted) setTrip(value) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load this trip.') })
      .finally(() => { if (!controller.signal.aborted) setChecking(false) })
    return () => controller.abort()
  }, [tripId, attempt])
  return <section className="trip-detail-page">
    <button type="button" className="trip-back" onClick={onBack}>← Back to your trips</button>
    {error && !trip ? <div className="trip-feedback trip-feedback--error" role="alert">{error}<button type="button" className="trip-text-button" onClick={() => setAttempt((value) => value + 1)}>Try again</button></div>
      : !trip ? <p className="trip-loading" role="status">Getting your group together…</p>
      : <><div className="trip-detail-heading"><p className="trip-eyebrow">YOUR NEXT ADVENTURE</p><h1>{trip.title}</h1>
        {trip.description && <p className="trip-intro-copy">{trip.description}</p>}
        <div className="trip-detail-meta"><span className="trip-role">{trip.role === 'administrator' ? 'You’re the administrator' : 'You’re a member'}</span><span>{trip.member_count} {trip.member_count === 1 ? 'person' : 'people'} in the group</span><button type="button" className="trip-text-button" disabled={checking} onClick={() => setAttempt((value) => value + 1)}>{checking ? 'Refreshing…' : 'Refresh group'}</button></div></div>
        {notice && <p className="trip-feedback trip-feedback--success" role="status">{notice}</p>}
        {error && <p className="trip-feedback trip-feedback--error" role="alert">Could not refresh the group. {error} Your preference edits are still here.</p>}
        <div className="trip-detail-grid"><section className="trip-members-panel" aria-labelledby="members-title"><div className="trip-panel-title"><h2 id="members-title">Your people</h2><span>{trip.member_count.toString().padStart(2, '0')}</span></div>
          <ul className="trip-member-list">{trip.members.map((member) => <li key={member.user_id}><span className="trip-member-avatar" aria-hidden="true">{member.display_name.slice(0, 1).toUpperCase()}</span><span className="trip-member-name">{member.display_name}</span><span className="trip-member-role">{member.role === 'administrator' ? 'Administrator' : 'Member'}</span></li>)}</ul>
          <p className="trip-field-note">A shared trip. A place for everyone.</p></section>
          {trip.role === 'administrator' ? <InvitationPanel tripId={trip.id} /> : <aside className="trip-member-welcome"><span aria-hidden="true">↗</span><h2>You’re part of the plan.</h2><p>Your trip administrator manages invitations. Your own preferences and budget stay private.</p></aside>}</div>
        <PlanningPanel key={`planning-${trip.id}`} trip={trip} revision={attempt + savedRevision} onRefresh={() => setAttempt((value) => value + 1)} />
        <PreferencesPanel key={trip.id} tripId={trip.id} onSaved={() => setSavedRevision((value) => value + 1)} />
      </>}
  </section>
}
