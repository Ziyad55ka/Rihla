import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { bookingLink, type PriceAgeLimits, safeLink, stayDates } from '../../lib/proposals'
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
  const direct = safeLink(stay.hotel_url ?? null)
  const search = bookingLink(stay.booking_url)
  const roomsHint = <Hint text={t('Check for enough rooms for the group.')} />
  if (!name && !price.amount_sar) return <div className="details-hotel details-hotel--empty">
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {search
      ? <a className="trip-primary" href={search} target="_blank" rel="noopener noreferrer">{t('Search for hotels in {city}', { city })} <ExternalIcon /></a>
      : <p className="details-hint">{t('No booking link')}</p>}
    <p className="details-hint details-inline">{t('We did not find a confirmed hotel in {city}', { city })}{roomsHint}</p>
  </div>
  return <div className="details-hotel">
    {name ? <h4 className="details-hotel-name"><bdi>{name}</bdi>{stay.hotel_name.status === 'Unconfirmed' && <StatusBadge status="Unconfirmed" />}</h4> : <p className="details-no-hotel">{t('The hotel is not confirmed yet')}</p>}
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {price.amount_sar
      ? <div className="details-value details-share"><PriceValue price={price} unit="per night" /><PriceAgeBadge pricedAt={stay.priced_at} limits={limits} />{stay.hotel_source && <Hint text={`${t('Source:')} ${stay.hotel_source}`} />}</div>
      : <p className="details-hint">{t('The price appears on the booking page')}</p>}
    <div className="details-hotel-actions">
      {direct
        ? <>
          <a className="trip-primary" href={direct} target="_blank" rel="noopener noreferrer">{t('Book this hotel')} <ExternalIcon /></a>
          {search && <a className="details-text-link" href={search} target="_blank" rel="noopener noreferrer">{t('Compare on Booking')} <ExternalIcon /></a>}
        </>
        : search
          ? <a className="trip-primary" href={search} target="_blank" rel="noopener noreferrer">{name ? t('Search on Booking.com') : t('Search for hotels in {city}', { city })} <ExternalIcon /></a>
          : <p className="details-hint">{t('No booking link')}</p>}
      {roomsHint}
    </div>
  </div>
}

export function CityStaysSection({ proposal, limits }: { proposal: Proposal; limits: PriceAgeLimits }) {
  const { t, locale, language } = useLanguage()
  const dates = stayDates(proposal)
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
          <Hotel stay={stay} city={city} limits={limits} />
          <CityActivities stay={stay} />
        </li>
      })}
    </ol>
  </section>
}
