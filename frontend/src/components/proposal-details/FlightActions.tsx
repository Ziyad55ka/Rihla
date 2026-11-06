import { useEffect, useRef, useState } from 'react'
import { checkMessages } from '../../lib/aiStatus'
import { airlineName } from '../../lib/airlines'
import { useLanguage } from '../../lib/language'
import type { AirlineFareNote } from '../../types/proposal'
import { bookFlight, checkAndReload, type BookLeg, type FlightCheckResult, type FlightFacts, type FlightFallback, linkFractionLeft, linkMinutesLeft, localTime, priceChange, refreshFlights, reportFlightNotOffered, safeLink, sourceLabel } from '../../lib/proposals'
import { AiStatus } from '../AiStatus'
import { Hint } from './Hint'
import { BagIcon, CheckIcon, ChevronIcon, ClockIcon, ExternalIcon, InfoIcon, RefreshIcon } from './icons'
import { useSar } from './useSar'

// Say what happened and what to do; Google Flights is only the last resort.
const fallbackMessages: Record<FlightFallback, string> = {
  not_available: 'This flight is no longer offered on these dates, and no other flight was found. Change the trip dates, or try again later.',
  limit: 'Flight checking is temporarily limited. Nothing was checked.',
  demo: 'Demo mode: no flight was checked.',
  check_failed: 'We could not reach the flight sources just now. Try again in a few minutes.',
  no_link: 'We could not confirm outbound and return on one booking just now. Try again in a few minutes, or change the dates.',
}

/** Why there is no booking page, when to try again and, after a second failure,
 * the search on Google Flights as the last resort. */
function FallbackNote({ result, failures, onRetry }: { result: FlightCheckResult; failures: number; onRetry?: () => void }) {
  const { t, locale } = useLanguage()
  const fallback = result.fallback
  if (!fallback) return null
  const retry = result.retry_at ? new Date(result.retry_at) : null
  const time = retry && Number.isFinite(retry.getTime()) ? retry.toLocaleString(locale, { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : null
  const link = (failures >= 2 || fallback === 'demo') ? safeLink(result.url) : null
  return <div className="details-fallback details-reveal" role="status">
    <p className="details-note">{t(fallbackMessages[fallback])}{fallback === 'limit' && time && <> {t('Try again after {time}.', { time })}</>}</p>
    {fallback !== 'limit' && fallback !== 'demo' && onRetry && <button type="button" className="trip-secondary" onClick={onRetry}>{t('Check again')}</button>}
    {link && <a className="details-text-link" href={link} target="_blank" rel="noopener noreferrer">{t('Still not working? Search these dates on Google Flights')} <ExternalIcon /></a>}
  </div>
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

/** What the price may leave out. Rihla only gives the link and the price, so the
 * airline's site decides any extra cost; the member reads this before paying. */
export function ExtraFeesNote({ checkedBags }: { checkedBags?: number | null }) {
  const { t, locale } = useLanguage()
  const bag = checkedBags === 0
    ? t('This fare does not include a checked bag.')
    : checkedBags && checkedBags > 0
      ? t('This fare includes {count} checked bags.', { count: checkedBags.toLocaleString(locale) })
      : t('The price is for the cheapest fare, which may not include a checked bag.')
  return <p className="details-fees" role="note"><InfoIcon /> <span>{bag} {t('The airline may charge extra for bags, seat choice or other options. Check them on the airline’s site before paying: Rihla gives the link and the price only.')}</span></p>
}

/** The source's own fare and bag first, then what is generally known of the airline. */
export function FareLine({ facts }: { facts: Pick<FlightFacts, 'cabin_class' | 'fare_name' | 'checked_bags'> & { airline_fares?: AirlineFareNote[] } }) {
  const { t, language, locale } = useLanguage()
  const cabin = facts.fare_name ?? (facts.cabin_class ? t(cabinLabels[facts.cabin_class] ?? 'Economy') : null)
  const bags = facts.checked_bags
  if (bags !== null && bags !== undefined) return <span className="details-chip"><BagIcon /> {cabin && <><bdi>{cabin}</bdi> · </>}{bags === 0 ? t('No checked bag') : t('{count} checked bags', { count: bags.toLocaleString(locale) })}</span>
  const notes = facts.airline_fares ?? []
  if (notes.length === 0) return <span className="details-chip"><BagIcon /> {cabin ? <bdi>{cabin}</bdi> : t('Cheapest fare')}<Hint text={t('The price is for the cheapest fare available, and may not include a bag.')} /></span>
  return <>{notes.map((note) => <span className="details-chip" key={note.code}><BagIcon /> <bdi>{language === 'ar' ? note.name_ar : note.name_en}</bdi> · <bdi>{language === 'ar' ? note.fare_ar : note.fare_en}</bdi> · {note.checked_kg === null || note.checked_kg === undefined ? t('Check the bag on the airline’s site') : note.checked_kg === 0 ? t('No checked bag') : t('Checked bag {kg} kg', { kg: note.checked_kg.toLocaleString(locale) })}<Hint text={t('General information about the airline’s cheapest fare, not a promise for your ticket.')} /></span>)}</>
}

function ChosenFlight({ facts }: { facts: FlightFacts }) {
  const { t, language, locale } = useLanguage()
  if (facts.flights.length === 0) return null
  return <ul className="details-flight-list">{facts.flights.map((item) => {
    const departs = clock(item.departure_time)
    const arrives = clock(item.arrival_time)
    return <li key={item.direction}>
      <strong>{t(item.direction === 'outbound' ? 'Outbound' : 'Return')}</strong>
      {item.airline && <bdi>{airlineName(item.airline, language)}</bdi>}
      {item.flight_number && <bdi>{item.flight_number}</bdi>}
      {departs && arrives && <span><bdi>{localTime(departs, locale)}</bdi> – <bdi>{localTime(arrives, locale)}</bdi></span>}
    </li>
  })}</ul>
}

function PriceChange({ result }: { result: FlightCheckResult }) {
  const { t } = useLanguage()
  const sar = useSar()
  const change = priceChange(result.price_sar, result.previous_price_sar)
  if (change) return <p className={`details-change details-reveal ${change.difference > 0 ? 'details-change--up' : 'details-change--down'}`} role="status">{t('Was {old}, now {new} ({difference})', { old: sar(change.previous), new: sar(change.price), difference: `${change.difference > 0 ? '+' : '-'}${sar(Math.abs(change.difference))}` })}</p>
  if (result.price_sar && !result.fallback && result.checked_at) return <p className="details-change details-reveal" role="status"><CheckIcon /> {t('Checked just now. The price is the same.')}</p>
  return null
}

function Alternative({ result }: { result: FlightCheckResult }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const found = result.alternative
  if (!found) return null
  const link = safeLink(found.url)
  const name = found.seller ? airlineName(found.seller, language) : t('Another flight')
  const amount = found.price_sar ? sar(found.price_sar) : ''
  const titles = { gone: 'The original flight is gone. Replacement: {name} · {amount}', no_link: 'Bookable directly: {name} · {amount}', cheaper: 'Cheaper option available: {name} · {amount}', agent: 'Cheaper through a travel agent: {name} · {amount}' }
  return <details className="details-alternative details-reveal" open={found.reason === 'gone'}>
    <summary><span>{t(titles[found.reason], { name, amount })}</span><ChevronIcon /></summary>
    <div className="details-alternative-body">
      <ChosenFlight facts={found} />
      {found.reason === 'agent' && <p className="details-hint">{t('This is an agent, not the airline, so check its fees and terms before paying.')}</p>}
      {found.within_budget === false && <p className="details-note">{t('This option is over the group budget.')}</p>}
      {link && found.reason !== 'gone' && <a className="trip-secondary" href={link} target="_blank" rel="noopener noreferrer">{t('Open this flight')} <ExternalIcon /></a>}
    </div>
  </details>
}

/** What to do on the seller's page, since airlines show the outbound price first. */
function BookGuide({ result, leg }: { result: FlightCheckResult; leg: BookLeg }) {
  const { t, language, locale } = useLanguage()
  const sar = useSar()
  const flightText = (direction: 'outbound' | 'return') => {
    const item = result.flights.find((flight) => flight.direction === direction)
    if (!item?.flight_number) return null
    const time = clock(item.departure_time)
    return time ? t('{flight} at {time}', { flight: item.flight_number, time: localTime(time, locale) }) : item.flight_number
  }
  const notes = result.airline_fares
  const fare = result.fare_name ?? (notes.length === 1 ? (language === 'ar' ? notes[0].fare_ar : notes[0].fare_en) : null)
  const price = result.price_sar ? sar(result.price_sar) : null
  const outbound = flightText('outbound')
  const back = flightText('return')
  if (!price) return null
  if (leg === 'round_trip' && outbound && back) return <p className="details-guide">{t(fare ? 'Choose the outbound {outbound}, then the return {back}, in the {fare} fare, and check the total is close to {price}.' : 'Choose the outbound {outbound}, then the return {back}, and check the total is close to {price}.', { outbound, back, price, fare: fare ?? '' })}</p>
  const flight = leg === 'inbound' ? back : outbound
  if (leg === 'round_trip' || !flight) return null
  return <p className="details-guide">{t('Choose flight {flight}, and check the price is close to {price}.', { flight, price })}</p>
}

/** A ring that empties as the link's time runs out. The words beside it carry the meaning. */
export function TimerRing({ fraction }: { fraction: number }) {
  return <svg className="details-ring" viewBox="0 0 36 36" width="24" height="24" aria-hidden="true" focusable="false">
    <circle className="details-ring-track" cx="18" cy="18" r="15" pathLength="100" />
    <circle className="details-ring-value" cx="18" cy="18" r="15" pathLength="100" strokeDasharray="100" strokeDashoffset={100 - fraction * 100} />
  </svg>
}

export function BookResultView({ result, leg = 'round_trip', onRecheck, onNotOffered, now, failures = 1 }: { result: FlightCheckResult; leg?: BookLeg; onRecheck?: () => void; onNotOffered?: () => void; now?: number; failures?: number }) {
  const { t, language, locale } = useLanguage()
  const ticking = useNow(!result.fallback && Boolean(result.checked_at))
  const time = now ?? ticking
  const left = linkMinutesLeft(result.checked_at, result.link_valid_minutes, time)
  const expired = !result.fallback && left === 0
  const link = safeLink(result.url)
  // Both chosen flights already selected, which the airline's own link may not keep.
  const itinerary = leg === 'round_trip' ? safeLink(result.itinerary_url ?? null) : null
  // The seller's own page with the flights, fare and travellers already chosen.
  const direct = !result.fallback && leg === 'round_trip' && result.exact_flight && Boolean(link)
  return <div className="details-book-result details-reveal">
    <PriceChange result={result} />
    {result.fallback && <FallbackNote result={result} failures={failures} onRetry={onRecheck} />}
    {!result.fallback && <>
      {result.seller && <p className="details-hint details-inline">{t('Sold by {seller}', { seller: airlineName(result.seller, language) })}<Hint text={[t(sourceLabel({ ...result, price_source: result.seller_type ? 'seller' : 'search' })), ...(result.exact_flight ? [] : [t('This is a results page, so choose the flight yourself.')])].join(' · ')} /></p>}
      {!direct && <BookGuide result={result} leg={leg} />}
    </>}
    {expired
      ? <><p className="details-note" role="status"><ClockIcon /> {t('This link may have expired. Check again.')}</p>{onRecheck && <button type="button" className="trip-secondary" onClick={onRecheck}>{t('Check again')}</button>}</>
      : <>
        {link && !result.fallback && <a className="trip-primary" href={link} target="_blank" rel="noopener noreferrer">{t(direct ? 'Continue to the booking page' : 'Open the booking page')} <ExternalIcon /></a>}
        {direct && <p className="details-hint">{t('This link requests both flights for your group. Check the dates, travellers and final fare on the airline’s page.')}</p>}
        {itinerary && !direct && <a className="details-text-link" href={itinerary} target="_blank" rel="noopener noreferrer">{t('See these exact flights on Google Flights')} <ExternalIcon /></a>}
        {!result.fallback && <ExtraFeesNote checkedBags={result.checked_bags} />}
        {!result.fallback && left !== null && <p className="details-timer" role="timer"><TimerRing fraction={linkFractionLeft(result.checked_at, result.link_valid_minutes, time)} /> {left === 1 ? t('The link should work for about a minute more. Finish booking now.') : t('The link should work for about {count} more minutes. Finish booking now.', { count: left.toLocaleString(locale) })}</p>}
        {/* Search data can lag behind the airline (Nielsen 9: a way to recover). */}
        {!result.fallback && onNotOffered && <p className="details-hint details-not-offered">{t('The site did not show this flight?')} <button type="button" className="details-text-button" onClick={onNotOffered}>{t('Find another flight')}</button></p>}
        {!result.fallback && onRecheck && <button type="button" className="trip-secondary" onClick={onRecheck}>{t('Refresh the price')}</button>}
      </>}
    <Alternative result={result} />
  </div>
}

/** Off for a while after each press, to protect the free requests. */
function useCooldown(minutes: number) {
  const [until, setUntil] = useState(0)
  const now = useNow(until > 0)
  const seconds = Math.max(0, Math.ceil((until - now) / 1000))
  return { waitMinutes: Math.ceil(seconds / 60), start: () => setUntil(Date.now() + minutes * 60000), deferUntil: (deadline: number) => { if (Number.isFinite(deadline)) setUntil(previous => Math.max(previous, deadline)) } }
}

export function BookSteps({ busy, result }: { busy: boolean; result: FlightCheckResult | null }) {
  const { t } = useLanguage()
  const stage = busy ? 1 : result ? 3 : 0
  if (stage === 0) return null
  return <div className="details-steps-bar" role="progressbar" aria-label={t('Booking steps')} aria-valuemin={0} aria-valuemax={3} aria-valuenow={stage}><span style={{ transform: `scaleX(${stage / 3})` }} /></div>
}

export function BookFlight({ tripId, proposalId, leg, label, cooldownMinutes, onChanged }: { tripId: string; proposalId: string; leg: BookLeg; label: string; cooldownMinutes: number; onChanged: () => void }) {
  const { t, locale } = useLanguage()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<FlightCheckResult | null>(null)
  const [error, setError] = useState('')
  const [failures, setFailures] = useState(0)
  const { waitMinutes, start, deferUntil } = useCooldown(cooldownMinutes)
  const inFlight = useRef(false)
  async function check(notOffered = false) {
    if (inFlight.current || waitMinutes > 0) return
    inFlight.current = true
    setBusy(true); setError(''); setResult(null); start()
    try {
      const found = await checkAndReload(() => notOffered ? reportFlightNotOffered(tripId, proposalId) : bookFlight(tripId, proposalId, leg), onChanged)
      setFailures(count => found.fallback ? count + 1 : 0)
      if (found.fallback === 'limit' && found.retry_at) deferUntil(Date.parse(found.retry_at))
      setResult(found)
    }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not check this flight.') }
    finally { inFlight.current = false; setBusy(false) }
  }
  return <div className="details-booking">
    {!result && <button type="button" className="trip-primary details-book-button" aria-busy={busy} disabled={busy || waitMinutes > 0} onClick={() => { void check() }}>{busy ? <AiStatus messages={checkMessages} /> : label}</button>}
    {!busy && waitMinutes > 0 && result?.fallback !== 'limit' && <p className="details-hint">{t('You can check again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    <BookSteps busy={busy} result={result} />
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <BookResultView result={result} leg={leg} failures={failures} onRecheck={waitMinutes > 0 ? undefined : () => { void check() }} onNotOffered={leg === 'round_trip' && waitMinutes === 0 ? () => { void check(true) } : undefined} />}
  </div>
}

export function RefreshView({ waitMinutes, busy, result, error, onRefresh, failures = 1 }: { waitMinutes: number; busy: boolean; result: FlightCheckResult | null; error: string; onRefresh: () => void; failures?: number }) {
  const { t, locale } = useLanguage()
  return <div className="details-refresh">
    <button type="button" className="details-small-button" aria-busy={busy} disabled={busy || waitMinutes > 0} onClick={onRefresh}>{busy ? <AiStatus messages={checkMessages} /> : <><RefreshIcon /> {t('Refresh the price')}</>}</button>
    {waitMinutes > 0 && !busy && <p className="details-hint">{t('You can check again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <PriceChange result={result} />}
    {result?.now_over_budget && <p className="details-note details-reveal" role="status">{t('With the new price, this proposal is over the group budget.')}</p>}
    {result?.fallback && <FallbackNote result={result} failures={failures} />}
    {result && <Alternative result={result} />}
  </div>
}

export function RefreshFlights({ tripId, proposalId, cooldownMinutes, onChanged }: { tripId: string; proposalId: string; cooldownMinutes: number; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<FlightCheckResult | null>(null)
  const [error, setError] = useState('')
  const [failures, setFailures] = useState(0)
  const { waitMinutes, start } = useCooldown(cooldownMinutes)
  async function refresh() {
    setBusy(true); setError(''); start()
    try {
      const found = await checkAndReload(() => refreshFlights(tripId, proposalId), onChanged)
      setFailures(count => found.fallback ? count + 1 : 0)
      setResult(found)
    }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not check this flight.') }
    finally { setBusy(false) }
  }
  return <RefreshView waitMinutes={waitMinutes} busy={busy} result={result} error={error} failures={failures} onRefresh={() => { void refresh() }} />
}
