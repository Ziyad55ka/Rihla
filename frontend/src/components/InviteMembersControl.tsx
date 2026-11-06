import { useLanguage } from '../lib/language'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { invitationUrl, issueInvitation } from '../lib/trips'
import { FlyIcon } from './FlightIcons'

export function InviteMembersControl({ tripId }: { tripId: string }) {
  const { t } = useLanguage()
  const [link, setLink] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<'link' | 'code' | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const closeButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)
    closeButton.current?.focus()
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', closeOnEscape) }
  }, [open])

  async function invite() {
    if (link) { setCopied(null); setOpen(true); return }
    setBusy(true)
    setError('')
    try {
      const invitation = await issueInvitation(tripId)
      setLink(invitationUrl(invitation.token))
      setCode(invitation.code)
      setCopied(null)
      setOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create an invitation link.')
    } finally {
      setBusy(false)
    }
  }

  async function copy(value: string, kind: 'link' | 'code') {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(kind)
      setError('')
    } catch {
      setError('Clipboard access is unavailable. Select the value and copy it manually.')
    }
  }

  return <div className="planning-invite-control">
    <button className="planning-invite-button" type="button" disabled={busy} onClick={() => void invite()}>{busy ? t("Creating link…") : t("Invite members")} <span aria-hidden="true"><FlyIcon /></span></button>
    {error && !open && <p className="planning-invite-error" role="alert">{t(error)}</p>}
    {open && link && createPortal(<div className="planning-invite-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section className="planning-invite-dialog" role="dialog" aria-modal="true" aria-labelledby="invitation-dialog-title">
        <button ref={closeButton} className="planning-invite-close" type="button" aria-label={t("Close invitation")} onClick={() => setOpen(false)}>×</button>
        <p className="trip-eyebrow">{t("BRING YOUR PEOPLE")}</p>
        <h2 id="invitation-dialog-title">{t("Invite members")}</h2>
        <p>{t("Share the simple code, or copy the full link.")}</p>
        <div className="planning-invite-code">
          <label htmlFor={`trip-invitation-code-${tripId}`}>{t("6-digit code")}</label>
          <div><input id={`trip-invitation-code-${tripId}`} readOnly value={code} onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={() => void copy(code, 'code')}>{copied === 'code' ? t("Copied ✓") : t("Copy code")}</button></div>
        </div>
        <div className="planning-invite-link">
          <label htmlFor={`trip-invitation-${tripId}`}>{t("Invitation link")}</label>
          <div><input id={`trip-invitation-${tripId}`} readOnly value={link} onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={() => void copy(link, 'link')}>{copied === 'link' ? t("Copied ✓") : t("Copy link")}</button></div>
        </div>
        {error && <p className="planning-invite-error" role="alert">{t(error)}</p>}
      </section>
    </div>, document.body)}
  </div>
}
