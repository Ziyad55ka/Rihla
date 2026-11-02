import { useLanguage } from '../../lib/language'
import { placeName } from '../../lib/places'
import { type PriceAgeLimits, sourceLabel } from '../../lib/proposals'
import type { Flights, Proposal, TripType } from '../../types/proposal'
import { BookFlight, FareLine, RefreshFlights, SplitBooking } from './FlightActions'
import { FlightLine } from './FlightLine'
import { Hint } from './Hint'
import { FlightsTitleIcon, ForwardIcon, UsersIcon } from './icons'
import { SectionTitle } from './SectionTitle'
import { useSar } from './useSar'
import { PriceAgeBadge, PriceNotice, PriceValue } from './values'

const tripTypeLabels: Partial<Record<TripType, string>> = {
  split: 'Two separate bookings',
  one_way: 'One way only',
}

/** Each direction and the total, in the airlines' order. Never made by dividing. */
function PriceParts({ route }: { route: Flights }) {
  const { t } = useLanguage()
  const sar = useSar()
  const [outbound, back] = route.legs
  const total = route.price_per_person.amount_sar
  if (route.trip_type === 'one_way' || !outbound.price.amount_sar || !back?.price.amount_sar || !total) return null
  return <p className="details-parts">{t('Outbound {outbound} + return {back} = {total} per person', { outbound: sar(outbound.price.amount_sar), back: sar(back.price.amount_sar), total: sar(total) })}</p>
}

function Route({ route, proposal, limits, cooldownMinutes, onChanged }: { route: Flights; proposal: Proposal; limits: PriceAgeLimits; cooldownMinutes: number; onChanged: () => void }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const typeLabel = tripTypeLabels[route.trip_type]
  const home = placeName(route.origin, language)
  const away = placeName(proposal.cities[0].city, language, proposal.cities[0].city_ar)
  const partsShown = route.legs.length === 2 && route.legs.every((leg) => leg.price.amount_sar)
  return <div className="details-card details-card--featured">
    <div className="details-route-top">
      <h3><bdi>{home}</bdi> <ForwardIcon rtl={language === 'ar'} /> <bdi>{away}</bdi></h3>
      {typeLabel && <span className="planning-badge details-badge--neutral">{t(typeLabel)}</span>}
      {route.group_availability === 'available' && <span className="details-chip"><UsersIcon /> {t('Available for all travellers from your city')}</span>}
    </div>
    {route.group_availability === 'not_found' && <p className="details-note" role="status">{t('We could not find one flight with room for all travellers from your city. You may need different flights.')}</p>}
    {route.legs.map((leg) => {
      const out = leg.direction === 'outbound'
      return <FlightLine key={leg.direction} leg={leg} from={out ? home : away} to={out ? away : home} fromCode={out ? route.origin_airport : route.destination_airport} toCode={out ? route.destination_airport : route.origin_airport} />
    })}
    <div className="details-price-block">
      <div className="details-price-main" key={route.price_per_person.amount_sar ?? 'none'}>
        <span className="details-total-label">{t(route.trip_type === 'one_way' ? 'One way, per person' : 'Round trip, per person')}{route.provider && <Hint text={t(sourceLabel(route))} />}</span>
        <div className="details-value details-price-row"><PriceValue price={route.price_per_person} startsFrom /><PriceAgeBadge pricedAt={route.priced_at} limits={limits} canRefresh /></div>
      </div>
      <RefreshFlights tripId={proposal.trip_id} proposalId={proposal.id} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />
    </div>
    <PriceParts route={route} />
    <div className="details-chips">
      <FareLine facts={{ cabin_class: route.cabin_class ?? null, fare_name: route.fare_name ?? null, checked_bags: route.checked_bags ?? null, airline_fares: route.airline_fares }} />
      {route.trip_type === 'one_way' && <span className="details-chip">{t('The return price is not counted.')}</span>}
      {route.fare_basis === 'solo' && route.solo_saving_sar && <span className="details-chip">{t('The price shown is for each person booking alone.')}<Hint text={t('It could be {amount} per person cheaper if each person books alone, but you may not be on the same flight.', { amount: sar(route.solo_saving_sar) })} /></span>}
      {!partsShown && route.trip_type === 'round_trip' && <span className="details-chip details-chip--plain">{t('Sites may show the outbound price first')}<Hint text={t('The airline’s site may show the outbound price first, then add the return. The final total appears after you choose both flights.')} /></span>}
    </div>
    {route.trip_type === 'split'
      ? <SplitBooking tripId={proposal.trip_id} proposalId={proposal.id} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />
      : <BookFlight tripId={proposal.trip_id} proposalId={proposal.id} leg={route.trip_type === 'one_way' ? 'outbound' : 'round_trip'} label={t('Book')} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />}
  </div>
}

export function FlightsSection({ proposal, isAdmin, limits, cooldownMinutes, onChanged }: { proposal: Proposal; isAdmin: boolean; limits: PriceAgeLimits; cooldownMinutes: number; onChanged: () => void }) {
  const { t } = useLanguage()
  return <section aria-labelledby="details-flights">
    <SectionTitle id="details-flights" icon={<FlightsTitleIcon />} title={t('Flights from your city')} hint={<Hint text={t('You only see flights from your departure city')} />} />
    <PriceNotice />
    {proposal.flights.length > 0
      ? proposal.flights.map((route) => <Route key={route.origin} route={route} proposal={proposal} limits={limits} cooldownMinutes={cooldownMinutes} onChanged={onChanged} />)
      : <p className="details-note" role="status">{t(isAdmin ? 'This proposal has no flights from your city. Generate the proposals again to include it.' : 'This proposal has no flights from your city. Wait for the administrator to generate the proposals again.')}</p>}
  </section>
}
