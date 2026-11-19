import { useEffect, useId, useRef, useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { authenticatedRequest } from '../../lib/http'
import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { proposalTitle } from '../../lib/proposals'
import { longRequest } from '../../lib/proposalsHttp'
import type { Proposal } from '../../types/proposal'

export function ProposalFeedback({ proposal, isAdmin, stale, onChanged }: {
  proposal: Proposal; isAdmin: boolean; stale: boolean; onChanged: () => void
}) {
  const { t, language, locale } = useLanguage()
  const field = useId()
  const input = useRef<HTMLTextAreaElement>(null)
  const [open, setOpen] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(0)
  const [history, setHistory] = useState<Proposal[] | null>(null)
  const [reading, setReading] = useState(false)
  const base = `/api/trips/${proposal.trip_id}/proposals/${proposal.id}` as const
  const revision = proposal.revision ?? 1
  useEffect(() => { if (open) input.current?.focus() }, [open])
  async function submit() {
    if (busy || stale || !feedback.trim() || saved > revision) return
    setBusy(true); setError('')
    try {
      const result = await longRequest<{ revision: number }>(`${base}/revise`, {
        body: { feedback: feedback.trim(), revision }, timeoutMs: 600000,
      })
      setSaved(result.revision); setFeedback(''); setOpen(false); setHistory(null); onChanged()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not revise this proposal.') }
    finally { setBusy(false) }
  }
  async function toggleHistory() {
    if (history) { setHistory(null); return }
    setReading(true); setError('')
    try { setHistory(await authenticatedRequest<Proposal[]>(`${base}/history`)) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load proposals.') }
    finally { setReading(false) }
  }
  if (!isAdmin && revision === 1) return null
  return <section className="proposal-feedback">
    {isAdmin && <button type="button" className="trip-primary feedback-toggle" aria-expanded={open} disabled={busy || stale || saved > revision} onClick={() => setOpen(!open)}>
      <MessageSquare size={22} aria-hidden="true" />{t('What do you want to change')}
    </button>}
    {open && <form className="details-card feedback-form" onSubmit={event => { event.preventDefault(); void submit() }}>
      <label htmlFor={field}>{t('Describe the change you want in this proposal.')}</label>
      <textarea id={field} ref={input} value={feedback} maxLength={1500} rows={4} required disabled={busy} dir="auto" onChange={event => setFeedback(event.target.value)} />
      <p className="details-hint">{t('Only this option will be revised. A new itinerary needs fresh activity choices. Your other proposals stay the same.')}</p>
      <button className="trip-primary" disabled={busy || stale || !feedback.trim() || saved > revision}>{t(busy ? 'Revising your proposal…' : 'Revise this proposal')}</button>
    </form>}
    {saved > 0 && !open && <p role="status">{t('Revision {number} saved.', { number: saved })}</p>}
    {error && <p role="alert" className="trip-feedback trip-feedback--error">{t(error)}</p>}
    {revision > 1 && <><p>{t('Current version: {number}', { number: revision })}</p><button type="button" className="trip-secondary" disabled={reading} aria-expanded={!!history} onClick={() => void toggleHistory()}>{t('Earlier versions')}</button></>}
    {history?.map(item => <details key={item.revision ?? 1} className="details-card"><summary>{t('Version {number}', { number: item.revision ?? 1 })} · {proposalTitle(item, language)}</summary>
      <p>{calendarDate(item.start_date, locale)} – {calendarDate(item.end_date, locale)}</p>
      <ol>{item.cities.map(city => <li key={city.order}>{(language === 'ar' && city.city_ar) || city.city} · {t('{count} nights', { count: city.nights })}{city.hotel_name.value && ` · ${city.hotel_name.value}`}</li>)}</ol>
      {item.flights.map(route => <p key={route.origin}>{route.origin} → {item.destination} · {route.airline.value ?? t('Not available')}</p>)}
    </details>)}
  </section>
}
