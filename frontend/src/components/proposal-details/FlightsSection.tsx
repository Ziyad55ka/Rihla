import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import type { PriceAgeLimits } from '../../lib/proposals'
import type { FlightLeg, Flights, Proposal, TripType } from '../../types/proposal'
import { BookFlight, RefreshFlights } from './FlightActions'
import { InfoValue, PriceAgeBadge, PriceValue } from './values'

const tripTypeLabels: Record<TripType, string> = {
  round_trip: 'Round trip · One booking',
  split: 'Two separate bookings',
  one_way: 'One way only',
}

const clock = (value?: string | null) => /T(\d{2}:\d{2})/.exec(value ?? '')?.[1] ?? null

function Leg({ leg, proposal, separate }: { leg: FlightLeg; proposal: Proposal; separate: boolean }) {
  const { t, locale } = useLanguage()
  const departs = clock(leg.departure_time)
  const arrives = clock(leg.arrival_time)
  const stops = leg.stops
  return <div className="details-leg">
    <div className="details-leg-facts">
      <strong>{t(leg.direction === 'outbound' ? 'Outbound' : 'Return')}</strong>
      <span>{calendarDate(leg.date, locale)}</span>
      <InfoValue field={leg.airline} />
      {leg.flight_number && <span><bdi>{leg.flight_number}</bdi></span>}
      {departs && arrives && <span><bdi>{departs}</bdi> – <bdi>{arrives}</bdi></span>}
      <InfoValue field={leg.duration} />
      {stops !== undefined && stops !== null && <span>{stops === 0 ? t('Nonstop') : stops === 1 ? t('One stop') : stops === 2 ? t('Two stops') : t('{count} stops', { count: stops.toLocaleString(locale) })}</span>}
    </div>
    {separate && <>
      <PriceValue price={leg.price} unit="per person" />
      <BookFlight tripId={proposal.trip_id} proposalId={proposal.id} leg={leg.direction === 'outbound' ? 'outbound' : 'inbound'} label={t('Book this flight')} />
    </>}
    {!separate && leg.price.status !== 'Not available' && <PriceValue price={leg.price} unit="per person" />}
  </div>
}

function Route({ route, proposal, limits, cooldownMinutes, onChanged }: { route: Flights; proposal: Proposal; limits: PriceAgeLimits; cooldownMinutes: number; onChanged: () => void }) {
  const { t, language } = useLanguage()
  const separate = route.trip_type === 'split' || route.trip_type === 'one_way'
  return <div className="details-card">
    <div className="details-route-top">
      <h3><bdi>{placeName(route.origin, language)}</bdi> {language === 'ar' ? '←' : '→'} <bdi>{placeName(proposal.cities[0].city, language, proposal.cities[0].city_ar)}</bdi></h3>
      <span className="planning-badge details-badge--neutral">{t(tripTypeLabels[route.trip_type])}</span>
    </div>
    {route.group_availability === 'available' && <p className="details-hint">{t('Available for all travellers from your city')}</p>}
    {route.group_availability === 'not_found' && <p className="proposals-review" role="status">{t('We could not find one flight with room for all travellers from your city. You may need different flights.')}</p>}
    {route.legs.map((leg) => <Leg key={leg.direction} leg={leg} proposal={proposal} separate={separate} />)}
    {route.trip_type === 'one_way' && <p className="proposals-review">{t('The return price is not counted.')}</p>}
    {route.trip_type === 'split' && <p className="proposals-review">{t('Two separate bookings on two airlines. Book both.')}</p>}
    <div className="details-route-total">
      <span className="details-total-label">{t(route.trip_type === 'one_way' ? 'One way, per person' : 'Round trip, per person')}</span>
      <div className="details-value"><PriceValue price={route.price_per_person} /><PriceAgeBadge pricedAt={route.priced_at} limits={limits} canRefresh /></div>
      {route.trip_type === 'round_trip' && <BookFlight tripId={proposal.trip_id} proposalId={proposal.id} leg="round_trip" label={t('Book the trip')} />}
      <RefreshFlights tripId={proposal.trip_id} proposalId={proposal.id} pricedAt={route.priced_at} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />
    </div>
  </div>
}

export function FlightsSection({ proposal, isAdmin, limits, cooldownMinutes, onChanged }: { proposal: Proposal; isAdmin: boolean; limits: PriceAgeLimits; cooldownMinutes: number; onChanged: () => void }) {
  const { t } = useLanguage()
  return <section aria-labelledby="details-flights">
    <h2 id="details-flights">{t('Flights from your city')}</h2>
    <p className="details-section-note">{t('You only see flights from your departure city')}</p>
    {proposal.flights.length > 0
      ? proposal.flights.map((route) => <Route key={route.origin} route={route} proposal={proposal} limits={limits} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />)
      : <p className="proposals-review" role="status">{t(isAdmin ? 'This proposal has no flights from your city. Generate the proposals again to include it.' : 'This proposal has no flights from your city. Wait for the administrator to generate the proposals again.')}</p>}
  </section>
}
