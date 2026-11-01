import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { type PriceAgeLimits, safeLink, stayDates, staySource } from '../../lib/proposals'
import type { CityStay, Proposal } from '../../types/proposal'
import { CityActivities } from './CityActivities'
import { nightsLabel } from './nights'
import { PlacePhoto } from './PlacePhoto'
import { useSar } from './useSar'
import { InfoValue, PriceAgeBadge, PriceNotice, PriceValue, StayLink } from './values'

function Hotel({ stay, city, proposal, limits }: { stay: CityStay; city: string; proposal: Proposal; limits: PriceAgeLimits }) {
  const { t } = useLanguage()
  const sar = useSar()
  const named = Boolean(stay.hotel_name.value)
  const perNight = stay.hotel_price_per_night.amount_sar
  const direct = safeLink(stay.hotel_url ?? null)
  const search = stay.booking_url
  if (!named && !perNight) return <div className="details-hotel">
    <p className="trip-eyebrow">{t('HOTEL')}</p>
    <p className="details-no-hotel">{t('We did not find a confirmed hotel in {city}', { city })}</p>
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    <StayLink url={search} label={t('Search for hotels in {city}', { city })} />
  </div>
  const source = staySource(stay, proposal.sources)
  return <div className="details-hotel">
    <p className="trip-eyebrow">{t('HOTEL')}</p>
    {named ? <InfoValue field={stay.hotel_name} /> : <p className="details-no-hotel">{t('The hotel is not confirmed yet')}</p>}
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {perNight
      ? <div className="details-value"><PriceValue price={stay.hotel_price_per_night} unit="per night" /><PriceAgeBadge pricedAt={stay.priced_at} limits={limits} /></div>
      : <p className="details-hint">{t('The price appears on the booking page')}</p>}
    {perNight && stay.nights > 0 && <p className="details-hint">{t('About {amount} for the whole stay', { amount: sar(Number(perNight) * stay.nights) })}</p>}
    {source && <p className="details-hint">{t('Source:')} <bdi>{source}</bdi></p>}
    {direct && <a className="trip-primary" href={direct} target="_blank" rel="noopener noreferrer">{t('Book this hotel')} <span aria-hidden="true">↗</span></a>}
    <StayLink url={search} label={direct ? t('Compare on Booking') : named ? t('Search on Booking.com') : t('Search for hotels in {city}', { city })} />
    {named && safeLink(search) && !direct && <a className="details-text-link" href={safeLink(search) as string} target="_blank" rel="noopener noreferrer">{t('See photos of this hotel')} <span aria-hidden="true">↗</span></a>}
  </div>
}

export function CityStaysSection({ proposal, limits }: { proposal: Proposal; limits: PriceAgeLimits }) {
  const { t, locale, language } = useLanguage()
  const dates = stayDates(proposal)
  return <section aria-labelledby="details-cities">
    <h2 id="details-cities">{t('Cities and stays')}</h2>
    <p className="details-section-note">{t('In order, with the suggested hotel in each city')}</p>
    <PriceNotice />
    <ol className="details-cities">
      {proposal.cities.map((stay, index) => {
        const city = placeName(stay.city, language, stay.city_ar)
        return <li className="details-card details-city" key={stay.order}>
          <PlacePhoto image={stay.image} place={city} />
          <h3><span className="details-order">{stay.order.toLocaleString(locale)}</span> <bdi>{city}</bdi></h3>
          <p className="details-section-note">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>
          <Hotel stay={stay} city={city} proposal={proposal} limits={limits} />
          <CityActivities stay={stay} />
        </li>
      })}
    </ol>
  </section>
}
