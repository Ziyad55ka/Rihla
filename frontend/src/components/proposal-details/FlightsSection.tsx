import { airlineName } from '../../lib/airlines'
import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { type PriceAgeLimits, sourceLabel } from '../../lib/proposals'
import type { FlightLeg, Flights, Proposal, TripType } from '../../types/proposal'
import { BookFlight, FareLine, RefreshFlights } from './FlightActions'
import { InfoIcon } from './icons'
import { useSar } from './useSar'
import { InfoValue, PriceAgeBadge, PriceNotice, PriceValue } from './values'

const tripTypeLabels: Record<TripType, string> = {
  round_trip: 'Round trip · One booking',
  split: 'Two separate bookings',
  one_way: 'One way only',
}

const clock = (value?: string | null) => /[T ](\d{2}:\d{2})/.exec(value ?? '')?.[1] ?? null

function Leg({ leg, proposal, separate, cooldownMinutes, onChanged }: { leg: FlightLeg; proposal: Proposal; separate: boolean; cooldownMinutes: number; onChanged: () => void }) {
  const { t, locale, language } = useLanguage()
  const departs = clock(leg.departure_time)
  const arrives = clock(leg.arrival_time)
  const stops = leg.stops
  return <div className="details-leg">
    <div className="details-leg-facts">
      <strong>{t(leg.direction === 'outbound' ? 'Outbound' : 'Return')}</strong>
      <span>{calendarDate(leg.date, locale)}</span>
      <InfoValue field={leg.airline} display={(name) => airlineName(name, language)} />
      {leg.flight_number && <span className="details-flight-number"><bdi>{leg.flight_number}</bdi></span>}
      {departs && arrives && <span className="details-times"><bdi>{departs}</bdi> – <bdi>{arrives}</bdi></span>}
      <InfoValue field={leg.duration} />
      {stops !== undefined && stops !== null && <span>{stops === 0 ? t('Nonstop') : stops === 1 ? t('One stop') : stops === 2 ? t('Two stops') : t('{count} stops', { count: stops.toLocaleString(locale) })}</span>}
    </div>
    {separate && <>
      <PriceValue price={leg.price} unit="per person" startsFrom />
      <BookFlight tripId={proposal.trip_id} proposalId={proposal.id} leg={leg.direction === 'outbound' ? 'outbound' : 'inbound'} label={t('Book this flight')} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />
    </>}
  </div>
}

/** Each direction and the total, in the airlines' order. Never made by dividing. */
function PriceParts({ route }: { route: Flights }) {
  const { t } = useLanguage()
  const sar = useSar()
  const [outbound, back] = route.legs
  const total = route.price_per_person.amount_sar
  if (route.trip_type === 'one_way') return null
  if (outbound.price.amount_sar && back?.price.amount_sar && total) return <p className="details-parts">{t('Outbound {outbound} + return {back} = {total} per person', { outbound: sar(outbound.price.amount_sar), back: sar(back.price.amount_sar), total: sar(total) })}</p>
  return <p className="details-fact details-fact--soft"><InfoIcon /> <span>{t('The airline’s site may show the outbound price first, then add the return. The final total appears after you choose both flights.')}</span></p>
}

function Route({ route, proposal, allSameCity, limits, cooldownMinutes, onChanged }: { route: Flights; proposal: Proposal; allSameCity: boolean; limits: PriceAgeLimits; cooldownMinutes: number; onChanged: () => void }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const separate = route.trip_type === 'split' || route.trip_type === 'one_way'
  return <div className="details-card">
    <div className="details-route-top">
      <h3><bdi>{placeName(route.origin, language)}</bdi> {language === 'ar' ? '←' : '→'} <bdi>{placeName(proposal.cities[0].city, language, proposal.cities[0].city_ar)}</bdi></h3>
      <span className="planning-badge details-badge--neutral">{t(tripTypeLabels[route.trip_type])}</span>
    </div>
    {route.group_availability === 'available' && <p className="details-hint">{t('Available for all travellers from your city')}</p>}
    {route.group_availability === 'not_found' && <p className="proposals-review" role="status">{t('We could not find one flight with room for all travellers from your city. You may need different flights.')}</p>}
    {route.legs.map((leg) => <Leg key={leg.direction} leg={leg} proposal={proposal} separate={separate} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />)}
    {route.trip_type === 'one_way' && <p className="proposals-review">{t('The return price is not counted.')}</p>}
    {route.trip_type === 'split' && <p className="proposals-review">{t('Two separate bookings. Book both.')}</p>}
    <div className="details-route-total">
      <span className="details-total-label">{t(route.trip_type === 'one_way' ? 'One way, per person' : 'Round trip, per person')}</span>
      <div className="details-value details-price-row"><PriceValue price={route.price_per_person} startsFrom /><PriceAgeBadge pricedAt={route.priced_at} limits={limits} canRefresh /></div>
      <RefreshFlights tripId={proposal.trip_id} proposalId={proposal.id} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />
      {allSameCity && route.group_total_sar && <p className="details-hint">{t('{amount} for the whole group', { amount: sar(route.group_total_sar) })}</p>}
      <PriceParts route={route} />
      <FareLine facts={{ cabin_class: route.cabin_class ?? null, fare_name: route.fare_name ?? null, checked_bags: route.checked_bags ?? null, airline_fares: route.airline_fares }} />
      {route.provider && <p className="details-hint">{t(sourceLabel(route))}</p>}
      {route.fare_basis === 'solo' && route.solo_saving_sar && <p className="proposals-review" role="status">{t('The price shown is for each person booking alone.')} {t('It could be {amount} per person cheaper if each person books alone, but you may not be on the same flight.', { amount: sar(route.solo_saving_sar) })}</p>}
      {route.trip_type === 'round_trip' && <BookFlight tripId={proposal.trip_id} proposalId={proposal.id} leg="round_trip" label={t('Book the trip')} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />}
    </div>
  </div>
}

export function FlightsSection({ proposal, allSameCity, isAdmin, limits, cooldownMinutes, onChanged }: { proposal: Proposal; allSameCity: boolean; isAdmin: boolean; limits: PriceAgeLimits; cooldownMinutes: number; onChanged: () => void }) {
  const { t } = useLanguage()
  return <section aria-labelledby="details-flights">
    <h2 id="details-flights">{t('Flights from your city')}</h2>
    <p className="details-section-note">{t('You only see flights from your departure city')}</p>
    <PriceNotice />
    {proposal.flights.length > 0
      ? proposal.flights.map((route) => <Route key={route.origin} route={route} proposal={proposal} allSameCity={allSameCity} limits={limits} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />)
      : <p className="proposals-review" role="status">{t(isAdmin ? 'This proposal has no flights from your city. Generate the proposals again to include it.' : 'This proposal has no flights from your city. Wait for the administrator to generate the proposals again.')}</p>}
  </section>
}
