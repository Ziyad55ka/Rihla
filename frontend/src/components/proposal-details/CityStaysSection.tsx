import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { type PriceAgeLimits, stayDates } from '../../lib/proposals'
import type { Proposal } from '../../types/proposal'
import { CityActivities } from './CityActivities'
import { nightsLabel } from './nights'
import { useSar } from './useSar'
import { InfoValue, PriceAgeBadge, PriceValue, StayLink } from './values'

export function CityStaysSection({ proposal, limits }: { proposal: Proposal; limits: PriceAgeLimits }) {
  const { t, locale, language } = useLanguage()
  const sar = useSar()
  const dates = stayDates(proposal)
  return <section aria-labelledby="details-cities">
    <h2 id="details-cities">{t('Cities and stays')}</h2>
    <p className="details-section-note">{t('In order, with the suggested hotel in each city')}</p>
    <ol className="details-cities">
      {proposal.cities.map((stay, index) => {
        const city = placeName(stay.city, language, stay.city_ar)
        const perNight = stay.hotel_price_per_night.amount_sar
        return <li className="details-card" key={stay.order}>
          <h3><span className="details-order">{stay.order.toLocaleString(locale)}</span> <bdi>{city}</bdi></h3>
          <p className="details-section-note">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>
          <div className="details-hotel">
            <p className="trip-eyebrow">{t('HOTEL')}</p>
            <InfoValue field={stay.hotel_name} />
            {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
            <div className="details-value"><PriceValue price={stay.hotel_price_per_night} unit="per night" />{perNight && <PriceAgeBadge pricedAt={stay.priced_at} limits={limits} />}</div>
            {perNight && stay.nights > 0 && <p className="details-hint">{t('About {amount} for the whole stay', { amount: sar(Number(perNight) * stay.nights) })}</p>}
            <StayLink url={stay.booking_url} label={stay.hotel_name.value ? t('Search on Booking.com') : t('Search for hotels in {city}', { city })} />
          </div>
          <CityActivities stay={stay} />
        </li>
      })}
    </ol>
  </section>
}
