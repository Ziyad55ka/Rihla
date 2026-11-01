import { useEffect, useState } from 'react'
import { airlineName } from '../../lib/airlines'
import { useLanguage } from '../../lib/language'
import { bookFlight, checkAndReload, type BookLeg, type FlightCheckResult, type FlightFacts, type FlightFallback, linkMinutesLeft, priceChange, refreshFlights, safeLink, sourceLabel } from '../../lib/proposals'
import { BagIcon, CheckIcon, ClockIcon, InfoIcon, SwapIcon } from './icons'
import { useSar } from './useSar'

const fallbackMessages: Record<FlightFallback, string> = {
  not_available: 'This flight is gone and we found no replacement in any source. These are search results for the same date.',
  limit: 'We reached the update limit for now. These are direct search results for your trip.',
  demo: 'Demo mode: no flight was checked. These are search results for the same date.',
  check_failed: 'We could not reach the flight sources just now, so nothing was checked. These are search results for the same date.',
  no_link: 'This flight exists, but its seller gives no page that opens it directly. These are search results for the same date.',
}

const cabinLabels: Record<string, string> = { economy: 'Economy', premium_economy: 'Premium economy', business: 'Business', first: 'First class' }
const clock = (value?: string | null) => /[T ](\d{2}:\d{2})/.exec(value ?? '')?.[1] ?? null

/** Ticks once a second while a timer is showing. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

export function FareLine({ facts }: { facts: Pick<FlightFacts, 'cabin_class' | 'fare_name' | 'checked_bags'> }) {
  const { t } = useLanguage()
  const cabin = facts.fare_name ?? (facts.cabin_class ? t(cabinLabels[facts.cabin_class] ?? 'Economy') : null)
  const bags = facts.checked_bags
  return <p className="details-fact">
    <BagIcon />
    {bags === null || bags === undefined
      ? <span>{cabin && <><bdi>{cabin}</bdi> · </>}{t('The price is for the cheapest fare available, and may not include a bag.')}</span>
      : <span>{cabin && <><bdi>{cabin}</bdi> · </>}{bags === 0 ? t('No checked bag') : t('{count} checked bags', { count: String(bags) })}</span>}
  </p>
}

function ChosenFlight({ facts }: { facts: FlightFacts }) {
  const { t, language } = useLanguage()
  if (facts.flights.length === 0) return null
  return <ul className="details-flight-list">{facts.flights.map((item) => <li key={item.direction}>
    <strong>{t(item.direction === 'outbound' ? 'Outbound' : 'Return')}</strong>
    {item.airline && <bdi>{airlineName(item.airline, language)}</bdi>}
    {item.flight_number && <bdi>{item.flight_number}</bdi>}
    {clock(item.departure_time) && clock(item.arrival_time) && <span><bdi>{clock(item.departure_time)}</bdi> – <bdi>{clock(item.arrival_time)}</bdi></span>}
  </li>)}</ul>
}

function PriceChange({ result }: { result: FlightCheckResult }) {
  const { t } = useLanguage()
  const sar = useSar()
  const change = priceChange(result.price_sar, result.previous_price_sar)
  if (change) return <p className="details-change details-change--moved" role="status">{t('Was {old} → now {new} ({difference})', { old: sar(change.previous), new: sar(change.price), difference: `${change.difference > 0 ? '+' : '−'}${sar(Math.abs(change.difference))}` })}</p>
  if (result.price_sar && !result.fallback && result.checked_at) return <p className="details-change" role="status"><CheckIcon /> {t('Checked just now. The price is the same.')}</p>
  return null
}

function Alternative({ result }: { result: FlightCheckResult }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const found = result.alternative
  if (!found) return null
  const link = safeLink(found.url)
  const titles = { gone: 'The original flight is gone. We found a replacement.', no_link: 'This flight can’t be opened directly. This one can.', cheaper: 'A cheaper option you can book directly' }
  return <div className="details-alternative">
    <p className="details-alternative-title"><SwapIcon /> {t(titles[found.reason])}</p>
    <ChosenFlight facts={found} />
    {found.price_sar && <p className="details-alternative-price">{t('From {amount}', { amount: sar(found.price_sar) })} <span className="details-hint">{t('per person')}</span></p>}
    {found.seller && <p className="details-hint">{t('Sold by {seller}', { seller: airlineName(found.seller, language) })}</p>}
    {found.within_budget === false && <p className="proposals-review">{t('This option is over the group budget.')}</p>}
    {link && found.reason !== 'gone' && <a className="trip-secondary" href={link} target="_blank" rel="noopener noreferrer">{t('Open this flight')} <span aria-hidden="true">↗</span></a>}
  </div>
}

export function BookResultView({ result, onRecheck, now }: { result: FlightCheckResult; onRecheck?: () => void; now?: number }) {
  const { t, language, locale } = useLanguage()
  const ticking = useNow(!result.fallback && Boolean(result.checked_at))
  const left = linkMinutesLeft(result.checked_at, result.link_valid_minutes, now ?? ticking)
  const expired = !result.fallback && left === 0
  const link = safeLink(result.url)
  const first = result.flights[0]
  const time = clock(first?.departure_time)
  return <div className="details-book-result">
    <PriceChange result={result} />
    {result.fallback && <p>{t(fallbackMessages[result.fallback])}</p>}
    {!result.fallback && <>
      <FareLine facts={result} />
      <p className="details-fact"><InfoIcon /> <span>{t(sourceLabel({ ...result, price_source: result.seller_type ? 'seller' : 'search' }))}{result.seller && <> · {t('Sold by {seller}', { seller: airlineName(result.seller, language) })}</>}</span></p>
      {!result.exact_flight && <p className="proposals-review">{first?.flight_number && time ? t('This is a results page. Choose flight {flight} at {time}.', { flight: first.flight_number, time }) : t('This is a results page. Choose the same flight there.')}</p>}
    </>}
    {expired
      ? <><p className="proposals-review" role="status"><ClockIcon /> {t('This link may have expired. Check again.')}</p>{onRecheck && <button type="button" className="trip-secondary" onClick={onRecheck}>{t('Check again')}</button>}</>
      : <>
        {link && <a className={result.fallback ? 'trip-secondary' : 'trip-primary'} href={link} target="_blank" rel="noopener noreferrer">{t(result.fallback ? 'Open the search results' : 'Open the booking page')} <span aria-hidden="true">↗</span></a>}
        {!result.fallback && left !== null && <p className="details-timer" role="timer"><ClockIcon /> {left === 1 ? t('The link should work for about a minute more. Finish booking now.') : t('The link should work for about {count} more minutes. Finish booking now.', { count: left.toLocaleString(locale) })}</p>}
      </>}
    <Alternative result={result} />
  </div>
}

/** Off for a while after each press, to protect the free requests. */
function useCooldown(minutes: number) {
  const [until, setUntil] = useState(0)
  const now = useNow(until > 0)
  const seconds = Math.max(0, Math.ceil((until - now) / 1000))
  return { waitMinutes: Math.ceil(seconds / 60), start: () => setUntil(Date.now() + minutes * 60000) }
}

export function BookSteps({ busy, result }: { busy: boolean; result: FlightCheckResult | null }) {
  const { t } = useLanguage()
  const stage = busy ? 1 : result ? 3 : 0
  if (stage === 0) return null
  const steps = ['Checking the price and seats now…', 'Check the result', 'Open the booking page']
  return <ol className="details-steps">{steps.map((label, index) => <li key={label} className={index + 1 < stage ? 'is-done' : index + 1 === stage || (stage === 3 && index === 1) ? 'is-now' : ''} aria-current={index + 1 === stage ? 'step' : undefined}><span aria-hidden="true">{index + 1 < stage ? <CheckIcon /> : (index + 1).toLocaleString()}</span>{t(label)}</li>)}</ol>
}

export function BookFlight({ tripId, proposalId, leg, label, cooldownMinutes, onChanged }: { tripId: string; proposalId: string; leg: BookLeg; label: string; cooldownMinutes: number; onChanged: () => void }) {
  const { t, locale } = useLanguage()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<FlightCheckResult | null>(null)
  const [error, setError] = useState('')
  const { waitMinutes, start } = useCooldown(cooldownMinutes)
  async function check() {
    setBusy(true); setError(''); setResult(null); start()
    try { setResult(await checkAndReload(() => bookFlight(tripId, proposalId, leg), onChanged)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not check this flight.') }
    finally { setBusy(false) }
  }
  return <div className="details-booking">
    {!result && <button type="button" className="trip-primary" disabled={busy || waitMinutes > 0} onClick={() => { void check() }}>{busy ? t('Checking…') : label}</button>}
    {!result && !busy && waitMinutes > 0 && <p className="details-hint">{t('You can check again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    <BookSteps busy={busy} result={result} />
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <BookResultView result={result} onRecheck={waitMinutes > 0 ? undefined : () => { void check() }} />}
    {!result && !busy && <p className="details-hint">{t('We check the flight when you press, then give you the seller’s page.')}</p>}
  </div>
}

export function RefreshView({ waitMinutes, busy, result, error, onRefresh }: { waitMinutes: number; busy: boolean; result: FlightCheckResult | null; error: string; onRefresh: () => void }) {
  const { t, locale } = useLanguage()
  const link = result?.fallback ? safeLink(result.url) : null
  return <div className="details-refresh">
    <button type="button" className="trip-secondary" disabled={busy || waitMinutes > 0} onClick={onRefresh}>{busy ? t('Checking…') : t('Refresh the price')}</button>
    {waitMinutes > 0 && !busy && <p className="details-hint">{t('You can check again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <PriceChange result={result} />}
    {result?.now_over_budget && <p className="proposals-review" role="status">{t('With the new price, this proposal is over the group budget.')}</p>}
    {result?.fallback && <p className="proposals-review" role="status">{t(fallbackMessages[result.fallback])}</p>}
    {link && <a className="trip-secondary" href={link} target="_blank" rel="noopener noreferrer">{t('Open the search results')} <span aria-hidden="true">↗</span></a>}
    {result && <Alternative result={result} />}
  </div>
}

export function RefreshFlights({ tripId, proposalId, cooldownMinutes, onChanged }: { tripId: string; proposalId: string; cooldownMinutes: number; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<FlightCheckResult | null>(null)
  const [error, setError] = useState('')
  const { waitMinutes, start } = useCooldown(cooldownMinutes)
  async function refresh() {
    setBusy(true); setError(''); start()
    try { setResult(await checkAndReload(() => refreshFlights(tripId, proposalId), onChanged)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not check this flight.') }
    finally { setBusy(false) }
  }
  return <RefreshView waitMinutes={waitMinutes} busy={busy} result={result} error={error} onRefresh={() => { void refresh() }} />
}
