import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import { bookFlight, type BookFlightResult, type BookLeg, refreshFlights, type RefreshFlightsResult, refreshWaitMinutes, safeLink } from '../../lib/proposals'
import { useSar } from './useSar'

const fallbackMessages = {
  not_available: 'The original flight is no longer available. These are search results for the same date.',
  limit: 'We reached today’s update limit. These are direct search results for your trip.',
  demo: 'Demo mode: no flight was checked. These are search results for the same date.',
} as const

export function BookResultView({ result }: { result: BookFlightResult }) {
  const { t } = useLanguage()
  const sar = useSar()
  const link = safeLink(result.url)
  const changed = result.previous_price_sar && result.price_sar
  return <div className="details-book-result" role="status">
    {result.fallback && <p>{t(fallbackMessages[result.fallback])}</p>}
    {!result.fallback && changed && <p>{t('The price is now {new} instead of {old}. Continue?', { new: sar(result.price_sar as string), old: sar(result.previous_price_sar as string) })}</p>}
    {!result.fallback && result.seller && <p className="details-hint">{t('Sold by {seller}', { seller: result.seller })}</p>}
    {!result.fallback && !result.exact_flight && <p className="details-hint">{t('This page shows search results. Choose the same flight there.')}</p>}
    {link && <a className="trip-primary" href={link} target="_blank" rel="noopener noreferrer">{t(result.fallback ? 'Open the search results' : changed ? 'Continue to the seller' : 'Open the seller’s page')} <span aria-hidden="true">↗</span></a>}
  </div>
}

export function BookFlight({ tripId, proposalId, leg, label }: { tripId: string; proposalId: string; leg: BookLeg; label: string }) {
  const { t } = useLanguage()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<BookFlightResult | null>(null)
  const [error, setError] = useState('')
  async function check() {
    setBusy(true); setError(''); setResult(null)
    try { setResult(await bookFlight(tripId, proposalId, leg)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not check this flight.') }
    finally { setBusy(false) }
  }
  return <div className="details-booking">
    <button type="button" className="trip-primary" disabled={busy} onClick={() => { void check() }}>{busy ? t('Checking the flight…') : label}</button>
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <BookResultView result={result} />}
    <p className="details-hint">{t('Prices and seats change constantly and we cannot guarantee them. We check the flight when you press, then send you to the seller’s site. Finish booking quickly, because the booking page can expire soon.')}</p>
  </div>
}

export function RefreshView({ waitMinutes, busy, result, error, onRefresh }: { waitMinutes: number; busy: boolean; result: RefreshFlightsResult | null; error: string; onRefresh: () => void }) {
  const { t, locale } = useLanguage()
  const link = result?.url ? safeLink(result.url) : null
  return <div className="details-refresh">
    <button type="button" className="trip-secondary" disabled={busy || waitMinutes > 0} onClick={onRefresh}>{busy ? t('Checking the flight…') : t('Refresh the flight price')}</button>
    {waitMinutes > 0 && <p className="details-hint">{t('You can refresh again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result?.now_over_budget && <p className="proposals-review" role="status">{t('With the new price, this proposal is over the group budget.')}</p>}
    {result?.fallback && <p className="proposals-review" role="status">{t(fallbackMessages[result.fallback])}</p>}
    {link && <a className="trip-secondary" href={link} target="_blank" rel="noopener noreferrer">{t('Open the search results')} <span aria-hidden="true">↗</span></a>}
  </div>
}

export function RefreshFlights({ tripId, proposalId, pricedAt, cooldownMinutes, onChanged }: { tripId: string; proposalId: string; pricedAt?: string | null; cooldownMinutes: number; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<RefreshFlightsResult | null>(null)
  const [error, setError] = useState('')
  async function refresh() {
    setBusy(true); setError('')
    try {
      const next = await refreshFlights(tripId, proposalId)
      setResult(next)
      if (next.updated) onChanged()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not check this flight.') }
    finally { setBusy(false) }
  }
  return <RefreshView waitMinutes={refreshWaitMinutes(pricedAt, cooldownMinutes, Date.now())} busy={busy} result={result} error={error} onRefresh={() => { void refresh() }} />
}
