import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { bookingLink, type PriceAgeLimits, hotelLink, localTime, stayDates } from '../../lib/proposals'
import type { CityStay, Proposal } from '../../types/proposal'
import { CityActivities } from './CityActivities'
import { Hint } from './Hint'
import { ExternalIcon, StaysTitleIcon } from './icons'
import { nightsLabel } from './nights'
import { PlacePhoto } from './PlacePhoto'
import { SectionTitle } from './SectionTitle'
import { PriceAgeBadge, PriceValue, StatusBadge, StayNotice } from './values'

function Hotel({ stay, city, limits }: { stay: CityStay; city: string; limits: PriceAgeLimits }) {
  const { t } = useLanguage()
  const name = stay.hotel_name.value
  const price = stay.hotel_price_per_night
  const direct = hotelLink(stay.hotel_url ?? null)
  const search = bookingLink(stay.booking_url)
  const roomsHint = <Hint text={t('Check for enough rooms for the group.')} />
  const average = stay.hotel_source?.includes('market average')
  const nearby = stay.hotel_source?.includes('nearby-date')
  if (!name && !price.amount_sar) return <div className="details-hotel details-hotel--empty">
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {search
      ? <a className="trip-primary" href={search} target="_blank" rel="noopener noreferrer">{t('Search for hotels in {city}', { city })} <ExternalIcon /></a>
      : <p className="details-hint">{t('No booking link')}</p>}
    <p className="details-hint details-inline">{t('We did not find a confirmed hotel in {city}', { city })}{roomsHint}</p>
    <p className="details-hint" role="status">{t('No reliable hotel price was available. Open the booking search to check live prices for your dates and group.')}</p>
  </div>
  return <div className="details-hotel">
    {average && <p className="details-hint">{t('Average for comparable hotels, per room per night. Not a quote for a particular hotel.')}</p>}
    {nearby && <p className="details-hint" role="status">{t('Reference average from nearby dates. Hotel availability and the final price for your trip are not confirmed; search Booking for your dates.')}</p>}
    {stay.hotel_stars && <p className="details-hint">{t('{stars} stars', { stars: stay.hotel_stars })}</p>}
    {name ? <h4 className="details-hotel-name"><bdi>{name}</bdi>{stay.hotel_name.status === 'Unconfirmed' && <StatusBadge status="Unconfirmed" />}</h4> : <p className="details-no-hotel">{t('The hotel is not confirmed yet')}</p>}
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {price.amount_sar
      ? <><div className="details-value details-share"><PriceValue price={price} unit="per night" /><PriceAgeBadge pricedAt={stay.priced_at} limits={limits} />{stay.hotel_source && <Hint text={`${t('Source:')} ${stay.hotel_source}`} />}</div>
        {price.status === 'Unconfirmed' && !nearby && <p className="details-hint">{t('Typical nightly estimate, not a live quote. Open the booking search to confirm the total for your dates and group.')}</p>}</>
      : <p className="details-hint" role="status">{t('No reliable hotel price was available. Open the booking search to check live prices for your dates and group.')}</p>}
    <div className="details-hotel-actions">
      {direct
        ? <>
          <a className="trip-primary" href={direct} target="_blank" rel="noopener noreferrer">{t(average ? 'Compare hotel prices' : 'Check hotel prices')} <ExternalIcon /></a>
          {search && <a className="details-text-link" href={search} target="_blank" rel="noopener noreferrer">{t('Compare on Booking')} <ExternalIcon /></a>}
        </>
        : search
          ? <a className="trip-primary" href={search} target="_blank" rel="noopener noreferrer">{name ? t('Search on Booking.com') : t('Search for hotels in {city}', { city })} <ExternalIcon /></a>
          : <p className="details-hint">{t('No booking link')}</p>}
      {roomsHint}
    </div>
  </div>
}

/** The member's own flight home, when it leaves before dawn on the last day. */
function earlyHomeTime(proposal: Proposal): string | null {
  const back = proposal.flights[0]?.legs.find((leg) => leg.direction === 'return')
  const when = back?.departure_time ?? ''
  if (!when.startsWith(proposal.end_date)) return null
  const hour = Number(when.slice(11, 13))
  return Number.isFinite(hour) && hour < 6 ? when.slice(11, 16) : null
}

export function CityStaysSection({ proposal, limits }: { proposal: Proposal; limits: PriceAgeLimits }) {
  const { t, locale, language } = useLanguage()
  const dates = stayDates(proposal)
  const early = earlyHomeTime(proposal)
  const last = proposal.cities.length - 1
  return <section aria-labelledby="details-cities">
    <SectionTitle id="details-cities" icon={<StaysTitleIcon />} title={t('Hotels and stays')} />
    <StayNotice />
    <ol className="details-cities">
      {proposal.cities.map((stay, index) => {
        const city = placeName(stay.city, language, stay.city_ar)
        return <li className="details-card details-city" key={stay.order}>
          <PlacePhoto image={stay.image} place={city} />
          <h3><span className="details-order">{stay.order.toLocaleString(locale)}</span> <bdi>{city}</bdi></h3>
          <p className="details-hint">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>
          {early && index === last && <p className="details-fees" role="note">{t('Your return flight leaves at {time} on {date}. All planned hotel nights are included; confirm checkout and your transfer to the airport.', { time: localTime(early, locale), date: calendarDate(proposal.end_date, locale) })}</p>}
          <Hotel stay={stay} city={city} limits={limits} />
          <CityActivities stay={stay} />
        </li>
      })}
    </ol>
  </section>
}
