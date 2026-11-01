import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import type { FlightLeg, Flights, Proposal, TripType } from '../../types/proposal'
import { BookingLink, InfoValue, PriceValue } from './values'

const tripTypeLabels: Record<TripType, string> = {
  round_trip: 'Round trip · One booking',
  split: 'Two separate bookings',
  one_way: 'One way only',
}

function Leg({ leg, proposal, separate }: { leg: FlightLeg; proposal: Proposal; separate: boolean }) {
  const { t, locale } = useLanguage()
  return <div className="details-leg">
    <strong>{t(leg.direction === 'outbound' ? 'Outbound' : 'Return')}</strong>
    <span>{calendarDate(leg.date, locale)}</span>
    <InfoValue field={leg.airline} sources={proposal.sources} />
    <InfoValue field={leg.duration} sources={proposal.sources} />
    {separate && <>
      <PriceValue price={leg.price} unit="per person" sources={proposal.sources} />
      <BookingLink url={leg.booking_url} label={t('Book this flight')} solid />
    </>}
  </div>
}

function Route({ route, proposal }: { route: Flights; proposal: Proposal }) {
  const { t, language } = useLanguage()
  const separate = route.trip_type !== 'round_trip'
  return <div className="details-card">
    <div className="details-route-top">
      <h3><bdi>{route.origin}</bdi> {language === 'ar' ? '←' : '→'} <bdi>{proposal.cities[0].city}</bdi></h3>
      <span className="planning-badge details-badge--neutral">{t(tripTypeLabels[route.trip_type])}</span>
    </div>
    {route.legs.map((leg) => <Leg key={leg.direction} leg={leg} proposal={proposal} separate={separate} />)}
    {route.trip_type === 'one_way' && <p className="proposals-review">{t('The return price is not counted.')}</p>}
    <div className="details-route-total">
      {route.trip_type === 'split' && <p className="details-hint">{t('The total is an estimate, because these are two bookings.')}</p>}
      <PriceValue price={route.price_per_person} unit="per person" sources={proposal.sources} />
      {!separate && <BookingLink url={route.legs[0]?.booking_url ?? null} label={t('Book the trip')} solid />}
    </div>
  </div>
}

export function FlightsSection({ proposal, isAdmin }: { proposal: Proposal; isAdmin: boolean }) {
  const { t } = useLanguage()
  return <section aria-labelledby="details-flights">
    <h2 id="details-flights">{t('Flights from your city')}</h2>
    <p className="details-section-note">{t('You only see flights from your departure city')}</p>
    {proposal.flights.length > 0
      ? proposal.flights.map((route) => <Route key={route.origin} route={route} proposal={proposal} />)
      : <p className="proposals-review" role="status">{t(isAdmin ? 'This proposal has no flights from your city. Generate the proposals again to include it.' : 'This proposal has no flights from your city. Wait for the administrator to generate the proposals again.')}</p>}
  </section>
}
