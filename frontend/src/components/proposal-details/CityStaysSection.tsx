import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { type PriceAgeLimits, safeLink, stayDates, staySource } from '../../lib/proposals'
import { adultsInLink, linkWithRooms, type RoomChoice, roomsFor, sharePerPerson } from '../../lib/rooms'
import { useCountUp } from '../../lib/motion'
import type { CityStay, Proposal } from '../../types/proposal'
import { CityActivities } from './CityActivities'
import { nightsLabel } from './nights'
import { PlacePhoto } from './PlacePhoto'
import { useSar } from './useSar'
import { InfoValue, PriceAgeBadge, PriceNotice, PriceValue, StayLink } from './values'

function RoomPicker({ choice, onChange }: { choice: RoomChoice; onChange: (choice: RoomChoice) => void }) {
  const { t } = useLanguage()
  const options: { value: RoomChoice; label: string }[] = [{ value: 'shared', label: 'Shared rooms (two to a room)' }, { value: 'own', label: 'A room for each person' }]
  return <fieldset className="details-rooms">
    <legend>{t('How will you share rooms?')}</legend>
    <div className="details-rooms-options">{options.map((option) => <label key={option.value} className={choice === option.value ? 'is-chosen' : undefined}>
      <input type="radio" name="details-rooms" value={option.value} checked={choice === option.value} onChange={() => onChange(option.value)} />
      <span>{t(option.label)}</span>
    </label>)}</div>
    <p className="details-hint">{t('This only changes what you see. It is not saved, and nobody else sees it.')}</p>
  </fieldset>
}

/** One person's share, gliding when the room choice changes. */
function PersonShare({ perRoom, rooms, adults, nights }: { perRoom: number; rooms: number; adults: number; nights: number }) {
  const { t } = useLanguage()
  const sar = useSar()
  const perNight = useCountUp(sharePerPerson(perRoom, rooms, adults))
  const shown = Math.round(perNight)
  return <p className="details-share"><strong>{t('About {amount} per person a night', { amount: sar(shown) })}</strong>{nights > 0 && <> · {t('About {amount} per person for the whole stay', { amount: sar(shown * nights) })}</>}</p>
}

function Hotel({ stay, city, proposal, limits, choice }: { stay: CityStay; city: string; proposal: Proposal; limits: PriceAgeLimits; choice: RoomChoice }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const named = Boolean(stay.hotel_name.value)
  const perNight = stay.hotel_price_per_night.amount_sar
  const direct = safeLink(stay.hotel_url ?? null)
  const adults = adultsInLink(stay.booking_url)
  const rooms = adults ? roomsFor(choice, adults) : null
  const search = stay.booking_url && rooms ? linkWithRooms(stay.booking_url, rooms) : stay.booking_url
  const labels = (language === 'ar' ? stay.labels_ar : stay.labels_en) ?? []
  if (!named && !perNight) return <div className="details-hotel details-hotel--empty">
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
    {labels.length > 0 && <ul className="details-labels">{labels.map((label) => <li key={label}><bdi>{label}</bdi></li>)}</ul>}
    {perNight
      ? <div className="details-value"><PriceValue price={stay.hotel_price_per_night} unit="per night" /><PriceAgeBadge pricedAt={stay.priced_at} limits={limits} /></div>
      : <p className="details-hint">{t('The price appears on the booking page')}</p>}
    {perNight && rooms && adults
      ? <PersonShare perRoom={Number(perNight)} rooms={rooms} adults={adults} nights={stay.nights} />
      : perNight && stay.nights > 0 && <p className="details-hint">{t('About {amount} for the whole stay', { amount: sar(Number(perNight) * stay.nights) })}</p>}
    {source && <p className="details-hint">{t('Source:')} <bdi>{source}</bdi></p>}
    {direct && <a className="trip-primary" href={direct} target="_blank" rel="noopener noreferrer">{t('Book this hotel')} <span aria-hidden="true">↗</span></a>}
    <StayLink url={search} label={direct ? t('Compare on Booking') : named ? t('Search on Booking.com') : t('Search for hotels in {city}', { city })} />
    {named && safeLink(search) && !direct && <a className="details-text-link" href={safeLink(search) as string} target="_blank" rel="noopener noreferrer">{t('See photos of this hotel')} <span aria-hidden="true">↗</span></a>}
  </div>
}

export function CityStaysSection({ proposal, limits, defaultRooms = 'shared' }: { proposal: Proposal; limits: PriceAgeLimits; defaultRooms?: RoomChoice }) {
  const { t, locale, language } = useLanguage()
  const [choice, setChoice] = useState<RoomChoice>(defaultRooms)
  const dates = stayDates(proposal)
  const canChoose = proposal.cities.some((stay) => (adultsInLink(stay.booking_url) ?? 0) > 1)
  return <section aria-labelledby="details-cities">
    <h2 id="details-cities">{t('Hotels and stays')}</h2>
    <p className="details-section-note">{t('In order, with the suggested hotel in each city')}</p>
    <PriceNotice />
    {canChoose && <RoomPicker choice={choice} onChange={setChoice} />}
    <ol className="details-cities">
      {proposal.cities.map((stay, index) => {
        const city = placeName(stay.city, language, stay.city_ar)
        return <li className="details-card details-city" key={stay.order}>
          <PlacePhoto image={stay.image} place={city} />
          <h3><span className="details-order">{stay.order.toLocaleString(locale)}</span> <bdi>{city}</bdi></h3>
          <p className="details-section-note">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>
          <Hotel stay={stay} city={city} proposal={proposal} limits={limits} choice={choice} />
          <CityActivities stay={stay} />
        </li>
      })}
    </ol>
  </section>
}
