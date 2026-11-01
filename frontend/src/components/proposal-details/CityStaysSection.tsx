import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { stayDates } from '../../lib/proposals'
import type { Proposal } from '../../types/proposal'
import { CityActivities } from './CityActivities'
import { nightsLabel } from './nights'
import { BookingLink, InfoValue, PriceValue } from './values'

export function CityStaysSection({ proposal }: { proposal: Proposal }) {
  const { t, locale, language } = useLanguage()
  const dates = stayDates(proposal)
  return <section aria-labelledby="details-cities">
    <h2 id="details-cities">{t('Cities and stays')}</h2>
    <p className="details-section-note">{t('In order, with the suggested hotel in each city')}</p>
    <ol className="details-cities">
      {proposal.cities.map((stay, index) => <li className="details-card" key={stay.order}>
        <h3><span className="details-order">{stay.order.toLocaleString(locale)}</span> <bdi>{stay.city}</bdi></h3>
        <p className="details-section-note">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>
        <div className="details-hotel">
          <p className="trip-eyebrow">{t('HOTEL')}</p>
          <InfoValue field={stay.hotel_name} sources={proposal.sources} />
          <PriceValue price={stay.hotel_price_per_night} unit="per night" sources={proposal.sources} />
          <BookingLink url={stay.booking_url} label={stay.hotel_name.value ? t('Search on Booking.com') : t('Search for hotels in {city}', { city: stay.city })} />
        </div>
        <CityActivities stay={stay} />
      </li>)}
    </ol>
  </section>
}
