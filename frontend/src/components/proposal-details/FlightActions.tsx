import { useEffect, useState } from 'react'
import { checkMessages } from '../../lib/aiStatus'
import { airlineName } from '../../lib/airlines'
import { useLanguage } from '../../lib/language'
import { bookFlight, checkAndReload, type BookLeg, type FlightCheckResult, type FlightFacts, type FlightFallback, linkFractionLeft, linkMinutesLeft, localTime, priceChange, refreshFlights, safeLink, sourceLabel } from '../../lib/proposals'
import type { AirlineFareNote } from '../../types/proposal'
import { AiStatus } from '../AiStatus'
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

/** The source's own fare and bag first, then what is generally known of the airline. */
export function FareLine({ facts }: { facts: Pick<FlightFacts, 'cabin_class' | 'fare_name' | 'checked_bags'> & { airline_fares?: AirlineFareNote[] } }) {
  const { t, language, locale } = useLanguage()
  const cabin = facts.fare_name ?? (facts.cabin_class ? t(cabinLabels[facts.cabin_class] ?? 'Economy') : null)
  const bags = facts.checked_bags
  if (bags !== null && bags !== undefined) return <p className="details-fact"><BagIcon /> <span>{cabin && <><bdi>{cabin}</bdi> · </>}{bags === 0 ? t('No checked bag') : t('{count} checked bags', { count: bags.toLocaleString(locale) })}</span></p>
  const notes = facts.airline_fares ?? []
  if (notes.length === 0) return <p className="details-fact"><BagIcon /> <span>{cabin && <><bdi>{cabin}</bdi> · </>}{t('The price is for the cheapest fare available, and may not include a bag.')}</span></p>
  return <div className="details-fare-notes">
    {notes.map((note) => <p className="details-fact" key={note.code}><BagIcon /> <span>
      <bdi>{language === 'ar' ? note.name_ar : note.name_en}</bdi>: <bdi>{language === 'ar' ? note.fare_ar : note.fare_en}</bdi> · {note.checked_kg === null || note.checked_kg === undefined ? t('Check the bag on the airline’s site') : note.checked_kg === 0 ? t('No checked bag') : t('Checked bag {kg} kg', { kg: note.checked_kg.toLocaleString(locale) })}
    </span></p>)}
    <p className="details-hint">{t('General information about the airline’s cheapest fare, not a promise for your ticket.')}</p>
  </div>
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
  if (change) return <p className={`details-change details-reveal ${change.difference > 0 ? 'details-change--up' : 'details-change--down'}`} role="status">{t('Was {old} → now {new} ({difference})', { old: sar(change.previous), new: sar(change.price), difference: `${change.difference > 0 ? '+' : '−'}${sar(Math.abs(change.difference))}` })}</p>
  if (result.price_sar && !result.fallback && result.checked_at) return <p className="details-change details-reveal" role="status"><CheckIcon /> {t('Checked just now. The price is the same.')}</p>
  return null
}

function Alternative({ result }: { result: FlightCheckResult }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const found = result.alternative
  if (!found) return null
  const link = safeLink(found.url)
  const titles = { gone: 'The original flight is gone. We found a replacement.', no_link: 'This flight can’t be opened directly. This one can.', cheaper: 'A cheaper option you can book directly', agent: 'Cheaper through a travel agent, for the same flight' }
  return <div className="details-alternative details-reveal">
    <p className="details-alternative-title"><SwapIcon /> {t(titles[found.reason])}</p>
    <ChosenFlight facts={found} />
    {found.price_sar && <p className="details-alternative-price">{t('From {amount}', { amount: sar(found.price_sar) })} <span className="details-hint">{t('per person')}</span></p>}
    {found.seller && <p className="details-hint">{t('Sold by {seller}', { seller: airlineName(found.seller, language) })}</p>}
    {found.reason === 'agent' && <p className="details-hint">{t('This is an agent, not the airline, so check its fees and terms before paying.')}</p>}
    {found.within_budget === false && <p className="proposals-review">{t('This option is over the group budget.')}</p>}
    {link && found.reason !== 'gone' && <a className="trip-secondary" href={link} target="_blank" rel="noopener noreferrer">{t('Open this flight')} <span aria-hidden="true">↗</span></a>}
  </div>
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
  return <svg className="details-ring" viewBox="0 0 36 36" width="28" height="28" aria-hidden="true" focusable="false">
    <circle className="details-ring-track" cx="18" cy="18" r="15" pathLength="100" />
    <circle className="details-ring-value" cx="18" cy="18" r="15" pathLength="100" strokeDasharray="100" strokeDashoffset={100 - fraction * 100} />
  </svg>
}

export function BookResultView({ result, leg = 'round_trip', onRecheck, now }: { result: FlightCheckResult; leg?: BookLeg; onRecheck?: () => void; now?: number }) {
  const { t, language, locale } = useLanguage()
  const ticking = useNow(!result.fallback && Boolean(result.checked_at))
  const time = now ?? ticking
  const left = linkMinutesLeft(result.checked_at, result.link_valid_minutes, time)
  const expired = !result.fallback && left === 0
  const link = safeLink(result.url)
  return <div className="details-book-result details-reveal">
    <PriceChange result={result} />
    {result.fallback && <p>{t(fallbackMessages[result.fallback])}</p>}
    {!result.fallback && <>
      <FareLine facts={result} />
      <p className="details-fact"><InfoIcon /> <span>{t(sourceLabel({ ...result, price_source: result.seller_type ? 'seller' : 'search' }))}{result.seller && <> · {t('Sold by {seller}', { seller: airlineName(result.seller, language) })}</>}</span></p>
      {!result.exact_flight && <p className="details-hint">{t('This is a results page, so choose the flight yourself.')}</p>}
      <BookGuide result={result} leg={leg} />
    </>}
    {expired
      ? <><p className="proposals-review" role="status"><ClockIcon /> {t('This link may have expired. Check again.')}</p>{onRecheck && <button type="button" className="trip-secondary" onClick={onRecheck}>{t('Check again')}</button>}</>
      : <>
        {link && <a className={result.fallback ? 'trip-secondary' : 'trip-primary'} href={link} target="_blank" rel="noopener noreferrer">{t(result.fallback ? 'Open the search results' : 'Open the booking page')} <span aria-hidden="true">↗</span></a>}
        {!result.fallback && left !== null && <p className="details-timer" role="timer"><TimerRing fraction={linkFractionLeft(result.checked_at, result.link_valid_minutes, time)} /> {left === 1 ? t('The link should work for about a minute more. Finish booking now.') : t('The link should work for about {count} more minutes. Finish booking now.', { count: left.toLocaleString(locale) })}</p>}
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
  const { t, locale } = useLanguage()
  const stage = busy ? 1 : result ? 3 : 0
  if (stage === 0) return null
  const steps = ['Checking the price and seats now…', 'Check the result', 'Open the booking page']
  return <div className="details-steps-wrap">
    <div className="details-steps-bar" role="progressbar" aria-label={t('Booking steps')} aria-valuemin={0} aria-valuemax={3} aria-valuenow={stage}><span style={{ transform: `scaleX(${stage / 3})` }} /></div>
    <ol className="details-steps">{steps.map((label, index) => {
      const done = index + 1 < stage && !(stage === 3 && index === 1)
      const now = index + 1 === stage || (stage === 3 && index === 1)
      return <li key={label} className={done ? 'is-done' : now ? 'is-now' : ''} aria-current={index + 1 === stage ? 'step' : undefined}><span aria-hidden="true">{done ? <CheckIcon /> : (index + 1).toLocaleString(locale)}</span>{t(label)}</li>
    })}</ol>
  </div>
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
    {!result && <button type="button" className="trip-primary" aria-busy={busy} disabled={busy || waitMinutes > 0} onClick={() => { void check() }}>{busy ? <AiStatus messages={checkMessages} /> : label}</button>}
    {!result && !busy && waitMinutes > 0 && <p className="details-hint">{t('You can check again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    <BookSteps busy={busy} result={result} />
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <BookResultView result={result} leg={leg} onRecheck={waitMinutes > 0 ? undefined : () => { void check() }} />}
    {!result && !busy && <p className="details-hint">{t('We check the flight when you press, then give you the seller’s page.')}</p>}
  </div>
}

export function RefreshView({ waitMinutes, busy, result, error, onRefresh }: { waitMinutes: number; busy: boolean; result: FlightCheckResult | null; error: string; onRefresh: () => void }) {
  const { t, locale } = useLanguage()
  const link = result?.fallback ? safeLink(result.url) : null
  return <div className="details-refresh">
    <button type="button" className="trip-secondary" aria-busy={busy} disabled={busy || waitMinutes > 0} onClick={onRefresh}>{busy ? <AiStatus messages={checkMessages} /> : t('Refresh the price')}</button>
    {waitMinutes > 0 && !busy && <p className="details-hint">{t('You can check again in {count} minutes.', { count: waitMinutes.toLocaleString(locale) })}</p>}
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {result && <PriceChange result={result} />}
    {result?.now_over_budget && <p className="proposals-review details-reveal" role="status">{t('With the new price, this proposal is over the group budget.')}</p>}
    {result?.fallback && <p className="proposals-review details-reveal" role="status">{t(fallbackMessages[result.fallback])}</p>}
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
